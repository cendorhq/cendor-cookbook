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
5 cases: trip rate 100.0% (3/3 attacks), false-positive rate 0.0% (0/2 benign)

by category (attacks caught / attacks):
  override   2/2
  roleplay   1/1
```

The 100% here is on a *tiny* inline corpus rigged to the keywords — the point of red-teaming is to
find where your gate fails, then raise the trip rate by **layering tiers** (a classifier, an
`llm_judge`, a hosted rail), never by overfitting keywords to the test set. Publish a rate only with
the corpus named — see the [threat model](https://cendor.ai/docs/guardrails#threat-model).

Libraries: `guardrails` · Offline ✓ · [← all recipes](../../../README.md)
