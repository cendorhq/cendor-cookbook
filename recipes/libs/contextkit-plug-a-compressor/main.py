"""contextkit-plug-a-compressor — swap the compression backend without touching a call site.

contextkit does not know what `squeeze` is. When a block says `evict="compress"` it asks whatever
object matches core's `Compressor` **protocol**:

    compress(content, *, target_tokens, model) -> (compressed_text, handle)

`squeeze` is the default because it is deterministic and dependency-free. But your domain may
compress better than a general algorithm can: a support transcript is mostly boilerplate, a codebase
has a natural summary, an ML summarizer may beat any heuristic. Register yours once with
`use_compressor()` and every `evict="compress"` block in the process uses it — no call site changes.

This recipe plugs in a deliberately domain-specific compressor: it keeps only the lines that carry a
decision, and stores the original in a dict so the returned handle can `expand()` it back exactly.
That reversibility is the contract — contextkit surfaces the handle on the block's `BlockDecision`,
so a downstream step can recover what was dropped.

Then it swaps back to `squeeze` and compresses the same block, so you can compare the two.

Offline: pure assembly, no model call.

  uv run python recipes/libs/contextkit-plug-a-compressor/main.py
"""

import hashlib

from cendor.contextkit import Block, Context, use_compressor
from cendor.core import tokens
from cendor.squeeze import SqueezeCompressor

MODEL = "gpt-4o"
DECISION_WORDS = ("approved", "refunded", "escalated", "denied")


class DecisionsOnly:
    """A domain compressor: for a case log, only the decisions matter.

    Satisfies core's `Compressor` protocol by SHAPE — no base class, no import from contextkit. The
    handle is any object with `.expand()`; here a tiny closure over a content-addressed dict, which
    is exactly what squeeze does internally with its own store.
    """

    def __init__(self) -> None:
        self.originals: dict[str, str] = {}

    def compress(self, content, *, target_tokens=None, model=None, **_):
        text = content if isinstance(content, str) else str(content)
        key = hashlib.sha256(text.encode()).hexdigest()
        self.originals[key] = text
        kept = [ln for ln in text.splitlines() if any(w in ln for w in DECISION_WORDS)]
        small = "\n".join(kept) or text[:200]

        originals = self.originals

        class Handle:
            id = key
            technique = "decisions-only"

            def expand(self) -> str:
                return originals[key]

        return small, Handle()


def case_log(entries: int = 90) -> str:
    lines = []
    for i in range(entries):
        lines.append(f"[{i:03}] agent viewed the order and read the policy aloud to the customer")
        if i % 15 == 0:
            lines.append(f"[{i:03}] DECISION: refunded order-{7000 + i} under the 30-day rule")
    return "\n".join(lines)


def assemble_with(compressor, text: str):
    previous = use_compressor(compressor)
    try:
        ctx = (
            Context(budget_tokens=260, model=MODEL, reserve_output=0)
            .add(Block("Summarize the decisions.", role="system", pin=True, priority=100))
            .add(Block(text, role="user", priority=1, evict="compress"))
        )
        ctx.assemble()
        return next(d for d in ctx.report().decisions if d.action == "compressed")
    finally:
        use_compressor(previous)


def main() -> None:
    log = case_log()
    mine = assemble_with(DecisionsOnly(), log)
    theirs = assemble_with(SqueezeCompressor(), log)

    print(f"raw case log     : {tokens.count(log, MODEL):,} tokens, {len(log.splitlines())} lines")
    print(
        f"DecisionsOnly    : {mine.tokens_before} -> {mine.tokens_after} tok  "
        f"(technique {mine.handle.technique}, expand() exact: {mine.handle.expand() == log})"
    )
    print(
        f"squeeze (default): {theirs.tokens_before} -> {theirs.tokens_after} tok  "
        f"(technique {theirs.handle.technique}, expand() exact: {theirs.handle.expand() == log})"
    )
    print("both satisfy the same protocol - contextkit imported neither, and no call site changed")
    print("the handle is the contract: whatever you plug in must be able to give the original back")

    assert mine.handle.expand() == log, "the custom compressor's handle was not reversible"
    assert theirs.handle.expand() == log, "the squeeze handle was not reversible"
    assert mine.tokens_after < mine.tokens_before, "the custom compressor did not compress"


if __name__ == "__main__":
    main()
