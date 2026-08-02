"""prices-live-and-explain — where a rate came from, and what to do when it is old.

Every USD number cendor prints starts as a per-token rate looked up in a price table. Which table,
from which source, as of which date, and does one of YOUR registrations override it? Until you can
answer that, a cost figure is a number with no provenance — and a USD cap enforced against a rate
nobody can source is a control you cannot defend in a review.

  prices.explain(model)   the whole answer for one id: resolved key, how it resolved, the rates,
                          which SOURCE that specific row came from, that source's own as-of date,
                          whether a registration of yours is in effect, and honest caveats.
                          Never raises: an unpriced model is an answer, not an error.
  prices.refresh()        pull a newer table. Never-raise by default (a CDN blip must not take your
                          app down at import); `required=True` when silence is the wrong trade.
  prices.save() / load()  the ONLY persistence. refresh() is in-memory, per process, and writes no
                          hidden cache — because a hidden cache is exactly how prices go invisibly
                          stale. You choose the path; provenance rides along.
  StalePriceTableWarning  tokenguard says so, once per process, when a USD budget estimates from a
                          table older than 45 days.

Offline: everything below runs on the BUNDLED snapshot, which carries per-row provenance because it
is generated from the cendor-prices feed rather than typed by hand. No key, no network.

  uv run python recipes/libs/prices-live-and-explain/main.py

  LIVE=1 uv run python recipes/libs/prices-live-and-explain/main.py   # also fetch the real feed
"""

import json
import os
import tempfile
import warnings
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from cendor import tokenguard
from cendor.core import instrument, prices
from cendor.tokenguard import StalePriceTableWarning

MODEL = "gpt-4o"
#: A Bedrock wire id. Nothing registers it; the table answers through NORMALIZATION.
WIRE_ID = "eu.anthropic.claude-sonnet-4-6-v1:0"
#: A Microsoft Foundry deployment name. Arbitrary by construction, so no table on earth has it.
DEPLOYMENT = "prod-chat-eastus"

#: tokenguard's default staleness threshold is 45 days; this table is deliberately older.
STALE_UPDATED = "2026-01-01"


