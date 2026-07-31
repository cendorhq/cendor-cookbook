# block-before-record — a call that never happened leaves nothing to replay

**The pain.** You wire a guardrail and a recorder into the same app and then have to reason about
which runs first. Get it backwards and your cassette fills with requests that were never sent — and
a later replay happily hands back a response for the exact call the guardrail exists to prevent.

**What this shows.** The ordering, as a measurement. `guardrails` blocks **pre-flight**, before the
request leaves your process; `cassette` records on the **response**. So inside one
`cassette.using(..., mode="record")` scope, a clean prompt is sent and recorded, and a denied prompt
reaches the provider **zero** times and writes **zero** cassette entries.

Two libraries with no import between them: each registers its own interceptor on `@cendor/core`, and
core runs them in the documented order.

## Run it

```bash
uv run python recipes/combos/block-before-record/main.py
```

## Expected output

```text
clean request    : reached the provider, recorded
blocked request  : GuardrailTripped - guardrail 'keyword_deny' blocked at stage 'input': denied keyword: 'wire transfer'
provider calls   : 1 (the blocked one never left the process)
cassette entries : 1 - one per call that actually happened
nothing to replay: a request that was refused has no recorded response to hand back
```

Two requests went into the scope; one call and one cassette entry came out. Both numbers are
counted, not claimed — the fake client increments a counter, and the recipe reads the entry count
back out of the cassette JSON.

The consequence worth internalising: **your cassettes only contain traffic that was allowed.** A
cassette recorded in production is therefore safe to replay in CI without re-running the policy — the
policy already ran.

Libraries: `core`, `guardrails`, `cassette` · Offline ✓ · [← all recipes](../../../README.md)
