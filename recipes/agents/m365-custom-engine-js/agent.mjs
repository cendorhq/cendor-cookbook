/**
 * Govern a **Microsoft 365 Agents SDK custom engine agent** (TypeScript/JS) — the wrap map, one file.
 *
 * A *custom engine agent* is the tile where **you** hold the model client ("you manage orchestration
 * and provide your own LLM" — Microsoft's words). Your process hosts `AgentApplication` behind
 * `POST /api/messages`, and the model call inside your message handler is an ordinary provider-SDK
 * call. Your call, your tokens, your bill — which is exactly why cendor applies.
 *
 * Everything here is real host code from `@microsoft/agents-hosting` + `-express` plus the published
 * `@cendor/*` packages. The only stand-in is the provider client: `makeClient()` returns a small
 * async fake so this runs in CI with **no key and no network**. Swap it for
 * `instrument(new OpenAI())` and nothing else changes — `instrument()` detection is structural.
 *
 * The wrap map, in the order the handler hits it:
 *
 *   (A) pre-flight estimate + block .... preflight()      refuse before spending anything
 *   (B) per-turn budget scope .......... turnBudget()     wraps the WHOLE body (tool loops)
 *   (C) per-conversation cap ........... SpendLedger      TurnState, Decimal-as-string
 *   (D) attribution tags ............... turnScope()      conversation.id (never AAD by default)
 *   (E) mid-stream break ............... turnBudget({stream:true})
 *
 *   + instrument() on the client, guardrails in/out, acttrace guard + hash-chained audit,
 *     contextkit/squeeze history assembly, and the `channelData.cendor` reply envelope.
 *
 * ⚠️ This host runs `/api/messages` with no configured client id, i.e. **anonymous** — the supported
 * local posture and an **open relay in production**. See the README's "Before you deploy this" box.
 */
import { AsyncLocalStorage } from 'node:async_hooks';
import express from 'express';
import { Decimal } from 'decimal.js';
import {
  LLMCall,
  Money,
  addAmbientProvider,
  addInterceptor,
  bus,
  instrument,
  prices,
  removeAmbientProvider,
  removeInterceptor,
  tokens,
  trace,
} from '@cendor/core';
import { AuditLog, Policy, PolicyViolation, guard } from '@cendor/acttrace';
import { Block, Context as CkContext } from '@cendor/contextkit';
import { GuardrailTripped, evaluateAsync, presets, rules } from '@cendor/guardrails';
import { compress } from '@cendor/squeeze';
import { BudgetExceeded, track, withBudget } from '@cendor/tokenguard';
import { AgentApplication, MemoryStorage, StreamingResponse } from '@microsoft/agents-hosting';
import { Activity, ActivityTypes } from '@microsoft/agents-activity';
import { createAgentRequestHandler } from '@microsoft/agents-hosting-express';

export const MODEL = process.env.MODEL ?? 'gpt-4o-mini';
const INSTRUCTIONS =
  'You are a concise support agent in Microsoft Teams. Answer in one short sentence.';

// (C) Money is a `Decimal`, never a JS number — which is also why the ledger round-trips through
// TurnState as a *string*.
export const SESSION_CAP_USD = new Decimal(process.env.SESSION_CAP_USD ?? '5.00');
const TURN_CAP_USD = new Decimal(process.env.TURN_CAP_USD ?? '0.05');
const MAX_OUTPUT_TOKENS = 48;
const CONTEXT_BUDGET_TOKENS = 1200;

// TurnState in the JS port is a **property proxy** (`state.conversation.foo = …`), not Python's
// dotted-path string. Same conversation scope, different ergonomics.
const SPEND_PROP = 'cendorSpentUsd';
const HISTORY_PROP = 'cendorHistory';

// ───────────────────────────────────────────── the instrumented client (one line, at startup)

/**
 * The provider client, wrapped once. **Swap the body, keep the `instrument()`.**
 *
 *   import OpenAI from 'openai';
 *   return instrument(new OpenAI());        // or new AzureOpenAI({...}) / new Anthropic()
 *
 * The fake below keeps this recipe offline and keyless.
 */
