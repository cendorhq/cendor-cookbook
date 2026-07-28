# Chat Playground — see the plumbing

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/cendorhq/cendor-cookbook?quickstart=1)

**The pain:** the cost/context/testing/governance layer under an LLM app is invisible. You can't
*see* the budget projecting a call, the context being packed to fit, the audit chain growing, or
the compression saving tokens — so you don't trust that any of it is really happening.

This is a chat app that makes that layer visible on **every turn**. Chat on the left; a live
"plumbing panel" on the right where each Cendor library shows its work. Everything except the
reply text is real Cendor — real token counting, real budget math, real offline secret/PII
detection, and a real signed hash chain.

## What each panel shows

| Panel | Library | What you watch happen |
|---|---|---|
| **💰 Budget** | `tokenguard` | An editable USD cap (default `$0.50`) and a spend bar that fills per turn. In `block` mode the ~$0.09/turn demo spend trips the pre-flight cap on the **6th** turn: `BudgetExceeded — blocked pre-flight, $0 spent` (the call never runs). Flip to `downgrade` and the near-cap turn reroutes to a cheaper model instead. |
| **🧾 Receipt** | `contextkit` | The per-turn assembly receipt (`block · action · tokens`). Chat history is packed through a real `Context` with a visible token budget — watch the history block keep recent turns and **peel its oldest** ones as the chat grows. |
| **🗜 Compression** | `squeeze` | Paste more than 1,500 characters and it's compressed *before* it's sent: `X → Y tokens (Z% smaller)`. The **Expand** button restores the original **byte-for-byte**. |
| **⏺ Recorder** | `cassette` | **Record** the session, then **Replay** it offline — same replies, **0 calls, $0** (works even with the key removed). **Download** the session as a cassette JSON and **Upload** one back to replay it — the "send a bug repro as a cassette" story. Uploads are size-capped, version-checked, and never `eval`'d. |
| **🔗 Audit** | `acttrace` | An offline **detection engine** scans every prompt (~20 categories across secret · credential · financial · gov_id · pii · special_category) against a **Policy** preset — `default` · `gdpr` · `pci` · `strict` — and each hit resolves to **block · redact · flag**. `default` **redacts** an API key/email *before send* (the model never sees it); switch to `strict`/`pci` and the same key is **blocked pre-flight** ($0 spent). Every action lands on the signed hash chain. **Export** an EU-AI-Act-tagged evidence pack (JSONL), **Verify** it (`True`), and run the **Tamper** demo — one flipped byte makes verify return `False` and names the failing sequence number. |
| **📡 Bus feed** | `core` | One normalized event card per call: `provider · model · usage · Decimal cost · cost_estimated`. The `instrument()` seam, made visible. |

## Run it locally

```bash
uv sync --group apps
uv run --group apps python recipes/apps/chat-playground/app.py
```

Then open the printed URL (default <http://127.0.0.1:7860>). No key required.

## Run it in the cloud

Click the **Open in GitHub Codespaces** badge above. The devcontainer installs `uv`, runs
`uv sync --group apps`, and **auto-starts the playground on the forwarded port `7860`** — a preview
opens automatically once it's up (watch `/tmp/playground.log` for boot progress). No terminal step
is needed.

If you ever need to restart it (e.g. after editing the app):

```bash
uv run --group apps python recipes/apps/chat-playground/app.py
```

## Demo mode vs. live mode

**Demo mode is the default and needs no key.** It uses a fake provider-shaped client with canned,
deterministic replies priced as `gpt-4o`. The reply *text* is scripted; **everything else is real
Cendor** — the token counts, the budget projection, the context receipt, the compression, the
offline secret/PII detection, the cassette, and the signed audit chain are all genuine. The UI
labels this honestly:
*"demo model — connect a key for a live one."*

**Live mode** adds a provider picker (OpenAI / Anthropic) and a password box. The key is read from
the box or from the environment and is used only to call the provider directly:

| Provider | Env var | Model |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `gpt-4o` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |

The key **stays in process memory** — it is never written to disk, never logged, and gone when
you stop the app. (An optional `CENDOR_DEMO_KEY` signs the audit chain; it defaults to a demo
value so the app is green out of the box.)

## Offline guarantee

Demo mode makes **no network call** — the fake client has no socket, the acttrace detection engine
(`scan`/`redact`) runs entirely offline, and the provider SDKs are imported lazily only on the live
path. The offline test suite asserts it:

```bash
uv run --group apps pytest recipes/apps/chat-playground/test_app.py
```

> `acttrace` produces **evidence to support** compliance — not a guarantee, and not legal advice.

Libraries: `core`, `tokenguard`, `contextkit`, `squeeze`, `cassette`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
