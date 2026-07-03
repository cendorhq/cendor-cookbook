# llamaindex — pack unbounded RAG retrieval into a token budget, reversibly

**The pain.** Your retriever returns however many nodes it returns, and some are huge. Stuffing
them all into the prompt blows the context window; naive truncation silently corrupts a document
mid-sentence. You want to pack what fits, compress what's oversized, and know what got dropped.

**What this shows.** A real LlamaIndex retriever returns six oversized nodes. contextkit packs
them into a token budget — compressing the big ones with squeeze (`evict="compress"`) and
dropping the lowest-ranked when there's no room — and prints a receipt. Each compressed chunk
keeps a handle that restores the original byte-for-byte. `cendor` works **alongside** LlamaIndex.

## Run it

```bash
uv run --group frameworks-llamaindex python recipes/frameworks/llamaindex/main.py
```

## Expected output

```text
retriever returned 6 nodes
AssemblyReport(model=gpt-4o, order=default) budget=3000 reserved_output=200 used=2799/2800
  [kept      ] system    8->8tok
  [kept      ] user      6->6tok
  [kept      ] user      761->761tok
  [kept      ] user      761->761tok
  [kept      ] user      761->761tok
  [compressed] user      761->475tok
  [dropped   ] user      761->0tok  # no room (framing)
  [dropped   ] user      761->0tok  # no room (framing)

compressed a chunk; handle.expand() restores the original: True
sent 6 packed messages -> gpt-4o, cost $0.008200000
```

The receipt shows exactly which retrieved chunks were kept, compressed, and dropped — and the
compressed chunk can be restored in full if the model needs it.

Libraries: `core`, `contextkit`, `squeeze` · Offline ✓ · [← all recipes](../../../README.md)
