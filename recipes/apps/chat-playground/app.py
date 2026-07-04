"""chat-playground — a chat UI with Cendor's plumbing made visible on every turn.

You normally can't *see* the cost/context/audit layer under an LLM app. This Gradio app puts a
chat on the left and a live "plumbing panel" on the right, so every turn shows the real machinery:

  * Budget (tokenguard) — a pre-flight USD cap; the block banner when the next call would cross it.
  * Receipt (contextkit) — the per-turn assembly receipt as chat history is packed to a budget.
  * Compression (squeeze) — paste a big blob and watch it shrink, reversibly, before it's sent.
  * Recorder (cassette) — record the session, replay it offline (0 calls, $0), download/upload it.
  * Audit (acttrace) — the growing hash chain; export an evidence pack, verify it, tamper it.
  * Bus feed (core) — one normalized event per call: provider, model, usage, Decimal cost.

Everything except the reply text is REAL Cendor. Demo mode (default, no key) uses a fake
provider-shaped client with canned replies priced as gpt-4o; live mode calls OpenAI/Anthropic
with a key from the environment or the password box (the key stays in process memory only).

Run:  uv sync --group apps && uv run --group apps python recipes/apps/chat-playground/app.py
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from html import escape
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import gradio as gr
from cendor import cassette
from cendor.acttrace import AuditLog, verify
from cendor.contextkit import Block, Context
from cendor.core import bus, instrument, tokens
from cendor.core.types import LLMCall
from cendor.squeeze import compress
from cendor.tokenguard import BudgetExceeded, budget, downgrades, track
from theme import BLUE, CendorTheme

# --------------------------------------------------------------------------- configuration

DEMO_MODEL = "gpt-4o"
OPENAI_MODEL = "gpt-4o"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
# Pre-flight downgrade targets (cheaper siblings) for on_exceed="downgrade".
DOWNGRADE = {"gpt-4o": "gpt-4o-mini", "claude-sonnet-4-6": "claude-haiku-4-5"}

# A support assistant that stuffs a product knowledge base + chat history into context each turn.
# The KB is deliberately large so the budget math and the context receipt both have something real
# to chew on: with a $0.50 cap the ~$0.09/turn spend trips the pre-flight block around the 6th turn,
# and the history block visibly peels its oldest turns as the chat grows past the token budget.
CONTEXT_BUDGET = 40_000
RESERVE_OUTPUT = 1_000
COMPRESS_THRESHOLD = 1_500  # chars pasted before squeeze kicks in
COMPRESS_TARGET_TOKENS = 400
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # reject cassette uploads larger than 2 MB
SUPPORTED_CASSETTE_VERSIONS = (1, 2)
DEFAULT_CAP = 0.50

# Demo signing key: env override, fallback so the app is green out of the box. In production load
# this from a secret manager — never commit a real key.
SIGNING_KEY = os.environ.get("CENDOR_DEMO_KEY", "demo-signing-key")

SYSTEM_PROMPT = (
    "You are Cendor Store's support assistant. Answer using the knowledge base provided, cite the "
    "relevant policy number when you can, and keep replies concise and friendly."
)

_KB_UNIT = (
    "Policy {n}: Duplicate or double charges are refunded within five business days once a "
    "billing agent confirms the transaction id. A refund needs the order number, the charge "
    "date, and the last four digits of the card on file. Subscription cancellations take effect "
    "at the end of the current billing period; prorated credits are not issued. Shipping delays "
    "beyond ten business days qualify for expedited reshipment at no cost. Tier-two support "
    "handles chargebacks and fraud holds. "
)
# ~91 tokens/unit. 424 units ≈ 38.6k tokens — calibrated so with the default $0.50 cap the
# ~$0.096/turn spend trips the pre-flight block on the 6th turn, while leaving just enough room in
# the 40k context budget that the history block keeps recent turns and peels its oldest ones (the
# receipt shows "truncated 378 → 291" as the chat grows). See test_app.py::test_demo_full_loop.
KB_UNITS = 424
KB_DOC = "Cendor Store — Support Knowledge Base.\n" + "".join(
    _KB_UNIT.format(n=i) for i in range(1, KB_UNITS + 1)
)

# Deterministic canned replies, varied in length. Several are intentionally long so the chat
# history block grows quickly — enough to watch contextkit peel its oldest turns in the receipt.
CANNED_REPLIES = [
    "Hi! I'm the Cendor Store assistant. I can help with refunds, orders, shipping, cancellations, "
    "and billing questions. I'll always cite the relevant policy so you can see exactly why "
    "something is or isn't covered. To get started, tell me your order number and what happened — "
    "for a billing issue, the charge date and the last four digits of the card help me find it "
    "fast. What can I do for you today?",
    "Per Policy 1, a duplicate or double charge is refunded within five business days once a "
    "billing agent confirms the transaction id. To confirm it, I need three things: the order "
    "number, the date of the charge, and the last four digits of the card on file. As soon as I "
    "have those I'll match the transaction, queue the reversal, and email you a confirmation with "
    "a reference number you can quote if you ever need to follow up.",
    "Good news — I found the order and I can see the two identical charges from the same day. "
    "I've queued the duplicate for reversal under Policy 1, so you'll see the credit land on your "
    "statement within five business days. I've also emailed a receipt with today's reference "
    "number. The original, legitimate charge stays in place; only the accidental duplicate is "
    "being returned. Is there anything else on the account I should check while I'm here?",
    "Refund eligibility under Policy 1 comes down to three details: the order number, the charge "
    "date, and the last four digits of the card. Once you send those, I verify the transaction "
    "against our records, and if it matches I can start the reversal immediately — no manager "
    "approval needed for a confirmed duplicate. If any detail doesn't line up, I'll tell you "
    "exactly what's missing rather than leaving you guessing.",
    "For a subscription cancellation, the change takes effect at the end of your current billing "
    "period, so you keep full access until then and won't be charged again afterward. Prorated "
    "credits aren't issued for the unused part of the period — that's covered in the cancellation "
    "policy — but there are no cancellation fees either. Want me to schedule it to end at your "
    "next renewal date, or cancel it right away and let access lapse at period end?",
    "When a shipment runs more than ten business days late, our policy covers a free expedited "
    "reshipment at no cost to you — you don't pay twice and you don't wait in line behind new "
    "orders. I can trigger that reshipment now; I just need you to confirm the delivery address on "
    "file is still correct. If the original package turns up later, you're welcome to keep or "
    "return it, whichever is easier — there's no penalty either way.",
    "That looks like a chargeback question, which tier-two support owns rather than the front "
    "line. I've flagged your case for them and attached the transaction id and the notes from our "
    "conversation so you won't have to repeat yourself. They typically follow up by email within "
    "one business day. In the meantime, avoid filing a bank dispute for the same charge, since a "
    "duplicate dispute can actually slow the refund down.",
    "Happy to help! To summarize what we've covered so far: I confirmed the order, started the "
    "refund for the duplicate charge under Policy 1, and emailed you a receipt with a reference "
    "number. Nothing else on the account looks unusual — no failed payments, no pending holds, and "
    "the subscription is active and paid through the current period. Is there anything else you'd "
    "like me to look into while we're connected?",
    "I don't see a matching transaction under that order number, which usually means one of a few "
    "things: a typo in the number, an order placed under a different email, or a charge that's "
    "still pending and hasn't posted yet. Could you double-check the number, or share the email "
    "address the order was placed under? I can search by email, by the last four digits of the "
    "card, or by the approximate charge date — whichever is easiest for you.",
    "You're welcome — glad I could sort that out. Your reference number for today's refund is in "
    "the confirmation email I just sent; keep it handy in case you ever need to reference this "
    "conversation. The credit should appear within five business days, and if it hasn't shown up "
    "by then, reply to that email with the reference and we'll escalate it immediately. Thanks for "
    "being a Cendor Store customer, and reach out any time.",
]

_KEYWORDS = [
    (("hello", "hi ", "hey"), 0),
    (("cancel", "subscription", "unsubscribe"), 4),
    (("late", "shipping", "delivery", "arrive"), 5),
    (("chargeback", "fraud", "dispute"), 6),
    (("thank", "thanks", "cheers"), 9),
    (("refund", "double", "duplicate", "charged"), 1),
]


def _demo_reply(user_text: str, turn: int) -> str:
    """A deterministic canned reply: keyword match first, else cycle by turn (great for videos)."""
    text = f" {user_text.lower()} "
    for needles, idx in _KEYWORDS:
        if any(n in text for n in needles):
            return CANNED_REPLIES[idx]
    return CANNED_REPLIES[turn % len(CANNED_REPLIES)]


# --------------------------------------------------------------------------- session state

# The Cendor bus, tokenguard records and acttrace subscriptions are process-global, so this app is
# built for one active session at a time (one local run / one Codespace). Session objects are held
# here (not in gr.State) because they own an AuditLog with an open file handle and a live bus
# subscription — gr.State holds only the session id string.
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


def _new_session() -> Session:
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


def _session(sid: str | None) -> Session:
    if sid and sid in SESSIONS:
        return SESSIONS[sid]
    return _new_session()


# --------------------------------------------------------------------------- clients


def _demo_client(reply: str) -> Any:
    """A fake OpenAI-shaped client. It reports the *real* token counts of the messages it receives
    and of the canned reply, so pricing, budget math and the receipt are all genuine — only the
    reply text is scripted. Makes no network call."""

    class Completions:
        def create(self, **kwargs: Any) -> Any:
            model = kwargs.get("model", DEMO_MODEL)
            messages = kwargs.get("messages", [])
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
                usage=SimpleNamespace(
                    prompt_tokens=tokens.count(messages, model),
                    completion_tokens=tokens.count(
                        [{"role": "assistant", "content": reply}], model
                    ),
                ),
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def _resolve_key(provider: str, key: str) -> str:
    if key:
        return key
    return os.environ.get("OPENAI_API_KEY" if provider == "OpenAI" else "ANTHROPIC_API_KEY", "")


def _call_model(
    run_mode: str, provider: str, key: str, model: str, messages: list[dict], reply: str
) -> str:
    """Issue one instrumented model call and return the reply text. Demo mode is offline; live mode
    calls the provider directly with the key (kept in memory only, never written or logged)."""
    if run_mode == "Demo":
        client = _demo_client(reply)
        resp = client.chat.completions.create(model=model, messages=messages)
        return resp.choices[0].message.content
    if provider == "OpenAI":
        from openai import OpenAI  # lazy: live mode only

        client = instrument(OpenAI(api_key=key))
        resp = client.chat.completions.create(model=OPENAI_MODEL, messages=messages)
        return resp.choices[0].message.content
    from anthropic import Anthropic  # lazy: live mode only

    client = instrument(Anthropic(api_key=key))
    system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
    body = "\n\n".join(str(m.get("content", "")) for m in messages if m.get("role") != "system")
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": body}],
    )
    return resp.content[0].text


# --------------------------------------------------------------------------- the turn pipeline


def _build_context(history: list[dict], user_content: str, model: str) -> tuple[list[dict], Any]:
    """Pack system + knowledge base + chat history + the user's message to the token budget.
    Emits an AssemblyReport on the bus (so acttrace records a context_assembly entry) and returns
    (messages, report)."""
    ctx = Context(budget_tokens=CONTEXT_BUDGET, model=model, reserve_output=RESERVE_OUTPUT)
    ctx.add(Block(SYSTEM_PROMPT, priority=10, pin=True, role="system"))
    ctx.add(Block(KB_DOC, priority=5, evict="truncate", role="user"))
    if history:
        ctx.add(Block(messages=list(history), priority=3, evict="drop_oldest"))
    ctx.add(Block(user_content, priority=9, pin=True, role="user"))
    messages = ctx.assemble()
    return messages, ctx.report()


def _snapshot(event: LLMCall) -> dict:
    """A UI-friendly snapshot of a bus LLMCall for the feed and the recorder."""
    label = (
        "replayed"
        if event.metadata.get("replayed")
        else "cost_reported"
        if event.metadata.get("cost_reported")
        else "cost_estimated"
    )
    return {
        "provider": event.provider,
        "model": event.model,
        "input": event.usage.input_tokens if event.usage else 0,
        "output": event.usage.output_tokens if event.usage else 0,
        "cost": str(event.cost.amount) if event.cost else "0",
        "label": label,
        "rerouted": bool(event.metadata.get("rerouted")),
        "replayed": bool(event.metadata.get("replayed")),
    }


def _run_turn(
    session: Session,
    display_text: str,
    content: str,
    run_mode: str,
    provider: str,
    key: str,
    cap: float,
    mode: str,
) -> dict:
    """Run one chat turn through the full Cendor pipeline and mutate the session. Returns a dict of
    what the panels should render (reply, block/downgrade status, the assembly report, events)."""
    model = (
        DEMO_MODEL
        if run_mode == "Demo"
        else (OPENAI_MODEL if provider == "OpenAI" else ANTHROPIC_MODEL)
    )
    on_exceed = "downgrade" if mode == "downgrade" else "block"
    dmap = {model: DOWNGRADE[model]} if (on_exceed == "downgrade" and model in DOWNGRADE) else None

    captured: list[dict] = []

    def capture(event: object) -> None:
        if isinstance(event, LLMCall):
            captured.append(_snapshot(event))

    result: dict[str, Any] = {"reply": None, "blocked": False, "block_msg": "", "reroute": None}
    n_downgrades = len(downgrades())
    guard = budget(
        usd=float(cap), on_exceed=on_exceed, downgrade=dmap, output_reserve=RESERVE_OUTPUT
    )

    bus.subscribe(capture)
    try:
        with session.audit.decision(input="chat turn", actor="user") as decision:
            messages, report = _build_context(session.history, content, model)
            result["report"] = report
            try:
                with guard:
                    guard.frame.spent_usd = session.spent_usd
                    with track(feature="chat", session_id=session.sid[:8]):
                        result["reply"] = _call_model(
                            run_mode,
                            provider,
                            key,
                            model,
                            messages,
                            _demo_reply(display_text, session.turn),
                        )
                    decision.record(model=model, prompt_id="support@v1")
                session.spent_usd = guard.frame.spent_usd
            except BudgetExceeded as exc:
                result["blocked"] = True
                result["block_msg"] = str(exc)
                decision.flag(
                    "budget cap would be exceeded",
                    action="blocked",
                    severity="warning",
                    data="tokenguard_preflight",
                )
    finally:
        bus.unsubscribe(capture)

    if len(downgrades()) > n_downgrades:
        last = downgrades()[-1]
        result["reroute"] = (last["from"], last["to"])

    session.events.extend(captured)
    session.events = session.events[-8:]
    result["events"] = captured

    if result["blocked"]:
        session.transcript.append({"role": "user", "content": display_text})
        session.transcript.append(
            {
                "role": "assistant",
                "content": "⛔ **Blocked pre-flight** — refused to keep spend under cap. $0 spent.",
            }
        )
    else:
        session.turn += 1
        session.history.append({"role": "user", "content": content})
        session.history.append({"role": "assistant", "content": result["reply"]})
        session.transcript.append({"role": "user", "content": display_text})
        session.transcript.append({"role": "assistant", "content": result["reply"]})
        if session.record_on and captured:
            ev = captured[-1]
            session.recorded.append(
                {
                    "user": display_text,
                    "request": {
                        "provider": ev["provider"],
                        "model": ev["model"],
                        "messages": messages,
                    },
                    "response": {
                        "choices": [{"message": {"content": result["reply"]}}],
                        "usage": {"prompt_tokens": ev["input"], "completion_tokens": ev["output"]},
                    },
                }
            )
    return result


# --------------------------------------------------------------------------- renderers


def _render_budget(session: Session, cap: float, result: dict | None) -> str:
    spent = float(session.spent_usd)
    cap = max(float(cap), 1e-9)
    pct = min(100.0, 100.0 * spent / cap)
    blocked = bool(result and result.get("blocked"))
    reroute = result.get("reroute") if result else None
    fill = "#DC2626" if blocked else BLUE
    banner = ""
    if blocked:
        banner = (
            "<div class='cendor-banner cendor-block'>⛔ <b>BudgetExceeded</b> — blocked "
            "pre-flight, $0 spent. The over-budget call never ran.</div>"
        )
    elif reroute:
        banner = (
            "<div class='cendor-banner cendor-reroute'>↘ <b>Downgraded</b> — "
            f"{escape(reroute[0])} → {escape(reroute[1])} to stay under cap ($0 extra).</div>"
        )
    return (
        f"<div class='cendor-num'>${spent:.4f} / ${cap:.2f} &nbsp;({pct:.0f}%)</div>"
        f"<div class='cendor-bar'><div class='cendor-bar-fill' style='width:{pct:.1f}%;"
        f"background:{fill}'></div></div>{banner}"
    )


def _render_receipt(result: dict | None) -> tuple[list[list[str]], str]:
    if not result or "report" not in result:
        return [], ""
    report = result["report"]
    rows = [
        [d.role, d.action, f"{d.tokens_before:,} → {d.tokens_after:,}"] for d in report.decisions
    ]
    room = report.budget - report.reserved_output
    ok = "✓" if report.used <= room else "✗"
    caption = (
        f"<div class='cendor-num'>used {report.used:,} / budget {report.budget:,} "
        f"(−{report.reserved_output:,} output reserve) &nbsp;{ok}</div>"
    )
    return rows, caption


def _render_compression(comp: dict | None) -> str:
    if not comp:
        return (
            "<div class='cendor-muted'>No compression this turn. Paste more than "
            f"{COMPRESS_THRESHOLD:,} characters to squeeze it before sending.</div>"
        )
    ok = "byte-for-byte identical ✓" if comp["restored_ok"] else "restore FAILED ✗"
    return (
        f"<div class='cendor-num'>{comp['before']:,} → {comp['after']:,} tokens "
        f"({comp['pct']:.0f}% smaller)</div>"
        f"<div class='cendor-muted'>technique: {escape(comp['kind'])} · Expand() → {ok}</div>"
    )


def _render_bus(session: Session) -> str:
    if not session.events:
        return "<div class='cendor-muted'>No calls yet — send a message.</div>"
    cards = []
    for ev in reversed(session.events):
        badges = f"<span class='cendor-tag'>{escape(ev['label'])}</span>"
        if ev["rerouted"]:
            badges += "<span class='cendor-tag cendor-tag-blue'>rerouted</span>"
        if ev["replayed"]:
            badges += "<span class='cendor-tag cendor-tag-blue'>replay · $0</span>"
        cards.append(
            "<div class='cendor-card'>"
            f"<div class='cendor-num'>{escape(ev['provider'])} · {escape(ev['model'])}</div>"
            f"<div class='cendor-muted'>{ev['input']:,} in + {ev['output']:,} out · "
            f"${ev['cost']}</div>{badges}</div>"
        )
    return "".join(cards)


def _render_audit(session: Session) -> str:
    return (
        f"<div class='cendor-num'>hash-chain entries: {len(session.audit.entries)}</div>"
        f"<div class='cendor-muted'>system: {escape(session.audit.system)} · risk_tier: "
        f"{escape(session.audit.risk_tier)} · signed</div>"
    )


# --------------------------------------------------------------------------- event handlers


def on_submit(
    user_msg: str,
    sid: str | None,
    run_mode: str,
    provider: str,
    key: str,
    cap: float,
    mode: str,
) -> tuple:
    session = _session(sid)
    cap = _cap(cap)
    user_msg = (user_msg or "").strip()
    if not user_msg:
        return _panels(session, None, cap)

    if run_mode == "Live":
        resolved = _resolve_key(provider, key)
        if not resolved:
            env = "OPENAI_API_KEY" if provider == "OpenAI" else "ANTHROPIC_API_KEY"
            session.transcript.append({"role": "user", "content": user_msg})
            session.transcript.append(
                {
                    "role": "assistant",
                    "content": f"⚠️ Live mode needs a {provider} key — paste one, or set {env}.",
                }
            )
            return _panels(session, None, cap)
        key = resolved

    active_model = (
        DEMO_MODEL
        if run_mode == "Demo"
        else (OPENAI_MODEL if provider == "OpenAI" else ANTHROPIC_MODEL)
    )
    content = user_msg
    session.last_compression = None
    if len(user_msg) > COMPRESS_THRESHOLD:
        small, handle = compress(user_msg, kind="auto", target_tokens=COMPRESS_TARGET_TOKENS)
        before = tokens.count(user_msg, active_model)
        after = tokens.count(small, active_model)
        session.last_compression = {
            "handle": handle,
            "original": user_msg,
            "before": before,
            "after": after,
            "pct": 100.0 * (1 - after / before) if before else 0.0,
            "kind": handle.kind,
            "restored_ok": handle.expand() == user_msg,
        }
        content = small

    result = _run_turn(session, user_msg, content, run_mode, provider, key, cap, mode)
    return _panels(session, result, cap)


def _panels(session: Session, result: dict | None, cap: float) -> tuple:
    rows, caption = _render_receipt(result)
    return (
        session.transcript,
        "",
        _render_budget(session, cap, result),
        rows,
        caption,
        _render_compression(session.last_compression),
        _render_bus(session),
        _render_audit(session),
        session.sid,
    )


def _cap(cap: float | None) -> float:
    """Coerce the cap Number to a sane positive float (it can be cleared to None in the UI)."""
    try:
        value = float(cap)
    except (TypeError, ValueError):
        return DEFAULT_CAP
    return value if value > 0 else DEFAULT_CAP


def on_cap_change(cap: float, sid: str | None) -> str:
    return _render_budget(_session(sid), _cap(cap), None)


def on_expand(sid: str | None) -> str:
    session = _session(sid)
    comp = session.last_compression
    if not comp:
        return "Nothing to expand — no blob was compressed this session."
    restored = comp["handle"].expand()
    ok = restored == comp["original"]
    head = restored[:1200] + ("…" if len(restored) > 1200 else "")
    return (
        f"**Expanded — byte-for-byte identical: {ok}** "
        f"({len(restored):,} chars restored from {comp['after']:,} tokens)\n\n```\n{head}\n```"
    )


def on_export(sid: str | None) -> tuple[Any, str]:
    session = _session(sid)
    path = os.path.join(session.tmp, "evidence.jsonl")
    session.audit.export(path, framework="eu_ai_act")
    session.evidence_path = path
    return (
        path,
        f"Exported {len(session.audit.entries)} entries → evidence.jsonl (EU AI Act tagged).",
    )


def on_verify(sid: str | None) -> str:
    session = _session(sid)
    if not session.evidence_path or not Path(session.evidence_path).exists():
        session.audit.export(os.path.join(session.tmp, "evidence.jsonl"), framework="eu_ai_act")
        session.evidence_path = os.path.join(session.tmp, "evidence.jsonl")
    ok, detail = verify(session.evidence_path, key=SIGNING_KEY)
    icon = "✅" if ok else "❌"
    return f"{icon} **verify: {ok}**\n\n`{escape(detail)}`"


def on_tamper(sid: str | None) -> str:
    session = _session(sid)
    if not session.evidence_path or not Path(session.evidence_path).exists():
        session.audit.export(os.path.join(session.tmp, "evidence.jsonl"), framework="eu_ai_act")
        session.evidence_path = os.path.join(session.tmp, "evidence.jsonl")
    data = Path(session.evidence_path).read_bytes()
    marker = DEMO_MODEL.encode()
    if marker not in data:
        return "Run at least one chat turn first, so there's a signed model call to tamper with."
    i = data.index(marker)
    flipped = data[:i] + b"G" + data[i + 1 :]  # flip one byte inside a hashed payload
    tampered = os.path.join(session.tmp, "evidence_tampered.jsonl")
    Path(tampered).write_bytes(flipped)
    ok, detail = verify(tampered, key=SIGNING_KEY)
    return f"🔨 flipped one byte → **verify: {ok}**\n\n`{escape(detail)}`"


def on_record_toggle(value: bool, sid: str | None) -> str:
    session = _session(sid)
    session.record_on = bool(value)
    if session.record_on:
        return "🔴 Recording — each successful turn is captured."
    return f"⏹ Stopped. {len(session.recorded)} turn(s) captured. Replay or download them below."


def _build_cassette(session: Session) -> str | None:
    if not session.recorded:
        return None
    trace = os.path.join(session.tmp, "trace.jsonl")
    lines = [
        json.dumps({"kind": "llm", "request": r["request"], "response": r["response"]})
        for r in session.recorded
    ]
    Path(trace).write_text("\n".join(lines), encoding="utf-8")
    cass = os.path.join(session.tmp, "session.cassette.json")
    cassette.promote(trace, cass)
    return cass


def on_download(sid: str | None) -> tuple[Any, str]:
    session = _session(sid)
    cass = _build_cassette(session)
    if not cass:
        return None, "Nothing recorded yet — toggle Record on and chat a few turns."
    n = len(json.loads(Path(cass).read_text(encoding="utf-8"))["entries"])
    return cass, f"Cassette ready: {n} entries. Download it, then upload it back to replay offline."


def _replay_cassette(
    session: Session, cass_path: str, pairs: list[str] | None
) -> tuple[list[dict], str]:
    """Replay a cassette offline through the real cassette interceptor and prove 0 real calls."""
    payload = json.loads(Path(cass_path).read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    real_calls = {"n": 0}

    def counting_client() -> Any:
        class Completions:
            def create(self, **kwargs: Any) -> Any:  # only runs if replay MISSES (it shouldn't)
                real_calls["n"] += 1
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="(live miss)"))],
                    usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
                )

        return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))

    transcript: list[dict] = []
    captured: list[dict] = []

    def capture(event: object) -> None:
        if isinstance(event, LLMCall):
            captured.append(_snapshot(event))

    client = counting_client()
    bus.subscribe(capture)
    try:
        with cassette.using(cass_path, mode="replay"):
            for i, entry in enumerate(entries):
                req = entry["request"]
                resp = client.chat.completions.create(model=req["model"], messages=req["messages"])
                reply = resp.choices[0].message.content
                user = pairs[i] if pairs and i < len(pairs) else f"(recorded turn {i + 1})"
                transcript.append({"role": "user", "content": user})
                transcript.append({"role": "assistant", "content": reply})
    finally:
        bus.unsubscribe(capture)

    session.events.extend(captured)
    session.events = session.events[-8:]
    status = (
        f"▶ Replayed {len(entries)} turn(s) offline — **{real_calls['n']} real calls, $0 spent**. "
        "Same replies, no network."
    )
    return transcript, status


def on_replay(sid: str | None) -> tuple:
    session = _session(sid)
    cass = _build_cassette(session)
    if not cass:
        return (
            session.transcript,
            "Nothing recorded yet — toggle Record on and chat first.",
            _render_bus(session),
            session.sid,
        )
    pairs = [r["user"] for r in session.recorded]
    transcript, status = _replay_cassette(session, cass, pairs)
    session.transcript = transcript
    return transcript, status, _render_bus(session), session.sid


def on_upload(file_path: Any, sid: str | None) -> tuple:
    session = _session(sid)
    path = file_path if isinstance(file_path, str) else getattr(file_path, "name", None)
    if not path or not Path(path).exists():
        return session.transcript, "No file received.", _render_bus(session), session.sid
    size = Path(path).stat().st_size
    if size > MAX_UPLOAD_BYTES:
        return (
            session.transcript,
            f"Rejected: file is {size:,} bytes (cap {MAX_UPLOAD_BYTES:,}).",
            _render_bus(session),
            session.sid,
        )
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (
            session.transcript,
            f"Rejected: not valid JSON ({exc}).",
            _render_bus(session),
            session.sid,
        )
    if not isinstance(payload, dict):
        return (
            session.transcript,
            "Rejected: cassette must be a JSON object.",
            _render_bus(session),
            session.sid,
        )
    version = payload.get("version")
    if version not in SUPPORTED_CASSETTE_VERSIONS:
        return (
            session.transcript,
            f"Rejected: unsupported cassette version {version!r} (this app replays "
            f"{SUPPORTED_CASSETTE_VERSIONS}).",
            _render_bus(session),
            session.sid,
        )
    if not isinstance(payload.get("entries"), list):
        return (
            session.transcript,
            "Rejected: cassette has no 'entries' list.",
            _render_bus(session),
            session.sid,
        )
    # Copy to our temp dir and replay it. Nothing from the file is ever eval'd.
    safe = os.path.join(session.tmp, "uploaded.cassette.json")
    shutil.copyfile(path, safe)
    transcript, status = _replay_cassette(session, safe, None)
    session.transcript = transcript
    return (
        transcript,
        f"Loaded {Path(path).name} (v{version}). {status}",
        _render_bus(session),
        session.sid,
    )


def on_reset(sid: str | None) -> tuple:
    if sid and sid in SESSIONS:
        old = SESSIONS.pop(sid)
        old.audit.detach()
    session = _new_session()
    return (
        session.transcript,
        "",
        _render_budget(session, DEFAULT_CAP, None),
        [],
        "",
        _render_compression(None),
        _render_bus(session),
        _render_audit(session),
        "",
        "New session started.",
        session.sid,
    )


def on_mode_change(run_mode: str) -> tuple:
    live = run_mode == "Live"
    return gr.update(visible=live), gr.update(visible=live)


# --------------------------------------------------------------------------- UI

_CSS = """
.cendor-num { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums; color: #E2E8F0; font-size: 0.9rem; }
.cendor-muted { font-family: ui-monospace, Menlo, Consolas, monospace; color: #94A3B8;
  font-size: 0.8rem; margin-top: 2px; }
.cendor-bar { height: 12px; background: #111C30; border-radius: 6px; margin: 6px 0;
  overflow: hidden; border: 1px solid #334155; }
.cendor-bar-fill { height: 100%; transition: width .25s ease; }
.cendor-banner { margin-top: 8px; padding: 8px 10px; border-radius: 6px; font-size: 0.85rem; }
.cendor-block { background: rgba(220,38,38,.15); border: 1px solid #DC2626; color: #FCA5A5; }
.cendor-reroute { background: rgba(37,99,235,.15); border: 1px solid #2563EB; color: #93C5FD; }
.cendor-card { background: #111C30; border: 1px solid #334155; border-radius: 8px;
  padding: 8px 10px; margin-bottom: 6px; }
.cendor-tag { display: inline-block; margin-top: 6px; margin-right: 4px; padding: 1px 8px;
  border-radius: 999px; font-size: 0.72rem; background: #334155; color: #CBD5E1;
  font-family: ui-monospace, Menlo, monospace; }
.cendor-tag-blue { background: #2563EB; color: #fff; }
"""

_HONEST_LABEL = (
    "**Demo model** — canned replies priced as `gpt-4o`. Everything except the reply text is real "
    "Cendor. Connect a key for a live one."
)


def build_demo() -> gr.Blocks:
    with gr.Blocks(theme=CendorTheme(), css=_CSS, title="Cendor Chat Playground") as demo:
        state = gr.State(None)
        gr.Markdown(
            "# ✳ Cendor Chat Playground\nA chat with the plumbing made visible — every turn."
        )

        with gr.Row():
            run_mode = gr.Radio(
                ["Demo", "Live"],
                value="Demo",
                label="Mode",
                scale=2,
                info="Demo runs offline with no key.",
            )
            provider = gr.Radio(
                ["OpenAI", "Anthropic"], value="OpenAI", label="Provider", visible=False, scale=2
            )
            key = gr.Textbox(
                label="API key",
                type="password",
                visible=False,
                scale=3,
                placeholder="stays in memory — never written or logged",
            )
        demo_note = gr.Markdown(_HONEST_LABEL)

        with gr.Row():
            with gr.Column(scale=5):
                chatbot = gr.Chatbot(
                    type="messages", height=460, label="Chat", show_copy_button=True
                )
                with gr.Row():
                    msg = gr.Textbox(
                        placeholder="Ask about a refund… or paste a big blob to squeeze it.",
                        scale=8,
                        show_label=False,
                        lines=2,
                    )
                    send = gr.Button("Send", variant="primary", scale=1)
                reset = gr.Button("Reset session", size="sm")

            with gr.Column(scale=4):
                with gr.Group():
                    gr.Markdown("### 💰 Budget · tokenguard")
                    with gr.Row():
                        cap = gr.Number(value=DEFAULT_CAP, label="USD cap", scale=1, minimum=0.01)
                        mode = gr.Radio(
                            ["block", "downgrade"], value="block", label="on exceed", scale=2
                        )
                    budget_html = gr.HTML(_render_budget_empty())

                with gr.Group():
                    gr.Markdown("### 🧾 Receipt · contextkit")
                    receipt_df = gr.Dataframe(
                        headers=["block", "action", "tokens"],
                        datatype=["str", "str", "str"],
                        col_count=(3, "fixed"),
                        interactive=False,
                        wrap=True,
                    )
                    receipt_cap = gr.HTML()

                with gr.Group():
                    gr.Markdown("### 🗜 Compression · squeeze")
                    comp_html = gr.HTML(_render_compression(None))
                    expand_btn = gr.Button("Expand last blob", size="sm")
                    expand_out = gr.Markdown()

                with gr.Group():
                    gr.Markdown("### ⏺ Recorder · cassette")
                    record = gr.Checkbox(value=False, label="Record this session")
                    with gr.Row():
                        replay_btn = gr.Button("▶ Replay offline", size="sm")
                        download_btn = gr.Button("⬇ Build download", size="sm")
                    upload_btn = gr.UploadButton(
                        "⬆ Upload cassette (.json)",
                        file_types=[".json"],
                        type="filepath",
                        size="sm",
                    )
                    recorder_status = gr.Markdown("Idle. Toggle Record on to capture turns.")
                    cassette_file = gr.File(label="cassette", interactive=False)

                with gr.Group():
                    gr.Markdown("### 🔗 Audit · acttrace")
                    audit_html = gr.HTML(_render_audit_empty())
                    with gr.Row():
                        export_btn = gr.Button("Export evidence", size="sm")
                        verify_btn = gr.Button("Verify", size="sm")
                        tamper_btn = gr.Button("Tamper demo", size="sm")
                    audit_status = gr.Markdown()
                    evidence_file = gr.File(label="evidence pack", interactive=False)

                with gr.Group():
                    gr.Markdown("### 📡 Bus feed · core")
                    bus_html = gr.HTML(_render_bus_empty())

        # wiring
        panel_out = [
            chatbot,
            msg,
            budget_html,
            receipt_df,
            receipt_cap,
            comp_html,
            bus_html,
            audit_html,
            state,
        ]
        submit_in = [msg, state, run_mode, provider, key, cap, mode]
        send.click(on_submit, submit_in, panel_out)
        msg.submit(on_submit, submit_in, panel_out)

        run_mode.change(on_mode_change, run_mode, [provider, key])
        run_mode.change(lambda m: gr.update(visible=(m == "Demo")), run_mode, demo_note)
        cap.change(on_cap_change, [cap, state], budget_html)

        expand_btn.click(on_expand, state, expand_out)
        record.change(on_record_toggle, [record, state], recorder_status)
        replay_btn.click(on_replay, state, [chatbot, recorder_status, bus_html, state])
        download_btn.click(on_download, state, [cassette_file, recorder_status])
        upload_btn.upload(
            on_upload, [upload_btn, state], [chatbot, recorder_status, bus_html, state]
        )

        export_btn.click(on_export, state, [evidence_file, audit_status])
        export_btn.click(lambda s: _render_audit(_session(s)), state, audit_html)
        verify_btn.click(on_verify, state, audit_status)
        tamper_btn.click(on_tamper, state, audit_status)

        reset.click(
            on_reset,
            state,
            [
                chatbot,
                msg,
                budget_html,
                receipt_df,
                receipt_cap,
                comp_html,
                bus_html,
                audit_html,
                expand_out,
                recorder_status,
                state,
            ],
        )
    return demo


def _render_budget_empty() -> str:
    return (
        f"<div class='cendor-num'>$0.0000 / ${DEFAULT_CAP:.2f} &nbsp;(0%)</div>"
        f"<div class='cendor-bar'><div class='cendor-bar-fill' style='width:0%;background:{BLUE}'>"
        "</div></div>"
    )


def _render_audit_empty() -> str:
    return (
        "<div class='cendor-num'>hash-chain entries: 1</div>"
        "<div class='cendor-muted'>system: chat_playground · risk_tier: limited · signed</div>"
    )


def _render_bus_empty() -> str:
    return "<div class='cendor-muted'>No calls yet — send a message.</div>"


if __name__ == "__main__":
    build_demo().launch(favicon_path=str(Path(__file__).parent / "assets" / "favicon.svg"))
