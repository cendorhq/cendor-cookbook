# azure-foundry-otel-export — Foundry governance, exported as OpenTelemetry spans

**Which direction is this?** **Export** — you hold the client. Governance goes *out* to your backend
as spans. If a managed runtime owns the loop and you hold nothing, you want the other one:
[`frameworks/azure-foundry-otel`](../azure-foundry-otel/), which brings the runtime's `gen_ai.*` spans
*in* via `otel.ingest()`. They were one folder name until 2026-08-02, when the two languages turned
out to be covering different subjects under it.

**The pain.** You run on Microsoft Foundry and already have Azure Monitor. You want governance —
budgets, refusals, an audit trail — visible in the dashboard you already look at, without adopting
another vendor's agent.

**What this shows.** Both halves of the Foundry story, ending in ordinary OTel spans:

1. the **v1 GA endpoint** with the standard `openai` client;
2. `prices.register_deployment(...)`, without which a USD budget cannot bind at all;
3. every governance event exported as a span your backend already understands.

## Run it

```bash
uv run --group frameworks-otel python recipes/frameworks/azure-foundry-otel-export/main.py
```

## Expected output

```text
deployment : prod-gpt4o-eastus -> priced like gpt-4o ($0.042500000/call)
calls that ran : 1 (the next was refused pre-flight: True)
spans exported : 3 — audit.audit_open, audit.budget_event, audit.llm_call
refusal span   : audit.budget_event
verify(file)   : True - ok: 3 entries, head 98f7bf703adf…
```

**`audit.budget_event` is the line that matters.** A refused call makes no provider request, so this
span is the *only* trace of it that ever reaches your backend. Everything else you could reconstruct
from provider logs; a refusal you could not.

## ⚠️ Two ways to accidentally export nothing

**1. No `output_reserve` ⇒ no refusal span.** Without it the pre-flight projection counts input only,
the cap is crossed at *settlement* instead, and a post-flight overspend raises the same
`BudgetExceeded` while emitting **no `BudgetEvent`** — because by then the call already happened.

**2. A stub-sized prompt ⇒ no refusal span either.** The projection counts the tokens actually in
`messages`; the fake's reported usage only governs what settles. With a one-word prompt the
projection is ~nothing and the block is again post-flight. This recipe uses a realistic prompt for
exactly that reason.

## In production

```python
from azure.monitor.opentelemetry import configure_azure_monitor
configure_azure_monitor()     # sets the GLOBAL provider; change nothing else
```

⚠️ The recipe injects an explicit `tracer` instead, because **asserting against the global provider
is an assertion that passes whether or not your code emitted anything** — there is always *a*
provider, and a no-op one records nothing and complains about nothing.

## Honest limits

⚠️ **The FILE is the evidence; the spans are an operational copy.** `verify()` runs on the file and
never on the mirror — losing your telemetry backend must not invalidate the record.

⚠️ **`azure-ai-inference` is captured by NOTHING** (different client shape; returned untouched, and
Microsoft retires it 2026-08-26). ⚠️ **A `model-router` deployment is not priceable** — it bills at
the serving model's rates while reporting the router's own id, so no single registration is correct.

⚠️ **The recipe does not print those warnings**, unlike its TypeScript twin, and that is deliberate:
a `⚠️` inside a Python `print()` raises `UnicodeEncodeError` on a Windows console (cp1252). CI is
Linux, so nothing would catch it. Every other recipe in this tree keeps its warnings in the docstring
and the README for the same reason.

TypeScript twin: [`frameworks/azure-foundry-otel-export`](https://github.com/cendorhq/cendor-cookbook-js/tree/main/recipes/frameworks/azure-foundry-otel-export) ·
Sibling (the other direction): [`frameworks/azure-foundry-otel`](../azure-foundry-otel/) — ingest a managed runtime's spans ·
Libraries: `core`, `tokenguard`, `acttrace` · Offline ✓ · Live switch: none (offline only) · [← all recipes](../../../README.md)
