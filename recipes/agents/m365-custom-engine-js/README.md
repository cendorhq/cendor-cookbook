# Govern a Microsoft 365 Agents SDK custom engine agent (TypeScript / JS)

A **custom engine agent** is the Agents Toolkit tile whose own description is *"you manage
orchestration and provide your own LLM."* Those are Microsoft's words and they are exactly the
boundary: your process hosts `AgentApplication` behind `POST /api/messages`, and the model call inside
your message handler is an ordinary provider-SDK call. Your call, your tokens, your bill — so cendor
governs it like any other call.

Pick **Custom Engine Agent** in the toolkit's *New Project* menu. The **Teams Agents and Apps**
bot/agent flavour is equivalent — same wrap map, and Microsoft's own Teams SDK guidance is "bring the
OpenAI SDK." A **Declarative Agent** is the opposite topology (Microsoft holds the model, you are
billed in Copilot Credits) and there is nothing for a token library to govern there.

```
recipes/agents/m365-custom-engine-js/
  agent.mjs         the wrap map + the host — this is the file you copy
  channelStub.mjs   a local stand-in for the channel, so this runs in CI
  index.mjs         a narrated offline run that asserts as it goes (node:assert)
```

## Run it

No key. No network. No tenant, no tunnel, no bot registration. `node index.mjs` **is** the test — a
broken governance path exits non-zero.

```bash
cd recipes/agents/m365-custom-engine-js && npm install && node index.mjs
```

## Expected output

```text
--- one governed turn ------------------------------------------
  tokens      : 41 in / 8 out   (gpt-4o-mini)
  cost        : $0.00001095   Decimal, priced from the snapshot
  session     : $0.00001095 of $5  (in TurnState)
  trace_id    : cookbook-m365:137a4ee5-8352-4b64-bdd0-6c54b9056ae8
--- governance that fired --------------------------------------
  input gate  : input_blocked -> "I can't process that message."
  redaction   : ["email_redact:redact"]
  mid-stream  : broke_on_budget after 3 channel activities
  session cap : session_cap_reached -> "This conversation has used its budget, …"
  pre-flight  : preflight_refused -> "That request would exceed what's left …"
  audit chain : verify=true — ok: 14 entries, head afb8ca2d7272…
--- the afterTurn trap, measured -------------------------------
  with  app.onTurn('afterTurn') : $0.0000219 cumulative after 2 turns
  without it (the quickstart)   : $0.00001095 — one turn's worth, every turn
--- $0 whole-agent CI ------------------------------------------
  identical   : true

all assertions passed
```

Everything there is real: a real `AgentApplication`, the SDK's real request handler, real `TurnState`,
over a real socket. The only stand-in is the provider client — `makeClient()` returns a small async
fake, so CI costs nothing. To go live, replace its body:

```js
import OpenAI from 'openai';
return instrument(new OpenAI());        // or new AzureOpenAI({...}) / new Anthropic()
```

Nothing else changes. `instrument()` detection is structural, not name-based.

**Driving it interactively** — the same endpoint, from the M365 Agents Playground (local, anonymous,
no tenant):

```bash
npm i -g @microsoft/m365agentsplayground        # or: winget install agentsplayground
node -e "import('./agent.mjs').then(m => m.serve(new m.GovernedAgent({auditPath:'chain.jsonl'})))"
agentsplayground -e "http://localhost:3979/api/messages" -c emulator
```

## The wrap map

