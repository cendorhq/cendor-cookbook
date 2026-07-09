"""Offline test for the task-adherence recipe: the alignment judge's model calls replay from the
committed cassette in strict mode — zero live calls — and the verdicts gate correctly (aligned call
passes, off-task call is flagged).

Re-record after an intentional change:  RERECORD=1 uv run pytest <this recipe dir>
"""

import importlib.util
import json
import os
from types import SimpleNamespace

from cendor import cassette
from cendor.core import bus, instrument
from cendor.guardrails import Context, evaluate, judge, rules

_spec = importlib.util.spec_from_file_location(
    "task_adherence_recipe", os.path.join(os.path.dirname(__file__), "main.py")
)
_recipe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_recipe)
FIXTURE, INSTRUCTION = _recipe.FIXTURE, _recipe.INSTRUCTION

MODE = "record" if os.environ.get("RERECORD") else "replay"


def _counting_judge_client(calls: dict):
    class Completions:
        def create(self, **kwargs):
            calls["n"] += 1
            proposed = kwargs["messages"][-1]["content"].lower()
            aligned = "search_flights" in proposed or "book_flight" in proposed
            verdict = {"trip": not aligned, "reason": "on-task" if aligned else "off-task"}
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(verdict)))],
                usage=SimpleNamespace(prompt_tokens=60, completion_tokens=12),
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def _screen(rail, tool, args):
    ctx = Context(stage="tool_call", tool=tool, tool_args=args, instruction=INSTRUCTION)
    _cleaned, decs = evaluate([rail], "tool_call", args, ctx)
    return "flagged" if any(d.action == "flag" for d in decs) else "aligned"


def test_task_adherence_replays_offline_and_gates():
    bus._reset()
    calls = {"n": 0}
    check = judge.task_adherence(_recipe.make_respond(_counting_judge_client(calls)))
    rail = rules.llm_judge(check, stage="tool_call", action="flag", name="task_adherence")

    def _session():  # must reproduce main()'s exact proposed calls so the cassette requests match
        aligned = _screen(rail, "search_flights", {"to": "Paris", "when": "next Friday"})
        off_task = _screen(rail, "delete_account", {"user": "self"})
        return aligned, off_task

    aligned, off_task = cassette.use(FIXTURE, mode=MODE)(_session)()
    assert aligned == "aligned"
    assert off_task == "flagged"
    if MODE == "replay":
        assert calls["n"] == 0  # both judge calls served from the cassette — no live model call
