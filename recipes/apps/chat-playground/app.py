"""chat-playground — a chat UI with Cendor's plumbing made visible on every turn.

You normally can't *see* the cost/context/audit layer under an LLM app. This Gradio app puts a
chat on the left and a live "plumbing panel" on the right, so every turn shows the real machinery:

  * Budget (tokenguard) — a pre-flight USD cap; the block banner when the next call would cross it.
  * Receipt (contextkit) — the per-turn assembly receipt as chat history is packed to a budget.
  * Compression (squeeze) — paste a big blob and watch it shrink, reversibly, before it's sent.
  * Recorder (cassette) — record the session, replay it offline (0 calls, $0), download/upload it.
  * Audit (acttrace) — an offline detection engine scans every prompt against a Policy preset and
    blocks/redacts/flags secrets & PII; the growing hash chain records it. Export, verify, tamper.
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
from cendor.acttrace import AuditLog, Policy, redact, scan, verify
from cendor.contextkit import Block, Context
from cendor.core import bus, instrument, tokens
from cendor.core.types import LLMCall
from cendor.squeeze import compress
from cendor.tokenguard import BudgetExceeded, budget, downgrades, track
from theme import HUE, CendorTheme, font_face_css

# --------------------------------------------------------------------------- configuration

DEMO_MODEL = "gpt-4o"
OPENAI_MODEL = "gpt-4o"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
# Pre-flight downgrade targets (cheaper siblings) for on_exceed="downgrade".
DOWNGRADE = {"gpt-4o": "gpt-4o-mini", "claude-sonnet-4-6": "claude-haiku-4-5"}

# acttrace 1.1 detection policy presets. Each maps the ~20 detected categories (secret · credential
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
_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}
# acttrace policy actions → the receipt's cd-act-* colour classes (red · green · amber · gray).
_ACT_CLASS = {"block": "dropped", "redact": "compressed", "flag": "truncated", "allow": "kept"}

# A support assistant that stuffs a product knowledge base + chat history into context each turn.
# The KB is deliberately large so the budget math and the context receipt both have something real
# to chew on: with a $0.50 cap the ~$0.09/turn spend trips the pre-flight block around the 6th turn,
# and the history block visibly peels its oldest turns as the chat grows past the token budget.
CONTEXT_BUDGET = 40_000
RESERVE_OUTPUT = 1_000

# ⚠️ LIVE MODE IS SIZED SEPARATELY, and it has to be. The numbers above are calibrated against the
# *fake* client, which is free and has no rate limit. Sent to a real provider they are a wall:
# a 40k budget packs ~38.7k input tokens into EVERY turn, and OpenAI's default tier allows
# 30,000 tokens per minute — so live mode used to die on turn 1 with
#   429 Request too large for gpt-4o ... on tokens per min (TPM): Limit 30000, Requested 50818
# (measured 2026-07-31; the "Requested" figure is the input plus OpenAI's own output reservation).
# It was not a slow leak either: Anthropic, whose limit is higher, billed 43,313 input tokens for
# one "hi" — **$0.13 per message**, blowing the app's own $0.50 cap in four turns.
# So live mode keeps the same *shape* — a KB big enough to truncate, history that peels, a cap that
# trips after a handful of turns — at roughly a seventh of the size. The model stays the same as
# demo mode so the receipt, the pricing and the downgrade demo all still line up.
LIVE_CONTEXT_BUDGET = 6_000
LIVE_KB_UNITS = 48
LIVE_DEFAULT_CAP = 0.10  # ~$0.014/turn on gpt-4o -> trips pre-flight around the 7th live turn
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


def _kb(units: int) -> str:
    return "Cendor Store — Support Knowledge Base.\n" + "".join(
        _KB_UNIT.format(n=i) for i in range(1, units + 1)
    )


KB_DOC = _kb(KB_UNITS)
LIVE_KB_DOC = _kb(LIVE_KB_UNITS)


def sizing(run_mode: str) -> tuple[int, str, float]:
    """(context budget, knowledge base, default cap) for this run mode — see LIVE_CONTEXT_BUDGET."""
    if run_mode == "Demo":
        return CONTEXT_BUDGET, KB_DOC, DEFAULT_CAP
    return LIVE_CONTEXT_BUDGET, LIVE_KB_DOC, LIVE_DEFAULT_CAP


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
    policy_name: str = "default"  # acttrace detection preset (default | gdpr | pci | strict)
    policy: Any = field(default_factory=lambda: Policy.default())


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


def _build_context(
    history: list[dict], user_content: str, model: str, run_mode: str = "Demo"
) -> tuple[list[dict], Any]:
    """Pack system + knowledge base + chat history + the user's message to the token budget.
    Emits an AssemblyReport on the bus (so acttrace records a context_assembly entry) and returns
    (messages, report).

    ``run_mode`` picks the sizing: demo mode packs the full 40k budget (free, no rate limit), live
    mode packs ~6k so a real provider neither 429s nor charges $0.13 a message. See `sizing()`."""
    budget_tokens, kb_doc, _ = sizing(run_mode)
    ctx = Context(budget_tokens=budget_tokens, model=model, reserve_output=RESERVE_OUTPUT)
    ctx.add(Block(SYSTEM_PROMPT, priority=10, pin=True, role="system"))
    ctx.add(Block(kb_doc, priority=5, evict="truncate", role="user"))
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


def _max_sev(sevs: Any) -> str:
    """The most serious of the given severities (info < warning < critical)."""
    return max(sevs, key=lambda s: _SEVERITY_RANK.get(s, 0), default="warning")


def _findings_json(findings: Any) -> list[dict]:
    """Serialize scan() findings for the panel — counts + resolved action, never the raw value."""
    return [
        {
            "category": f.category,
            "group": f.group,
            "severity": f.severity,
            "action": f.action,
            "count": f.count,
        }
        for f in findings
    ]


def _detect(session: Session, text: str) -> dict:
    """acttrace 1.1 detection & policy on the RAW input (before squeeze/assembly). Scans against the
    session's Policy; the app ENFORCES (block pre-flight / scrub-before-send) while acttrace RECORDS
    a tamper-evident policy_flag for every non-allow action. Returns the resolved actions plus a
    safe (redacted) copy of the text — scan()/redact() never expose the offending value."""
    findings = scan(text, session.policy)
    block_cats = sorted({f.category for f in findings if f.action == "block"})
    redact_cats = sorted({f.category for f in findings if f.action == "redact"})
    flag_cats = sorted({f.category for f in findings if f.action == "flag"})
    detection = {
        "policy": session.policy_name,
        "findings": _findings_json(findings),
        "block_cats": block_cats,
        "redact_cats": redact_cats,
        "flag_cats": flag_cats,
        "blocked": bool(block_cats),
        "safe_text": text,
        "redacted": False,
    }
    if block_cats:
        session.audit.flag(
            f"blocked {', '.join(block_cats)} in prompt",
            action="blocked",
            severity=_max_sev(f.severity for f in findings if f.action == "block"),
            data=block_cats,
        )
        return detection  # nothing is sent; the caller short-circuits the turn
    # redact-before-send: scrub the redact-action categories so the model (and stored history and
    # any downloaded cassette) never carry the raw secret; record it on the chain.
    if redact_cats:
        detection["safe_text"], _ = redact(text, session.policy)
        detection["redacted"] = True
        session.audit.flag(
            f"redacted {', '.join(redact_cats)} from prompt",
            action="redacted",
            severity="info",
            data=redact_cats,
        )
    if flag_cats:
        session.audit.flag(
            f"flagged {', '.join(flag_cats)} in prompt",
            action="flagged",
            severity=_max_sev(f.severity for f in findings if f.action == "flag"),
            data=flag_cats,
        )
    return detection


def _run_turn(
    session: Session,
    display_text: str,
    content: str,
    run_mode: str,
    provider: str,
    key: str,
    cap: float,
    mode: str,
    record_text: str | None = None,
) -> dict:
    """Run one chat turn through the full Cendor pipeline and mutate the session. Returns a dict of
    what the panels should render (reply, block/downgrade status, the assembly report, events).

    ``record_text`` is the (possibly redacted) prompt stored in a downloaded cassette; it defaults
    to ``display_text`` so the recorded session never leaks a secret the policy scrubbed."""
    record_text = display_text if record_text is None else record_text
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
            messages, report = _build_context(session.history, content, model, run_mode)
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
            except Exception as exc:  # noqa: BLE001 — a provider error is a UI state, not a crash
                # Anything the provider raises (429 rate limit, 401 bad key, 400 bad request) used
                # to escape into Gradio's queue as a bare traceback in the terminal, leaving the UI
                # silent — the user saw nothing at all. It is a governance-relevant outcome, so it
                # is flagged on the chain and rendered in the chat like a block is.
                result["provider_error"] = f"{type(exc).__name__}: {exc}"
                decision.flag(
                    f"provider call failed: {type(exc).__name__}",
                    action="flagged",
                    severity="warning",
                    data=type(exc).__name__,
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
    elif result.get("provider_error"):
        session.transcript.append({"role": "user", "content": display_text})
        session.transcript.append(
            {"role": "assistant", "content": _provider_error_message(result["provider_error"])}
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
                    "user": record_text,
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


def _provider_error_message(err: str) -> str:
    """Turn a provider exception into something a reader can act on. A 429 on a rate limit is the
    one people actually hit, and the useful reply is not "an error occurred" — it is which knob."""
    low = err.lower()
    if "rate_limit" in low or "429" in low or "RateLimitError" in err:
        return (
            "⚠️ **The provider rate-limited this turn** (HTTP 429). Nothing was billed.\n\n"
            f"`{err[:300]}`\n\n"
            "Live mode packs a knowledge base into every turn, so each request is a few thousand "
            f"tokens. If your account's tokens-per-minute allowance is lower than that, drop "
            f"`LIVE_CONTEXT_BUDGET` (currently {LIVE_CONTEXT_BUDGET:,}) and `LIVE_KB_UNITS` "
            f"(currently {LIVE_KB_UNITS}), or wait a minute and retry."
        )
    if "authentication" in low or "401" in low or "api key" in low:
        return f"⚠️ **The provider rejected the key** — check it and try again.\n\n`{err[:300]}`"
    return (
        "⚠️ **The provider call failed** — nothing was billed and the turn was not recorded. "
        f"acttrace chained a `policy_flag` for it.\n\n`{err[:400]}`"
    )


# --------------------------------------------------------------------------- renderers


def _render_budget(session: Session, cap: float, result: dict | None) -> str:
    """The tokenguard spend bar: a filled track with the cap marked, matching the site's demo."""
    spent = float(session.spent_usd)
    cap = max(float(cap), 1e-9)
    pct = min(100.0, 100.0 * spent / cap)
    blocked = bool(result and result.get("blocked"))
    reroute = result.get("reroute") if result else None
    hue = HUE["tokenguard"]
    fill = "#F43F5E" if blocked else hue
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
    return (
        f"<div class='cd-barmeta'><span>spent <b>${spent:.4f}</b> / ${cap:.2f}</span>"
        f"<span>{pct:.0f}%</span></div>"
        f"<div class='cd-track'><div class='cd-fill' style='width:{pct:.1f}%;"
        f"--fh:{fill}'></div><div class='cd-capmark'><span>cap ${cap:.2f}</span></div></div>"
        f"{banner}"
    )


