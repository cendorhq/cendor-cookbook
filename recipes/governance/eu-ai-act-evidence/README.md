# eu-ai-act-evidence — a tamper-evident evidence pack for a high-risk decision

**The pain.** A regulator — or your own compliance team — asks: *what did the agent see, what did
it decide, what did it refuse, and can you prove the record wasn't edited afterward?* A log file
alone can't answer the last part.

**What this shows.** A loan-triage agent (`risk_tier="high"`). A pre-flight guard on the
`instrument()` seam **flags and blocks** an SSN-bearing prompt — the refusal is recorded, the
model never sees the data. A clean decision then runs with a recorded human-oversight sign-off.
The whole thing is exported as an EU-AI-Act-tagged evidence pack, verified by the `acttrace` CLI,
and then tampered with: **one edited byte makes the CLI exit 1.**

> **Evidence to support compliance — not a guarantee, not legal advice.** `acttrace` provides
> record-keeping, human-oversight events, and tamper-evidence to *support* compliance work; the
> control mappings are starting templates for your compliance team, not a determination that any
> system is compliant.

## Run it

```bash
uv run python recipes/governance/eu-ai-act-evidence/main.py
# it's also a test:
uv run pytest recipes/governance/eu-ai-act-evidence
```

## Expected output

```text
SSN-bearing prompt blocked pre-flight : True (refusal recorded)
refusal is inside the evidence pack   : True
$ acttrace verify evidence.jsonl --key ***
ok: 9 entries, head 2ff318bedf8f… (signatures verified; metadata signature verified)
(1 byte edited, then re-verify)
$ acttrace verify evidence.jsonl --key ***
tampered entry at seq 7: hash mismatch
clean exit 0  ->  tampered exit 1
```

*(The head hash varies per run.)* The refusal itself is part of the tamper-evident pack, the clean
pack verifies with exit 0, and a single edited byte is caught — the CLI exits 1 and names the
entry. The signing key is read from `CENDOR_DEMO_KEY` with a fallback default; in production, load
it from your secret manager and never commit it.

Libraries: `core`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
