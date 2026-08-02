# Govern a Microsoft 365 Agents SDK custom engine agent (Python)

A **custom engine agent** is the Agents Toolkit tile whose own description is *"you manage
orchestration and provide your own LLM."* Those are Microsoft's words and they are exactly the
boundary: your process hosts `AgentApplication` behind `POST /api/messages`, and the model call
inside your `activity("message")` handler is an ordinary provider-SDK call. Your call, your tokens,
your bill — so cendor governs it like any other call.

Pick **Custom Engine Agent** in the toolkit's *New Project* menu. The **Teams Agents and Apps**
bot/agent flavour is equivalent — same wrap map, and Microsoft's own Teams SDK guidance is "bring the
OpenAI SDK." A **Declarative Agent** is the opposite topology (Microsoft holds the model, you are
billed in Copilot Credits) and there is nothing for a token library to govern there.

```
recipes/agents/m365-custom-engine-py/
  agent.py            the wrap map + the host — this is the file you copy
  channel_stub.py     a local stand-in for the channel, so this runs in CI
  main.py             a narrated offline run: six governed turns, then a keyless replay
  test_m365_agent.py  the same walkthrough, asserted
```

## Run it

No key. No network. No tenant, no tunnel, no bot registration.

```bash
uv run --group agents-m365 python recipes/agents/m365-custom-engine-py/main.py
uv run --group agents-m365 pytest recipes/agents/m365-custom-engine-py
```

## Expected output

```text
--- one governed turn ------------------------------------------
  reply       : Your refund is on its way.
  tokens      : 41 in / 8 out   (gpt-4o-mini)
  cost        : $0.0000109500   Decimal, priced from the snapshot
  session     : $0.0000109500 of $5.00  (in TurnState)
  trace_id    : cookbook-m365:b0690137-b53c-49d4-aed6-b4807f24ca19
--- governance that fired --------------------------------------
  input gate  : input_blocked -> "I can't process that message."
  redaction   : ['email_redact:redact']
  mid-stream  : broke_on_budget after 2 channel activities
  session cap : session_cap_reached -> "This conversation has used its budget, …"
  pre-flight  : preflight_refused -> "That request would exceed what's left …"
  audit chain : verify=True — ok: 14 entries, head c6ff71f9f822…
--- $0 whole-agent CI ------------------------------------------
  identical   : True
```

Everything in that output is real: a real `AgentApplication`, a real `CloudAdapter`, the real JWT
middleware, real `TurnState`, over a real socket. The only stand-in is the provider client —
`make_client()` returns a small **async** fake, so CI costs nothing. To go live, replace its body:

```python
from openai import AsyncOpenAI
return instrument(AsyncOpenAI())        # or AsyncAnthropic(...)

# Azure AI Foundry — the same client, pointed at the v1 GA endpoint (no api-version):
return instrument(AsyncOpenAI(
    base_url=f"{os.environ['AZURE_OPENAI_ENDPOINT'].rstrip('/')}/openai/v1/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"]))
```

Nothing else changes. `instrument()` detection is structural, not name-based.

**Driving it interactively** — the same endpoint, from the M365 Agents Playground (local, anonymous,
no tenant). Verified end to end against **`@microsoft/m365agentsplayground` 0.2.28** on 2026-08-01:
the agent answers in the Playground UI.

```bash
npm i -g @microsoft/m365agentsplayground        # or: winget install agentsplayground

# terminal 1 — the agent. Note BOTH the `cd` and the `uv run --group agents-m365`.
cd recipes/agents/m365-custom-engine-py
uv run --group agents-m365 python -c \
  "import agent; agent.serve(agent.GovernedAgent(audit_path='chain.jsonl'))"

# terminal 2 — the Playground, pointed at it
agentsplayground -e "http://localhost:3978/api/messages" -c emulator
```

