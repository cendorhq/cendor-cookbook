"""pytest-cassette — an agent test suite that runs offline, on a plane, for free.

A real mini-suite for a fake agent that makes one tool call and one model call. Each test has its
own cassette (xdist-safe: one file per test), so `pytest -n auto` replays them in parallel with
zero API calls. `mode="replay"` is strict — an unrecorded call raises, so drift can't pass
silently.

Run the suite:
  uv run pytest recipes/testing/pytest-cassette
  uv run pytest recipes/testing/pytest-cassette -n auto     # parallel, still 0 calls

Re-record the committed cassettes:
  RERECORD=1 uv run pytest recipes/testing/pytest-cassette

⚠️ This recipe's client is a **fake** (`make_agent` below), so `RERECORD=1` re-records the fake
and needs **no key and no network** — it is how you refresh the committed fixtures after changing
the fake or the agent's call shape, not how you capture real traffic. Point `make_agent` at a real
client if you want that; the cassette mechanics are identical either way.
"""

import os
from types import SimpleNamespace

import pytest
from cendor import cassette
from cendor.core import bus, instrument, instrument_tool

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
MODE = "record" if os.environ.get("RERECORD") else "replay"
_calls = {"llm": 0, "tool": 0}


@pytest.fixture(autouse=True)
def _clean_bus():
    bus._reset()
    _calls.update(llm=0, tool=0)
    yield
    bus._reset()


@instrument_tool("lookup_account")
def lookup_account(user_id: str) -> dict:
    _calls["tool"] += 1
    return {"user_id": user_id, "tier": "gold"}


def make_agent():
    class Completions:
        def create(self, **kwargs):
            _calls["llm"] += 1
            msg = SimpleNamespace(content="Your refund was approved.")
            return SimpleNamespace(
                choices=[SimpleNamespace(message=msg)],
                usage=SimpleNamespace(prompt_tokens=22, completion_tokens=7),
            )

    client = instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))

    def run(query: str) -> str:
        account = lookup_account("alice")  # one tool call...
        resp = client.chat.completions.create(  # ...then one model call
            model="gpt-4o",
            messages=[
                {"role": "system", "content": str(account)},
                {"role": "user", "content": query},
            ],
        )
        return resp.choices[0].message.content

    return run


def _fixture(name: str) -> str:
    return os.path.join(FIXTURES, f"{name}.json")  # one cassette per test — xdist-safe


def test_triage_offers_refund():
    run = make_agent()
    out = cassette.use(_fixture("triage"), mode=MODE)(lambda: run("I was double charged"))()
    assert cassette.semantic_match(out, "a refund was approved")
    if MODE == "replay":
        assert _calls["llm"] == 0  # replayed — no real model call


def test_tool_call_is_replayed():
    run = make_agent()
    cassette.use(_fixture("tool"), mode=MODE)(lambda: run("look up my account"))()
    if MODE == "replay":
        assert _calls["llm"] == 0 and _calls["tool"] == 0  # both model + tool replayed offline


def test_replay_mode_is_strict(tmp_path):
    run = make_agent()
    path = str(tmp_path / "strict.json")
    cassette.use(path, mode="record")(lambda: run("recorded question"))()
    # An unrecorded call under mode="replay" must raise — drift can't slip through.
    with pytest.raises(cassette.CassetteError):
        cassette.use(path, mode="replay")(lambda: run("a completely different question"))()
