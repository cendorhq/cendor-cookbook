# ollama-local — budgeted, recorded, audited — on a $0 local model

**The pain.** You want the whole production-plumbing story — cost, testing, audit — but on a local
model, with no cloud account, no key, and no data leaving the machine.

**What this shows.** One Ollama turn, instrumented once, then priced (llama3 is $0.00 in the
snapshot), budgeted, recorded to a cassette, and written to a signed audit trail — fully offline.
In CI it runs against a fake `ollama.Client().chat` shape; locally you swap in the real client.

## The five steps (every recipe in `providers/` walks these, in this order)

| # | Step | What it is here |
|---|---|---|
| 1 | **connect** | `ollama.Client()` — a local daemon, no cloud at all |
| 2 | **instrument** | one wrap — detection is structural, not name-based |
| 3 | **govern** | a **token** cap (the one that works with no rate) plus a `keyword_deny` gate |
| 4 | **record** | `cassette` — the same call replayed offline: **0 provider calls, $0** |
| 5 | **prove** | `acttrace` `verify()` over the hash chain, and a cost that came from `prices` |

**Distinctive here: the cost step is the one that cannot be honest.** A local model has
no invoice — `llama3` carries a $0.00 row, `llama3.2:latest` carries none at all and
`call.cost` is `None`. The recipe **documents the omission instead of faking a number**,
and caps *tokens* instead of dollars.

## Run it

```bash
# Offline (fake client) — what CI runs:
uv run python recipes/providers/ollama-local/main.py

# Against a real local daemon (one-line swap):
ollama pull llama3
OLLAMA_LIVE=1 uv run --with ollama python recipes/providers/ollama-local/main.py

# A different local model you already have:
OLLAMA_MODEL=llama3.2 OLLAMA_LIVE=1 uv run --with ollama python recipes/providers/ollama-local/main.py
```

`ollama` is not a dependency of this repo — the offline path fakes the client shape and never imports
it, so `--with ollama` is what supplies it for a live run.

## Expected output

```text
gate    : BLOCKED by keyword_deny - the daemon saw 0 call(s)
turn    : llama3 (local) … 26 in + 298 out … cost: $0.00
budget  : $0.000 spent of $1.00 cap  (a USD cap on a $0 model measures nothing)
tokens  : pre-flight block: ~267 tokens would exceed cap 100 (model=llama3)
audit   : decision recorded, verify: True - ok: 11 entries, head eab9043806f9… (signatures verified; metadata signature verified)
cassette: recorded (1 call) -> replayed (0 calls, offline)
```

A complete turn — budgeted, recorded, and audited — for $0.00, with no network. CI is mock/replay
only (no daemon required); the `OLLAMA_LIVE=1` path is the real-local run.

**Two honest details about a local model, both measured live on 2026-07-30:**

- ⚠️ **`$0.00` and *unpriced* are different answers, and only one of them is a measurement.** `llama3`
  has a `$0.00` row in the bundled snapshot; **`llama3.2:latest` has no row at all**, so its cost is
  `None` and the recipe prints `unpriced (no rate for this id — token counts are still exact)` rather
  than a $0.00 nobody measured. Token counts, the budget's token dimension and the audit chain are
  exact either way; a **USD** cap cannot bind to an unpriced id (`tokenguard` warns), a `tokens=` cap
  can.
- Under `OLLAMA_LIVE=1` the "recorded" count reads `not counted (live client)`. The counter only
  increments inside the *fake* client, so a genuinely recorded live call is invisible to it — better to
  say so than to print `recorded (0 call)` straight after making one.

Libraries: `core`, `tokenguard`, `guardrails`, `cassette`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
