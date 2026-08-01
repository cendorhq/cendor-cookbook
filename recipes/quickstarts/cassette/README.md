# cassette — record an agent call once, replay it forever (offline, free)

**The pain.** Your agent tests hit a real model. They cost money, they're slow, and they flake
when the model's wording drifts. You want the same assertions to run offline, deterministically,
for free.

**What this shows.** `@cassette.use(path)` wraps an instrumented (fake) client. The first run
**records** the exchange to a JSON cassette; the second run **replays** it — the client is never
called. This file is both a runnable script and a pytest module.

## Run it

```bash
uv run python recipes/quickstarts/cassette/main.py
# or run it as a test:
uv run pytest recipes/quickstarts/cassette/main.py
```

## Expected output

```text
run 1: recorded (1 call, 12.9 ms)
run 2: replayed (0 calls, offline, 21.1 ms)
same assertion green: True == 'Refund issued.'
```

*(Timings vary run-to-run.)* Run 1 makes exactly one call and writes the cassette; run 2 makes
**zero** calls and returns the recorded response — same assertion, no network. In a real project
you commit the cassette so CI replays it. Regenerate with `mode="rerecord"` when the API changes;
`cassette.drift()` shows what moved.

## Run it as a notebook

[`notebook.ipynb`](notebook.ipynb) tells the same story a cell at a time — each step prints its own
output, the markdown carries the *why*, and the last cell asserts what `main.py` asserts. Offline
like everything else.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/quickstarts/cassette/notebook.ipynb
```

In a Codespace it is already runnable — the devcontainer installs the Jupyter extension, so just
open the file and **Run All**.

> The notebooks are **executed in CI** (`pytest --nbmake`, Python 3.11 and 3.13), so one that stops
> working turns the build red rather than quietly becoming a screenshot of code that used to run.


Libraries: `core`, `cassette` · Offline ✓ · [← all recipes](../../../README.md)
