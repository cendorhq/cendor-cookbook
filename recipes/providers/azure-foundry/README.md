# azure-foundry — cost truth for an Azure AI Foundry deployment

**The pain.** Azure models are called through the OpenAI SDK, so capture "just works" —
`instrument()` detects an `AzureOpenAI` client as `openai` and every call lands on the bus with exact
usage. Then you look at the money and it is **`$0`**. You did not call `gpt-4o`; you called *your
deployment*, and a deployment name is arbitrary — `prod-chat` can have anything behind it. There is
no price row for it, so a USD `budget(..., on_exceed="block")` counts every call as zero and
**silently never binds**. That is the failure that costs real money: the cap is in your code, in your
review, in your runbook, and it is not enforcing anything.

**What this shows.** The same call, three times: unpriced (cap does nothing), after one
`register_model_price(...)` line (cap blocks pre-flight), and with the cap raised (costed and
allowed). Plus the two Azure-specific traps that turn a working sample into a 400.

## Run it

```bash
# Offline (fake AzureOpenAI shape) — what CI runs, no key:
uv run python recipes/providers/azure-foundry/main.py

# Against YOUR Foundry deployment (records a redacted cassette):
export AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com"
export AZURE_OPENAI_API_KEY="<your-key>"
export AZURE_OPENAI_DEPLOYMENT="<your-deployment-name>"
export AZURE_OPENAI_API_VERSION="2024-10-21"
RECORD=1 uv run --group apps python recipes/providers/azure-foundry/main.py
```

`openai` is not a base dependency of this repo — the offline path never imports it. `--group apps`
supplies it for the `RECORD=1` path.

## Expected output

```text
unpriced (as shipped)  provider=openai model=my-chat-deployment 1200 in / 400 out -> None (estimated)
  warning: UnpricedModelWarning: tokenguard: no price for model 'my-chat-deployment', so the active USD budget (on_exceed='block') counts its calls as $0 and cannot enforce a USD cap on it.
  -> the $0.00001 USD cap did NOT bind: an unpriced call projects $0.

priced (registered)   BudgetExceeded: pre-flight block: projected $0.000672500 would exceed cap $0.00001 (model=my-chat-deployment)
priced, cap raised     provider=openai model=my-chat-deployment 1200 in / 400 out -> $0.007000000 (estimated)
  -> same deployment, same call: now costed, and the USD cap enforces pre-flight.
```

Read the first line carefully: `provider=openai` (detection worked), exact token counts (capture
worked), **`cost -> None`** (there is no price, and cendor says so rather than inventing one). The
rates in `register_model_price(DEPLOYMENT, input=2.50, output=10.00)` are **yours to supply** — Azure
list price for whatever model sits behind the deployment. Cendor never guesses them.

## Traps this recipe exists to teach

Each one was measured against a real Foundry `gpt-5-mini` deployment on api-version `2024-10-21`.

1. **An unpriced model makes a USD cap a no-op, not an error.** `on_exceed="block"` with no price row
   projects `$0`, so nothing ever exceeds. cendor raises `UnpricedModelWarning` — and
   `tokenguard.configure(on_unpriced="raise")` turns it into a refusal if you would rather fail
   closed. A **token** cap (`budget(tokens=…)`) binds on an unpriced model perfectly well; only money
   needs a rate.
2. **`max_tokens` is a hard 400 on the reasoning families.** o-series and `gpt-5-*` answer
   *"Unsupported parameter: 'max_tokens' is not supported with this model. Use
   'max_completion_tokens' instead."* — every call, so the sample never runs at all. And **a
   deployment name cannot tell you which family it is**: this recipe defaults by name, and
   `OUTPUT_CAP_PARAM` overrides it.
3. **On a reasoning deployment the output cap covers reasoning tokens, so a small cap returns
   nothing.** Measured on `gpt-5-mini` with a 48-token cap: `37 in / 48 out` and an **empty** visible
   reply. Usage, cost and the audit chain were all correct; there was simply no text.
4. **Foundry's *Agent Service* is a different integration.** If the loop runs server-side, you never
   hold the client, so there is nothing to `instrument()` — ingest its OpenTelemetry instead. That is
   the [`azure-foundry-otel`](../../frameworks/azure-foundry-otel/) recipe, not this one.

## Your keys stay yours

No endpoint, resource name, deployment name or key appears anywhere in this repo. Every value comes
from **your** environment; the documented placeholders are `https://<your-resource>.openai.azure.com`
and `<your-deployment-name>`. CI has no secrets and never will — a recipe that needs a key to go
green is a bug in the recipe.

Libraries: `core`, `tokenguard`, `sdk` (for `register_model_price`) · Offline ✓ ·
[← all recipes](../../../README.md)