export function makeClient() {
  const completions = {
    async create(kw) {
      if (kw.stream) return fakeStream(kw);
      const answer = JSON.stringify(kw.messages).includes('refund')
        ? 'Your refund is on its way.'
        : 'Happy to help.';
      return {
        model: kw.model,
        choices: [{ message: { content: answer } }],
        usage: { prompt_tokens: 41, completion_tokens: 8 },
      };
    },
  };
  return instrument({ chat: { completions } });
}

/** An OpenAI-shaped chunk stream, so the (E) breaker has real chunks to break on. */
async function* fakeStream(kw) {
  const words = ['Here', ' is', ' a', ' long', ' answer', ' that', ' keeps', ' going', ' and', ' on'];
  for (let i = 0; i < 6; i++) {
    for (const w of words) {
      yield { model: kw.model, choices: [{ delta: { content: w }, finish_reason: null }], usage: null };
    }
  }
}

// ──────────────────────────────────── (D) attribution: an AsyncLocalStorage + a `trace()` scope

const TURN = new AsyncLocalStorage();

/** Once, at startup: stamp whatever is in `TURN` onto every event the bus sees. */
export function installTurnAmbient() {
  const provider = () => ({ ...(TURN.getStore() ?? {}) });
  addAmbientProvider(provider);
  return provider;
}

/**
 * Both halves matter, and both are scoped to exactly one turn:
 *
 *  - the **ambient stamp** — conversation / channel / activity id on every `LLMCall`;
 *  - the **`trace()` scope** — so a tool loop's N calls share ONE `traceId`. Without it a call
 *    carries no trace id at all and the reply envelope has nothing to correlate.
 *
 * ⚠️ `AsyncLocalStorage.run(value, fn)` — **never `enterWith`**. On Node 20/22 (legacy ALS) an
 * `enterWith` leaks into concurrent flows and is never restored on exit, and a server handling
 * overlapping turns is precisely the shape that breaks on. `run()` is correct on every Node.
 *
 * Only `conversation.id` is stamped. The sender's AAD object id is on the Activity and deliberately
 * **not** tagged: identity in exported telemetry is personal data. Opt in (and consider hashing) if
 * you need per-user attribution.
 *
 * ⚠️ Forgetting this scope fails **silently** — cost and usage stay exact, only attribution vanishes.
 */
export async function turnScope(context, fn) {
  const act = context.activity;
  const stamp = {
    conversation: act.conversation.id,
    channel: act.channelId,
    turn_activity_id: act.id ?? '',
  };
  return TURN.run(stamp, () => trace(`${stamp.conversation}:${stamp.turn_activity_id}`, () => fn(stamp)));
}

// ─────────────────────────────────────────────────── guardrails on the channel boundary

const inputGate = () => [
  presets.promptInjection({ stage: 'input', action: 'block' }),
  rules.regexRule(/[\w.+-]+@[\w-]+\.[\w.]+/g, {
    action: 'redact',
    stage: 'input',
    name: 'email_redact',
    replacement: '[email redacted]',
  }),
  rules.lengthBounds({ maxChars: 8000, stage: 'input', action: 'block', name: 'activity_length' }),
];

const outputGate = () => [
  rules.keywordDeny(['internal-only'], { stage: 'output', action: 'block', name: 'disclosure_deny' }),
  rules.regexRule(/\bsk-[A-Za-z0-9]{8,}\b/g, {
    action: 'redact',
    stage: 'output',
    name: 'apikey_redact',
    replacement: '[redacted]',
  }),
];

/**
 * ⚠️ **THE most important call shape on this page.**
 *
 * `evaluateAsync` (and Python's `evaluate_async`) **THROW** `GuardrailTripped` on a block — they do
 * not hand you back a decision list with `action === 'block'` in it. A handler that only reads the
 * return value never sees the block: it escapes as an unhandled turn error and your user reads
 * *"the agent hit an error"* instead of your policy's refusal, which is indistinguishable from a
 * broken agent. Catch it, and the refusal becomes yours to word.
 *
 * The `redact` path is why this is `evaluateAsync` and not a boolean check: the returned payload is
 * the *rewritten* text, so the model never sees the e-mail address.
 */
