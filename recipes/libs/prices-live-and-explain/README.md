# prices-live-and-explain — where a rate came from, and what to do when it is old

**The pain.** Your cost dashboard says `$0.0000109500`. Where did that number come from? Which
source, as of what date, and is one of your own registrations overriding it? A USD cap enforced
against a rate nobody can source is a control you cannot defend in a review — and the two ways it
goes wrong are both silent. A **missing** rate makes the cap count `$0` and never bind. A **stale**
rate makes it bind at the wrong number, and after a price *rise* it binds **late**, so you overspend.

**What this shows.** `prices.explain(model)` answers the whole question for one id, and it never
raises — an unpriced model is an answer, not an error. Then the three things that follow from it:
persistence is explicit (there is no hidden cache), `refresh()` is never-raise until you ask for the
loud version, and an old table announces itself once per process.

| call | what it is for |
|---|---|
| `prices.explain(model)` | resolved key, `how`, the rates, the **row's** source + that source's own as-of date, whether a registration is in effect, honest caveats |
| `prices.refresh()` | pull a newer table. No args = the **cendor-prices feed**; `source=`/`region=` for a specific catalog; `required=True` to raise instead of returning `False` |
| `prices.save(path)` / `load(path)` | the only persistence there is. `refresh()` is in-memory, per process, and writes nothing |
| `StalePriceTableWarning` | tokenguard, once per process, when a USD budget prices a call from a table older than 45 days |

Closes `prices.explain`, `prices.save`/`load`, `refresh(required=)` and `StalePriceTableWarning`.

## Run it

No key, no network — the bundled snapshot carries per-row provenance, because it is **generated**
from the feed rather than typed by hand.

```bash
uv run python recipes/libs/prices-live-and-explain/main.py

# also fetch the real feed, and show a gateway's resale caveat:
LIVE=1 uv run python recipes/libs/prices-live-and-explain/main.py
```

## Expected output

```text
--- explain(): where did this rate come from? --------------------
  table      : bundled (bundled), 849 rows, _updated=2026-08-02, age=0d
  exact      : gpt-4o: cached=0.00000125 input=0.0000025 output=0.00001 — exact, from azure as of 2026-07-01
               how='exact' registered=False row_source='azure'
  normalized : eu.anthropic.claude-sonnet-4-6-v1:0 (via claude-sonnet-4-6): cache_write=0.00000375 cached=3E-7 input=0.000003 output=0.000015 — normalized, from modelsdev as of 2026-03-13
               how='normalized' registered=False row_source='modelsdev'
  unpriced   : prod-chat-eastus: no price in the bundled table — cost will be None
               how='unpriced' registered=False row_source=None
               note: estimate() raises UnknownModelError and tokenguard records $0 — register a rate with prices.register_model_price(...) or prices.register_deployment(...)

--- a registration outranks every table --------------------------
  register   : register_deployment('prod-chat-eastus', like='gpt-4o') -> input=0.0000025 output=0.00001
  deployment : prod-chat-eastus: cached=0.00000125 input=0.0000025 output=0.00001 — registered, from bundled as of 2026-08-02
               how='registered' registered=True row_source=None
               note: a register()/register_model_price()/register_deployment() call overrides every table for this id, including after a refresh()

--- save() / load(): explicit, never implicit ---------------------
  saved      : prices.json (850 rows, _schema='prices/1', keeps _provenance=True)
  loaded     : True -> source()='loaded' source_name()='bundled' _updated=2026-08-02
  after load : gpt-4o: cached=0.00000125 input=0.0000025 output=0.00001 — exact, from azure as of 2026-07-01
               how='exact' registered=False row_source='azure'
               the registration was re-applied too: explain('prod-chat-eastus').registered = True

--- refresh(): silent by default, loud on request -----------------
  default    : refresh(url=<unreachable>) -> False  (table untouched: 850 rows still loaded)
  required   : refresh(url=<unreachable>, required=True) -> raises PriceRefreshError

--- a stale table binds the cap late ------------------------------
  table      : _updated=2026-01-01 age=213d is_stale(45)=True
  two calls  : 1 StalePriceTableWarning for 2 priced calls (once per process, not per call — a hot loop must not become a log flood)
  silence it : tokenguard.configure(on_stale_prices='ignore'), or move the threshold with stale_prices_after_days=

--- undatable is not the same as fresh ----------------------------
  table      : _updated=None age_days()=None is_stale(45)=False
  undated    : gpt-4o: cached=0.00000125 input=0.0000025 output=0.00001 — exact, from azure as of 2026-07-01
               how='exact' registered=False row_source='azure'
               note: this source publishes no as-of date, so staleness cannot be measured (is_stale() reports False, which means unknown, not fresh)

--- the live feed (skipped — set LIVE=1) -----------------
  offline    : every section above ran on the bundled snapshot, which is GENERATED
               from that same feed — which is why row_source/row_asof exist here
```

> The two `age=` figures are **computed from today's date**, so they move: the bundled snapshot's
> age grows by one per day, and `213d` is however long it has been since the deliberately-aged
> `2026-01-01`. Everything else in that transcript is fixed by the snapshot. The rest of the recipe
> asserts rather than prints — `how`, `registered`, the refresh return values and the
> **one** warning are all checked at the bottom of `main.py`.

