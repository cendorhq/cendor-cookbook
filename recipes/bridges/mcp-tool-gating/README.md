# mcp-tool-gating — gate an MCP server's tools with a cendor Guardrail

**The pain.** You expose tools over MCP to any client. A malicious or careless argument (`rm -rf /`,
a URL to a bad host) should be refused at the tool boundary — with evidence.

**What this shows.** A small `@gated(...)` decorator wraps a `FastMCP` tool so a cendor guardrail runs
over its arguments at the `tool_call` stage *before* the body executes. A `block` returns a
`[blocked …]` result the caller sees instead of running the tool — mirroring how `cendor-sdk` handles
a tool-stage block. Offline: the gated tool is called directly — no transport, no client, no network.

## Run it

```bash
uv sync --group frameworks-mcp
uv run python recipes/bridges/mcp-tool-gating/main.py
```

## Expected output

```text
'ls -la'       -> ran: ls -la
'rm -rf /'     -> [blocked by guardrail] guardrail 'keyword_deny' blocked at stage 'tool_call': denied keyword: 'rm -rf'
```

The decorator is framework-thin; swap in any `tool_call`-stage guardrail. `mcp` is upper-bounded in
the `frameworks-mcp` group.

Libraries: `guardrails` · Framework: `mcp` · Offline ✓ · [← all recipes](../../../README.md)
