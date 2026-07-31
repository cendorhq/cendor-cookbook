"""openai-agents-sdk — budget + audit an agent loop the SDK fully owns.

The OpenAI Agents SDK drives the turn loop itself. You never see the individual calls — but the
SDK still talks to an OpenAI client, so `instrument()` that client and every turn lands on the
cendor bus: `tokenguard` prices each one under a pre-flight budget, and `acttrace` chains them
into a tamper-evident trail. The Agent/Runner code is untouched.

Offline: fake Responses client returns a tool call, then a final answer (2 turns). Run:
  uv run python recipes/frameworks/openai-agents-sdk/main.py
Record a real cassette: RECORD=1 OPENAI_API_KEY=sk-... uv run python .../main.py
"""

import asyncio
import os
from types import SimpleNamespace

from agents import Agent, OpenAIResponsesModel, Runner, function_tool, set_tracing_disabled
from cendor.acttrace import AuditLog, verify
from cendor.core import bus, instrument
from cendor.tokenguard import budget, reset
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)
from openai.types.responses.response_usage import (
    InputTokensDetails,
    OutputTokensDetails,
    ResponseUsage,
)

SIGNING_KEY = os.environ.get("CENDOR_DEMO_KEY", "demo-signing-key")
set_tracing_disabled(True)  # no trace upload — fully offline


def _resp(output):
    """One Responses-API envelope with the usage fields the SDK's own types demand.

    This is the fiddly part of faking an agent framework: the SDK parses its provider's response
    with real pydantic models, so a `SimpleNamespace` will not do — every required field has to be
    present and correctly typed. The usage numbers are what cendor prices; the rest is scaffolding.
    """
    return Response(
        id="resp",
        created_at=0,
        model="gpt-4o",
        object="response",
        tools=[],
        parallel_tool_calls=False,
        tool_choice="auto",
        output=output,
        usage=ResponseUsage(
            input_tokens=50,
            output_tokens=12,
            total_tokens=62,
            input_tokens_details=InputTokensDetails(cached_tokens=0, cache_write_tokens=0),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        ),
    )


def fake_responses_client():
    """A fake AsyncOpenAI whose `responses.create` returns tool-call then final answer.

    Two turns is the minimum that makes the point: the SDK owns the loop, so *you* never write the
    second call. Both still land on the bus, which is the only way a budget can cover a tool loop.
    """
    turn = {"n": 0}

    class Responses:
        async def create(self, **kwargs):
            turn["n"] += 1
            if turn["n"] == 1:
                return _resp(
                    [
                        ResponseFunctionToolCall(
                            type="function_call",
                            id="fc",
                            call_id="c1",
                            name="get_order_status",
                            arguments='{"order_id": "8823"}',
                        )
                    ]
                )
            return _resp(
                [
                    ResponseOutputMessage(
                        id="m",
                        type="message",
                        role="assistant",
                        status="completed",
                        content=[
                            ResponseOutputText(
                                type="output_text", text="Order 8823 was refunded.", annotations=[]
                            )
                        ],
                    )
                ]
            )

    return SimpleNamespace(responses=Responses())


@function_tool
def get_order_status(order_id: str) -> str:
    """An ordinary Agents-SDK tool. Nothing here is cendor-aware — that is the point of the seam."""
    return "refunded"


def record_live() -> None:  # RECORD=1 path — ships unrecorded; maintainer runs it once
    from cendor import cassette
    from openai import AsyncOpenAI

    client = instrument(AsyncOpenAI())
    agent = Agent(
        name="Support",
        instructions="Help with orders. Use tools when needed.",
        model=OpenAIResponsesModel(model="gpt-4o", openai_client=client),
        tools=[get_order_status],
    )
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "agents.json")

    @cassette.use(fixture, mode="record")
    def run():
        asyncio.run(Runner.run(agent, "Was order 8823 refunded?"))

    run()
    print(f"recorded live run to {fixture}")


def main() -> None:
    if os.environ.get("RECORD") == "1":
        record_live()
        return

    reset()
    # THE integration: one wrap of the client the SDK will use. The `Agent`/`Runner` code below is
    # verbatim OpenAI Agents SDK — no callback, no middleware, no subclass.
    client = instrument(fake_responses_client())
    seen: list = []
    bus.subscribe(seen.append)
    # `AuditLog` subscribes to the bus on construction, so every turn the Runner drives is chained
    # without the loop knowing. `detach()` below is what a long-lived process would NOT call.
    audit = AuditLog(system="agents_sdk", risk_tier="limited", signing_key=SIGNING_KEY)

    agent = Agent(
        name="Support",
        instructions="Help with orders. Use tools when needed.",
        model=OpenAIResponsesModel(model="gpt-4o", openai_client=client),
        tools=[get_order_status],
    )

    # One fuse for the WHOLE loop, not per call. That distinction is the reason a budget belongs
    # here rather than inside a tool: the SDK may drive five turns for one user question, and a
    # per-call cap would happily let all five through.
    with budget(usd=0.10):
        result = asyncio.run(Runner.run(agent, "Was order 8823 refunded?"))
    audit.detach()

    print(f"SDK final answer : {result.final_output!r}")
    print(f"SDK drove {len(seen)} turns (tool call -> final answer), all offline:")
    for i, call in enumerate(seen, 1):
        print(f"  turn {i}  {call.model}  ${call.cost.amount}")
    llm_entries = sum(1 for e in audit.entries if e.type == "llm_call")
    ok, _ = verify_chain(audit)
    print(f"acttrace chain   : {llm_entries} llm_call entries, verify: {ok}")

    # Measured ending. The failure mode worth guarding is the quiet one: if the SDK ever built its
    # own client internally instead of using the one passed in, `seen` would be empty, the run
    # would still print a perfectly good final answer, and no budget would have been enforced.
    assert len(seen) == 2, f"the SDK drove {len(seen)} captured turn(s), expected 2"
    assert all(c.cost and c.cost.amount > 0 for c in seen), "a turn reached the bus unpriced"
    assert llm_entries == 2, f"the chain recorded {llm_entries} llm_call entries, expected 2"
    assert ok is True, "the exported evidence pack failed verify()"


def verify_chain(audit) -> tuple:
    """Export the chain to a throwaway file and verify it — `verify()` reads a file, not memory."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "evidence.jsonl")
        audit.export(path, framework="eu_ai_act")
        return verify(path, key=SIGNING_KEY)


if __name__ == "__main__":
    main()
