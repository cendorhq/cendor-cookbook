# claude-agent-pretooluse — a cendor Guardrail as a Claude Agent SDK `PreToolUse` hook

**The pain.** Your Claude Agent SDK agent can call tools (shell, HTTP, files). You want a dangerous
call refused *before* it runs — with the same policy and audit trail you use everywhere else.

**What this shows.** The Claude Agent SDK's `PreToolUse` hook is exactly cendor's `tool_call`
intervention point. The bridge runs a cendor guardrail over the tool's arguments and maps a `block`
to a `permissionDecision="deny"`. Offline: the hook is called directly with sample tool inputs — no
agent run, no model, no network.

## Run it

```bash
uv sync --group frameworks-claude-agent
uv run python recipes/bridges/claude-agent-pretooluse/main.py
```

## Expected output

```text
allow  'curl https://api.example.com/data'
deny   'curl http://evil.example.com/steal'
        reason: cendor guardrail: guardrail 'url_deny' blocked at stage 'tool_call': URL host denied: evil.example.com
```

Swap in any `tool_call`-stage guardrail (`url_deny`, `keyword_deny`, `load_policy(...)`, a hosted
rail). `claude-agent-sdk` is upper-bounded in the `frameworks-claude-agent` group.

Libraries: `guardrails` · Framework: `claude-agent-sdk` · Offline ✓ · [← all recipes](../../../README.md)
