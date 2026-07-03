"""anthropic — make prompt-cache billing legible, and audit the call.

Anthropic's prompt caching splits usage into `input_tokens`, `cache_read_input_tokens`, and
`cache_creation_input_tokens` — priced at three different rates. `instrument()` normalizes cache
*reads* into `input_tokens` (as a `cached` subset) and tracks cache *writes* as their own billed
category, so the cost matches Anthropic's formula. The same call is recorded to a tamper-evident
audit trail.

Offline: fake `messages.create` shape. Run:
  uv run python recipes/providers/anthropic/main.py

Record a real cassette (maintainer, needs a key + `anthropic` installed):
  RECORD=1 ANTHROPIC_API_KEY=sk-ant-... uv run python recipes/providers/anthropic/main.py
"""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor.acttrace import AuditLog, verify
from cendor.core import bus, instrument

SIGNING_KEY = os.environ.get("CENDOR_DEMO_KEY", "demo-signing-key")


def fake_anthropic():
    """Stand-in for `Anthropic()` — `messages.create` reporting cache read + write tokens."""

    class Messages:
        def create(self, **kwargs):
            return SimpleNamespace(
                usage=SimpleNamespace(
                    input_tokens=1000,  # uncached input
                    output_tokens=200,
                    cache_read_input_tokens=800,  # billed at the cache-read rate
                    cache_creation_input_tokens=300,  # billed at the cache-write rate
                )
            )

    return SimpleNamespace(messages=Messages())


def show(call) -> None:
    u = call.usage
    print(
        f"usage: {u.input_tokens:,} in ({u.cached_tokens} cache-read) + "
        f"{u.cache_write} cache-write -> {u.output_tokens} out"
    )
    print(f"cost : ${call.cost.amount}  (uncached input + cache-read + cache-write + output)")


def record_live() -> None:  # RECORD=1 path — ships unrecorded
    from anthropic import Anthropic
    from cendor import cassette

    client = instrument(Anthropic())
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "anthropic.json")

    @cassette.use(fixture, mode="record")
    def one_call():
        client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=64,
            messages=[{"role": "user", "content": "Say hi."}],
        )

    one_call()
    print(f"recorded live call to {fixture}")


def main() -> None:
    if os.environ.get("RECORD") == "1":
        record_live()
        return

    bus.subscribe(show)
    with tempfile.TemporaryDirectory() as d:
        evidence = str(Path(d) / "evidence.jsonl")
        audit = AuditLog(system="assistant", risk_tier="limited", signing_key=SIGNING_KEY)
        client = instrument(fake_anthropic())
        with audit.decision(input="cache-heavy prompt", actor="agent") as dec:
            client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=256,
                messages=[{"role": "user", "content": "Answer using the cached system prompt."}],
            )
            dec.record(model="claude-sonnet-4-6")
        audit.export(evidence, framework="eu_ai_act")
        audit.detach()
        ok, detail = verify(evidence, key=SIGNING_KEY)
        print(f"audit: exported + {('verified' if ok else 'FAILED')} ({detail})")


if __name__ == "__main__":
    main()
