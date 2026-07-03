# squeeze — shrink a huge blob before it eats your context window

**The pain.** A tool returns a 200 KB log dump. You need the model to reason over it, but pasting
it in blows the context window (and the bill). It's mostly repetition anyway — you just can't
throw it away, because you might need the original later.

**What this shows.** `compress(kind="auto", target_tokens=400)` detects the content is logs,
normalizes and de-duplicates it, and returns a compact string plus a reversible **handle**.
`handle.expand()` restores the original byte-for-byte. Sizes and token counts are measured, not
asserted.

## Run it

```bash
uv run python recipes/quickstarts/squeeze/main.py
```

## Expected output

```text
kind detected : logs  (technique: normalize+dedup)
tokens        : 82,999 -> 58  (target 400)
234.8 KB -> 0.2 KB (99.9% smaller) · expand(): byte-for-byte identical OK
```

You send ~58 tokens to the model instead of ~83,000, and can still recover every original byte on
demand. (squeeze trades storage for tokens — it shrinks what you *send*, while keeping the full
original for exact restore.)

Libraries: `core`, `squeeze` · Offline ✓ · [← all recipes](../../../README.md)