| # | Where | Library | What it does in the handler |
|---|---|---|---|
| **(A)** | before any spend | `@cendor/tokenguard` `prices.estimate` | refuses a turn the remaining budget can't cover — **zero** provider calls |
| **(B)** | around the whole body | `withBudget({onExceed:'block'})` | one fuse per turn, so a tool loop's five calls share it |
| **(C)** | across turns | tokenguard + the host's `TurnState` | cumulative session cap, `Decimal`-as-string; the per-turn allowance is the *derived remainder* |
| **(D)** | every bus event | `@cendor/core` ambient + `trace()` | `conversation.id` on every `LLMCall`, and one `traceId` for the turn |
| **(E)** | mid-stream | `withBudget({onExceed:'break'})` | stops a streamed answer at the chunk where the allowance dies |
| — | on the client | `@cendor/core` `instrument()` | exact tokens, `Decimal` cost, provider + model, TTFT |
| — | in / out of the channel | `@cendor/guardrails` | injection block + PII redaction on `activity.text`; disclosure/secret gate on the reply |
| — | per turn | `@cendor/acttrace` `guard()` + `AuditLog` | hash-chained, `verify()`-able evidence, with a data-policy gate before the model |
| — | the prompt | `@cendor/contextkit` + `squeeze` | history assembled *inside* a token budget instead of concatenated |
| — | the reply | in-handler | `channelData.cendor` = `trace_id` · `cost_usd` · usage · session spend · decisions |

**`FoundryAdapter` is deliberately not used.** That adapter belongs to cendor's separate **Azure AI
Foundry** integration. The M365 Agents SDK owns its own Activity plumbing, so the envelope is three
lines on the reply Activity — using both would duplicate the host.

## Traps this recipe exists to teach

Each was measured against a real agent, and every one of them *looks* like working code.

1. **`app.onTurn('afterTurn', async () => true)` is REQUIRED — and this is the JS-only one.**
   `AgentApplication.run()` calls `state.save()` only inside `if (this._afterTurn.length > 0)`, and
   the **official nodejs quickstart registers nothing** — so `TurnState` is never persisted (its own
   `count` demo echoes `[1]` forever). The number on your envelope still *looks* plausible, because
   each turn reports its own cost; it just never accumulates, so a cumulative cap can never bind.
   `index.mjs` proves it with a **negative control**: the same agent minus that one line reports
   `$0.00001095` after two turns instead of `$0.0000219`. Python's `AgentApplication.run()` saves
   unconditionally, so this line has no Python twin.
2. **`evaluateAsync` THROWS on a block** — it does not return a decision list with
   `action === 'block'` in it. A handler that only reads the return value never sees the block; it
   escapes as an unhandled turn error and your user reads *"the agent hit an error"* instead of your
   policy's refusal. `agent.mjs`'s `gate()` catches it. Same in Python (`evaluate_async`).
3. **A third exception type.** The `acttrace` `guard()` installed at startup throws `PolicyViolation`
   from *inside* the provider call. Alongside `BudgetExceeded` and `GuardrailTripped`, that is three
   things a governed handler must expect. Report the finding's **categories**, never the matched value.
4. **`withBudget(cfg, cb)` — not `budget(cfg, cb)`.** `budget` is curried (`budget(cfg)(cb)`) and its
   two-argument overload is a deliberate compile error whose message tells you the right shape.
5. **`AsyncLocalStorage.run(value, fn)` — never `enterWith`.** On Node 20/22 an `enterWith` leaks into
   concurrent flows and is never restored on exit, and a server handling overlapping turns is exactly
   the shape that breaks on. A test green on Node 24 proves nothing about the LTS.
6. **(A) and (E) are mutually exclusive on a streamed turn.** The estimate reserves the *full*
   `max_tokens`, so any allowance small enough for the breaker to fire is already smaller than the
   estimate — the turn would be refused before a chunk existed. A streamed turn's fuse **is** the
   breaker; this recipe skips (A) there on purpose.
7. **Never word a pre-flight refusal as "you reached your cap."** The estimate over-reserves — on one
   measured turn, `$0.0000333` estimated against `$0.00001095` actually spent, **3.04×**. So (A) can
   refuse while the ledger still shows headroom. Say the request *would* exceed what is left. (In the
   run above, `preflight_refused` and `session_cap_reached` are two different sentences for that
   reason.)
8. **A cassette scope in a server must wrap the LISTENER START, not the driver.** Replay matches calls
   by a session id stamped from async-context storage, and a request handler inherits the context that
   was active when the server began listening. A scope around your client-side driver never reaches the
   handler and every call goes to the network. One scope per server lifetime also matters because the
   recorder writes the file on scope **exit** — a per-turn scope leaves only the last turn in it.
9. **Forgetting `turnScope()` fails silently.** Cost and usage stay exact; only attribution vanishes,
   with no warning.
