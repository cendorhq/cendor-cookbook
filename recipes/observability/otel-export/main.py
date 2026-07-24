"""otel-export — stream governance to your OpenTelemetry backend, offline.

Cendor emits standard `gen_ai.*` telemetry into the **global** OpenTelemetry provider your app
configures — so spend metrics and the audit trail flow to Azure Monitor / CloudWatch / Datadog / any
OTLP backend with **no Cendor-specific exporter**. This recipe proves it with IN-MEMORY OTel readers
(no account, no collector, no network):

  1. `use_sink(OTelSink())`         — spend rows become metric counters, dimensioned by track() tags.
  2. `AuditLog(mirror=OTelMirror())` — every chained audit entry also becomes an `audit.<type>` span.
  3. A pre-flight `budget(..., on_exceed="block")` trips a `BudgetEvent`, which acttrace chains as a
     `budget_event` and the mirror exports as an `audit.budget_event` span — the one signal a
     *refused* call ever leaves.

The hash-chained file stays the sole verifiable evidence (`verify()` runs on it, never the mirror).
In production you'd replace the two in-memory readers with one line — e.g.
`azure.monitor.opentelemetry.configure_azure_monitor(...)` — and change nothing else. Run:

  uv run --group observability-otel python recipes/observability/otel-export/main.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor.acttrace import AuditLog, OTelMirror, verify
from cendor.core import instrument
from cendor.tokenguard import BudgetExceeded, budget, report, reset, track, use_sink
from cendor.tokenguard.sinks import OTelSink
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

SIGNING_KEY = "demo-signing-key"


def configure_otel() -> tuple[InMemorySpanExporter, InMemoryMetricReader]:
    """Stand in for your backend's distro: set the GLOBAL OTel providers to in-memory readers.

    In production this is one call to your vendor (`configure_azure_monitor()`, `useAzureMonitor()`)
    or an OTLP exporter — Cendor emits into whatever is set here.
    """
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    metric_reader = InMemoryMetricReader()
    metrics.set_meter_provider(MeterProvider(metric_readers=[metric_reader]))
    return span_exporter, metric_reader


def fake_client() -> object:
    """An instrumented OpenAI-shaped client — real pricing/audit, no network, no key."""

    class Completions:
        def create(self, **kwargs: object) -> object:
            return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500))

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def token_usage_total(metric_reader: InMemoryMetricReader) -> int:
    """Sum the `gen_ai.client.token.usage` counter across all attribute sets (defensive read)."""
    data = metric_reader.get_metrics_data()
    total = 0
    for rm in getattr(data, "resource_metrics", []):
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == "gen_ai.client.token.usage":
                    total += sum(point.value for point in metric.data.data_points)
    return total


def main() -> None:
    reset()
    span_exporter, metric_reader = configure_otel()

    use_sink(OTelSink())  # spend -> OTel metrics (dimensioned by model + track() tags)
    audit = AuditLog(
        system="support", risk_tier="limited", signing_key=SIGNING_KEY, mirror=OTelMirror()
    )
    client = fake_client()

    blocked = False
    with track(feature="support", user_id="alice"):
        with audit.decision(input="refund please", actor="agent"):
            try:
                # $5-per-call model here is ~$0.0075; a $0.01 cap lets call 1 run and blocks call 2.
                with budget(usd=0.01, on_exceed="block", scope="session"):
                    client.chat.completions.create(
                        model="gpt-4o", messages=[{"role": "user", "content": "refund order 42"}]
                    )
                    client.chat.completions.create(
                        model="gpt-4o", messages=[{"role": "user", "content": "and order 43"}]
                    )
            except BudgetExceeded:
                blocked = True  # the pre-flight breaker fired -> a BudgetEvent rode the bus

    audit.detach()

    # ---- read the telemetry back (what your backend would have received) ----------------------
    spans = span_exporter.get_finished_spans()
    span_names = sorted({s.name for s in spans})
    tokens_exported = token_usage_total(metric_reader)
    r = report(group_by=["feature"])

    print(f"budget breaker fired (call blocked pre-flight): {blocked}")
    print(
        f"spend -> OTel metrics : {tokens_exported} tokens on gen_ai.client.token.usage "
        f"(local report: ${r.total().amount})"
    )
    print(f"audit -> OTel spans   : {len(spans)} mirrored ({', '.join(span_names)})")
    assert "audit.budget_event" in span_names, "the budget block should mirror as a span"

    # the file — not the mirror — is the evidence: verify it offline.
    with tempfile.TemporaryDirectory() as d:
        evidence = str(Path(d) / "evidence.jsonl")
        audit.export(evidence, framework="eu_ai_act")
        ok, detail = verify(evidence, key=SIGNING_KEY)
    print(f"audit file (evidence) : verify -> {ok} ({detail})")


if __name__ == "__main__":
    main()
