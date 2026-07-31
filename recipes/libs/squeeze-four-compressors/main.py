"""squeeze-four-compressors — the same 'compress this' means four different things.

A JSON payload, a log dump, a source file and a page of prose fail in different ways, so squeeze
runs a different technique per kind and picks one by sniffing the content (`kind="auto"`):

  json   minify + drop nulls        — whitespace and empty fields are pure overhead
  logs   normalize + dedup          — volatile fields blanked, then near-identical lines collapse
  code   strip comments/blank lines — structure is the signal, not the formatting
  prose  extractive                 — keep the sentences that carry the most new information

`fidelity` then chooses how hard to push: `lossless` (reversible transforms only), `balanced`, or
`aggressive`. Every result is reversible regardless — the original is kept in the content-addressed
store and `handle.expand()` returns it byte-for-byte.

The ratios below are measured on this recipe's own inputs, not quoted from anywhere. Run it and you
get the numbers for *your* content by swapping the samples.

Offline: pure compression, no model call.

  uv run python recipes/libs/squeeze-four-compressors/main.py
"""

import json

from cendor.core import tokens
from cendor.squeeze import compress, detect

MODEL = "gpt-4o"

SAMPLES = {
    "json": json.dumps(
        [
            {"id": i, "sku": f"SKU-{i:04}", "note": None, "qty": i % 7, "warehouse": "eu-west-1"}
            for i in range(120)
        ],
        indent=2,
    ),
    "logs": "\n".join(
        f"2026-07-31T09:{i % 60:02}:{i % 60:02}Z INFO worker-3 handled req id=req-{i} "
        f"status=200 latency_ms={10 + i % 4} route=/v1/orders"
        for i in range(400)
    ),
    "code": "\n".join(
        [
            "# The refund path. Historically this was three functions; it is one now.",
            "",
            "def refund(order_id: str, amount: Decimal) -> Receipt:",
            '    """Issue a refund and return the receipt."""',
            "    # Look the order up first — a refund against a missing order is a support ticket.",
            "    order = orders.get(order_id)",
            "",
            "    if order is None:",
            "        raise OrderNotFound(order_id)",
            "    # Partial refunds are allowed; over-refunds are not.",
            "    if amount > order.total:",
            "        raise TooMuch(amount, order.total)",
            "",
            "    return gateway.refund(order, amount)",
        ]
        * 12
    ),
    "prose": (
        "The refund policy is unchanged this quarter. Orders are refundable within thirty days "
        "of delivery, provided the item is returned in its original packaging. Digital goods are "
        "refundable only if unopened. The thirty-day window starts at delivery, not at purchase. "
        "Support agents may extend the window by seven days at their discretion. "
    )
    * 25,
}


def main() -> None:
    print(f"{'kind':<7} {'detect()':<8} {'fidelity':<10} {'tokens':<18} {'ratio':<7} technique")
    results = []
    for kind, content in SAMPLES.items():
        for fidelity in ("lossless", "balanced", "aggressive"):
            small, handle = compress(content, kind=kind, fidelity=fidelity, model=MODEL)
            before = tokens.count(content, MODEL)
            after = tokens.count(small, MODEL)
            exact = handle.expand() == content
            results.append((kind, fidelity, before, after, exact))
            print(
                f"{kind:<7} {detect(content):<8} {fidelity:<10} "
                f"{before:>6,} -> {after:>6,}  {after / before:>5.1%}   {handle.technique}"
            )

    auto, auto_handle = compress(SAMPLES["logs"], kind="auto", target_tokens=400, model=MODEL)
    print(
        f"\nauto    detected {detect(SAMPLES['logs'])}, target 400 -> "
        f"{tokens.count(auto, MODEL)} tokens ({auto_handle.technique})"
    )
    print("every row above is reversible: handle.expand() returned the original byte-for-byte")

    assert all(exact for *_, exact in results), "a compression was not reversible"
    assert all(after <= before for *_, before, after, _ in results), (
        "a 'compression' grew the input"
    )
    assert auto_handle.expand() == SAMPLES["logs"], (
        "the auto-detected compression was not reversible"
    )
    assert detect(SAMPLES["json"]) == "json" and detect(SAMPLES["logs"]) == "logs", (
        "detect() missed"
    )


if __name__ == "__main__":
    main()
