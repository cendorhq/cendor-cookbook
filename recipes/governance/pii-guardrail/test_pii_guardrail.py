"""Offline test for the pii-guardrail recipe — the model never sees the email in the clear."""

import importlib.util
import os
from types import SimpleNamespace

from cendor.core import bus, instrument
from cendor.guardrails import GuardrailTripped, install, uninstall

# Load the recipe's main.py under a unique name (avoids the shared 'main' module collision when
# pytest collects every governance recipe together).
_spec = importlib.util.spec_from_file_location(
    "pii_guardrail_recipe", os.path.join(os.path.dirname(__file__), "main.py")
)
_recipe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_recipe)
pii_guardrail = _recipe.pii_guardrail


def _client(calls):
    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def test_redacts_email_before_send():
    bus._reset()
    calls: list = []
    client = _client(calls)
    install([pii_guardrail(action="redact", stage="input")])
    try:
        client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": "ping bob@corp.example"}]
        )
    finally:
        uninstall()
    sent = calls[-1]["messages"][0]["content"]
    assert "bob@corp.example" not in sent and "<redacted>" in sent


def test_block_action_stops_pre_spend():
    bus._reset()
    calls: list = []
    client = _client(calls)
    install([pii_guardrail(action="block", stage="input")])
    try:
        raised = False
        try:
            client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "key sk-abcdEFGH1234ijklMNOP"}],
            )
        except GuardrailTripped:
            raised = True
        assert raised and calls == []  # blocked before the model was called — $0
    finally:
        uninstall()
