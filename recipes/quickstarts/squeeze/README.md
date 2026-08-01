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

## Run it as a notebook

[`notebook.ipynb`](notebook.ipynb) tells the same story a cell at a time — each step prints its own
output, the markdown carries the *why*, and the last cell asserts what `main.py` asserts. Offline
like everything else.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/quickstarts/squeeze/notebook.ipynb
```

In a Codespace it is already runnable — the devcontainer installs the Jupyter extension, so just
open the file and **Run All**.

> The notebooks are **executed in CI** (`pytest --nbmake`, Python 3.11 and 3.13), so one that stops
> working turns the build red rather than quietly becoming a screenshot of code that used to run.


Libraries: `core`, `squeeze` · Offline ✓ · [← all recipes](../../../README.md)
