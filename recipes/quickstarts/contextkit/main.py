"""contextkit quickstart — fit a prompt to a token budget without dropping the wrong things.

Naive truncation lops off the end of your prompt — often the pinned instructions or the
user's actual question. contextkit assembles blocks by priority, shrinks what it's allowed
to, drops what it must, and hands back a receipt. Same inputs -> identical output.

Offline: pure token math, no model call. Run:
  uv run python recipes/quickstarts/contextkit/main.py
"""

from cendor.contextkit import Block, Context

SYSTEM_PROMPT = "You are a meticulous support agent. Cite the policy for every answer."
USER_MSG = "I was charged twice for order #8823 — can you refund the duplicate?"

# A big retrieved-docs blob and a long chat history — together they blow the budget, so
# contextkit must shrink the docs (truncate) and peel the oldest chat turns (drop_oldest).
DOCS = "Refund policy. " + ("Duplicate charges are refunded within 5 business days. " * 900)
_TURN = "discussing the refund timeline and the duplicate-charge policy. "
HISTORY = [
    {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}: {_TURN * 12}"}
    for i in range(40)
]


def build() -> Context:
    ctx = Context(budget_tokens=8000, model="gpt-4o", reserve_output=500)
    ctx.add(Block(SYSTEM_PROMPT, priority=10, pin=True, role="system"))  # never dropped
    ctx.add(Block(DOCS, priority=5, evict="truncate", role="user"))  # shrink to fit
    ctx.add(Block(messages=HISTORY, priority=3, evict="drop_oldest"))  # peel oldest turns
    ctx.add(Block(USER_MSG, priority=9, pin=True, role="user"))  # never dropped
    ctx.assemble()
    return ctx


def main() -> None:
    ctx = build()
    report = ctx.report()

    print(report)  # the receipt: kept / truncated / dropped per block
    print()
    ok = report.used <= (report.budget - report.reserved_output)
    print(
        f"used {report.used} <= budget {report.budget - report.reserved_output} "
        f"(after {report.reserved_output}-tok output reserve)  {'OK' if ok else 'OVER'}"
    )

    # Determinism: identical inputs -> byte-identical assembled messages.
    identical = build().assemble() == build().assemble()
    print(f"same inputs -> identical output: {identical}")

    assert ok, "assembled prompt must fit the budget"
    assert identical, "assembly must be deterministic"


if __name__ == "__main__":
    main()
