# azure-foundry-otel — budget + audit calls your process never made

**The pain.** A managed runtime (like Azure AI Foundry's Agent Service) runs the agent loop
server-side. Your client never sees the model calls, so your cost and audit tooling — which hooks
the client — sees nothing. All you get is OpenTelemetry `gen_ai.*` spans.

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

Libraries: `core`, `tokenguard`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
