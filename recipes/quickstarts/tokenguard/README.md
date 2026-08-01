# tokenguard — cap a runaway agent loop before it overspends

**The pain.** An agent loop with a bug (or an adversarial input) quietly calls the model over
and over. You find out when the invoice arrives. You wanted a hard ceiling, checked *before*
each call — not a post-mortem.

**What this shows.** `instrument()` wraps a fake OpenAI-shaped client; `@budget(usd=0.50,
on_exceed="block")` puts a **pre-flight** cap around the loop. Each turn is priced from the
offline snapshot at ~$0.09, so the 6th turn's projection crosses $0.50 and is refused *before it
reaches the model*. `report(group_by=["feature"])` then shows where the money went.

## Run it

```bash
uv run python recipes/quickstarts/tokenguard/main.py
```

## Expected output

```text
BudgetExceeded: pre-flight block: projected $0.539995000 would exceed cap $0.5 (model=gpt-4o)

Turns that actually ran, by feature:
  planner     3 calls   $0.270000000
  researcher  2 calls   $0.180000000
  TOTAL       5 calls   $0.450000000

(The 6th turn was blocked pre-flight - $0 spent on it; the model never saw it.)
```

Five turns ran ($0.45); the sixth was **blocked before the call** — `on_exceed="raise"` would
have let it complete and overshoot the cap. Every dollar figure comes from `prices.estimate`
on the stated token counts — no invented numbers.

## Run it as a notebook

[`notebook.ipynb`](notebook.ipynb) tells the same story a cell at a time — each step prints its own
output, the markdown carries the *why*, and the last cell asserts what `main.py` asserts. Offline
like everything else.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/quickstarts/tokenguard/notebook.ipynb
```

In a Codespace it is already runnable — the devcontainer installs the Jupyter extension, so just
open the file and **Run All**.

> The notebooks are **executed in CI** (`pytest --nbmake`, Python 3.11 and 3.13), so one that stops
> working turns the build red rather than quietly becoming a screenshot of code that used to run.


Libraries: `core`, `tokenguard` · Offline ✓ · [← all recipes](../../../README.md)
