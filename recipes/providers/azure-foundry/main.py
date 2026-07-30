"""azure-foundry — cost truth for an Azure AI Foundry deployment (an UNPRICED model id).

Azure models are called through the OpenAI SDK, so `instrument()` detects them as `openai` and
capture is free. The thing nobody warns you about is **money**: you call your *deployment name*,
not a model id, so the price table has no row for it. Usage and the audit chain stay exact; the
cost is `$0` and a USD `budget(...)` silently cannot bind. This recipe shows that happening, then
fixes it with one `register_model_price(...)` line — and the SAME call becomes enforceable.

Offline: fake `AzureOpenAI` shape. Run:
  uv run python recipes/providers/azure-foundry/main.py

Record a real cassette (maintainer, needs a key + `openai` installed):
  RECORD=1 uv run --group apps python recipes/providers/azure-foundry/main.py
  # env: AZURE_OPENAI_ENDPOINT AZURE_OPENAI_API_KEY AZURE_OPENAI_DEPLOYMENT AZURE_OPENAI_API_VERSION
"""

import os
import re
import warnings
from types import SimpleNamespace

from cendor.core import bus, instrument
from cendor.sdk.pricing import register_model_price
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


def fake_azure_openai():
    """Stand-in for `AzureOpenAI(...)` — identical `chat.completions.create` shape, no network."""

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


def record_live() -> None:  # the RECORD=1 path — ships unrecorded; needs YOUR endpoint + key
    from cendor import cassette
    from openai import AzureOpenAI  # lazily imported; the offline path needs no provider SDK

    client = instrument(
        AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],  # https://<you>.openai.azure.com
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        )
    )
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

    client = instrument(fake_azure_openai())
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

    # 2 — one line of truth. Rates are YOURS to supply (Azure list price for the model behind the
    #     deployment); cendor never guesses them. This survives prices.refresh().
    register_model_price(DEPLOYMENT, input=2.50, output=10.00)  # USD per 1M tokens

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
