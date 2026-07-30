"""ollama-local — a fully budgeted, recorded, audited turn on a $0 local model.

The whole Cendor stack works with no cloud at all. Here one Ollama turn is priced (llama3 is
$0.00 in the snapshot), budgeted, recorded to a cassette, and written to a tamper-evident audit
trail — with no network and no key. In CI it runs against a fake `ollama.Client().chat` shape;
locally, pull a model and set OLLAMA_LIVE=1 to swap in the real client (one line).

Run (offline, fake client):
  uv run python recipes/providers/ollama-local/main.py
Run against a local daemon:
  ollama pull llama3
  OLLAMA_LIVE=1 uv run --with ollama python recipes/providers/ollama-local/main.py
  # a different local model: OLLAMA_MODEL=llama3.2 OLLAMA_LIVE=1 uv run --with ollama python ...
"""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor import cassette
from cendor.acttrace import AuditLog, verify
from cendor.core import bus, instrument
from cendor.tokenguard import budget

SIGNING_KEY = os.environ.get("CENDOR_DEMO_KEY", "demo-signing-key")
# The local model id. Every other live switch in this repo reads an env var; this one hard-coded
# `llama3`, so a box with only `llama3.2` pulled had to fetch a second model to run the recipe.
MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
_calls = {"n": 0}


def make_client():
    if os.environ.get("OLLAMA_LIVE"):
        import ollama  # real local daemon; needs `ollama pull <MODEL>` first

        return instrument(ollama.Client())

    def chat(**kwargs):  # fake `ollama.Client().chat` — a callable, returns a dict
        _calls["n"] += 1
        return {
            "model": MODEL,
            "message": {"role": "assistant", "content": "Here is your summary."},
            "prompt_eval_count": 26,
            "eval_count": 298,
        }

    return instrument(SimpleNamespace(chat=chat))


def main() -> None:
    seen: list = []
    bus.subscribe(seen.append)
    client = make_client()

    with tempfile.TemporaryDirectory() as d:
        cass = str(Path(d) / "turn.json")
        audit = AuditLog(system="local_agent", risk_tier="limited", signing_key=SIGNING_KEY)
        evidence = str(Path(d) / "evidence.jsonl")

        def turn():
            with audit.decision(input="summarize the notes", actor="agent") as dec:
                client.chat(model=MODEL, messages=[{"role": "user", "content": "summarize"}])
                dec.record(model=MODEL)

        _calls["n"] = 0
        with budget(usd=1.00) as b:  # a $1 cap it will never approach
            cassette.use(cass, mode="record")(turn)()  # first run records
        rec_calls, spent = _calls["n"], b.spent

        _calls["n"] = 0
        cassette.use(cass, mode="replay")(turn)()  # replay: zero calls
        replay_calls = _calls["n"]

        audit.export(evidence, framework="eu_ai_act")
        audit.detach()
        ok, _ = verify(evidence, key=SIGNING_KEY)

    call = seen[0]
    # ⚠️ `call.cost` is None for an UNPRICED model id, and a local id often is one: `llama3` has a
    # $0.00 row in the bundled snapshot, `llama3.2:latest` has no row at all. The old one-liner
    # here read `call.cost.amount` on the else branch and crashed with AttributeError the moment
    # OLLAMA_MODEL pointed at anything unpriced. Say "unpriced" rather than print a $0.00 that was
    # never measured — the token counts and the audit chain are exact either way.
    if call.cost is None:
        cost = "unpriced (no rate for this id — token counts are still exact)"
    else:
        cost = f"${'0.00' if call.cost.amount == 0 else call.cost.amount}"
    print(
        f"turn   : {MODEL} (local) · {call.usage.input_tokens} in + {call.usage.output_tokens} out"
        f" · cost: {cost}"
    )
    print(f"budget : ${spent.amount} spent of $1.00 cap")
    print(f"audit  : decision recorded, verify: {ok}")
    # `_calls` only increments inside the FAKE client, so under OLLAMA_LIVE=1 the recorded count
    # is 0 by construction — a real call was made, this counter cannot see it. Say which one this
    # is rather than printing "recorded (0 call)" after a real call.
    live = bool(os.environ.get("OLLAMA_LIVE"))
    counted = "not counted (live client)" if live else f"{rec_calls} call"
    print(f"cassette: recorded ({counted}) -> replayed ({replay_calls} calls, offline)")


if __name__ == "__main__":
    main()
