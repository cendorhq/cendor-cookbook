"""openai-responses — capture reasoning + cached tokens on the Responses API.

New OpenAI apps (and the Agents SDK) use `responses.create`, which reports usage differently:
`input_tokens`/`output_tokens`, with cached tokens under `input_tokens_details.cached_tokens`
and reasoning under `output_tokens_details.reasoning_tokens`. `instrument()` normalizes all of
it, so cost accounting sees the reasoning and cached tokens you're actually billed for.

Offline: fake `responses.create` shape. Run:
  uv run python recipes/providers/openai-responses/main.py

Record a real cassette (maintainer, needs a key + `openai` installed):
  RECORD=1 OPENAI_API_KEY=sk-... uv run python recipes/providers/openai-responses/main.py
"""

import os
from types import SimpleNamespace

from cendor.core import bus, instrument


def fake_openai_responses():
    """Stand-in for `OpenAI()` — the Responses API shape with reasoning + cached details."""

    class Responses:
        def create(self, **kwargs):
            return SimpleNamespace(
                usage=SimpleNamespace(
                    input_tokens=1204,
                    output_tokens=850,
                    input_tokens_details=SimpleNamespace(cached_tokens=200),
                    output_tokens_details=SimpleNamespace(reasoning_tokens=620),
                )
            )

    return SimpleNamespace(responses=Responses())


def show(call) -> None:
    u = call.usage
    label = "cost_reported" if call.metadata.get("cost_reported") else "cost_estimated"
    print(
        f"usage: {u.input_tokens:,} in ({u.cached_tokens} cached) -> "
        f"{u.output_tokens:,} out ({u.reasoning_tokens} reasoning) · "
        f"cost ${call.cost.amount} ({label})"
    )


def record_live() -> None:  # RECORD=1 path — ships unrecorded
    from cendor import cassette
    from openai import OpenAI

    client = instrument(OpenAI())
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "openai-responses.json")

    @cassette.use(fixture, mode="record")
    def one_call():
        client.responses.create(model="gpt-4o", input="Reason briefly, then greet me.")

    one_call()
    print(f"recorded live call to {fixture}")


def main() -> None:
    if os.environ.get("RECORD") == "1":
        record_live()
        return

    bus.subscribe(show)
    client = instrument(fake_openai_responses())
    client.responses.create(model="gpt-4o", input="Summarize this thread, then reason about it.")


if __name__ == "__main__":
    main()
