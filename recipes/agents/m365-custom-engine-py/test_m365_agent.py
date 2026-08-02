"""pytest for the governed M365 custom engine agent — the same walkthrough, asserted.

Runs offline: no key, no network. See `main.py` for the runnable narration and `agent.py` for the
wrap map itself.

    uv run --group agents-m365 pytest recipes/agents/m365-custom-engine-py
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from decimal import Decimal
from pathlib import Path

import agent as agent_mod
from main import offline_replay, walkthrough


def test_governed_turn_is_priced_and_carries_the_envelope():
    with tempfile.TemporaryDirectory() as d:
        report = asyncio.run(walkthrough(Path(d)))

    g = report["governed"]
    assert g["governance"] == "ok"
    assert g["input_tokens"] > 0 and g["output_tokens"] > 0  # exact usage, off the response
    assert Decimal(g["cost_usd"]) > 0  # a Decimal, never a float
    assert g["trace_id"], "turn_scope()'s trace() is what puts a trace_id on the envelope"
    assert g["model"] == agent_mod.MODEL
    assert Decimal(g["session_spent_usd"]) == Decimal(g["cost_usd"])  # the ledger persisted
    ok, detail = report["audit"]
    assert ok, detail  # the hash chain verifies


def test_the_gates_and_the_fuses_fire():
    with tempfile.TemporaryDirectory() as d:
        report = asyncio.run(walkthrough(Path(d)))

    # the input gate: a block reaches the channel as a refusal, not as an error
    assert report["blocked"]["governance"] == "input_blocked"
    assert "hit an error" not in report["blocked"]["text"].lower()
    assert any("prompt_injection" in d for d in report["blocked"]["decisions"])

    # redaction is a decision on an otherwise-normal turn
    assert any("email_redact" in d for d in report["redacted"]["decisions"])

    # (E) the mid-stream break, and the channel still got a clean close
    assert report["streamed"]["governance"] == "broke_on_budget"
    assert report["stream_activities"] > 0, "the channel keeps what it was already sent"

    # (C) the session cap refuses with zero spend — no model call, so no cost on the envelope
    assert report["capped"]["governance"] == "session_cap_reached"
    assert "cost_usd" not in report["capped"]
    assert "reached its cap" not in report["capped"]["text"]

    # (A) the pre-flight refusal is a *different* sentence, and equally zero-spend. It must never
    # claim the cap was reached — the estimate over-reserves, so there may still be headroom.
    assert report["preflight"]["governance"] == "preflight_refused"
    assert "cost_usd" not in report["preflight"]
    assert "reached" not in report["preflight"]["text"]


def test_the_governance_card_says_what_happened():
    """The card is the only view of the libraries a Playground/Teams user actually sees.

    ⚠️ These assert *content*, not shape. A card that renders and says nothing is the failure mode
    worth guarding: the whole reason it exists is that `channelData` was invisible in the chat pane.
    """
    with tempfile.TemporaryDirectory() as d:
        report = asyncio.run(walkthrough(Path(d)))

    card = report["card_ok"]
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.5", "1.5 keeps Playground + Teams + WebChat all rendering it"

    text = json.dumps(card)
    # every library that acted on the turn is named ON the card, beside what it did
    for lib in ("core", "tokenguard", "contextkit", "guardrails", "acttrace"):
        assert lib in text, f"{lib} did work on this turn and the card does not say so"
    # …and the numbers are the SAME TURN's envelope values, not a second computation of them.
    # ⚠️ Compare against `card_ok_env` (that reply's own envelope), never against another turn's:
    # the deterministic fake makes two turns' costs equal, so a cross-turn assertion passes for the
    # wrong reason. The trace id is what catches it — it is unique per turn.
    env = report["card_ok_env"]
    assert env["cost_usd"] in text, "the card's money must be the turn's real Decimal cost"
    assert env["trace_id"] in text, "the card must describe THIS turn, not a re-run of it"
    assert str(env["input_tokens"]) in text and str(env["output_tokens"]) in text
    # provenance: a dollar figure with no source is what a cost review rejects
    assert "rate " in text and ("as of" in text or "outranks every table" in text)

    # a refusal must EXPLAIN itself. "the agent hit an error" is the failure this replaces.
    refusal = json.dumps(report["preflight_card"])
    assert "refused before the call" in refusal
    assert "Zero provider calls, $0 spent" in refusal
    # ⚠️ and it must not claim the CAP was reached — the estimate over-reserves, so it can refuse
    # while the ledger still shows headroom. Two different sentences, on purpose.
    # ⚠️ Match the claim, not the word: a bare `"reached" not in refusal` fails on the card's own
    # honest line "nothing reached the provider". A substring is not a claim.
    for lie in ("cap reached", "reached your cap", "reached its cap"):
        assert lie not in refusal.lower(), f"a pre-flight refusal must not say {lie!r}"
    # …and the NEGATIVE CONTROL: the session-cap refusal is a genuinely different event, and it
    # does say so. Without this line the assertion above would still pass on a card that had
    # simply stopped explaining anything.
    capped = json.dumps(report["capped_card"]).lower()
    assert "session cap reached" in capped
    assert "no model call was made" in capped

    # off by default, and the toggle really turns it off: governance never depends on styling
    assert report["card_off"] == {}, "/cards off must stop attaching the card"


def test_the_whole_agent_replays_offline():
    with tempfile.TemporaryDirectory() as d:
        r = asyncio.run(offline_replay(Path(d)))

    assert r["recorded"] == r["replayed"], (r["recorded"], r["replayed"])
    assert all(t.strip() for t in r["replayed"])
    assert r["cassette_bytes"] > 0
