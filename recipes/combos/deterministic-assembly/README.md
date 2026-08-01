# deterministic-assembly — why a replay is worth anything at all

**The pain.** Your offline test suite passes. Is it actually offline? A cassette replays by hashing
the request, so if prompt assembly is not deterministic — eviction ties breaking on dict order, a
summarizer paraphrasing differently each run — run 2 hashes differently, the cassette misses, and
you are back to a live call. It fails *silently*: nothing says "this test just made a real request".

**What this shows.** `contextkit`'s packing is deterministic by construction, measured rather than
claimed. The same 40-turn conversation is built and assembled twice into a budget too small to hold
it (so real eviction happens — the hard case, where a non-deterministic packer would diverge), both
assembled prompts are hashed, then a cassette recorded from run 1 is replayed against **run 2's**
prompt with a client that raises if it is ever reached.

The negative control is in the output: change one character of the input and the fingerprint changes.

## Run it

```bash
uv run python recipes/combos/deterministic-assembly/main.py
```

## Expected output

```text
assembled   : 284 tokens of 400 - history: kept 13 of 40 turns
run 1 hash  : 718e0b34d6966202…
run 2 hash  : 718e0b34d6966202…   identical: True
one char    : 4ad87780e879e472…   identical: False
replay      : provider called 0x, answered 'acknowledged'
```

27 of 40 turns were evicted and the two runs still hash identically — that is the property. `one
char` is the control: a fingerprint that never changed would prove nothing, so the recipe appends a
single `.` to the last message and asserts the hash moves.

This is the foundation under [`record-a-governed-run`](../record-a-governed-run/) and under
[`testing/pytest-cassette`](../../testing/pytest-cassette/): a recorded test suite is only
trustworthy if the thing being hashed is stable.

## Run it as a notebook

[`notebook.ipynb`](notebook.ipynb) tells the same story a cell at a time — each step prints its own
output, the markdown carries the *why*, and the last cell asserts what `main.py` asserts. Offline
like everything else.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/combos/deterministic-assembly/notebook.ipynb
```

In a Codespace it is already runnable — the devcontainer installs the Jupyter extension, so just
open the file and **Run All**.

> The notebooks are **executed in CI** (`pytest --nbmake`, Python 3.11 and 3.13), so one that stops
> working turns the build red rather than quietly becoming a screenshot of code that used to run.


Libraries: `core`, `contextkit`, `cassette` · Offline ✓ · [← all recipes](../../../README.md)
