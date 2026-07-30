"""Govern a **Microsoft 365 Agents SDK custom engine agent** — the whole wrap map, one file.

A *custom engine agent* is the tile where **you** hold the model client ("you manage orchestration
and provide your own LLM" — Microsoft's words). Your process hosts `AgentApplication` behind
`POST /api/messages`; the model call inside the `activity("message")` handler is an ordinary
provider-SDK call. That is the whole reason cendor applies: it is your call, your tokens, your bill.

Everything below is real host code from `microsoft-agents-hosting-aiohttp` plus the published cendor
packages. The only stand-in is the provider client — `make_client()` returns a small async fake so
this recipe runs in CI with **no key and no network**. Swap it for
`instrument(AsyncOpenAI())` and nothing else changes; `instrument()` detection is structural.

The wrap map, in the order the handler hits it:

    (A) pre-flight estimate + block ..... `preflight()`      refuse before spending anything
    (B) per-turn budget scope ........... `turn_budget()`     wraps the WHOLE body (tool loops)
    (C) per-conversation cumulative cap . `SpendLedger`       TurnState, Decimal-as-string
    (D) attribution tags ................ `turn_scope()`      conversation.id (never AAD by default)
    (E) mid-stream break ................ `turn_budget(stream=True)`

    + instrument() on the client, guardrails in/out, acttrace guard + hash-chained audit,
      contextkit/squeeze history assembly, and the `channelData.cendor` reply envelope.

⚠️ This host runs `/api/messages` in **anonymous** mode, which is the supported local posture and an
**open relay in production**. See the README's "Before you deploy this" box.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from cendor.acttrace import AuditLog, Policy, PolicyViolation, guard
from cendor.contextkit import Block
from cendor.contextkit import Context as CkContext
from cendor.core import (
    LLMCall,
    Money,
    add_ambient_provider,
    add_interceptor,
    bus,
    instrument,
    prices,
    tokens,
    trace,
)
from cendor.guardrails import (
    Context as GrContext,
)
from cendor.guardrails import (
    GuardrailDecision,
    GuardrailTripped,
    evaluate_async,
    presets,
    rules,
)
from cendor.squeeze import compress
from cendor.tokenguard import BudgetExceeded, budget, track
from microsoft_agents.activity import Activity, ActivityTypes
from microsoft_agents.hosting.aiohttp import (
    CloudAdapter,
    jwt_authorization_middleware,
    start_agent_process,
)
from microsoft_agents.hosting.core import (
    AgentApplication,
    Authorization,
    MemoryStorage,
    StreamingResponse,
    TurnContext,
    TurnState,
)
from microsoft_agents.hosting.core.authorization import (
    AgentAuthConfiguration,
    AnonymousTokenProvider,
    ConnectionManager,
)

MODEL = os.environ.get("MODEL", "gpt-4o-mini")
INSTRUCTIONS = "You are a concise support agent in Microsoft Teams. Answer in one short sentence."

# (C) The session cap. Money is a `Decimal`, never a float — cardinal rule, and the reason the
# ledger round-trips through TurnState as a *string*.
SESSION_CAP_USD = Decimal(os.environ.get("SESSION_CAP_USD", "5.00"))
TURN_CAP_USD = Decimal(os.environ.get("TURN_CAP_USD", "0.05"))
MAX_OUTPUT_TOKENS = 48
CONTEXT_BUDGET_TOKENS = 1200

# ⚠️ TRAP — **the output-cap parameter is not the same on every model, and the wrong one is a hard
# 400 on every turn.** The reasoning families (o-series, gpt-5-*) reject `max_tokens` outright:
#
#   400 Unsupported parameter: 'max_tokens' is not supported with this model.
#       Use 'max_completion_tokens' instead.
#
# Measured against a Foundry deployment running `gpt-5-mini` (api-version 2024-10-21) — which is
# exactly the `AsyncAzureOpenAI(...)` swap `make_client()` offers below, so the recipe's own
# documented Azure path used to fail on its first call. It matters here more than in a plain OpenAI
# app because **an Azure deployment name is arbitrary**: `MODEL` may be `prod-chat` with a gpt-5
# behind it, so no name heuristic can be authoritative. Hence: heuristic default, env override,
# and a one-shot switch when the provider tells us which name it wants.
CAP_PARAM = os.environ.get("OUTPUT_CAP_PARAM") or (
    "max_completion_tokens" if re.match(r"(?i)^(o[1-9]|gpt-5)", MODEL) else "max_tokens"
)
# ⚠️ And once the cap is accepted, mind what it BUYS on a reasoning model: the cap covers reasoning
# tokens too. Measured on the same deployment, `MAX_OUTPUT_TOKENS = 48` returned
# `37 in / 48 out` with an EMPTY visible reply — the whole allowance went to hidden reasoning. The
# governance numbers are all correct; there is simply no text. Raise the cap for a reasoning
# deployment, or keep the demo cap and expect an empty answer.

# ⚠️ TRAP — TurnState paths are scoped by the state **class name**, not by a lowercase word.
# `state.get_value("conversation.spent_usd")` raises `ValueError: Scope 'conversation' not found`.
SPEND_KEY = "ConversationState.cendor_spent_usd"
HISTORY_KEY = "ConversationState.history"


# ─────────────────────────────────────────────────── the instrumented client (one line, at startup)


def make_client() -> Any:
    """The provider client, wrapped once. **Swap the body, keep the `instrument()`.**

    Production::

        from openai import AsyncOpenAI
        return instrument(AsyncOpenAI())      # or AsyncAzureOpenAI(...), AsyncAnthropic(...)

    The fake below keeps this recipe offline and keyless. It is an *async* client on purpose: an
    aiohttp handler is async, and the async path is the one that used to break under cassette replay
    (fixed in cendor-core 1.14.1 — see the README's pins).
    """

    class Completions:
        async def create(self, **kw: Any) -> Any:
            if kw.get("stream"):
                return _fake_stream(kw)
            answer = (
                "Your refund is on its way."
                if "refund" in str(kw.get("messages"))
                else "Happy to help."
            )
            return SimpleNamespace(
                model=kw["model"],
                choices=[SimpleNamespace(message=SimpleNamespace(content=answer))],
                usage=SimpleNamespace(prompt_tokens=41, completion_tokens=8),
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


async def _fake_stream(kw: dict[str, Any]) -> Any:
    """An OpenAI-shaped chunk stream, so the (E) breaker has real chunks to break on."""
    words = ("Here", " is", " a", " long", " answer", " that", " keeps", " going", " and", " going")
    for w in words * 6:
        yield SimpleNamespace(
            model=kw["model"],
            choices=[SimpleNamespace(delta=SimpleNamespace(content=w), finish_reason=None)],
            usage=None,
        )


# ──────────────────────────────────────── (D) attribution: a ContextVar + a `trace()` scope
#
# The framework owns identity — cendor carries none of its own. `TurnContext` is handed to the
# handler explicitly, so a ContextVar is all it takes, and it isolates correctly under genuinely
# concurrent turns (measured with six overlapping conversations in one process).

_TURN: ContextVar[dict[str, Any] | None] = ContextVar("m365_turn", default=None)


def install_turn_ambient() -> Any:
    """Once, at startup: stamp whatever is in `_TURN` onto every event the bus sees.

    Returns the provider so `close()` can remove it; a long-lived server never needs to.
    """

    def provider(_event: Any) -> dict[str, Any]:
        return dict(_TURN.get() or {})

    add_ambient_provider(provider)
    return provider


@contextmanager
def turn_scope(context: TurnContext) -> Iterator[dict[str, Any]]:
    """Both halves matter, and both are scoped to exactly one turn.

    * the **ambient stamp** — conversation / channel / activity id on every `LLMCall`;
    * the **`trace()` scope** — so a tool loop's N calls share ONE `trace_id`. Without it a call
      carries no trace id at all and the reply envelope has nothing to correlate.

    Only `conversation.id` is stamped. The sender's AAD object id is right there on
    `activity.from_property` and is deliberately **not** tagged: identity in exported telemetry is
    personal data. Opt in explicitly (and consider hashing) if you need per-user attribution.

    ⚠️ Forgetting this scope fails **silently** — cost and usage stay exact, only attribution
    vanishes, with no warning. TypeScript equivalent: `AsyncLocalStorage.run(value, fn)`, never
    `enterWith`.
    """
    act = context.activity
    stamp = {
        "conversation": act.conversation.id,
        "channel": act.channel_id,
        "turn_activity_id": act.id,
    }
    token = _TURN.set(stamp)
    try:
        with trace(f"{act.conversation.id}:{act.id}"):
            yield stamp
    finally:
        _TURN.reset(token)


# ────────────────────────────────────────────────────── guardrails on the channel boundary


def input_gate() -> tuple:
    return (
        presets.prompt_injection(stage="input", action="block"),
        rules.regex_rule(
            r"[\w.+-]+@[\w-]+\.[\w.]+",
            action="redact",
            stage="input",
            name="email_redact",
            replacement="[email redacted]",
        ),
        rules.length_bounds(max_chars=8000, stage="input", action="block", name="activity_length"),
    )


def output_gate() -> tuple:
    return (
        rules.keyword_deny(
            ["internal-only"], stage="output", action="block", name="disclosure_deny"
        ),
        rules.regex_rule(
            r"\bsk-[A-Za-z0-9]{8,}\b",
            action="redact",
            stage="output",
            name="apikey_redact",
            replacement="[redacted]",
        ),
    )


async def gate(
    guardrails: tuple, stage: str, payload: Any, *, conversation_id: str
) -> tuple[Any, list]:
    """⚠️ **THE most important call shape on this page.**

    `evaluate_async` (and TypeScript's `evaluateAsync`) **RAISE** `GuardrailTripped` on a block —
    they do not hand you back a decision list with `action="block"` in it. A handler that only reads
    the return value never sees the block: it escapes as an unhandled turn error and your user reads
    *"the agent hit an error"* instead of your policy's refusal, which is indistinguishable from a
    broken agent. Catch it, and the refusal becomes yours to word.

    The `redact` path is why this is `evaluate_async` and not a boolean check: the returned payload
    is the *rewritten* text, so the model never sees the e-mail address.
    """
    ctx = GrContext(
        stage=stage, agent="m365-custom-engine", metadata={"conversation": conversation_id}
    )
    try:
        return await evaluate_async(guardrails, stage, payload, ctx)
    except GuardrailTripped as tripped:
        return payload, list(tripped.decisions)


def blocked(decisions: list[GuardrailDecision]) -> GuardrailDecision | None:
    return next((d for d in decisions if d.action == "block"), None)


# ──────────────────────────────────────────────── acttrace: evidence for a long-lived server


def install_audit(path: str) -> tuple[AuditLog, Any]:
    """One append-only, hash-chained file per **process**, installed once at startup.

    Why an interceptor and not a per-turn `with guard(...)`: the scope form mutates a process-global
    interceptor list, so under concurrent turns turn A's exit races turn B's entry.

    Reopening this same path after a restart **resumes** the chain and `acttrace.verify()` stays
    green. What acttrace refuses (>= 1.13.1) is two *live* `AuditLog`s on one file at once —
    the second raises at construction, because two interleaved hash chains in one file can never
    verify. So rotate per process only if you have **concurrent writers**, not merely because you
    restarted. (That is also why `verify()` here is the module function, taking a path: reading a
    chain needs no second live writer.)
    """
    log = AuditLog(system="m365-custom-engine", risk_tier="limited", path=path)
    interceptor = guard(Policy.gdpr(), log)
    add_interceptor(interceptor)
    return log, interceptor


# ─────────────────────────────────────── contextkit + squeeze: the prompt in a token budget
#
# Replayed conversation history is the dominant token-growth driver in a chat agent — every turn
# re-sends the previous ones. So assemble inside a budget instead of concatenating.


@dataclass
class Assembly:
    messages: list[dict]
    compressed: bool = False


def assemble_prompt(*, history: list[dict], user_text: str) -> Assembly:
    ctx = CkContext(budget_tokens=CONTEXT_BUDGET_TOKENS, model=MODEL, reserve_output=256)
    ctx.add(Block(content=INSTRUCTIONS, role="system", priority=100, pin=True))

    compressed = False
    if history:
        blob = "\n".join(f"{m['role']}: {m['content']}" for m in history)
        if len(blob) > 1200:
            text, _handle = compress(blob, kind="prose", target_tokens=256, model=MODEL)
            ctx.add(
                Block(
                    content=f"Earlier conversation (compressed):\n{text}",
                    role="system",
                    priority=50,
                )
            )
            compressed = True
        else:
            ctx.add(Block(messages=history, priority=50, evict="drop_oldest"))

    ctx.add(Block(content=user_text, role="user", priority=90, pin=True))
    return Assembly(messages=ctx.assemble(), compressed=compressed)


# ───────────────────────────────── (C) the per-conversation cap, held in the host's own TurnState
#
# tokenguard budgets are scope-shaped: they live and die with a `with`. Conversations are
# long-lived. The bridge is the hosting SDK's own conversation-scoped state, so the cap survives
# turns — and, with Blob/Cosmos storage instead of MemoryStorage, process restarts.


@dataclass
class SpendLedger:
    state: Any
    cap_usd: Decimal = SESSION_CAP_USD
    turn_cap_usd: Decimal = TURN_CAP_USD

    @property
    def spent(self) -> Decimal:
        raw = self.state.get_value(SPEND_KEY, lambda: None)  # absent must read $0, not raise
        return Decimal(str(raw)) if raw else Decimal("0")

    @property
    def remaining(self) -> Decimal:
        return self.cap_usd - self.spent

    @property
    def exhausted(self) -> bool:
        return self.spent >= self.cap_usd

    def turn_allowance(self) -> Decimal:
        """The per-turn scope is the **derived remainder** — a $4.97 session can burn $0.03 more."""
        return min(self.turn_cap_usd, self.remaining)

    def add(self, cost: Money | None) -> Decimal:
        total = self.spent + (cost.amount if isinstance(cost, Money) else Decimal("0"))
        self.state.set_value(SPEND_KEY, str(total))  # Decimal-as-string, never a float
        return total


@contextmanager
def turn_budget(
    allowance: Decimal, *, conversation_id: str, stream: bool = False
) -> Iterator[None]:
    """(B)/(E) — ONE scope around the whole handler body, so a tool loop shares one fuse.

    `on_exceed="break"` on a streamed turn stops the provider stream at the chunk where the
    allowance dies; `"block"` otherwise refuses call N+1 after calls 1..N ate the cap.
    """
    with track(conversation=conversation_id):
        with budget(
            usd=allowance,
            on_exceed="break" if stream else "block",
            name=f"m365-turn:{conversation_id}",
        ):
            yield


def preflight(messages: list[dict], *, allowance: Decimal) -> tuple[bool, Money | None]:
    """(A) — estimate before spending. Zero spend on refusal.

    ⚠️ The estimate reserves the **full** `max_output_tokens`, which a short answer never uses
    (measured 3.04x over-reservation on one real turn). So (A) can refuse while the ledger still
    shows headroom — correct and zero-spend, but **never word that refusal as "you reached your
    cap"**. Say the request *would* exceed what is left.

    An unpriced model (Azure deployment names, Bedrock/HF/Ollama ids) yields `None`: there is no
    number, so there is no refusal — let the real budget scope do the work.
    """
    try:
        text = "\n".join(str(m.get("content", "")) for m in messages)
        est = prices.estimate(MODEL, tokens.count(text, MODEL), MAX_OUTPUT_TOKENS)
    except Exception:
        return True, None
    if est is None or est.amount <= 0:
        return True, est
    return est.amount <= allowance, est


# ───────────────────────────────────────────────────── the reply envelope, attached in the handler
#
# `FoundryAdapter` is **not** used here, on purpose. That adapter belongs to the separate Azure AI
# Foundry integration; the M365 Agents SDK owns its own Activity plumbing, so the envelope is three
# lines on the reply Activity. Mixing the two would duplicate the host's plumbing.


@dataclass
class Envelope:
    governance: str = "ok"
    trace_id: str | None = None
    cost_usd: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    session_spent_usd: str | None = None
    session_cap_usd: str | None = None
    decisions: list[str] = field(default_factory=list)

    def as_channel_data(self) -> dict[str, Any]:
        return {"cendor": {k: v for k, v in self.__dict__.items() if v not in (None, "", [])}}


async def reply(context: TurnContext, text: str, envelope: Envelope) -> None:
    """Plain text plus the envelope — the whole of it.

    `channelData.cendor` is for the channel / your back end to consume. Whether a *client* surfaces
    it is client-specific: the M365 Agents Playground projects `channelData` away in its UI (it is
    still on the wire), so don't tell people to look for it there — assert it in a test, or log it.
    """
    activity = Activity(type=ActivityTypes.message, text=text)
    activity.channel_data = {**(activity.channel_data or {}), **envelope.as_channel_data()}
    await context.send_activity(activity)


# ═════════════════════════════════════════════════════════════════════ the agent


class GovernedAgent:
    """Startup singletons + the one governed handler."""

    def __init__(
        self, *, audit_path: str, storage: Any = None, session_cap_usd: Decimal | None = None
    ) -> None:
        self.client = make_client()
        self.input_gate, self.output_gate = input_gate(), output_gate()
        self.session_cap_usd = SESSION_CAP_USD if session_cap_usd is None else session_cap_usd
        self._ambient = install_turn_ambient()
        self.audit, self._interceptor = install_audit(audit_path)

        # The host, in anonymous local mode (see the README before deploying).
        auth = AgentAuthConfiguration(anonymous_allowed=True)
        cm = ConnectionManager(lambda _c: AnonymousTokenProvider(), {"SERVICE_CONNECTION": auth})
        store = storage or MemoryStorage()
        self.auth_config = auth
        self.app = AgentApplication[TurnState](
            storage=store,
            adapter=CloudAdapter(connection_manager=cm),
            authorization=Authorization(store, cm),
        )
        self._register()

    def close(self) -> None:
        """Undo the process-global installs. **A real server never calls this** — it lives forever.

        Tests do, because the ambient provider, the guard interceptor and the audit log are all
        process-global: without this, a second agent in one process stacks a second guard on
        every call, and re-opening the same chain path raises (two live writers, above).
        """
        from cendor.core import remove_ambient_provider, remove_interceptor

        self.audit.detach()
        remove_interceptor(self._interceptor)
        remove_ambient_provider(self._ambient)

    def _register(self) -> None:
        agent = self

        @agent.app.activity("message")
        async def on_message(context: TurnContext, state: TurnState) -> None:
            text = (context.activity.text or "").strip()
            streamed = text.startswith("/stream ")
            if streamed:
                text = text[len("/stream ") :]
            ledger = SpendLedger(state, cap_usd=agent.session_cap_usd)

            # (D) every bus event raised below carries this turn's identity and one trace id
            with turn_scope(context):
                # (C) the cheapest refusal there is: the cap is gone, so no model call happens
                if ledger.exhausted:
                    await reply(
                        context,
                        "This conversation has used its budget, so I didn't call the model.",
                        Envelope(
                            governance="session_cap_reached",
                            session_spent_usd=str(ledger.spent),
                            session_cap_usd=str(ledger.cap_usd),
                        ),
                    )
                    return

                gated_text, in_decisions = await gate(
                    agent.input_gate,
                    "input",
                    text,
                    conversation_id=context.activity.conversation.id,
                )
                if (hit := blocked(in_decisions)) is not None:
                    agent.audit.flag(
                        f"input blocked by {hit.guardrail}", action="blocked", severity="warning"
                    )
                    await reply(
                        context,
                        "I can't process that message.",
                        Envelope(
                            governance="input_blocked",
                            decisions=[f"{d.guardrail}:{d.action}" for d in in_decisions],
                            session_spent_usd=str(ledger.spent),
                        ),
                    )
                    return

                history: list[dict] = list(state.get_value(HISTORY_KEY, lambda: []) or [])
                assembly = assemble_prompt(history=history, user_text=str(gated_text))
                allowance = ledger.turn_allowance()

                # (A) is skipped on a streamed turn, on purpose. ⚠️ (A) and (E) are MUTUALLY
                # EXCLUSIVE: the estimate reserves the full `max_output_tokens`, so any allowance
                # small enough for the breaker to fire is already below the estimate — the
                # turn would be refused before a chunk exists. A stream's fuse IS the breaker.
                if not streamed:
                    affordable, _est = preflight(assembly.messages, allowance=allowance)
                    if not affordable:
                        await reply(
                            context,
                            "That request would exceed what's left of this conversation's budget.",
                            Envelope(
                                governance="preflight_refused",
                                session_spent_usd=str(ledger.spent),
                                session_cap_usd=str(ledger.cap_usd),
                            ),
                        )
                        return

                calls: list[LLMCall] = []
                unsub = bus.subscribe(lambda e: calls.append(e) if isinstance(e, LLMCall) else None)
                try:
                    with agent.audit.decision(input=str(gated_text)[:200]) as decision:
                        if streamed:
                            answer, broke = await agent._streamed_turn(
                                context, assembly.messages, allowance
                            )
                        else:
                            answer, broke = await agent._plain_turn(assembly.messages, allowance)
                        decision.record(model=MODEL, streamed=streamed)
                except PolicyViolation as violation:
                    # ⚠️ The THIRD exception type a governed handler must expect, alongside
                    # BudgetExceeded and GuardrailTripped: the acttrace `guard()` installed at
                    # startup raises from *inside* the provider call, at core's interceptor seam.
                    # Uncaught, the channel shows "the agent hit an error" instead of the refusal.
                    # Report categories, never the matched value.
                    categories = sorted({f.category for f in (violation.findings or [])})
                    await reply(
                        context,
                        "I can't send that to the model — our data policy blocked it"
                        + (f" ({', '.join(categories)})." if categories else "."),
                        Envelope(
                            governance="policy_blocked",
                            decisions=[f"acttrace:{c}" for c in categories],
                        ),
                    )
                    return
                finally:
                    bus.unsubscribe(unsub)

                cost = Money(
                    sum((c.cost.amount for c in calls if isinstance(c.cost, Money)), Decimal("0"))
                )
                usage_in = sum(int(getattr(c.usage, "input_tokens", 0) or 0) for c in calls)
                usage_out = sum(int(getattr(c.usage, "output_tokens", 0) or 0) for c in calls)

                safe_answer, out_decisions = await gate(
                    agent.output_gate,
                    "output",
                    answer,
                    conversation_id=context.activity.conversation.id,
                )
                out_hit = blocked(out_decisions)
                if out_hit is not None:
                    safe_answer = "I generated a response our output policy blocked."

                total = ledger.add(cost)  # (C) write the cap back into TurnState
                history += [
                    {"role": "user", "content": str(gated_text)},
                    {"role": "assistant", "content": str(safe_answer)},
                ]
                state.set_value(HISTORY_KEY, history[-20:])

                envelope = Envelope(
                    governance="broke_on_budget"
                    if broke
                    else ("output_blocked" if out_hit else "ok"),
                    trace_id=calls[-1].trace_id if calls else None,
                    cost_usd=str(cost.amount),
                    model=MODEL,
                    input_tokens=usage_in or None,
                    output_tokens=usage_out or None,
                    session_spent_usd=str(total),
                    session_cap_usd=str(ledger.cap_usd),
                    decisions=[f"{d.guardrail}:{d.action}" for d in in_decisions + out_decisions],
                )
                # A streamed turn already flushed its text, so the envelope rides a final activity.
                await reply(context, "" if streamed else str(safe_answer), envelope)

        # ⚠️ **A ports asymmetry that decides whether the cap above works at all.** On Python
        # (`microsoft-agents-hosting-core` 1.2.0) `AgentApplication.run()` awaits
        # `turn_state.save()` unconditionally, so nothing extra is needed here — verified in
        # `_run_after_turn_middleware`, which returns `True` when no handler is registered.
        # **The JavaScript port does NOT**: `@microsoft/agents-hosting` 1.7.1 saves only inside
        # `if (this._afterTurn.length > 0)`, and the official nodejs quickstart registers nothing —
        # so a JS agent's ledger reads $0 every turn and the cap silently never binds. The JS twin
        # of this recipe therefore carries `app.onTurn('afterTurn', async () => true)`.
        # If you want the Python belt-and-braces version, it is `@app.after_turn` taking
        # `(context, state) -> bool` (return `True`).

    # ------------------------------------------------------------------- the two turn shapes
    async def _create(self, *, cap: int, **kw: Any) -> Any:
        """One model call, with the output cap under whichever name this model accepts (see the
        `CAP_PARAM` trap note at the top).

        The retry costs nothing: the rejected call never reached the model, so there is no double
        spend, and the switch is remembered process-wide so it happens at most once.
        """
        global CAP_PARAM
        try:
            return await self.client.chat.completions.create(**kw, **{CAP_PARAM: cap})
        except Exception as exc:  # noqa: BLE001 — provider-agnostic on purpose (no openai import)
            other = "max_completion_tokens" if CAP_PARAM == "max_tokens" else "max_tokens"
            text = str(exc)
            if other not in text or "nsupported" not in text:
                raise
            CAP_PARAM = other
            return await self.client.chat.completions.create(**kw, **{CAP_PARAM: cap})

    async def _plain_turn(self, messages: list[dict], allowance: Decimal) -> tuple[str, bool]:
        try:
            with turn_budget(allowance, conversation_id="turn"):
                resp = await self._create(cap=MAX_OUTPUT_TOKENS, model=MODEL, messages=messages)
        except BudgetExceeded:
            return (
                "I stopped before calling the model — this turn's budget was already spent.",
                True,
            )
        return resp.choices[0].message.content or "", False

    async def _streamed_turn(
        self, context: TurnContext, messages: list[dict], allowance: Decimal
    ) -> tuple[str, bool]:
        """(E) provider stream → the channel's streamed reply, with the breaker in between.

        **Spend truth vs display truth.** Break stops token consumption at the chunk boundary. The
        channel keeps whatever it had already been sent — queued chunks cannot be unsent. Whether
        anything was already visible depends on the channel and on how long the answer ran; on a
        non-streaming channel the user simply sees the truncated answer plus the notice. Never claim
        the user-visible text is cut at the exact budget token.
        """
        stream = StreamingResponse(context)
        stream.queue_informative_update("Thinking…")
        collected: list[str] = []
        broke = False
        try:
            with turn_budget(
                allowance, conversation_id=context.activity.conversation.id, stream=True
            ):
                provider_stream = await self._create(
                    cap=512,
                    model=MODEL,
                    messages=messages,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                async for chunk in provider_stream:
                    # ⚠️ **A chunk can carry NO choices.** With `stream_options={"include_usage":
                    # True}` — which is how a streamed call reports real usage at all — OpenAI sends
                    # a FINAL chunk whose `choices` list is EMPTY, carrying only `usage`. Measured
                    # against openai-python 2.48.0: 9 chunks with include_usage, the 9th
                    # `choices=[]` + `usage` present; 8 chunks without it, none empty. A fake stream
                    # never emits that chunk, so `chunk.choices[0]` is green offline forever and
                    # `IndexError`s on the first real streamed turn. (The TypeScript twin reads
                    # `chunk.choices?.[0]?.delta?.content ?? ''`, which is why it never had this.)
                    if not chunk.choices:
                        continue
                    if piece := (chunk.choices[0].delta.content or ""):
                        collected.append(piece)
                        stream.queue_text_chunk(piece)
        except BudgetExceeded:
            broke = True
            stream.queue_text_chunk("\n\n_[stopped at the budget cap]_")
        finally:
            # ⚠️ On Python BOTH of these are coroutines. `end_stream()` un-awaited is a silent
            # RuntimeWarning and the last chunk never reaches the channel. (On TypeScript
            # `waitForQueue()` is private and `endStream()` drains the queue itself.)
            await stream.wait_for_queue()
            await stream.end_stream()
        return "".join(collected), broke


# ═════════════════════════════════════════════════════════════════════ the aiohttp host


def build_web_app(agent: GovernedAgent):
    """The quickstart's server: one POST route behind the JWT middleware."""
    from aiohttp.web import Application, Request, Response

    async def entry_point(req: Request) -> Response:
        return await start_agent_process(req, req.app["agent_app"], req.app["adapter"])

    app = Application(middlewares=[jwt_authorization_middleware])
    app.router.add_post("/api/messages", entry_point)
    app["agent_configuration"] = agent.auth_config
    app["agent_app"] = agent.app
    app["adapter"] = agent.app.adapter
    return app


def serve(agent: GovernedAgent, *, port: int = 3978) -> None:
    from aiohttp.web import run_app

    run_app(build_web_app(agent), host="localhost", port=port)