def _render_receipt(result: dict | None) -> str:
    """The contextkit assembly receipt, as the site's mono table: block · action · tokens."""
    if not result or "report" not in result:
        return "<div class='cd-empty'>Send a message — the packed context receipt lands here.</div>"
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
    return f"<div class='cd-table'>{head}{rows}</div>{foot}"


def _render_compression(comp: dict | None) -> str:
    if not comp:
        return (
            "<div class='cd-empty'>No compression this turn. Paste more than "
            f"{COMPRESS_THRESHOLD:,} characters and squeeze runs before the send.</div>"
        )
    ok = "byte-for-byte identical ✓" if comp["restored_ok"] else "restore FAILED ✗"
    return (
        f"<div class='cd-big'>{comp['before']:,} → {comp['after']:,} "
        f"<span class='cd-dim'>tokens</span> "
        f"<span class='cd-pct'>({comp['pct']:.0f}% smaller)</span></div>"
        f"<div class='cd-sub'>technique <b>{escape(comp['kind'])}</b> · expand() → {ok}</div>"
    )


def _render_bus(session: Session) -> str:
    """The core bus feed — one normalized LLMCall card per call, newest first (site .ev-card)."""
    if not session.events:
        return "<div class='cd-empty'>The bus is quiet — send a message to make a call.</div>"
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


