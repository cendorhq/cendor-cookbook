# batch-ingest — account for a completed Batch API job's spend

**What this shows.** The provider **Batch API** (OpenAI / Anthropic) runs server-side and returns
results *hours* later, so pre-flight governance — a `budget(..., on_exceed="block")` breaker, a
guardrail — is **structurally impossible**: there is no call to intercept at request time. The
*accounting*, though, is fully recoverable. Each result line carries its token usage, and
`cendor.core.otel.ingest(...)` turns those `gen_ai.*` numbers into a normalized `LLMCall` on the same
event bus a live call rides — so `tokenguard` prices and reports it, and an `OTelSink` / `acttrace`
mirror see it too, exactly as if it had been instrumented locally.

## Run it

```bash
uv run --group observability-otel python recipes/observability/batch-ingest/main.py
```

## Expected output

```text
ingested batch lines : 3
batch spend attributed: $0.020900000 across feature=nightly-summaries
tokens                : 4000 in / 1090 out
OK — server-side batch spend is governed after the fact (no pre-flight possible).
```

## How it works

The recipe reads a canned batch `output.jsonl` payload (offline — no key, no network). In production
you'd stream the lines of the file the finished job hands back:

```python
with track(feature="nightly-summaries", batch_id=job.id), trace(job.id):
    for line in downloaded_output_jsonl:  # the job's result file, one JSON object per line
        body = line["response"]["body"]
        otel.ingest({
            "gen_ai.system": "openai",
            "gen_ai.request.model": body["model"],
            "gen_ai.usage.input_tokens": body["usage"]["prompt_tokens"],
            "gen_ai.usage.output_tokens": body["usage"]["completion_tokens"],
        })
```

`track(...)` tags the batch's spend with your feature; `trace(batch_id)` correlates every line as one
run (`ingest` stamps the ambient trace id onto each call). Then `report()` shows the batch alongside
your live runs, and any attached `OTelSink` exports it — **zero library change**.

## Honest limits

- **Post-hoc only — no pre-flight for batches.** A batch is decided and billed on the provider's
  servers; Cendor can *account* for it after the results land, but it cannot *block* or *clamp* it
  the way it does a live call. Budget breakers and guardrails apply to interactive/streamed calls, not
  to a batch already submitted.
- **You supply the usage.** Accounting is only as accurate as the `usage` the provider returns on each
  line; a line without usage prices to `$0` (there is nothing to count).
- **`ingest` is the managed-runtime capture path** — the same seam used for Foundry Agent Service /
  OpenAI Assistants (see the [Observability guide](https://cendor.ai/docs/observability)). It needs no
  OpenTelemetry dependency; the `observability-otel` group here is only for parity with the sibling
  recipe.

Libraries: `core`, `tokenguard` · Offline ✓ · [← all recipes](../../../README.md)
