# azure-foundry-otel — budget + audit calls your process never made

**Which direction is this?** **Ingest** — a managed runtime owns the loop and you hold nothing. Its
`gen_ai.*` spans come *in* via `otel.ingest()`. If you hold the client and want governance to go *out*
to your backend as spans, you want
[`frameworks/azure-foundry-otel-export`](../azure-foundry-otel-export/).

> These were one folder name until 2026-08-02. This Python file was ingest, the TypeScript file under
> the same name was export, and the `/cookbook` card described only this one — so a reader who clicked
> **TypeScript recipe →** landed on something that did not do what the card promised. A recipe folder
> name is an API shared by both trees; the name was stable and the *meaning* was not.

**The pain.** A managed runtime (like the Agent Service in Microsoft Foundry, formerly Azure AI
Foundry) runs the agent loop server-side. Your client never sees the model calls, so your cost and
audit tooling — which hooks the client — sees nothing. All you get is OpenTelemetry `gen_ai.*` spans.

**What this shows.** Forward each span's attributes to `otel.ingest()` and the call lands on the
same cendor bus as any other — so `tokenguard` budgets it and `acttrace` records it, for calls
your process never made. Fully offline by nature: the spans are built in-memory (no Azure account,
no collector). `cendor` works **alongside** Foundry via OpenTelemetry.

## Run it

```bash
uv run --group frameworks-otel python recipes/frameworks/azure-foundry-otel/main.py
```

## Expected output

```text
ingested 3 Foundry gen_ai.* spans (calls this process never made)
tokenguard: $0.018325000 across 3 calls
acttrace  : 3 llm_call entries, verify: True
```

Budgets and a verifiable audit trail, populated entirely from telemetry.

## Which Foundry span attributes to forward

`otel.ingest()` reads the OpenTelemetry GenAI semantic-convention keys:

| Span attribute | Meaning |
|---|---|
| `gen_ai.system` | provider label (e.g. `azure_ai_foundry`) |
| `gen_ai.request.model` (or `gen_ai.response.model`) | model id — used for pricing |
| `gen_ai.usage.input_tokens` (or `…prompt_tokens`) | input tokens |
| `gen_ai.usage.output_tokens` (or `…completion_tokens`) | output tokens |
| `gen_ai.usage.cached_tokens` (or `…cache_read_input_tokens`) | cached input tokens |
| `gen_ai.usage.reasoning_tokens` | reasoning output tokens |

## The two adoption points, and how to tell which one you need

`instrument()` wraps **a client you hold**. `otel.ingest()` takes **telemetry about a call you did
not make**. They are not alternatives to weigh up — the topology decides:

| you hold… | use | this recipe |
|---|---|---|
| the provider client (`openai`, `anthropic`, `boto3` …) | `instrument(client)` | [`azure-foundry-otel-export`](../azure-foundry-otel-export/) |
| nothing — a managed runtime ran the loop | `otel.ingest(attributes)` | **this one** |

`ingest()` is also the adoption point for anything that reports after the fact: see
[`observability/batch-ingest`](../../observability/batch-ingest/) for a completed Batch API job, where
pre-flight governance is structurally impossible and the accounting is still fully recoverable.

## Honest limits

⚠️ **`ingest()` normalizes telemetry; it does not measure.** It trusts the runtime's numbers. A span
carrying no usage attributes yields a call with `usage=None` and no cost — never a guess.

⚠️ **Post-hoc means post-hoc.** Nothing here can *block* a call: the runtime already made it. You get
accounting, attribution and an audit trail, not a pre-flight breaker.

⚠️ **A Foundry DEPLOYMENT name is unpriced.** These spans report `gpt-4o`, a real model id. A runtime
reporting `prod-gpt4o-eastus` needs `prices.register_deployment("prod-gpt4o-eastus", like="gpt-4o")`
first, or the cost is `None` — and a `model-router` deployment is never priceable, because it bills at
the serving model's rates while reporting the router's own id.

TypeScript twin: [`frameworks/azure-foundry-otel`](https://github.com/cendorhq/cendor-cookbook-js/tree/main/recipes/frameworks/azure-foundry-otel) ·
Sibling (the other direction): [`frameworks/azure-foundry-otel-export`](../azure-foundry-otel-export/) ·
Libraries: `core`, `tokenguard`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
