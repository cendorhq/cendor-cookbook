"""cassette quickstart — record an agent call once, replay it forever (offline, free).

Every test run that hits a real model costs money and flakes. cassette records the exchange
the first time, then replays it: same assertion, zero calls, no network. This file is BOTH a
runnable script and a pytest module.

Run as a script:  uv run python recipes/quickstarts/cassette/main.py
Run as a test:     uv run pytest recipes/quickstarts/cassette/main.py
"""

import tempfile
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

from cendor import cassette
from cendor.core import instrument

_calls = {"n": 0}  # counts real (fake-client) calls, so we can prove replay makes none


def make_client():
    class Completions:
        def create(self, **kwargs):
            _calls["n"] += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Refund issued."))],
                usage=SimpleNamespace(prompt_tokens=19, completion_tokens=4),
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def _run_agent() -> str:
    client = make_client()
    resp = client.chat.completions.create(
        model="gpt-4o", messages=[{"role": "user", "content": "I was double charged"}]
    )
    return resp.choices[0].message.content


def _record_then_replay(path: str) -> dict:
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


def test_records_then_replays():
    with tempfile.TemporaryDirectory() as d:
        r = _record_then_replay(str(Path(d) / "run.json"))
    assert r["record"]["n"] == 1  # first run records with exactly one real call
    assert r["replay"]["n"] == 0  # replay makes zero calls — offline
    assert cassette.semantic_match(r["replay"]["out"], "a refund was issued")


if __name__ == "__main__":
    main()
