"""ollama-local — a fully budgeted, recorded, audited turn on a $0 local model.

The whole Cendor stack works with no cloud at all. Here one Ollama turn is priced (llama3 is
$0.00 in the snapshot), budgeted, recorded to a cassette, and written to a tamper-evident audit
trail — with no network and no key. In CI it runs against a fake `ollama.Client().chat` shape;
locally, `ollama pull llama3` and set OLLAMA_LIVE=1 to swap in the real client (one line).

Run (offline, fake client):
  uv run python recipes/providers/ollama-local/main.py
Run against a local daemon:
  OLLAMA_LIVE=1 uv run python recipes/providers/ollama-local/main.py
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
_calls = {"n": 0}


def make_client():
    if os.environ.get("OLLAMA_LIVE"):
        import ollama  # real local daemon; needs `ollama pull llama3`

        return instrument(ollama.Client())

    def chat(**kwargs):  # fake `ollama.Client().chat` — a callable, returns a dict
        _calls["n"] += 1
        return {
            "model": "llama3",
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
                client.chat(model="llama3", messages=[{"role": "user", "content": "summarize"}])
                dec.record(model="llama3")

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
    cost = "0.00" if call.cost is not None and call.cost.amount == 0 else str(call.cost.amount)
    print(
        f"turn   : llama3 (local) · {call.usage.input_tokens} in + {call.usage.output_tokens} out"
        f" · cost: ${cost} (local)"
    )
    print(f"budget : ${spent.amount} spent of $1.00 cap")
    print(f"audit  : decision recorded, verify: {ok}")
    print(f"cassette: recorded ({rec_calls} call) -> replayed ({replay_calls} calls, offline)")


if __name__ == "__main__":
    main()
