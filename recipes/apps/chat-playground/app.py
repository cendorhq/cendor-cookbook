"""chat-playground — a chat UI with Cendor's plumbing made visible on every turn.

You normally cannot *see* the cost/context/governance/audit layer under an LLM app. This Gradio app
puts a chat on the left and the machinery on the right, so every turn shows **all seven libraries**
doing real work:

  * Budget (tokenguard)  — a pre-flight USD cap; the block banner when the next call would cross it
  * Receipt (contextkit) — the per-turn assembly receipt as chat history is packed to a budget
  * Compression (squeeze)— paste a big blob and watch it shrink, reversibly, before it is sent
  * Gate (guardrails)    — a DETERMINISTIC gate on the call: it raises before the request leaves
  * Recorder (cassette)  — record the session, replay it offline (0 calls, $0), download/upload it
  * Audit (acttrace)     — offline detection + policy + a growing signed hash chain; export, verify,
                           tamper
  * Bus feed (core)      — one normalized event per call: provider, model, usage, Decimal cost

Everything except the reply text is REAL Cendor. Demo mode (default, no key) uses a fake
provider-shaped client with canned replies priced as gpt-4o; live mode calls OpenAI/Anthropic with
a key from the environment or the password box (the key stays in process memory only).

This file is deliberately thin. The parts worth reading (and testing) are split so none of them
needs Gradio:

    config.py    every constant, with the reason it has that value; `sizing()` (demo vs live)
    session.py   one chat session and the registry that holds it
    engine.py    the turn pipeline — detect -> compress -> assemble -> gate -> budget -> call
    panels.py    the seven renderers; every number comes from a live object
    ui.py        the Gradio layout and the handlers
    theme.py     the Cendor theme + web fonts

Run:  uv sync --group apps && uv run --group apps python recipes/apps/chat-playground/app.py
"""

from __future__ import annotations

from pathlib import Path

from ui import build_demo  # noqa: F401 — the CI smoke test imports `app.build_demo`

__all__ = ["build_demo"]


if __name__ == "__main__":
    build_demo().launch(favicon_path=str(Path(__file__).parent / "assets" / "favicon.svg"))
