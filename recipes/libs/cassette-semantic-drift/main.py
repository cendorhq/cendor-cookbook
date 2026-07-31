"""cassette-semantic-drift — `drift()` compares bytes; you usually want to compare meaning.

Models do not produce bytes twice. So a scheduled `rerecord` against a live provider reports a
divergence on nearly every entry, most of them a harmless rewording — and a signal that is mostly
noise gets muted, which is the same as having no signal.

`semantic_drift(threshold, scorer)` filters that list: it scores recorded-vs-live and keeps only the
divergences **below** the threshold. The scorer is pluggable on purpose, and this recipe is mostly
about *why* it has to be.

**The measured result, which is not the intuitive one.** Both bundled-by-default paths score
*surface* similarity, and on the pair below they get it exactly backwards:

  a harmless paraphrase             scores LOW  (few shared words)
  "30 days" changed to "14 days"    scores HIGH (one token differs)

So a surface scorer keeps the noise and drops the thing you needed to see. That is not a bug in
`lexical_score` — it is what lexical similarity *is*. It is the reason `scorer=` exists, and the
reason this recipe prints the numbers instead of asserting a happy ending.

For real semantic scoring offline, install `cendor-cassette[embeddings]` and pass
`local_embedding_scorer()` (model2vec static embeddings — no torch, no key, no network at score
time). The cookbook stays dependency-light, so this recipe shows the **seam** with a toy embedder
and reports honestly that a toy embedder does not fix the problem either.

  uv run python recipes/libs/cassette-semantic-drift/main.py
"""

import hashlib
import math
import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor import cassette
from cendor.cassette import embedding_scorer, lexical_score, semantic_match
from cendor.core import instrument

MODEL = "gpt-4o"
ASK = [{"role": "user", "content": "what is the refund window?"}]

RECORDED = "Refunds are available within 30 days of delivery."
REWORDED = "You can request a refund up to 30 days after the item arrives."  # same meaning
CHANGED = "Refunds are available within 14 days of delivery."  # different meaning


def provider(answer: str):
    class Completions:
        def create(self, **kw):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=answer))],
                usage=SimpleNamespace(prompt_tokens=24, completion_tokens=12),
                model=MODEL,
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def toy_embed(texts: list[str]) -> list[list[float]]:
    """A hashed bag-of-words embedder — deterministic, offline, and DELIBERATELY crude.

    Here to show the seam: `embedding_scorer` takes any `texts -> vectors` callable, so cassette
    binds no model and gains no dependency. It is **not** a semantic model, and the output below
    says so.
    """
    dim = 96
    vectors = []
    for text in texts:
        vec = [0.0] * dim
        for word in text.lower().replace(".", " ").split():
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vectors.append([v / norm for v in vec])
    return vectors


def rerecord(tape: Path, answer: str) -> int:
    with cassette.using(str(tape), mode="rerecord"):
        provider(answer).chat.completions.create(model=MODEL, messages=ASK)
    return len(cassette.drift())


def main() -> None:
    tape = Path(tempfile.mkdtemp(prefix="cendor-recipe-")) / "policy.json"
    with cassette.using(str(tape), mode="record"):
        provider(RECORDED).chat.completions.create(model=MODEL, messages=ASK)

    embed = embedding_scorer(toy_embed)
    rows = []
    for label, live in (("paraphrase", REWORDED), ("real change", CHANGED)):
        byte_level = rerecord(tape, live)
        rows.append(
            (
                label,
                byte_level,
                lexical_score(live, RECORDED),
                len(cassette.semantic_drift(0.8)),
                embed(live, RECORDED),
                len(cassette.semantic_drift(0.8, embed)),
            )
        )

    print(f"recorded    : {RECORDED!r}\n")
    print(f"{'live answer':<12} {'drift()':<8} {'lexical':<8} {'kept':<5} {'toy-embed':<10} kept")
    for label, byte_level, lex, lex_kept, emb, emb_kept in rows:
        print(f"{label:<12} {byte_level:<8} {lex:<8.2f} {lex_kept:<5} {emb:<10.2f} {emb_kept}")

    print(
        "\nread the two 'kept' columns: the PARAPHRASE survives the filter and the REAL CHANGE is"
    )
    print("dropped, under both scorers. A surface scorer measures shared words, so a rewrite looks")
    print("like a big change and one edited number looks like none. That is the whole reason")
    print("semantic_drift() takes scorer= - install cendor-cassette[embeddings] and pass")
    print("local_embedding_scorer() for a real one (model2vec, offline, no key).")

    print("\nwhere the lexical default IS the right tool - asserting an answer means roughly X:")
    for expected in ("refund within 30 days", "delivery"):
        print(f"  semantic_match(recorded, {expected!r}) = {semantic_match(RECORDED, expected)}")

    negation = "We will not offer a refund."
    print("\nhonest limit, measured rather than hidden:")
    print(
        f"  lexical_score({negation!r}, 'offer a refund') = "
        f"{lexical_score(negation, 'offer a refund'):.2f} -> match "
        f"{semantic_match(negation, 'offer a refund')}"
    )
    print("  keyword containment cannot see a negation. Do not use it as a safety check.")

    lex_paraphrase, lex_changed = rows[0][2], rows[1][2]
    assert all(r[1] == 1 for r in rows), (
        "rerecord should report one byte-level divergence each time"
    )
    assert lex_paraphrase < lex_changed, "the measured inversion this recipe teaches has changed"
    assert semantic_match(RECORDED, "refund within 30 days"), "the lexical default missed a match"
    assert semantic_match(negation, "offer a refund"), "the documented negation limit changed"


if __name__ == "__main__":
    main()