> ⚠️ **Both halves of that first command matter, and getting either wrong looks like "the recipe
> doesn't run".** This block used to say plain `python …` with no `cd`, which is the only command in
> this repo that skips the project's toolchain. Measured, verbatim, on a clean shell:
>
> | What you type | What you get |
> |---|---|
> | `python -c "import agent; …"` | `ModuleNotFoundError: No module named 'cendor.acttrace'` — bare `python` is the system interpreter, not the project venv |
> | the right command from the repo root | `ModuleNotFoundError: No module named 'agent'` — `python -c` puts the *current directory* on `sys.path`, and `agent.py` lives in this folder |
> | port 3978 already in use | a raw `OSError: [Errno 10048] … bind` traceback from aiohttp |
>
> Prefer not to remember any of that? `uv run --group agents-m365 python
> recipes/agents/m365-custom-engine-py/serve.py` does the `cd` for you, says which port it is on,
> and turns a busy port into one readable line.

Or run the scripted smoke instead of clicking — it starts the agent, sends the Playground's own
handshake and a message Activity, and asserts a governed reply came back:

```bash
uv run --group agents-m365 python recipes/agents/m365-custom-engine-py/smoke.py
```

## What the user actually sees: the governance card

⚠️ **The envelope is invisible in the Playground's chat pane, and that is measured, not assumed.**
Playground 0.2.28's UI projection (`convertMessage()`) forwards a fixed field set and reads
`channelData` only for `feedbackLoopEnabled`. The envelope is on the wire — the Log Panel's raw
Activity JSON has it — and a person looking at the chat sees nothing. `attachments`, by contrast,
**are** forwarded and rendered.

So the recipe ships a governance **Adaptive Card**, opt-in, off by default:

```bash
/cards on            # in the chat, any channel
M365_CARDS=1 …       # or at startup
```