def fake_client():
    """An OpenAI-shaped client. `instrument()` identifies a client by shape, not by name."""

    class Completions:
        def create(self, **kw):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=1200, completion_tokens=300),
                model=kw.get("model", MODEL),
            )

    return instrument(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def show(label: str, model: str) -> None:
    e = prices.explain(model)
    print(f"  {label:11}: {e.summary()}")
    print(f"  {'':11}  how={e.how!r} registered={e.registered} row_source={e.row_source!r}")
    for note in e.notes:
        print(f"  {'':11}  note: {note}")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cendor-prices-"))
    good = tmp / "prices.json"

    # ── 1. explain(): the same question, three different answers ──────────────────────────────────
    #
    # `how` is the part to read. "exact" = the id IS a table key. "normalized" = a wire-level id was
    # reduced to its base, which is why a Bedrock ARN-shaped id prices at all. "unpriced" = no rate
    # exists — and that is an ANSWER, not an exception, because the honest output of a missing price
    # is None plus a warn-once, never a guess.
    print("--- explain(): where did this rate come from? --------------------")
    print(
        f"  table      : {prices.source_name()} ({prices.source()}), {len(prices.models())} rows,"
        f" _updated={prices.snapshot_date()}, age={prices.age_days()}d"
    )
    show("exact", MODEL)
    show("normalized", WIRE_ID)
    show("unpriced", DEPLOYMENT)

    # ── 2. the precedence contract ────────────────────────────────────────────────────────────────
    #
    # A registration outranks EVERY table and survives every refresh()/load(). That is the answer to
    # "the live price is wrong for me" — negotiated rates, a private deployment, a fine-tune — and
    # it has always been shipped. `register_deployment` is the form that needs no rate card: you
    # name the model your deployment serves, which you already know.
    print("\n--- a registration outranks every table --------------------------")
    rates = prices.register_deployment(DEPLOYMENT, like=MODEL)
    print(
        f"  register   : register_deployment({DEPLOYMENT!r}, like={MODEL!r})"
        f" -> input={rates['input']} output={rates['output']}"
    )
    show("deployment", DEPLOYMENT)

    # ── 3. save() / load(): the only persistence, and it is yours ─────────────────────────────────
    #
    # refresh() is in-memory ONLY, per process — a serverless worker starts at the bundled snapshot
    # every time. There is deliberately no implicit cache. save()/load() is the explicit escape
    # hatch, and provenance rides along: after a load(), explain() still describes where the rates
    # CAME FROM, not where they were read from.
    print("\n--- save() / load(): explicit, never implicit ---------------------")
    prices.save(str(good))
    written = json.loads(good.read_text(encoding="utf-8"))
    print(
        f"  saved      : {good.name} ({len(written['models'])} rows, "
        f"_schema={written['_schema']!r}, keeps _provenance={'_provenance' in written})"
    )
    loaded = prices.load(str(good))
    print(
        f"  loaded     : {loaded} -> source()={prices.source()!r} "
        f"source_name()={prices.source_name()!r} _updated={prices.snapshot_date()}"
    )
    show("after load", MODEL)
    print(
        f"  {'':11}  the registration was re-applied too: "
        f"explain({DEPLOYMENT!r}).registered = {prices.explain(DEPLOYMENT).registered}"
    )

    # ── 4. refresh() is never-raise — until you ask for the loud one ──────────────────────────────
    #
    # Both calls below go nowhere: 127.0.0.1:9 is the discard port, so this is a local socket that
    # fails, not a network fetch. The DEFAULT keeps the last-good table and returns False, because a
    # CDN blip must never take an application down at import. In a billing job or a CI cost gate
    # that trade is wrong, and `required=True` raises instead.
    print("\n--- refresh(): silent by default, loud on request -----------------")
    dead = "http://127.0.0.1:9/nope.json"
    quiet = prices.refresh(url=dead, timeout=1.0)
    print(
        f"  default    : refresh(url=<unreachable>) -> {quiet}  "
        f"(table untouched: {len(prices.models())} rows still loaded)"
    )
    try:
        prices.refresh(url=dead, timeout=1.0, required=True)
        raised = "nothing"
    except Exception as exc:  # noqa: BLE001 — the point is which type reaches you
        raised = type(exc).__name__
    print(f"  required   : refresh(url=<unreachable>, required=True) -> raises {raised}")

    # ── 5. an OLD table is a wrong cap, in a direction that depends on the price move ─────────────
    #
    # After a price CUT a stale table over-estimates and the cap binds early (conservative). After a
    # price RISE it under-estimates and the cap binds LATE — you overspend. tokenguard warns once
    # per process when a USD budget prices a call from a table older than 45 days.
    print("\n--- a stale table binds the cap late ------------------------------")
    stale_file = tmp / "stale.json"
    aged = json.loads(good.read_text(encoding="utf-8"))
    aged["_updated"] = STALE_UPDATED
    stale_file.write_text(json.dumps(aged, indent=1), encoding="utf-8")
    prices.load(str(stale_file))
    print(
        f"  table      : _updated={prices.snapshot_date()} age={prices.age_days()}d "
        f"is_stale(45)={prices.is_stale(45)}"
    )

    client = fake_client()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with tokenguard.budget(usd=Decimal("5.00"), on_exceed="block"):
            client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "a"}])
            client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "b"}])
        # Catch it by TYPE, not by message text: it is an exported class precisely so you can
        # `simplefilter("error", StalePriceTableWarning)` and make a stale table fail a build.
        stale_warnings = [w for w in caught if issubclass(w.category, StalePriceTableWarning)]
    print(
        f"  two calls  : {len(stale_warnings)} StalePriceTableWarning for 2 priced calls "
        f"(once per process, not per call — a hot loop must not become a log flood)"
    )
    print(
        "  silence it : tokenguard.configure(on_stale_prices='ignore'), or move the threshold "
        "with stale_prices_after_days="
    )

    # ── 6. undatable is not fresh ─────────────────────────────────────────────────────────────────
    #
    # litellm, openrouter and vercel publish no as-of date. is_stale() reports False for those, and
    # False there means UNKNOWN, not fresh. Inventing an age would be the exact dishonesty the whole
    # provenance design exists to avoid — so explain() says so in a note instead.
    print("\n--- undatable is not the same as fresh ----------------------------")
    undated = tmp / "undated.json"
    aged.pop("_updated", None)
    undated.write_text(json.dumps(aged, indent=1), encoding="utf-8")
    prices.load(str(undated))
    print(
        f"  table      : _updated={prices.snapshot_date()} age_days()={prices.age_days()} "
        f"is_stale(45)={prices.is_stale(45)}"
    )
    show("undated", MODEL)

    # ── 7. LIVE=1 — the real feed, and a gateway's resale rate ────────────────────────────────────
    #
    # A bare refresh() fetches the cendor-prices feed: a static, keyless JSON file on GitHub's CDN,
    # reconciled daily from Microsoft's and Amazon's own catalogs plus the MIT aggregators, with
    # per-row provenance. Cendor operates no service here, so there is no Cendor outage that can
    # break your cost estimation.
    live = os.getenv("LIVE") == "1"
    print(f"\n--- the live feed ({'LIVE=1' if live else 'skipped — set LIVE=1'}) -----------------")
    if live:
        ok = prices.refresh()
        print(
            f"  feed       : refresh() -> {ok}, {len(prices.models())} rows, "
            f"_updated={prices.snapshot_date()}, source={prices.source_name()!r}"
        )
        show("gpt-4o", MODEL)
        # A gateway sells you someone else's model at its own price. explain() surfaces that rather
        # than burying it in the docs, because a resale rate silently substituted for a lab's rate
        # is a cost report that is wrong and confident.
        if prices.refresh(source="openrouter"):
            print(f"  resale     : refresh(source='openrouter') -> {len(prices.models())} rows")
            show("gpt-4o", MODEL)
    else:
        print("  offline    : every section above ran on the bundled snapshot, which is GENERATED")
        print("               from that same feed — which is why row_source/row_asof exist here")

    # ── assertions: the recipe is its own test ────────────────────────────────────────────────────
    prices.load(str(good))
    assert prices.explain(MODEL).how == "exact", "a table key should resolve exactly"
    assert prices.explain(WIRE_ID).how == "normalized", "a wire id should reduce to its base"
    assert prices.explain(DEPLOYMENT).registered, "a registration must survive save()/load()"
    assert prices.explain("no-such-model-ever").how == "unpriced", "explain() must never raise"
    assert quiet is False, "an unreachable refresh() must return False, not raise"
    assert raised == "PriceRefreshError", "required=True must raise PriceRefreshError"
    assert len(stale_warnings) == 1, "StalePriceTableWarning is once per process, not per call"


if __name__ == "__main__":
    main()
