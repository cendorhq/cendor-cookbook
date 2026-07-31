# context-under-budget — the budget binds on what actually ships

**The pain.** You set a token cap based on the prompt you *wrote*, but what leaves the process is
the prompt your context assembler *built* — after eviction, compression and framing. Guess at that
number and you either overspend, or you clamp a request that was already small. Nobody wants to
count tokens twice.

**What this shows.** `contextkit` assembles an oversized JSON block to a 220-token budget, routing
the eviction through core's `Compressor` **protocol** to `squeeze` (registered once with
`use_compressor`). The assembly receipt (`report().used`) is then proven to be the *real* token
count of the assembled messages, and `tokenguard`'s `clamp` binds on that same number — measured by
a fake provider that bills exactly what it was sent.

Three libraries cooperating with **zero imports between them**: contextkit asks the protocol,
squeeze satisfies it, tokenguard reads the resulting `LLMCall` off core's bus.

## Run it

```bash
uv run python recipes/combos/context-under-budget/main.py
```

## Expected output

```text
raw block        : 6,004 tokens  (14.2 KB of JSON)
assembled        : 199 tokens of a 220-token budget
eviction         : compressed (6004 -> 181 tok), reversible
billed input     : 199 tokens  == the receipt: True
clamp injected   : max_completion_tokens=50  (1 clamp recorded)
cost projection  : $0.001777500 assembled vs $0.016307500 raw
```

The three numbers that matter: the receipt (199) **is** the billed input, the clamp injected a
server-side output ceiling rather than raising, and the cost projection over the assembled prompt is
~9× cheaper than over the raw block — because a projection over what you typed is a projection of a
call you are not making.

The compression stays reversible: `decision.handle.expand()` returns the original 200 rows exactly.
See [`compress-and-restore`](../compress-and-restore/) for the audit trail that goes with it.

Libraries: `core`, `contextkit`, `squeeze`, `tokenguard` · Offline ✓ · [← all recipes](../../../README.md)
