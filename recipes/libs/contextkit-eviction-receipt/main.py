"""contextkit-eviction-receipt — read the receipt, not the vibes.

Everyone writes the same helper eventually: "if the prompt is too long, drop some history". Then a
bug report arrives — the model forgot the system rules, or the retrieved doc it needed is missing —
and there is nothing to look at. Which block went? Why that one?

contextkit makes the packing declarative and hands back a **receipt**. Each block declares:

  priority=  higher survives longer (the eviction order)
  pin=True   never evicted, at any budget (raises BudgetError if the pins alone don't fit)
  evict=     what to do when this block must shrink — drop_oldest / truncate / summarize / compress
  keep=      which end of a truncated block to keep, "head" or "tail"

and `report()` returns an `AssemblyReport`: the budget, the tokens actually used, the output
reserve, and a `BlockDecision` per block (`action`, `tokens_before`, `tokens_after`, `note`).

`whatif(n)` answers "what would a tighter budget cost me?" without committing — useful for choosing
a budget, and side-effect free (the committed report is untouched).

Offline: pure assembly, no model call.

  uv run python recipes/libs/contextkit-eviction-receipt/main.py
"""

from cendor.contextkit import Block, Context
from cendor.core import tokens

MODEL = "gpt-4o"

RULES = "You are a support agent. Never promise a refund without checking the policy."
POLICY = "Refund policy, section 4: " + "orders are refundable within 30 days of delivery. " * 60
RETRIEVED = "Knowledge base article 88: " + "the customer must return the item first. " * 120
HISTORY = [
    {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}: " + "chatter " * 14}
    for i in range(24)
]


def build(budget_tokens: int) -> Context:
    return (
        Context(budget_tokens=budget_tokens, model=MODEL, reserve_output=200)
        # Pinned: the rules are the reason the agent behaves at all. Never evict them.
        .add(Block(RULES, role="system", pin=True, priority=100))
        # High priority, but truncatable from the TAIL if it must shrink (the top of the policy
        # matters most).
        .add(Block(POLICY, role="system", priority=80, evict="truncate", keep="head"))
        # A retrieved doc: useful, but the first thing to go.
        .add(Block(RETRIEVED, role="user", priority=10, evict="truncate", keep="head"))
        # Conversation history: drop the oldest turns, keep the recent ones.
        .add(Block(messages=HISTORY, priority=50, evict="drop_oldest"))
    )


def main() -> None:
    ctx = build(1200)
    messages = ctx.assemble()
    receipt = ctx.report()

    raw = tokens.count(RULES + POLICY + RETRIEVED, MODEL) + tokens.count(HISTORY, MODEL)
    print(f"raw input        : {raw:,} tokens")
    print(
        f"budget           : {receipt.budget} tokens "
        f"({receipt.reserved_output} reserved for the answer)"
    )
    print(f"used             : {receipt.used} tokens in {len(messages)} messages")
    print("the receipt      :")
    for d in receipt.decisions:
        note = f"  # {d.note}" if d.note else ""
        print(
            f"  [{d.action:<10}] {d.role:<9} {d.tokens_before:>5} -> {d.tokens_after:<5} tok{note}"
        )

    # whatif(): price a tighter budget without committing to it.
    committed = receipt.used
    projections = [(b, ctx.whatif(b).used) for b in (1200, 800, 500, 300)]
    print("whatif()         : " + ", ".join(f"{b}->{u}" for b, u in projections))
    print(f"                   committed report untouched: {ctx.report().used == committed}")

    pinned = next(d for d in receipt.decisions if d.role == "system" and d.action == "kept")
    print(f"pinned block     : {pinned.action} at every budget - it is the reason the agent works")

    assert receipt.used <= receipt.budget - receipt.reserved_output, "the assembly overshot"
    assert any(d.action != "kept" for d in receipt.decisions), "nothing was evicted"
    assert all(projections[i][1] >= projections[i + 1][1] for i in range(len(projections) - 1)), (
        "whatif() used should not grow as the budget shrinks"
    )
    assert ctx.report().used == committed, "whatif() mutated the committed report"
    assert RULES in str(messages), "the pinned block was evicted"


if __name__ == "__main__":
    main()
