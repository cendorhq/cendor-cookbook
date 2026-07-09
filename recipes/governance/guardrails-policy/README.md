# guardrails-policy — declare guardrails in a versioned file, prove which one was active

**The pain.** Your guardrails live in code, scattered across the app. When an auditor asks "what
policy was enforcing this call, on this date?", you're grepping git history — and you can't prove the
answer wasn't edited after the fact.

**What this shows.** `load_policy("guardrails.json")` builds a guardrail list from a **versioned,
reviewable file** of deterministic rules. Its content hash (`policy_hash`) and declared version are
stamped into **every** `guardrail_decision` — so the tamper-evident audit chain records exactly which
policy gated each call. A leaked `sk-…` key is **redacted before send**; a jailbreak phrase is
**blocked pre-spend** ($0). Offline, no key — the "OpenAI" client is a fake provider-shaped object.

> The document supports the deterministic built-ins (`keyword_deny`, `regex_rule`, `url_allowlist` /
> `url_deny`, `length_bounds`, `json_schema`) — rules that need a callable or a cloud client (an LLM
> judge, the hosted rails) are wired in code. YAML needs the `cendor-guardrails[yaml]` extra; JSON is
> stdlib. In TypeScript, `loadPolicy(text, { parse })` is the same, minus the file read.

## Run it

```bash
uv run python recipes/governance/guardrails-policy/main.py
```

## Expected output

```text
loaded policy 2026-07-09 — sha256:8371aae2…
REDACTED before send: provider received 'my key is [redacted]'
BLOCKED pre-spend: guardrail 'keyword_deny' blocked at stage 'input': denied keyword: 'ignore previous instructions'  ($0 spent — 1 call so far)

every decision proves which policy was active:
  redact regex_rule   policy=2026-07-09
  block  keyword_deny policy=2026-07-09

chain verifies: True  (policy_hash sha256:8371aae… is in the evidence)
```

The evidence angle is the point: `verify()` confirms the chain, and each entry names the policy
version + hash that produced it. Change the file, and the hash changes — a mismatch is provable.

Libraries: `core`, `guardrails`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
