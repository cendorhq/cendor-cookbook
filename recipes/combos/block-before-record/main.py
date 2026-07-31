"""block-before-record — a call that never happened leaves nothing to replay.

Ordering is the whole subject here. `guardrails` blocks *pre-flight*, before the request leaves your
process; `cassette` records on the *response*. So a blocked call is refused before the recorder ever
sees anything — and that is the behaviour you want. If a block were recorded, your cassette would
grow entries for requests that were never sent, and a later replay would happily "replay" a call the
guardrail exists to prevent.

This recipe records that ordering as a measurement: with a `keyword_deny` guardrail installed, a
forbidden prompt inside a `cassette.using(..., mode="record")` scope reaches the provider **zero**
times and writes **zero** cassette entries, while a clean prompt in the same scope records normally.

Two libraries, no import between them: guardrails registers a core interceptor, cassette registers
its own, and core runs them in the documented order. Offline, keyless.

  uv run python recipes/combos/block-before-record/main.py
"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor import cassette
from cendor.core import instrument
from cendor.guardrails import GuardrailTripped, install, rules, uninstall

MODEL = "gpt-4o"


def counting_client(calls: dict):
    """A fake OpenAI-shaped client that counts every request that actually reaches it."""

    class Completions:
        def create(self, **kw):
            calls["n"] += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="here is the summary"))],
                usage=SimpleNamespace(prompt_tokens=30, completion_tokens=8),
                model=MODEL,
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def entries_in(tape: Path) -> int:
    if not tape.exists():
        return 0
    return len(json.loads(tape.read_text(encoding="utf-8"))["entries"])


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cendor-recipe-"))
    tape = tmp / "support.json"
    calls = {"n": 0}
    client = counting_client(calls)

    install([rules.keyword_deny(["wire transfer"], action="block")])
    tripped = None
    try:
        with cassette.using(str(tape), mode="record"):
            # 1 — the clean request: allowed, sent, recorded.
            client.chat.completions.create(
                model=MODEL, messages=[{"role": "user", "content": "summarize ticket 41"}]
            )

            # 2 — the forbidden one: refused before the provider, so never recorded.
            try:
                client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": "arrange a wire transfer now"}],
                )
            except GuardrailTripped as exc:
                tripped = exc
    finally:
        uninstall()

    recorded = entries_in(tape)

    print("clean request    : reached the provider, recorded")
    print(f"blocked request  : GuardrailTripped - {tripped}")
    print(f"provider calls   : {calls['n']} (the blocked one never left the process)")
    print(f"cassette entries : {recorded} - one per call that actually happened")
    print("nothing to replay: a request that was refused has no recorded response to hand back")

    assert tripped is not None, "the guardrail did not block the forbidden request"
    assert calls["n"] == 1, "the blocked request reached the provider"
    assert recorded == 1, "a blocked call was written to the cassette"


if __name__ == "__main__":
    main()