10. **`endStream()` drains the queue itself here**; `waitForQueue()` is private. On Python **both** are
    coroutines and an un-awaited `end_stream()` is a silent `RuntimeWarning` that loses the last chunk.
11. **A second, un-instrumented client is invisible.** Budgets, gates and evidence only see calls
    through the client you wrapped. `npx @cendor/init doctor` static-checks that.
12. **A stream chunk can carry NO choices.** With `stream_options: { include_usage: true }` (the only
    way a streamed call reports real usage) OpenAI sends a **final chunk whose `choices` array is
    empty**, carrying only `usage`. Measured: **9** chunks with `include_usage`, the 9th `choices=[]`;
    **8** without it, none empty. This port reads `chunk.choices?.[0]?.delta?.content ?? ''` and so
    survives it — the Python twin used `chunk.choices[0]` and crashed on its first real streamed turn
    (fixed 2026-07-30). Keep the optional chaining; it is load-bearing, not defensive noise.
13. **The output-cap parameter is not the same on every model, and the wrong one is a hard 400.**
    The reasoning families (o-series, `gpt-5-*`) reject `max_tokens`: *"Unsupported parameter:
    'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead."* Measured
    against an Azure AI Foundry `gpt-5-mini` deployment on api-version `2024-10-21` — the
    `new AzureOpenAI({...})` swap this recipe offers. It bites hardest on Azure because **a deployment
    name is arbitrary**: `MODEL` may be `prod-chat` with a gpt-5 behind it, so no name heuristic is
    authoritative. `agent.mjs` defaults by name, honours `OUTPUT_CAP_PARAM`, and switches once if the
    provider names the other parameter.
14. **On a reasoning model the cap covers reasoning tokens, so a small cap can return NOTHING.** Same
    deployment, `MAX_OUTPUT_TOKENS = 48`: `37 in / 48 out` with an **empty** visible reply — the whole
    allowance went to hidden reasoning. Every governance number was correct; there was simply no text.
15. **An Azure deployment name is UNPRICED, so a USD budget cannot bind to it.** The same live run
    warns: *"no price for model 'gpt-5-mini' … counts its calls as $0 and cannot enforce a USD cap."*
    Register a rate, use a token cap, or refuse unpriced calls. Token counts and the audit chain stay
    exact — only the money is unknown. (This is also why `index.mjs`'s `cost_usd > 0` assertion is an
    OpenAI-path assertion: against an unpriced deployment it correctly reads `$0`.)

## `$0` whole-agent CI

`index.mjs`'s last section records the model calls once, then replays **the entire agent** — HTTP →
request handler → governed handler → channel — with the cassette in `replay` mode. Same replies, byte
for byte, no key and no network. That is the CI story: your governed agent has an end-to-end test that
costs nothing and cannot flake on a provider.

No shim is needed, in either language. This port never needed one — `await` on a non-thenable is legal
in JS, so a replayed value passes straight through. The Python port did until `cendor-core` 1.14.1
taught the replay seam to honour the wrapped method's async contract; on the current shelf both ports
just write `await client.chat.completions.create(...)`.

## Before you deploy this

> ⚠️ **This host runs `/api/messages` with no configured client id, i.e. anonymous.** That is the
> supported *local* posture — it is what the Playground relies on — and an **open relay** in
> production: anyone who can reach the port can drive your agent and spend your tokens. A deployed
> agent configures a real `clientId` / `tenantId` / `clientSecret` (or a federated credential) so the
> SDK's request handler actually validates the channel's token.

Two more deployment facts, neither of them cendor's:

- **`MemoryStorage` loses the session cap on restart.** Point `new AgentApplication({ storage })` at
  Blob or Cosmos storage and the cumulative cap survives a redeploy, because it lives in the host's
  own state.
- **Publishing through the Agents Toolkit is not supported in Microsoft 365 *Government* tenants.**
  GCC / sovereign customers use the manual Azure Bot Service deploy path. (From Microsoft's
  m365-agents-sdk extensibility page — re-check its date before relying on it.)

## What this does *not* govern

`tokenguard` governs the **model meter** — which in this topology is the agent's entire AI bill.
Three other meters exist and none of them is a token meter:

