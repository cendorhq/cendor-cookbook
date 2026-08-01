# acttrace — a tamper-evident record of what your agent did

**The pain.** Someone asks: "prove what the agent saw, what it decided, and who signed off."
A plain log won't do — anyone could edit it after the fact. You need a record that *detects*
tampering.

**What this shows.** `AuditLog` hash-chains every event and signs it. A decision is recorded with
a human-oversight sign-off, exported as an EU-AI-Act-tagged evidence pack, and verified. Then we
flip **one byte** inside the file and verify again — the chain breaks at a known sequence number.

## Run it

```bash
uv run python recipes/quickstarts/acttrace/main.py
```

## Expected output

```text
verify: True  (ok: 5 entries, head e188e4e440f3… (signatures verified; metadata signature verified))
(1 byte flipped)
verify: False  (tampered entry at seq 1: hash mismatch)
```

*(The head hash varies per run because entries are timestamped.)* One edited byte is caught, and
verify points at the exact entry. `acttrace` produces **evidence to support** compliance — not a
guarantee, and not legal advice.

The signing key is read from `CENDOR_DEMO_KEY` with a fallback default so the recipe is green out
of the box; in production, load it from your secret manager and never commit it.

## Run it as a notebook

[`notebook.ipynb`](notebook.ipynb) tells the same story a cell at a time — each step prints its own
output, the markdown carries the *why*, and the last cell asserts what `main.py` asserts. Offline
like everything else.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/quickstarts/acttrace/notebook.ipynb
```

In a Codespace it is already runnable — the devcontainer installs the Jupyter extension, so just
open the file and **Run All**.

> The notebooks are **executed in CI** (`pytest --nbmake`, Python 3.11 and 3.13), so one that stops
> working turns the build red rather than quietly becoming a screenshot of code that used to run.


Libraries: `core`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
