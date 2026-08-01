# record-a-governed-run — record the governed triad once, re-run it forever for $0

**The pain.** The usual objection to testing governance is the bill: if every CI run makes real
calls to prove your budget blocks and your audit chain verifies, you pay to prove it — every push,
every branch, every retry. So the governance tests get skipped, and the one thing you needed to be
sure about is the thing nobody checks.

**What this shows.** Record a run that is budgeted (`tokenguard`) and audited (`acttrace`) into a
`cassette`. On replay the provider is **never reached** — yet the same budget accrues the recorded
usage, the same audit chain is written, and `verify()` still returns `True`.

The `$0` claim is *proven*, not asserted: the replay pass is handed a client that raises
`AssertionError` if it is called at all. If the replay ever reached the provider, this recipe
crashes instead of printing.

## Run it

```bash
uv run python recipes/combos/record-a-governed-run/main.py
```

## Expected output

```text
record  : provider called 1x · 960 tok · $0.003450000
replay  : provider called 0x · 960 tok · $0.003450000
          ^ the same tokens are accounted, with $0 of REAL spend
answer  : 'three fixes, one feature'
audited : 1 llm_call entry chained on the replay
verify(): True — ok: 3 entries, head dae721b4a462…
cassette: 814 bytes on disk — commit it and CI runs free
```

Read the two spend rows together. They are identical because tokenguard accounts the *recorded*
usage on replay — the accounting stays honest, so a test can still assert "this feature costs under
$X" — while `provider called 0x` is the part your invoice sees. Commit the 814-byte cassette and
that assertion runs free forever.

Both passes are wrapped in `track(feature=…)`, which is why `report(group_by=["feature"])` can tell
them apart. In a real suite you would use one tag per test.

## Run it as a notebook

[`notebook.ipynb`](notebook.ipynb) tells the same story a cell at a time — each step prints its own
output, the markdown carries the *why*, and the last cell asserts what `main.py` asserts. Offline
like everything else.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/combos/record-a-governed-run/notebook.ipynb
```

In a Codespace it is already runnable — the devcontainer installs the Jupyter extension, so just
open the file and **Run All**.

> The notebooks are **executed in CI** (`pytest --nbmake`, Python 3.11 and 3.13), so one that stops
> working turns the build red rather than quietly becoming a screenshot of code that used to run.


Libraries: `core`, `cassette`, `tokenguard`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
