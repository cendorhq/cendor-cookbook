"""context-under-budget — the budget binds on what actually SHIPS, not on what you typed.

A 200-row JSON blob would blow the context window. contextkit assembles it to a token budget
(compressing the oversized block through squeeze), and the tokenguard clamp then binds on the
*assembled* prompt — so the receipt contextkit hands you and the input the provider bills are the
same number. Guess at that number and you either overspend or clamp a prompt that was already small.

Three libraries, zero imports between them: contextkit asks core's `Compressor` protocol for a
backend, squeeze satisfies it, tokenguard reads the same `LLMCall` off core's bus.

Offline: a fake OpenAI-shaped client whose reported `prompt_tokens` is the *real* token count of
whatever it received, so "billed == receipt" is a measurement, not an assumption.

  uv run python recipes/combos/context-under-budget/main.py
"""

import json
from types import SimpleNamespace

from cendor.contextkit import Block, Context, use_compressor
from cendor.core import instrument, tokens
from cendor.squeeze import SqueezeCompressor
from cendor.tokenguard import budget, clamps, estimate, reset

MODEL = "gpt-4o"


def counting_client(seen: dict):
    """A fake OpenAI client that bills exactly what it was sent — the honest scale."""

    class Completions:
        def create(self, **kw):
            seen.update(kw)
            n = tokens.count(kw.get("messages", []), MODEL)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=n, completion_tokens=1),
                model=kw.get("model", MODEL),
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def main() -> None:
    reset()
    row = {"status": "shipped", "region": "eu-west-1", "total": 19.99}
    payload = json.dumps({"rows": [{"id": i, **row} for i in range(200)]})
    raw_tokens = tokens.count(payload, MODEL)

    previous = use_compressor(SqueezeCompressor())  # process-wide backend for evict="compress"
    try:
        ctx = (
            Context(budget_tokens=220, model=MODEL, reserve_output=0)
            .add(Block("You are a precise data analyst.", role="system", pin=True, priority=100))
            .add(Block(payload, role="user", priority=1, evict="compress"))
        )
        messages = ctx.assemble()
        receipt = ctx.report()

        compressed = [d for d in receipt.decisions if d.action == "compressed"]
        assert compressed, "evict='compress' never fired — squeeze did not cooperate"
        assert compressed[0].handle.expand() == payload, "the eviction was not reversible"
        assert receipt.used <= receipt.budget, "the assembled prompt overshot the budget"
        assert receipt.used == tokens.count(messages, MODEL), "the receipt is not the real count"

        # Ship it under a clamp cap just above the input: input + the 256-token output reserve
        # breaches the cap, so the clamp injects a server-side output ceiling instead of raising.
        seen: dict = {}
        client = counting_client(seen)
        with budget(tokens=receipt.used + 50, on_exceed="clamp"):
            client.chat.completions.create(model=MODEL, messages=messages)
    finally:
        use_compressor(previous)

    billed = seen and tokens.count(seen["messages"], MODEL)
    ceiling = seen.get("max_completion_tokens")

    print(f"raw block        : {raw_tokens:,} tokens  ({len(payload) / 1024:.1f} KB of JSON)")
    print(f"assembled        : {receipt.used} tokens of a {receipt.budget}-token budget")
    cut = compressed[0]
    shrink = f"{cut.tokens_before} -> {cut.tokens_after} tok"
    print(f"eviction         : {cut.action} ({shrink}), reversible")
    print(f"billed input     : {billed} tokens  == the receipt: {billed == receipt.used}")
    print(f"clamp injected   : max_completion_tokens={ceiling}  ({len(clamps())} clamp recorded)")
    print(
        f"cost projection  : ${estimate(MODEL, messages, 128).amount} assembled "
        f"vs ${estimate(MODEL, [{'role': 'user', 'content': payload}], 128).amount} raw"
    )

    assert billed == receipt.used, "billed input drifted from the contextkit receipt"
    assert ceiling is not None, "the clamp did not inject a server-side output ceiling"
    assert (
        estimate(MODEL, messages, 128).amount
        < estimate(MODEL, [{"role": "user", "content": payload}], 128).amount
    ), "the projection did not bind on the assembled prompt"


if __name__ == "__main__":
    main()
