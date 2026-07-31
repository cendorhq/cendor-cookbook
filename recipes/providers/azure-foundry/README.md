# azure-foundry — cost truth for an Azure AI Foundry deployment

**The pain.** Azure/Foundry models are called through the **standard `openai` SDK** pointed at the
Foundry v1 GA endpoint, so capture "just works" — `instrument()` detects the client as `openai` and
every call lands on the bus with exact usage. Then you look at the money and it is **`None`**. You
did not call `gpt-4o`; you called *your deployment*, and a deployment name is arbitrary — `prod-chat`
can have anything behind it. There is no price row for it, so a USD `budget(..., on_exceed="block")`
counts every call as zero and **silently never binds**. That is the failure that costs real money:
the cap is in your code, in your review, in your runbook, and it is not enforcing anything.

**What this shows.** The same call, three times: unpriced (cap does nothing), after one
`prices.register_deployment(DEPLOYMENT, like="gpt-4o")` line (cap blocks pre-flight), and with the cap
raised (costed and allowed). You do not have to go and find a rate card — you name the model the
deployment serves, which you already know. Plus the Azure-specific traps that turn a working sample
into a 400.

## Run it

```bash
# Offline (a fake OpenAI-shaped client) — what CI runs, no key:
uv run python recipes/providers/azure-foundry/main.py

# Against YOUR Foundry deployment (records a redacted cassette):
export AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com"
export AZURE_OPENAI_API_KEY="<your-key>"
export AZURE_OPENAI_DEPLOYMENT="<your-deployment-name>"
export AZURE_BASE_MODEL="gpt-4o"          # optional — the model that deployment serves
RECORD=1 uv run --group apps python recipes/providers/azure-foundry/main.py
```

`openai` is not a base dependency of this repo — the offline path never imports it. `--group apps`
supplies it for the `RECORD=1` path.

## The endpoint: the v1 GA API, a plain `OpenAI` client

Microsoft's current guidance is the **v1 GA API**: the standard `OpenAI` client with
`base_url=<endpoint>/openai/v1/` and **no `api-version`**. Three endpoint forms all work:

| form | when |
|---|---|
| `https://<res>.openai.azure.com` | Azure OpenAI models |
| `https://<res>.services.ai.azure.com` | Foundry Models (DeepSeek, Grok, Llama, …) |
| `https://<res>.services.ai.azure.com/api/projects/<project>` | the project endpoint the portal shows |

```python
from openai import OpenAI
from cendor.core import instrument

client = instrument(OpenAI(
    base_url=f"{os.environ['AZURE_OPENAI_ENDPOINT'].rstrip('/')}/openai/v1/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
))
```

For **Microsoft Entra ID** (keyless), pass a refreshing bearer-token provider as `api_key` — the v1
client re-reads it per request:

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

token = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
client = instrument(OpenAI(base_url=..., api_key=token))
```

> **Legacy note.** Older apps build an `openai.AzureOpenAI` client with an `api_version`. Those are
> **still detected and still captured** — it is the same `openai` SDK shape, and Cendor pins that with
> a regression test on purpose. Nothing to migrate for capture's sake; the v1 form is simply what
> Microsoft documents for new code, and it needs no "same shape, so it counts as openai" caveat.

## With the Foundry SDK (`azure-ai-projects`)

If your app already builds an `AIProjectClient`, hand its OpenAI client straight to `instrument()`.
`get_openai_client()` returns a **plain `openai.OpenAI`** pointed at `<endpoint>/openai/v1`, so there
is nothing Foundry-specific for Cendor to know:

```python
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from cendor.core import instrument

project = AIProjectClient(
    endpoint=os.environ["AZURE_PROJECT_ENDPOINT"],   # …/api/projects/<your-project>
    credential=DefaultAzureCredential(),             # Entra ID, keyless
)
client = instrument(project.get_openai_client())
```

`pip install azure-ai-projects` is **your** dependency, never Cendor's. Set `AZURE_PROJECT_ENDPOINT`
and `USE_FOUNDRY_SDK=1` to record this path instead of the plain one — note that
`DefaultAzureCredential()` needs a real Entra sign-in (`az login`, a managed identity, or a service
principal in the environment). Without one it raises `ClientAuthenticationError` before any call is
made; the plain v1 path above needs only your resource key.

## Expected output

```text
unpriced (as shipped)  provider=openai model=my-chat-deployment 1200 in / 400 out -> None (estimated)
  warning: UnpricedModelWarning: tokenguard: no price for model 'my-chat-deployment', so the active USD budget (on_exceed='block') counts its calls as $0 and cannot enforce a USD cap on it.
  -> the $0.00001 USD cap did NOT bind: an unpriced call projects $0.

