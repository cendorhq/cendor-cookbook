"""A local stand-in for the channel — the small Bot Connector REST subset an agent replies to.

Not a cendor surface and deliberately dumb: it exists so this recipe can drive the agent's **real**
HTTP endpoint deterministically, in CI, with no tenant and no tunnel. In production Azure Bot
Service
plays this part; the M365 Agents Playground plays it interactively
(`agentsplayground -e http://localhost:3978/api/messages -c emulator`).

Routes (from the hosting SDK's own connector client):

    POST   /v3/conversations/{cid}/activities             send to conversation
    POST   /v3/conversations/{cid}/activities/{aid}        reply to activity
    PUT    /v3/conversations/{cid}/activities/{aid}        update activity (streaming uses this)
"""

from __future__ import annotations

import asyncio
import itertools
import time
import uuid
from typing import Any

import aiohttp
from aiohttp import web


class ChannelStub:
    def __init__(self, port: int) -> None:
        self.port = port
        self.replies: dict[str, list[dict[str, Any]]] = {}
        self.updates: dict[str, list[dict[str, Any]]] = {}
        self._ids = itertools.count(1)
        self._runner: web.AppRunner | None = None
        self._event = asyncio.Event()

    @property
    def service_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def start(self) -> ChannelStub:
        app = web.Application()
        app.router.add_post("/v3/conversations/{cid}/activities", self._on_send)
        app.router.add_post("/v3/conversations/{cid}/activities/{aid}", self._on_send)
        app.router.add_put("/v3/conversations/{cid}/activities/{aid}", self._on_update)
        app.router.add_route("*", "/{tail:.*}", self._on_other)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", self.port).start()
        return self

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _record(self, request: web.Request, bucket: dict) -> web.Response:
        cid = request.match_info["cid"]
        try:
            body = await request.json()
        except Exception:
            body = {"_raw": (await request.text())[:500]}
        bucket.setdefault(cid, []).append(body)
        self._event.set()
        return web.json_response({"id": f"stub-{next(self._ids)}"})

    async def _on_send(self, request: web.Request) -> web.Response:
        return await self._record(request, self.replies)

    async def _on_update(self, request: web.Request) -> web.Response:
        return await self._record(request, self.updates)

    async def _on_other(self, _request: web.Request) -> web.Response:
        return web.json_response({})

    # ------------------------------------------------------------------------------- assertions
    def messages(self, conversation_id: str) -> list[dict[str, Any]]:
        return [a for a in self.replies.get(conversation_id, []) if a.get("type") == "message"]

    def all_for(self, conversation_id: str) -> list[dict[str, Any]]:
        return list(self.replies.get(conversation_id, [])) + list(
            self.updates.get(conversation_id, [])
        )

    async def wait_for(
        self, conversation_id: str, *, count: int = 1, timeout: float = 30.0, quiet: float = 0.0
    ) -> list[dict[str, Any]]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(self.messages(conversation_id)) < count:
            self._event.clear()
            try:
                await asyncio.wait_for(
                    self._event.wait(), timeout=max(0.05, deadline - time.monotonic())
                )
            except TimeoutError:
                break
        if quiet:  # streamed turns: wait for the reply flow to go silent, not for the first arrival
            last = len(self.all_for(conversation_id))
            while time.monotonic() < deadline:
                await asyncio.sleep(quiet)
                now = len(self.all_for(conversation_id))
                if now == last:
                    break
                last = now
        return self.messages(conversation_id)


def make_activity(
    text: str, *, conversation_id: str, service_url: str, channel_id: str = "emulator"
) -> dict:
    """A channel-shaped Activity, as the emulator channel sends one.

    `aadObjectId` is what a real tenant puts on `from` — it is deliberately absent here, and the
    handler never tags it either (identity in exported telemetry is personal data; opt in first).
    """
    return {
        "type": "message",
        "id": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "serviceUrl": service_url,
        "channelId": channel_id,
        "from": {"id": "user-1", "name": "Cookbook User", "role": "user"},
        "conversation": {"id": conversation_id, "conversationType": "personal", "isGroup": False},
        "recipient": {"id": "m365-custom-engine", "name": "Governed agent", "role": "bot"},
        "textFormat": "plain",
        "locale": "en-US",
        "text": text,
    }


async def post_turn(endpoint: str, activity: dict, *, timeout: float = 30.0) -> int:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            endpoint, json=activity, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            await resp.read()
            return resp.status
