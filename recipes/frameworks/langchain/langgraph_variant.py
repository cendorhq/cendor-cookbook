"""langgraph_variant — a 2-node LangGraph agent whose tool calls join the same stream.

The LLM node uses an instrumented ChatOpenAI; the tool node calls a function wrapped with
`instrument_tool()`. Both the model call and the tool call land on the same cendor bus — so one
subscriber sees the whole turn, model + tools, without touching LangGraph's control flow.

Offline: fake OpenAI-shaped client. Run:
  uv run python recipes/frameworks/langchain/langgraph_variant.py
"""

from types import SimpleNamespace
from typing import TypedDict

from cendor.core import bus, instrument, instrument_tool
from cendor.core.types import LLMCall
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.completion_usage import CompletionUsage


def _instrumented_completions():
    class Completions:
        def create(self, **kwargs):
            return ChatCompletion(
                id="chatcmpl-cendor",
                model="gpt-4o",
                object="chat.completion",
                created=0,
                choices=[
                    Choice(
                        index=0,
                        finish_reason="stop",
                        message=ChatCompletionMessage(
                            role="assistant", content="Looking up the order..."
                        ),
                    )
                ],
                usage=CompletionUsage(prompt_tokens=90, completion_tokens=12, total_tokens=102),
            )

    comp = Completions()
    instrument(SimpleNamespace(chat=SimpleNamespace(completions=comp)))
    comp.with_raw_response = SimpleNamespace(
        create=lambda **kw: SimpleNamespace(parse=lambda: comp.create(**kw), headers={})
    )
    return comp


llm = ChatOpenAI(model="gpt-4o", api_key="sk-offline", client=_instrumented_completions())


@instrument_tool("lookup_order")  # tool calls emit ToolCall on the same bus
def lookup_order(order_id: str) -> dict:
    return {"order_id": order_id, "status": "refunded"}


class State(TypedDict):
    question: str
    answer: str
    order: dict


def call_model(state: State) -> dict:
    return {"answer": llm.invoke(state["question"]).content}


def run_tool(state: State) -> dict:
    return {"order": lookup_order("8823")}


def main() -> None:
    graph = StateGraph(State)
    graph.add_node("agent", call_model)
    graph.add_node("tool", run_tool)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", "tool")
    graph.add_edge("tool", END)
    app = graph.compile()

    seen: list = []
    bus.subscribe(seen.append)
    app.invoke({"question": "Was order 8823 refunded?"})

    print("one bus stream, model + tool:")
    for e in seen:
        if isinstance(e, LLMCall):
            print(f"  LLMCall   {e.model}  ${e.cost.amount}")
        else:
            print(
                f"  ToolCall  {e.name}  args={e.arguments['kwargs'] or e.arguments['args']}"
                f"  -> {e.result}"
            )


if __name__ == "__main__":
    main()
