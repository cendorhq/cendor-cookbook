<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/cendor-cookbook-banner-dark.png">
    <img alt="cendor-cookbook" src=".github/assets/cendor-cookbook-banner-light.png" width="820">
  </picture>
</p>

<!-- The header block is centred as one unit, to line up with the banner above. That means HTML, not
     markdown: GitHub does not process markdown inside an HTML block, so `**bold**` and `[a](b)` would
     render literally inside a <p align="center">. Verified against the GitHub markdown API.
     The three badges were also one-per-source-line here, which is a second reason they stacked. -->

<h1 align="center">Cendor Cookbook</h1>

<p align="center">
  <a href="https://github.com/cendorhq/cendor-cookbook/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/cendorhq/cendor-cookbook/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <a href="https://codespaces.new/cendorhq/cendor-cookbook?quickstart=1"><img alt="Open in GitHub Codespaces" src="https://github.com/codespaces/badge.svg"></a>
</p>

Copy-paste recipes proving [**Cendor**](https://github.com/cendorhq/cendor-libs) — production plumbing
for LLM apps (cost, context, testing, governance) — works with the frameworks and providers you
already use. **Every recipe runs offline, with no API key.**

Every recipe installs the shipped PyPI package (`cendor-libs>=1.0,<2.0`) and drives it against a fake
provider-shaped client, exactly the way Cendor's own test suite does — so there's nothing to sign
up for and nothing to spend.

> **This is the Python cookbook.** The TypeScript recipes live in
> [**cendorhq/cendor-cookbook-js**](https://github.com/cendorhq/cendor-cookbook-js) — twins, not
> forks: a recipe folder name means the same thing in both trees. They are separate repos so each
> has one unambiguous toolchain; a single repo carrying a root `pyproject.toml` *and* scattered
> `package.json` files gives a devcontainer nothing definite to provision.
>
> **Since 2026-08-01 the two trees are at parity: 52 of the 53 recipes here have a TypeScript twin.**
> The exception is [`apps/chat-playground`](recipes/apps/chat-playground/), which is a **Gradio** app
> — Gradio is Python-only, so a TypeScript port would be a *different application* wearing a twin's
> folder name. Four folder names differ deliberately: `quickstarts/core`, `sdk/governed-agent` and
> `agents/m365-custom-engine-py` carry a `-js` suffix on the other side for historical reasons, and
> `testing/pytest-cassette` is `testing/vitest-cassette` there because `pytest` is a Python toolchain
> name and the twin genuinely is a different test runner.

**Running a recipe live?** Swap the fake client for a real one — or, in the SDK recipes, drop the
explicit `client` and set your provider's standard env var (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, …).
Where the key goes is documented once at
[Keys & providers](https://cendor.ai/docs/sdk/providers#api-keys--credentials).

## Start here: the Chat Playground

New to Cendor? The [**Chat Playground**](recipes/apps/chat-playground/) is a chat app that makes
the whole plumbing layer visible on every turn — budget blocking, context packing, compression, a
deterministic gate that refuses a prompt before it leaves, record/replay, and a tamper-evident audit
chain. **All seven libraries, live in one UI.** Open it in the cloud with one click — in Codespaces
it **auto-starts** on the forwarded port 7860 — or run it locally:

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
uv run --group agents-m365 python recipes/agents/m365-custom-engine-py/main.py
uv run pytest recipes/testing recipes/governance          # the test-style recipes
```

## Recipes

| Recipe | Category | What it proves | Libraries | Offline |
|---|---|---|---|---|
| [**chat-playground**](recipes/apps/chat-playground/) | **app** | All **seven** libraries live in one chat UI — the plumbing made visible per turn | `core` `tokenguard` `contextkit` `squeeze` `guardrails` `cassette` `acttrace` | ✓ |
| [**m365-custom-engine-py**](recipes/agents/m365-custom-engine-py/) | **agent** | Govern a Microsoft 365 Agents SDK **custom engine agent**: session cap in `TurnState`, gates on the Activity, evidence per turn, and the whole agent replayed offline for `$0` CI | `core` `tokenguard` `guardrails` `contextkit` `squeeze` `cassette` `acttrace` | ✓ |
| [tokenguard](recipes/quickstarts/tokenguard/) | quickstart | Block a runaway loop *before* it overspends (pre-flight cap) | `core` `tokenguard` | ✓ |
| [contextkit](recipes/quickstarts/contextkit/) | quickstart | Fit a prompt to budget with a kept/shrunk/dropped receipt | `core` `contextkit` | ✓ |
| [squeeze](recipes/quickstarts/squeeze/) | quickstart | Compress a huge blob to a token target, restore byte-for-byte | `core` `squeeze` | ✓ |
| [cassette](recipes/quickstarts/cassette/) | quickstart | Record an agent call once, replay it forever offline | `core` `cassette` | ✓ |
| [acttrace](recipes/quickstarts/acttrace/) | quickstart | Signed hash-chain; one edited byte breaks `verify` | `core` `acttrace` | ✓ |
| [guardrails](recipes/quickstarts/guardrails/) | quickstart | Block / redact a call before it's sent; every decision in the audit chain | `core` `guardrails` `acttrace` | ✓ |
| [core](recipes/quickstarts/core/) | quickstart | One `instrument()` wrap → every call on a normalized bus | `core` | ✓ |
| [context-under-budget](recipes/combos/context-under-budget/) | **combo** | The clamp binds on the *assembled* prompt: contextkit's receipt **is** the billed input, measured | `core` `contextkit` `squeeze` `tokenguard` | ✓ |
| [compress-and-restore](recipes/combos/compress-and-restore/) | **combo** | A reversible eviction, chained as a metadata-only `compression` audit entry that holds no text | `core` `contextkit` `squeeze` `acttrace` | ✓ |
| [record-a-governed-run](recipes/combos/record-a-governed-run/) | **combo** | Record the governed triad once, replay it at `$0` — proven by a client that raises if reached | `core` `cassette` `tokenguard` `acttrace` | ✓ |
| [break-midstream-audited](recipes/combos/break-midstream-audited/) | **combo** | `on_exceed="break"` cuts a runaway stream and closes the socket; the cut is chained + verifies | `core` `tokenguard` `acttrace` | ✓ |
| [block-before-record](recipes/combos/block-before-record/) | **combo** | A guardrail block pre-empts the recorder — 2 requests in, 1 call and 1 cassette entry out | `core` `guardrails` `cassette` | ✓ |
| [deterministic-assembly](recipes/combos/deterministic-assembly/) | **combo** | Byte-identical assembly across runs is what makes a replay mean anything (with a hash control) | `core` `contextkit` `cassette` | ✓ |
| [tokenguard-hard-vs-runaway](recipes/libs/tokenguard-hard-vs-runaway/) | library | `clamp` (provider-enforced) vs `break` (mid-flight) — including `break` on a non-stream | `core` `tokenguard` | ✓ |
| [tokenguard-durable-spend](recipes/libs/tokenguard-durable-spend/) | library | `QueueSink` off the hot path + the `BudgetEvent` stream, the only trace a blocked call leaves | `core` `tokenguard` | ✓ |
| [contextkit-eviction-receipt](recipes/libs/contextkit-eviction-receipt/) | library | priority / pin / evict / keep, and the `AssemblyReport` receipt; `whatif()` prices a tighter budget | `core` `contextkit` | ✓ |
| [contextkit-plug-a-compressor](recipes/libs/contextkit-plug-a-compressor/) | library | `use_compressor()` with a domain backend — no base class, no call-site change | `core` `contextkit` `squeeze` | ✓ |
| [squeeze-four-compressors](recipes/libs/squeeze-four-compressors/) | library | json / logs / code / prose × fidelity, with ratios measured on the recipe's own inputs | `core` `squeeze` | ✓ |
| [squeeze-persist-and-restore](recipes/libs/squeeze-persist-and-restore/) | library | `SQLiteStore` + `decompress()` across a **real** process restart, with the MemoryStore failure shown | `core` `squeeze` | ✓ |
| [cassette-four-modes](recipes/libs/cassette-four-modes/) | library | record / replay / rerecord / auto — and why `auto` is wrong for CI | `core` `cassette` | ✓ |
| [cassette-semantic-drift](recipes/libs/cassette-semantic-drift/) | library | Measured: a surface scorer keeps the paraphrase and drops the real change — why `scorer=` exists | `core` `cassette` | ✓ |
| [acttrace-custom-detector](recipes/libs/acttrace-custom-detector/) | library | `register_detector()` with a validator + `enable_locale_pack()`; 1 of 5 found before, 5 after | `core` `acttrace` | ✓ |
| [core-seams](recipes/libs/core-seams/) | library | `trace()`, `add_stream_observer()` (an enforcement seam) and `tokens.register()` | `core` | ✓ |
| [openai-chat](recipes/providers/openai-chat/) | provider · RECORD | Pre-flight budget + attribution on Chat Completions | `core` `tokenguard` | ✓ |
| [openai-responses](recipes/providers/openai-responses/) | provider · RECORD | Capture reasoning + cached tokens on the Responses API | `core` `tokenguard` | ✓ |
| [anthropic](recipes/providers/anthropic/) | provider · RECORD | Price prompt-cache reads/writes correctly, audited | `core` `tokenguard` `acttrace` | ✓ |
| [ollama-local](recipes/providers/ollama-local/) | provider · Local | Budgeted, recorded, audited turn on a $0 local model | `core` `tokenguard` `cassette` `acttrace` | ✓ |
| [azure-foundry](recipes/providers/azure-foundry/) | provider · RECORD | Your **deployment name** is unpriced, so a USD cap silently never binds — then one `prices.register_model_price` line and it does. v1 GA endpoint + the Foundry SDK | `core` `tokenguard` | ✓ |
| [gemini](recipes/providers/gemini/) | provider · RECORD | `usage_metadata`, not `usage` — one seam, budget + audit unchanged; streaming captured | `core` `tokenguard` `acttrace` | ✓ |
| [bedrock](recipes/providers/bedrock/) | provider · RECORD | camelCase Converse usage, and the two caps that work on an unpriced marketplace id | `core` `tokenguard` | ✓ |
| [langchain](recipes/frameworks/langchain/) | framework · Live swap | Cost + audit without changing LangChain code (+LangGraph) | `core` `tokenguard` `acttrace` | ✓ |
| [openai-agents-sdk](recipes/frameworks/openai-agents-sdk/) | framework · RECORD | Budget + audit a loop the Agents SDK fully owns | `core` `tokenguard` `acttrace` | ✓ |
| [llamaindex](recipes/frameworks/llamaindex/) | framework | Pack RAG retrieval to a token budget, reversibly | `core` `contextkit` `squeeze` | ✓ |
| [azure-foundry-otel](recipes/frameworks/azure-foundry-otel/) | framework | Budget + audit calls your process never made (OTel spans) | `core` `tokenguard` `acttrace` | ✓ |
| [otel-export](recipes/observability/otel-export/) | observability | Stream spend + the audit trail + a budget block to any OTel backend (Azure Monitor / CloudWatch / Datadog); the file stays the evidence | `core` `tokenguard` `acttrace` | ✓ |
| [batch-ingest](recipes/observability/batch-ingest/) | observability | Account for a completed Batch API job's spend after the fact (`otel.ingest` per result line) — no pre-flight possible, but the accounting is | `core` `tokenguard` | ✓ |
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
| [openai-agents-guardrail](recipes/bridges/openai-agents-guardrail/) | bridge | A cendor Guardrail as an OpenAI Agents SDK `@input_guardrail` | `guardrails` + `openai-agents` | ✓ |
| [claude-agent-pretooluse](recipes/bridges/claude-agent-pretooluse/) | bridge | A cendor Guardrail as a Claude Agent SDK `PreToolUse` hook (deny a tool call) | `guardrails` + `claude-agent-sdk` | ✓ |
| [mcp-tool-gating](recipes/bridges/mcp-tool-gating/) | bridge | Gate a `FastMCP` server's tools with a cendor Guardrail at the tool boundary | `guardrails` + `mcp` | ✓ |
| [langchain-middleware](recipes/bridges/langchain-middleware/) | bridge | A cendor Guardrail as a LangChain `before_model` agent middleware | `guardrails` + `langchain` | ✓ |

**RECORD** recipes ship green offline against a fake client and carry a `RECORD=1` path a
maintainer runs once with a real key to capture a replayable cassette (secrets redacted on write).
**Local** = also runs against a live local Ollama daemon with a one-line swap.

## Run any recipe

Every recipe is a folder with a `main.py` you can run directly. Quickstart, provider, SDK, combo,
per-library, and governance recipes run on the base install; framework, bridge, and agent-host
recipes each need their own dependency group so a breaking release in one can't turn the others red:

| Category | Command |
|---|---|
| quickstart / provider | `uv run python recipes/<category>/<name>/main.py` |
| **sdk** | `uv run python recipes/sdk/<name>/main.py` |
| **combos** | `uv run python recipes/combos/<name>/main.py` |
| **libs** | `uv run python recipes/libs/<name>/main.py` |
| governance | `uv run python recipes/governance/<name>/main.py` |
| testing | `uv run pytest recipes/testing` |
| frameworks · langchain | `uv run --group frameworks-langchain python recipes/frameworks/langchain/main.py` |
| frameworks · openai-agents-sdk | `uv run --group frameworks-agents python recipes/frameworks/openai-agents-sdk/main.py` |
| frameworks · llamaindex | `uv run --group frameworks-llamaindex python recipes/frameworks/llamaindex/main.py` |
| frameworks · azure-foundry-otel | `uv run --group frameworks-otel python recipes/frameworks/azure-foundry-otel/main.py` |
| bridges · openai-agents-guardrail | `uv run --group frameworks-agents python recipes/bridges/openai-agents-guardrail/main.py` |
| bridges · claude-agent-pretooluse | `uv run --group frameworks-claude-agent python recipes/bridges/claude-agent-pretooluse/main.py` |
| bridges · mcp-tool-gating | `uv run --group frameworks-mcp python recipes/bridges/mcp-tool-gating/main.py` |
| bridges · langchain-middleware | `uv run --group frameworks-langchain python recipes/bridges/langchain-middleware/main.py` |
| observability · otel-export | `uv run --group observability-otel python recipes/observability/otel-export/main.py` |
| observability · batch-ingest | `uv run --group observability-otel python recipes/observability/batch-ingest/main.py` |
| **agents** · m365-custom-engine-py | `uv run --group agents-m365 python recipes/agents/m365-custom-engine-py/main.py` |
| apps · chat-playground | `uv run --group apps python recipes/apps/chat-playground/app.py` |

Any recipe that ships a test file is also runnable via `uv run pytest recipes/<category>/<name>`.
Every category above has a matching job in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) —
that is what backs the "every recipe runs offline" claim, so a new category needs a new job.

### Or run it as a notebook

**20 recipes ship a `notebook.ipynb` beside `main.py`** — all 7 `quickstarts/`, all 7 `providers/`
and all 6 `combos/`. Each tells the same story a cell at a time: markdown carries the *why*, every
step prints its own output, and the final cell asserts exactly what the script asserts.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/quickstarts/core/notebook.ipynb
```

In a Codespace they are runnable the moment it opens — the devcontainer installs the Jupyter
extension. They are **executed in CI** (`pytest --nbmake`, on both Python 3.11 and 3.13), so a
notebook cannot rot into a screenshot of code that used to work; and because each one's final cell
mirrors its `main.py`, a library change that breaks one breaks both.

## How offline works

Three mechanisms, and every recipe uses one of them. None needs a key, a network, or a daemon.

**1. A fake provider-shaped client** (most recipes). `instrument()` identifies an LLM client by its
**shape**, not by network access — so a plain `types.SimpleNamespace` with the same
`chat.completions.create` / `responses.create` / `messages.create` / `chat(...)` surface is all it
needs. The fake returns a canned `usage`, and Cendor normalizes and prices it from a bundled offline
snapshot exactly as it would a real call.

**2. A committed cassette fixture, replayed** (3 recipes, 4 fixture files). Where the recipe's *point* is a real
model call — a judge screening a prompt — the exchange is recorded once into a small JSON file that
is committed, and every run after that replays it:

| Recipe | Fixture | Mode |
|---|---|---|
| [llm-judge-guardrail](recipes/governance/llm-judge-guardrail/) | `fixtures/judge.json` | `cassette.use(…, mode="auto")` — replays when the file exists |
| [task-adherence](recipes/governance/task-adherence/) | `fixtures/adherence.json` | `cassette.use(…, mode="auto")` |
| [pytest-cassette](recipes/testing/pytest-cassette/) | `fixtures/triage.json`, `fixtures/tool.json` | `mode="replay"` — **strict**: an unrecorded call raises, so drift can't pass silently. One file per test, so `pytest -n auto` stays safe. Re-record deliberately with `RERECORD=1 uv run pytest …` |

**3. Record-then-replay in one run** (1 recipe). The [cassette quickstart](recipes/quickstarts/cassette/)
proves the round-trip rather than shipping a fixture: it records into a `tempfile.TemporaryDirectory()`
and immediately replays from it, asserting the second pass made **zero** calls. Nothing is committed,
because the artifact is the demonstration.

**Committed fixture vs. generated recording — and where `RECORD=1` actually writes.** A recipe's own
`fixtures/` directory is a reviewed input, added explicitly and read by CI. ⚠️ **A `RECORD=1` /
`RERECORD=1` run writes straight into that same `fixtures/` directory** — it does *not* go to the
ignored `**/_recordings/` path (that pattern is `.gitignore`d for ad-hoc local recordings and is not
where any recipe writes). So a maintainer recording against a real key **dirties tracked-adjacent
files by design**: check `git diff` afterwards and either commit the refresh deliberately or
`git checkout -- <recipe>/fixtures/` / delete the new directory. Cassette redacts ids and secrets on
write regardless, and the RECORD recipes ship **unrecorded** — CI runs their fake-client path.

Costs shown anywhere come from `prices.estimate` on the stated token counts — no invented numbers.

## Pins

**There is exactly one shelf for the whole repo, and it lives in
[`pyproject.toml`](pyproject.toml).** Every recipe here installs the *published* PyPI packages
through that single manifest — no per-recipe pin file, so there is nothing to drift out of sync
with anything else. (The TypeScript twin is the other way round: `cendor-cookbook-js` gives every
recipe its own `package.json` and therefore its own `## Pins` section, because a copy-pasteable
`package.json` is the thing it needs to prove resolves.)

| Range | Why that floor |
|---|---|
| `cendor-core>=1.17.0,<2.0` | Anthropic `messages.stream()`/`parse()` are captured (they emitted nothing before), and a `Reroute` no longer ends the interceptor chain — several `combos/` recipes install a budget *and* a guard on the same call, and before 1.17.0 exactly one of them took effect, silently, depending on registration order |
| `cendor-libs>=1.0,<2.0` · `cendor-sdk>=1.0,<2.0` | the umbrella + the SDK recipes |
| `cendor-guardrails>=1.4,<2.0` | `rules.intent` / `custom_category` |
| `cendor-acttrace>=1.4,<2.0` | decision `metadata` (`policy_hash` / `policy_version`) reaches the chain |
| `cendor-tokenguard>=1.6.3,<2.0` | an explicit floor so a fresh resolve cannot land on the 1.6.1 post-flight message the `bedrock` recipe teaches against |

⚠️ **`uv.lock` is deliberately NOT committed** — see the reason in [`.gitignore`](.gitignore). CI runs
a bare `uv sync` with no `--frozen`/`--locked`, so every run re-resolves against the current shipped
packages and the weekly cron is what catches dependency drift. Recipes pin **ranges**, not a frozen
lock. To check your own working copy against what is actually published:

```bash
uv run python scripts/check_shelf.py    # exits 1 and names the package if anything is behind
```

## Contributing

New recipes are welcome — the one hard rule is **it runs green offline, with no key**. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the recipe template and the offline bar.

Also: [Code of Conduct](CODE_OF_CONDUCT.md) · [Security policy](SECURITY.md) — **never** open a public
issue for a security problem; report it privately through the Security tab.

## Links

- **TypeScript cookbook:** [github.com/cendorhq/cendor-cookbook-js](https://github.com/cendorhq/cendor-cookbook-js)
  — the same recipes in TypeScript, same folder names, one repo per toolchain.
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
