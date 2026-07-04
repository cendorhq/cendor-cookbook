"""Offline tests for the chat-playground app — the plumbing, not the Gradio UI.

Drives the real event handlers (no server, no browser) to prove the money shots hold with no key
and no network: the 6th demo turn is blocked pre-flight, the receipt peels history, a pasted blob
is compressed reversibly, a recorded session replays with 0 calls, and the evidence pack verifies
then fails on a one-byte tamper. Skips cleanly if the `apps` group isn't installed.

    uv run --group apps pytest recipes/apps/chat-playground/test_app.py
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

pytest.importorskip("gradio")  # the apps group isn't installed on the base env

import app  # noqa: E402  (import after the skip guard)
from cendor.core import bus  # noqa: E402
from cendor.tokenguard import reset as tokenguard_reset  # noqa: E402

# The scripted demo conversation that deterministically spends ~$0.096/turn.
PROMPTS = [
    "hello",
    "I was double charged on order 8823",
    "can you confirm the refund?",
    "what about my late shipment?",
    "cancel my subscription please",
    "thanks",
]


@pytest.fixture(autouse=True)
def _isolate():
    """Give each test a clean process-global bus + tokenguard, and detach every session's audit
    log so one test's calls can't leak onto another's chain."""
    _detach_all()
    bus._reset()
    tokenguard_reset()
    yield
    _detach_all()


def _detach_all():
    for session in list(app.SESSIONS.values()):
        session.audit.detach()
    app.SESSIONS.clear()


def _submit(prompt, sid, cap=0.50, mode="block", run_mode="Demo"):
    out = app.on_submit(prompt, sid, run_mode, "OpenAI", "", cap, mode)
    return out, out[8]  # (outputs, session id)


def _blocked(session) -> bool:
    return bool(session.transcript) and session.transcript[-1]["content"].startswith("⛔")


def test_theme_and_build():
    from theme import CendorTheme

    assert CendorTheme() is not None
    assert app.build_demo() is not None


def test_demo_blocks_on_sixth_turn():
    sid = None
    spends = []
    for i, prompt in enumerate(PROMPTS, 1):
        _, sid = _submit(prompt, sid)
        session = app.SESSIONS[sid]
        spends.append(float(session.spent_usd))
        if i < 6:
            assert not _blocked(session), f"turn {i} should have run"
        else:
            assert _blocked(session), "the 6th turn must be blocked pre-flight"
    # The blocked turn spends nothing extra; five turns of real spend stay under the $0.50 cap.
    assert spends[-1] == spends[-2]
    assert spends[-2] <= 0.50


def test_receipt_peels_history():
    sid = None
    peeled = False
    for prompt in PROMPTS[:5]:  # stop before the block
        out, sid = _submit(prompt, sid)
        for row in out[3]:  # receipt rows: [block, action, tokens]
            if row[0] == "history" and row[1] in ("truncated", "dropped"):
                peeled = True
    assert peeled, "history should peel its oldest turns as the chat grows"


def test_no_network_in_demo_mode():
    app.tokens.count("warm the tokenizer cache", "gpt-4o")  # pre-warm before blocking sockets
    original = socket.socket

    def forbidden(*args, **kwargs):
        raise AssertionError("demo mode attempted a network connection")

    socket.socket = forbidden
    try:
        _, sid = _submit("hello", None)
    finally:
        socket.socket = original
    assert not _blocked(app.SESSIONS[sid])
    assert len(app.SESSIONS[sid].transcript[-1]["content"]) > 0


def test_compression_is_reversible():
    blob = '{"event":"purchase","user":"u42","amount":12.50,"ts":"2026-07-04"} ' * 60
    _, sid = _submit(blob, None)
    comp = app.SESSIONS[sid].last_compression
    assert comp is not None
    assert comp["after"] < comp["before"]
    assert comp["restored_ok"] is True
    assert "byte-for-byte identical: True" in app.on_expand(sid)


def test_cassette_record_download_replay_roundtrip():
    sid = None
    _, sid = _submit("warmup", None, cap=5.0)
    app.on_record_toggle(True, sid)
    for prompt in ["hello", "I was double charged", "thanks"]:
        _, sid = _submit(prompt, sid, cap=5.0)
    assert len(app.SESSIONS[sid].recorded) == 3

    cass, status = app.on_download(sid)
    assert cass and "3 entries" in status
    payload = json.loads(Path(cass).read_text(encoding="utf-8"))
    assert payload["version"] == 2 and len(payload["entries"]) == 3

    _, replay_status, _, _ = app.on_replay(sid)
    assert "0 real calls" in replay_status and "$0" in replay_status

    # Upload the same cassette back and replay it.
    _, up_status, _, _ = app.on_upload(cass, sid)
    assert "0 real calls" in up_status


def test_cassette_upload_rejects_unknown_format(tmp_path):
    _, sid = _submit("hi", None)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"version": 99, "entries": []}), encoding="utf-8")
    _, status, _, _ = app.on_upload(str(bad), sid)
    assert "unsupported cassette version 99" in status

    notjson = tmp_path / "notjson.json"
    notjson.write_text("{not valid", encoding="utf-8")
    _, status, _, _ = app.on_upload(str(notjson), sid)
    assert "not valid JSON" in status


def test_audit_export_verify_and_tamper():
    sid = None
    for prompt in ["hello", "I was double charged"]:
        _, sid = _submit(prompt, sid)
    _, export_status = app.on_export(sid)
    assert "entries" in export_status

    assert "verify: True" in app.on_verify(sid)

    tampered = app.on_tamper(sid)
    assert "verify: False" in tampered
    assert "seq" in tampered  # names the failing sequence number


def test_downgrade_mode_reroutes_under_cap():
    sid = None
    rerouted = None
    for i in range(1, 8):
        _, sid = _submit(f"refund question {i}", sid, mode="downgrade")
        session = app.SESSIONS[sid]
        if session.events and session.events[-1]["rerouted"]:
            rerouted = session.events[-1]
            break
    assert rerouted is not None, "downgrade mode should reroute a near-cap call"
    assert rerouted["model"] == "gpt-4o-mini"
    assert float(app.SESSIONS[sid].spent_usd) <= 0.50
