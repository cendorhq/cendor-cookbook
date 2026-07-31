# cassette-semantic-drift — `drift()` compares bytes; you want to compare meaning

**The pain.** You run a scheduled `rerecord` against the live provider to catch answers that have
moved. Models do not produce bytes twice, so it reports a divergence on nearly every entry — and a
signal that is mostly noise gets muted, which is the same as having no signal.

**What this shows.** `semantic_drift(threshold, scorer)` filters `drift()` down to divergences that
score **below** the threshold. The scorer is pluggable, and this recipe is mostly about *why* it has
to be.

**The measured result is not the intuitive one.** Both scorers available with no extra install
measure *surface* similarity, and on a realistic pair they get it exactly backwards.

## Run it

```bash
uv run python recipes/libs/cassette-semantic-drift/main.py
```

## Expected output

```text
recorded    : 'Refunds are available within 30 days of delivery.'

live answer  drift()  lexical  kept  toy-embed  kept
paraphrase   1        0.42     1     0.18       1
real change  1        0.96     0     0.89       0

read the two 'kept' columns: the PARAPHRASE survives the filter and the REAL CHANGE is
dropped, under both scorers. A surface scorer measures shared words, so a rewrite looks
like a big change and one edited number looks like none. That is the whole reason
semantic_drift() takes scorer= - install cendor-cassette[embeddings] and pass
local_embedding_scorer() for a real one (model2vec, offline, no key).

where the lexical default IS the right tool - asserting an answer means roughly X:
  semantic_match(recorded, 'refund within 30 days') = True
  semantic_match(recorded, 'delivery') = True

honest limit, measured rather than hidden:
  lexical_score('We will not offer a refund.', 'offer a refund') = 1.00 -> match True
  keyword containment cannot see a negation. Do not use it as a safety check.
```

**Read the two `kept` columns.** A harmless paraphrase scores 0.42 and *survives* the filter; "30
days" changed to "14 days" scores 0.96 and is *dropped*. Both scorers behave the same way, because
both count shared words: a rewrite shares few, and one edited number shares almost all.

That is not a bug in `lexical_score`, it is what lexical similarity **is** — and it is precisely why
`semantic_drift()` takes a `scorer=`. For a real one, offline and keyless:

```bash
pip install 'cendor-cassette[embeddings]'
```

```python
from cendor.cassette import local_embedding_scorer, semantic_drift
semantic_drift(0.8, local_embedding_scorer())   # model2vec static embeddings, no torch, no key
```

The cookbook stays dependency-light, so the recipe demonstrates the **seam** with a deliberately
crude hashed bag-of-words embedder and reports honestly that a toy embedder does not fix the
problem. `embedding_scorer(embed_fn)` takes any `texts -> vectors` callable, so cassette binds no
model and gains no dependency — wrap a local model, or your provider's embeddings endpoint.

**Where the lexical default is right:** asserting that an agent's answer *means roughly* something,
as in `assert semantic_match(out, "explains the charge")`. It is recall-oriented, so it tolerates
extra surrounding text. It is also why it accepts a negation — do not use it as a safety check.

> **TypeScript note.** `localEmbeddingScorer` exists in `@cendor/cassette` but **throws by design** —
> model2vec has no maintained pure-JS port. Use `embeddingScorer(embedFn)` with your own embedder.
> The TypeScript twin of this recipe documents that rather than faking it:
> [`cendor-cookbook-js`](https://github.com/cendorhq/cendor-cookbook-js/tree/main/recipes/libs/cassette-semantic-drift).

Libraries: `core`, `cassette` · Offline ✓ · [← all recipes](../../../README.md)
