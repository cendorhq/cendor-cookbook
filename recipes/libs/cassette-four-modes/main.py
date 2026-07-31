"""cassette-four-modes — record, replay, rerecord, auto: four modes, four environments.

The modes are one keyword apart and mean very different things. Pick by *where the code is running*:

  record     run live, write the tape. What you do once, deliberately, with a key.
  replay     never touch the provider; an unrecorded call RAISES. What CI runs — strict on purpose,
             so drift surfaces as a red test instead of a silent live call.
  auto       replay if the tape exists, else record. Good for a laptop; **wrong for CI**, because a
             missing file silently becomes a live call (and a missing key becomes a crash).
  rerecord   run live and report `drift()` — what changed since the tape — WITHOUT overwriting it.
             The refresh check you run on a schedule.

And the fifth choice: **no cassette scope at all.** Nothing is intercepted; every call is live. That
is the default, and it is the right answer in production.

This recipe drives all four against a fake provider whose answer *changes* between the recording and
the rerecord, so `drift()` has something real to report.

Offline: a fake OpenAI-shaped client and a temp directory. No key, nothing committed.

  uv run python recipes/libs/cassette-four-modes/main.py
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor import cassette
from cendor.cassette import CassetteError
from cendor.core import instrument

MODEL = "gpt-4o"
ASK = [{"role": "user", "content": "what is the refund window?"}]
OTHER = [{"role": "user", "content": "who approved order 8812?"}]


class Provider:
    """A fake provider whose answer changes, and which counts how often it is really reached."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.answer))],
            usage=SimpleNamespace(prompt_tokens=24, completion_tokens=9),
            model=MODEL,
        )


def client(provider: Provider):
    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=provider)))


def main() -> None:
    tape = Path(tempfile.mkdtemp(prefix="cendor-recipe-")) / "policy.json"

    # ---- record ---------------------------------------------------------------------------------
    p1 = Provider("30 days from delivery.")
    with cassette.using(str(tape), mode="record"):
        client(p1).chat.completions.create(model=MODEL, messages=ASK)
    print(f"record   : provider {p1.calls}x -> tape written ({tape.stat().st_size} bytes)")

    # ---- replay: free, and STRICT ----------------------------------------------------------------
    p2 = Provider("never reached")
    with cassette.using(str(tape), mode="replay"):
        out = client(p2).chat.completions.create(model=MODEL, messages=ASK)
    print(f"replay   : provider {p2.calls}x -> {out.choices[0].message.content!r}")

    p3 = Provider("never reached")
    unrecorded = None
    try:
        with cassette.using(str(tape), mode="replay"):
            client(p3).chat.completions.create(model=MODEL, messages=OTHER)
    except CassetteError as exc:
        unrecorded = str(exc).splitlines()[0]
    print(f"           an UNRECORDED call raises: {unrecorded[:78]}")

    # ---- auto: replays here, but would have recorded if the file were missing -------------------
    p4 = Provider("never reached")
    with cassette.using(str(tape), mode="auto"):
        client(p4).chat.completions.create(model=MODEL, messages=ASK)
    missing = tape.with_name("not-there.json")
    p5 = Provider("recorded on first use")
    with cassette.using(str(missing), mode="auto"):
        client(p5).chat.completions.create(model=MODEL, messages=ASK)
    print(
        f"auto     : existing tape -> provider {p4.calls}x (replayed); "
        f"missing tape -> provider {p5.calls}x (recorded)"
    )

    # ---- rerecord: run live, report what changed, leave the tape alone ---------------------------
    before = tape.read_bytes()
    p6 = Provider("14 days from delivery.")  # the policy changed upstream
    with cassette.using(str(tape), mode="rerecord"):
        client(p6).chat.completions.create(model=MODEL, messages=ASK)
    changes = cassette.drift()
    print(
        f"rerecord : provider {p6.calls}x -> drift() reports {len(changes)} divergence(s); "
        f"tape unchanged on disk: {tape.read_bytes() == before}"
    )

    # ---- no scope at all -------------------------------------------------------------------------
    p7 = Provider("live")
    client(p7).chat.completions.create(model=MODEL, messages=ASK)
    print(f"no scope : provider {p7.calls}x - nothing is intercepted; this is production")

    assert p1.calls == 1 and p2.calls == 0 and p4.calls == 0, "replay must not reach the provider"
    assert unrecorded is not None, "replay must RAISE on an unrecorded call, not fall through"
    assert p5.calls == 1, "auto should have recorded against a missing tape"
    assert p6.calls == 1 and changes, "rerecord must run live and report the divergence"
    assert tape.read_bytes() == before, "rerecord overwrote the tape"


if __name__ == "__main__":
    main()
