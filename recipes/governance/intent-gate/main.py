"""Intent gate — decide whether a request should reach the model at all, before you spend a token.

`rules.intent(...)` screens a turn by **intent**, at the `input` stage. Two modes:
  * `mode="allow"` — an *off-topic* gate: trip when the request matches **none** of the topics you
    serve (a support bot that only answers support/billing questions).
  * `mode="deny"`  — trip when the request matches a topic you never serve.

Three backends (this recipe uses the offline **classifier** one — a tiny keyword `classify(text)` —
so it runs with no model and no network; the embedding + LLM-judge backends are shown as comments).
There is **no accuracy claim**: an intent gate is a screening heuristic — keep it `flag` (advisory)
until you have calibrated it, then `block`.

Offline: no model, no network. Run:
    uv run python recipes/governance/intent-gate/main.py
"""

from cendor.core import bus
from cendor.guardrails import GuardrailTripped, apply, rules

# A tiny, deterministic intent classifier — realistic enough to demo, honest that it is a stand-in.
# Swap in a trained CLU-style model, an ONNX head, or the embedding backend for production.
_KEYWORDS = {
    "support": ["password", "login", "reset", "account", "error", "bug"],
    "billing": ["invoice", "refund", "charge", "card", "subscription", "price"],
}


def classify(text: str) -> dict[str, float]:
    """Return a {label: score} map — the fraction of a label's keywords present in the text."""
    low = text.lower()
    return {label: sum(k in low for k in kws) / len(kws) for label, kws in _KEYWORDS.items()}


def main() -> None:
    bus._reset()

    # allow-mode off-topic gate: flag anything that isn't support or billing.
    gate = rules.intent(
        ["support", "billing"],  # the in-scope labels (classifier backend)
        classify=classify,
        mode="allow",
        threshold=0.15,
        action="flag",  # advisory — surface off-topic, don't hard-block until calibrated
    )

    on_topic = "I can't reset my password, the login page shows an error"
    off_topic = "Write me a poem about the ocean"

    print("=== on-topic (support) — passes ===")
    print(f"  {on_topic!r} -> decisions: {apply([gate], 'input', on_topic)}")

    print("\n=== off-topic — flagged before the model runs ===")
    decs = apply([gate], "input", off_topic)
    for d in decs:
        print(f"  {d.guardrail} {d.action}: {d.reason}  metadata={d.metadata}")

    assert apply([gate], "input", on_topic) == []  # support keywords present → in scope
    assert decs and decs[0].action == "flag" and decs[0].metadata["intent"]  # off-topic → flagged

    # deny-mode + block: refuse a topic outright (here, "billing" is off-limits for this bot).
    deny = rules.intent(["billing"], classify=classify, mode="deny", threshold=0.15, action="block")
    try:
        apply([deny], "input", "I want a refund on my last charge")
        raise AssertionError("expected a block")
    except GuardrailTripped as e:
        print(f"\n=== deny-mode block === {e.decisions[-1].reason}")

    # The other two backends (not run here — they need an embedder / a model):
    #   embedding exemplars (offline once you pass a local embedder):
    #     from cendor.guardrails import embeddings
    #     embed = embeddings.local_embedder()          # pip install 'cendor-guardrails[embeddings]'
    #     rules.intent({"support": ["reset my password"]}, embed=embed, mode="allow")
    #   small-LLM judge (its own spend budgeted + audited through your instrumented client):
    #     from cendor.guardrails import judge
    #     policy = judge.intent_prompt(["support", "billing"], mode="allow")
    #     rules.llm_judge(judge.judge(respond, policy), stage="input", action="flag")
    print("\nintent screening is a heuristic — no accuracy claim; calibrate + prefer flag")


if __name__ == "__main__":
    main()
