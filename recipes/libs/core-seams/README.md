# core-seams — the three hooks every other Cendor library is built on

**The pain.** You want one of the things Cendor does, but not quite the way it does it — spend
grouped by *your* run id, a per-chunk latency meter, a token count for a model nobody bundles a
tokenizer for. Normally that means forking, or patching the client a second time and hoping the two
patches agree.

**What this shows.** `cendor-core` is deliberately small: it normalizes provider calls onto one bus
and exposes a handful of seams. Every other library in the set is *just a subscriber* — so the same
seams are open to you.

| seam | what it does |
|---|---|
| `trace(id)` | group a unit of work: every `LLMCall`/`ToolCall` inside carries `trace_id=id`, and with OpenTelemetry configured they become children of **one** parent span instead of N unrelated roots |
| `add_stream_observer(fn)` | `fn(call, delta_text, delta_thinking)` per chunk of every instrumented stream. Core extracts the deltas, so an observer never parses a provider shape. **Raising aborts the stream** |
| `tokens.register(fam, fn)` | override the token counter for a model family — a fine-tune, a local model, a vendor with its own BPE |

Closes `add_stream_observer` and `tokens.register`, and deepens `core.trace`.

## Run it

```bash
uv run python recipes/libs/core-seams/main.py
```

## Expected output

```text
trace()          : current_trace_id() inside the scope = 'order-8812-refund'
                   2 of 3 calls carry it; the one outside has trace_id=''
stream observer  : 12 chunk deltas seen for 12 chunks consumed, first delta 'part 0 '
                   raising inside the observer CLOSES the provider stream - that is how tokenguard's break works
tokens.register(): acme-llm-1 family='default'
                   before 9 tokens (method 'bpe-estimate') -> after 21 tokens (method 'registered')
                   every budget, receipt and estimate downstream now uses your counter
```

**`add_stream_observer` is not a logging hook — it is an enforcement seam.** Raising from it closes
the provider stream, finalizes the `LLMCall` with a partial estimated usage, and propagates to the
consumer. That is *exactly* how `tokenguard`'s `on_exceed="break"` is implemented, and core learns no
budget vocabulary in the process. With zero observers registered it costs one truthiness check per
chunk, so the streaming hot path is untouched.

**`tokens.method()` tells you how confident to be.** It returns `registered` (your counter),
`exact` (a model-native tiktoken encoding), `bpe-estimate` (an o200k proxy — every non-OpenAI model,
and any OpenAI id tiktoken does not recognise) or `heuristic`. Surface it rather than presenting an
estimate as a count.

⚠️ **`family()` maps an id to a family, and an unrecognised id lands in `"default"`** — so registering
there also covers every *other* unrecognised model in the process. Register a specific family
(`"openai"`, `"anthropic"`) when that is what you mean.

The audited, budgeted versions of these seams are the rest of the cookbook — the point of this recipe
is that they are the same seams, open to your code.

Libraries: `core` · Offline ✓ · [← all recipes](../../../README.md)
