# custom-category — catch a request by meaning, not the exact words

**The pain.** A keyword denylist blocks `"write python code"` but sails straight past the paraphrase
`"create an app"` — same intent, different words. Literal matching can't see meaning.

**What this shows.** `rules.custom_category(name, examples, embed=...)` defines a category by a few
example phrases and trips when a turn is close enough to any of them — the local, `$0` counterpart to
Azure Content Safety's *rapid custom categories* (examples → embedding search), with no cloud call
and no training step. It composes with a keyword denylist: the denylist catches the literal wording,
the category catches the paraphrase the denylist missed.

`embed(text)` is bring-your-own. **In production, pass `embeddings.local_embedder()`** (the
`[embeddings]` extra — model2vec static embeddings, numpy-only, no torch). To stay offline in CI with
no model download, this recipe uses a tiny lexical bag-of-words `embed` (it matches shared *words*,
not true meaning) — enough to show the API and the compose-with-denylist pattern.

## Run it

```bash
uv run python recipes/governance/custom-category/main.py
uv run pytest recipes/governance/custom-category      # lexical stand-in embed; 0 live calls
```

## Expected output

```text
'write python code for hello world'
  denylist fired: True   custom_category fired: True
    - denylist flag: denied keyword: 'write python code'
    - code_requests flag: custom category 'code_requests': sim 0.35 >= 0.3

'create a hello world app'
  denylist fired: False   custom_category fired: True
    - code_requests flag: custom category 'code_requests': sim 0.35 >= 0.3
```

**Honest limits.** A similarity threshold is a heuristic — there is **no catch-rate claim**. The
bag-of-words embed here is a lexical stand-in (it would miss a paraphrase with no shared words); a
real embedder (`embeddings.local_embedder()`) matches meaning, and you calibrate the threshold on your
own data (`benchmarks/bench_semantic_gate.py` is the harness). Keep it `flag` until measured.

Libraries: `core`, `guardrails` · Offline ✓ · [← all recipes](../../../README.md)
