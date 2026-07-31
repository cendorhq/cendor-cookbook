# cassette-four-modes — four modes, four environments

**The pain.** The modes are one keyword apart and mean very different things. Pick the convenient
one and your CI quietly starts making live calls the first time a tape is missing — which is the
exact failure a cassette exists to prevent, and it fails green.

**What this shows.** All four modes driven against the same fake provider, with the provider-call
count printed for each, so the difference is a number rather than a description.

| mode | provider | write | use it |
|---|---|---|---|
| `record` | called | writes the tape | once, deliberately, with a key |
| `replay` | **never** | — | CI. An unrecorded call **raises** — strict on purpose |
| `auto` | only if the tape is missing | writes if missing | a laptop. **Wrong for CI**: a missing file silently becomes a live call |
| `rerecord` | called | **does not overwrite** — reports `drift()` | the scheduled refresh check |

And the fifth choice: **no cassette scope at all**. Nothing is intercepted; every call is live. That
is the default, and it is the right answer in production.

## Run it

```bash
uv run python recipes/libs/cassette-four-modes/main.py
```

## Expected output

```text
record   : provider 1x -> tape written (808 bytes)
replay   : provider 0x -> '30 days from delivery.'
           an UNRECORDED call raises: no recorded response for llm request (hash 48f3cff8053b…) in policy.json; re-r
auto     : existing tape -> provider 0x (replayed); missing tape -> provider 1x (recorded)
rerecord : provider 1x -> drift() reports 1 divergence(s); tape unchanged on disk: True
no scope : provider 1x - nothing is intercepted; this is production
```

The `auto` line is the one to internalise: **the same mode did two different things** depending on
whether a file existed. That is convenient locally and dangerous in CI, where "the tape didn't get
committed" should be a red test, not a live call. Use `mode="replay"` there and let the
`CassetteError` tell you.

`rerecord` ran live *and left the tape alone* (`tape unchanged on disk: True`). It answers "has the
provider's answer moved since we recorded?" without you losing the recorded baseline in the act of
asking. Filtering that drift down to changes that actually *mean* something is
[`cassette-semantic-drift`](../cassette-semantic-drift/).

Libraries: `core`, `cassette` · Offline ✓ · [← all recipes](../../../README.md)
