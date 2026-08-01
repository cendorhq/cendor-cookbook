"""chat-playground — every constant, in one place, with the reason it has that value.

Nothing here imports Gradio, so the whole configuration (and `sizing()`, the one function that
decides demo-vs-live) is importable and testable without a UI.
"""

from __future__ import annotations

import os

# ── models ────────────────────────────────────────────────────────────────────────────────────
DEMO_MODEL = "gpt-4o"
OPENAI_MODEL = "gpt-4o"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
# Pre-flight downgrade targets (cheaper siblings) for on_exceed="downgrade".
DOWNGRADE = {"gpt-4o": "gpt-4o-mini", "claude-sonnet-4-6": "claude-haiku-4-5"}

# ── sizing ────────────────────────────────────────────────────────────────────────────────────
# A support assistant that stuffs a product knowledge base + chat history into context each turn.
# The KB is deliberately large so the budget math and the context receipt both have something real
# to chew on: with a $0.50 cap the ~$0.09/turn spend trips the pre-flight block around the 6th turn,
# and the history block visibly peels its oldest turns as the chat grows past the token budget.
CONTEXT_BUDGET = 40_000
RESERVE_OUTPUT = 1_000
KB_UNITS = 424  # ~91 tokens/unit -> ~38.6k tokens
DEFAULT_CAP = 0.50

# ⚠️ LIVE MODE IS SIZED SEPARATELY, and it has to be. The numbers above are calibrated against the
# *fake* client, which is free and has no rate limit. Sent to a real provider they are a wall:
# a 40k budget packs ~38.7k input tokens into EVERY turn, and OpenAI's default tier allows
# 30,000 tokens per minute — so live mode used to die on turn 1 with
#   429 Request too large for gpt-4o ... on tokens per min (TPM): Limit 30000, Requested 50818
# (measured 2026-07-31; the "Requested" figure is the input plus OpenAI's own output reservation).
# It was not a slow leak either: Anthropic, whose limit is higher, billed 43,313 input tokens for
# one "hi" — **$0.13 per message**, blowing the app's own $0.50 cap in four turns.
# So live mode keeps the same *shape* — a KB big enough to truncate, history that peels, a cap that
# trips after a handful of turns — at roughly a seventh of the size. The model stays the same as
# demo mode so the receipt, the pricing and the downgrade demo all still line up.
# Re-measured 2026-08-01 at `_run_turn()`: 4,440 in / 59 out, $0.011690 on gpt-4o (cap trips ~turn
# 8) and 4,970 in / 164 out, $0.017370 on claude-sonnet-4-6 (~turn 5). No 429 on either.
LIVE_CONTEXT_BUDGET = 6_000
LIVE_KB_UNITS = 48
LIVE_DEFAULT_CAP = 0.10

COMPRESS_THRESHOLD = 1_500  # chars pasted before squeeze kicks in
COMPRESS_TARGET_TOKENS = 400
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # reject cassette uploads larger than 2 MB
SUPPORTED_CASSETTE_VERSIONS = (1, 2)

# Demo signing key: env override, fallback so the app is green out of the box. In production load
# this from a secret manager — never commit a real key.
SIGNING_KEY = os.environ.get("CENDOR_DEMO_KEY", "demo-signing-key")

SYSTEM_PROMPT = (
    "You are Cendor Store's support assistant. Answer using the knowledge base provided, cite the "
    "relevant policy number when you can, and keep replies concise and friendly."
)

_KB_UNIT = (
    "Policy {n}: Duplicate or double charges are refunded within five business days once a "
    "billing agent confirms the transaction id. A refund needs the order number, the charge "
    "date, and the last four digits of the card on file. Subscription cancellations take effect "
    "at the end of the current billing period; prorated credits are not issued. Shipping delays "
    "beyond ten business days qualify for expedited reshipment at no cost. Tier-two support "
    "handles chargebacks and fraud holds. "
)


def kb(units: int) -> str:
    """The synthetic knowledge base, `units` policies long."""
    return "Cendor Store — Support Knowledge Base.\n" + "".join(
        _KB_UNIT.format(n=i) for i in range(1, units + 1)
    )


KB_DOC = kb(KB_UNITS)
LIVE_KB_DOC = kb(LIVE_KB_UNITS)


def sizing(run_mode: str) -> tuple[int, str, float]:
    """(context budget, knowledge base, default cap) for this run mode.

    The single place demo and live diverge. Every caller that packs context or sets a cap goes
    through here, so the two calibrations cannot drift apart — which is what made the 429 possible.
    """
    if run_mode == "Demo":
        return CONTEXT_BUDGET, KB_DOC, DEFAULT_CAP
    return LIVE_CONTEXT_BUDGET, LIVE_KB_DOC, LIVE_DEFAULT_CAP


