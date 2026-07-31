# contextkit-plug-a-compressor — swap the compression backend, change no call sites

**The pain.** A general-purpose compressor is by definition ignorant of your domain. Your case logs
are 90% "agent viewed the order" boilerplate and 10% decisions; you know that and no library does.
But swapping the backend usually means touching every place that builds a prompt.

**What this shows.** contextkit does not know what `squeeze` is. When a block says
`evict="compress"` it asks whatever object matches core's `Compressor` protocol:

```python
compress(content, *, target_tokens, model) -> (compressed_text, handle)
```

`use_compressor(mine)` registers yours process-wide and every `evict="compress"` block uses it —
no call site changes. The recipe plugs in a `DecisionsOnly` compressor (keep the lines that carry a
decision, stash the original in a dict), then swaps back to `squeeze` and compresses the same block
so you can compare.

Closes `use_compressor`, which no other recipe exercises.

## Run it

```bash
uv run python recipes/libs/contextkit-plug-a-compressor/main.py
```

## Expected output

```text
raw case log     : 1,547 tokens, 96 lines
DecisionsOnly    : 1547 -> 107 tok  (technique decisions-only, expand() exact: True)
squeeze (default): 1547 -> 243 tok  (technique extractive, expand() exact: True)
both satisfy the same protocol - contextkit imported neither, and no call site changed
the handle is the contract: whatever you plug in must be able to give the original back
```

The domain compressor wins on this content (107 vs 243 tokens) because it knows something the
general algorithm cannot: on a case log, "agent viewed the order" is noise and "DECISION: refunded"
is the whole point. On prose it would be far worse. That is the argument for the seam, not for the
implementation.

**`expand() exact: True` is the contract.** contextkit surfaces the handle on the block's
`BlockDecision`, so a downstream step can recover what was dropped. A compressor that cannot give the
original back is not a compressor here — it is a summarizer, and there is an `evict="summarize"` for
that.

Note there is **no base class and no import from contextkit** — the protocol is satisfied by shape.
Your compressor can live anywhere, including in your own package.

Libraries: `core`, `contextkit`, `squeeze` · Offline ✓ · [← all recipes](../../../README.md)