## Where a rate comes from, in order

The precedence contract, exactly as the code behaves. Nothing in it guesses.

| # | Source | Beats |
|---|---|---|
| 1 | a provider- or gateway-**reported** real cost (`metadata["cost_reported"]`) | everything |
| 2 | **your** `register` / `register_model_price` / `register_deployment` | every table, and it survives every `refresh()` |
| 3 | a refreshed table — in memory, this process only | the snapshot |
| 4 | the bundled snapshot | nothing |
| 5 | `None` + a warn-once | — |

Row 5 is the design decision worth stating: **an honest gap beats a confident wrong number.** A
model with no rate reports `None`, not an estimate, not `$0.00` — and `explain()` says so in a note
rather than making you infer it from a missing key.

## The four things this recipe exists to teach

1. **`row_source` is per row, not per table.** The feed reconciles several catalogs, so one table
   can carry `gpt-4o` from Microsoft's own meters (`azure`, as of 2026-07-01) and
   `claude-sonnet-4-6` from `modelsdev` (2026-03-13) at the same time. `row_asof` is **that
   source's** as-of date, never the day you fetched it — a fetch date would make a six-month-old
   rate look like today's.

2. **There is no implicit cache, and that is deliberate.** `refresh()` writes nothing to disk, so a
   serverless worker starts at the bundled snapshot every time. A library quietly writing price
   files is a side effect, and a hidden cache is exactly how prices go *invisibly* stale. The escape
   hatch is a path you choose:

   ```python
   prices.refresh()
   prices.save(".cache/cendor-prices.json")      # in your deploy step

   # ... a later process:
   if not prices.load(".cache/cendor-prices.json"):
       prices.refresh()                           # nothing saved yet, or unreadable
   ```

   Provenance rides along, so `explain()` and `age_days()` after a `load()` still describe where the
   rates **came from**. `source()` then reports `"loaded"` — the transport, not the provenance.

3. **`refresh()` is contractually never-raise.** It returns `False` and leaves the last-good table
   active, because a CDN blip must not take an application down at import. When that trade is the
   wrong one — a billing job, a cost gate in CI — `required=True` raises `PriceRefreshError`
   instead. Both are shown above against a dead local socket, so the negative control runs offline.

4. **Undatable is not fresh.** `litellm`, `openrouter` and `vercel` publish no as-of date, so
   `is_stale()` returns `False` for them — and `False` there means **unknown**. Inventing an age
   would be the exact dishonesty the provenance design exists to avoid, so `explain()` puts it in a
   note instead. ⚠️ Do not write `if not prices.is_stale(): ...` and read it as "the rates are
   current"; check `age_days() is not None` first.

## The live sources

Every built-in source is an unauthenticated HTTPS GET of a **static** JSON resource — never a
running service, never a key. Cendor operates nothing here, so there is no Cendor outage that can
break your cost estimation.

| `source=` | What it is | Dated? |
|---|---|---|
| *(none — the default)* | the **cendor-prices feed**: the rest, reconciled, with per-row provenance | yes |
| `azure` | **Microsoft's own** Retail Prices catalog, Foundry Models meters (`region=`, default `eastus2`) | yes |
| `aws` | **Amazon's own** Bedrock public price files (`region=`, default `us-east-1`) | yes |
| `modelsdev` | models.dev — MIT, the widest keyless catalog | yes, per row |
| `litellm` | LiteLLM — MIT, broad coverage | no |
| `openrouter` · `vercel` | gateway catalogs | no — ⚠️ **resale** prices |

⚠️ **A gateway's number is not the lab's number.** `openrouter` and `vercel` publish what *they*
charge you to resell a model, which may differ from the model lab's own rate. `explain()` says so in
a note (visible on the `LIVE=1` path above) rather than leaving it in the docs where a cost report
can quietly disagree with an invoice.

OpenAI and Anthropic publish **no pricing API** — their model-list endpoints carry ids only. That is
why the two clouds and the MIT aggregators are the sources, and why the feed exists at all.

## Honest limits

- **These are list prices.** Enterprise agreements, committed-use discounts and private offers are
  not in any public catalog. Register your own numbers (`register_model_price`) — row 2 of the
  precedence table exists for exactly this, and it survives every refresh.
- **`azure` meter names are prose**, so the id mapping is imperfect by design. It maps 104 models in
  one region, which is most of what a Foundry tenant serves, not all of it.
- **A `model-router` deployment is not priceable at all.** The router bills at the *serving* model's
  rates while the call reports the router's own id, so no single registration is ever correct.
- **`explain()` describes the table, not your invoice.** It tells you which rate cendor used and
  where it came from. Reconciling that against a bill is still your job.

Related: [`providers/azure-foundry`](../../providers/azure-foundry/) prices a deployment name end to
end, and [`providers/bedrock`](../../providers/bedrock/) does the same for a Bedrock marketplace id
with `refresh(source="aws")`.

Libraries: `core` `tokenguard` · Offline ✓ · Live switch: LIVE=1 · [← all recipes](../../../README.md)
