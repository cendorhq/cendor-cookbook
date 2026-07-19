# otel-export — stream governance to your OpenTelemetry backend

**What this shows.** Cendor emits standard `gen_ai.*` telemetry into the **global** OpenTelemetry
provider your app configures — so spend metrics and the audit trail flow to **Azure Monitor /
Application Insights, AWS CloudWatch, Datadog, Grafana, or any OTLP backend** with **no
Cendor-specific exporter**. This recipe proves it end to end, fully offline (in-memory OTel readers
stand in for a collector — no account, no network, no key).

Three attachments do the work:

1. `use_sink(OTelSink())` — each spend row becomes OpenTelemetry **metric** counters
   (`gen_ai.client.token.usage` / `.cost.usd` / `.reasoning.token.usage`), dimensioned by `model` and
   your `track(...)` tags.
2. `AuditLog(mirror=OTelMirror())` — every chained audit entry (decisions, `llm_call`,
   `budget_event`, `policy_flag`, human oversight) is **also** emitted as an `audit.<type>` **span**.
3. A pre-flight `budget(..., on_exceed="block")` trips a `BudgetEvent` — the one signal a *refused*
   call ever leaves — which acttrace chains as a `budget_event` and the mirror exports as an
   `audit.budget_event` span.

```bash
uv run --group observability-otel python recipes/observability/otel-export/main.py
```

Expected output: the budget breaker fires, 1,500 tokens land on the spend counter, five `audit.*`
spans are mirrored (including `audit.budget_event`), and the evidence file verifies.

## The one-line change for production

Replace the two in-memory readers in `configure_otel()` with your backend's distro and change nothing
else:

```python
# Azure Monitor / Application Insights
from azure.monitor.opentelemetry import configure_azure_monitor
configure_azure_monitor(connection_string="InstrumentationKey=…")
# …then the same use_sink(OTelSink()) + AuditLog(mirror=OTelMirror()) as here.
```

Any OTLP backend works the same way — set `OTEL_EXPORTER_OTLP_ENDPOINT` and start an OTel SDK. See the
[Observability guide](https://cendor.ai/docs/observability).

## Honest limits

- **Cendor exports; it doesn't collect.** You configure the OpenTelemetry pipeline (a collector or a
  vendor distro) in your process — Cendor never runs one for you (local-first).
- **The mirror is an operational copy, not the evidence.** `verify()` runs on the hash-chained file,
  never on the mirror. Keep the file (or a signed `export()` pack) as the compliance record.
- **Metric cardinality.** `OTelSink` dimensions spend by your `track(...)` tags — keep tag *values*
  low-cardinality (`feature`, `tenant`) or pass `OTelSink(tags=False)` for model-only counters.
