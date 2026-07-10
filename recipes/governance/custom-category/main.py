"""Custom category — catch a request by *meaning*, not the exact words it used.

A keyword denylist blocks `"write python code"` but sails past the paraphrase `"create an app"`.
`rules.custom_category(name, examples, embed=...)` defines a category by a few example phrases and
trips when a turn is close enough to any of them (recording `metadata["category"]`/`["score"]`) —
the local, `$0` counterpart to Azure Content Safety's *rapid custom categories* (examples →
embedding search), with no cloud call and no training step.

`embed(text)` is bring-your-own. **In production, pass the zero-config offline default**
`embeddings.local_embedder()` (the `[embeddings]` extra — model2vec static embeddings, numpy-only,
no torch). To keep THIS recipe offline in CI with no model download, it uses a tiny lexical
bag-of-words `embed` defined below — enough to show the mechanism and the compose-with-keyword-deny
pattern. There is **no catch-rate claim**: a similarity threshold is a heuristic — keep it `flag`
until you calibrate on your own data.

Offline: no model, no network. Run:
    uv run python recipes/governance/custom-category/main.py
"""

import math
import re

from cendor.core import bus
from cendor.guardrails import apply, rules

_VOCAB = [
    "write",
    "create",
    "build",
    "make",
    "program",
    "app",
    "script",
    "code",
    "tool",
    "hello",
    "world",
]
_INDEX = {w: i for i, w in enumerate(_VOCAB)}


def embed(text: str) -> list[float]:
    """A tiny lexical bag-of-words vector (L2-normalized) — offline, dependency-free. NOT semantic:
    it matches shared *words*, so it demos the API + composition. Swap for
    `cendor.guardrails.embeddings.local_embedder()` for real (paraphrase) semantic matching."""
    vec = [0.0] * len(_VOCAB)
    for tok in re.findall(r"[a-z]+", text.lower()):
        if tok in _INDEX:
            vec[_INDEX[tok]] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def main() -> None:
    bus._reset()

    # A "code_requests" category defined by example — catches wordings a denylist would miss.
    category = rules.custom_category(
        "code_requests",
        ["write a program", "build an app", "create a script"],
        embed=embed,
        threshold=0.3,  # tuned for the weak lexical stand-in embed; a real embedder wants ~0.6-0.8
        action="flag",  # advisory until you calibrate the threshold on your data
        name="code_requests",
    )

    denylist = rules.keyword_deny(["write python code"], action="flag", name="denylist")

    for turn in ["write python code for hello world", "create a hello world app"]:
        gate = [denylist, category]
        decs = apply(gate, "input", turn)
        fired = {d.guardrail for d in decs}
        print(f"\n{turn!r}")
        deny_hit, cat_hit = "denylist" in fired, "code_requests" in fired
        print(f"  denylist fired: {deny_hit}   custom_category fired: {cat_hit}")
        for d in decs:
            print(f"    - {d.guardrail} {d.action}: {d.reason}")

    # The denylist misses the paraphrase; the semantic category catches it — the whole point.
    para = apply([denylist, category], "input", "create a hello world app")
    assert [d.guardrail for d in para] == ["code_requests"]  # ONLY the category fired
    assert para[0].metadata["category"] == "code_requests"
    print(
        "\nkeyword_deny is literal; custom_category is by meaning. Pass "
        "embeddings.local_embedder() (the [embeddings] extra) for real paraphrase matching — the "
        "bag-of-words embed here is just an offline stand-in. No catch-rate claim; calibrate first."
    )


if __name__ == "__main__":
    main()
