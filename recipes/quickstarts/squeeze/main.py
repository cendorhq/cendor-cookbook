"""squeeze quickstart — shrink a huge blob before it eats your context window.

A verbose log dump is mostly repetition. squeeze compresses it toward a token target and
hands back a reversible handle, so you can send 400 tokens to the model and still restore the
original byte-for-byte when you need it.

Offline: pure compression, no model call. Run:
  uv run python recipes/quickstarts/squeeze/main.py
"""

from cendor.core import tokens
from cendor.squeeze import compress

MODEL = "gpt-4o"


def noisy_logs(lines: int = 1500) -> str:
    """Repetitive application logs — the kind that balloon a prompt for no real signal."""
    out = []
    for i in range(lines):
        out.append(
            f"2026-07-03T10:{i % 60:02d}:{i % 60:02d}Z INFO  worker-7 "
            f"handled request id=req-{i} status=200 latency_ms=12 route=/v1/refunds "
            f"user=svc-billing region=us-east-1 cache=hit retries=0"
        )
    return "\n".join(out)


def main() -> None:
    logs = noisy_logs()

    small, handle = compress(logs, kind="auto", target_tokens=400)

    before_kb, after_kb = len(logs) / 1024, len(small) / 1024
    before_tok = tokens.count(logs, MODEL)
    after_tok = tokens.count(small, MODEL)
    pct = 100 * (1 - len(small) / len(logs))

    restored = handle.expand()
    identical = restored == logs

    print(f"kind detected : {handle.kind}  (technique: {handle.technique})")
    print(f"tokens        : {before_tok:,} -> {after_tok:,}  (target 400)")
    print(
        f"{before_kb:.1f} KB -> {after_kb:.1f} KB ({pct:.1f}% smaller) · "
        f"expand(): byte-for-byte identical {'OK' if identical else 'FAIL'}"
    )

    assert identical, "expand() must restore the original exactly"
    assert after_tok <= 400, "compressed output must respect the token target"


if __name__ == "__main__":
    main()
