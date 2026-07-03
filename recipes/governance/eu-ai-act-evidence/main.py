"""eu-ai-act-evidence — a tamper-evident evidence pack for a high-risk decision.

A loan-triage agent. A pre-flight guard flags and BLOCKS an SSN-bearing prompt (the refusal is
recorded), a clean decision runs with human oversight, and the whole thing is exported as an
EU-AI-Act-tagged evidence pack. The acttrace CLI verifies it offline; editing a single byte makes
the CLI exit non-zero.

acttrace produces EVIDENCE to support compliance — not a guarantee, and not legal advice.

Offline: fake OpenAI-shaped client. Run:
  uv run python recipes/governance/eu-ai-act-evidence/main.py
"""

import json
import os
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor.acttrace import AuditLog
from cendor.acttrace.cli import main as acttrace_cli
from cendor.core import instrument
from cendor.core.instrument import MISS, add_interceptor, remove_interceptor
from cendor.core.types import LLMCall

SIGNING_KEY = os.environ.get("CENDOR_DEMO_KEY", "demo-signing-key")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


class PolicyViolation(Exception):
    """Your policy exception — raising it in a guard blocks the call (acttrace records the flag)."""


def fake_openai():
    class Completions:
        def create(self, **kwargs):
            msg = SimpleNamespace(content="Approved: within policy.")
            return SimpleNamespace(
                choices=[SimpleNamespace(message=msg)],
                usage=SimpleNamespace(prompt_tokens=60, completion_tokens=8),
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def _has_refusal(path: str) -> bool:
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("type") == "policy_flag" and rec.get("payload", {}).get("action") == "blocked":
            return True
    return False


def build_and_verify(workdir: str, verbose: bool = False) -> dict:
    raw = str(Path(workdir) / "audit.jsonl")
    evidence = str(Path(workdir) / "evidence.jsonl")
    audit = AuditLog(system="loan_triage", risk_tier="high", path=raw, signing_key=SIGNING_KEY)
    client = instrument(fake_openai())
    blocked = False

    def guard(call):  # pre-flight guard on the instrument() seam
        content = " ".join(str(m.get("content", "")) for m in getattr(call, "messages", []))
        if isinstance(call, LLMCall) and _SSN.search(content):
            audit.flag("SSN in prompt", action="blocked", severity="critical", data="us_ssn")
            raise PolicyViolation("blocked: SSN in prompt")
        return MISS

    add_interceptor(guard)
    try:
        with audit.decision(input="loan application (raw, may contain PII)", actor="agent"):
            try:
                client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "Applicant SSN 123-45-6789, approve?"}],
                )
            except PolicyViolation:
                blocked = True  # the model never saw it; the refusal is now in the log
        with audit.decision(input="loan application (screened)", actor="agent") as d:
            client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Income 90000, score 720. Approve?"}],
            )
            d.record(model="gpt-4o", prompt_id="loan_triage@v1")
            d.human_oversight(reviewer="risk_officer@bank", action="approved", note="within policy")
    finally:
        remove_interceptor(guard)

    audit.export(evidence, framework="eu_ai_act")
    audit.detach()
    refusal = _has_refusal(evidence)

    if verbose:
        print(f"SSN-bearing prompt blocked pre-flight : {blocked} (refusal recorded)")
        print(f"refusal is inside the evidence pack   : {refusal}")
        print("$ acttrace verify evidence.jsonl --key ***")
    exit_ok = acttrace_cli(["verify", evidence, "--key", SIGNING_KEY])  # 0 = pass

    data = Path(evidence).read_bytes()  # flip ONE byte inside a hashed payload
    i = data.index(b"approved")
    Path(evidence).write_bytes(data[:i] + b"A" + data[i + 1 :])
    if verbose:
        print("(1 byte edited, then re-verify)")
        print("$ acttrace verify evidence.jsonl --key ***")
    exit_tampered = acttrace_cli(["verify", evidence, "--key", SIGNING_KEY])  # 1 = fail

    if verbose:
        print(f"clean exit {exit_ok}  ->  tampered exit {exit_tampered}")
    return {
        "blocked": blocked,
        "refusal_in_pack": refusal,
        "verify_exit": exit_ok,
        "tampered_exit": exit_tampered,
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        build_and_verify(d, verbose=True)


if __name__ == "__main__":
    main()
