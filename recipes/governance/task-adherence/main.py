"""Task adherence — is a proposed tool call on-task? A BYO-judge check at the tool_call stage.

Agents drift: the user asks to *book a flight*, and the model proposes `delete_account(...)`.
`judge.task_adherence(respond)` asks one question — *given the user's instruction and this proposed
tool call + arguments, is the action aligned with intent?* — reusing the judge helpers. In the SDK
the runner threads the user's turn into `Context.instruction` for you; here (door 1) we set it
ourselves. It defaults to `action="flag"` (advisory) — misalignment is a softer signal than a
content block. The judge is an ordinary instrumented call, so **its own spend is budgeted +
audited**; the call is cassette-recorded so this runs offline in CI with zero API calls.

Offline: the "judge model" is a fake, provider-shaped client. No key, no network.
Run:  uv run python recipes/governance/task-adherence/main.py
"""

import json
import os
from types import SimpleNamespace

from cendor import cassette
from cendor.core import bus, instrument
from cendor.guardrails import Context, evaluate, judge, rules
from cendor.tokenguard import report
from cendor.tokenguard import reset as tg_reset

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "adherence.json")

INSTRUCTION = "Book me a flight to Paris next Friday."


def judge_client() -> SimpleNamespace:
    """A fake instrumented 'small model' standing in for your real alignment judge. It reads the
    proposed call from the user message and returns the strict-JSON verdict task_adherence reads."""

    class Completions:
        def create(self, **kwargs):
            proposed = kwargs["messages"][-1]["content"].lower()
            aligned = "search_flights" in proposed or "book_flight" in proposed
            verdict = {
                "trip": not aligned,  # trip == misaligned
                "reason": "on-task: a flight search"
                if aligned
                else "off-task: unrelated to booking a flight",
            }
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(verdict)))],
                usage=SimpleNamespace(prompt_tokens=60, completion_tokens=12),
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def make_respond(client):
    """Your respond(system, user): prompt the (instrumented) judge model, return its reply."""

    def respond(system: str, user: str) -> str:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content

    return respond


def _screen(rail, tool: str, args: dict) -> str:
    ctx = Context(stage="tool_call", tool=tool, tool_args=args, instruction=INSTRUCTION)
    _cleaned, decs = evaluate([rail], "tool_call", args, ctx)
    flags = [d for d in decs if d.action == "flag"]
    return f"flagged: {flags[-1].reason}" if flags else "aligned"


def run_session(rail) -> list[tuple[str, str]]:
    """Screen both proposed calls in one cassette session (mode='auto' records the judge's model
    calls once, then replays them — so this stays offline in CI with zero API calls)."""

    def _session() -> list[tuple[str, str]]:
        return [
            ("aligned", _screen(rail, "search_flights", {"to": "Paris", "when": "next Friday"})),
            ("off-task", _screen(rail, "delete_account", {"user": "self"})),
        ]

    return cassette.use(FIXTURE, mode="auto")(_session)()


def main() -> None:
    bus._reset()
    tg_reset()
    check = judge.task_adherence(make_respond(judge_client()))
    rail = rules.llm_judge(check, stage="tool_call", action="flag", name="task_adherence")

    for label, outcome in run_session(rail):
        print(f"{label:9} -> {outcome}")

    spend = report()
    calls = sum(row["calls"] for row in spend.rows)
    tokens = sum(row["tokens"] for row in spend.rows)
    print(
        f"\nthe alignment judge's own spend is budgeted + attributed ({calls} call(s), {tokens} "
        "tokens) — the safety check is itself measured. No adherence-rate claim: it's a BYO judge, "
        "only as good as its model + prompt."
    )


if __name__ == "__main__":
    main()
