"""One chat session: its audit chain, its history, its recorder, its gate.

Held in a module-level registry rather than in `gr.State`, because a session owns an `AuditLog`
with an open file handle and a live bus subscription — `gr.State` carries only the id string.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from cendor.acttrace import AuditLog, Policy
from config import SIGNING_KEY

# acttrace detection policy presets. Each maps the ~20 detected categories (secret · credential
# · financial · gov_id · pii · special_category) to an action — allow · flag · redact · block:
#   default  secrets & email redact, everything else flag — never blocks
#   gdpr     personal data redacted across the board
#   pci      payment/financial data blocked, secrets & PII redacted
#   strict   high-severity groups blocked, the rest redacted
# The app ENFORCES (block pre-flight / scrub-before-send); acttrace RECORDS a tamper-evident flag.
POLICY_PRESETS = {
    "default": Policy.default,
    "gdpr": Policy.gdpr,
    "pci": Policy.pci,
    "strict": Policy.strict,
}
POLICY_NAMES = list(POLICY_PRESETS)

# The Cendor bus, tokenguard records and acttrace subscriptions are process-global, so this app is
# built for one active session at a time (one local run / one Codespace).
SESSIONS: dict[str, Session] = {}


@dataclass
class Session:
    sid: str
    tmp: str
    audit: AuditLog
    spent_usd: Decimal = Decimal("0")
    history: list[dict] = field(default_factory=list)  # real turns packed into context
    transcript: list[dict] = field(default_factory=list)  # what the chatbot shows
    events: list[dict] = field(default_factory=list)  # bus feed snapshots
    record_on: bool = False
    recorded: list[dict] = field(default_factory=list)  # captured turns while recording
    last_compression: dict | None = None
    evidence_path: str | None = None
    turn: int = 0
    policy_name: str = "default"  # acttrace detection preset (default | gdpr | pci | strict)
    policy: Any = field(default_factory=lambda: Policy.default())
    gate_on: bool = True  # the cendor.guardrails deterministic gate (see engine.gate_scope)
    gate_decisions: list[dict] = field(default_factory=list)  # this session's guardrail feed
    run_mode: str = "Demo"  # remembered so a reset re-renders the right cap


def new_session() -> Session:
    sid = uuid.uuid4().hex
    tmp = tempfile.mkdtemp(prefix=f"cendor_pg_{sid[:8]}_")
    audit = AuditLog(
        system="chat_playground",
        risk_tier="limited",
        path=os.path.join(tmp, "audit.jsonl"),
        signing_key=SIGNING_KEY,
    )
    session = Session(sid=sid, tmp=tmp, audit=audit)
    SESSIONS[sid] = session
    return session


def get(sid: str | None) -> Session:
    """The session for this browser tab, or a fresh one. Never returns None — every handler can
    render a panel even on the very first event, before `gr.State` holds anything."""
    if sid and sid in SESSIONS:
        return SESSIONS[sid]
    return new_session()


def set_policy(session: Session, name: str) -> Session:
    """Resolve the acttrace preset by name, falling back to `default` on anything unrecognised."""
    session.policy_name = name if name in POLICY_PRESETS else "default"
    session.policy = POLICY_PRESETS[session.policy_name]()
    return session


def drop(sid: str | None) -> None:
    """Close a session's chain. Two live `AuditLog` writers on one path is an error, so the old
    session has to be detached before a new one opens — that is what this exists for."""
    if sid and sid in SESSIONS:
        SESSIONS.pop(sid).audit.detach()
