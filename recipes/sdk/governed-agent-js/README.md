# governed-agent (JS) — a budget-capped, audited agent in ~15 lines

**What this shows.** `@cendor/sdk` makes governance the default. This agent runs one tool call under a
USD `withBudget(... onExceed: 'block')` circuit breaker, writes a tamper-evident `AuditLog` chain, and
proves it with `verify()` — all offline, no key. The TypeScript twin of the
[`governed-agent`](../governed-agent/README.md) recipe.

## Run it

```bash
cd recipes/sdk/governed-agent-js
npm install    # pulls @cendor/sdk from npm
node index.mjs
```

## Expected output

```text
output : Done — your refund for order 123 is on the way.
cost   : 0.000... USD
tokens : 182
tools  : [ 'refund' ]
trace  : <hex>
audit  : true — ok: 6 entries, head <hex>… (signatures verified; metadata signature verified)
```

Drop the `client:` argument and set `OPENAI_API_KEY` (Anthropic: `ANTHROPIC_API_KEY`) to run it
live — the SDK builds the provider client from your env; or pass `client: new OpenAI()` yourself. The
budget/audit/verify guarantees are unchanged, and the audit chain it writes verifies in **Python**
too (`cendor.acttrace.verify`), byte-for-byte.

Libraries: `@cendor/sdk` (+ `@cendor/tokenguard`, `@cendor/acttrace`) · Offline ✓ · TypeScript ·
[← all recipes](../../../README.md)
