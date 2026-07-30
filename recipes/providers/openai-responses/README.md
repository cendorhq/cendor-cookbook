# openai-responses — account for reasoning + cached tokens

**The pain.** New OpenAI apps use the Responses API, which reports usage differently from Chat
Completions. If your cost tooling only understands `prompt_tokens`/`completion_tokens`, it
silently misses cached input and reasoning output — the tokens you're actually billed for.

**What this shows.** A fake `responses.create` returns `input_tokens`/`output_tokens` with
`input_tokens_details.cached_tokens` and `output_tokens_details.reasoning_tokens`. `instrument()`
normalizes all four into one `Usage`, and prices the call — reasoning and cached tokens visibly
accounted for.

## Run it

```bash
uv run python recipes/providers/openai-responses/main.py
```

## Expected output

```text
usage: 1,204 in (200 cached) -> 850 out (620 reasoning) · cost $0.011260000 (cost_estimated)
```

The cached input and reasoning output are captured, not dropped, and the cost is labeled
`cost_estimated` (priced offline from the snapshot).

**Live cassette (RECORD ✓, ships unrecorded):** record a real Responses call with
`RECORD=1 OPENAI_API_KEY=sk-... uv run --group apps python .../main.py` — `openai` is not a base
dependency of this repo, so `--group apps` (or `uv run --with openai`) is required. **No fixture is
committed**; CI runs the fake-client path above.

Libraries: `core`, `tokenguard` · Offline ✓ · [← all recipes](../../../README.md)
