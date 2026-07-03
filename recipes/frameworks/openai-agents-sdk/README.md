# openai-agents-sdk — budget + audit a loop the SDK fully owns

**The pain.** The OpenAI Agents SDK runs the turn loop for you — deciding, calling tools, calling
the model again. That's the point, but it means you never see the individual calls to put a
budget or an audit trail around them.

**What this shows.** The SDK still talks to an OpenAI client. `instrument()` that client and every
turn the SDK drives lands on the cendor bus: `tokenguard` prices each one under a pre-flight
budget, and `acttrace` chains them into a tamper-evident trail — without touching the Agent or
Runner code. `cendor` works **alongside** the Agents SDK; it is not an official integration.

## Run it

```bash
uv run --group frameworks-agents python recipes/frameworks/openai-agents-sdk/main.py
```

## Expected output

```text
SDK final answer : 'Order 8823 was refunded.'
SDK drove 2 turns (tool call -> final answer), all offline:
  turn 1  gpt-4o  $0.000245000
  turn 2  gpt-4o  $0.000245000
acttrace chain   : 2 llm_call entries, verify: True
```

The SDK drove a real tool-calling loop (offline, tracing disabled); tokenguard shows per-turn
spend and acttrace's chain holds every turn.

**Live cassette (RECORD ✓, ships unrecorded):** `RECORD=1 OPENAI_API_KEY=sk-... uv run --group
frameworks-agents python .../main.py`.

Libraries: `core`, `tokenguard`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
