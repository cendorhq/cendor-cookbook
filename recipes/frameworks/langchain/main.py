"""langchain — cost control + audit without changing your LangChain code.

You wrap the OpenAI client with `instrument()` and hand it to `ChatOpenAI`. Your chain is
written the normal LangChain way; budgeting (`tokenguard`) and a tamper-evident trail
(`acttrace`) populate anyway, because every model call still flows through the wrapped client.

Note: langchain-openai reads responses through `client.chat.completions.with_raw_response`, so
this recipe routes that accessor back through the instrumented `.create` (the `_attach_cendor`
helper) — one small bridge, then LangChain is untouched.

Offline: fake OpenAI-shaped client. Run:
  uv run python recipes/frameworks/langchain/main.py
Record a real cassette: RECORD=1 OPENAI_API_KEY=sk-... uv run python .../main.py
"""

import os
from types import SimpleNamespace

from cendor.acttrace import AuditLog
from cendor.core import bus, instrument
from cendor.tokenguard import budget, report, reset, track
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.completion_usage import CompletionUsage

SIGNING_KEY = os.environ.get("CENDOR_DEMO_KEY", "demo-signing-key")


def _fake_completions():
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
                            role="assistant",
                            content="Refunds are processed within 5 business days.",
                        ),
                    )
                ],
                usage=CompletionUsage(prompt_tokens=180, completion_tokens=24, total_tokens=204),
            )

    return Completions()


def _attach_cendor(completions):
    """Wrap `.create` with instrument(), then bridge with_raw_response back to it."""
    instrument(SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    completions.with_raw_response = SimpleNamespace(
        create=lambda **kw: SimpleNamespace(parse=lambda: completions.create(**kw), headers={})
    )
    return completions


def main() -> None:
    reset()
    if os.environ.get("RECORD") == "1":
        from openai import OpenAI

        completions = _attach_cendor(OpenAI().chat.completions)
    else:
        completions = _attach_cendor(_fake_completions())

    # --- ordinary LangChain, unchanged ---
    llm = ChatOpenAI(model="gpt-4o", api_key="sk-offline", client=completions)
    chain = (
        ChatPromptTemplate.from_messages(
            [("system", "You are a terse support agent."), ("human", "{question}")]
        )
        | llm
    )
    # --- /ordinary LangChain ---

    seen: list = []
    bus.subscribe(seen.append)
    audit = AuditLog(system="langchain_support", risk_tier="limited", signing_key=SIGNING_KEY)
    with budget(usd=0.10) as b, track(feature="support_chain"):
        with audit.decision(input="How long do refunds take?", actor="agent") as dec:
            answer = chain.invoke({"question": "How long do refunds take?"})
            dec.record(model="gpt-4o", prompt_id="support@v1")
    audit.detach()

    print(f"LangChain answer : {answer.content!r}")
    print(
        f"tokenguard spend : ${report().total().amount} over {len(seen)} model call(s) "
        f"(budget ${b.spent.amount} of $0.10)"
    )
    print(f"acttrace entries : {len(audit.entries)} (chain wrote spend + audit, code unchanged)")

    # The claim this recipe makes is "the LangChain code is unchanged and cendor still sees the
    # call". These three lines are that claim, measured, so it cannot quietly stop being true.
    assert seen, "no LLMCall reached the bus - the LangChain call was not captured"
    assert report().total().amount > 0, "the captured call was not priced"
    assert len(audit.entries) >= 2, "the chain recorded no decision for the LangChain turn"


if __name__ == "__main__":
    main()
