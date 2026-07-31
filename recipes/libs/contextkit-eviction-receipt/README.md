# contextkit-eviction-receipt — read the receipt, not the vibes

**The pain.** Everyone writes the same helper eventually: *"if the prompt is too long, drop some
history."* Then a bug report arrives — the model forgot the system rules, or the retrieved doc it
needed is missing — and there is nothing to look at. Which block went? Why that one?

**What this shows.** contextkit makes the packing declarative and hands back a **receipt**. Each
block declares `priority=` (higher survives longer), `pin=True` (never evicted, at any budget),
`evict=` (what to do when it must shrink) and `keep=` (which end of a truncation to keep). Then
`report()` returns an `AssemblyReport` with a `BlockDecision` per block: what happened, the tokens
before and after, and a note.

`whatif(n)` prices a tighter budget without committing to it — and leaves the committed report
untouched, which the recipe asserts.

## Run it

```bash
uv run python recipes/libs/contextkit-eviction-receipt/main.py
```

## Expected output

```text
raw input        : 2,144 tokens
budget           : 1200 tokens (200 reserved for the answer)
used             : 1000 tokens in 18 messages
the receipt      :
  [kept      ] system       15 -> 15    tok
  [kept      ] system      608 -> 608   tok
  [truncated ] history     456 -> 285   tok  # history: kept 15 of 24 turns
  [truncated ] user        967 -> 17    tok
whatif()         : 1200->1000, 800->600, 500->300, 300->100
                   committed report untouched: True
pinned block     : kept at every budget - it is the reason the agent works
```

Four blocks, four decisions, and the priorities are visible in the outcome: the pinned rules
survived untouched, the high-priority policy was kept whole, the history lost its oldest 9 turns,
and the low-priority retrieved doc — the thing you can most afford to lose — was cut to 17 tokens.
Nothing had to be guessed about, because the receipt says so.

`whatif()` is the answer to "what budget should I set?". Run it across a few values, look at what
each one costs you, and pick — instead of discovering the answer in production.

To make the eviction **reversible** rather than lossy, give the block `evict="compress"`:
[`combos/compress-and-restore`](../../combos/compress-and-restore/).

Libraries: `core`, `contextkit` · Offline ✓ · [← all recipes](../../../README.md)
