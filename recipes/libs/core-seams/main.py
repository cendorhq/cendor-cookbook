"""core-seams — the three hooks every other Cendor library is built on.

`cendor-core` is deliberately small: it normalizes provider calls onto one bus and exposes a handful
of seams. Every other library in the set is *just a subscriber* to those seams — which is also why
you can build your own tool beside them without forking anything.

  trace(id)                group a unit of work. Every LLMCall and ToolCall inside carries
                           trace_id=id, and (with OpenTelemetry configured) the calls become
                           children of one parent span instead of N unrelated roots.
  add_stream_observer(fn)  fn(call, delta_text, delta_thinking) per chunk of every instrumented
                           stream. Core extracts the deltas, so an observer never parses a provider
                           shape. **Raising aborts the stream** — that is exactly how tokenguard's
                           `on_exceed="break"` breaker is implemented; core learns no budget words.
  tokens.register(fam, fn) override the token counter for a model family. Needed the day you serve
                           a model whose tokenizer nobody bundles — a fine-tune, a local model, a
                           vendor with its own BPE. Everything downstream (budgets, contextkit
                           receipts, cost estimates) then measures with YOUR counter.

Offline: fake OpenAI-shaped clients, no key, no OpenTelemetry needed.

  uv run python recipes/libs/core-seams/main.py
"""

from types import SimpleNamespace

from cendor.core import (
    LLMCall,
    add_stream_observer,
    bus,
    current_trace_id,
    instrument,
    remove_stream_observer,
    tokens,
    trace,
)

MODEL = "gpt-4o"
HOUSE_MODEL = "acme-llm-1"  # a model nobody bundles a tokenizer for


def fake_client(stream_chunks: int = 0):
    class Completions:
        def create(self, **kw):
            if kw.get("stream"):
                return iter(
                    SimpleNamespace(
                        choices=[SimpleNamespace(delta=SimpleNamespace(content=f"part {i} "))]
                    )
                    for i in range(stream_chunks)
                )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=30, completion_tokens=7),
                model=kw.get("model", MODEL),
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def main() -> None:
    calls: list[LLMCall] = []

    def collect(event: object) -> None:
        if isinstance(event, LLMCall):
            calls.append(event)

    bus.subscribe(collect)

    # ---- seam 1: trace() groups a unit of work ---------------------------------------------------
    client = fake_client()
    with trace("order-8812-refund"):
        inside = current_trace_id()
        client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "a"}])
        client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "b"}])
    client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "c"}])

    grouped = [c for c in calls if c.trace_id == "order-8812-refund"]
    print(f"trace()          : current_trace_id() inside the scope = {inside!r}")
    print(
        f"                   {len(grouped)} of {len(calls)} calls carry it; the one outside "
        f"has trace_id={calls[-1].trace_id!r}"
    )

    # ---- seam 2: a per-chunk stream observer ----------------------------------------------------
    seen: list[str] = []

    def meter(call: LLMCall, delta_text: str, delta_thinking: str) -> None:
        seen.append(delta_text)

    add_stream_observer(meter)
    try:
        streamed = fake_client(stream_chunks=12)
        # `messages=[]` is fine for a fake and a hard 400 on any real provider ("[] is too short").
        # Harmless here — this recipe is about core's seams, not a portable call shape — but if you
        # lift this line into your own code, send a real message.
        consumed = list(streamed.chat.completions.create(model=MODEL, messages=[], stream=True))
    finally:
        remove_stream_observer(meter)

    print(
        f"stream observer  : {len(seen)} chunk deltas seen for {len(consumed)} chunks consumed, "
        f"first delta {seen[0]!r}"
    )
    print(
        "                   raising inside the observer CLOSES the provider stream - that is how "
        "tokenguard's break works"
    )

    # ---- seam 3: a custom tokenizer for a model nobody bundles ----------------------------------
    text = "the quick brown fox jumps over the lazy dog"
    before = tokens.count(text, HOUSE_MODEL), tokens.method(HOUSE_MODEL)

    # Our house model bills one token per two characters. Nothing else needs to know.
    # NOTE: family() maps an id to a tokenizer family, and an id nobody recognises lands in
    # "default" — so registering here also covers every other unrecognised model. Register a
    # specific family ("openai", "anthropic") when that is what you mean.
    tokens.register(tokens.family(HOUSE_MODEL), lambda t, m: max(1, len(str(t)) // 2))
    after = tokens.count(text, HOUSE_MODEL), tokens.method(HOUSE_MODEL)

    print(f"tokens.register(): {HOUSE_MODEL} family={tokens.family(HOUSE_MODEL)!r}")
    print(
        f"                   before {before[0]} tokens (method {before[1]!r}) -> "
        f"after {after[0]} tokens (method {after[1]!r})"
    )
    print("                   every budget, receipt and estimate downstream now uses your counter")

    bus.unsubscribe(collect)

    assert len(grouped) == 2 and calls[-1].trace_id != "order-8812-refund", "trace() did not group"
    assert len(seen) == 12, "the stream observer did not see every chunk"
    assert after[1] == "registered", "tokens.method() should report the registered counter"
    assert after[0] == len(text) // 2, "the custom counter was not used"


if __name__ == "__main__":
    main()
