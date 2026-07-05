# governed-agent — a governed agent in ~10 lines

**The pain.** Agent SDKs make it easy to spin up a tool-calling loop — and just as easy to ship one
with no spend cap, no record of what it did, and PII flowing straight to the provider.

**What this shows.** `cendor-sdk` makes governance the *foundation*: the same ~10 lines that define
the agent also cap spend **pre-flight**, redact PII before send, and write every call, tool, and
decision to a **tamper-evident audit chain** that verifies offline. A real two-turn tool loop runs
(`get_weather` → answer) against a stub client — no network, no API key.

```python
agent = Agent(name="assistant", model="gpt-4o", tools=[get_weather], client=stub)  # drop client= in prod
log = AuditLog(system="support", risk_tier="limited", path="audit.jsonl")
with budget(usd=0.25, on_exceed="block"), guard(Policy.default(), audit=log):
    result = run(agent, "What's the weather in Paris?", audit=log)
verify("audit.jsonl")   # (True, "…") — the chain re-walks and verifies, offline
```

## Run it

```bash
uv run python recipes/sdk/governed-agent/main.py
# it's also a test:
uv run pytest recipes/sdk/governed-agent
```

## Expected output

```text
output      : It's sunny in Paris.
cost        : 0.000… USD  (budget $0.25, enforced pre-flight)
usage       : Usage(input_tokens=140, output_tokens=21, …)
tools called : ['get_weather']
audit chain : True — ok: … entries
audit file  : /tmp/…/audit.jsonl
```

The loop and budgets, the redaction, and the hash-chained audit are all real; only the model call is
a stub. Drop the `client=` argument and set `OPENAI_API_KEY` to run it live — the governance code is
identical. Want to drop down to the libraries directly? Everything here is `cendor-core` +
`cendor-tokenguard` + `cendor-acttrace` under the hood.

> **Evidence to support compliance — not a guarantee, not legal advice.** `acttrace` provides
> record-keeping and tamper-evidence to *support* compliance work, not a determination of compliance.

Libraries: `cendor-sdk` (core · tokenguard · acttrace) · Offline ✓ · [← all recipes](../../../README.md)
