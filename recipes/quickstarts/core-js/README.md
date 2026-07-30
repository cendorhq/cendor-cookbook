# core (JS) — one wrap, and every LLM call lands on a normalized event bus

**The pain.** Every cost/testing/audit tool wants to monkey-patch your client. Stack three of them
and you have three patches fighting over the same method.

**What this shows.** `@cendor/core` patches the client **once**. `instrument()` wraps it in place and
emits a normalized `LLMCall` on a shared bus for every request — provider, model, usage, a
decimal-exact cost with an honest pricing label, and the token-counting method it would use. Every
other `@cendor/*` tool is just a subscriber. This is the TypeScript twin of the
[`core` quickstart](../core/README.md).

## Run it

```bash
cd recipes/quickstarts/core-js
npm install    # pulls @cendor/core from npm
node index.mjs
```

## Expected output

```text
LLMCall on the bus:
  provider : openai
  model    : gpt-4o
  usage    : 1200 in + 350 out = 1550 tokens
  cost     : $0.0065 (cost_estimated)
  tokens   : counted via 'exact' for gpt-4o
```

Cost is priced offline from the bundled snapshot and labeled `cost_estimated`; the token method is
`exact` because `js-tiktoken` ships with `@cendor/core`. The cost matches the Python recipe to the
last digit — same price dataset, same decimal math (value-equal; `decimal.js` prints `0.0065`).

## Pins

The npm shelf this recipe was **verified against on 2026-07-30** — a record of what was run, not a
lockfile. `package.json` declares a caret and at `3.x` a caret spans the whole major, so a fresh
`npm install` resolves forward within major 3: a newer patch than the number below is expected, not
drift. `package-lock.json` is deliberately **not** committed, for the same reason.

```
@cendor/core 3.0.1
```

⚠️ `npm install` over an existing `node_modules` is **lock-obedient, not a refresh** — it will happily
leave you on an older 3.x. To move onto what is actually published:
`rm -rf node_modules package-lock.json && npm install`.

Libraries: `@cendor/core` · Offline ✓ · TypeScript · [← all recipes](../../../README.md)
