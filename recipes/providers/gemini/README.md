# gemini — one seam, a completely different usage shape

**The pain.** Gemini reports usage nothing like OpenAI. There is no `usage` object: there is
`usage_metadata`, with `prompt_token_count` and `candidates_token_count`, and the call is
`client.models.generate_content(model=…, contents=…)`. Every cost tool, audit tool and test tool that
reads `response.usage.prompt_tokens` is blind here — so teams end up with a second, parallel
accounting path for one provider.

**What this shows.** The provider-specific part is *only* the client. `instrument()` maps
`usage_metadata` onto the same normalized `LLMCall`, so the budget, the `track()` attribution, the
`report()` row and the tamper-evident audit chain are the same three lines you would write for
OpenAI — and the pre-flight refusal reads in dollars, not in Gemini's vocabulary.

## Run it

```bash
# Offline (fake genai.Client shape) — what CI runs, no key:
uv run python recipes/providers/gemini/main.py

# Against the real API (records a redacted cassette):
export GOOGLE_API_KEY="<your-key>"        # GEMINI_API_KEY is read too
RECORD=1 uv run --with google-genai python recipes/providers/gemini/main.py
```

`google-genai` is not a dependency of this repo — the offline path never imports it. `--with
google-genai` supplies it for the `RECORD=1` path only.

## Expected output

```text
provider : google   (inferred from the client's shape, not configured)
model    : gemini-2.5-flash
usage    : 980 in + 210 out   (mapped from usage_metadata.prompt_token_count / .candidates_token_count)
cost     : $0.000819000
spend    : {'feature': 'triage'} 1 call(s) -> $0.000819000
refused  : pre-flight block: projected $0.000643300 would exceed cap $0.00001 (model=gemini-2.5-flash)
audit    : verify=True — ok: 7 entries, head 3b729c5f890c… (signatures verified; metadata signature verified)
```

*(The head hash varies per run.)* `provider : google` is **inferred from the client's shape** — you
configure nothing. The second turn never reaches the model: the projection is compared to the cap
before the request goes out, so the refusal costs `$0.00`.

## Honest limits

- **Streaming is not captured on the libraries door.** `instrument()` wraps
  `models.generate_content` and its async twin `aio.models.generate_content`, but **not**
  `generate_content_stream` — a streamed Gemini call raises no error and emits no `LLMCall`, so it is
  invisible to budgets and audit. Use `cendor-sdk`'s Gemini provider if you need governed streaming,
  or keep the libraries-door path non-streamed.
- **Not every Gemini id is priced.** The bundled snapshot (`2026-07-13`) carries six Gemini rows;
  `gemini-2.0-flash`, for instance, is **not** one of them, and an unpriced model costs `None` — so a
  USD budget cannot bind to it. `prices.models()` lists what is priced, and
  `register_model_price(...)` adds a rate (see [azure-foundry](../azure-foundry/) for that story in
  full).
- **A known Gemini rough edge, stated rather than hidden:** `cendor-acttrace`'s redact-before-send
  reroute writes an OpenAI-shaped message list into `contents`, which `google-genai` rejects. That is
  why this recipe budgets and audits but does not demonstrate `guard(..., action="redact")` on Gemini.
  Tracked in the suite; not fixed as of the shelf this recipe was verified against.

## Your keys stay yours

No key appears anywhere in this repo. `genai.Client()` reads **your** `GOOGLE_API_KEY` /
`GEMINI_API_KEY` from the environment, and CI has no secrets — a recipe that needs a key to go green
is a bug in the recipe.

Libraries: `core`, `tokenguard`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
