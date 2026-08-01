"""Scripted Playground smoke — start the agent, drive it the way the Playground does, assert a
governed reply came back. No key, no tenant, no clicking.

    uv run --group agents-m365 python recipes/agents/m365-custom-engine-py/smoke.py

Why this exists: "does it run in the M365 Agents Playground?" was, until 2026-08-01, a question
only a human with a browser could answer, so a broken run instruction sat in the README unnoticed.
This script answers the same question in CI. It sends the two Activities the Playground itself
sends — a `conversationUpdate` handshake, then a `message` — to the agent's **real** aiohttp
endpoint behind the **real** JWT middleware, and reads the reply off a local channel stub standing
in for the Playground's `/_connector`.

⚠️ **What it cannot prove:** that the Playground's *own* UI renders the reply. That needs the real
Playground binary and a browser, and it was verified by hand on 2026-08-01 against
`@microsoft/m365agentsplayground` **0.2.28** — both twins answered
`Your refund is on its way.` over the Playground's WebSocket relay. The README's manual runbook is
that walkthrough; this file is the part a machine can re-check every push.

⚠️ **Also measured, and worth knowing before you go looking:** the Playground **projects
`channelData` away** in its UI relay. The Cendor envelope (`trace_id`, `cost_usd`, usage, session
spend, decisions) is on the wire to the connector — this script asserts it there — but you will not
see it in the Playground's chat pane. Assert it in a test, do not hunt for it in the UI.
"""

from __future__ import annotations

import asyncio
import socket
import sys
import tempfile
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent as agent_mod  # noqa: E402
from channel_stub import ChannelStub, make_activity, post_turn  # noqa: E402

CONVERSATION = "playground-smoke"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def handshake(service_url: str) -> dict:
    """The `conversationUpdate` the Playground sends before your first message.

    The agent registers no handler for it, so the SDK logs `No route found for activity type:
    conversationUpdate` and accepts it anyway — which is correct, and is exactly what a reader who
    tails the log will see first. It is not an error.
    """
    return {
        "type": "conversationUpdate",
        "id": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "serviceUrl": service_url,
        "channelId": "emulator",
        "from": {"id": "user-1", "name": "Cookbook User", "role": "user"},
        "conversation": {"id": CONVERSATION, "conversationType": "personal", "isGroup": False},
        "recipient": {"id": "m365-custom-engine", "name": "Governed agent", "role": "bot"},
        "membersAdded": [{"id": "user-1"}, {"id": "m365-custom-engine"}],
    }


async def run() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="cendor-m365-smoke-"))
    gov = agent_mod.GovernedAgent(audit_path=str(tmp / "chain.jsonl"))
    stub = ChannelStub(_free_port())
    port = _free_port()
    from aiohttp.web import AppRunner, TCPSite

    await stub.start()
    runner = AppRunner(agent_mod.build_web_app(gov))
    await runner.setup()
    await TCPSite(runner, "127.0.0.1", port).start()
    endpoint = f"http://127.0.0.1:{port}/api/messages"
    print(f"agent      : {endpoint}")
    print(f"channel    : {stub.service_url}  (stands in for the Playground's /_connector)")

    try:
        # 1 — the handshake. Accepted with no reply activity is the correct outcome.
        status = await post_turn(endpoint, handshake(stub.service_url))
        print(f"handshake  : conversationUpdate -> HTTP {status} (no route registered: correct)")
        # 202, not 200: `start_agent_process` ACCEPTS the Activity and processes it asynchronously,
        # which is the whole shape of the Bot Framework protocol — the reply comes back out-of-band
        # on the connector, not in this response body. Asserting 200 here is a real mistake and it
        # was made writing this file.
        assert status in (200, 202), f"the handshake was rejected with HTTP {status}"

        # 2 — a real message, exactly as the Playground relays one.
        act = make_activity(
            "I was double charged, can I get a refund?",
            conversation_id=CONVERSATION,
            service_url=stub.service_url,
        )
        status = await post_turn(endpoint, act)
        print(f"message    : message -> HTTP {status} (accepted; the reply arrives on the channel)")
        assert status in (200, 202), f"the message Activity was rejected with HTTP {status}"

        msgs = await stub.wait_for(CONVERSATION, count=1, timeout=30)
        assert msgs, "the agent never replied — nothing reached the channel"
        reply = msgs[-1]
        text = (reply.get("text") or "").strip()
        print(f"reply      : {text[:90]!r}")
        assert text, "the agent replied with an empty message"

        env = ((reply.get("channelData") or {}).get("cendor")) or {}
        print(f"envelope   : {sorted(env)}")
        # The governance envelope the handler attaches. Present on the WIRE; the Playground UI
        # projects channelData away, which is why this is asserted here and not looked for there.
        for field in ("trace_id", "cost_usd", "input_tokens", "output_tokens", "governance"):
            assert field in env, f"channelData.cendor is missing {field!r}: {env}"
        assert float(env["cost_usd"]) > 0, f"the turn was priced at {env['cost_usd']}"
        assert env["governance"] == "ok", f"governance said {env['governance']!r}"
        print(
            f"cost       : ${env['cost_usd']}  "
            f"{env['input_tokens']} in / {env['output_tokens']} out  model={env['model']}"
        )
        print(f"session    : ${env['session_spent_usd']} of ${env['session_cap_usd']}")
    finally:
        await runner.cleanup()
        await stub.stop()
        gov.close()

    print("\nPLAYGROUND SMOKE OK — the agent answers a Playground-shaped turn, governed.")
    return 0


def test_playground_smoke() -> None:
    """Same check, as a pytest so the `agents` CI job runs it on every push."""
    assert asyncio.run(run()) == 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
