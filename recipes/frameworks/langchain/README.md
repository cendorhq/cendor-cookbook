# langchain — cost control + audit, without changing your LangChain code

**The pain.** You've built on LangChain and want a spend cap and an audit trail. You do **not**
want to rewrite your chains around a new abstraction to get them.

**What this shows.** You wrap the OpenAI client with `instrument()` and hand it to `ChatOpenAI`.
The chain is ordinary LangChain; `tokenguard` prices the call under a budget and `acttrace`
records it — because every model call still flows through the wrapped client. `cendor` works
**alongside** LangChain; it is not an official LangChain integration.

> Note: langchain-openai reads responses via `client.chat.completions.with_raw_response`, which
> `instrument()` doesn't wrap directly, so the recipe bridges that accessor back to the
> instrumented `.create` (the `_attach_cendor` helper). One small bridge, then LangChain is
> untouched.

Also included: [`langgraph_variant.py`](langgraph_variant.py) — a 2-node LangGraph agent whose
tool (wrapped with `instrument_tool()`) joins the **same** bus stream as the model call.

## Run it

```bash
uv run --group frameworks-langchain python recipes/frameworks/langchain/main.py
uv run --group frameworks-langchain python recipes/frameworks/langchain/langgraph_variant.py
```

## Expected output

```text
LangChain answer : 'Refunds are processed within 5 business days.'
tokenguard spend : $0.000690000 over 1 model call(s) (budget $0.000690000 of $0.10)
acttrace entries : 5 (chain wrote spend + audit, code unchanged)
```

LangGraph variant — model and tool calls on one stream:

```text
one bus stream, model + tool:
  LLMCall   gpt-4o  $0.000345000
  ToolCall  lookup_order  args=['8823']  -> {'order_id': '8823', 'status': 'refunded'}
```

**Live swap (`RECORD=1`) — a live run, *not* a recording.** `RECORD=1 OPENAI_API_KEY=sk-... uv run
--group frameworks-langchain python .../main.py` swaps the fake completions object for a real
`OpenAI().chat.completions` and runs the chain against the live API. Unlike the `providers/*` RECORD
paths, **this recipe imports no cassette and writes no fixture** — verified by running it live
(2026-07-30): the spend and the audit entries are real, and no `fixtures/` directory appears. The env
var name is kept for consistency with the other live switches.

Libraries: `core`, `tokenguard`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
