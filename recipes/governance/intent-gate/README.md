# intent-gate — decide whether a request should reach the model at all

**The pain.** Not every turn deserves a model call. A support bot asked to write poetry, a request
for a topic you don't serve — you want to catch that *before* you spend a token, and neither a
keyword denylist (too literal) nor a content classifier (wrong question) answers "is this on-task?"

**What this shows.** `rules.intent(...)` screens a turn by **intent**, at the `input` stage.
`mode="allow"` is an off-topic gate (trip when the request matches **none** of your topics);
`mode="deny"` refuses a topic you never serve. Three backends — an offline keyword **classifier**
(used here), embedding exemplars (pass a BYO `embed`), or a small-LLM judge
(`judge.intent_prompt` + `rules.llm_judge`, its own spend budgeted + audited). No accuracy claim: a
screening heuristic — keep it `flag` until you calibrate, then `block`.

## Run it

```bash
uv run python recipes/governance/intent-gate/main.py
uv run pytest recipes/governance/intent-gate      # deterministic classifier; 0 live calls
```

## Expected output

```text
=== on-topic (support) — passes ===
  "I can't reset my password, the login page shows an error" -> decisions: []

=== off-topic — flagged before the model runs ===
  intent flag: off-topic (closest 'support' 0.00 < 0.15)  metadata={'intent': 'support', 'score': 0.0}

=== deny-mode block === denied intent 'billing': 0.33 >= 0.15
```

**Honest limits.** An intent gate is a heuristic, not a guarantee — there is **no accuracy claim**.
The keyword classifier here is a stand-in; swap in a trained CLU-style model, an ONNX head, or the
embedding backend (`embeddings.local_embedder()`, the `[embeddings]` extra) for production. Calibrate
the threshold on your own traffic and prefer `flag` until you have.

Libraries: `core`, `guardrails` · Offline ✓ · [← all recipes](../../../README.md)
