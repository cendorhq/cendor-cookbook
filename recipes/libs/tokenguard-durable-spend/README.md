# tokenguard-durable-spend — spend that survives a restart, without paying for it per call

**The pain.** `report()` aggregates in memory, which is perfect for a test and useless for a service:
restart the pod and the month's spend is gone. So you write the rows to a database — and now every
model call waits on your disk (or worse, your network), because the bus fans out to subscribers
**inline**.

**What this shows.** `QueueSink` wraps any sink so its writes run on a background thread:
`write()` enqueues and returns immediately, one daemon worker drains the queue into the inner sink
**in order**.

```python
use_sink(QueueSink(SQLiteSink(path)))
```

Durability is opt-in at shutdown, and that is deliberate: the worker is a *daemon*, so an abrupt exit
can drop queued rows. `flush()` blocks until the queue is empty; `close()` flushes, stops the worker
and closes the inner sink. Call one before you exit.

It also counts `BudgetEvent`s off the same bus — the **only** signal a blocked call leaves, because a
call refused pre-flight never becomes an `LLMCall` and so never reaches a sink at all.

Closes `QueueSink`, which no other recipe exercises.

## Run it

```bash
uv run python recipes/libs/tokenguard-durable-spend/main.py
```

## Expected output

```text
persisted rows   : 3 in spend.db (8192 bytes)
  {"tenant": "acme"}   $0.004500000  1000 in / 200 out
  {"tenant": "acme"}   $0.004500000  1000 in / 200 out
  {"tenant": "globex"} $0.004500000  1000 in / 200 out
in-memory report : acme $0.009000000 over 2 calls, globex $0.004500000
budget events    : 1 - action='blocked', cap=10 tokens (a blocked call emits no LLMCall, so this is the ONLY signal)
shutdown         : flush() drained the queue before close() - a daemon worker would otherwise drop queued rows on an abrupt exit
```

Four calls were attempted and **three** rows persisted. The fourth was blocked pre-flight, so there
is no spend row for it — correct, because no money was spent, and exactly why you also watch the
`BudgetEvent` stream. Alerting on "spend went up" cannot tell you the breaker fired; alerting on
`action='blocked'` can.

The rows are read back with plain `sqlite3`, the way a *different* process would — the sink is not a
cache in front of `report()`, it is the durable copy.

Your `track(...)` tags travel into the sink (`{"tenant": "acme"}`), so the same attribution you get
from `report(group_by=["tenant"])` is available in SQL after the process is gone.

Libraries: `core`, `tokenguard` · Offline ✓ · [← all recipes](../../../README.md)
