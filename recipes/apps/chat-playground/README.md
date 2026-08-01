# Chat Playground — all seven libraries, on every turn

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/cendorhq/cendor-cookbook?quickstart=1)

**The pain:** the cost/context/governance/testing layer under an LLM app is invisible. You can't
*see* the budget projecting a call, the context being packed to fit, a gate refusing a prompt before
it leaves, the audit chain growing, or the compression saving tokens — so you don't trust that any
of it is really happening.

This is a chat app that makes that layer visible on **every turn**. Chat on the left; the machinery
on the right, in three tabs. Everything except the reply text is real Cendor — real token counting,
real budget math, a real deterministic gate, real offline secret/PII detection, and a real signed
hash chain.

## What each panel shows

### Tab 1 — Cost & context

| Panel | Library | What you watch happen |
|---|---|---|
| **💰 Budget** | `tokenguard` | An editable USD cap (default `$0.50` in demo, `$0.10` in live) and a spend bar that fills per turn. In `block` mode the ~$0.09/turn demo spend trips the pre-flight cap on the **6th** turn: `BudgetExceeded — blocked pre-flight, $0 spent` (the call never runs). Flip to `downgrade` and the near-cap turn reroutes to a cheaper model instead. |
| **🧾 Receipt** | `contextkit` | The per-turn assembly receipt (`block · action · tokens`) with the active sizing in its header. Chat history is packed through a real `Context` with a visible token budget — watch the history block keep recent turns and **peel its oldest** ones as the chat grows. |
| **🗜 Compression** | `squeeze` | Paste more than 1,500 characters and it's compressed *before* it's sent: `X → Y tokens (Z% smaller)`. The **Expand** button restores the original **byte-for-byte**. |

### Tab 2 — Governance (two libraries, two different jobs)

| Panel | Library | What you watch happen |
|---|---|---|
| **🛡 Gate** | `guardrails` | A **deterministic gate on the call itself**. Two rules are armed: a `keyword_deny` that **blocks** a prompt-injection attempt, and a `regex_rule` that **redacts** an internal customer reference (`CUST-######`). A block **raises `GuardrailTripped`** — the request never leaves the process, $0 spent — and the chat shows your policy's refusal rather than "the agent hit an error". Untick **Arm the deterministic gate** and the same prompt goes straight through: the negative control, on screen. |
| **🔗 Audit** | `acttrace` | An offline **detection engine** scans every prompt (~20 categories across secret · credential · financial · gov_id · pii · special_category) against a **Policy** preset — `default` · `gdpr` · `pci` · `strict` — and each hit resolves to **block · redact · flag**. `default` **redacts** an API key/email *before send*; switch to `strict`/`pci` and the same key is **blocked pre-flight** ($0 spent). Every action lands on the signed hash chain. **Export** an EU-AI-Act-tagged evidence pack (JSONL), **Verify** it (`True`), and run the **Tamper** demo — one flipped byte makes verify return `False` and names the failing sequence number. |

> **Why both?** `guardrails` **enforces** — it refuses, and the request never leaves. `acttrace`
> **records** — a tamper-evident account of what the policy saw and decided. A reader who has met
> only one of them usually assumes it does the other's job too, so the two panels sit side by side.
>
> The division of labour is visible in the rules themselves: acttrace's detection engine already
> knows the standard catalogue, and it runs **first** — measured, all four presets resolve a leaked
> `sk-…` key (three to `redact`, `strict` to `block`) before the gate is ever reached. So the gate's
> redact rule targets an **internal customer reference** instead, which is exactly the kind of thing
> only your organisation knows is sensitive and no general catalogue can contain.

### Tab 3 — Record & bus

| Panel | Library | What you watch happen |
|---|---|---|
| **⏺ Recorder** | `cassette` | **Record** the session, then **Replay** it offline — same replies, **0 calls, $0** (works even with the key removed). **Download** the session as a cassette JSON and **Upload** one back to replay it — the "send a bug repro as a cassette" story. Uploads are size-capped, version-checked, and never `eval`'d. |
| **📡 Bus feed** | `core` | One normalized event card per call: `provider · model · usage · Decimal cost · cost_estimated`. The `instrument()` seam, made visible. |

## Run it locally

```bash
uv sync --group apps
uv run --group apps python recipes/apps/chat-playground/app.py
```

