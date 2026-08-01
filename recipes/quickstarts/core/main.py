"""core quickstart — one wrap, and every LLM call lands on a normalized event bus.

Every cost/audit/testing tool wants to patch your client. cendor-core patches it *once*:
`instrument()` wraps the client in place and emits a normalized `LLMCall` on a shared bus —
provider, model, usage, a Decimal cost with an honest pricing label, and the token-counting
method it would use. Every other Cendor tool just listens.

Offline: fake provider-shaped client, no key. Run:
  uv run python recipes/quickstarts/core/main.py

Against a real provider (your key, one tiny call):
  LIVE=1 OPENAI_API_KEY=sk-... uv run --group apps python recipes/quickstarts/core/main.py

⚠️ The live path proves what the offline one only asserts: `instrument()` identifies a client by its
SHAPE, so the fake below and a real `OpenAI()` travel the identical code path. Nothing in `main()`
branches on which one it got — `make_client()` is the only line that knows.
"""

import os
from types import SimpleNamespace

from cendor.core import bus, instrument, tokens

LIVE = bool(os.environ.get("LIVE"))
# A real reply is ~10 output tokens against the fake's 350. It does not matter *here* — this recipe
# asserts that usage is present and priced, not that it is any particular size — but it is exactly
# why a recipe with a THRESHOLD needs live-specific sizing. See quickstarts/tokenguard.
MODEL = os.environ.get("LIVE_MODEL", "gpt-4o-mini") if LIVE else "gpt-4o"


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


def make_client():
    """The fake, or the real thing. The ONLY line in this file that knows the difference."""
    if LIVE:
        from openai import OpenAI  # lazy: the offline path needs no provider SDK

        return instrument(OpenAI())
    return instrument(fake_openai())


def main() -> None:
    seen: list = []
    bus.subscribe(print_event)  # any tool would subscribe the same way
    bus.subscribe(seen.append)
    client = make_client()  # the one and only wrap

    client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "Say hi in three words."}],
        **({"max_tokens": 16} if LIVE else {}),  # keep a live run to a fraction of a cent
    )

    # The claim is "one wrap and every tool downstream sees a normalized, priced event". Assert it,
    # because a seam that silently emitted nothing would print nothing and still exit 0.
    assert seen, "no event reached the bus — instrument() captured nothing"
    call = seen[-1]
    assert call.provider == "openai", f"provider was inferred as {call.provider!r}, not 'openai'"
    assert call.usage.input_tokens and call.usage.output_tokens, "usage was not normalized"
    assert call.cost and call.cost.amount > 0, "the call reached the bus unpriced"
    mode = "LIVE" if LIVE else "offline"
    print(f"\nmode     : {mode} - the assertions above are identical either way")


if __name__ == "__main__":
    main()
