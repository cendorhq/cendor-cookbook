"""openai-responses — the governed lifecycle on the Responses API, where usage looks different.

Same five steps as every recipe in `providers/`, on `responses.create`:

  1. connect     `OpenAI()` — the Responses shape, faked here with identical fields
  2. instrument  one wrap; the seam recognises the client by SHAPE, so nothing below changes
  3. govern      a `tokenguard` USD budget + one `guardrails` gate
  4. record      `cassette` replay — 0 provider calls, $0
  5. prove       `acttrace` verify() + a cost that came from `prices`

What is DISTINCTIVE here: **reasoning and cached tokens**. New OpenAI apps (and the Agents SDK)
call `responses.create`, which reports `input_tokens`/`output_tokens` with cached tokens under
`input_tokens_details.cached_tokens` and reasoning under `output_tokens_details.reasoning_tokens`.
Those are billed, at different rates, and a naive prompt+completion sum misses both.
`instrument()` normalizes them into `usage.cached_tokens` / `usage.reasoning_tokens`, so the cost
matches the invoice rather than the intuition.

Offline: fake `responses.create` shape. No key, no network. Run:
  uv run python recipes/providers/openai-responses/main.py

Record a real cassette (maintainer, needs a key + `openai` installed):
  RECORD=1 OPENAI_API_KEY=sk-... uv run python recipes/providers/openai-responses/main.py
"""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor import cassette
from cendor.acttrace import AuditLog, verify
from cendor.core import bus, instrument
from cendor.core.types import LLMCall
from cendor.guardrails import GuardrailTripped, install, rules, uninstall
from cendor.tokenguard import BudgetExceeded, budget, reset

MODEL = "gpt-4o"


def fake_openai_responses(seen: list) -> SimpleNamespace:
    """Stand-in for `OpenAI()` — the Responses API shape with reasoning + cached details.

    620 of the 850 output tokens are reasoning, and 200 of the 1,204 input tokens are cache reads.
    Both are real billing categories; the point of the fake is that they are *present*, not that
    the numbers are typical.
    """

    class Responses:
        def create(self, **kwargs):
            seen.append(kwargs)
            return SimpleNamespace(
                output_text="Summarised.",
                usage=SimpleNamespace(
                    input_tokens=1204,
                    output_tokens=850,
                    input_tokens_details=SimpleNamespace(cached_tokens=200),
                    output_tokens_details=SimpleNamespace(reasoning_tokens=620),
                ),
            )

    return SimpleNamespace(responses=Responses())


def record_live() -> None:  # RECORD=1 path — ships unrecorded
    from openai import OpenAI

    client = instrument(OpenAI())
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "openai-responses.json")

    @cassette.use(fixture, mode="record")
    def one_call():
        client.responses.create(model=MODEL, input="Reason briefly, then greet me.")

    one_call()
    print(f"recorded live call to {fixture}")


def main() -> None:
    if os.environ.get("RECORD") == "1":
        record_live()
        return

    reset()
    seen: list = []
    calls: list[LLMCall] = []
    bus.subscribe(lambda e: calls.append(e) if isinstance(e, LLMCall) else None)

    # (1) connect + (2) instrument
    client = instrument(fake_openai_responses(seen))

    tmp = Path(tempfile.mkdtemp(prefix="cendor-openai-responses-"))
    chain, tape = str(tmp / "audit.jsonl"), str(tmp / "answer.cassette.json")

    with AuditLog(system="reasoner", risk_tier="limited", path=chain) as audit:
        # (3a) govern — the gate runs on the *input*, so a refusal costs nothing.
        install([rules.regex_rule(r"\bsk-[A-Za-z0-9]{16,}\b", action="block", stage="input")])
        blocked = ""
        try:
            try:
                client.responses.create(model=MODEL, input="my key is sk-ABCD1234EFGH5678")
            except GuardrailTripped as e:
                blocked = e.decisions[-1].guardrail
                print(f"gate     : BLOCKED by {blocked} - provider saw {len(seen)} call(s), $0")

            # (3b) govern + the real turn.
            with audit.decision(input="summarise the thread", actor="agent") as dec:
                with budget(usd=0.50, on_exceed="block"):
                    client.responses.create(model=MODEL, input="Summarize, then reason.")
                dec.record(model=MODEL)

            # A cap smaller than one call's projection: refused before the request is built.
            refused = ""
            try:
                with budget(usd=0.000_01, on_exceed="block"):
                    client.responses.create(model=MODEL, input="And this one?")
            except BudgetExceeded as e:
                refused = str(e).splitlines()[0]
        finally:
            uninstall()

    call = calls[0]
    u = call.usage
    label = "cost_reported" if call.metadata.get("cost_reported") else "cost_estimated"
    print(
        f"usage    : {u.input_tokens:,} in ({u.cached_tokens} cached) -> "
        f"{u.output_tokens:,} out ({u.reasoning_tokens} reasoning)"
    )
    print(f"cost     : ${call.cost.amount} ({label}) - reasoning + cached are IN this number")
    print(f"refused  : {refused}")

    # (4) record — the same call replayed offline.
    before = len(seen)
    with cassette.using(tape, mode="record"):
        client.responses.create(model=MODEL, input="Say hi.")
    recorded = len(seen) - before
    with cassette.using(tape, mode="replay"):
        client.responses.create(model=MODEL, input="Say hi.")
    extra = len(seen) - before - recorded
    print(f"cassette : replayed 1 call, {extra} provider call(s), $0")

    # (5) prove
    ok, detail = verify(chain)
    print(f"verify() : {ok} - {detail}")

    assert u.reasoning_tokens == 620, "reasoning tokens were not normalized out of the details"
    assert u.cached_tokens == 200, "cached tokens were not normalized out of the details"
    assert call.cost and call.cost.amount > 0, "the Responses call was not priced"
    assert blocked, "the input gate did not fire on a leaked key"
    assert refused, "the tiny cap did not refuse the third call pre-flight"
    assert extra == 0, "a replayed call must not reach the provider"
    assert ok is True, "the audit chain failed verify()"


if __name__ == "__main__":
    main()
