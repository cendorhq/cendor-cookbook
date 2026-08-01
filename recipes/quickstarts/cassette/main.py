"""cassette quickstart — record an agent call once, replay it forever (offline, free).

Every test run that hits a real model costs money and flakes. cassette records the exchange
the first time, then replays it: same assertion, zero calls, no network. This file is BOTH a
runnable script and a pytest module.

Run as a script:  uv run python recipes/quickstarts/cassette/main.py
Run as a test:     uv run pytest recipes/quickstarts/cassette/main.py

Against a real provider (records once with your key, then replays offline forever):
  LIVE=1 OPENAI_API_KEY=sk-... uv run --group apps python recipes/quickstarts/cassette/main.py

⚠️ The live run is the one that makes the point. Offline, "the replay made 0 calls" is asserted
against a fake we own; live, run 1 genuinely bills you and run 2 genuinely does not — and the
second run's latency drops to the disk read. That gap is the whole reason cassette exists.
"""

import os
import tempfile
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

from cendor import cassette
from cendor.core import instrument

LIVE = bool(os.environ.get("LIVE"))
MODEL = os.environ.get("LIVE_MODEL", "gpt-4o-mini") if LIVE else "gpt-4o"

# Counts calls that reached the client. A replay recipe that only compared OUTPUT would pass just
# as happily if the "replay" quietly re-called the provider — the call count is the actual claim.
#
# ⚠️ Under LIVE=1 this counter wraps the REAL client, so it still counts correctly. That is worth
# saying because the obvious shortcut — counting on the bus instead — would be wrong: a replayed
# call still emits an LLMCall (flagged `replayed`), so a bus count reads 1 for a run that touched
# no network at all.
_calls = {"n": 0}


def make_client():
    """The fake, or a real OpenAI client. Everything below is identical for both."""
    if LIVE:
        from openai import OpenAI  # lazy: the offline path needs no provider SDK

        # ⚠️ `instrument(_counted(...))`, NOT `_counted(instrument(...))`. The counter has to sit
        # exactly where the offline fake sits — BELOW the interceptor chain — because a replayed
        # call is served by cassette's interceptor and never reaches the client at all. Wrapped the
        # other way round the counter reads 1 on replay, and the recipe's central claim ("0 calls")
        # fails against a replay that is working perfectly. Measured on the first live run.
        return instrument(_counted(OpenAI()))

    class Completions:
        def create(self, **kwargs):
            _calls["n"] += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Refund issued."))],
                usage=SimpleNamespace(prompt_tokens=19, completion_tokens=4),
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def _counted(client):
    """Count calls that reach the RAW client, then hand it to `instrument()`.

    This is the same vantage point the offline fake occupies, which is what makes the two paths
    comparable: whatever the interceptor chain refuses or serves from disk never gets here.
    """
    inner = client.chat.completions.create

    def create(**kwargs):
        _calls["n"] += 1
        return inner(**kwargs)

    client.chat.completions.create = create
    return client


def _run_agent() -> str:
    client = make_client()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "I was double charged"}],
        **({"max_tokens": 24} if LIVE else {}),
    )
    return resp.choices[0].message.content


def _record_then_replay(path: str) -> dict:
    """Record on the first call, replay on the second — `mode="auto"` decides by whether the file
    is there. That is what makes a cassette usable in CI without a flag: the first developer run
    writes it, every run afterwards (including the ones with no key) reads it."""
    _calls["n"] = 0
    t0 = perf_counter()
    out1 = cassette.use(path, mode="auto")(_run_agent)()  # no file yet -> records
    rec = {"out": out1, "n": _calls["n"], "ms": (perf_counter() - t0) * 1000}

    _calls["n"] = 0
    t0 = perf_counter()
    out2 = cassette.use(path, mode="auto")(_run_agent)()  # file exists -> replays
    rep = {"out": out2, "n": _calls["n"], "ms": (perf_counter() - t0) * 1000}
    return {"record": rec, "replay": rep}


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        r = _record_then_replay(str(Path(d) / "run.json"))
    rec, rep = r["record"], r["replay"]
    print(f"run 1: recorded ({rec['n']} call, {rec['ms']:.1f} ms)")
    print(f"run 2: replayed ({rep['n']} calls, offline, {rep['ms']:.1f} ms)")
    print(f"same assertion green: {rec['out'] == rep['out']!r} == {rec['out']!r}")
    if LIVE:
        print(f"(LIVE: run 1 hit {MODEL} and billed you; run 2 read the file and did not)")

    assert rec["n"] == 1, "the first run should have made exactly one real call"
    assert rep["n"] == 0, "the replay reached the client — it is not offline"
    assert rec["out"] == rep["out"], "the replayed answer differs from the recorded one"


def test_records_then_replays():
    """The same three claims as `main()`, as a pytest so CI enforces them."""
    with tempfile.TemporaryDirectory() as d:
        r = _record_then_replay(str(Path(d) / "run.json"))
    assert r["record"]["n"] == 1  # first run records with exactly one real call
    assert r["replay"]["n"] == 0  # replay makes zero calls — offline
    # `semantic_match` rather than `==`: a replayed reply is byte-identical, but the same assertion
    # written this way keeps working when the fixture is later re-recorded against a live model,
    # whose wording will differ. (And it will differ — see libs/cassette-semantic-drift.)
    assert cassette.semantic_match(r["replay"]["out"], "a refund was issued")


if __name__ == "__main__":
    main()
