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
audit  : true — ok: 7 entries, head <hex>… (signatures verified)
```

Drop the `client:` argument and set `OPENAI_API_KEY` (Anthropic: `ANTHROPIC_API_KEY`) to run it
live. ⚠️ **`openai` is an OPTIONAL PEER of `@cendor/sdk` and this recipe does not declare it**, so the
live swap needs `npm install openai` first — otherwise the SDK cannot construct a client and you get a
module-not-found rather than an auth error. Then it
live — the SDK builds the provider client from your env; or pass `client: new OpenAI()` yourself. The
budget/audit/verify guarantees are unchanged, and the audit chain it writes verifies in **Python**
too (`cendor.acttrace.verify`), byte-for-byte.

## Pins

The npm shelf this recipe was **live-verified against on 2026-07-30** — a record of what was run, not a
lockfile. `package.json` declares carets and at `3.x` a caret spans the whole major, so a fresh
`npm install` resolves forward within major 3. `package-lock.json` is deliberately not committed.

```
@cendor/sdk 3.0.3  (pulls @cendor/core 3.0.1 + the six libraries)
zod 4.x
```

⚠️ `npm install` over an existing `node_modules` is **lock-obedient, not a refresh**. To move onto what
is published: `rm -rf node_modules package-lock.json && npm install`. Then
`node ../../../scripts/check-one-core.mjs .` asserts exactly one `@cendor/core` — two copies are two
event buses, and cross-library cooperation stops with nothing failing to say so.

Libraries: `@cendor/sdk` (+ `@cendor/tokenguard`, `@cendor/acttrace`) · Offline ✓ · TypeScript · [← all recipes](../../../README.md)
