# llm-judge-guardrail — screen with a model, and budget/audit the judge itself

**The pain.** Deterministic rules (keyword / regex) can't catch a *novel* jailbreak they were never
told about. You want a model to judge open-ended risk — but a second model call costs real tokens,
and most "AI firewall" tools hide that cost from you.

**What this shows.** `rules.llm_judge` is the bring-your-own-model tier: you supply the model call;
cendor ships no classifier. The point of difference is that the judge call is an **ordinary
instrumented call** — so its own tokens and cost land in `tokenguard`/`acttrace` like any other. The
guardrail you added to stay safe is itself **measured, budgeted, and audited**. The judge's model
call is recorded with `cassette`, so the recipe (and your CI) runs offline with **zero** API calls.

## Run it

```bash
uv run python recipes/governance/llm-judge-guardrail/main.py
uv run pytest recipes/governance/llm-judge-guardrail      # replays the cassette; 0 live calls
```

## Expected output

```text
benign  -> allowed
attack  -> blocked: prompt-injection

the judge's own spend is budgeted + attributed (2 judge call(s), 102 tokens) — the guardrail is
itself measured, on the same bus as every other call.
```

**Honest cost.** An LLM judge runs in **seconds** and is billed, where the deterministic rules are
microseconds and `$0`. Treat the judge as a targeted screen (use a small, cheap model; scope it to
the `input` stage) on top of the free deterministic floor — not a replacement for it. A judge is
only as good as its prompt; there is no jailbreak-detection **claim** here.

> `cendor-guardrails` 1.1+ ships `cendor.guardrails.judge` helpers (verdict prompt + strict-JSON
> parsing + timeout + fail policy) that package the prompt/parse shown inline here.

Libraries: `core`, `guardrails`, `tokenguard`, `cassette` · Offline ✓ · [← all recipes](../../../README.md)
