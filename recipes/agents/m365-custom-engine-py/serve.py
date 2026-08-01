"""Start the governed agent on :3978 so the M365 Agents Playground can drive it.

    uv run --group agents-m365 python recipes/agents/m365-custom-engine-py/serve.py

Then, in another terminal:

    agentsplayground -e "http://localhost:3978/api/messages" -c emulator

⚠️ **This file exists because the one-liner in the README was the recipe's most reported failure.**
`python -c "import agent; agent.serve(...)"` is the only command in this repo that skips the
project's toolchain, and it needs the current directory to be *this* folder. Measured on a clean
shell: bare `python` gives `ModuleNotFoundError: No module named 'cendor.acttrace'`, and running it
from the repo root gives `ModuleNotFoundError: No module named 'agent'`. Both read as "the recipe
doesn't run" and neither has anything to do with the agent.

So: this script fixes `sys.path` to its own directory, and turns a busy port into one readable line
instead of a raw `OSError: [Errno 10048]` traceback out of aiohttp.

Nothing here is a cendor surface — it is three lines of ergonomics around `agent.serve()`.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # so `import agent` works from any cwd

import agent as agent_mod  # noqa: E402

PORT = int(os.environ.get("PORT", "3978"))
AUDIT = os.environ.get("AUDIT_PATH", str(HERE / "chain.jsonl"))


def _port_is_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def main() -> int:
    if not _port_is_free(PORT):
        print(
            f"Port {PORT} is already in use — something else is listening there.\n"
            f"Stop it, or start this agent somewhere else:  PORT=3988 uv run --group agents-m365 "
            f"python {Path(__file__).name}",
            file=sys.stderr,
        )
        return 2

    print(f"audit chain : {AUDIT}")
    print(f"endpoint    : http://localhost:{PORT}/api/messages   (anonymous — LOCAL ONLY)")
    print(f'drive it    : agentsplayground -e "http://localhost:{PORT}/api/messages" -c emulator')
    print("(verified against @microsoft/m365agentsplayground 0.2.28)\n")
    agent_mod.serve(agent_mod.GovernedAgent(audit_path=AUDIT), port=PORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
