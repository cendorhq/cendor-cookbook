"""azure-foundry-otel — budget + audit calls your process never made.

A managed runtime (e.g. the Agent Service in Microsoft Foundry, formerly Azure AI Foundry) owns the
agent loop server-side; your client never sees the calls. But it emits OpenTelemetry `gen_ai.*`
spans. Forward each span's attributes to `otel.ingest()` and the call lands on the same cendor bus
— so tokenguard budgets it and acttrace records it, exactly as if you'd made the call yourself.

Fully offline by nature (in-memory spans; no Azure account, no collector). Run:
  uv run python recipes/frameworks/azure-foundry-otel/main.py
"""

from cendor.acttrace import AuditLog, verify
from cendor.core import otel
from cendor.tokenguard import report, reset, track
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

SIGNING_KEY = "demo-signing-key"

# Three turns of a Foundry-hosted agent, as gen_ai.* span attributes (model, tokens, cache).
FOUNDRY_TURNS = [
    {"gen_ai.request.model": "gpt-4o", "in": 1200, "out": 400, "cached": 0},
    {"gen_ai.request.model": "gpt-4o", "in": 1500, "out": 350, "cached": 300},
    {"gen_ai.request.model": "gpt-4o", "in": 900, "out": 220, "cached": 0},
]


def emit_foundry_spans():
    """Stand in for Foundry's telemetry: real OTel spans carrying gen_ai.* attributes."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("azure-foundry-agent")
    for turn in FOUNDRY_TURNS:
        with tracer.start_as_current_span("chat gpt-4o") as span:
            span.set_attribute("gen_ai.system", "azure_ai_foundry")
            span.set_attribute("gen_ai.request.model", turn["gen_ai.request.model"])
            span.set_attribute("gen_ai.usage.input_tokens", turn["in"])
            span.set_attribute("gen_ai.usage.output_tokens", turn["out"])
            span.set_attribute("gen_ai.usage.cached_tokens", turn["cached"])
    return exporter.get_finished_spans()


def main() -> None:
    reset()
    audit = AuditLog(system="foundry_agent", risk_tier="limited", signing_key=SIGNING_KEY)
    spans = emit_foundry_spans()

    with track(feature="foundry_agent"):
        for span in spans:
            otel.ingest(dict(span.attributes))  # forward the span -> normalized LLMCall on the bus
    audit.detach()

    r = report(group_by=["feature"])
    print(f"ingested {len(spans)} Foundry gen_ai.* spans (calls this process never made)")
    print(f"tokenguard: ${r.total().amount} across {sum(row['calls'] for row in r)} calls")

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        evidence = str(Path(d) / "evidence.jsonl")
        audit.export(evidence, framework="eu_ai_act")
        ok, _ = verify(evidence, key=SIGNING_KEY)
    entries = sum(1 for e in audit.entries if e.type == "llm_call")
    print(f"acttrace  : {entries} llm_call entries, verify: {ok}")


if __name__ == "__main__":
    main()