def _render_audit(session: Session, result: dict | None = None) -> str:
    """The acttrace panel: hash-chain length + the active policy, plus this turn's scan findings
    (category · resolved action · count) when detection fired."""
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


# --------------------------------------------------------------------------- event handlers


def on_submit(
    user_msg: str,
    sid: str | None,
    run_mode: str,
    provider: str,
    key: str,
    cap: float,
    mode: str,
    policy_name: str = "default",
) -> tuple:
    session = _session(sid)
    cap = _cap(cap)
    # Keep the session's acttrace policy in sync with the panel dropdown (resolved fresh each turn).
    session.policy_name = policy_name if policy_name in POLICY_PRESETS else "default"
    session.policy = POLICY_PRESETS[session.policy_name]()
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

    # acttrace detection & policy first: scan the raw prompt, then block or scrub *before* anything
    # is compressed, assembled, or sent to the model.
    detection = _detect(session, user_msg)
    if detection["blocked"]:
        session.transcript.append({"role": "user", "content": user_msg})
        session.transcript.append(
            {
                "role": "assistant",
                "content": (
                    f"⛔ **Blocked by policy** — the `{detection['policy']}` policy blocks "
                    f"{', '.join(detection['block_cats'])} in a prompt. Nothing was sent to the "
                    "model; $0 spent. acttrace recorded a tamper-evident "
                    "policy_flag(action=blocked)."
                ),
            }
        )
        return _panels(session, {"policy_block": True, "detection": detection}, cap)

    # Everything downstream uses the redacted copy, so the secret never reaches the model, the
    # stored history, or a downloaded cassette. The chat bubble still shows what the user typed.
    send_text = detection["safe_text"]
    content = send_text
    session.last_compression = None
    if len(send_text) > COMPRESS_THRESHOLD:
        small, handle = compress(send_text, kind="auto", target_tokens=COMPRESS_TARGET_TOKENS)
        before = tokens.count(send_text, active_model)
        after = tokens.count(small, active_model)
        session.last_compression = {
            "handle": handle,
            "original": send_text,
            "before": before,
            "after": after,
            "pct": 100.0 * (1 - after / before) if before else 0.0,
            "kind": handle.kind,
            "restored_ok": handle.expand() == send_text,
        }
        content = small

    result = _run_turn(
        session, user_msg, content, run_mode, provider, key, cap, mode, record_text=send_text
    )
    result["detection"] = detection
    return _panels(session, result, cap)