async function gate(guardrails, stage, payload, conversationId) {
  const ctx = { stage, agent: 'm365-custom-engine', metadata: { conversation: conversationId } };
  try {
    const res = await evaluateAsync(guardrails, stage, payload, ctx);
    return { payload: res.payload, decisions: res.decisions };
  } catch (err) {
    if (err instanceof GuardrailTripped) {
      const decisions = err.decisions ?? [];
      return {
        payload,
        decisions: decisions.length
          ? decisions
          : [{ guardrail: err.guardrail ?? 'guardrail', stage, action: 'block' }],
      };
    }
    throw err;
  }
}

const blocked = (decisions) => decisions.find((d) => d.action === 'block') ?? null;

// ───────────────────────────────────────── acttrace: evidence for a long-lived server

/**
 * One append-only, hash-chained file per **process**, installed once at startup.
 *
 * Why an interceptor and not a per-turn `guard(...)` scope: the scope form mutates a process-global
 * interceptor list, so under concurrent turns turn A's exit races turn B's entry.
 *
 * Reopening this same path after a restart **resumes** the chain and `verify()` stays green. What
 * acttrace refuses is two *live* `AuditLog`s on one file at once — the second throws at construction,
 * because two interleaved hash chains in one file can never verify. So rotate per process only if you
 * have **concurrent writers**, not merely because you restarted.
 */
function installAudit(path) {
  const log = new AuditLog('m365-custom-engine', { riskTier: 'limited', path });
  const interceptor = guard(Policy.gdpr(), log);
  addInterceptor(interceptor);
  return { log, interceptor };
}

// ──────────────────────── contextkit + squeeze: the prompt, inside a token budget
//
// Replayed conversation history is the dominant token-growth driver in a chat agent — every turn
// re-sends the previous ones. So assemble inside a budget instead of concatenating.

async function assemblePrompt(history, userText) {
  const ctx = new CkContext({
    budgetTokens: CONTEXT_BUDGET_TOKENS,
    model: MODEL,
    reserveOutput: 256,
  });
  ctx.add(new Block(INSTRUCTIONS, { role: 'system', priority: 100, pin: true }));

  if (history.length) {
    const blob = history.map((m) => `${m.role}: ${m.content}`).join('\n');
    if (blob.length > 1200) {
      const [text] = compress(blob, { kind: 'prose', targetTokens: 256, model: MODEL });
      ctx.add(new Block(`Earlier conversation (compressed):\n${text}`, { role: 'system', priority: 50 }));
    } else {
      ctx.add(new Block({ messages: history, priority: 50, evict: 'drop_oldest' }));
    }
  }
  ctx.add(new Block(userText, { role: 'user', priority: 90, pin: true }));
  return await ctx.assemble();
}

// ────────────────── (C) the per-conversation cap, held in the host's own TurnState
//
// tokenguard budgets are scope-shaped: they live and die with a callback. Conversations are
// long-lived. The bridge is the hosting SDK's own conversation-scoped state, so the cap survives
// turns — and, with Blob/Cosmos storage instead of MemoryStorage, process restarts.

export class SpendLedger {
  constructor(state, capUsd = SESSION_CAP_USD, turnCapUsd = TURN_CAP_USD) {
    this.state = state;
    this.capUsd = capUsd;
    this.turnCapUsd = turnCapUsd;
  }
  get spent() {
    const raw = this.state.conversation?.[SPEND_PROP];
    return raw ? new Decimal(String(raw)) : new Decimal(0);
  }
  get remaining() {
    return this.capUsd.minus(this.spent);
  }
  get exhausted() {
    return this.spent.gte(this.capUsd);
  }
  /** The per-turn scope is the **derived remainder** — a $4.97 session can burn $0.03 more. */
  turnAllowance() {
    return Decimal.min(this.turnCapUsd, this.remaining);
  }
  add(cost) {
    const amount = cost instanceof Money ? new Decimal(cost.amount.toString()) : new Decimal(0);
    const total = this.spent.plus(amount);
    this.state.conversation[SPEND_PROP] = total.toString(); // Decimal-as-string, never a JS number
    return total;
  }
}

