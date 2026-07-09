# task-adherence — is this tool call on-task? (a BYO-judge alignment check)

**The pain.** Agents drift. The user asks to *book a flight*; a few turns later the model proposes
`delete_account(...)`. Content filters don't catch this — the call isn't unsafe, it's just **not
what the user asked for**.

**What this shows.** `judge.task_adherence(respond)` is a bring-your-own-judge check for the
`tool_call` stage: *given the user's instruction and this proposed tool call + arguments, is the
action aligned with intent?* It reuses the judge helpers (strict-JSON verdict) and reads the intent
from `Context.instruction` — which the **`cendor-sdk` runner threads for you** from the run's input
turn; here (door 1) we set it ourselves. The alignment judge is an **ordinary instrumented call**, so
its own tokens and cost land in `tokenguard`/`acttrace` — the safety check is itself measured. The
judge's model call is recorded with `cassette`, so the recipe (and your CI) runs offline with **zero**
API calls.

## Run it

```bash
uv run python recipes/governance/task-adherence/main.py
uv run pytest recipes/governance/task-adherence      # replays the cassette; 0 live calls
```

## Expected output

```text
aligned   -> aligned
off-task  -> flagged: off-task: unrelated to booking a flight

the alignment judge's own spend is budgeted + attributed (2 call(s), 144 tokens) — the safety check
is itself measured. No adherence-rate claim: it's a BYO judge, only as good as its model + prompt.
```

**Honest cost & claim.** Task adherence is an extra model call per gated tool call — **seconds and
billed**, where the deterministic rules are microseconds and `$0`. It defaults to `action="flag"`
(advisory); set `action="block"` to short-circuit the tool. There is **no adherence-rate claim** — a
BYO judge is only as good as your model + prompt; measure it on your own data with the
[guardrails-redteam](../guardrails-redteam/) harness before citing a number.

> Needs `cendor-guardrails` 1.3+ (the `task_adherence` helper + `Context.instruction`). In the SDK,
> the `tool_call` gate sets `Context.instruction` automatically.

Libraries: `core`, `guardrails`, `tokenguard`, `cassette` · Offline ✓ · [← all recipes](../../../README.md)
