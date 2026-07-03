"""tokenguard quickstart — stop a runaway agent loop *before* it overspends.

Offline: the "OpenAI" client is a fake provider-shaped object. No key, no network.
Run:  uv run python recipes/quickstarts/tokenguard/main.py
"""

from types import SimpleNamespace

from cendor.core import instrument
from cendor.tokenguard import BudgetExceeded, budget, report, reset, track

# Each simulated turn sends ~12k input tokens and reserves 6k output on gpt-4o. tokenguard
# prices that from the offline snapshot at ~$0.09/turn — so a $0.50 cap is crossed on the
# 6th turn. With on_exceed="block", the projection is checked BEFORE the call, so the 6th
# turn is refused and never reaches the model.
CONTEXT = "The support ticket thread and the product knowledge-base docs. " * 1090
IN_TOKENS, OUT_TOKENS = 12_000, 6_000


def fake_openai():
    """A stand-in for `OpenAI()` — same `chat.completions.create` shape, no network."""

    class Completions:
        def create(self, **kwargs):
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=IN_TOKENS, completion_tokens=OUT_TOKENS)
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


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
    client = instrument(fake_openai())

    try:
        run_agent_loop(client)
    except BudgetExceeded as e:
        print(f"{type(e).__name__}: {e}\n")

    r = report(group_by=["feature"])
    print("Turns that actually ran, by feature:")
    for row in sorted(r, key=lambda x: x["tags"].get("feature", "")):
        print(f"  {row['tags']['feature']:<11} {row['calls']} calls   ${row['usd'].amount}")
    print(f"  {'TOTAL':<11} {sum(row['calls'] for row in r)} calls   ${r.total().amount}")
    print("\n(The 6th turn was blocked pre-flight - $0 spent on it; the model never saw it.)")


if __name__ == "__main__":
    main()