/**
 * (B)/(E) — ONE scope around the whole handler body, so a tool loop shares one fuse.
 *
 * ⚠️ `withBudget(cfg, cb)` — **not** `budget(cfg, cb)`. `budget` is curried
 * (`budget(cfg)(cb)`) and its two-argument overload is a deliberate compile error that tells you so.
 */
function turnBudget(allowance, { conversationId, stream = false }, cb) {
  return track({ conversation: conversationId }, () =>
    withBudget(
      {
        usd: allowance.toString(),
        onExceed: stream ? 'break' : 'block',
        name: `m365-turn:${conversationId}`,
      },
      cb,
    ),
  );
}

/**
 * (A) — estimate before spending. Zero spend on refusal.
 *
 * ⚠️ The estimate reserves the **full** `maxOutputTokens`, which a short answer never uses (measured
 * 3.04x over-reservation on one real turn). So (A) can refuse while the ledger still shows headroom —
 * correct and zero-spend, but **never word that refusal as "you reached your cap"**. Say the request
 * *would* exceed what is left.
 *
 * An unpriced model (Azure deployment names, Bedrock/HF/Ollama ids) yields null: no number, so no
 * refusal — let the real budget scope do the work.
 */
function preflight(messages, allowance) {
  try {
    const text = messages.map((m) => String(m.content ?? '')).join('\n');
    const est = prices.estimate(MODEL, tokens.count(text, MODEL), { outputTokens: MAX_OUTPUT_TOKENS });
    if (!est) return true;
    const amount = new Decimal(est.amount.toString());
    return amount.lte(0) ? true : amount.lte(allowance);
  } catch {
    return true;
  }
}

// ─────────────────── the reply envelope, attached in the handler
//
// `FoundryAdapter` is **not** used here, on purpose. That adapter belongs to the separate Azure AI
// Foundry integration; the M365 Agents SDK owns its own Activity plumbing, so the envelope is three
// lines on the reply Activity. Using both would duplicate the host's plumbing.

function channelDataFor(envelope) {
  const payload = {};
  for (const [k, v] of Object.entries(envelope)) {
    if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)) continue;
    payload[k] = v;
  }
  return { cendor: payload };
}

/**
 * Plain text plus the envelope — the whole of it.
 *
 * `channelData.cendor` is for the channel / your back end to consume. Whether a *client* surfaces it
 * is client-specific: the M365 Agents Playground projects `channelData` away in its UI (it is still
 * on the wire), so don't tell people to look for it there — assert it in a test, or log it.
 */
async function reply(context, text, envelope) {
  const activity = Activity.fromObject({ type: ActivityTypes.Message, text });
  activity.channelData = { ...(activity.channelData ?? {}), ...channelDataFor(envelope) };
  await context.sendActivity(activity);
}

// ═══════════════════════════════════════════════════════════════════ the agent

export class GovernedAgent {
  /**
   * @param opts.skipAfterTurnHandler  **Do not set this in real code.** It exists so the recipe can
   *   demonstrate the trap below with a negative control, instead of just asserting the happy path.
   */
  constructor({
    auditPath,
    storage = new MemoryStorage(),
    sessionCapUsd = SESSION_CAP_USD,
    skipAfterTurnHandler = false,
  } = {}) {
    this.client = makeClient();
    this.inGate = inputGate();
    this.outGate = outputGate();
    this.sessionCapUsd = sessionCapUsd;
    this.ambient = installTurnAmbient();
    const installed = installAudit(auditPath);
    this.audit = installed.log;
    this.interceptor = installed.interceptor;

    this.app = new AgentApplication({ storage });

    // ⚠️ **REQUIRED, and its absence looks exactly like working code.**
    // `AgentApplication.run()` calls `state.save()` only inside `if (this._afterTurn.length > 0)`,
    // and the official nodejs quickstart registers nothing — so `TurnState` is never persisted, the
    // ledger above reads $0 on every turn, and the session cap silently never binds. (Its own `count`
    // demo echoes `[1]` forever for the same reason.) The Python port saves unconditionally, so this
    // line has no Python twin.
    if (!skipAfterTurnHandler) this.app.onTurn('afterTurn', async () => true);

    this.register();
  }

