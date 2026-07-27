"""pytest for the governed M365 custom engine agent — the same walkthrough, asserted.

Runs offline: no key, no network. See `main.py` for the runnable narration and `agent.py` for the
wrap map itself.

    uv run --group agents-m365 pytest recipes/agents/m365-custom-engine-py
"""

from __future__ import annotations

import asyncio
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


def test_the_whole_agent_replays_offline():
    with tempfile.TemporaryDirectory() as d:
        r = asyncio.run(offline_replay(Path(d)))

    assert r["recorded"] == r["replayed"], (r["recorded"], r["replayed"])
    assert all(t.strip() for t in r["replayed"])
    assert r["cassette_bytes"] > 0
