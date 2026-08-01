"""The seven panels, as HTML. One renderer per library; no Gradio import, so they are unit-testable.

House rule for this file: **every number rendered here comes from a live object** — a bus event, a
`prices` cost, a `contextkit` report, `len(audit.entries)`. There are no literals standing in for
measurements, not even in the empty states. (The old build hard-coded `1 hash-chain entries` and
`$0.0000 / $0.50` into its empty panels, which meant two of the first things a visitor read were
printed strings that happened to be true.)
"""

from __future__ import annotations

from html import escape

from config import COMPRESS_THRESHOLD, sizing
from engine import GATE_NAMES
from session import Session

# The seven library hues. ⚠️ These are per-library accents on separate panels — they are never
# combined into one gradient (org brand rule: no rainbow).
HUE = {
    "core": "#94A3BB",
    "tokenguard": "#8B5CF6",
    "contextkit": "#3B82F6",
    "squeeze": "#22C55E",
    "guardrails": "#F59E0B",
    "cassette": "#14B8A6",
    "acttrace": "#F43F5E",
}

# acttrace policy actions → the receipt's cd-act-* colour classes (red · green · amber · gray).
_ACT_CLASS = {"block": "dropped", "redact": "compressed", "flag": "truncated", "allow": "kept"}


def _empty(msg: str) -> str:
    return f"<div class='cd-empty'>{msg}</div>"


# ── tokenguard ────────────────────────────────────────────────────────────────────────────────


def budget_panel(session: Session, cap: float, result: dict | None) -> str:
    """The spend bar: a filled track with the cap marked. `spent` is tokenguard's own figure."""
    spent = float(session.spent_usd)
    cap = max(float(cap), 1e-9)
    pct = min(100.0, 100.0 * spent / cap)
    blocked = bool(result and result.get("blocked"))
    reroute = result.get("reroute") if result else None
    fill = "#F43F5E" if blocked else HUE["tokenguard"]
    banner = ""
    if blocked:
        banner = (
            "<div class='cd-banner cd-block'>⛔ <b>BudgetExceeded</b> — blocked pre-flight, "
            "$0 spent. The over-budget call never ran.</div>"
        )
    elif reroute:
        banner = (
            "<div class='cd-banner cd-reroute'>↘ <b>Downgraded</b> — "
            f"{escape(reroute[0])} → {escape(reroute[1])} to stay under cap ($0 extra).</div>"
        )
    left = max(0.0, cap - spent)
    return (
        f"<div class='cd-barmeta'><span>spent <b>${spent:.4f}</b> / ${cap:.2f}</span>"
        f"<span>${left:.4f} left · {pct:.0f}%</span></div>"
        f"<div class='cd-track'><div class='cd-fill' style='width:{pct:.1f}%;"
        f"--fh:{fill}'></div><div class='cd-capmark'><span>cap ${cap:.2f}</span></div></div>"
        f"{banner}"
    )


# ── contextkit ────────────────────────────────────────────────────────────────────────────────


def receipt_panel(result: dict | None, run_mode: str = "Demo") -> str:
    """The assembly receipt as a mono table: block · action · tokens, plus the active sizing."""
    budget_tokens, _, _ = sizing(run_mode)
    head_note = (
        f"<div class='cd-sub'>{escape(run_mode.lower())} sizing · budget "
        f"<b>{budget_tokens:,}</b> tok</div>"
    )
    if not result or "report" not in result:
        return head_note + _empty("Send a message — the packed context receipt lands here.")
    report = result["report"]
    rows = "".join(
        f"<div class='cd-row'><div class='cd-tag'>{escape(d.role)}</div>"
        f"<div class='cd-act cd-act-{escape(d.action)}'>{escape(d.action)}</div>"
        f"<div class='cd-num'>{d.tokens_before:,} → {d.tokens_after:,}</div></div>"
        for d in report.decisions
    )
    room = report.budget - report.reserved_output
    ok = report.used <= room
    mark = "✓" if ok else "✗"
    foot = (
        f"<div class='cd-foot {'cd-ok' if ok else 'cd-bad'}'>used {report.used:,} / "
        f"{report.budget:,} tok (−{report.reserved_output:,} reserved) {mark}</div>"
    )
    head = "<div class='cd-row cd-hd'><div>block</div><div>action</div><div>tokens</div></div>"
    return f"{head_note}<div class='cd-table'>{head}{rows}</div>{foot}"


# ── squeeze ───────────────────────────────────────────────────────────────────────────────────


def compression_panel(comp: dict | None) -> str:
    if not comp:
        return _empty(
            f"No compression this turn. Paste more than {COMPRESS_THRESHOLD:,} characters "
            "and squeeze runs before the send."
        )
    ok = "byte-for-byte identical ✓" if comp["restored_ok"] else "restore FAILED ✗"
    return (
        f"<div class='cd-big'>{comp['before']:,} → {comp['after']:,} "
        f"<span class='cd-dim'>tokens</span> "
        f"<span class='cd-pct'>({comp['pct']:.0f}% smaller)</span></div>"
        f"<div class='cd-sub'>technique <b>{escape(comp['kind'])}</b> · expand() → {ok}</div>"
    )


# ── guardrails (the deterministic gate) ───────────────────────────────────────────────────────


