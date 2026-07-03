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
OLLAMA_LIVE=1 uv run python recipes/providers/ollama-local/main.py
```

## Expected output

```text
turn   : llama3 (local) · 26 in + 298 out · cost: $0.00 (local)
budget : $0.000 spent of $1.00 cap
audit  : decision recorded, verify: True
cassette: recorded (1 call) -> replayed (0 calls, offline)
```

A complete turn — budgeted, recorded, and audited — for $0.00, with no network. CI is mock/replay
only (no daemon required); the `OLLAMA_LIVE=1` path is the real-local run.

Libraries: `core`, `tokenguard`, `cassette`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
