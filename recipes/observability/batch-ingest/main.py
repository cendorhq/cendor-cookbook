"""batch-ingest — account for a completed Batch API job's spend, offline (L15).

The OpenAI/Anthropic **Batch API** is server-side and returns results *hours* later, so pre-flight
governance (a budget breaker, a guardrail) is structurally impossible — there is nothing to
intercept at call time. But the **accounting** is fully recoverable after the fact: each result line
carries its token usage, and `cendor.core.otel.ingest(...)` turns those `gen_ai.*` numbers into a
normalized `LLMCall` on the same event bus a local call rides — so `tokenguard` prices + reports it,
and an `OTelSink` / `acttrace` mirror see it too, *exactly* as if it had been instrumented locally.

Run each ingest under `track(...)` + `trace(batch_id)` and the whole batch is attributed to a
feature and correlated as one run. **Zero library change, no network, no key** — this recipe reads a
canned batch-results payload; in production you'd stream the job's downloaded `output.jsonl` lines.

  uv run --group observability-otel python recipes/observability/batch-ingest/main.py
"""

from __future__ import annotations

import json

from cendor.core import otel, trace
from cendor.tokenguard import report, reset, track

# A completed batch job's downloaded results (OpenAI Batch `output.jsonl` shape, trimmed to the
# fields that matter for accounting). In production these are the lines of the file the job returns.
_BATCH_OUTPUT_JSONL = "\n".join(
    json.dumps(line)
    for line in [
        {
            "custom_id": "req-1",
            "response": {
                "body": {
                    "model": "gpt-4o",
                    "usage": {"prompt_tokens": 1200, "completion_tokens": 300},
                }
            },
        },
        {
            "custom_id": "req-2",
            "response": {
                "body": {
                    "model": "gpt-4o",
                    "usage": {"prompt_tokens": 800, "completion_tokens": 150},
                }
            },
        },
        {
            "custom_id": "req-3",
            "response": {
                "body": {
                    "model": "gpt-4o",
                    "usage": {"prompt_tokens": 2000, "completion_tokens": 640},
                }
            },
        },
    ]
)


def ingest_batch(output_jsonl: str, *, batch_id: str, feature: str) -> int:
    """Attribute a completed batch's spend: one governed `LLMCall` per line (returns the count).

    Each line's usage becomes `gen_ai.*` attributes fed to `otel.ingest`, under `track()` (so the
    spend is tagged with the feature + batch) and `trace(batch_id)` (so all lines correlate as one
    run — `ingest` stamps the ambient trace id onto the call). No pre-flight gate is possible here;
    this is *post-hoc accounting*, which is exactly what the Batch API leaves room for.
    """
    count = 0
    # trace() outside the loop so every ingested line shares one run/trace id (one batch = one run).
    with track(feature=feature, batch_id=batch_id), trace(batch_id):
        for raw in output_jsonl.splitlines():
            if not raw.strip():
                continue
            line = json.loads(raw)
            body = line["response"]["body"]
            usage = body["usage"]
            otel.ingest(
                {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": body["model"],
                    "gen_ai.usage.input_tokens": usage["prompt_tokens"],
                    "gen_ai.usage.output_tokens": usage["completion_tokens"],
                }
            )
            count += 1
    return count


def main() -> None:
    reset()
    n = ingest_batch(_BATCH_OUTPUT_JSONL, batch_id="batch_2026_07_23", feature="nightly-summaries")

    r = report(group_by=["feature"])
    cost = r.total()  # Report.total() is the aggregate cost (Money); tokens live on the rows
    tokens_in = sum(row["input_tokens"] for row in r)
    tokens_out = sum(row["output_tokens"] for row in r)
    print(f"ingested batch lines : {n}")
    print(f"batch spend attributed: ${cost.amount} across feature=nightly-summaries")
    print(f"tokens                : {tokens_in} in / {tokens_out} out")

    # The batch's spend now shows up in the same report a live run does — post-hoc, but accounted.
    assert n == 3, "every result line should be ingested"
    assert tokens_in == 4000 and tokens_out == 1090, "usage summed across lines"
    assert cost.amount > 0, "priced via the local price table (gpt-4o), no network"
    print("OK — server-side batch spend is governed after the fact (no pre-flight possible).")


if __name__ == "__main__":
    main()
