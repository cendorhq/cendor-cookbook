"""gemini — capture, budget and audit `google-genai` calls (a different usage shape entirely).

Gemini does not report usage the way OpenAI does: there is no `usage`, there is `usage_metadata`
with `prompt_token_count` / `candidates_token_count`, and the call is
`client.models.generate_content(model=…, contents=…)`. `instrument()` normalizes all of it, so the
budget, the report and the audit chain are written exactly once — the same three lines you would
write for OpenAI.

Offline: fake `genai.Client()` shape. Run:
  uv run python recipes/providers/gemini/main.py

Record a real cassette (maintainer, needs a key + `google-genai` installed):
  RECORD=1 uv run --with google-genai python recipes/providers/gemini/main.py
  # env: GOOGLE_API_KEY (or GEMINI_API_KEY) · GEMINI_MODEL optional
"""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor.acttrace import AuditLog, verify
from cendor.core import bus, instrument
from cendor.tokenguard import BudgetExceeded, budget, report, reset, track

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
SIGNING_KEY = os.environ.get("CENDOR_DEMO_KEY", "demo-signing-key")


def fake_genai():
    """Stand-in for `genai.Client()` — the real `models.generate_content` shape, no network.

    Note what is being faked: `usage_metadata`, not `usage`. That difference is the whole reason a
    normalizing seam is worth having.
    """

    class Models:
        def generate_content(self, **kwargs):
            return SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=SimpleNamespace(parts=[SimpleNamespace(text="Within policy.")])
                    )
                ],
                usage_metadata=SimpleNamespace(
                    prompt_token_count=980,
                    candidates_token_count=210,
                    cached_content_token_count=0,
                ),
            )

    return SimpleNamespace(models=Models())


def ask(client, prompt: str):
    return client.models.generate_content(model=MODEL, contents=prompt)


def record_live() -> None:  # the RECORD=1 path — ships unrecorded; needs YOUR key
    from cendor import cassette
    from google import genai  # lazily imported; the offline path needs no provider SDK

    client = instrument(genai.Client())  # reads GOOGLE_API_KEY / GEMINI_API_KEY
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "gemini.json")

    @cassette.use(fixture, mode="record")  # secrets are redacted on write
    def one_call():
        ask(client, "Reply with the single word: pong")

    one_call()
    print(f"recorded live call to {fixture}")


def main() -> None:
    if os.environ.get("RECORD") == "1":
        record_live()
        return

    reset()
    seen: list = []
    bus.subscribe(seen.append)
    client = instrument(fake_genai())

    with tempfile.TemporaryDirectory() as d:
        evidence = str(Path(d) / "evidence.jsonl")
        audit = AuditLog(system="triage", risk_tier="limited", signing_key=SIGNING_KEY)

        # One turn: attributed, budgeted, audited — nothing Gemini-specific in this block.
        with budget(usd=0.05, on_exceed="block"), track(feature="triage"):
            with audit.decision(input="policy question", actor="agent") as dec:
                ask(client, "Is this request within policy?")
                dec.record(model=MODEL)

        # Then the cap the second turn cannot afford — refused before the call is made.
        blocked = ""
        try:
            with budget(usd=0.000_01, on_exceed="block"):
                ask(client, "And this one?")
        except BudgetExceeded as e:
            blocked = str(e)

        audit.export(evidence, framework="eu_ai_act")
        audit.detach()
        ok, detail = verify(evidence, key=SIGNING_KEY)

    call = seen[0]
    print(f"provider : {call.provider}   (inferred from the client's shape, not configured)")
    print(f"model    : {call.model}")
    print(
        f"usage    : {call.usage.input_tokens} in + {call.usage.output_tokens} out"
        f"   (mapped from usage_metadata.prompt_token_count / .candidates_token_count)"
    )
    print(f"cost     : ${call.cost.amount if call.cost else None}")
    rows = list(report(group_by=["feature"]))
    print(f"spend    : {rows[0]['tags']} {rows[0]['calls']} call(s) -> ${rows[0]['usd'].amount}")
    print(f"refused  : {blocked}")
    print(f"audit    : verify={ok} — {detail}")


if __name__ == "__main__":
    main()
