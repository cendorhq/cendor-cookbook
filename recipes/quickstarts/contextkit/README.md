# contextkit — fit a prompt to budget without dropping the wrong things

**The pain.** Your prompt is over the context window, so something has to go. Naive truncation
chops the tail — often your pinned instructions or the user's actual question. You want to keep
what matters and shed what doesn't, and know exactly what happened.

**What this shows.** Four blocks — a pinned system prompt, a big retrieved-docs blob
(`evict="truncate"`), a long chat history (`evict="drop_oldest"`), and the pinned user message —
assembled into an 8000-token budget with 500 reserved for output. `report()` prints a receipt of
what was kept, shrunk, and dropped. Same inputs → byte-identical output.

## Run it

```bash
uv run python recipes/quickstarts/contextkit/main.py
```

## Expected output

```text
AssemblyReport(model=gpt-4o, order=default) budget=8000 reserved_output=500 used=7499/7500
  [kept      ] system    14->14tok
  [kept      ] user      16->16tok
  [truncated ] user      9004->7454tok
  [dropped   ] history   5000->0tok  # history: dropped all 40 turns (no room)

used 7499 <= budget 7500 (after 500-tok output reserve)  OK
same inputs -> identical output: True
```

The pinned system prompt and user question are never at risk; the docs are shrunk to fit; the
low-priority chat history is dropped entirely because the docs were more important. The receipt
tells you precisely what the model did and didn't see — and assembly is deterministic, so the
same inputs always produce the same prompt.

## Run it as a notebook

[`notebook.ipynb`](notebook.ipynb) tells the same story a cell at a time — each step prints its own
output, the markdown carries the *why*, and the last cell asserts what `main.py` asserts. Offline
like everything else.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/quickstarts/contextkit/notebook.ipynb
```

In a Codespace it is already runnable — the devcontainer installs the Jupyter extension, so just
open the file and **Run All**.

> The notebooks are **executed in CI** (`pytest --nbmake`, Python 3.11 and 3.13), so one that stops
> working turns the build red rather than quietly becoming a screenshot of code that used to run.


Libraries: `core`, `contextkit` · Offline ✓ · [← all recipes](../../../README.md)