def _panels(session: Session, result: dict | None, cap: float) -> tuple:
    return (
        session.transcript,
        "",
        _render_budget(session, cap, result),
        _render_receipt(result),
        _render_compression(session.last_compression),
        _render_bus(session),
        _render_audit(session, result),
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


def on_policy_change(policy_name: str, sid: str | None) -> tuple[str, str]:
    """Switch the acttrace detection preset and re-render the Audit panel. Returns the session id so
    the (possibly freshly created) session persists in gr.State for the next turn."""
    session = _session(sid)
    session.policy_name = policy_name if policy_name in POLICY_PRESETS else "default"
    session.policy = POLICY_PRESETS[session.policy_name]()
    return _render_audit(session), session.sid


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


def on_reset(sid: str | None, policy_name: str = "default") -> tuple:
    if sid and sid in SESSIONS:
        old = SESSIONS.pop(sid)
        old.audit.detach()
    session = _new_session()
    # The dropdown keeps its value across a reset, so carry the chosen policy onto the new session.
    session.policy_name = policy_name if policy_name in POLICY_PRESETS else "default"
    session.policy = POLICY_PRESETS[session.policy_name]()
    return (
        session.transcript,
        "",
        _render_budget(session, DEFAULT_CAP, None),
        _render_receipt(None),
        _render_compression(None),
        _render_bus(session),
        _render_audit(session),
        "",
        "New session started.",
        session.sid,
    )


def on_mode_change(run_mode: str) -> tuple:
    """Reveal the provider + key rows for live mode, and retarget the cap to that mode's sizing.

    The cap has to move with the mode: $0.50 is ~6 demo turns at the 40k calibration but ~35 live
    turns at the 6k one, so leaving it put would make the pre-flight block look broken in live mode.
    """
    live = run_mode == "Live"
    _, _, cap_for_mode = sizing(run_mode)
    return (
        gr.update(visible=live),
        gr.update(visible=live),
        gr.update(value=cap_for_mode),
        gr.update(
            value=(
                f"Live mode packs a smaller knowledge base ({LIVE_KB_UNITS} policies, "
                f"~{LIVE_CONTEXT_BUDGET:,}-token budget) than demo mode, so one turn fits inside a "
                f"default provider rate limit and costs about a cent. Cap set to "
                f"${cap_for_mode:.2f}."
            )
            if live
            else ""
        ),
    )


# --------------------------------------------------------------------------- UI

# The Cendor starburst (Mark 3): 6 line segments + 4 diagonal dots + 1 blue hub, matching the
# site's Logo.astro. The vertical arm is a plain gapped stroke (no end dots); only the four
# diagonal branches are capped. White on the app's fixed navy topbar; the hub stays blue.
_LOGO_SVG = (
    "<svg width='30' height='30' viewBox='0 0 44 44' aria-hidden='true'>"
    "<g stroke='#fff' stroke-width='2.4' stroke-linecap='round'>"
    "<line x1='22' y1='5' x2='22' y2='14'/><line x1='22' y1='30' x2='22' y2='39'/>"
    "<line x1='7.3' y1='13.5' x2='15' y2='18'/><line x1='29' y1='26' x2='36.7' y2='30.5'/>"
    "<line x1='7.3' y1='30.5' x2='15' y2='26'/><line x1='29' y1='18' x2='36.7' y2='13.5'/></g>"
    "<circle cx='7.3' cy='13.5' r='2.6' fill='#fff'/>"
    "<circle cx='36.7' cy='30.5' r='2.6' fill='#fff'/>"
    "<circle cx='7.3' cy='30.5' r='2.6' fill='#fff'/>"
    "<circle cx='36.7' cy='13.5' r='2.6' fill='#fff'/>"
    "<circle cx='22' cy='22' r='5.4' fill='#2563EB'/></svg>"
)

_HEADER = (
    "<div class='cd-topbar'><div class='cd-brand'>" + _LOGO_SVG + "<span class='cd-word'>CENDOR"
    "</span><span class='cd-slash'>/</span><span class='cd-page'>chat playground</span></div>"
    "<div class='cd-tagline'>the plumbing, made visible — every turn</div></div>"
)

_HONEST_LABEL = (
    "<div class='cd-honest'><b>Demo model</b> — canned replies priced as "
    "<code>gpt-4o</code>. Everything except the reply text is real Cendor. "
    "Connect a key for a live one.</div>"
)

# Ported from the cendor.ai stylesheet + its library-demo components, scoped to this app.
_CSS = (
    font_face_css()
    + """
:root { --hue: #3B82F6; }
.cd-mono, .cd-num, .cd-big, .cd-eyebrow, .cd-barmeta, .cd-row, .cd-foot, .ev-line, .cd-capmark span,
.cd-empty { font-family: "JetBrains Mono","Cascadia Code","SF Mono",Consolas,monospace;
  font-variant-numeric: tabular-nums; }

/* ── top bar ─────────────────────────────────────────────── */
.cd-topbar { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap;
  gap:10px; padding:6px 4px 18px; border-bottom:1px solid rgba(148,163,187,.16);
  margin-bottom:6px; }
.cd-brand { display:flex; align-items:center; gap:10px; }
.cd-word { font-family:"Manrope",system-ui,sans-serif; font-weight:800; letter-spacing:.14em;
  font-size:19px; color:#fff; }
.cd-slash { color:#5F7189; font-weight:400; }
.cd-page { font-family:"JetBrains Mono",monospace; font-size:12px; letter-spacing:.18em;
  text-transform:uppercase; color:#3B82F6; }
.cd-tagline { font-family:"JetBrains Mono",monospace; font-size:12px; color:#94A3BB; }
.cd-honest { font-size:13px; color:#94A3BB; margin:2px 2px 10px; }
.cd-honest b { color:#E5E7EB; }
.cd-honest code { font-family:"JetBrains Mono",monospace; font-size:12px; color:#7DB4FF;
  background:#0A101F; padding:1px 6px; border-radius:5px; }

/* ── panel headers (per-library eyebrow) ─────────────────── */
.cd-panel { border-top:2px solid var(--hue) !important; }
.cd-tokenguard { --hue:#8B5CF6; } .cd-contextkit { --hue:#3B82F6; }
.cd-squeeze { --hue:#22C55E; } .cd-cassette { --hue:#14B8A6; }
.cd-acttrace { --hue:#F43F5E; } .cd-core { --hue:#94A3BB; }
.cd-head { padding:2px 2px 4px; }
.cd-eyebrow { font-size:10.5px; letter-spacing:.2em; text-transform:uppercase; color:var(--hue);
  font-weight:700; }
.cd-h { font-family:"Manrope",system-ui,sans-serif; font-weight:700; font-size:15px; color:#fff;
  margin-top:2px; }

/* ── generic bits ────────────────────────────────────────── */
.cd-num { color:#E5E7EB; font-size:13px; }
.cd-big { color:#fff; font-size:19px; font-weight:700; }
.cd-big .cd-dim { color:#5F7189; font-size:13px; font-weight:400; }
.cd-pct { color:#22C55E; font-size:14px; }
.cd-sub { color:#94A3BB; font-size:12.5px; margin-top:4px; font-family:"JetBrains Mono",monospace; }
.cd-sub b { color:#E5E7EB; }
.cd-empty { font-size:12.5px; color:#5F7189; padding:14px 2px; }

/* ── budget bar (tokenguard) ─────────────────────────────── */
.cd-barmeta { display:flex; justify-content:space-between; font-size:12px; color:#94A3BB;
  margin-bottom:8px; }
.cd-barmeta b { color:#E5E7EB; }
.cd-track { position:relative; height:22px; background:#0B1220;
  border:1px solid rgba(148,163,187,.16); border-radius:8px; margin-top:14px; }
.cd-fill { position:absolute; top:0; bottom:0; left:0; width:0;
  background:linear-gradient(90deg, color-mix(in srgb, var(--fh) 45%, transparent), var(--fh));
  border-radius:7px 0 0 7px; transition:width .35s ease; }
.cd-capmark { position:absolute; right:0; top:-7px; bottom:-7px; width:2px; background:#8B5CF6;
  border-radius:2px; }
.cd-capmark span { position:absolute; top:-20px; right:0; font-size:10px; color:#8B5CF6;
  white-space:nowrap; font-weight:700; }
.cd-banner { margin-top:16px; padding:10px 12px; border-radius:8px; font-size:13px; }
.cd-block { background:rgba(244,63,94,.13); border:1px solid #F43F5E; color:#FDA4AF; }
.cd-reroute { background:rgba(139,92,246,.13); border:1px solid #8B5CF6; color:#C4B5FD; }
.cd-banner b { color:#fff; }

/* ── receipt table (contextkit) ──────────────────────────── */
.cd-table { border:1px solid rgba(148,163,187,.16); border-radius:10px; overflow:hidden; }
.cd-row { display:grid; grid-template-columns:1fr .9fr 1.1fr; border-bottom:1px solid
  rgba(148,163,187,.09); background:#111C33; }
.cd-row:last-child { border-bottom:0; }
.cd-row.cd-hd { background:#0B1220; font-size:10px; letter-spacing:.14em; text-transform:uppercase;
  color:#94A3BB; }
.cd-row > div { padding:9px 12px; font-size:12.5px; }
.cd-tag { color:#3B82F6; }
.cd-act-kept { color:#94A3BB; } .cd-act-truncated { color:#F59E0B; }
.cd-act-dropped { color:#F43F5E; } .cd-act-compressed { color:#22C55E; }
.cd-num { color:#E5E7EB; }
.cd-foot { margin-top:10px; font-size:12px; color:#94A3BB; }
.cd-foot.cd-ok { color:#22C55E; } .cd-foot.cd-bad { color:#F43F5E; }

/* ── bus feed (core) ─────────────────────────────────────── */
.ev-card { background:#111C33; border:1px solid rgba(148,163,187,.09); border-radius:9px;
  padding:11px 14px; margin-bottom:8px; }
.ev-line { font-size:12px; line-height:1.6; color:#C6D3E8; word-break:break-word; }
.ev-k { color:#3B82F6; font-weight:700; } .ev-cost { color:#10B981; } .ev-dim { color:#5F7189; }
"""
)


def _panel_head(library: str, title: str) -> str:
    return (
        f"<div class='cd-head'><div class='cd-eyebrow'>{library}</div>"
        f"<div class='cd-h'>{title}</div></div>"
    )


def build_demo() -> gr.Blocks:
    with gr.Blocks(theme=CendorTheme(), css=_CSS, title="Cendor Chat Playground") as demo:
        state = gr.State(None)
        gr.HTML(_HEADER)

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
        demo_note = gr.HTML(_HONEST_LABEL)
        live_note = gr.Markdown("", elem_classes=["cd-live-note"])

        with gr.Row():
            with gr.Column(scale=5):
                chatbot = gr.Chatbot(type="messages", height=520, label="Chat")
                with gr.Row():
                    msg = gr.Textbox(
                        placeholder="Ask about a refund… or paste a big blob to squeeze it.",
                        scale=8,
                        show_label=False,
                        lines=2,
                    )
                    send = gr.Button("Send", variant="primary", scale=1)
                reset = gr.Button("↺ Reset session", size="sm")
                gr.Examples(
                    examples=[
                        ["I was double charged on order 8823 — can you refund the duplicate?"],
                        ["Cancel my subscription, please."],
                        [
                            "Here's my key sk-proj-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8 — "
                            "email the summary to alice@example.com"
                        ],
                    ],
                    inputs=msg,
                    label="Try one — the last carries a secret (default redacts it; "
                    "switch the policy to strict/pci to block it)",
                )

            with gr.Column(scale=4):
                with gr.Group(elem_classes=["cd-panel", "cd-tokenguard"]):
                    gr.HTML(_panel_head("tokenguard", "Budget"))
                    with gr.Row():
                        cap = gr.Number(value=DEFAULT_CAP, label="USD cap", scale=1, minimum=0.01)
                        mode = gr.Radio(
                            ["block", "downgrade"], value="block", label="on exceed", scale=2
                        )
                    budget_html = gr.HTML(_render_budget_empty())

                with gr.Group(elem_classes=["cd-panel", "cd-contextkit"]):
                    gr.HTML(_panel_head("contextkit", "Receipt"))
                    receipt_html = gr.HTML(_render_receipt(None))

                with gr.Group(elem_classes=["cd-panel", "cd-squeeze"]):
                    gr.HTML(_panel_head("squeeze", "Compression"))
                    comp_html = gr.HTML(_render_compression(None))
                    expand_btn = gr.Button("Expand last blob", size="sm")
                    expand_out = gr.Markdown()

                with gr.Group(elem_classes=["cd-panel", "cd-cassette"]):
                    gr.HTML(_panel_head("cassette", "Recorder"))
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

                with gr.Group(elem_classes=["cd-panel", "cd-acttrace"]):
                    gr.HTML(_panel_head("acttrace", "Audit"))
                    policy_dd = gr.Dropdown(
                        POLICY_NAMES,
                        value="default",
                        label="detection policy",
                        info="every prompt is scanned offline; each hit is blocked, redacted, or "
                        "flagged per preset",
                    )
                    audit_html = gr.HTML(_render_audit_empty())
                    with gr.Row():
                        export_btn = gr.Button("Export evidence", size="sm")
                        verify_btn = gr.Button("Verify", size="sm")
                        tamper_btn = gr.Button("Tamper demo", size="sm")
                    audit_status = gr.Markdown()
                    evidence_file = gr.File(label="evidence pack", interactive=False)

                with gr.Group(elem_classes=["cd-panel", "cd-core"]):
                    gr.HTML(_panel_head("core", "Bus feed"))
                    bus_html = gr.HTML(_render_bus_empty())

        # wiring
        panel_out = [
            chatbot,
            msg,
            budget_html,
            receipt_html,
            comp_html,
            bus_html,
            audit_html,
            state,
        ]
        submit_in = [msg, state, run_mode, provider, key, cap, mode, policy_dd]
        send.click(on_submit, submit_in, panel_out)
        msg.submit(on_submit, submit_in, panel_out)

        run_mode.change(on_mode_change, run_mode, [provider, key, cap, live_note])
        run_mode.change(lambda m: gr.update(visible=(m == "Demo")), run_mode, demo_note)
        cap.change(on_cap_change, [cap, state], budget_html)
        policy_dd.change(on_policy_change, [policy_dd, state], [audit_html, state])

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
            [state, policy_dd],
            [
                chatbot,
                msg,
                budget_html,
                receipt_html,
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
        f"<div class='cd-barmeta'><span>spent <b>$0.0000</b> / ${DEFAULT_CAP:.2f}</span>"
        "<span>0%</span></div>"
        "<div class='cd-track'><div class='cd-fill' style='width:0%;--fh:#8B5CF6'></div>"
        f"<div class='cd-capmark'><span>cap ${DEFAULT_CAP:.2f}</span></div></div>"
    )


def _render_audit_empty() -> str:
    return (
        "<div class='cd-big'>1 <span class='cd-dim'>hash-chain entries</span></div>"
        "<div class='cd-sub'>system <b>chat_playground</b> · risk_tier <b>limited</b> · "
        "policy <b>default</b> · signed</div>"
    )


def _render_bus_empty() -> str:
    return "<div class='cd-empty'>The bus is quiet — send a message to make a call.</div>"


if __name__ == "__main__":
    build_demo().launch(favicon_path=str(Path(__file__).parent / "assets" / "favicon.svg"))
