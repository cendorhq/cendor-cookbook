"""The governance recipe doubles as a test: the evidence pack must record the refusal, verify
clean, and fail verification after a single-byte edit."""

import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "eu_ai_act_recipe", os.path.join(os.path.dirname(__file__), "main.py")
)
_recipe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_recipe)


def test_evidence_pack_records_refusal_and_is_tamper_evident(tmp_path):
    r = _recipe.build_and_verify(str(tmp_path))
    assert r["blocked"], "the SSN-bearing prompt must be blocked pre-flight"
    assert r["refusal_in_pack"], "the refusal must appear in the exported evidence pack"
    assert r["verify_exit"] == 0, "the clean pack must verify (CLI exit 0)"
    assert r["tampered_exit"] == 1, "one edited byte must fail the CLI (exit 1)"
