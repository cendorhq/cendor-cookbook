# break-midstream-audited — cut a runaway stream mid-flight, and keep the evidence

**The pain.** A pre-flight cap cannot help you here. You asked for one paragraph; the model is four
thousand tokens into a loop and still going. The request was already approved, and by the time the
response settles you have paid for all of it.

**What this shows.** `on_exceed="break"` is the guard for exactly that shape. `tokenguard` registers
a per-chunk observer on core's stream seam; when the running output estimate crosses the cap it
**closes the provider stream**, keeps the partial text, and raises once. Because the cut is a
governance action, `acttrace` chains it as a `budget_event(action="broken")` on the same
tamper-evident file as everything else — and the chain still verifies.

## Run it

```bash
uv run python recipes/combos/break-midstream-audited/main.py
```

## Expected output

```text
stream       : cut after 9 of 60 chunks (partial text kept)
provider     : underlying stream closed = True
raised       : 1x BudgetExceeded - mid-stream break: streamed output ~23 tokens crossed the remaining budget (~20 left) for gpt-4o; the stream was cut. You keep the partial output; the provider bills to the cut (~one chunk + one RTT).
chained      : budget_event(action='broken'), cap 20 tokens
verify()     : True - ok: 3 entries, head ff5f19ede00f…
```

`underlying stream closed = True` is the line to read. A consumer-side `break` out of the `for` loop
would stop *your* iteration while the provider kept generating and billing; this closes the socket.
The fake stream's `close()` sets a flag, and the recipe asserts it — so the claim is measured.

**`break` is not a substitute for `block`.** It cuts a stream that is already running; it cannot
refuse a call, and a non-streamed response can still cross the cap post-flight. Choosing between
them by intent is [`libs/tokenguard-hard-vs-runaway`](../../libs/tokenguard-hard-vs-runaway/).

Libraries: `core`, `tokenguard`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
