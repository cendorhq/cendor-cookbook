"""tokenguard-durable-spend — spend that survives the process, without paying for it per call.

`report()` aggregates in memory. That is perfect for a test and useless for a long-running service:
restart the pod and the month's spend is gone. A **sink** persists each row as it happens — but the
bus fans out to subscribers *inline*, so a naive durable sink adds its disk (or network) latency to
every single model call.

`QueueSink` decouples that: `write()` enqueues and returns immediately, while one daemon worker
drains the queue into the inner sink **in order**. Wrap any sink with it:

    use_sink(QueueSink(SQLiteSink(path)))

Durability is opt-in at shutdown. The worker is a *daemon*, so an abrupt exit can drop queued rows —
call `flush()` (block until drained) or `close()` (flush, stop, close the inner sink) before you go.

The same bus also carries `BudgetEvent`s — the only signal a *blocked* call leaves, because a call
refused pre-flight never becomes an `LLMCall`. Counting those is how you alert on "the breaker
fired", and this recipe counts them beside the spend rows.

Offline: a fake OpenAI-shaped client and a temp SQLite file. No key, no network.

  uv run python recipes/libs/tokenguard-durable-spend/main.py
"""

import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace

from cendor.core import bus, instrument
from cendor.tokenguard import BudgetEvent, BudgetExceeded, budget, report, reset, track, use_sink
from cendor.tokenguard.sinks import QueueSink, SQLiteSink

MODEL = "gpt-4o"


def fake_openai():
    class Completions:
        def create(self, **kw):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=1_000, completion_tokens=200),
                model=MODEL,
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def main() -> None:
    reset()
    db = Path(tempfile.mkdtemp(prefix="cendor-recipe-")) / "spend.db"
    client = fake_openai()

    blocked: list[BudgetEvent] = []

    def watch(event: object) -> None:
        if isinstance(event, BudgetEvent):
            blocked.append(event)

    bus.subscribe(watch)

    sink = QueueSink(SQLiteSink(str(db)))
    previous = use_sink(sink)
    try:
        for tenant in ("acme", "acme", "globex"):
            with track(tenant=tenant), budget(usd=1.00, on_exceed="block"):
                client.chat.completions.create(
                    model=MODEL, messages=[{"role": "user", "content": "hi"}]
                )
        # A fourth call under a cap it cannot fit: refused pre-flight, so it never becomes an
        # LLMCall and never reaches the sink. The BudgetEvent is the only trace it leaves.
        try:
            with track(tenant="globex"), budget(tokens=10, on_exceed="block"):
                client.chat.completions.create(
                    model=MODEL, messages=[{"role": "user", "content": "hi"}]
                )
        except BudgetExceeded:
            pass
        sink.flush()  # block until the worker has drained — the durability handshake
    finally:
        use_sink(previous)
        sink.close()
        bus.unsubscribe(watch)

    # Read the rows back the way a *different* process would: straight out of the file.
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT tags, usd, input_tokens, output_tokens FROM spend").fetchall()

    in_memory = {r["tags"].get("tenant"): r for r in report(group_by=["tenant"]).rows}

    print(f"persisted rows   : {len(rows)} in {db.name} ({db.stat().st_size} bytes)")
    for tags, usd, tin, tout in rows:
        print(f"  {tags:<20} ${usd}  {tin} in / {tout} out")
    print(
        f"in-memory report : acme ${in_memory['acme']['usd'].amount} over "
        f"{in_memory['acme']['calls']} calls, globex ${in_memory['globex']['usd'].amount}"
    )
    print(
        f"budget events    : {len(blocked)} - action={blocked[-1].action!r}, "
        f"cap={blocked[-1].cap_tokens} tokens (a blocked call emits no LLMCall, so this is "
        f"the ONLY signal)"
    )
    print(
        "shutdown         : flush() drained the queue before close() - a daemon worker would "
        "otherwise drop queued rows on an abrupt exit"
    )

    assert len(rows) == 3, "one persisted row per call that actually happened"
    assert len(blocked) == 1 and blocked[-1].action == "blocked", "the block was not on the bus"
    assert all("tenant" in tags for tags, *_ in rows), "track() tags did not reach the sink"


if __name__ == "__main__":
    main()
