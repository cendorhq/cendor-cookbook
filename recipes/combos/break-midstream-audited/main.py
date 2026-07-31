"""break-midstream-audited — cut a runaway stream mid-flight, and keep the evidence.

A pre-flight cap cannot help you here. The model was asked for one paragraph and is 4,000 tokens
into a loop; the request was already approved, and by the time the response settles you have paid.
`on_exceed="break"` is the guard for exactly that shape: tokenguard registers a per-chunk observer
on core's stream seam, and when the running output estimate crosses the cap it closes the provider
stream, keeps the partial text, and raises **once**.

The cut is a governance action, so it is chained: acttrace records a `budget_event(action="broken")`
on the same tamper-evident file as everything else, and the chain still verifies.

`break` is not a replacement for `block` — see `recipes/libs/tokenguard-hard-vs-runaway` for
choosing between them. Offline: a fake streaming client, no key.

  uv run python recipes/combos/break-midstream-audited/main.py
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor.acttrace import AuditLog, verify
from cendor.core import instrument
from cendor.tokenguard import BudgetExceeded, budget, reset

MODEL = "gpt-4o"
CHUNKS = 60


def runaway_client():
    """A provider stream that will not stop. `closed['v']` flips when core closes it on the cut —
    which is what proves the break reached the socket, not just the consumer's loop."""
    closed = {"v": False}
    chunks = [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="and then "))])
        for _ in range(CHUNKS)
    ]

    class Stream:
        def __init__(self) -> None:
            self._it = iter(chunks)

        def __iter__(self):
            return self

        def __next__(self):
            return next(self._it)

        def close(self) -> None:
            closed["v"] = True

    class Completions:
        def create(self, **kw):
            return Stream()

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions()))), closed


def main() -> None:
    reset()
    tmp = Path(tempfile.mkdtemp(prefix="cendor-recipe-"))
    chain = tmp / "stream-break.jsonl"

    audit = AuditLog(system="answer-bot", risk_tier="limited", path=str(chain))
    client, closed = runaway_client()
    received, raised = [], 0
    try:
        with budget(tokens=20, on_exceed="break"):
            stream = client.chat.completions.create(model=MODEL, messages=[], stream=True)
            try:
                for chunk in stream:
                    received.append(chunk)
            except BudgetExceeded as exc:
                raised += 1
                reason = str(exc)
    finally:
        audit.detach()

    events = [e for e in audit.entries if e.type == "budget_event"]
    broken = [e for e in events if e.payload["action"] == "broken"]
    ok, detail = verify(str(chain))

    print(f"stream       : cut after {len(received)} of {CHUNKS} chunks (partial text kept)")
    print(f"provider     : underlying stream closed = {closed['v']}")
    print(f"raised       : {raised}x BudgetExceeded - {reason.splitlines()[0]}")
    cap = broken[-1].payload["cap_tokens"]
    print(f"chained      : budget_event(action='broken'), cap {cap} tokens")
    print(f"verify()     : {ok} - {detail}")

    assert raised == 1, "exactly one BudgetExceeded should surface on the cut"
    assert 0 < len(received) < CHUNKS, "the runaway stream was not cut mid-flight"
    assert closed["v"] is True, "the provider stream was left open after the cut"
    assert broken, "the cut was not chained as a budget_event(action='broken')"
    assert ok is True, "the break audit chain failed verify()"


if __name__ == "__main__":
    main()
