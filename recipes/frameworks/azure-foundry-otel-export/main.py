"""azure-foundry-otel-export — Microsoft Foundry governance, exported as OpenTelemetry spans.

The EXPORT direction: you hold the client, you `instrument()` it, and governance goes OUT to your
backend as ordinary spans. Its twin `frameworks/azure-foundry-otel` is the INGEST direction — a
managed runtime owns the loop, you hold nothing, and its `gen_ai.*` spans come IN via
`otel.ingest()`. Two folders because they are two subjects; a shared name would make one of them a
lie in whichever language you opened second.

This is the two halves of the Foundry story in one file:

  1. the **v1 GA endpoint** with the standard `openai` client — no `AzureOpenAI` class, no
     `api-version`, and no `azure-ai-inference` (which `instrument()` captures NOTHING from);
  2. a deployment name is **unpriced**, so `prices.register_deployment(...)` is what makes a USD
     budget able to bind at all;

...and then every governance event lands in your existing OTel backend as a standard span. Azure
Monitor is one `configure_azure_monitor()` call in production; here it is an in-memory exporter so
the recipe stays offline and its assertions can only pass if something was really emitted.

⚠️ **Injected tracer, not a global provider.** `OTelMirror(tracer)` takes the instrument explicitly.
Asserting against the global provider is an assertion that passes whether or not your code emitted
anything — there is always *a* provider, and a no-op one records nothing.

Offline: a fake OpenAI-shaped client + in-memory OTel. No key, no network. Run:

  uv run --group frameworks-otel python recipes/frameworks/azure-foundry-otel-export/main.py

Honest limits:

⚠️ **The FILE is the evidence; the spans are an operational copy.** `verify()` runs on the file and
never on the mirror — losing your telemetry backend must not invalidate the record.

⚠️ **A `model-router` deployment is NOT priceable:** it bills at the serving model's rates while
reporting the router's own id, so no single registration is ever correct.

⚠️ **`azure-ai-inference` is captured by NOTHING** — a different client shape, returned untouched,
and Microsoft retires it 2026-08-26.

(These stay in the docstring and the README rather than a closing `print()`, which is the convention
every other recipe here follows — and there is a reason beyond consistency: a `⚠️` in a `print()`
raises `UnicodeEncodeError` on a Windows console, whose default encoding is cp1252. CI is Linux, so
nothing would have caught it. Measured while writing this recipe; the TypeScript twin prints its
warnings safely because Node always writes UTF-8.)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor.acttrace import AuditLog, OTelMirror, verify
from cendor.core import LLMCall, bus, instrument, prices
from cendor.tokenguard import BudgetExceeded, budget, reset
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

SIGNING_KEY = "demo-signing-key"
DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "prod-gpt4o-eastus")
BASE_MODEL = os.environ.get("AZURE_BASE_MODEL", "gpt-4o")
IN_TOKENS = 11_000
OUT_TOKENS = 1_500
# ⚠️ A REAL prompt, not a one-word stub. The pre-flight projection counts the tokens actually in
# `messages`; the fake's reported usage only governs what SETTLES. With a one-character prompt the
# projection is ~nothing, the cap is never crossed before the call, and you get a POST-flight
# overspend — which raises the same BudgetExceeded but emits NO BudgetEvent, so the refusal never
# reaches your telemetry backend. Measured while writing the TypeScript twin.
CLAIM = "The claimant's policy history plus the adjuster's notes and the repair estimate. " * 1000


def fake_foundry() -> object:
    """Stand-in for the v1 GA client. Foundry echoes the DEPLOYMENT name back, not a model id."""

    class Completions:
        def create(self, **kwargs: object) -> object:
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Approved."))],
                usage=SimpleNamespace(prompt_tokens=IN_TOKENS, completion_tokens=OUT_TOKENS),
                model=DEPLOYMENT,
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def main() -> None:
    # In production this whole block is one line from your vendor's distro:
    #   from azure.monitor.opentelemetry import configure_azure_monitor
    #   configure_azure_monitor()        # sets the GLOBAL provider; change nothing else below
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    tracer = tracer_provider.get_tracer("cendor-recipe")

    reset()
    bus._reset()
    calls: list[LLMCall] = []
    bus.subscribe(lambda e: calls.append(e) if isinstance(e, LLMCall) else None)

    client = instrument(fake_foundry())

    # (2) make the deployment priceable, or the USD budget below is a silent no-op.
    prices.register_deployment(DEPLOYMENT, like=BASE_MODEL)
    unit = prices.estimate(DEPLOYMENT, IN_TOKENS, output_tokens=OUT_TOKENS)
    print(f"deployment : {DEPLOYMENT} -> priced like {BASE_MODEL} (${unit.amount}/call)")

    with tempfile.TemporaryDirectory() as d:
        chain = str(Path(d) / "audit.jsonl")
        audit = AuditLog(
            system="foundry-triage",
            risk_tier="high",
            path=chain,
            signing_key=SIGNING_KEY,
            mirror=OTelMirror(tracer),
        )

        # `output_reserve` is what makes the block PRE-flight. Without it the projection counts
        # input only, the cap is crossed at settlement instead, and a post-flight overspend emits no
        # BudgetEvent — so the refusal would never reach your backend at all.
        blocked = False
        try:
            with budget(
                usd=0.06,
                on_exceed="block",
                output_reserve=OUT_TOKENS,
                name="foundry-triage cap",  # a BOUNDED identifier — it becomes a metric attribute
            ):
                for _ in range(8):
                    client.chat.completions.create(
                        model=DEPLOYMENT, messages=[{"role": "user", "content": CLAIM}]
                    )
        except BudgetExceeded:
            blocked = True
        finally:
            audit.detach()

        spans = span_exporter.get_finished_spans()
        span_names = sorted({s.name for s in spans})
        budget_span = next((s for s in spans if s.name == "audit.budget_event"), None)
        ok, detail = verify(chain, key=SIGNING_KEY)

    print(f"calls that ran : {len(calls)} (the next was refused pre-flight: {blocked})")
    print(f"spans exported : {len(spans)} — {', '.join(span_names)}")
    print(f"refusal span   : {budget_span.name if budget_span else 'MISSING'}")
    print(f"verify(file)   : {ok} - {detail}")
    print("\nAzure Monitor sees these as ordinary spans. Nothing Cendor-specific is exported.")

    assert unit.amount > 0, "register_deployment() did not make the deployment priceable"
    assert blocked, "the USD cap never bound — the deployment is still effectively unpriced"
    assert 0 < len(calls) < 8, f"the cap should bind mid-loop, got {len(calls)}"
    assert spans, "the OTelMirror exported no spans at all"
    # The refusal is the whole point of exporting governance: a blocked call makes no provider
    # request, so this span is the ONLY trace of it that ever reaches your backend.
    assert budget_span, f"no audit.budget_event span — a refused call left no trace: {span_names}"
    assert ok, "the hash-chained file failed verify()"

    # The honest limits live in the module docstring and the README, not in a print — see there.
    print("\nThe file is the evidence; the spans are its operational copy. See the README.")


if __name__ == "__main__":
    main()
