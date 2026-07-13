<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/cendor-cookbook-banner-dark.png">
    <img alt="cendor-cookbook" src=".github/assets/cendor-cookbook-banner-light.png" width="820">
  </picture>
</p>

# Cendor Cookbook

[![CI](https://github.com/cendorhq/cendor-cookbook/actions/workflows/ci.yml/badge.svg)](https://github.com/cendorhq/cendor-cookbook/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/cendorhq/cendor-cookbook?quickstart=1)

Copy-paste recipes proving [**Cendor**](https://github.com/cendorhq/cendor-libs) — production plumbing
for LLM apps (cost, context, testing, governance) — works with the frameworks and providers you
already use. **Every recipe runs offline, with no API key.**

Most recipes install the shipped PyPI package (`cendor-libs>=1.0,<2.0`) and drive it against a fake
provider-shaped client, exactly the way Cendor's own test suite does — so there's nothing to sign
up for and nothing to spend. Two recipes are the TypeScript twins (`core-js`, `governed-agent-js`);
they install the published `@cendor/*` npm packages and run the same way with `node`.

**Running a recipe live?** Swap the fake client for a real one — or, in the SDK recipes, drop the
explicit `client` and set your provider's standard env var (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, …).
Where the key goes is documented once at
[Keys & providers](https://cendor.ai/docs/sdk/providers#api-keys--credentials).

## Start here: the Chat Playground

New to Cendor? The [**Chat Playground**](recipes/apps/chat-playground/) is a chat app that makes
the whole plumbing layer visible on every turn — budget blocking, context packing, compression,
record/replay, and a tamper-evident audit chain, all live in one UI. Open it in the cloud with one
click — in Codespaces it **auto-starts** on the forwarded port 7860 — or run it locally:

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/cendorhq/cendor-cookbook?quickstart=1)

```bash
uv sync --group apps
uv run --group apps python recipes/apps/chat-playground/app.py
```

## Quickstart

```bash
git clone https://github.com/cendorhq/cendor-cookbook
cd cendor-cookbook
uv sync

# the 5-minute win — a runaway loop, capped before it overspends:
uv run python recipes/quickstarts/tokenguard/main.py
```

Provider and quickstart recipes run on the base install. Framework recipes pull their SDK from a
per-category group, e.g.:

```bash
uv run --group frameworks-langchain python recipes/frameworks/langchain/main.py
uv run pytest recipes/testing recipes/governance          # the test-style recipes
```

## Recipes

| Recipe | Category | What it proves | Libraries | Offline |
|---|---|---|---|---|
| [**chat-playground**](recipes/apps/chat-playground/) | **app** | Every library live in one chat UI — the plumbing made visible per turn | `core` `tokenguard` `contextkit` `squeeze` `cassette` `acttrace` | ✓ |
| [tokenguard](recipes/quickstarts/tokenguard/) | quickstart | Block a runaway loop *before* it overspends (pre-flight cap) | `core` `tokenguard` | ✓ |
| [contextkit](recipes/quickstarts/contextkit/) | quickstart | Fit a prompt to budget with a kept/shrunk/dropped receipt | `core` `contextkit` | ✓ |
| [squeeze](recipes/quickstarts/squeeze/) | quickstart | Compress a huge blob to a token target, restore byte-for-byte | `core` `squeeze` | ✓ |
| [cassette](recipes/quickstarts/cassette/) | quickstart | Record an agent call once, replay it forever offline | `core` `cassette` | ✓ |
| [acttrace](recipes/quickstarts/acttrace/) | quickstart | Signed hash-chain; one edited byte breaks `verify` | `core` `acttrace` | ✓ |
| [guardrails](recipes/quickstarts/guardrails/) | quickstart | Block / redact a call before it's sent; every decision in the audit chain | `core` `guardrails` `acttrace` | ✓ |
| [core](recipes/quickstarts/core/) | quickstart | One `instrument()` wrap → every call on a normalized bus | `core` | ✓ |
| [core-js](recipes/quickstarts/core-js/) | quickstart · TS | The `core` quickstart in TypeScript — `@cendor/core` on npm, decimal-safe cost | `@cendor/core` | ✓ |
| [openai-chat](recipes/providers/openai-chat/) | provider · RECORD | Pre-flight budget + attribution on Chat Completions | `core` `tokenguard` | ✓ |
| [openai-responses](recipes/providers/openai-responses/) | provider · RECORD | Capture reasoning + cached tokens on the Responses API | `core` `tokenguard` | ✓ |
| [anthropic](recipes/providers/anthropic/) | provider · RECORD | Price prompt-cache reads/writes correctly, audited | `core` `tokenguard` `acttrace` | ✓ |
| [ollama-local](recipes/providers/ollama-local/) | provider · Local | Budgeted, recorded, audited turn on a $0 local model | `core` `tokenguard` `cassette` `acttrace` | ✓ |
| [langchain](recipes/frameworks/langchain/) | framework · RECORD | Cost + audit without changing LangChain code (+LangGraph) | `core` `tokenguard` `acttrace` | ✓ |
| [openai-agents-sdk](recipes/frameworks/openai-agents-sdk/) | framework · RECORD | Budget + audit a loop the Agents SDK fully owns | `core` `tokenguard` `acttrace` | ✓ |
| [llamaindex](recipes/frameworks/llamaindex/) | framework | Pack RAG retrieval to a token budget, reversibly | `core` `contextkit` `squeeze` | ✓ |
| [azure-foundry-otel](recipes/frameworks/azure-foundry-otel/) | framework | Budget + audit calls your process never made (OTel spans) | `core` `tokenguard` `acttrace` | ✓ |
| [pytest-cassette](recipes/testing/pytest-cassette/) | testing | An offline agent test suite that runs on a plane | `core` `cassette` | ✓ |
| [eu-ai-act-evidence](recipes/governance/eu-ai-act-evidence/) | governance | A tamper-evident evidence pack for a high-risk decision | `core` `acttrace` | ✓ |
| [pii-guardrail](recipes/governance/pii-guardrail/) | governance | PII/secrets as a guardrail (`rules.custom` + acttrace) — redacted before send, in the audit chain | `core` `guardrails` `acttrace` | ✓ |
| [llm-judge-guardrail](recipes/governance/llm-judge-guardrail/) | governance | A model-judge input screen whose own spend is budgeted + audited; cassette-replayed offline | `core` `guardrails` `tokenguard` `cassette` | ✓ |
| [guardrails-policy](recipes/governance/guardrails-policy/) | governance | Config-as-data: `load_policy` from a versioned file; `policy_hash`/`version` on every decision proves which policy was active | `core` `guardrails` `acttrace` | ✓ |
| [guardrails-redteam](recipes/governance/guardrails-redteam/) | governance | Measure a guardrail's trip rate + false positives against a labeled corpus (`run_redteam`) — a number, not a claim | `guardrails` | ✓ |
| [spotlight-untrusted-docs](recipes/governance/spotlight-untrusted-docs/) | governance | `rules.spotlight` wraps a retrieved doc in a trust-lowering delimiter (a `$0` mitigation vs indirect injection); composes with a denylist | `core` `guardrails` | ✓ |
| [task-adherence](recipes/governance/task-adherence/) | governance | A BYO-judge `tool_call` alignment check (is the proposed call on-task?) whose own spend is budgeted + audited; cassette-replayed offline | `core` `guardrails` `tokenguard` `cassette` | ✓ |
| [intent-gate](recipes/governance/intent-gate/) | governance | `rules.intent` — a pre-LLM intent gate (off-topic `allow` / deny) before you spend a token; offline keyword classifier, no model | `core` `guardrails` | ✓ |
| [custom-category](recipes/governance/custom-category/) | governance | `rules.custom_category` catches a paraphrase a keyword denylist misses (semantic by-example); composes with `keyword_deny` | `core` `guardrails` | ✓ |
| [governed-agent](recipes/sdk/governed-agent/) | **sdk** | A governed agent in ~10 lines — budget + audit + a real tool loop | `cendor-sdk` | ✓ |
| [governed-agent-js](recipes/sdk/governed-agent-js/) | **sdk** · TS | The governed-agent recipe in TypeScript — `@cendor/sdk` on npm | `@cendor/sdk` | ✓ |
| [openai-agents-guardrail](recipes/bridges/openai-agents-guardrail/) | bridges | A cendor Guardrail as an OpenAI Agents SDK `@input_guardrail` | `guardrails` + `openai-agents` | ✓ |
| [claude-agent-pretooluse](recipes/bridges/claude-agent-pretooluse/) | bridges | A cendor Guardrail as a Claude Agent SDK `PreToolUse` hook (deny a tool call) | `guardrails` + `claude-agent-sdk` | ✓ |
| [mcp-tool-gating](recipes/bridges/mcp-tool-gating/) | bridges | Gate a `FastMCP` server's tools with a cendor Guardrail at the tool boundary | `guardrails` + `mcp` | ✓ |
| [langchain-middleware](recipes/bridges/langchain-middleware/) | bridges | A cendor Guardrail as a LangChain `before_model` agent middleware | `guardrails` + `langchain` | ✓ |

**RECORD** recipes ship green offline against a fake client and carry a `RECORD=1` path a
maintainer runs once with a real key to capture a replayable cassette (secrets redacted on write).
**Local** = also runs against a live local Ollama daemon with a one-line swap.

## Run any recipe

Most recipes are a folder with a `main.py` you can run directly; the two TypeScript twins
(`core-js`, `governed-agent-js`) are a folder with an `index.mjs` run with `node`. Quickstart,
provider, SDK, and governance recipes run on the base install; framework recipes each need their
own dependency group so a breaking release in one can't turn the others red:

| Category | Command |
|---|---|
| quickstart / provider | `uv run python recipes/<category>/<name>/main.py` |
| quickstart · TypeScript | `cd recipes/quickstarts/core-js && npm install && node index.mjs` |
| **sdk** | `uv run python recipes/sdk/<name>/main.py` |
| **sdk** · TypeScript | `cd recipes/sdk/governed-agent-js && npm install && node index.mjs` |
| governance | `uv run python recipes/governance/<name>/main.py` |
| testing | `uv run pytest recipes/testing` |
| frameworks · langchain | `uv run --group frameworks-langchain python recipes/frameworks/langchain/main.py` |
| frameworks · openai-agents-sdk | `uv run --group frameworks-agents python recipes/frameworks/openai-agents-sdk/main.py` |
| frameworks · llamaindex | `uv run --group frameworks-llamaindex python recipes/frameworks/llamaindex/main.py` |
| frameworks · azure-foundry-otel | `uv run --group frameworks-otel python recipes/frameworks/azure-foundry-otel/main.py` |
| apps · chat-playground | `uv run --group apps python recipes/apps/chat-playground/app.py` |

Any recipe that ships a test file is also runnable via `uv run pytest recipes/<category>/<name>`.

## How offline works

`instrument()` identifies an LLM client by its **shape**, not by network access — so a plain
`types.SimpleNamespace` with the same `chat.completions.create` / `responses.create` /
`messages.create` / `chat(...)` surface is all it needs. The fake returns a canned `usage`, and
Cendor normalizes and prices it from a bundled offline snapshot exactly as it would a real call.
No key, no network, forever. Costs shown come from `prices.estimate` on the stated token counts —
no invented numbers.

## Contributing

New recipes are welcome — the one hard rule is **it runs green offline, with no key**. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the recipe template and the offline bar.

## Links

- **Library:** [github.com/cendorhq/cendor-libs](https://github.com/cendorhq/cendor-libs)
- **Site:** [cendor.ai](https://cendor.ai) · [cendor.ai/cookbook](https://cendor.ai/cookbook)
- **Docs:** [cendor.ai/docs](https://cendor.ai/docs)
- **MCP server:** [cendor.ai/mcp](https://cendor.ai/mcp) — an agent-mode assistant can list these recipe
  categories with the `list_recipes` tool (remote `mcp.cendor.ai` or local `npx @cendor/mcp` / `uvx cendor-mcp`).
- **For AI assistants:** [cendor.ai/docs/for-ai-assistants](https://cendor.ai/docs/for-ai-assistants) — the
  call-shape trap sheet + paste-in rules files for wiring Cendor into your coding assistant.

## License & disclaimer

Apache-2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Copyright © 2026 Raghav Mishra (PowerAI Labs).

> Provided **"AS IS", without warranties of any kind**; the authors carry no liability for use —
> see Apache-2.0 §7–§8. In particular, `acttrace` produces **evidence to support** compliance —
> not a guarantee, and not legal advice.
