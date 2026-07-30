# ollama-local — budgeted, recorded, audited — on a $0 local model

**The pain.** You want the whole production-plumbing story — cost, testing, audit — but on a local
model, with no cloud account, no key, and no data leaving the machine.

**What this shows.** One Ollama turn, instrumented once, then priced (llama3 is $0.00 in the
snapshot), budgeted, recorded to a cassette, and written to a signed audit trail — fully offline.
In CI it runs against a fake `ollama.Client().chat` shape; locally you swap in the real client.

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
turn   : llama3 (local) · 26 in + 298 out · cost: $0.00
budget : $0.000 spent of $1.00 cap
audit  : decision recorded, verify: True
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

Libraries: `core`, `tokenguard`, `cassette`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
