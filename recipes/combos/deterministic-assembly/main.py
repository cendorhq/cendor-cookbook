"""deterministic-assembly — why a replay is worth anything at all.

A cassette replays by hashing the request. If your prompt assembly is not deterministic — if
eviction ties break on dict order, or a summarizer paraphrases differently each run — then run 2
hashes differently, the cassette misses, and you are back to paying for a live call. Worse, it
misses *silently*: you assume the test is offline and it is not.

contextkit's packing is deterministic by construction. This recipe measures it rather than claiming
it: the same 40-turn conversation is assembled twice into a budget too small to hold it (so real
eviction happens — most of the history is dropped, which is where a non-deterministic packer would
diverge), the two assembled prompts are hashed, and then a cassette recorded from run 1 is replayed
against run 2's prompt with a client that raises if it is ever reached.

Change one character of the input and the hash changes; that is the property that makes a recorded
test suite trustworthy. Offline, keyless.

  uv run python recipes/combos/deterministic-assembly/main.py
"""

import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor import cassette
from cendor.contextkit import Block, Context
from cendor.core import instrument

MODEL = "gpt-4o"


def build() -> Context:
    """The same context, built from scratch each time — as a real request handler would."""
    turns = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}: " + "detail " * 12}
        for i in range(40)
    ]
    return (
        Context(budget_tokens=400, model=MODEL, reserve_output=100)
        .add(Block("You are terse.", role="system", pin=True, priority=100))
        .add(Block(messages=turns, evict="drop_oldest"))
    )


def fingerprint(messages: list[dict]) -> str:
    return hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()


def client(provider):
    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=provider)))


class Provider:
    def __init__(self, *, boom: bool = False) -> None:
        self.boom = boom
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.boom:
            raise AssertionError("run 2 hashed differently — assembly is not deterministic")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="acknowledged"))],
            usage=SimpleNamespace(prompt_tokens=640, completion_tokens=6),
        )


def main() -> None:
    ctx1, ctx2 = build(), build()
    run1, run2 = ctx1.assemble(), ctx2.assemble()
    report = ctx1.report()
    evicted = [d for d in report.decisions if d.action != "kept"]

    tmp = Path(tempfile.mkdtemp(prefix="cendor-recipe-"))
    tape = tmp / "conversation.json"

    live = Provider()
    with cassette.using(str(tape), mode="record"):
        client(live).chat.completions.create(model=MODEL, messages=run1)

    boom = Provider(boom=True)
    with cassette.using(str(tape), mode="replay"):
        out = client(boom).chat.completions.create(model=MODEL, messages=run2)

    # One character changed at the source must change the fingerprint — the negative control.
    nudged = json.loads(json.dumps(run2))
    nudged[-1]["content"] += "."

    print(f"assembled   : {report.used} tokens of {report.budget} - {evicted[0].note}")
    print(f"run 1 hash  : {fingerprint(run1)[:16]}…")
    print(f"run 2 hash  : {fingerprint(run2)[:16]}…   identical: {run1 == run2}")
    same = fingerprint(nudged) == fingerprint(run2)
    print(f"one char    : {fingerprint(nudged)[:16]}…   identical: {same}")
    print(
        f"replay      : provider called {boom.calls}x, answered {out.choices[0].message.content!r}"
    )

    assert run1 == run2, "assembly is not byte-deterministic across runs"
    assert evicted, "nothing was evicted - this would prove determinism on an easy case only"
    assert boom.calls == 0, "run 2 missed the cassette — the assembled prompt hashed differently"
    assert fingerprint(nudged) != fingerprint(run2), "the fingerprint ignored a real change"


if __name__ == "__main__":
    main()
