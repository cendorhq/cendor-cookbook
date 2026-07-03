"""openai-chat — cost controls for the classic Chat Completions API.

Same story as the tokenguard quickstart, but on the `chat.completions.create` shape you
actually call in production. Wrap the client once; budgeting, attribution, auditing, and
record/replay all ride the same `instrument()` seam — no other code changes.

Offline: fake `chat.completions.create` shape. Run:
  uv run python recipes/providers/openai-chat/main.py

Record a real cassette (maintainer, needs a key + `openai` installed):
  RECORD=1 OPENAI_API_KEY=sk-... uv run python recipes/providers/openai-chat/main.py
"""

import os
from types import SimpleNamespace

from cendor.core import instrument
from cendor.tokenguard import BudgetExceeded, budget, report, reset, track

CONTEXT = "The customer's ticket history plus the retrieved policy docs. " * 1100
IN_TOKENS, OUT_TOKENS = 12_000, 6_000


def fake_openai():
    """Stand-in for `OpenAI()` — the real `chat.completions.create` shape, no network."""

    class Completions:
        def create(self, **kwargs):
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=IN_TOKENS, completion_tokens=OUT_TOKENS)
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


@budget(usd=0.50, on_exceed="block", output_reserve=OUT_TOKENS)
def support_bot(client) -> None:
    for _ in range(50):
        with track(feature="support_bot", user_id="user-42"):
            client.chat.completions.create(
                model="gpt-4o", messages=[{"role": "user", "content": CONTEXT}]
            )


def record_live() -> None:  # the RECORD=1 path — ships unrecorded; maintainer runs it once
    from cendor import cassette
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
    client = instrument(fake_openai())
    try:
        support_bot(client)
    except BudgetExceeded as e:
        print(f"{type(e).__name__}: {e}\n")

    r = report(group_by=["feature", "user_id"])
    print("Spend by feature/user:")
    for row in r:
        print(f"  {row['tags']} {row['calls']} calls  ${row['usd'].amount}")
    print(f"  TOTAL  {sum(row['calls'] for row in r)} calls  ${r.total().amount}")


if __name__ == "__main__":
    main()
