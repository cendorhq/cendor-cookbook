"""Bridge: gate an MCP server's tools with a cendor Guardrail.

An MCP server exposes tools to any client. Wrap a tool with a cendor guardrail at the `tool_call`
stage and a dangerous argument is refused *before* the tool body runs — the same gate `cendor-sdk`
puts on its own tool loop, now protecting a tool you expose over MCP.

Offline: we register the tool on a `FastMCP` server (the wiring) and call the gated function
directly — no transport, no client, no network. Needs the `frameworks-mcp` group:
  uv sync --group frameworks-mcp
Run:  uv run python recipes/bridges/mcp-tool-gating/main.py
"""

import functools

from cendor.guardrails import GuardrailTripped, apply, rules
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo")


def gated(guardrails, *, stage="tool_call"):
    """Decorator: run `guardrails` over the tool's arguments before the body. A cendor `block`
    returns an MCP tool result the model can see (`[blocked …]`) instead of executing — mirroring
    how `cendor-sdk` handles a tool-stage block."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(**kwargs) -> str:
            try:
                apply(guardrails, stage, str(kwargs))  # raises GuardrailTripped on a block
            except GuardrailTripped as e:
                return f"[blocked by guardrail] {e}"
            return fn(**kwargs)

        return wrapper

    return deco


@mcp.tool()
@gated([rules.keyword_deny(["rm -rf", "mkfs"], action="block", stage="tool_call")])
def run_shell(command: str) -> str:
    """Run a shell command (guarded)."""
    return f"ran: {command}"


def main() -> None:
    for command in ["ls -la", "rm -rf /"]:
        result = run_shell(command=command)
        print(f"{command!r:14} -> {result}")


if __name__ == "__main__":
    main()