  /** Undo the process-global installs. **A real server never calls this** — it lives forever. */
  close() {
    this.audit.detach();
    removeInterceptor(this.interceptor);
    removeAmbientProvider(this.ambient);
  }

  register() {
    this.app.onActivity(ActivityTypes.Message, async (context, state) => {
      let text = (context.activity.text ?? '').trim();
      const streamed = text.startsWith('/stream ');
      if (streamed) text = text.slice('/stream '.length);
      const cid = context.activity.conversation.id;
      const ledger = new SpendLedger(state, this.sessionCapUsd);

      // (D) every bus event raised below carries this turn's identity and one trace id
      await turnScope(context, async () => {
        // (C) the cheapest refusal there is: the cap is gone, so no model call happens
        if (ledger.exhausted) {
          await reply(context, "This conversation has used its budget, so I didn't call the model.", {
            governance: 'session_cap_reached',
            session_spent_usd: ledger.spent.toString(),
            session_cap_usd: ledger.capUsd.toString(),
          });
          return;
        }

        const inGated = await gate(this.inGate, 'input', text, cid);
        const inHit = blocked(inGated.decisions);
        if (inHit) {
          this.audit.flag(`input blocked by ${inHit.guardrail}`, {
            action: 'blocked',
            severity: 'warning',
          });
          await reply(context, "I can't process that message.", {
            governance: 'input_blocked',
            decisions: inGated.decisions.map((d) => `${d.guardrail}:${d.action}`),
            session_spent_usd: ledger.spent.toString(),
          });
          return;
        }

        const history = state.conversation[HISTORY_PROP] ?? [];
        const messages = await assemblePrompt(history, String(inGated.payload));
        const allowance = ledger.turnAllowance();

        // (A) is skipped on a streamed turn, on purpose. ⚠️ (A) and (E) are MUTUALLY EXCLUSIVE: the
        // estimate reserves the full `maxOutputTokens`, so any allowance small enough for the breaker
        // to fire is already below the estimate — the turn would be refused before a chunk existed.
        // A stream's fuse IS the breaker.
        if (!streamed && !preflight(messages, allowance)) {
          await reply(context, "That request would exceed what's left of this conversation's budget.", {
            governance: 'preflight_refused',
            session_spent_usd: ledger.spent.toString(),
            session_cap_usd: ledger.capUsd.toString(),
          });
          return;
        }

        const calls = [];
        const collect = (e) => {
          if (e instanceof LLMCall) calls.push(e);
        };
        bus.subscribe(collect);
        let answer = '';
        let broke = false;
        try {
          answer = await this.audit.decision(
            async (decision) => {
              const r = streamed
                ? await this.streamedTurn(context, messages, allowance)
                : await this.plainTurn(messages, allowance);
              broke = r.broke;
              decision.record({ model: MODEL, streamed });
              return r.text;
            },
            { input: String(inGated.payload).slice(0, 200) },
          );
        } catch (err) {
          // ⚠️ The THIRD exception type a governed handler must expect, alongside BudgetExceeded and
          // GuardrailTripped: the acttrace `guard()` installed at startup throws `PolicyViolation`
          // from *inside* the provider call, at core's interceptor seam. Uncaught, the channel shows
          // "the agent hit an error" instead of the refusal. Report categories, never the value.
          if (!(err instanceof PolicyViolation)) throw err;
          const categories = [...new Set((err.findings ?? []).map((f) => f.category))].sort();
          await reply(
            context,
            "I can't send that to the model — our data policy blocked it" +
              (categories.length ? ` (${categories.join(', ')}).` : '.'),
            { governance: 'policy_blocked', decisions: categories.map((c) => `acttrace:${c}`) },
          );
          return;
        } finally {
          bus.unsubscribe(collect);
        }

        const cost = new Money(
          calls.reduce(
            (t, c) => (c.cost instanceof Money ? t.plus(new Decimal(c.cost.amount.toString())) : t),
            new Decimal(0),
          ),
        );
        const usageIn = calls.reduce((n, c) => n + Number(c.usage?.inputTokens ?? 0), 0);
        const usageOut = calls.reduce((n, c) => n + Number(c.usage?.outputTokens ?? 0), 0);

        const outGated = await gate(this.outGate, 'output', answer, cid);
        const outHit = blocked(outGated.decisions);
        const safeAnswer = outHit ? 'I generated a response our output policy blocked.' : outGated.payload;

        const total = ledger.add(cost); // (C) write the cap back into TurnState
        state.conversation[HISTORY_PROP] = [
          ...history,
          { role: 'user', content: String(inGated.payload) },
          { role: 'assistant', content: String(safeAnswer) },
        ].slice(-20);

        const envelope = {
          governance: broke ? 'broke_on_budget' : outHit ? 'output_blocked' : 'ok',
          trace_id: calls.length ? calls[calls.length - 1].traceId : undefined,
          cost_usd: cost.amount.toString(),
          model: MODEL,
          input_tokens: usageIn || undefined,
          output_tokens: usageOut || undefined,
          session_spent_usd: total.toString(),
          session_cap_usd: ledger.capUsd.toString(),
          decisions: [...inGated.decisions, ...outGated.decisions].map((d) => `${d.guardrail}:${d.action}`),
        };
        // A streamed turn already flushed its text, so the envelope rides a final activity.
        await reply(context, streamed ? '' : String(safeAnswer), envelope);
      });
    });
  }

