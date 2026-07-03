# pytest-cassette — an agent test suite that runs on a plane

**The pain.** Agent tests hit real models: they're slow, they cost money, they flake on wording
drift, and they break under `pytest -n auto` when parallel workers fight over one cassette file.

**What this shows.** A real 3-test suite for a fake agent that makes one tool call and one model
call. Each test has its **own** cassette (one file per test — xdist-safe), so `pytest -n auto`
replays them in parallel with **zero** API calls. `mode="replay"` is strict: an unrecorded call
raises `CassetteError`, so drift can't pass silently. Committed cassettes live in
[`fixtures/`](fixtures/).

## Run it

```bash
uv run pytest recipes/testing/pytest-cassette            # fast, offline
uv run pytest recipes/testing/pytest-cassette -n auto    # parallel, still 0 calls
```

## Expected output

```text
...                                                                      [100%]
3 passed in 0.03s
```

Three passing tests, **0 API calls**, sub-second — under `-n auto` the same three pass in parallel
(a few seconds of that is just worker start-up). The suite runs with no key and no network.

## Recording & drift

The committed cassettes were recorded once against the fake client. After an intentional API
change, re-record them:

```bash
RERECORD=1 uv run pytest recipes/testing/pytest-cassette
```

To detect drift without overwriting, run a cassette in `mode="rerecord"` and inspect
`cassette.drift()` (byte-exact divergences) or `cassette.semantic_drift()` (meaningful ones only).

Libraries: `core`, `cassette` · Offline ✓ · [← all recipes](../../../README.md)
