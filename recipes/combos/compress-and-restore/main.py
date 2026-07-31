"""compress-and-restore — an eviction you can audit AND undo.

Dropping the oldest turns to fit a budget loses information you may need later, and leaves no
record of what went. `evict="compress"` instead routes the block through core's `Compressor`
**protocol** to whatever backend you registered — here `squeeze` — which returns a reversible
handle. squeeze then emits a metadata-only `CompressionEvent` on core's bus, and any attached
`acttrace` chain records it as a `compression` entry: technique, tokens before/after, handle id.

The point of the metadata-only rule: the audit file says a compression happened and by how much,
and **never contains the text**. So the chain is safe to keep even when the content is not.

Nothing imports anything: contextkit asks the protocol, squeeze satisfies it, acttrace duck-types
the event off the bus. Offline — pure compression, no model call.

  uv run python recipes/combos/compress-and-restore/main.py
"""

import tempfile
from pathlib import Path

from cendor.acttrace import AuditLog, verify
from cendor.contextkit import Block, Context, use_compressor
from cendor.core import tokens
from cendor.squeeze import SqueezeCompressor, decompress

MODEL = "gpt-4o"
SECRET = "case-notes: patient 55213, diagnosis withheld"


def transcript(turns: int = 60) -> str:
    """A long support transcript — the kind you must keep, but cannot afford to send."""
    lines = [f"{SECRET}. Ticket opened by the duty nurse."]
    for i in range(turns):
        lines.append(
            f"turn {i}: agent asked for the order id; customer replied with order-{4000 + i}; "
            f"agent confirmed the refund window is open and repeated the policy verbatim."
        )
    return "\n".join(lines)


def main() -> None:
    content = transcript()
    tmp = Path(tempfile.mkdtemp(prefix="cendor-recipe-"))
    chain = tmp / "compression-audit.jsonl"

    previous = use_compressor(SqueezeCompressor())
    audit = AuditLog(system="case-notes", risk_tier="high", path=str(chain))
    try:
        ctx = (
            Context(budget_tokens=300, model=MODEL, reserve_output=0)
            .add(Block("Summarize the case.", role="system", pin=True, priority=100))
            .add(Block(content, role="user", priority=1, evict="compress"))
        )
        ctx.assemble()
        decision = next(d for d in ctx.report().decisions if d.action == "compressed")
    finally:
        audit.detach()
        use_compressor(previous)

    entry = next(e for e in audit.entries if e.type == "compression")
    payload = entry.payload
    restored = decompress(decision.handle)  # identical to decision.handle.expand()
    ok, detail = verify(str(chain))

    print(f"original         : {tokens.count(content, MODEL):,} tokens")
    print(
        f"after compress   : {payload['tokens_after']:,} tokens  "
        f"({payload['technique']}, ratio {payload['ratio']:.3f})"
    )
    print(f"audit entry      : type={entry.type} handle_id={payload['handle_id'][:12]}…")
    print(
        f"leaked content   : {any(SECRET in str(v) for v in payload.values())}  "
        f"(metadata only — the chain never holds the text)"
    )
    print(f"decompress()     : byte-for-byte identical {restored == content}")
    print(f"verify()         : {ok} — {detail}")

    assert restored == content, "decompress() must restore the original exactly"
    assert not any(SECRET in str(v) for v in payload.values()), "the audit entry leaked raw content"
    assert payload["tokens_after"] < payload["tokens_before"], "nothing was actually compressed"
    assert ok is True, "the compression audit chain failed verify()"


if __name__ == "__main__":
    main()
