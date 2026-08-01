"""tokenguard quickstart — stop a runaway agent loop *before* it overspends.

Offline: the "OpenAI" client is a fake provider-shaped object. No key, no network.
Run:  uv run python recipes/quickstarts/tokenguard/main.py

Against a real provider — SIZED DIFFERENTLY ON PURPOSE, see LIVE_* below:
  LIVE=1 OPENAI_API_KEY=sk-... uv run --group apps python recipes/quickstarts/tokenguard/main.py
"""

import os
from types import SimpleNamespace

from cendor.core import instrument
from cendor.tokenguard import BudgetExceeded, budget, report, reset, track

# Each simulated turn sends ~12k input tokens and reserves 6k output on gpt-4o. tokenguard
# prices that from the offline snapshot at ~$0.09/turn — so a $0.50 cap is crossed on the
# 6th turn. With on_exceed="block", the projection is checked BEFORE the call, so the 6th
# turn is refused and never reaches the model.
#
# ⚠️ THE "6th TURN" IS A PROPERTY OF THIS FAKE, NOT OF A REAL PROVIDER. `OUT_TOKENS = 6_000` is
# what the fake *reports as settled usage*, and tokenguard bills what settles. A real model asked
# this question answers in 30–60 tokens, so real spend is ~$0.016/turn, not $0.09 — the cap is then
# crossed around the **27th** turn, and this 50-iteration loop makes ~27 twelve-thousand-token
# gpt-4o calls (~$0.41, and enough per-minute tokens to trip a default rate limit) before it stops.
# Measured live 2026-07-31. Nothing is wrong with tokenguard here: `output_reserve` governs the
# pre-flight *projection*, settled usage governs the *record*, and the two are meant to differ.
# If you point this at a real client, set the cap from a measured per-turn cost rather than reusing
# $0.50, or keep `output_reserve` and read the block as "projected", not "spent".
CONTEXT = "The support ticket thread and the product knowledge-base docs. " * 1090
IN_TOKENS, OUT_TOKENS = 12_000, 6_000

LIVE = bool(os.environ.get("LIVE"))
# ⚠️ THE LIVE PATH IS SIZED SEPARATELY, AND HAS TO BE. Everything above is calibrated against the
# fake's canned usage. Swap in a real client and change nothing else and this recipe blocks around
# the 27th turn after ~27 twelve-thousand-token gpt-4o calls — roughly $0.41, and enough tokens per
# minute to trip a default rate limit. That is not a cheaper version of the demo; it is a different
# demo that also costs money.
#
# So live keeps the SHAPE — a loop, a cap, a pre-flight block a handful of turns in — at a size a
# real provider actually produces. Measured 2026-07-31: ~$0.016/turn on gpt-4o with a 12k prompt;
# `gpt-4o-mini` with a short prompt and a 32-token ceiling is ~$0.00002/turn, so the cap below is
# set from THAT, not from $0.50.
LIVE_MODEL = os.environ.get("LIVE_MODEL", "gpt-4o-mini")
LIVE_CONTEXT = "Summarise the support thread. " * 40  # ~250 tokens, not 12,000
LIVE_MAX_OUTPUT = 32
LIVE_TURNS = 8  # a loop you can watch, not 50
# ⚠️ Measured, not guessed — and the first attempt was wrong. One live turn of the above PROJECTS
# $0.0000624 on gpt-4o-mini (250-ish input + the full 32-token output reservation), so a $0.00006
# cap refused turn ONE and the loop never started: "0/8 ran". A cap has to clear a single turn's
# projection before it can be crossed by several. $0.00022 lets three through and blocks the fourth.
LIVE_CAP_USD = 0.00022


def fake_openai():
    """A stand-in for `OpenAI()` — same `chat.completions.create` shape, no network."""

    class Completions:
        def create(self, **kwargs):
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=IN_TOKENS, completion_tokens=OUT_TOKENS)
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def make_client():
    """The fake, or the real thing. The only line that knows which."""
    if LIVE:
        from openai import OpenAI  # lazy: the offline path needs no provider SDK

        return instrument(OpenAI())
    return instrument(fake_openai())


def run_agent_loop_live(client) -> None:
    """The same loop, sized for a provider that answers in tens of tokens rather than thousands."""
    for i in range(LIVE_TURNS):
        feature = "planner" if i % 2 == 0 else "researcher"
        with track(feature=feature):
            client.chat.completions.create(
                model=LIVE_MODEL,
                messages=[{"role": "user", "content": LIVE_CONTEXT}],
                max_tokens=LIVE_MAX_OUTPUT,
            )


@budget(usd=0.50, on_exceed="block", output_reserve=OUT_TOKENS)
def run_agent_loop(client) -> None:
    for i in range(50):  # a loop that would happily run forever
        feature = "planner" if i % 2 == 0 else "researcher"
        with track(feature=feature):
            client.chat.completions.create(
                model="gpt-4o", messages=[{"role": "user", "content": CONTEXT}]
            )


def main() -> None:
    reset()
    client = make_client()

    try:
        if LIVE:
            # The cap is applied here rather than as a decorator so the live sizing is visible at
            # the call site next to the numbers it depends on.
            with budget(usd=LIVE_CAP_USD, on_exceed="block", output_reserve=LIVE_MAX_OUTPUT):
                run_agent_loop_live(client)
        else:
            run_agent_loop(client)
    except BudgetExceeded as e:
        print(f"{type(e).__name__}: {e}\n")

    r = report(group_by=["feature"])
    print("Turns that actually ran, by feature:")
    for row in sorted(r, key=lambda x: x["tags"].get("feature", "")):
        print(f"  {row['tags']['feature']:<11} {row['calls']} calls   ${row['usd'].amount}")
    print(f"  {'TOTAL':<11} {sum(row['calls'] for row in r)} calls   ${r.total().amount}")
    print("\n(The 6th turn was blocked pre-flight - $0 spent on it; the model never saw it.)")

    # Prove it rather than print it. `ran` is what tokenguard recorded, so if the pre-flight block
    # ever stopped working this line fails instead of the paragraph above quietly becoming false.
    ran = sum(row["calls"] for row in r)
    if LIVE:
        # Live, the exact turn depends on how long the model's answers happen to be, so assert the
        # SHAPE — some turns ran, the loop did not finish, and the cap is what stopped it.
        assert 0 < ran < LIVE_TURNS, f"the cap should stop the loop partway; {ran}/{LIVE_TURNS} ran"
        print(f"(LIVE: {ran} of {LIVE_TURNS} turns ran on {LIVE_MODEL} before the cap blocked one)")
    else:
        assert ran == 5, f"the $0.50 cap should let 5 turns through and block the 6th, got {ran}"
    assert r.total().amount > 0, "no spend was recorded at all"


if __name__ == "__main__":
    main()