registered            my-chat-deployment like gpt-4o -> cached, input, output rates copied
  by hand (input=2.50, output=10.00) -> input, output   same input/output: True, cached rate: copied vs silently omitted

priced (registered)   BudgetExceeded: pre-flight block: projected $0.000672500 would exceed cap $0.00001 (model=my-chat-deployment)
priced, cap raised     provider=openai model=my-chat-deployment 1200 in / 400 out -> $0.007000000 (estimated)
  -> same deployment, same call: now costed, and the USD cap enforces pre-flight.
```

Read the first line carefully: `provider=openai` (detection worked), exact token counts (capture
worked), **`cost -> None`** (there is no price, and cendor says so rather than inventing one).

## Two ways to price it, and the common one first

```python
from cendor.core import prices

prices.register_deployment(DEPLOYMENT, like="gpt-4o")            # core >= 1.16.0
prices.register_model_price(DEPLOYMENT, input=2.50, output=10.00)  # or: USD per 1M, yours to supply
```

`register_deployment` copies the base model's rates. That is what almost everyone actually wants,
because you know which model your deployment serves and you would otherwise be re-typing a published
rate card. Four properties, all deliberate:

- **Nothing is inferred from the deployment's name.** `like` is an explicit mapping you supply — not
  `-preview`/`-latest` alias guessing, which was considered and rejected, because a confidently wrong
  price is worse than an honest `None`.
- **An unknown base raises `UnknownModelError`.** Registering nothing and leaving the deployment
  quietly unpriced would reproduce the exact silence the call exists to remove.
- **Every rate key is copied**, cached and cache-write included — which the two-number hand-typed form
  silently omits, as the third line of the output above measures.
- **Copy-at-registration, not a live alias.** A later `prices.refresh()` that reprices `gpt-4o` does
  not reprice your deployment; call it again. Both forms survive `refresh()` otherwise.

Use `register_model_price` when you hold the exact numbers and there is no base model to copy — a
fine-tune, a negotiated rate. Both live in **`cendor.core.prices`** (`register_model_price` since
`cendor-core` 1.15.0, `register_deployment` since 1.16.0; in TypeScript
`prices.registerDeployment(dep, { like })` since `@cendor/core` 3.2.0), so this recipe is pure
libraries door — no SDK distribution required. `cendor.sdk.register_model_price` still works and is
now a thin re-export.

## Traps this recipe exists to teach

Each one was measured against a real Foundry deployment running `gpt-5-mini`.

1. **An unpriced model makes a USD cap a no-op, not an error.** `on_exceed="block"` with no price row
   projects `$0`, so nothing ever exceeds. cendor raises `UnpricedModelWarning` — and
   `tokenguard.configure(on_unpriced="raise")` turns it into a refusal if you would rather fail
   closed. A **token** cap (`budget(tokens=…)`) binds on an unpriced model perfectly well; only money
   needs a rate. The one-line fix is `prices.register_deployment(dep, like=<the model it serves>)`.
2. **`max_tokens` is a hard 400 on the reasoning families.** o-series and `gpt-5-*` answer
   *"Unsupported parameter: 'max_tokens' is not supported with this model. Use
   'max_completion_tokens' instead."* — every call, so the sample never runs at all. And **a
   deployment name cannot tell you which family it is**: this recipe defaults by name, and
   `OUTPUT_CAP_PARAM` overrides it. (On the *SDK* door you don't have to care: `cendor-sdk` ≥ 1.21.0
   reads that error and re-issues the call once with the rename.)
3. **On a reasoning deployment the output cap covers reasoning tokens, so a small cap returns
   nothing.** Measured with a 48-token cap on that deployment: `37 in / 48 out` and an **empty** visible
   reply. Usage, cost and the audit chain were all correct; there was simply no text.
4. **A bare project endpoint is not a base URL.** `…/api/projects/<name>` without `/openai/v1/`
   answers *"400 Missing required query parameter: api-version"* — which reads like "go back to the
   legacy client" and is not. Append the route (this recipe's `v1_base_url()` does).
5. **Foundry's *Agent Service* is a different integration.** If the loop runs server-side, you never
   hold the client, so there is nothing to `instrument()` — ingest its OpenTelemetry instead. That is
   the [`azure-foundry-otel`](../../frameworks/azure-foundry-otel/) recipe, not this one.

## Your keys stay yours

No endpoint, resource name, deployment name or key appears anywhere in this repo. Every value comes
from **your** environment; the documented placeholders are `https://<your-resource>.openai.azure.com`
and `<your-deployment-name>`. CI has no secrets and never will — a recipe that needs a key to go
green is a bug in the recipe.

Libraries: `core`, `tokenguard` · Offline ✓ ·
[← all recipes](../../../README.md)
