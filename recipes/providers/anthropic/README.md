# anthropic — make prompt-cache billing legible (and audited)

**The pain.** Anthropic's prompt caching bills at three rates: uncached input, cache **reads**,
and cache **writes**. The response splits them across `input_tokens`,
`cache_read_input_tokens`, and `cache_creation_input_tokens`. Getting the cost right by hand is
error-prone.

**What this shows.** `instrument()` normalizes cache reads into `input_tokens` (as a `cached`
subset) and tracks cache writes as their own billed category, so the estimate follows Anthropic's
formula. The same call is written to a tamper-evident, signed audit trail and verified offline.

## The five steps (every recipe in `providers/` walks these, in this order)

| # | Step | What it is here |
|---|---|---|
| 1 | **connect** | `Anthropic()` — the `messages.create` shape |
| 2 | **instrument** | one wrap — detection is structural, not name-based |
| 3 | **govern** | a `budget(usd=…)` cap **and** a `keyword_deny` gate |
| 4 | **record** | `cassette` — the same call replayed offline: **0 provider calls, $0** |
| 5 | **prove** | `acttrace` `verify()` over the hash chain, and a cost that came from `prices` |

**Distinctive here: three input rates on one call** — uncached input, cache **reads**
and cache **writes**, each billed differently.

⚠️ **Pre-flight token counting for Claude is approximate.** `o200k` under-counts Claude
by a measured **1.49×** (English) / **1.14×** (code), so a projection is a projection.
The usage printed below is *settled* — what Anthropic reported — and that one is exact.

## Run it

```bash
uv run python recipes/providers/anthropic/main.py
```

## Expected output

```text
gate     : BLOCKED by keyword_deny - provider saw 0 call(s), $0
usage    : 1,800 in (800 cache-read) + 300 cache-write -> 200 out
cost     : $0.00736500  (uncached + cache-read + cache-write + output)
refused  : pre-flight block: projected $0.00387300 would exceed cap $0.00001 (model=claude-sonnet-4-6)
cassette : replayed 1 call, 0 provider call(s), $0
verify() : True - ok: 9 entries, head f2a8647d1345… (signatures verified; metadata signature verified)
```

*(The head hash varies per run.)* Cache reads and writes are both priced and visible; the cost is
the sum of uncached input + cache-read + cache-write + output — Anthropic's cache-aware billing.

**Live cassette (RECORD ✓, ships unrecorded):** record a real call with
`RECORD=1 ANTHROPIC_API_KEY=sk-ant-... uv run --group apps python .../main.py` — `anthropic` is not a
base dependency of this repo, so `--group apps` (or `uv run --with anthropic`) is required. **No
fixture is committed**; CI runs the fake-client path above.

## Run it as a notebook

[`notebook.ipynb`](notebook.ipynb) tells the same story a cell at a time — each step prints its own
output, the markdown carries the *why*, and the last cell asserts what `main.py` asserts. Offline
like everything else.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/providers/anthropic/notebook.ipynb
```

In a Codespace it is already runnable — the devcontainer installs the Jupyter extension, so just
open the file and **Run All**.

> The notebooks are **executed in CI** (`pytest --nbmake`, Python 3.11 and 3.13), so one that stops
> working turns the build red rather than quietly becoming a screenshot of code that used to run.


Libraries: `core`, `tokenguard`, `guardrails`, `cassette`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
