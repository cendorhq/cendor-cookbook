# guardrails-redteam — measure your guardrails' trip rate against a labeled corpus

**The pain.** "Our guardrails catch jailbreaks" is a claim, not a number — and an unbenchmarked
number is worse than none. You want to *measure* what your gate catches and what it misses, on a
corpus you can name.

**What this shows.** `run_redteam(guardrails, cases)` runs your guardrails over a labeled corpus and
reports the **trip rate** (recall on attacks), the **false-positive rate** (benign cases that
tripped), and a per-category breakdown. cendor **vends no attack data** — `load_corpus("attacks.jsonl")`
reads a file *you* assembled or downloaded (public sets like AdvBench / JailbreakBench, under their
own licenses). Deterministic guardrails make the run fully offline; a run with an `llm_judge` or a
hosted rail should be cassette-recorded (`run_redteam_async`) so CI stays offline.

## Run it

```bash
uv run python recipes/governance/guardrails-redteam/main.py
```

## Expected output

```text
9 cases: trip rate 50.0% (3/6 attacks), false-positive rate 0.0% (0/3 benign)

by category (attacks caught / attacks):
  leak       0/1
  override   2/3
  roleplay   1/2
```

**50% is the honest answer, and it is the point.** A keyword denylist catches the three attacks that
use its phrases and misses the three that do not — an obfuscated variant (`1gnore all prior
directives`), a translation framing that never says "reveal", and a persona pivot. The false-positive
rate matters just as much: `what are your guidelines for handling refunds?` is benign and must not be
blocked, so a gate that scored 100% on attacks by blocking everything would show up here as a
false-positive rate, not as a win.

⚠️ **A corpus whose every attack matches your keywords prints 100% and means nothing.** This demo
shipped exactly that until 2026-07-30 — three attacks, three denied phrases — when a new test asserted
the score must be partial and caught it. Raise a trip rate by **layering tiers** (a classifier, an
`llm_judge`, a hosted rail), never by overfitting keywords to the test set, and publish a rate only
with the corpus named — see the [threat model](https://cendor.ai/docs/guardrails#threat-model).

Libraries: `guardrails` · Offline ✓ · [← all recipes](../../../README.md)
