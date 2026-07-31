# compress-and-restore — an eviction you can audit *and* undo

**The pain.** Fitting a long transcript to a budget usually means throwing turns away. You lose
information you might need later, and you have no record of what went — which is exactly the
question an auditor asks. And if the content is sensitive, you cannot solve the record problem by
logging what you dropped.

**What this shows.** `evict="compress"` routes the block through core's `Compressor` **protocol** to
whatever backend you registered with `use_compressor()` — here `squeeze`, which returns a reversible
handle. squeeze then emits a **metadata-only** `CompressionEvent` on core's bus, and an attached
`acttrace` chain records it as a `compression` entry: technique, tokens before/after, handle id, and
**never the text**. `decompress(handle)` restores the original byte-for-byte, and `verify()` still
passes on the chain.

Closes two APIs no other recipe exercises: `use_compressor` and `decompress`.

## Run it

```bash
uv run python recipes/combos/compress-and-restore/main.py
```

## Expected output

```text
original         : 1,999 tokens
after compress   : 264 tokens  (extractive, ratio 0.132)
audit entry      : type=compression handle_id=1a9034a4180b…
leaked content   : False  (metadata only — the chain never holds the text)
decompress()     : byte-for-byte identical True
verify()         : True — ok: 3 entries, head bd4f8f52f9c5…
```

`leaked content: False` is a real check, not a promise: the recipe plants a marker string in the
transcript and asserts it appears in no field of the audit payload. That is the property that lets
you keep the chain when you cannot keep the content.

`decompress(handle)` and `handle.expand()` are the same call — use whichever reads better where you
are. The original lives in squeeze's content-addressed store; see
[`libs/squeeze-persist-and-restore`](../../libs/squeeze-persist-and-restore/) for making that store
survive the process.

Libraries: `core`, `contextkit`, `squeeze`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
