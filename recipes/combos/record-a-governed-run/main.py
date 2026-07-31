"""record-a-governed-run — record the whole governed triad once, re-run it forever for $0.

The usual objection to governance in CI is cost: if every test run makes real calls, you pay to
prove your budget works. `cassette` removes the bill without removing the governance. Record a run
that is budgeted (tokenguard) and audited (acttrace); on replay the provider is **never reached**,
yet the same budget accrues the recorded usage and the same audit chain is written and verifies.

The proof is a client that raises if it is ever called. If the replay reached the provider, this
recipe crashes instead of printing.

Offline both ways: recording drives a fake OpenAI-shaped client into a temp cassette, and the
replay reads it back. No key, nothing committed.

  uv run python recipes/combos/record-a-governed-run/main.py
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor import cassette
from cendor.acttrace import AuditLog, verify
from cendor.core import instrument
from cendor.tokenguard import budget, report, reset, track

MODEL = "gpt-4o"
PROMPT = [{"role": "user", "content": "summarize the release notes"}]


class Provider:
    """A fake OpenAI-shaped client. `boom=True` makes any real call an immediate failure — which is
    how the $0 claim is *proven* rather than asserted."""

    def __init__(self, *, boom: bool = False) -> None:
        self.boom = boom
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.boom:
            raise AssertionError("a replayed run must never reach the provider")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="three fixes, one feature"))],
            usage=SimpleNamespace(prompt_tokens=820, completion_tokens=140),
            model=MODEL,
        )


def client(provider: Provider):
    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=provider)))


def main() -> None:
    reset()
    tmp = Path(tempfile.mkdtemp(prefix="cendor-recipe-"))
    tape, chain = tmp / "release-notes.json", tmp / "replay-audit.jsonl"

    # ---- pass 1: record a governed run (the only pass that would cost money) -------------------
    live = Provider()
    with track(feature="release-notes"), budget(usd=0.50, on_exceed="block"):
        with cassette.using(str(tape), mode="record"):
            client(live).chat.completions.create(model=MODEL, messages=PROMPT)

    # ---- pass 2: replay it. Same governance, same audit, no provider. --------------------------
    audit = AuditLog(system="release-notes", risk_tier="limited", path=str(chain))
    boom = Provider(boom=True)
    try:
        with track(feature="release-notes-replay"), budget(usd=0.50, on_exceed="block"):
            with cassette.using(str(tape), mode="replay"):
                replayed = client(boom).chat.completions.create(model=MODEL, messages=PROMPT)
    finally:
        audit.detach()

    rows = {r["tags"].get("feature"): r for r in report(group_by=["feature"]).rows}
    recorded_row, replay_row = rows["release-notes"], rows["release-notes-replay"]
    audited = [e for e in audit.entries if e.type == "llm_call"]
    ok, detail = verify(str(chain))

    def line(label, calls, row):
        return f"{label}: provider called {calls}x · {row['tokens']} tok · ${row['usd'].amount}"

    print(line("record  ", live.calls, recorded_row))
    print(line("replay  ", boom.calls, replay_row))
    print("          ^ the same tokens are accounted, with $0 of REAL spend")
    print(f"answer  : {replayed.choices[0].message.content!r}")
    print(f"audited : {len(audited)} llm_call entry chained on the replay")
    print(f"verify(): {ok} — {detail}")
    print(f"cassette: {tape.stat().st_size} bytes on disk — commit it and CI runs free")

    assert live.calls == 1 and boom.calls == 0, "the replay must short-circuit the provider"
    same = replay_row["tokens"] == recorded_row["tokens"]
    assert same, "the replay did not accrue the recorded usage"
    assert audited, "the replayed call was not chained by the attached audit log"
    assert ok is True, "the replay audit chain failed verify()"


if __name__ == "__main__":
    main()