def model_for(run_mode: str, provider: str) -> str:
    """Which model a turn will use — demo and live share `gpt-4o` so the receipt lines up."""
    if run_mode == "Demo":
        return DEMO_MODEL
    return OPENAI_MODEL if provider == "OpenAI" else ANTHROPIC_MODEL


# Deterministic canned replies, varied in length. Several are intentionally long so the chat
# history block grows quickly — enough to watch contextkit peel its oldest turns in the receipt.
CANNED_REPLIES = [
    "Hi! I'm the Cendor Store assistant. I can help with refunds, orders, shipping, cancellations, "
    "and billing questions. I'll always cite the relevant policy so you can see exactly why "
    "something is or isn't covered. To get started, tell me your order number and what happened — "
    "for a billing issue, the charge date and the last four digits of the card help me find it "
    "fast. What can I do for you today?",
    "Per Policy 1, a duplicate or double charge is refunded within five business days once a "
    "billing agent confirms the transaction id. To confirm it, I need three things: the order "
    "number, the date of the charge, and the last four digits of the card on file. As soon as I "
    "have those I'll match the transaction, queue the reversal, and email you a confirmation with "
    "a reference number you can quote if you ever need to follow up.",
    "Good news — I found the order and I can see the two identical charges from the same day. "
    "I've queued the duplicate for reversal under Policy 1, so you'll see the credit land on your "
    "statement within five business days. I've also emailed a receipt with today's reference "
    "number. The original, legitimate charge stays in place; only the accidental duplicate is "
    "being returned. Is there anything else on the account I should check while I'm here?",
    "Refund eligibility under Policy 1 comes down to three details: the order number, the charge "
    "date, and the last four digits of the card. Once you send those, I verify the transaction "
    "against our records, and if it matches I can start the reversal immediately — no manager "
    "approval needed for a confirmed duplicate. If any detail doesn't line up, I'll tell you "
    "exactly what's missing rather than leaving you guessing.",
    "For a subscription cancellation, the change takes effect at the end of your current billing "
    "period, so you keep full access until then and won't be charged again afterward. Prorated "
    "credits aren't issued for the unused part of the period — that's covered in the cancellation "
    "policy — but there are no cancellation fees either. Want me to schedule it to end at your "
    "next renewal date, or cancel it right away and let access lapse at period end?",
    "When a shipment runs more than ten business days late, our policy covers a free expedited "
    "reshipment at no cost to you — you don't pay twice and you don't wait in line behind new "
    "orders. I can trigger that reshipment now; I just need you to confirm the delivery address on "
    "file is still correct. If the original package turns up later, you're welcome to keep or "
    "return it, whichever is easier — there's no penalty either way.",
    "That looks like a chargeback question, which tier-two support owns rather than the front "
    "line. I've flagged your case for them and attached the transaction id and the notes from our "
    "conversation so you won't have to repeat yourself. They typically follow up by email within "
    "one business day. In the meantime, avoid filing a bank dispute for the same charge, since a "
    "duplicate dispute can actually slow the refund down.",
    "Happy to help! To summarize what we've covered so far: I confirmed the order, started the "
    "refund for the duplicate charge under Policy 1, and emailed you a receipt with a reference "
    "number. Nothing else on the account looks unusual — no failed payments, no pending holds, and "
    "the subscription is active and paid through the current period. Is there anything else you'd "
    "like me to look into while we're connected?",
    "I don't see a matching transaction under that order number, which usually means one of a few "
    "things: a typo in the number, an order placed under a different email, or a charge that's "
    "still pending and hasn't posted yet. Could you double-check the number, or share the email "
    "address the order was placed under? I can search by email, by the last four digits of the "
    "card, or by the approximate charge date — whichever is easiest for you.",
    "You're welcome — glad I could sort that out. Your reference number for today's refund is in "
    "the confirmation email I just sent; keep it handy in case you ever need to reference this "
    "conversation. The credit should appear within five business days, and if it hasn't shown up "
    "by then, reply to that email with the reference and we'll escalate it immediately. Thanks for "
    "being a Cendor Store customer, and reach out any time.",
]

_KEYWORDS = [
    (("hello", "hi ", "hey"), 0),
    (("cancel", "subscription", "unsubscribe"), 4),
    (("late", "shipping", "delivery", "arrive"), 5),
    (("chargeback", "fraud", "dispute"), 6),
    (("thank", "thanks", "cheers"), 9),
    (("refund", "double", "duplicate", "charged"), 1),
]


def demo_reply(user_text: str, turn: int) -> str:
    """A deterministic canned reply: keyword match first, else cycle by turn (great for videos)."""
    text = f" {user_text.lower()} "
    for needles, idx in _KEYWORDS:
        if any(n in text for n in needles):
            return CANNED_REPLIES[idx]
    return CANNED_REPLIES[turn % len(CANNED_REPLIES)]
