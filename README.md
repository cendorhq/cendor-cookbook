# Cendor Cookbook

[![CI](https://github.com/cendorhq/cendor-cookbook/actions/workflows/ci.yml/badge.svg)](https://github.com/cendorhq/cendor-cookbook/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Copy-paste recipes proving [**Cendor**](https://github.com/cendorhq/Cendor) — production plumbing
for LLM apps (cost, context, testing, governance) — works with the frameworks and providers you
already use. **Every recipe runs offline, with no API key.**

Each recipe installs the shipped PyPI package (`cendor>=1.0,<2.0`) and drives it against a fake
provider-shaped client, exactly the way Cendor's own test suite does — so there's nothing to sign
up for and nothing to spend.

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
| [tokenguard](recipes/quickstarts/tokenguard/) | quickstart | Block a runaway loop *before* it overspends (pre-flight cap) | `core` `tokenguard` | ✓ |
| [contextkit](recipes/quickstarts/contextkit/) | quickstart | Fit a prompt to budget with a kept/shrunk/dropped receipt | `core` `contextkit` | ✓ |
| [squeeze](recipes/quickstarts/squeeze/) | quickstart | Compress a huge blob to a token target, restore byte-for-byte | `core` `squeeze` | ✓ |
| [cassette](recipes/quickstarts/cassette/) | quickstart | Record an agent call once, replay it forever offline | `core` `cassette` | ✓ |
| [acttrace](recipes/quickstarts/acttrace/) | quickstart | Signed hash-chain; one edited byte breaks `verify` | `core` `acttrace` | ✓ |
| [core](recipes/quickstarts/core/) | quickstart | One `instrument()` wrap → every call on a normalized bus | `core` | ✓ |
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

**RECORD** recipes ship green offline against a fake client and carry a `RECORD=1` path a
maintainer runs once with a real key to capture a replayable cassette (secrets redacted on write).
**Local** = also runs against a live local Ollama daemon with a one-line swap.

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

- **Library:** [github.com/cendorhq/Cendor](https://github.com/cendorhq/Cendor)
- **Site:** [cendor.ai](https://cendor.ai) · [cendor.ai/cookbook](https://cendor.ai/cookbook)
- **Docs:** [docs.cendor.ai](https://docs.cendor.ai)

## License & disclaimer

Apache-2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Copyright © 2026 Raghav Mishra.

> Provided **"AS IS", without warranties of any kind**; the authors carry no liability for use —
> see Apache-2.0 §7–§8. In particular, `acttrace` produces **evidence to support** compliance —
> not a guarantee, and not legal advice.
