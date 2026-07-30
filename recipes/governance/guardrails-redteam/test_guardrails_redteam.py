"""Offline test for the guardrails-redteam recipe — a deterministic corpus, no model, no network.

Added 2026-07-30 (defect C7): this recipe and `guardrails-policy` were the only two under
`recipes/governance/` with no test file, so CI ran their `main.py` and nothing else.

What is worth pinning here is **honesty about the measurement**, not a trip rate: the corpus holds
benign cases as well as attacks, so a gate that blocked everything would score 100% on attacks and
be useless. These tests assert the shape of the report and that benign traffic is not caught — the
two things a published trip rate is meaningless without.
"""

import importlib.util
import os

from cendor.core import bus
from cendor.guardrails import rules

_spec = importlib.util.spec_from_file_location(
    "guardrails_redteam_recipe", os.path.join(os.path.dirname(__file__), "main.py")
)
_recipe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_recipe)


def _report():
    gate = rules.keyword_deny(
        ["ignore previous instructions", "disregard your rules", "pretend you have no"],
        action="block",
    )
    return _recipe.run_redteam([gate], _recipe.CORPUS)


def test_the_corpus_carries_benign_cases_too():
    """A trip rate measured only against attacks cannot detect a gate that blocks everything."""
    labels = {c.label for c in _recipe.CORPUS}
    assert "benign" in labels, labels
    assert len(labels) > 1, "an attacks-only corpus makes the number unfalsifiable"


def test_report_shape_is_per_category_and_countable():
    report = _report()
    assert report.by_category, "the report must break down by category"
    for _category, (attacks, caught) in report.by_category.items():
        assert attacks >= 0 and 0 <= caught <= attacks, (attacks, caught)
    assert isinstance(report.summary(), str) and report.summary().strip()


def test_a_deterministic_keyword_gate_catches_its_own_phrases_and_misses_novel_ones():
    """The recipe's point: a keyword floor is free and PARTIAL. It must catch the phrases it lists,
    and it must NOT score 100% — otherwise the corpus is not exercising anything."""
    report = _report()
    total_attacks = sum(a for a, _ in report.by_category.values())
    total_caught = sum(c for _, c in report.by_category.values())
    assert total_attacks > 0
    assert total_caught > 0, "the gate should catch the phrases it explicitly denies"
    assert total_caught < total_attacks, (
        "a keyword floor cannot catch a novel jailbreak — a 100% score here means the corpus was "
        "overfitted to the denylist, the dishonest number this recipe warns about"
    )


def test_main_runs_offline():
    bus._reset()
    _recipe.main()  # prints a measurement; no network, no key
