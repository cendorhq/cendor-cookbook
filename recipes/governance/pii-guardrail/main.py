"""PII/secrets as a guardrail — the library-user pattern (no SDK required).

`cendor-guardrails` deliberately ships no PII detector: detection lives in `acttrace`'s catalogue,
so there is ONE detection engine, not two. You bridge it in ~3 lines with `rules.custom(fn)` calling
`acttrace.scan` / `acttrace.redact`. (The `cendor-sdk` ships this as `rules.pii()` / `secrets()` /
`entropy()` for agents — same idea, and it can gate tool *outputs* too.)

Offline: the "OpenAI" client is a fake provider-shaped object. No key, no network.
Run:  uv run python recipes/governance/pii-guardrail/main.py
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor.acttrace import AuditLog, Policy, redact, scan, verify
from cendor.core import instrument
from cendor.guardrails import Verdict, install, rules, uninstall


def pii_guardrail(policy=None, *, stage="input", action="redact"):
    """A guardrail that scans a payload with acttrace's catalogue and redacts/blocks/flags PII.

    Three lines of real logic — scan, decide, (redact) — wrapped as a deterministic guardrail. The
    reason names the categories found, never the raw value (acttrace reports counts only)."""
    policy = policy or Policy.default()  # redacts secrets + emails, flags the rest

    def check(payload, ctx):
        findings = [f for f in scan(payload, policy) if f.action != "allow"]
        if not findings:
            return None
        cats = ", ".join(sorted({f.category for f in findings}))
        if action == "redact":
            cleaned, _ = redact(payload, policy)
            return Verdict("redact", reason=f"pii: {cats}", replacement=cleaned)
        return Verdict(action, reason=f"pii: {cats}")

    return rules.custom(check, stage=stage, name="pii")


def fake_openai(calls: list) -> SimpleNamespace:
    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2),
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def main() -> None:
    calls: list = []
    client = instrument(fake_openai(calls))

    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "audit.jsonl")
        with AuditLog(system="assistant", path=path) as audit:
            install([pii_guardrail(action="redact", stage="input")])
            try:
                client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "email alice@example.com the invoice"}],
                )
                sent = calls[-1]["messages"][0]["content"]
                print(f"REDACTED before send: provider received {sent!r}")
            finally:
                uninstall()

        print("\nguardrail_decision entries in the audit chain:")
        for e in (e for e in audit.entries if e.type == "guardrail_decision"):
            print(f"  {e.payload['action']:<6} {e.payload['stage']:<6} {e.payload['guardrail']}")
        ok, _ = verify(path)
        print(f"\nchain verifies: {ok}  (the email never left the process in the clear)")


if __name__ == "__main__":
    main()
