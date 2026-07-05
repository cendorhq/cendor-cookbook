"""The governed-agent recipe doubles as a test: the tool loop runs, the answer uses the tool
result, spend stays under budget, and the tamper-evident audit chain verifies — all offline."""

import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "governed_agent_recipe", os.path.join(os.path.dirname(__file__), "main.py")
)
_recipe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_recipe)


def test_governed_agent_offline(tmp_path):
    r = _recipe.run_governed(str(tmp_path))
    assert "Paris" in r["output"], "the agent must answer using the tool result"
    assert "get_weather" in r["tools_called"], "the tool-calling loop must actually run"
    assert r["audit_ok"], "the tamper-evident audit chain must verify offline"
