"""core quickstart — one wrap, and every LLM call lands on a normalized event bus.

Every cost/audit/testing tool wants to patch your client. cendor-core patches it *once*:
`instrument()` wraps the client in place and emits a normalized `LLMCall` on a shared bus —
provider, model, usage, a Decimal cost with an honest pricing label, and the token-counting
method it would use. Every other Cendor tool just listens.

Offline: fake provider-shaped client, no key. Run:
  uv run python recipes/quickstarts/core/main.py
"""

from types import SimpleNamespace

from cendor.core import bus, instrument, tokens


def fake_openai():
    class Completions:
        def create(self, **kwargs):
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=1_200, completion_tokens=350)
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def print_event(call) -> None:
    label = "cost_reported" if call.metadata.get("cost_reported") else "cost_estimated"
    print("LLMCall on the bus:")
    print(f"  provider : {call.provider}")
    print(f"  model    : {call.model}")
    print(
        f"  usage    : {call.usage.input_tokens} in + {call.usage.output_tokens} out "
        f"= {call.usage.total_tokens} tokens"
    )
    print(f"  cost     : ${call.cost.amount} ({label})")
    print(f"  tokens   : counted via '{tokens.method(call.model)}' for {call.model}")


def main() -> None:
    bus.subscribe(print_event)  # any tool would subscribe the same way
    client = instrument(fake_openai())  # the one and only wrap

    client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hello"}])


if __name__ == "__main__":
    main()
