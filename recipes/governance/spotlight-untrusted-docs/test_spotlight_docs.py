"""Offline test for the spotlight-untrusted-docs recipe: a pure string transform — no model, no
network. The doc is wrapped (redact), the following denylist still flags the exfil URL, and the
decision carries the reserved `redacted` annotation."""

import importlib.util
import os

from cendor.core import bus
from cendor.guardrails import evaluate, rules

_spec = importlib.util.spec_from_file_location(
    "spotlight_docs_recipe", os.path.join(os.path.dirname(__file__), "main.py")
)
_recipe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_recipe)


def test_spotlight_wraps_and_composes_with_a_denylist():
    bus._reset()
    chain = [
        rules.spotlight(stage="tool_output"),
        rules.url_deny(["evil.example"], stage="tool_output", action="flag"),
    ]
    cleaned, decs = evaluate(chain, "tool_output", _recipe.RETRIEVED_DOC)
    assert cleaned.startswith("<untrusted>\n") and cleaned.endswith("\n</untrusted>")
    assert [d.action for d in decs] == ["redact", "flag"]
    assert decs[0].metadata.get("redacted") is True


def test_main_runs_offline():
    _recipe.main()  # asserts inside; no network
