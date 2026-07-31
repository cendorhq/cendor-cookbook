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

Prove it against a real socket (the claim "it closes the provider stream" cannot be proven by a
fake, whose `close()` we own — see `runaway_client`):

  LIVE=1 OPENAI_API_KEY=sk-... uv run python recipes/combos/break-midstream-audited/main.py
  # asserts httpx `response.is_closed` instead of the fake's flag. Costs a fraction of a cent:
  # the cut lands ~24 chunks in, and you are billed to the cut plus about one round trip.
"""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor.acttrace import AuditLog, verify
from cendor.core import instrument
from cendor.tokenguard import BudgetExceeded, budget, reset

MODEL = "gpt-4o"
CHUNKS = 60
CAP_TOKENS = 20
LIVE = bool(os.environ.get("LIVE"))
# Live mode asks a real model for something long enough to still be talking when the cap lands.
LIVE_MODEL = os.environ.get("LIVE_MODEL", "gpt-4o-mini")
LIVE_PROMPT = "Count slowly from 1 to 300, one number per line."
# ⚠️ The cap counts the INPUT too, and the fake's request is `messages=[]` — zero input tokens — so
# offline all 20 tokens are available to the output. A real request cannot be empty: this prompt is
# ~12 input tokens, which left ~0 for the output and cut the live stream at chunk **zero** (measured
# 2026-08-01, first run of the new switch). The live cap therefore has to cover the prompt plus
# enough output to actually watch a cut happen; 40 lands it ~24 chunks in.
LIVE_CAP_TOKENS = int(os.environ.get("LIVE_CAP_TOKENS", "40"))


def runaway_client():
    """A provider stream that will not stop. `closed['v']` flips when core closes it on the cut —
    which is what proves the break reached the socket, not just the consumer's loop.

    ⚠️ **`closed['v']` is this fake's own flag, so offline it proves the cut reached *this object*
    and nothing more.** A real provider stream has no `close()` we own — it has an httpx response.
    That gap is why `LIVE=1` exists: it swaps in `instrument(OpenAI())` and reports
    `response.is_closed` instead, which is the claim people actually care about. Verified
    2026-08-01 against live OpenAI: `is_closed=True`, and re-iterating raises `httpx.ReadError`
    (one already-buffered chunk can still surface after the cut — the socket is shut, the buffer
    is not rewound).
    """
    closed = {"v": False}
    if LIVE:
        from openai import OpenAI

        return instrument(OpenAI()), closed

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


def stream_really_closed(stream, closed: dict) -> bool:
    """Did the provider stream actually shut, not just the consumer's loop end?

    Offline that is the fake's flag. Live it is the underlying httpx response, which is the only
    provider-agnostic evidence available — and the reason this recipe grew a `LIVE=1` switch.
    """
    if not LIVE:
        return bool(closed["v"])
    resp = getattr(stream, "response", None)
    return bool(getattr(resp, "is_closed", False))


def main() -> None:
    reset()
    tmp = Path(tempfile.mkdtemp(prefix="cendor-recipe-"))
    chain = tmp / "stream-break.jsonl"

    audit = AuditLog(system="answer-bot", risk_tier="limited", path=str(chain))
    client, closed = runaway_client()
    # `reason` has to be initialised, not just assigned in the except branch below. The fake stream
    # always trips the 20-token cap, so offline the branch always runs — but point this at any
    # client whose answer is short enough NOT to trip it and the print below dies with
    # `UnboundLocalError` instead of telling you the breaker never fired. (Measured 2026-07-31: a
    # real gpt-4o reply is far cheaper than this fake's 60 chunks, so that is the live path.)
    received, raised, reason = [], 0, ""
    # ⚠️ `messages=[]` is legal for the fake and a hard 400 on any real provider ("[] is too short").
    # Live mode has to send something, and something long — the cut is only observable while the
    # model is still talking.
    messages = [{"role": "user", "content": LIVE_PROMPT}] if LIVE else []
    try:
        with budget(tokens=LIVE_CAP_TOKENS if LIVE else CAP_TOKENS, on_exceed="break"):
            stream = client.chat.completions.create(
                model=LIVE_MODEL if LIVE else MODEL, messages=messages, stream=True
            )
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
    really_closed = stream_really_closed(stream, closed)
    evidence = "httpx response.is_closed" if LIVE else "the fake's close() flag"

    kept = f"cut after {len(received)} chunks" + ("" if LIVE else f" of {CHUNKS}")
    print(f"stream       : {kept} (partial text kept)")
    print(f"provider     : underlying stream closed = {really_closed}   [{evidence}]")
    first_line = reason.splitlines()[0] if reason else "(the cap was never crossed)"
    print(f"raised       : {raised}x BudgetExceeded - {first_line}")
    cap = broken[-1].payload["cap_tokens"]
    print(f"chained      : budget_event(action='broken'), cap {cap} tokens")
    print(f"verify()     : {ok} - {detail}")

    assert raised == 1, "exactly one BudgetExceeded should surface on the cut"
    assert received, "the stream produced nothing, so nothing was cut mid-flight"
    if not LIVE:
        assert len(received) < CHUNKS, "the runaway stream was not cut mid-flight"
    assert really_closed is True, "the provider stream was left open after the cut"
    assert broken, "the cut was not chained as a budget_event(action='broken')"
    assert ok is True, "the break audit chain failed verify()"


if __name__ == "__main__":
    main()
