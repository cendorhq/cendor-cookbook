"""The turn pipeline — every library except the UI lives here, and nothing here imports Gradio.

Order of a turn, and why it is this order:

  detect (acttrace)  scan the RAW prompt against the session's Policy. A `block` action ends the
                     turn here: nothing is compressed, assembled or sent, and the refusal is
                     chained. A `redact` action scrubs the text *before* anything downstream sees
                     it, so neither the model nor a downloaded cassette carries the secret.
  compress (squeeze) only if the (redacted) prompt is large. Reversible: `handle.expand()`.
  assemble (contextkit)  system + knowledge base + history + the user's message, packed to a token
                     budget. Emits an AssemblyReport, so acttrace records a context_assembly entry.
  gate (guardrails)  a DETERMINISTIC gate on the interceptor chain. It sees the final request, the
                     one that is about to leave, and raises `GuardrailTripped` on a block.
  budget (tokenguard)  a pre-flight USD cap around the call.
  call (core)        `instrument()`ed client — one normalized LLMCall on the bus, priced.
  record (cassette)  optional; the session recorder captures the turn for offline replay.

⚠️ **`guardrails` and `acttrace` are BOTH here on purpose, and they are not the same thing.**
acttrace *detects and records* (a tamper-evident chain of what the policy saw and decided);
guardrails *enforces* (a rule on the call itself that raises before the request leaves). A reader
who has only ever seen one of them usually assumes it does the other's job too. The Gate panel and
the Audit panel exist side by side so the difference is visible on one screen.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from cendor import cassette
from cendor.acttrace import redact, scan, verify
from cendor.contextkit import Block, Context
from cendor.core import bus, instrument, tokens
from cendor.core.types import LLMCall
from cendor.guardrails import GuardrailDecision, GuardrailTripped, install, rules, uninstall
from cendor.squeeze import compress
from cendor.tokenguard import BudgetExceeded, budget, downgrades, track
from config import (
    ANTHROPIC_MODEL,
    COMPRESS_TARGET_TOKENS,
    COMPRESS_THRESHOLD,
    DOWNGRADE,
    OPENAI_MODEL,
    RESERVE_OUTPUT,
    SIGNING_KEY,
    SYSTEM_PROMPT,
    demo_reply,
    model_for,
    sizing,
)
from session import Session

_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}

# The deterministic gate. Two rules, chosen so the panel shows both actions a gate can take:
#   * a keyword_deny that BLOCKS — the request never leaves, `GuardrailTripped` is raised
#   * a regex_rule that REDACTS — the request leaves with the value replaced
#
# ⚠️ The redact rule deliberately targets an **internal customer reference**, not an API key.
# acttrace's detection engine already knows the standard catalogue (~20 categories: secret,
# credential, financial, gov_id, pii, special_category) and it runs FIRST, so by the time a prompt
# reaches this gate a leaked `sk-…` has already been redacted or blocked by policy — measured: all
# four presets resolve `api_key`, three to `redact` and `strict` to `block`. A hand-written gate
# rule is for the things only *your* organisation knows are sensitive, which is precisely what the
# catalogue cannot contain. Writing the two layers so they overlap makes a good screenshot and
# teaches the wrong division of labour.
GATE_RULES = [
    lambda: rules.keyword_deny(
        ["ignore previous instructions", "disregard the system prompt"], action="block"
    ),
    lambda: rules.regex_rule(r"\bCUST-\d{6,}\b", action="redact", stage="input"),
]
GATE_NAMES = ["keyword_deny (block)", "regex_rule CUST-###### (redact)"]


class gate_scope:  # noqa: N801 — a context manager used like a function
    """Install the guardrails gate for the duration of one turn, and always uninstall it.

    `install()` is process-global. Left installed it silently gates every later call in the
    process, which in a long-lived app means a rule the user turned off in the UI is still running.
    """

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __enter__(self) -> gate_scope:
        if self.enabled:
            install([make() for make in GATE_RULES])
        return self

    def __exit__(self, *exc: object) -> None:
        if self.enabled:
            uninstall()


# --------------------------------------------------------------------------- clients


def demo_client(reply: str, seen: list | None = None) -> Any:
    """A fake OpenAI-shaped client. It reports the *real* token counts of the messages it receives
    and of the canned reply, so pricing, budget math and the receipt are all genuine — only the
    reply text is scripted. Makes no network call.

    ⚠️ `seen` records the kwargs **the client was actually handed** — i.e. below the interceptor
    chain, after guardrails has rewritten the request. That is the only vantage point from which a
    redaction can be proven. Reading `session.history` or the assembled `messages` shows the text
    *before* the chain ran, so a working redaction reads there as a leak. (Measured twice on this
    codebase: once in the 2026-07-31 sweep harness, once in this app's own test.)
    """

    class Completions:
        def create(self, **kwargs: Any) -> Any:
            if seen is not None:
                seen.append(kwargs)
            model = kwargs.get("model", OPENAI_MODEL)
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


def resolve_key(provider: str, key: str) -> str:
    if key:
        return key
    return os.environ.get("OPENAI_API_KEY" if provider == "OpenAI" else "ANTHROPIC_API_KEY", "")


def call_model(
    run_mode: str,
    provider: str,
    key: str,
    model: str,
    messages: list[dict],
    reply: str,
    seen: list | None = None,
) -> str:
    """Issue one instrumented model call and return the reply text. Demo mode is offline; live mode
    calls the provider directly with the key (kept in memory only, never written or logged).

    `seen` is filled only in demo mode: it is the fake's own record of the request, taken below the
    interceptor chain. There is no equivalent for a live provider — the wire is the provider's SDK.
    """
    if run_mode == "Demo":
        client = demo_client(reply, seen)
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


def build_context(
    history: list[dict], user_content: str, model: str, run_mode: str = "Demo"
) -> tuple[list[dict], Any]:
    """Pack system + knowledge base + chat history + the user's message to the token budget.

    ``run_mode`` picks the sizing: demo mode packs the full 40k budget (free, no rate limit), live
    mode packs ~6k so a real provider neither 429s nor charges $0.13 a message. See `sizing()`.
    """
    budget_tokens, kb_doc, _ = sizing(run_mode)
    ctx = Context(budget_tokens=budget_tokens, model=model, reserve_output=RESERVE_OUTPUT)
    ctx.add(Block(SYSTEM_PROMPT, priority=10, pin=True, role="system"))
    ctx.add(Block(kb_doc, priority=5, evict="truncate", role="user"))
    if history:
        ctx.add(Block(messages=list(history), priority=3, evict="drop_oldest"))
    ctx.add(Block(user_content, priority=9, pin=True, role="user"))
    messages = ctx.assemble()
    return messages, ctx.report()


def snapshot(event: LLMCall) -> dict:
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


def gate_snapshot(d: GuardrailDecision) -> dict:
    """A UI-friendly snapshot of one guardrails decision. Never carries the matched value."""
    return {
        "guardrail": d.guardrail,
        "stage": d.stage,
        "action": d.action,
        "reason": d.reason,
    }


def _max_sev(sevs: Any) -> str:
    """The most serious of the given severities (info < warning < critical)."""
    return max(sevs, key=lambda s: _SEVERITY_RANK.get(s, 0), default="warning")


def findings_json(findings: Any) -> list[dict]:
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


def detect(session: Session, text: str) -> dict:
    """acttrace detection & policy on the RAW input (before squeeze/assembly). Scans against the
    session's Policy; the app ENFORCES (block pre-flight / scrub-before-send) while acttrace RECORDS
    a tamper-evident policy_flag for every non-allow action. Returns the resolved actions plus a
    safe (redacted) copy of the text — scan()/redact() never expose the offending value."""
    findings = scan(text, session.policy)
    block_cats = sorted({f.category for f in findings if f.action == "block"})
    redact_cats = sorted({f.category for f in findings if f.action == "redact"})
    flag_cats = sorted({f.category for f in findings if f.action == "flag"})
    detection = {
        "policy": session.policy_name,
        "findings": findings_json(findings),
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


def run_turn(
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
    what the panels should render (reply, block/gate/downgrade status, the assembly report, events).

    ``record_text`` is the (possibly redacted) prompt stored in a downloaded cassette; it defaults
    to ``display_text`` so the recorded session never leaks a secret the policy scrubbed."""
    record_text = display_text if record_text is None else record_text
    model = model_for(run_mode, provider)
    on_exceed = "downgrade" if mode == "downgrade" else "block"
    dmap = {model: DOWNGRADE[model]} if (on_exceed == "downgrade" and model in DOWNGRADE) else None

    captured: list[dict] = []
    gate_seen: list[dict] = []
    # What the CLIENT was handed, below the interceptor chain — the only layer from which the
    # Gate panel can prove a redaction rather than assert one. Demo mode only; see call_model().
    wire: list[dict] = []

    def capture(event: object) -> None:
        if isinstance(event, LLMCall):
            captured.append(snapshot(event))
        elif isinstance(event, GuardrailDecision):
            gate_seen.append(gate_snapshot(event))

    result: dict[str, Any] = {"reply": None, "blocked": False, "block_msg": "", "reroute": None}
    n_downgrades = len(downgrades())
    guard = budget(
        usd=float(cap), on_exceed=on_exceed, downgrade=dmap, output_reserve=RESERVE_OUTPUT
    )

    bus.subscribe(capture)
    try:
        with session.audit.decision(input="chat turn", actor="user") as decision:
            messages, report = build_context(session.history, content, model, run_mode)
            result["report"] = report
            try:
                with gate_scope(session.gate_on), guard:
                    guard.frame.spent_usd = session.spent_usd
                    with track(feature="chat", session_id=session.sid[:8]):
                        result["reply"] = call_model(
                            run_mode,
                            provider,
                            key,
                            model,
                            messages,
                            demo_reply(display_text, session.turn),
                            wire,
                        )
                    decision.record(model=model, prompt_id="support@v1")
                session.spent_usd = guard.frame.spent_usd
            except GuardrailTripped as exc:
                # ⚠️ The gate RAISES on a block — it does not return a decision list with
                # action="block" in it. A handler that only reads the return value never sees the
                # block, and the user reads "the agent hit an error" instead of your policy's
                # refusal. Catching it here is what turns it into a rendered refusal.
                trip = exc.decisions[-1] if exc.decisions else None
                result["gate_blocked"] = gate_snapshot(trip) if trip else {"guardrail": "?"}
                decision.flag(
                    f"guardrail blocked: {result['gate_blocked'].get('guardrail')}",
                    action="blocked",
                    severity="warning",
                    data="guardrails",
                )
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
    session.gate_decisions.extend(gate_seen)
    session.gate_decisions = session.gate_decisions[-8:]
    result["events"] = captured
    result["gate_decisions"] = gate_seen
    result["sent_preview"] = _user_text(wire[-1]["messages"]) if wire else ""

    if result["blocked"] or result.get("gate_blocked"):
        session.transcript.append({"role": "user", "content": display_text})
        session.transcript.append({"role": "assistant", "content": _refusal_message(result)})
    elif result.get("provider_error"):
        session.transcript.append({"role": "user", "content": display_text})
        session.transcript.append(
            {"role": "assistant", "content": provider_error_message(result["provider_error"])}
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


def _user_text(messages: list[dict]) -> str:
    """The last user message as the CLIENT received it — post-gate, post-redaction."""
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content", ""))[-300:]
    return ""


def _refusal_message(result: dict) -> str:
    gate = result.get("gate_blocked")
    if gate:
        return (
            f"⛔ **Blocked by the guardrail** — `{gate.get('guardrail')}` refused this at the "
            f"`{gate.get('stage')}` stage. The request never left the process; $0 spent.\n\n"
            f"> {gate.get('reason', '')}\n\n"
            "*(This is `cendor.guardrails` — a deterministic gate that **raises**. The Audit panel "
            "shows `acttrace` recording the same turn: one enforces, the other proves.)*"
        )
    return "⛔ **Blocked pre-flight** — refused to keep spend under cap. $0 spent."


def provider_error_message(err: str) -> str:
    """Turn a provider exception into something a reader can act on. A 429 on a rate limit is the
    one people actually hit, and the useful reply is not "an error occurred" — it is which knob."""
    from config import LIVE_CONTEXT_BUDGET, LIVE_KB_UNITS

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


# --------------------------------------------------------------------------- squeeze


def maybe_compress(session: Session, text: str, model: str) -> str:
    """Compress a big paste before it is sent, reversibly. Returns what to send."""
    session.last_compression = None
    if len(text) <= COMPRESS_THRESHOLD:
        return text
    small, handle = compress(text, kind="auto", target_tokens=COMPRESS_TARGET_TOKENS)
    before = tokens.count(text, model)
    after = tokens.count(small, model)
    session.last_compression = {
        "handle": handle,
        "original": text,
        "before": before,
        "after": after,
        "pct": 100.0 * (1 - after / before) if before else 0.0,
        "kind": handle.kind,
        "restored_ok": handle.expand() == text,
    }
    return small


# --------------------------------------------------------------------------- cassette


def build_cassette(session: Session) -> str | None:
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


def replay_cassette(
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
            captured.append(snapshot(event))

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


# --------------------------------------------------------------------------- acttrace evidence


def export_evidence(session: Session) -> str:
    path = os.path.join(session.tmp, "evidence.jsonl")
    session.audit.export(path, framework="eu_ai_act")
    session.evidence_path = path
    return path


def verify_evidence(session: Session) -> tuple[bool, str]:
    if not session.evidence_path or not Path(session.evidence_path).exists():
        export_evidence(session)
    return verify(session.evidence_path, key=SIGNING_KEY)


def tamper_evidence(session: Session) -> tuple[bool, str] | None:
    """Flip one byte inside a hashed payload and re-verify. None if there is nothing to tamper."""
    if not session.evidence_path or not Path(session.evidence_path).exists():
        export_evidence(session)
    data = Path(session.evidence_path).read_bytes()
    marker = OPENAI_MODEL.encode()
    if marker not in data:
        return None
    i = data.index(marker)
    tampered = os.path.join(session.tmp, "evidence_tampered.jsonl")
    Path(tampered).write_bytes(data[:i] + b"G" + data[i + 1 :])
    return verify(tampered, key=SIGNING_KEY)