It is shaped like [cendor.ai/try](https://cendor.ai/try): **one row per library, saying what that
library did on this turn, in words.** A FactSet of raw keys is a JSON dump with better spacing; what
a reviewer needs to read is *"tokenguard refused this before any call, and here is the number it
refused on"*.

```text
  ✅  governed · answered
  Answered in 1 model call for $0.0000109500. This conversation has used $0.0000109500 of $5.00.

  Bus feed     core        detected openai · gpt-4o-mini from the client's shape
                           41 in / 8 out — the provider's count
                           one trace id for the turn: cookbook-m365:0fd4793a-…
  Budget       tokenguard  this turn $0.0000109500 (Decimal, never a float)
                           session $0.0000109500 of $5.00, held in the host's own TurnState
                           this turn's fuse: $0.05 (the remainder)
                           rate from azure as of 2026-07-01
  Receipt      contextkit  packed 2 message(s) into a 1,200-token window
  Gate         guardrails  in and out: nothing to act on
  Audit        acttrace    6 hash-chained entries
                           head a6d9d0ffbaa1be8b… — verify() re-walks the file
```

…and, more importantly, when governance refuses:

```text
  ⛔  tokenguard · refused before the call
  Refused before any model call: the estimate was $0.0000313500 against $0.000001 left for this
  turn. Zero provider calls, $0 spent. The estimate reserves the full output allowance, so this can
  refuse while the session ledger still shows headroom.

  Bus feed     core        no model call was made — nothing reached the provider
```

**Four decisions in that card worth copying:**

1. **A refusal explains itself.** "The agent hit an error" is the failure this whole recipe exists
   to prevent, and a bare *"I can't do that"* is only marginally better. The card names the library,
   the number it refused on, and what it cost you ($0).
2. **The pre-flight refusal must NOT say "you reached your cap."** The estimate reserves the full
   output allowance — measured 3.04× over-reservation on one real turn — so it can refuse while the
   ledger still shows headroom. The **session-cap** refusal is a different event and does say
   exactly that. `test_m365_agent.py` asserts both directions, and the second is the negative
   control for the first.
3. **The money carries its provenance.** `rate from azure as of 2026-07-01` comes from
   `prices.explain(MODEL)` (`cendor-core` ≥ 1.19). A USD cap is only as good as the rate under it,
   and an unpriced model would print **UNPRICED — every USD guard on this turn is a silent no-op**
   instead of a comfortable-looking `$0`. See
   [`libs/prices-live-and-explain`](../../libs/prices-live-and-explain/).
4. **The card is styling; governance is not.** Plain text stays the canonical reply and the card is
   off by default, so nothing enforced depends on a channel rendering an attachment. `/cards off`
   is asserted to remove the attachment entirely.

The numbers on the card are the **same turn's** envelope values, not a second computation of them —
the test compares them against that reply's own `channelData.cendor`, keyed on the per-turn
`trace_id`. (Comparing against a *different* turn's would have passed for the wrong reason: the
offline fake is deterministic, so two turns cost the same.)

## The wrap map

| # | Where | Library | What it does in the handler |
|---|---|---|---|
| **(A)** | before any spend | `tokenguard` `prices.estimate` | refuses a turn the remaining budget can't cover — **zero** provider calls |
| **(B)** | around the whole body | `tokenguard` `budget(on_exceed="block")` | one fuse per turn, so a tool loop's five calls share it |
| **(C)** | across turns | `tokenguard` + the host's `TurnState` | cumulative session cap, `Decimal`-as-string; the per-turn allowance is the *derived remainder* |
| **(D)** | every bus event | `core` ambient + `trace()` | `conversation.id` on every `LLMCall`, and one `trace_id` for the turn |
| **(E)** | mid-stream | `budget(on_exceed="break")` | stops a streamed answer at the chunk where the allowance dies |
| — | on the client | `core` `instrument()` | exact tokens, `Decimal` cost, provider + model, TTFT |
| — | in / out of the channel | `guardrails` | injection block + PII redaction on `activity.text`; disclosure/secret gate on the reply |
| — | per turn | `acttrace` `guard()` + `AuditLog` | hash-chained, `verify()`-able evidence, with a data-policy gate before the model |
| — | the prompt | `contextkit` + `squeeze` | history assembled *inside* a token budget instead of concatenated |
| — | the reply | in-handler | `channelData.cendor` = `trace_id` · `cost_usd` · usage · session spend · decisions |

**`FoundryAdapter` is deliberately not used.** That adapter belongs to cendor's separate **Azure AI
Foundry** integration. The M365 Agents SDK owns its own Activity plumbing, so the envelope is three
lines on the reply Activity — using both would duplicate the host.

## Traps this recipe exists to teach

Each of these was measured against a real agent, and every one of them *looks* like working code.

1. **`evaluate_async` RAISES on a block** — it does not return a decision list with
   `action="block"` in it. A handler that only reads the return value never sees the block; it
   escapes as an unhandled turn error and your user reads *"the agent hit an error"* instead of your
   policy's refusal. `agent.gate()` catches it. Same in TypeScript (`evaluateAsync`).
2. **A third exception type.** The `acttrace` `guard()` installed at startup raises
   `PolicyViolation` from *inside* the provider call. Alongside `BudgetExceeded` and
   `GuardrailTripped`, that is three things a governed handler must expect. Report the finding's
   **categories**, never the matched value.
3. **`TurnState` paths are scoped by the state class name.**
   `state.get_value("conversation.spent_usd")` raises `ValueError: Scope 'conversation' not found`.
   Use `"ConversationState.spent_usd"` (or `state.conversation.set_value(...)`).
4. **`end_stream()` and `wait_for_queue()` are coroutines on Python.** Un-awaited, `end_stream()` is
   a silent `RuntimeWarning` and the last chunk never reaches the channel. (On TypeScript
   `waitForQueue()` is private and `endStream()` drains the queue itself.)
5. **(A) and (E) are mutually exclusive on a streamed turn.** The estimate reserves the *full*
   `max_output_tokens`, so any allowance small enough for the breaker to fire is already smaller than
   the estimate — the turn would be refused before a chunk existed. A streamed turn's fuse **is** the
   breaker; this recipe skips (A) there on purpose.
6. **Never word a pre-flight refusal as "you reached your cap."** The estimate over-reserves — on one
   measured turn, `$0.0000333` estimated against `$0.00001095` actually spent, **3.04×**. So (A) can
   refuse while the ledger still shows headroom. Say the request *would* exceed what is left. (In the
   run above, `preflight_refused` and `session_cap_reached` are two different sentences for exactly
   that reason.)
7. **A cassette scope in a server must wrap the LISTENER START, not the driver.** Replay matches
   calls by a session id stamped from a ContextVar, and an aiohttp request-handler task inherits the
   context that was active when `TCPSite.start()` ran. A scope around your client-side driver never
   reaches the handler and every call goes to the network. One scope per server lifetime also matters
   because the recorder writes the file on scope **exit** — a per-turn scope leaves only the last
   turn in it.
8. **Forgetting `turn_scope()` fails silently.** Cost and usage stay exact; only attribution
   vanishes, with no warning. In TypeScript use `AsyncLocalStorage.run(value, fn)` — never
   `enterWith`, which leaks across concurrent turns on Node 20/22.
9. **The JS port does not persist `TurnState` on its own.** Python's `AgentApplication.run()` awaits
   `turn_state.save()` unconditionally (`_run_after_turn_middleware` returns `True` when no handler is
   registered), which is why this recipe registers nothing — and the `session_cap_reached` assertion in
   `test_m365_agent.py` is the proof: it can only fire if turn 1's spend survived into turn 2.
   `@microsoft/agents-hosting` saves only inside `if (this._afterTurn.length > 0)` and the official
   nodejs quickstart registers nothing, so a JS ledger never accumulates and the cap never binds. The
   JS twin carries `app.onTurn('afterTurn', async () => true)` and proves it with a negative control.
10. **A second, un-instrumented client is invisible.** Budgets, gates and evidence only see calls
    through the client you wrapped. `uvx cendor-init doctor` static-checks that.
11. **A stream chunk can carry NO choices — and a fake stream never proves it.** With
    `stream_options={"include_usage": True}` (the only way a streamed call reports real usage)
    OpenAI sends a **final chunk whose `choices` list is empty**, carrying only `usage`. Measured
    against openai-python 2.48.0: **9** chunks with `include_usage`, the 9th `choices=[]`; **8**
    without it, none empty. So `chunk.choices[0]` is green forever offline and `IndexError`s on the
    first real streamed turn — which is exactly what this recipe did until 2026-07-30. Skip a
    choice-less chunk. (The TypeScript twin reads `chunk.choices?.[0]?.delta?.content ?? ''`, so it
    never had the bug; one language's optional chaining was doing load-bearing work.)
12. **The output-cap parameter is not the same on every model, and the wrong one is a hard 400.**
    The reasoning families (o-series, `gpt-5-*`) reject `max_tokens`:
    *"Unsupported parameter: 'max_tokens' is not supported with this model. Use
    'max_completion_tokens' instead."* Measured against a Foundry deployment running `gpt-5-mini`
    — i.e. the Azure swap this recipe offers. It bites
    hardest on Azure because **a deployment name is arbitrary**: `MODEL` may be `prod-chat` with a
    gpt-5 behind it, so no name heuristic is authoritative. `agent.py` defaults by name, honours
    `OUTPUT_CAP_PARAM`, and switches once if the provider names the other parameter.
13. **On a reasoning model the cap covers reasoning tokens, so a small cap can return NOTHING.**
    Same deployment, `MAX_OUTPUT_TOKENS = 48`: `37 in / 48 out` with an **empty** visible reply — the
    whole allowance went to hidden reasoning. Every governance number was correct; there was simply
    no text.
14. **An Azure deployment name is UNPRICED, so a USD budget cannot bind to it.** The same live run
    warns: *"no price for model '<your-deployment>', so the active USD budget (`on_exceed='block'`) counts
    its calls as $0 and cannot enforce a USD cap."* Name the model your deployment serves —
    `prices.register_deployment(MODEL, like="gpt-4o")` (`cendor-core` ≥ 1.16.0) — or supply exact rates
    with `prices.register_model_price(MODEL, input=…, output=…)`; alternatively use a `tokens=` cap,
    which needs no rate at all, or `configure(on_unpriced="raise")` to refuse unpriced calls outright.
    The token counts and the audit chain are exact either way — only the money is unknown. See
    [`providers/azure-foundry`](../../providers/azure-foundry/) for that failure measured end to end.

    ⚠️ **This recipe now does it for you, and the reason is worth reading.** Until 2026-07-31 this
    entry described the trap and `agent.py` did not act on it — so the *documented* Azure swap ran
    green while doing nothing. Measured against the `gpt-5-mini` deployment: `cost: $0` on every
    turn, and the session cap, the pre-flight refusal **and** the mid-stream breaker all printed
    `ok` while enforcing nothing. `main.py` still exited **0**, and the `$0` replay proof below
    compared two empty strings and reported `identical: True`. A transcript that looks like five
    passing governance demos and is five no-ops is worse than a crash, because nothing tells you.
    `GovernedAgent.__init__` now calls `price_the_deployment()` before anything can spend, which
    registers `MODEL` like `AZURE_BASE_MODEL` (default `gpt-4o-mini`) when it has no rate card —
    and **raises** on a base model cendor does not know, rather than leaving it quietly at $0. With
    it, the same live Azure run reports `$0.0000343500`, `broke_on_budget`, `session_cap_reached`
    and `preflight_refused`. A plain OpenAI model name is already priced, so it is a no-op there.

## `$0` whole-agent CI

`main.py`'s last section records the model calls once, then replays **the entire agent** — HTTP →
middleware → adapter → governed handler → channel — with the cassette in `replay` mode. Same
replies, byte for byte, no key and no network. That is the CI story: your governed agent has an
end-to-end test that costs nothing and cannot flake on a provider.

No shim is needed in either language. On `cendor-core` ≥ 1.14.1 a replayed call on an **async**
client is awaitable, so the handler's ordinary
`await client.chat.completions.create(...)` is all it takes.

## Before you deploy this

> ⚠️ **This host runs `/api/messages` in anonymous mode.** That is the supported *local* posture — it
> is what the Playground relies on — and an **open relay** in production: anyone who can reach the
> port can drive your agent and spend your tokens. A deployed agent configures a real service
> connection (`CONNECTIONS__SERVICE_CONNECTION__SETTINGS__*` with your Entra app registration) so
> `jwt_authorization_middleware` actually validates the channel's token.

Two more deployment facts, neither of them cendor's:

- **`MemoryStorage` loses the session cap on restart.** Point `AgentApplication(storage=…)` at Blob
  or Cosmos storage and the cumulative cap survives a redeploy, because it lives in the host's own
  state.
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

- **Break stops spend at the chunk boundary; the channel keeps whatever it was already sent.**
  Queued chunks cannot be unsent. Whether anything was visible depends on the channel and on how long
  the answer ran — on a non-streaming channel the user simply sees the truncated answer plus the
  notice. Never claim the visible text is cut at the exact budget token.
- **A streamed break needs a streaming channel to be *visible*.** The two ports disagree about which
  channels those are: Python's `StreamingResponse` treats only `msteams`, `webchat`/`directline` and
  `deliveryMode='stream'` as streaming — **`emulator` is not one** — while the JS port groups
  `emulator` with webchat. So validate a streamed break with
  `agentsplayground -c msteams` on Python.
- **`channelData.cendor` is for the channel / your back end.** Whether a *client* surfaces it is
  client-specific. The M365 Agents Playground's **chat pane** projects `channelData` away — but its
  **Log Panel does not**: click the outbound activity (`message 201`, the agent → Playground
  direction) and the Request tab shows the whole Activity JSON with the envelope in it (measured on
  Playground 0.2.28). Assert it in a test or log it rather than depending on a client to render it.

## Orchestration layers

| layer | cost truth | note |
|---|---|---|
| plain OpenAI / Anthropic / Azure SDK | ✅ | this recipe |
| Semantic Kernel | ✅ | `OpenAIChatCompletion(async_client=instrument(AsyncOpenAI()))` |
| LangChain | ✅ | via `cendor.core`'s LangChain callback handler |
| Microsoft Agent Framework (MAF) | ✅ from `cendor-core` 1.14.1 | `OpenAIChatClient(async_client=instrument(AsyncOpenAI()))`. MAF 1.12.1 drives OpenAI through a raw-response envelope, which 1.14.1 taught core to read; below that, usage and cost are `None`. Pin both versions in any claim — MAF moves fast |
| Teams SDK's own AI libraries | — | **deprecated by Microsoft**; use the OpenAI SDK pattern |
| .NET / C# | ❌ | **explicit non-goal** — there is no cendor .NET port. Never assume coverage |

Expect **two OpenTelemetry span families** from a governed agent — the hosting SDK's own
`microsoft_agents` spans alongside `cendor.core` / `cendor.acttrace` — and three with MAF. That is
additive, not a conflict.

### Exporting them (this recipe ships no OTel bootstrap, on purpose)

A hosted agent's telemetry belongs to the host application, not to a sample, so `agent.py` sets up
no exporter. Everything it emits reaches any OTLP backend once *your* app configures one.

⚠️ **`OTEL_EXPORTER_OTLP_ENDPOINT` on its own does nothing, and the failure is silent.** Cendor's
telemetry is `mode=auto`: the emitter attaches only once a **global** `TracerProvider` exists.
Measured 2026-08-01 — with just the variable set, `main.py` runs green and the collector receives
**nothing**; with the five lines below, the same run lands **10 calls and 45 governance events**.
`CENDOR_DEBUG_TELEMETRY=1` prints which state you are in:
`armed (mode=auto); waiting for a provider` versus `provider=detected, emitter=attached`.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)      # the ONE global setup — your app owns it
```

To watch a conversation locally rather than wire a hosted backend:

```bash
docker run --rm -p 3000:3000 -p 4318:4318 -v cendor-monitor-data:/data \
  ghcr.io/cendorhq/cendor-monitor:0.15.0
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

Cendor Monitor is optional dev tooling — no library depends on it, Cendor never operates a telemetry
endpoint, and what it shows is an **operational copy**: `verify()` runs on the audit file on your
host, never on that telemetry. See `cendor-libs/docs/observability.md`.

## Pins

The PyPI shelf this recipe was **live-verified against on 2026-07-30** — a record of what was run, not
a lockfile. `pyproject.toml` at the repo root carries the cendor floors (all `>=`, so a fresh `uv sync`
resolves forward within major 1); the host SDK is in the `agents-m365` dependency group.

```
cendor-core 1.14.2 · cendor-tokenguard 1.6.2 · cendor-guardrails 1.6.1 · cendor-contextkit 1.0.3
cendor-squeeze 1.1.1 · cendor-cassette 1.1.1 · cendor-acttrace 1.14.0
microsoft-agents-hosting-aiohttp 1.2.0
```

**No `cendor-sdk`.** This recipe is the seven libraries under somebody else's host — the SDK's agent
loop is a different door, and nothing in this topology needs it. (`run()` does work inside the handler
if you want it; it is just not what this recipe is about.)

`cendor-core >= 1.14.1` is load-bearing, not cosmetic: it is where a replayed **async** call became
awaitable again, which is what makes the offline replay above work with no app-side shim.

The TypeScript twin lives in the TypeScript cookbook:
[`agents/m365-custom-engine-js`](https://github.com/cendorhq/cendor-cookbook-js/tree/main/recipes/agents/m365-custom-engine-js)
— same agent, same governance, a different host runtime. Full docs: [cendor.ai/docs/providers → Microsoft 365 Agents
SDK](https://cendor.ai/docs/providers#microsoft-365-agents-sdk-custom-engine-agent) — this is a **libraries**
integration, not a `cendor-sdk` one.

Libraries: `core`, `tokenguard`, `guardrails`, `contextkit`, `squeeze`, `cassette`, `acttrace` · Host: `microsoft-agents-hosting-aiohttp` · Offline ✓ · [← all recipes](../../../README.md)
