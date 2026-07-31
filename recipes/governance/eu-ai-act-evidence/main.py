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
    """A stand-in for `OpenAI()` — the same `chat.completions.create` shape, no network.

    It always approves, deliberately: the evidence pack has to be able to record a decision the
    model made *and* a decision the policy refused, and only one of those needs a model at all.
    """

    class Completions:
        def create(self, **kwargs):
            msg = SimpleNamespace(content="Approved: within policy.")
            return SimpleNamespace(
                choices=[SimpleNamespace(message=msg)],
                usage=SimpleNamespace(prompt_tokens=60, completion_tokens=8),
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def _has_refusal(path: str) -> bool:
    """Is the REFUSAL inside the exported pack?

    This is the check auditors care about and the one most implementations get wrong: a system that
    logs only what it did produces an evidence trail in which a blocked request is indistinguishable
    from a request nobody ever made. The refusal has to be a first-class record.
    """
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

    # A guard on the `instrument()` seam runs BEFORE the request leaves — so a refusal costs $0 and
    # the model provably never saw the SSN. A check inside the handler would be too late twice over:
    # the data has already been sent, and the log would say "we sent it, then complained".
    def guard(call):  # pre-flight guard on the instrument() seam
        content = " ".join(str(m.get("content", "")) for m in getattr(call, "messages", []))
        if isinstance(call, LLMCall) and _SSN.search(content):
            audit.flag("SSN in prompt", action="blocked", severity="critical", data="us_ssn")
            raise PolicyViolation("blocked: SSN in prompt")
        return MISS

    # `add_interceptor` is process-global, which is why the `finally` below is not optional: leave
    # it installed and every later call in the same process is silently gated by this recipe.
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

    # The tamper demo. One byte, inside a payload that is hashed into the chain — not a deleted
    # line, not a reordered file. A chain that only caught coarse edits would not be worth much.
    data = Path(evidence).read_bytes()
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
        r = build_and_verify(d, verbose=True)

    # Measured ending. `tampered_exit` is the important one: a chain that verified BOTH files would
    # print an identical happy path and be worthless as evidence.
    assert r["blocked"] is True, "the SSN-bearing prompt reached the model"
    assert r["refusal_in_pack"] is True, "the refusal is not in the exported evidence pack"
    assert r["verify_exit"] == 0, "the clean evidence pack failed verification"
    assert r["tampered_exit"] != 0, "a one-byte edit still verified — the chain proves nothing"


if __name__ == "__main__":
    main()
