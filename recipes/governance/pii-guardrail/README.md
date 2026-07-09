# pii-guardrail — PII/secrets as a guardrail, with the audit trail to prove it

**The pain.** You want PII and secrets scrubbed *before* a payload reaches the model — and you want
one detection engine, not a second half-baked regex list bolted onto your guardrails.

**What this shows.** `cendor-guardrails` ships **no** PII detector on purpose: detection is
`acttrace`'s job (its validated detector catalogue). You bridge it in ~3 lines with
`rules.custom(fn)` calling `acttrace.scan` / `acttrace.redact`, `install()` it on the interceptor
seam, and every scrub lands in the tamper-evident audit chain as a `guardrail_decision` that
`verify()` confirms — offline, no key. An email is **redacted before send** (the provider receives
`<redacted>`); a leaked `sk-…` key can **block** the call pre-spend.

> Building an **agent**? `cendor-sdk` ships this as `rules.pii()` / `rules.secrets()` /
> `rules.entropy()` — the same bridge, wired to all four stages, so it also scans **tool outputs**
> (which the process-global `guard()` never sees). This recipe is the framework-free, door-1 pattern.

## Run it

```bash
uv run python recipes/governance/pii-guardrail/main.py
```

## Expected output

```text
REDACTED before send: provider received 'email <redacted> the invoice'

guardrail_decision entries in the audit chain:
  redact input  pii

chain verifies: True  (the email never left the process in the clear)
```

There is **no catch-rate claim** here: coverage is exactly `acttrace`'s catalogue — validated
detectors for secrets, financial, gov-ID, and structured PII (measured per-category in
[the benchmarks](https://cendor.ai/benchmarks)). Free-text names/addresses need the optional
`acttrace[ner]` backend; deterministic detection does not stop a novel obfuscation.

Libraries: `core`, `guardrails`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
