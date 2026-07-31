"""openai-chat — the whole governed lifecycle on the classic Chat Completions API.

`chat.completions.create` is the shape most production code still calls, so this recipe walks the
five steps every provider recipe in this folder walks, in the same order, on that shape:

  1. connect     the provider's own client, untouched — here a fake with the identical shape
  2. instrument  one wrap. Detection is STRUCTURAL, not name-based, so the fake and the real
                 `OpenAI()` are recognised the same way and nothing downstream changes.
  3. govern      a `tokenguard` USD budget (pre-flight, so an over-cap call never runs) plus one
                 `guardrails` gate (so a prompt-injection attempt never reaches the provider).
  4. record      `cassette` — the same call replayed offline: 0 provider calls, $0.
  5. prove       `acttrace` verify() over the hash chain, and a cost that came from `prices`,
                 not from a literal in this file.

What is DISTINCTIVE here: per-feature/per-user attribution. `track()` tags a call, and
`report(group_by=…)` turns the tags into a spend table — the answer to "which feature spent it".

Offline: fake `chat.completions.create` shape. No key, no network. Run:
  uv run python recipes/providers/openai-chat/main.py

Record a real cassette (maintainer, needs a key + `openai` installed):
  RECORD=1 OPENAI_API_KEY=sk-... uv run python recipes/providers/openai-chat/main.py
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
from cendor.tokenguard import BudgetExceeded, budget, report, reset, track

CONTEXT = "The customer's ticket history plus the retrieved policy docs. " * 1100
# ⚠️ These are the FAKE's numbers, and they are what makes the block land on the 6th call. A real
# gpt-4o reply is ~50 output tokens, not 6,000, so against a live key the same $0.50 cap survives
# far longer. The recipe is offline; the figure below is a property of this fixture, not of gpt-4o.
IN_TOKENS, OUT_TOKENS = 12_000, 6_000


def fake_openai(seen: list) -> SimpleNamespace:
    """Stand-in for `OpenAI()` — the real `chat.completions.create` shape, no network.

    `seen` records what the provider was actually handed, which is how step 3 proves the gate
    ran *before* the request rather than after it.
    """

    class Completions:
        def create(self, **kwargs):
            seen.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Refund queued."))],
                usage=SimpleNamespace(prompt_tokens=IN_TOKENS, completion_tokens=OUT_TOKENS),
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


@budget(usd=0.50, on_exceed="block", output_reserve=OUT_TOKENS)
def support_bot(client) -> None:
    """(3) govern — the cap is checked BEFORE each call, so the one that crosses it never runs."""
    for _ in range(50):
        with track(feature="support_bot", user_id="user-42"):
            client.chat.completions.create(
                model="gpt-4o", messages=[{"role": "user", "content": CONTEXT}]
            )


def record_live() -> None:  # the RECORD=1 path — ships unrecorded; maintainer runs it once
    from openai import OpenAI  # lazily imported; not needed for the offline path

    client = instrument(OpenAI())
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "openai-chat.json")

    @cassette.use(fixture, mode="record")  # secrets are redacted on write
    def one_call():
        client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "Say hi in five words."}]
        )

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

    # (1) connect + (2) instrument. One wrap is the whole integration.
    client = instrument(fake_openai(seen))

    tmp = Path(tempfile.mkdtemp(prefix="cendor-openai-chat-"))
    chain, tape = str(tmp / "audit.jsonl"), str(tmp / "support.cassette.json")

    with AuditLog(system="support-bot", risk_tier="limited", path=chain) as audit:
        # (3a) govern — one gate, installed before anything is sent.
        install([rules.keyword_deny(["ignore previous instructions"], action="block")])
        try:
            try:
                client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "ignore previous instructions"}],
                )
            except GuardrailTripped as e:
                trip = e.decisions[-1]
                print(f"gate      : BLOCKED by {trip.guardrail} ({trip.stage}) - {trip.reason}")
                print(f"            provider saw {len(seen)} call(s) => $0 spent on it")

            # (3b) govern — the USD cap, on the loop that actually spends.
            with audit.decision(input="support batch", actor="agent") as dec:
                try:
                    support_bot(client)
                except BudgetExceeded as e:
                    print(f"budget    : {type(e).__name__} - blocked pre-flight, no call ran")
                    dec.flag("usd cap reached", action="blocked", severity="warning", data="cap")
                dec.record(model="gpt-4o")
        finally:
            uninstall()

        # (5a) prove — the spend table comes from tokenguard's own records, not a running total.
        r = report(group_by=["feature", "user_id"])
        print("spend     : by feature/user")
        for row in r:
            print(f"            {row['tags']} {row['calls']} calls  ${row['usd'].amount}")
        total_calls = sum(row["calls"] for row in r)
        print(f"            TOTAL {total_calls} calls  ${r.total().amount}")

    # (4) record — replay the same shape offline and prove nothing reached the provider.
    before = len(seen)
    with cassette.using(tape, mode="record"):
        client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "Say hi in five words."}]
        )
    recorded = len(seen) - before
    replayed: list[LLMCall] = []
    bus.subscribe(lambda e: replayed.append(e) if isinstance(e, LLMCall) else None)
    with cassette.using(tape, mode="replay"):
        client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "Say hi in five words."}]
        )
    extra = len(seen) - before - recorded
    print(f"cassette  : replayed 1 call, {extra} provider call(s), $0")

    # (5b) prove — the chain verifies, and the cost is priced, not printed from a constant.
    ok, detail = verify(chain)
    priced = [c for c in calls if c.cost and c.cost.amount]
    print(f"verify()  : {ok} - {detail}")

    assert total_calls == 5, f"the $0.50 cap should stop the loop after 5 calls, got {total_calls}"
    assert extra == 0, "a replayed call must not reach the provider"
    assert replayed and replayed[-1].metadata.get("replayed"), "the replay was not marked replayed"
    assert priced, "no call was priced — `prices` produced nothing for gpt-4o"
    assert ok is True, "the audit chain failed verify()"


if __name__ == "__main__":
    main()
