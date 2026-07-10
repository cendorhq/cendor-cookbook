"""Offline test for the custom-category recipe: a lexical bag-of-words embed, no model, no network.
The paraphrase that a keyword denylist misses is caught by the semantic category."""

import importlib.util
import os

from cendor.core import bus
from cendor.guardrails import apply

_spec = importlib.util.spec_from_file_location(
    "custom_category_recipe", os.path.join(os.path.dirname(__file__), "main.py")
)
_recipe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_recipe)


def test_category_catches_the_paraphrase_a_denylist_misses():
    bus._reset()
    category = _recipe.rules.custom_category(
        "code_requests",
        ["write a program", "build an app", "create a script"],
        embed=_recipe.embed,
        threshold=0.3,
        action="flag",
        name="code_requests",
    )
    denylist = _recipe.rules.keyword_deny(["write python code"], action="flag", name="denylist")
    decs = apply([denylist, category], "input", "create a hello world app")
    assert [d.guardrail for d in decs] == ["code_requests"]  # only the semantic category fires
    assert decs[0].metadata["category"] == "code_requests"
    assert decs[0].metadata["score"] >= 0.3


def test_main_runs_offline():
    _recipe.main()  # asserts inside; no network
