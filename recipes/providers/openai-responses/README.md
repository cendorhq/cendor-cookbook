# openai-responses — account for reasoning + cached tokens

**The pain.** New OpenAI apps use the Responses API, which reports usage differently from Chat
Completions. If your cost tooling only understands `prompt_tokens`/`completion_tokens`, it
silently misses cached input and reasoning output — the tokens you're actually billed for.

**What this shows.** A fake `responses.create` returns `input_tokens`/`output_tokens` with
`input_tokens_details.cached_tokens` and `output_tokens_details.reasoning_tokens`. `instrument()`
normalizes all four into one `Usage`, and prices the call — reasoning and cached tokens visibly
accounted for.

## The five steps (every recipe in `providers/` walks these, in this order)

| # | Step | What it is here |
|---|---|---|
| 1 | **connect** | `OpenAI()` — the `responses.create` shape |
| 2 | **instrument** | one wrap — detection is structural, not name-based |
| 3 | **govern** | a `budget(usd=…)` cap **and** a `regex_rule` gate that blocks a leaked key |
| 4 | **record** | `cassette` — the same call replayed offline: **0 provider calls, $0** |
| 5 | **prove** | `acttrace` `verify()` over the hash chain, and a cost that came from `prices` |

**Distinctive here: reasoning and cached tokens.** Both are billed, at different rates,
and a naive prompt+completion sum misses both.

## Run it

```bash
uv run python recipes/providers/openai-responses/main.py
```

## Expected output

```text
gate     : BLOCKED by regex_rule - provider saw 0 call(s), $0
usage    : 1,204 in (200 cached) -> 850 out (620 reasoning)
cost     : $0.011260000 (cost_estimated) - reasoning + cached are IN this number
refused  : pre-flight block: projected $0.002587500 would exceed cap $0.00001 (model=gpt-4o)
cassette : replayed 1 call, 0 provider call(s), $0
verify() : True - ok: 7 entries, head 9418cfbe97fa…
```

The cached input and reasoning output are captured, not dropped, and the cost is labeled
`cost_estimated` (priced offline from the snapshot).

**Live cassette (RECORD ✓, ships unrecorded):** record a real Responses call with
`RECORD=1 OPENAI_API_KEY=sk-... uv run --group apps python .../main.py` — `openai` is not a base
dependency of this repo, so `--group apps` (or `uv run --with openai`) is required. **No fixture is
committed**; CI runs the fake-client path above.

Libraries: `core`, `tokenguard`, `guardrails`, `cassette`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
