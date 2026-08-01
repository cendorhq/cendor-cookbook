# bedrock — govern Converse, where every model id is unpriced

**The pain.** Two things are different about Bedrock and both bite quietly. Usage comes back as
`{"inputTokens": …, "outputTokens": …}` — camelCase, one level up from where an OpenAI reader looks —
and every Bedrock **model id** is a marketplace id (`eu.amazon.nova-2-lite-v1:0`), so the bundled price
table has no row for it. A USD budget on an unpriced model projects `$0`, which means it **silently
never binds**: the cap is in your code and it is enforcing nothing.

**What this shows.** `instrument()` maps the camelCase usage onto the same normalized `LLMCall`, and
then the two caps that actually work on an unpriced id: a **token** cap needs no rate at all, and a
**USD** cap needs exactly one `prices.register_model_price(...)` line.

## The five steps (every recipe in `providers/` walks these, in this order)

| # | Step | What it is here |
|---|---|---|
| 1 | **connect** | `boto3.client("bedrock-runtime")` — the `converse` shape |
| 2 | **instrument** | one wrap — detection is structural, not name-based |
| 3 | **govern** | a **token** cap (needs no rate) **and** a **USD** cap after registration, plus a `keyword_deny` gate |
| 4 | **record** | `cassette` — the same call replayed offline: **0 provider calls, $0** |
| 5 | **prove** | `acttrace` `verify()` over the hash chain, and a cost that came from `prices` |

**Distinctive here: an unpriced model id, and camelCase usage.**

⚠️ **Not every Bedrock id is unpriced.** The lookup strips the region prefix, the vendor
prefix and `-v1:0`, so a **current** Bedrock Claude id prices itself with no registration
(`eu.anthropic.claude-sonnet-4-6-v1:0`) while Nova / Llama / Mistral and **retired**
Claude ids do not. The same cap in the same code binds on one model and is a silent
no-op on the next.

## Run it

```bash
# Offline (fake boto3 bedrock-runtime shape) — what CI runs, no credentials:
uv run python recipes/providers/bedrock/main.py

# Against real Bedrock (records a redacted cassette):
export AWS_ACCESS_KEY_ID="…" AWS_SECRET_ACCESS_KEY="…"   # or your usual AWS credential chain
export AWS_REGION="eu-north-1"
export BEDROCK_MODEL_ID="eu.amazon.nova-2-lite-v1:0"
RECORD=1 uv run --with boto3 python recipes/providers/bedrock/main.py
```

`boto3` is not a dependency of this repo — the offline path never imports it. `--with boto3` supplies
it for the `RECORD=1` path only.

> **If you use a Bedrock API key rather than IAM keys**, boto3 reads it from
> **`AWS_BEARER_TOKEN_BEDROCK`** — *not* from `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, and it must
> be the only one set. A Bedrock API key parked in the IAM variables fails with
> `UnrecognizedClientException: The security token included in the request is invalid`, which reads
> like a permissions problem and is not one. (Measured while live-verifying this recipe.)

## Expected output

```text
gate     : BLOCKED by keyword_deny - provider saw 0 call(s), $0
provider : bedrock   (detected from the boto-shaped .converse method)
model    : eu.amazon.nova-2-lite-v1:0
usage    : 1100 in + 320 out   (mapped from usage.inputTokens / usage.outputTokens)
cost     : $None   <- no price row for this id

tokens=  budget exceeded: used 1420 tokens > cap 1000 tokens after 1 call(s); last model=eu.amazon.nova-2-lite-v1:0. on_exceed='block' refused nothing here: the pre-flight estimate fitted the cap and the call's settled usage did not, so the cumulative post-flight check raised. Reserve more output (output_reserve=/reasoning_reserve=) or add on_exceed='clamp' to cap the call server-side.
usd=     pre-flight block: projected $0.0000622200 would exceed cap $0.00001 (model=eu.amazon.nova-2-lite-v1:0)
priced   $0.0001428000   (same id, same call, now costed)
cassette replayed 1 call, 0 provider call(s), $0
verify() True - ok: 5 entries, head 6dc282adbcdf…
```

Read the three enforcement lines as a set:

- **`tokens=`** — a token cap binds with **no rate at all**, because it counts tokens the provider
  reported. This one is set below a single call's settled usage on purpose: `on_exceed="block"` is
  *pre-flight*, so a call whose estimate fits and whose real completion does not still lands over the
  cap. The exception says exactly that and names the fix. (Needs `cendor-tokenguard >= 1.6.2` — before
  that release this same breach printed `spent $0 > cap $None` and advised using `block`, which is what
  the caller had passed. Found by this recipe.)
- **`usd=`** — after `prices.register_model_price`, the projection is compared **before** the request is sent:
  the call never happens, `$0.00` is spent.
- **`priced`** — the same id and the same call, now costed. The rates are **yours to supply**
  (`input=0.06, output=0.24` USD per 1M is Nova-2-Lite-shaped); cendor never guesses a marketplace
  price.

## Honest limits

- **Python only, by design.** `instrument()` detects Bedrock by a **boto-shaped `converse()`** method.
  The official `@aws-sdk/client-bedrock-runtime` v3 has no such method — it issues everything as
  `client.send(new ConverseCommand(...))`, and `send` is shared by every AWS command, so it cannot be
  duck-typed. aws-sdk-v3 Bedrock is captured through `@cendor/sdk`'s provider (which wraps the client
  directly) or a small `.converse()` shim of your own, **not** through `instrument()`. This is the one
  documented `instrument()` detection asymmetry between the ports; the
  [parity matrix](https://cendor.ai/docs/languages) is the contract.
- **`converse_stream` is captured (Python, core ≥ 1.10) as an always-stream target.** This recipe stays
  non-streamed to keep the money story in one screen.
- **`inferenceConfig.maxTokens` is where a clamp lands.** `on_exceed="clamp"` writes the ceiling into
  that nested key rather than a flat kwarg — one more reason not to hand-roll per-provider cap logic.

## Your credentials stay yours

No key, secret, account id, region or model id of anyone's is committed here. `boto3.client(...)` uses
**your** ordinary AWS credential chain and `BEDROCK_MODEL_ID` is read from **your** environment; the
default in the file is a public marketplace id, not an account-scoped resource. CI has no secrets — a
recipe that needs credentials to go green is a bug in the recipe.

## Run it as a notebook

[`notebook.ipynb`](notebook.ipynb) tells the same story a cell at a time — each step prints its own
output, the markdown carries the *why*, and the last cell asserts what `main.py` asserts. Offline
like everything else.

```bash
uv sync --group dev
uv run --group dev jupyter lab recipes/providers/bedrock/notebook.ipynb
```

In a Codespace it is already runnable — the devcontainer installs the Jupyter extension, so just
open the file and **Run All**.

> The notebooks are **executed in CI** (`pytest --nbmake`, Python 3.11 and 3.13), so one that stops
> working turns the build red rather than quietly becoming a screenshot of code that used to run.


Libraries: `core`, `tokenguard`, `guardrails`, `cassette`, `acttrace` · Offline ✓ · [← all recipes](../../../README.md)
