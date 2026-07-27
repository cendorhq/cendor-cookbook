/**
 * A local stand-in for the channel — the small Bot Connector REST subset an agent replies to.
 *
 * Not a cendor surface and deliberately dumb: it exists so this recipe can drive the agent's **real**
 * HTTP endpoint deterministically, in CI, with no tenant and no tunnel. In production Azure Bot
 * Service plays this part; the M365 Agents Playground plays it interactively
 * (`agentsplayground -e http://localhost:3979/api/messages -c emulator`).
 */
import express from 'express';
import net from 'node:net';
import { randomUUID } from 'node:crypto';

export async function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

export class ChannelStub {
  constructor(port) {
    this.port = port;
    this.replies = new Map();
    this.updates = new Map();
    this.server = null;
  }

  get serviceUrl() {
    return `http://127.0.0.1:${this.port}`;
  }

  async start() {
    const app = express();
    app.use(express.json({ limit: '5mb' }));
    const record = (bucket) => (req, res) => {
      const cid = req.params.cid;
      const list = bucket.get(cid) ?? [];
      list.push(req.body ?? {});
      bucket.set(cid, list);
      res.json({ id: `stub-${list.length}` });
    };
    app.post('/v3/conversations/:cid/activities', record(this.replies));
    app.post('/v3/conversations/:cid/activities/:aid', record(this.replies));
    app.put('/v3/conversations/:cid/activities/:aid', record(this.updates));
    app.use((_req, res) => res.json({}));

    await new Promise((resolve) => {
      this.server = app.listen(this.port, '127.0.0.1', () => resolve());
    });
    return this;
  }

  async stop() {
    if (!this.server) return;
    await new Promise((resolve) => this.server.close(() => resolve()));
    this.server = null;
  }

  messages(conversationId) {
    return (this.replies.get(conversationId) ?? []).filter((a) => a.type === 'message');
  }

  allFor(conversationId) {
    return [...(this.replies.get(conversationId) ?? []), ...(this.updates.get(conversationId) ?? [])];
  }

  /** Wait until `count` message replies have arrived; `quiet` waits for the flow to go silent. */
  async waitFor(conversationId, { count = 1, timeout = 30_000, quiet = 0 } = {}) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline && this.messages(conversationId).length < count) {
      await new Promise((r) => setTimeout(r, 25));
    }
    if (quiet) {
      let last = this.allFor(conversationId).length;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, quiet));
        const now = this.allFor(conversationId).length;
        if (now === last) break;
        last = now;
      }
    }
    return this.messages(conversationId);
  }
}

/**
 * A channel-shaped Activity, as the emulator channel sends one.
 *
 * `aadObjectId` is what a real tenant puts on `from` — deliberately absent here, and the handler never
 * tags it either (identity in exported telemetry is personal data; opt in on purpose).
 */
export function makeActivity(text, { conversationId, serviceUrl, channelId = 'emulator' }) {
  return {
    type: 'message',
    id: randomUUID(),
    timestamp: new Date(0).toISOString(),
    serviceUrl,
    channelId,
    from: { id: 'user-1', name: 'Cookbook User', role: 'user' },
    conversation: { id: conversationId, conversationType: 'personal', isGroup: false },
    recipient: { id: 'm365-custom-engine', name: 'Governed agent', role: 'bot' },
    textFormat: 'plain',
    locale: 'en-US',
    text,
  };
}

export async function postTurn(endpoint, activity) {
  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(activity),
  });
  await res.text();
  return res.status;
}
