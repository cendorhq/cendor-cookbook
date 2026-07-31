# tokenguard-hard-vs-runaway — `clamp` and `break` guard different failures

**The pain.** `on_exceed` takes six values and two of them look like the same thing. `clamp` and
`break` both "cap the output", the docs list them a line apart, and picking the wrong one means
either a truncated answer you did not want or a runaway you did not stop.

**What this shows.** The two mechanisms side by side, measured — including the case that makes the
difference obvious: `break` on a call that isn't streaming.

| | enforced by | when | on a non-stream |
|---|---|---|---|
| `clamp` | the **provider** — tokenguard injects `max_completion_tokens` (or the nested equivalent) before the request goes out | pre-flight | works: the ceiling is on the request |
| `break` | **you**, mid-flight — a per-chunk observer closes the provider stream | during the stream | nothing to cut; it can only notice **post-flight**, once you have paid |

## Run it

```bash
uv run python recipes/libs/tokenguard-hard-vs-runaway/main.py
```

## Expected output

```text
clamp  (non-stream) : injected max_completion_tokens=188 -> 1 clamp, no exception, the call ran
break  (stream)     : cut after 4/80 chunks, provider stream closed=True
break  (non-stream) : raised POST-flight - the money is already spent
                      budget exceeded: used 940 tokens > cap 25 tokens after 1 call(s); last model=gpt-4o. on_exceed='
choose              : clamp when the answer should be short (provider enforces it); break when length is unknown and you want a stop button
```

Read the third line. `break` did not fail — it did the only thing available on a non-streamed call,
which is tell you afterwards. If that is not what you wanted, the answer is `block` (refuse the call
pre-flight) or `clamp` (bound the response), not a bigger cap.

`provider stream closed=True` on the second line is the part that distinguishes `break` from a plain
`break` statement in your own `for` loop: a consumer-side exit stops *your* iteration while the
provider keeps generating and billing. This closes the socket.

**Rule of thumb.** `clamp` when you know the answer should be short. `break` when you don't know how
long it will be and want a stop button. `block` when the call must not happen at all
([quickstart](../../quickstarts/tokenguard/)). The audited version of the mid-stream cut is
[`combos/break-midstream-audited`](../../combos/break-midstream-audited/).

Libraries: `core`, `tokenguard` · Offline ✓ · [← all recipes](../../../README.md)
