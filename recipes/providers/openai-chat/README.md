# openai-chat — cost controls for the classic Chat Completions API

**The pain.** You're on `chat.completions.create` and want a hard spend cap and per-feature
attribution — without rewriting your call sites or bolting on a proxy.

**What this shows.** `instrument()` wraps the client once; a pre-flight `@budget(usd=0.50,
on_exceed="block")` refuses the call that would cross the cap, and `track(feature=…, user_id=…)`
attributes spend. Audit and record/replay ride the **same seam** — see the `RECORD=1` path in
`main.py` and the [anthropic](../anthropic/) / [pytest-cassette](../../testing/pytest-cassette/)
recipes.

## The five steps (every recipe in `providers/` walks these, in this order)

| # | Step | What it is here |
|---|---|---|
| 1 | **connect** | `OpenAI()` — the classic `chat.completions.create` shape |
| 2 | **instrument** | one wrap — detection is structural, not name-based |
| 3 | **govern** | a pre-flight `@budget(usd=0.50, on_exceed="block")` **and** a `keyword_deny` gate |
| 4 | **record** | `cassette` — the same call replayed offline: **0 provider calls, $0** |
| 5 | **prove** | `acttrace` `verify()` over the hash chain, and a cost that came from `prices` |

**Distinctive here: attribution.** `track(feature=…, user_id=…)` tags each call and
`report(group_by=…)` turns the tags into a spend table — the answer to *which feature
spent it*.

## Run it

```bash
uv run python recipes/providers/openai-chat/main.py
```

## Expected output

```text
gate      : BLOCKED by keyword_deny (input) - denied keyword: 'ignore previous instructions'
            provider saw 0 call(s) => $0 spent on it
budget    : BudgetExceeded - blocked pre-flight, no call ran
spend     : by feature/user
            {'feature': 'support_bot', 'user_id': 'user-42'} 5 calls  $0.450000000
            TOTAL 5 calls  $0.450000000
cassette  : replayed 1 call, 0 provider call(s), $0
verify()  : True - ok: 12 entries, head ecf96a3e5783…
```

Five turns ran ($0.45); the sixth was blocked before it reached the model, and the injection attempt
never reached it at all. All costs come from `prices.estimate` on the stated token counts, and the
run **asserts** every claim above — a cap that stopped working fails the recipe instead of quietly
changing the numbers.

⚠️ **The "6th turn" is a property of the FAKE's usage** (12,000 in / 6,000 out per call), not of
`gpt-4o`. A real reply is ~50 output tokens, so against a live key the same `$0.50` cap lasts far
longer — see `quickstarts/tokenguard` for the measured live figure.

**Live cassette (RECORD ✓, ships unrecorded):** a maintainer records a real call once with
`RECORD=1 OPENAI_API_KEY=sk-... uv run --group apps python .../main.py` — `openai` is not a base
dependency of this repo, so the `--group apps` is required. The recording lands in this recipe's
`fixtures/` directory; **no fixture is committed**, so CI always runs the fake-client path above.

## Run it as a notebook

[`notebook.ipynb`](notebook.ipynb) tells the same story a cell at a time — each step prints its own
output, the markdown carries the *why*, and the last cell asserts what `main.py` asserts. Offline
like everything else.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/providers/openai-chat/notebook.ipynb
```

In a Codespace it is already runnable — the devcontainer installs the Jupyter extension, so just
open the file and **Run All**.

> The notebooks are **executed in CI** (`pytest --nbmake`, Python 3.11 and 3.13), so one that stops
> working turns the build red rather than quietly becoming a screenshot of code that used to run.


Libraries: `core`, `tokenguard`, `guardrails`, `cassette`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