| meter | whose | in scope? |
|---|---|---|
| model tokens | yours (your provider account) | ✅ this recipe |
| Azure Bot Service messages | Microsoft | ❌ see Azure pricing |
| Copilot Credits | Microsoft | ❌ a self-hosted-RAG custom engine agent never triggers them |
| hosting (App Service / Container Apps) | your cloud bill | ❌ |

And within the model meter, three honest limits:

- **Break stops spend at the chunk boundary; the channel keeps whatever it was already sent.** Queued
  chunks cannot be unsent. Whether anything was visible depends on the channel and on how long the
  answer ran — on a non-streaming channel the user simply sees the truncated answer plus the notice.
  Never claim the visible text is cut at the exact budget token.
- **The two ports disagree about which channels stream.** JS `StreamingResponse.loadDefaults` groups
  `emulator` with webchat/directline (500 ms) and gives msteams 1000 ms; Python's `_set_defaults` lists
  only msteams, webchat/directline and `deliveryMode='stream'` — **`emulator` is not a streaming
  channel there at all**. So the same break renders differently: measured with an identical break at
  142 output tokens, JS emitted 3 interim flushes on emulator and 1 on msteams, Python 0 and 2.
- **`channelData.cendor` is for the channel / your back end.** Whether a *client* surfaces it is
  client-specific, and the M365 Agents Playground projects `channelData` away in its UI (it is still on
  the wire). Assert it in a test or log it; don't tell people to look for it in the Playground.

## Orchestration layers

| layer | cost truth | note |
|---|---|---|
| plain OpenAI / Anthropic / Azure SDK | ✅ | this recipe |
| LangChain | ✅ | via `@cendor/core/langchain`'s callback handler |
| Semantic Kernel / Microsoft Agent Framework | Python-verified | the injection spikes were run on Python (SK ✅ full truth; MAF ✅ from `cendor-core` 1.14.1). Pin both versions in any claim |
| Teams SDK's own AI libraries | — | **deprecated by Microsoft**; use the OpenAI SDK pattern |
| .NET / C# | ❌ | **explicit non-goal** — there is no cendor .NET port. Never assume coverage |

Expect **two OpenTelemetry span families** from a governed agent — the hosting SDK's own
`microsoft_agents` spans alongside `cendor.core` / `cendor.acttrace`. That is additive, not a conflict.

## Pins

The npm shelf this recipe was **validated against, on 2026-07-27** — a record of what was run, not a
lockfile. `package.json` declares these as carets, and at `3.x` a caret spans the whole major, so a
fresh install resolves forward within major 3: a newer patch than the numbers below is expected, not
drift. All `@cendor/*` libraries share **major 3**; minors and patches are independent per package,
which is why `@cendor/contextkit` is `3.0.1` and `@cendor/acttrace` is `3.1.0`.

```
@cendor/{core,tokenguard,guardrails,squeeze,cassette} 3.0.0
@cendor/contextkit 3.0.1 · @cendor/acttrace 3.1.0
@microsoft/agents-hosting 1.7.1 · @microsoft/agents-hosting-express 1.7.1 · @microsoft/agents-activity 1.7.1
```

⚠️ **Bump the whole `@cendor/*` set together.** A sibling left on an older major resolves a *second*
copy of `@cendor/core` — a second event bus — so cross-library cooperation silently stops (a guardrail
decision never reaches the budget). `node scripts/check-one-core.mjs recipes/agents/m365-custom-engine-js`
asserts there is exactly one, and cookbook CI runs it.

The Python twin is [`../m365-custom-engine-py`](../m365-custom-engine-py/). Full docs: [cendor.ai/docs/providers → Microsoft 365 Agents
SDK](https://cendor.ai/docs/providers#microsoft-365-agents-sdk-custom-engine-agent) — this is a **libraries**
integration, not a `cendor-sdk` one.

Libraries: `@cendor/core`, `tokenguard`, `guardrails`, `contextkit`, `squeeze`, `cassette`, `acttrace` · Host: `@microsoft/agents-hosting` · Offline ✓ · TypeScript · [← all recipes](../../../README.md)
