"""acttrace quickstart — a tamper-evident record of what your agent did.

"Prove what the agent saw and decided" is a real ask from compliance, security, and your own
future self. acttrace hash-chains every event; verify() re-walks the chain, and a single edited
byte breaks it at a known sequence number.

Offline: writes/reads a local signed log. Run:
  uv run python recipes/quickstarts/acttrace/main.py
"""

import os
import tempfile
from pathlib import Path

from cendor.acttrace import AuditLog, verify

# Demo signing key: env override with a fallback so the recipe is green out of the box.
# In production, load this from your secret manager — never commit a real key.
SIGNING_KEY = os.environ.get("CENDOR_DEMO_KEY", "demo-signing-key")


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        raw = str(Path(d) / "audit.jsonl")
        evidence = str(Path(d) / "evidence.jsonl")

        audit = AuditLog(
            system="support_bot", risk_tier="limited", path=raw, signing_key=SIGNING_KEY
        )
        with audit.decision(input="summarize the quarterly refunds report", actor="agent") as d1:
            d1.record(model="gpt-4o", prompt_id="summarize@v2")
            d1.human_oversight(reviewer="ops@acme", action="approved", note="spot-checked output")
        audit.export(evidence, framework="eu_ai_act")
        audit.detach()  # flush + close the file before we read/verify it

        ok, detail = verify(evidence, key=SIGNING_KEY)
        print(f"verify: {ok}  ({detail})")

        # Flip ONE byte inside a hashed payload: 'quarterly' -> 'Quarterly'.
        data = Path(evidence).read_bytes()
        i = data.index(b"quarterly")
        Path(evidence).write_bytes(data[:i] + b"Q" + data[i + 1 :])

        ok2, detail2 = verify(evidence, key=SIGNING_KEY)
        print("(1 byte flipped)")
        print(f"verify: {ok2}  ({detail2})")

        assert ok and not ok2, "clean log verifies; tampered log must fail"


if __name__ == "__main__":
    main()
