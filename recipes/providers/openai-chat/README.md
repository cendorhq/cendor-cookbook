# openai-chat — cost controls for the classic Chat Completions API

**The pain.** You're on `chat.completions.create` and want a hard spend cap and per-feature
attribution — without rewriting your call sites or bolting on a proxy.

**What this shows.** `instrument()` wraps the client once; a pre-flight `@budget(usd=0.50,
on_exceed="block")` refuses the call that would cross the cap, and `track(feature=…, user_id=…)`
attributes spend. Audit and record/replay ride the **same seam** — see the `RECORD=1` path in
`main.py` and the [anthropic](../anthropic/) / [pytest-cassette](../../testing/pytest-cassette/)
recipes.

## Run it

```bash
uv run python recipes/providers/openai-chat/main.py
```

## Expected output

```text
BudgetExceeded: pre-flight block: projected $0.537520000 would exceed cap $0.5 (model=gpt-4o)

Spend by feature/user:
  {'feature': 'support_bot', 'user_id': 'user-42'} 5 calls  $0.450000000
  TOTAL  5 calls  $0.450000000
```

Five turns ran ($0.45); the sixth was blocked before it reached the model. All costs come from
`prices.estimate` on the stated token counts.

**Live cassette (RECORD ✓, ships unrecorded):** a maintainer records a real call once with
`RECORD=1 OPENAI_API_KEY=sk-... uv run --group apps python .../main.py` — `openai` is not a base
dependency of this repo, so the `--group apps` is required. The recording lands in this recipe's
`fixtures/` directory; **no fixture is committed**, so CI always runs the fake-client path above.

Libraries: `core`, `tokenguard` · Offline ✓ · [← all recipes](../../../README.md)
