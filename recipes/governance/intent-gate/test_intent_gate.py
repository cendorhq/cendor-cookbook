"""Offline test for the intent-gate recipe: a deterministic keyword classifier, no model, no net.
The off-topic request is flagged before send; an in-scope one passes; deny-mode blocks."""

import importlib.util
import os

import pytest
from cendor.core import bus
from cendor.guardrails import GuardrailTripped, apply

_spec = importlib.util.spec_from_file_location(
    "intent_gate_recipe", os.path.join(os.path.dirname(__file__), "main.py")
)
_recipe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_recipe)


def test_allow_mode_flags_off_topic_and_passes_on_topic():
    bus._reset()
    gate = _recipe.rules.intent(
        ["support", "billing"],
        classify=_recipe.classify,
        mode="allow",
        threshold=0.15,
        action="flag",
    )
    assert apply([gate], "input", "I can't reset my password") == []  # in scope
    decs = apply([gate], "input", "write a poem about the ocean")  # off topic
    assert decs and decs[0].action == "flag" and decs[0].metadata["intent"]


def test_deny_mode_blocks_an_off_limits_topic():
    bus._reset()
    deny = _recipe.rules.intent(
        ["billing"], classify=_recipe.classify, mode="deny", threshold=0.15, action="block"
    )
    with pytest.raises(GuardrailTripped):
        apply([deny], "input", "I want a refund on my last charge")


def test_main_runs_offline():
    _recipe.main()  # asserts inside; no network
