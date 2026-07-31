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

## Streaming is captured too (`cendor-core` >= 1.15.0)

Gemini does not take a `stream=True` flag — it streams through a **separate method**, which is
exactly why capture used to miss it entirely: a streamed Gemini call raised no error and emitted no
`LLMCall`, so it was invisible to budgets and audit. Since `cendor-core` 1.15.0 the streaming twins
are their own detection target, and nothing about your code changes:

```python
for chunk in client.models.generate_content_stream(model=MODEL, contents="Count to five"):
    print(chunk.text, end="")
# one LLMCall lands when the stream completes — usage, cost, audit, exactly like a non-streamed call
```

Three details worth knowing, all measured:

- **Usage comes from the LAST chunk.** Gemini puts `usage_metadata` on *every* chunk carrying the
  **running** totals, so the final chunk is the real figure. (Reading the first one — the rule that
  works for OpenAI, where usage rides one terminal chunk — would under-count every stream.)
- **A stream that reports no usage still emits**, with cendor's offline estimate and
  `metadata["usage_estimated"] = True` so you can tell the two apart.
- **Mid-stream governance works.** `budget(tokens=…, on_exceed="break")` cuts a runaway stream and
  closes it, then settles one `LLMCall` for what was actually consumed.

## Honest limits

- **Not every Gemini id is priced.** The bundled snapshot (`2026-07-13`) carries six Gemini rows;
  `gemini-2.0-flash`, for instance, is **not** one of them, and an unpriced model costs `None` — so a
  USD budget cannot bind to it. `prices.models()` lists what is priced, and
  `prices.register_model_price(...)` adds a rate (see [azure-foundry](../azure-foundry/) for that
  story in full).
- **`guard(..., action="redact")` on Gemini needs `cendor-core` >= 1.15.0.** The redact-before-send
  reroute used to write an OpenAI-shaped message list into `contents`, which `google-genai` rejects —
  the redaction fired and then made the request unsendable. Core now back-maps it onto Gemini's own
  `contents` shape (string / `Content` / `Part`), the same way the embeddings path already did.

## Your keys stay yours

No key appears anywhere in this repo. `genai.Client()` reads **your** `GOOGLE_API_KEY` /
`GEMINI_API_KEY` from the environment, and CI has no secrets — a recipe that needs a key to go green
is a bug in the recipe.

Libraries: `core`, `tokenguard`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