  async plainTurn(messages, allowance) {
    try {
      const resp = await turnBudget(allowance, { conversationId: 'turn' }, () =>
        this.client.chat.completions.create({
          model: MODEL,
          messages,
          max_tokens: MAX_OUTPUT_TOKENS,
        }),
      );
      return { text: resp.choices[0].message.content ?? '', broke: false };
    } catch (err) {
      if (!(err instanceof BudgetExceeded)) throw err;
      return { text: "I stopped before calling the model — this turn's budget was already spent.", broke: true };
    }
  }

  /**
   * (E) provider stream → the channel's streamed reply, with the breaker in between.
   *
   * **Spend truth vs display truth.** Break stops token consumption at the chunk boundary. The
   * channel keeps whatever it had already been sent — queued chunks cannot be unsent. Whether
   * anything was visible depends on the channel and on how long the answer ran; on a non-streaming
   * channel the user simply sees the truncated answer plus the notice. Never claim the user-visible
   * text is cut at the exact budget token.
   */
  async streamedTurn(context, messages, allowance) {
    const stream = new StreamingResponse(context);
    stream.queueInformativeUpdate('Thinking…');
    const collected = [];
    let broke = false;
    try {
      await turnBudget(allowance, { conversationId: context.activity.conversation.id, stream: true }, async () => {
        const providerStream = await this.client.chat.completions.create({
          model: MODEL,
          messages,
          max_tokens: 512,
          stream: true,
          stream_options: { include_usage: true },
        });
        for await (const chunk of providerStream) {
          const piece = chunk.choices?.[0]?.delta?.content ?? '';
          if (piece) {
            collected.push(piece);
            stream.queueTextChunk(piece);
          }
        }
      });
    } catch (err) {
      if (!(err instanceof BudgetExceeded)) throw err;
      broke = true;
      stream.queueTextChunk('\n\n_[stopped at the budget cap]_');
    } finally {
      // On JS `waitForQueue()` is private and `endStream()` drains the queue itself. (On Python BOTH
      // are coroutines and an un-awaited `end_stream()` silently loses the last chunk.)
      await stream.endStream();
    }
    return { text: collected.join(''), broke };
  }
}

// ═══════════════════════════════════════════════════════════════════ the express host

/** The quickstart's server: one POST route behind the SDK's own request handler (JWT included). */
export function buildWebApp(agent) {
  const app = express();
  app.use(express.json({ limit: '5mb' }));
  app.post('/api/messages', createAgentRequestHandler(agent.app));
  return app;
}

export async function serve(agent, port = 3979) {
  return new Promise((resolve) => {
    const server = buildWebApp(agent).listen(port, '127.0.0.1', () => resolve(server));
  });
}
