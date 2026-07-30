# anthropic — make prompt-cache billing legible (and audited)

**The pain.** Anthropic's prompt caching bills at three rates: uncached input, cache **reads**,
and cache **writes**. The response splits them across `input_tokens`,
`cache_read_input_tokens`, and `cache_creation_input_tokens`. Getting the cost right by hand is
error-prone.

**What this shows.** `instrument()` normalizes cache reads into `input_tokens` (as a `cached`
subset) and tracks cache writes as their own billed category, so the estimate follows Anthropic's
formula. The same call is written to a tamper-evident, signed audit trail and verified offline.

## Run it

```bash
uv run python recipes/providers/anthropic/main.py
```

## Expected output

```text
usage: 1,800 in (800 cache-read) + 300 cache-write -> 200 out
cost : $0.00736500  (uncached input + cache-read + cache-write + output)
audit: exported + verified (ok: 5 entries, head 7218e18bf8c2… (signatures verified; metadata signature verified))
```

*(The head hash varies per run.)* Cache reads and writes are both priced and visible; the cost is
the sum of uncached input + cache-read + cache-write + output — Anthropic's cache-aware billing.

**Live cassette (RECORD ✓, ships unrecorded):** record a real call with
`RECORD=1 ANTHROPIC_API_KEY=sk-ant-... uv run --group apps python .../main.py` — `anthropic` is not a
base dependency of this repo, so `--group apps` (or `uv run --with anthropic`) is required. **No
fixture is committed**; CI runs the fake-client path above.

Libraries: `core`, `tokenguard`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
