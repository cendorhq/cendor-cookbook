# core — one wrap, and every LLM call lands on a normalized event bus

**The pain.** Every cost/testing/audit tool wants to monkey-patch your client. Stack three of
them and you have three patches fighting over the same method, each with its own idea of "a call".

**What this shows.** `cendor-core` patches the client **once**. `instrument()` wraps it in place
and emits a normalized `LLMCall` on a shared bus for every request — provider, model, usage, a
`Decimal` cost with an honest pricing label, and the token-counting method it would use. Every
other Cendor tool is just a subscriber.

## Run it

```bash
uv run python recipes/quickstarts/core/main.py
```

## Expected output

```text
LLMCall on the bus:
  provider : openai
  model    : gpt-4o
  usage    : 1200 in + 350 out = 1550 tokens
  cost     : $0.006500000 (cost_estimated)
  tokens   : counted via 'exact' for gpt-4o
```

The cost is priced offline from the bundled snapshot and labeled `cost_estimated` (a gateway that
reports real billed cost would show `cost_reported`). The token method is labeled honestly —
`exact` here because `tiktoken` is a required dependency of `cendor-core` (exact counts by default);
the `heuristic` tier is only a defensive fallback if `tiktoken` fails to import.

## Run it as a notebook

[`notebook.ipynb`](notebook.ipynb) tells the same story a cell at a time — each step prints its own
output, the markdown carries the *why*, and the last cell asserts what `main.py` asserts. Offline
like everything else.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/quickstarts/core/notebook.ipynb
```

In a Codespace it is already runnable — the devcontainer installs the Jupyter extension, so just
open the file and **Run All**.

> The notebooks are **executed in CI** (`pytest --nbmake`, Python 3.11 and 3.13), so one that stops
> working turns the build red rather than quietly becoming a screenshot of code that used to run.


Libraries: `core` · Offline ✓ · [← all recipes](../../../README.md)
