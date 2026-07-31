"""bedrock — govern boto3 Converse, where every id is unpriced and the usage keys are camelCase.

Bedrock's Converse API reports `usage` as `{"inputTokens": …, "outputTokens": …}` — camelCase, one
level down from where an OpenAI reader looks — and every Bedrock **model id** is a marketplace id
(`eu.amazon.nova-2-lite-v1:0`), so the price table has no row for it. `instrument()` normalizes the
usage; this recipe shows the two caps that still work on an unpriced model:

  * a **token** budget binds with no rate at all — it counts tokens, not dollars;
  * a **USD** budget binds after one `prices.register_model_price(...)` line, yours to supply.

Offline: fake boto3 `bedrock-runtime` shape. Run:
  uv run python recipes/providers/bedrock/main.py

Record a real cassette (maintainer, needs AWS credentials + `boto3` installed):
  RECORD=1 uv run --with boto3 python recipes/providers/bedrock/main.py
  # env: AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_REGION BEDROCK_MODEL_ID
"""

import os
from types import SimpleNamespace

from cendor.core import bus, instrument, prices
from cendor.tokenguard import BudgetExceeded, budget, reset

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "eu.amazon.nova-2-lite-v1:0")


def fake_bedrock_runtime():
    """Stand-in for `boto3.client("bedrock-runtime")` — the real `converse` shape, no network.

    `instrument()` detects Bedrock by a **boto-shaped `converse()` method**. That matters: the
    aws-sdk-v3 JavaScript client has no such method (it sends generic commands), which is why this
    recipe is Python-only — see "Honest limits" in the README.
    """

    def converse(**kwargs):
        return {
            "output": {"message": {"content": [{"text": "Within policy."}]}},
            "usage": {"inputTokens": 1_100, "outputTokens": 320, "totalTokens": 1_420},
            "stopReason": "end_turn",
        }

    return SimpleNamespace(converse=converse)


def ask(client, text: str = "Is this request within policy?"):
    return client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": text}]}],
        inferenceConfig={"maxTokens": 64},  # tokenguard's clamp writes the ceiling in HERE
    )


def record_live() -> None:  # the RECORD=1 path — ships unrecorded; needs YOUR AWS credentials
    import boto3  # lazily imported; the offline path needs no provider SDK
    from cendor import cassette

    client = instrument(
        boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    )
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "bedrock.json")

    @cassette.use(fixture, mode="record")  # secrets are redacted on write
    def one_call():
        ask(client, "Reply with the single word: pong")

    one_call()
    print(f"recorded live call to {fixture}")


def main() -> None:
    if os.environ.get("RECORD") == "1":
        record_live()
        return

    seen: list = []
    bus.subscribe(seen.append)
    client = instrument(fake_bedrock_runtime())

    reset()
    ask(client)
    call = seen[-1]
    print(f"provider : {call.provider}   (detected from the boto-shaped .converse method)")
    print(f"model    : {call.model}")
    print(
        f"usage    : {call.usage.input_tokens} in + {call.usage.output_tokens} out"
        f"   (mapped from usage.inputTokens / usage.outputTokens)"
    )
    print(f"cost     : ${call.cost.amount if call.cost else None}   <- no price row for this id")

    # 1 — a TOKEN cap needs no rate at all: it counts what the provider reported. Deliberately set
    #     BELOW one call's settled usage, because that is the honest edge: `block` is *pre-flight*,
    #     so a call whose estimate fits and whose real completion does not still lands over the cap.
    #     The exception says so, and says what to do about it (cendor-tokenguard >= 1.6.2).
    reset()
    try:
        with budget(tokens=1_000, on_exceed="block"):
            ask(client)
            ask(client)
    except BudgetExceeded as e:
        print(f"\ntokens=  {e}")

    # 2 — a USD cap needs a rate. Supply Bedrock's published price for the model behind the id.
    prices.register_model_price(MODEL_ID, input=0.06, output=0.24)  # USD per 1M tokens
    reset()
    try:
        with budget(usd=0.000_01, on_exceed="block"):
            ask(client)
    except BudgetExceeded as e:
        print(f"usd=     {e}")

    reset()
    with budget(usd=1.00, on_exceed="block"):
        ask(client)
    print(f"priced   ${seen[-1].cost.amount}   (same id, same call, now costed)")


if __name__ == "__main__":
    main()