def gate_panel(session: Session, result: dict | None = None) -> str:
    """The `cendor.guardrails` panel: which rules are armed, and what they decided this turn.

    This is the panel that distinguishes the two governance libraries on screen. `guardrails`
    REFUSES (it raises `GuardrailTripped`, so the request never leaves); `acttrace` RECORDS. The
    Audit panel below shows the same turn from the recording side.
    """
    state = "armed" if session.gate_on else "off"
    cls = "cd-ok" if session.gate_on else "cd-bad"
    rules_html = "".join(f"<li>{escape(n)}</li>" for n in GATE_NAMES)
    head = (
        f"<div class='cd-big'>{len(GATE_NAMES) if session.gate_on else 0} "
        f"<span class='cd-dim'>rules {state}</span></div>"
        f"<ul class='cd-rules'>{rules_html}</ul>"
    )
    if not session.gate_on:
        return head + f"<div class='cd-foot {cls}'>the gate is off — nothing is being refused</div>"

    decisions = (result or {}).get("gate_decisions") or session.gate_decisions
    if not decisions:
        return head + _empty(
            "No decision yet. Try the injection example — the gate refuses it before the "
            "request leaves, and the reply in the chat is the refusal, not an error."
        )
    rows = "".join(
        f"<div class='cd-row'><div class='cd-tag'>{escape(d['guardrail'])}</div>"
        f"<div class='cd-act cd-act-{_ACT_CLASS.get(d['action'], 'kept')}'>"
        f"{escape(d['action'])}</div><div class='cd-num'>{escape(d['stage'])}</div></div>"
        for d in decisions
    )
    tbl_head = (
        "<div class='cd-row cd-hd'><div>guardrail</div><div>action</div><div>stage</div></div>"
    )
    sent = (result or {}).get("sent_preview") or ""
    proof = ""
    if sent and any(d["action"] == "redact" for d in decisions):
        proof = (
            "<div class='cd-foot cd-ok'>the provider received: "
            f"<code>…{escape(sent[-90:])}</code></div>"
        )
    elif any(d["action"] == "block" for d in decisions):
        proof = (
            "<div class='cd-foot cd-bad'>GuardrailTripped raised — the request never left ✗</div>"
        )
    return f"{head}<div class='cd-table'>{tbl_head}{rows}</div>{proof}"


# ── cassette ──────────────────────────────────────────────────────────────────────────────────


def recorder_panel(session: Session) -> str:
    n = len(session.recorded)
    state = "🔴 recording" if session.record_on else "⏹ idle"
    return (
        f"<div class='cd-big'>{n} <span class='cd-dim'>turn(s) captured</span></div>"
        f"<div class='cd-sub'>{state} · replay makes <b>0</b> provider calls</div>"
    )


# ── core ──────────────────────────────────────────────────────────────────────────────────────


def bus_panel(session: Session) -> str:
    """One normalized LLMCall card per call, newest first."""
    if not session.events:
        return _empty("The bus is quiet — send a message to make a call.")
    cards = []
    for ev in reversed(session.events):
        cost = "$0.00 · replay" if ev["replayed"] else f"${ev['cost']}"
        tail = "" if ev["replayed"] else f" <span class='ev-dim'>({escape(ev['label'])})</span>"
        if ev["rerouted"]:
            tail += " <span class='ev-dim'>· rerouted</span>"
        cards.append(
            "<div class='ev-card'><div class='ev-line'>"
            f"<span class='ev-k'>LLMCall</span> · {escape(ev['provider'])} · "
            f"{escape(ev['model'])} · {ev['input']:,} → {ev['output']:,} tok · "
            f"<span class='ev-cost'>{cost}</span>{tail}</div></div>"
        )
    return "".join(cards)


# ── acttrace ──────────────────────────────────────────────────────────────────────────────────


def audit_panel(session: Session, result: dict | None = None) -> str:
    """Hash-chain length + the active policy, plus this turn's scan findings when detection fired.

    `len(session.audit.entries)` is read live, so the empty state shows the chain's genuine length
    (a fresh chain already has its `system_start` entry) rather than a number typed into this file.
    """
    base = (
        f"<div class='cd-big'>{len(session.audit.entries)} "
        f"<span class='cd-dim'>hash-chain entries</span></div>"
        f"<div class='cd-sub'>system <b>{escape(session.audit.system)}</b> · risk_tier "
        f"<b>{escape(session.audit.risk_tier)}</b> · policy <b>{escape(session.policy_name)}</b> · "
        "signed</div>"
    )
    det = result.get("detection") if result else None
    if not det or not det["findings"]:
        return base
    rows = "".join(
        f"<div class='cd-row'><div class='cd-tag'>{escape(f['category'])}</div>"
        f"<div class='cd-act cd-act-{_ACT_CLASS.get(f['action'], 'kept')}'>"
        f"{escape(f['action'])}</div><div class='cd-num'>×{f['count']}</div></div>"
        for f in det["findings"]
    )
    head = "<div class='cd-row cd-hd'><div>category</div><div>action</div><div>count</div></div>"
    if det["block_cats"]:
        note = "<div class='cd-foot cd-bad'>blocked pre-flight — $0 spent, nothing sent ✗</div>"
    elif det["redacted"]:
        note = (
            "<div class='cd-foot cd-ok'>redacted before send — the model never saw the raw "
            "value ✓</div>"
        )
    else:
        note = "<div class='cd-foot'>flagged on the tamper-evident chain</div>"
    return f"{base}<div class='cd-table' style='margin-top:12px'>{head}{rows}</div>{note}"


def panel_head(library: str, title: str) -> str:
    return (
        f"<div class='cd-head'><div class='cd-eyebrow'>{library}</div>"
        f"<div class='cd-h'>{title}</div></div>"
    )
