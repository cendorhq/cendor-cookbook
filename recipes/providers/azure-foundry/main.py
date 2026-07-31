"""azure-foundry — cost truth for an Azure AI Foundry deployment (an UNPRICED model id).

Azure/Foundry models are called through the **standard `openai` SDK** pointed at the Foundry v1 GA
endpoint, so `instrument()` detects them as `openai` and capture is free. The thing nobody warns you
about is **money**: you call your *deployment name*, not a model id, so the price table has no row
for it. Usage and the audit chain stay exact; the cost is `None` and a USD `budget(...)` silently
cannot bind. This recipe shows that happening, then fixes it with one
`prices.register_model_price(...)` line — and the SAME call becomes enforceable.

Offline: a fake OpenAI-shaped client. Run:
  uv run python recipes/providers/azure-foundry/main.py

Record a real cassette (maintainer, needs a key + `openai` installed):
  RECORD=1 uv run --group apps python recipes/providers/azure-foundry/main.py
  # env: AZURE_OPENAI_ENDPOINT AZURE_OPENAI_API_KEY AZURE_OPENAI_DEPLOYMENT
  # optional: AZURE_PROJECT_ENDPOINT (to record through the Foundry SDK instead)
"""

import os
import re
import warnings
from types import SimpleNamespace

from cendor.core import bus, instrument, prices
from cendor.tokenguard import BudgetExceeded, budget, reset

# Your Foundry deployment name — arbitrary by design. `gpt-4o` behind a deployment called
# `prod-chat` is normal, which is exactly why the price table cannot guess it.
DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "my-chat-deployment")

# ⚠️ The output-cap parameter is not the same on every model: the reasoning families (o-series,
# gpt-5-*) reject `max_tokens` with a 400 naming `max_completion_tokens`. A deployment name tells
# you nothing, so default by name and let the env override it.
CAP_PARAM = os.environ.get("OUTPUT_CAP_PARAM") or (
    "max_completion_tokens" if re.match(r"(?i)^(o[1-9]|gpt-5)", DEPLOYMENT) else "max_tokens"
)


def v1_base_url(endpoint: str) -> str:
    """The Foundry **v1 GA** route. Microsoft's current guidance is a plain `OpenAI` client here —
    no `AzureOpenAI`, no `api-version`. Three endpoint forms all work:

      https://<res>.openai.azure.com                      (Azure OpenAI models)
      https://<res>.services.ai.azure.com                 (Foundry Models: DeepSeek, Grok, Llama, …)
      https://<res>.services.ai.azure.com/api/projects/<p> (the project endpoint the portal shows)
    """
    return endpoint.rstrip("/") + "/openai/v1/"


def fake_openai_client():
    """Stand-in for the live client — identical `chat.completions.create` shape, no network."""

    class Completions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Within policy."))],
                usage=SimpleNamespace(prompt_tokens=1_200, completion_tokens=400),
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def ask(client) -> None:
    client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[{"role": "user", "content": "Is this request within policy?"}],
        **{CAP_PARAM: 64},
    )


def live_client():
    """The real thing: the v1 GA API through the standard `openai` SDK."""
    from openai import OpenAI  # lazily imported; the offline path needs no provider SDK

    return instrument(
        OpenAI(
            base_url=v1_base_url(os.environ["AZURE_OPENAI_ENDPOINT"]),
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
        )
    )


def foundry_sdk_client():
    """The same client, obtained from the **Foundry SDK** (`pip install azure-ai-projects`).

    `get_openai_client()` returns a plain `openai.OpenAI` pointed at `<endpoint>/openai/v1`, so
    there is nothing Foundry-specific for cendor to know — `instrument()` captures it as `openai`
    exactly like the client above. Use this when your app already builds an `AIProjectClient`.
    """
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    project = AIProjectClient(
        endpoint=os.environ["AZURE_PROJECT_ENDPOINT"],  # …/api/projects/<your-project>
        credential=DefaultAzureCredential(),  # Microsoft Entra ID (keyless)
    )
    return instrument(project.get_openai_client())


def record_live() -> None:  # the RECORD=1 path — ships unrecorded; needs YOUR endpoint + key
    from cendor import cassette

    client = foundry_sdk_client() if os.environ.get("USE_FOUNDRY_SDK") else live_client()
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "azure-foundry.json")

    @cassette.use(fixture, mode="record")  # secrets are redacted on write
    def one_call():
        ask(client)

    one_call()
    print(f"recorded live call to {fixture}")


def show(label: str, call) -> None:
    priced = "reported" if call.metadata.get("cost_reported") else "estimated"
    amount = "None" if call.cost is None else f"${call.cost.amount}"
    print(
        f"{label:<22} provider={call.provider} model={call.model} "
        f"{call.usage.input_tokens} in / {call.usage.output_tokens} out -> {amount} ({priced})"
    )


def main() -> None:
    if os.environ.get("RECORD") == "1":
        record_live()
        return

    client = instrument(fake_openai_client())
    seen: list = []
    bus.subscribe(seen.append)

    # 1 — as shipped: the deployment id is not in the price table.
    reset()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            with budget(usd=0.000_01, on_exceed="block"):
                ask(client)
        except BudgetExceeded as e:  # pragma: no cover — the point is that it does NOT happen
            print(f"unexpectedly blocked: {e}")
    show("unpriced (as shipped)", seen[-1])
    for w in caught:
        print(f"  warning: {type(w.message).__name__}: {str(w.message).split('.')[0]}.")
    print("  -> the $0.00001 USD cap did NOT bind: an unpriced call projects $0.")

    # 2 — one line of truth, from `cendor-core` itself (since 1.15.0 — no SDK distribution needed).
    #     Rates are YOURS to supply (Azure list price for the model behind the deployment); cendor
    #     never guesses them. This survives prices.refresh().
    prices.register_model_price(DEPLOYMENT, input=2.50, output=10.00)  # USD per 1M tokens

    reset()
    blocked = False
    try:
        with budget(usd=0.000_01, on_exceed="block"):
            ask(client)
    except BudgetExceeded as e:
        blocked = True
        print(f"\npriced (registered)   BudgetExceeded: {e}")
    if not blocked:  # pragma: no cover
        show("priced (registered)", seen[-1])

    reset()
    with budget(usd=1.00, on_exceed="block"):
        ask(client)
    show("priced, cap raised", seen[-1])
    print("  -> same deployment, same call: now costed, and the USD cap enforces pre-flight.")


if __name__ == "__main__":
    main()
