"""governed-agent — a governed agent in ~10 lines, running OFFLINE.

The whole point of cendor-sdk: a real tool-calling loop with cost budgets, a tamper-evident audit
chain, and PII redaction as the FOUNDATION, not add-ons. Everything here is real except the model
call, which a tiny stub client serves so the recipe needs no network and no API key.

In production you drop the ``client=`` argument and set ``OPENAI_API_KEY``:

    agent = Agent(name="assistant", model="gpt-4o", tools=[get_weather])

Run it:
  uv run python recipes/sdk/governed-agent/main.py
  uv run pytest recipes/sdk/governed-agent
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor.core import instrument
from cendor.sdk import Agent, AuditLog, Policy, budget, guard, run, tool, verify


@tool
def get_weather(city: str) -> str:
    """Current weather for a city."""
    return f"Sunny in {city}"


def _stub_client() -> object:
    """OpenAI-shaped stub: turn 1 calls the tool, turn 2 answers. No network, no key.

    ``instrument()`` identifies a client by *shape*, so a SimpleNamespace with the same
    ``chat.completions.create`` surface is all the SDK needs — the same trick Cendor's own
    tests use. The canned ``usage`` is normalized and priced from the bundled offline snapshot.
    """
    turns = iter(
        [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="tool_calls",
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    id="call_1",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="get_weather", arguments='{"city": "Paris"}'
                                    ),
                                )
                            ],
                        ),
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=52, completion_tokens=12),
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(content="It's sunny in Paris.", tool_calls=None),
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=88, completion_tokens=9),
            ),
        ]
    )

    class Completions:
        def create(self, **kwargs: object) -> object:
            return next(turns)

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def run_governed(workdir: str, verbose: bool = False) -> dict:
    audit_path = str(Path(workdir) / "audit.jsonl")

    # --- a governed agent, in ~10 lines ----------------------------------------------------------
    agent = Agent(
        name="assistant",
        model="gpt-4o",
        tools=[get_weather],
        instructions="Answer using tools when helpful.",
        client=_stub_client(),  # offline stub — omit in production
    )
    log = AuditLog(system="support", risk_tier="limited", path=audit_path)
    with budget(usd=0.25, on_exceed="block"), guard(Policy.default(), audit=log):
        result = run(agent, "What's the weather in Paris?", audit=log)
    log.detach()
    # ---------------------------------------------------------------------------------------------

    ok, detail = verify(audit_path)  # the audit chain re-walks and verifies OFFLINE
    tools_called = [s.name for s in result.tool_steps]

    if verbose:
        print("output      :", result.output)
        print("cost        :", result.cost, " (budget $0.25, enforced pre-flight)")
        print("usage       :", result.usage)
        print("tools called:", tools_called)
        print("audit chain :", ok, "—", detail)
        print("audit file  :", audit_path)

    return {
        "output": result.output,
        "cost": result.cost,
        "tools_called": tools_called,
        "audit_ok": ok,
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        run_governed(d, verbose=True)


if __name__ == "__main__":
    main()