Then open the printed URL (default <http://127.0.0.1:7860>). No key required.

## Run it in the cloud

Click the **Open in GitHub Codespaces** badge above. The devcontainer installs `uv`, runs
`uv sync --group apps --group dev`, and **auto-starts the playground on the forwarded port `7860`** —
a preview opens automatically once it's up (watch `/tmp/playground.log` for boot progress). No
terminal step is needed.

If you ever need to restart it (e.g. after editing the app):

```bash
uv run --group apps python recipes/apps/chat-playground/app.py
```

## How the code is laid out

`app.py` used to be a 1,379-line monolith, which meant the turn pipeline could only be exercised
through Gradio. It is now five modules and a thin entry point, so the interesting parts are
testable — and CI proves the split holds by importing the engine with **gradio made unimportable**:

| File | What is in it |
|---|---|
| `config.py` | every constant, with the reason it has that value; `sizing()` — the one place demo and live diverge |
| `session.py` | one chat session (audit chain, history, recorder, gate state) and the registry that holds it |
| `engine.py` | the turn pipeline: detect → compress → assemble → gate → budget → call → record |
| `panels.py` | the seven renderers. **Every number rendered comes from a live object** — a bus event, a `prices` cost, a `contextkit` report, `len(audit.entries)`. No literals, not even in the empty states |
| `ui.py` | the Gradio layout and the handlers |
| `app.py` | the entry point (`build_demo`), so the devcontainer command, the CI job and the commands above stay valid |

## Demo mode vs. live mode

**Demo mode is the default and needs no key.** It uses a fake provider-shaped client with canned,
deterministic replies priced as `gpt-4o`. The reply *text* is scripted; **everything else is real
Cendor** — the token counts, the budget projection, the context receipt, the compression, the
guardrail decisions, the offline secret/PII detection, the cassette, and the signed audit chain are
all genuine. The UI labels this honestly:
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

### ⚠️ Live mode is sized differently from demo mode, on purpose

Demo mode's knowledge base is deliberately huge (424 policies, a 40,000-token budget) because the
fake client is free and has no rate limit — that size is what makes the receipt truncate and the
`$0.50` cap trip on the 6th turn. Sending it to a **real** provider is a different story, and both
halves were measured on 2026-07-31:

* **OpenAI 429'd on turn one.** A 40k budget packs ~38.7k input tokens into every request, and the
  default paid tier allows **30,000 tokens per minute** —
  `429 Request too large for gpt-4o … Limit 30000, Requested 50818`.
* **Anthropic did not 429 — it charged.** One "hi" billed **43,313 input tokens ⇒ $0.13**, which
  blows the app's own `$0.50` cap in four turns.

So live mode keeps the same *shape* at about a seventh of the size, and the mode switch retargets
the cap for you:

| | Demo | Live |
|---|---|---|
| context budget | `CONTEXT_BUDGET` 40,000 | `LIVE_CONTEXT_BUDGET` 6,000 |
| knowledge base | `KB_UNITS` 424 (~38.6k tokens) | `LIVE_KB_UNITS` 48 (~4.4k tokens) |
| input per turn | ~38,656 tokens | ~4,440 tokens |
| default cap | `$0.50` | `$0.10` |
| cost per turn | $0 (no network) | see below |

**Re-measured 2026-08-01** against the rebuilt engine, at `engine.run_turn()` — the entry point the
UI itself uses:

| Provider | Model | Usage | Cost / turn | Cap trips |
|---|---|---|---|---|
| OpenAI | `gpt-4o` | 4,440 in / 56 out | **$0.011660** | ~turn 8 |
| Anthropic | `claude-sonnet-4-6` | 4,970 in / 158 out | **$0.017280** | ~turn 5 |

No 429 on either. A live turn refused by the guardrail costs **$0.000000** and reaches the provider
**0 times** — also measured, on both providers.

Every number the panel sections above quote — `$0.09/turn`, the 6th-turn block, `truncated 378 → 291`
— refers to **demo** mode, and demo mode is untouched. If your account's per-minute allowance is
lower still, drop `LIVE_CONTEXT_BUDGET` and `LIVE_KB_UNITS`; a rate-limited turn says so in the chat
(and chains a `policy_flag`) instead of vanishing into a terminal traceback.

## Offline guarantee

Demo mode makes **no network call** — the fake client has no socket, the acttrace detection engine
(`scan`/`redact`) and the guardrails gate both run entirely offline, and the provider SDKs are
imported lazily only on the live path. The offline test suite asserts it, including on the gate's
block path:

```bash
uv run --group apps pytest recipes/apps/chat-playground/test_app.py
```

> `acttrace` produces **evidence to support** compliance — not a guarantee, and not legal advice.

Libraries: `core`, `tokenguard`, `contextkit`, `squeeze`, `guardrails`, `cassette`, `acttrace` (all seven) · Offline ✓ · [← all recipes](../../../README.md)
