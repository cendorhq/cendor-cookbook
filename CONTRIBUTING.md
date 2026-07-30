# Contributing a recipe

Thanks for adding to the Cendor Cookbook. Every recipe here earns its place by proving
something real — and by **running green offline, with no API key**. That last rule is the bar
every PR must clear.

## The one hard rule: it runs offline

CI has **no secrets, ever**. A recipe must produce its money shot with:

- **no API key** in the environment, and
- **no network call** to any model provider.

We get there the way the library's own test suite does: drive `instrument()` with a **fake
provider-shaped client** (a plain `types.SimpleNamespace` exposing the same
`chat.completions.create` / `responses.create` / `messages.create` / `chat(...)` shape the real
SDK has). The fake returns a canned `usage`/response; `cendor` normalizes and prices it exactly
as it would a real call. No SDK, no key, no daemon.

If your recipe demonstrates a real provider or a local model, add a **`RECORD=1` path**: the same
code, gated behind an env check, that a maintainer runs once with a real key so `cassette` records
the exchange (secrets redacted on write). The committed cassette then lets CI replay it offline.
Ship the recipe **unrecorded** — the fake-client path is what keeps CI green until a cassette lands.

## The recipe standard

| Piece | Rule |
|---|---|
| `README.md` | the **pain** (2–3 lines, in a developer's words) → **what the recipe shows** → the **run command** → an **expected-output** snippet that includes the money shot |
| `main.py` | **~80 lines is the target, not a gate** — copy-paste runnable as `uv run python recipes/<category>/<name>/main.py`. Some recipes are legitimately longer (the agent-host and app recipes are hundreds of lines, because the *host* is the point); the real rule is that a reader can follow it top to bottom in one sitting. If you are over ~80 lines, make sure every extra line is teaching something. |
| Offline | green with **no key and no network** — fake provider-shaped client (default) or a committed cassette fixture |
| Honest claims | **no invented numbers.** Any cost printed comes from `prices.estimate(...)` on stated token counts. Frameworks "work alongside" Cendor — never "official integration" |
| No tool→tool imports | recipes compose libraries only through the documented seams (`instrument()`, the `cendor.core` bus, protocols) — never `import cendor.<toolA>` *from inside* `cendor.<toolB>` glue |

## Recipe template

```
recipes/<category>/<name>/
├── README.md      # pain → shows → run → expected output (money shot)
└── main.py        # ~80 lines target (not a gate), offline, uv run python .../main.py
```

`README.md` skeleton:

```markdown
# <name>

**The pain.** 2–3 lines in a developer's own words.

**What this shows.** One or two sentences: which Cendor libraries, composed how.

## Run it

```bash
uv run python recipes/<category>/<name>/main.py
```

## Expected output

```text
<the money shot — the exact line(s) the recipe prints>
```

Libraries: `core`, `<tool>` · Offline ✓
```

`main.py` skeleton (fake-client offline pattern):

```python
from types import SimpleNamespace
from cendor.core import instrument, bus

def fake_openai(prompt_tokens=1000, completion_tokens=500):
    class Completions:
        def create(self, **kw):
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
            )
    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))

def main() -> None:
    client = instrument(fake_openai())
    bus.subscribe(lambda call: print(call.provider, call.model, call.usage, call.cost))
    client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

if __name__ == "__main__":
    main()
```

## Before you open the PR

- [ ] `uv run python recipes/<category>/<name>/main.py` prints the money shot **with no key set**.
- [ ] If it's a test-style recipe, `uv run pytest recipes/<category>/<name>` is green.
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass.
- [ ] The README's expected-output snippet matches what the recipe actually prints.
- [ ] Any framework SDK you added lives in its own `frameworks-<name>` dependency-group with an
      upper bound at the next breaking release.
- [ ] No invented metrics; every cost traces to `prices.estimate(...)`.

## Conduct and security

Be respectful and constructive — see the [Code of Conduct](CODE_OF_CONDUCT.md).

Found a security problem in a recipe — an unsafe pattern people would copy, a credential that leaked
into a fixture, a cassette that isn't safe to load? **Don't open a public issue.** See
[SECURITY.md](SECURITY.md) for the private reporting channel and what belongs here versus in
[`cendor-libs`](https://github.com/cendorhq/cendor-libs).

## Site contract

Folder names under `recipes/` are an API — the cendor.ai `/cookbook` page deep-links to them.
**Don't rename an existing recipe folder** without updating the site.

---
Licensed under Apache-2.0. By contributing you agree your contribution is licensed under the
same terms. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
