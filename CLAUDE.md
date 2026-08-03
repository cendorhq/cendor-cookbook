# CLAUDE.md — cendor-cookbook

The org constitution is the workspace-root `cendorhq/CLAUDE.md` — a maintainer's local multi-repo
checkout, **not published anywhere**, so don't go looking for it. This file exists so the rules below
travel WITH the repo: a session checked out here alone must still see them. Nothing here binds a
contributor — [`CONTRIBUTING.md`](CONTRIBUTING.md) is the contract for that.

- **No `Co-Authored-By` trailer** on commits (org-wide rule).

## What this repo is, and why it is separate

The **Python half** of the Cendor Cookbook. Its TypeScript half is
[`cendorhq/cendor-cookbook-js`](https://github.com/cendorhq/cendor-cookbook-js); the two are twins,
not forks — a recipe folder name means the same thing in both trees.

The split is deliberate (2026-07-31). A single repo carrying a root `pyproject.toml` *and* scattered
`package.json` files gives a devcontainer no unambiguous toolchain to provision (GitHub Codespaces
picks one and the other language degrades), and it couples two dependency graphs that have no
business constraining each other. One repo per toolchain keeps both simple.

**Recipe folder names are an API.** cendor.ai `/cookbook` deep-links to them and the MCP docs server
indexes them. Never rename one — not even when moving a recipe between the two cookbooks.

### The four folder names that differ from their TypeScript twin

A new recipe uses the **bare** name in both trees. These four are the complete list of exceptions;
do not add a fifth without a reason as specific as these, and do not "fix" any of them:

| here | TypeScript twin | why |
|---|---|---|
| `quickstarts/core` | `quickstarts/core-js` | historical, from before the cookbooks were split |
| `sdk/governed-agent` | `sdk/governed-agent-js` | historical |
| `agents/m365-custom-engine-py` | `agents/m365-custom-engine-js` | historical |
| `testing/pytest-cassette` | `testing/vitest-cassette` | **deliberate** — the twin genuinely *is* a different test runner, and a TS folder called `pytest-cassette` would be wrong on its face |

The first three are frozen because renaming them would break a cendor.ai deep link and the MCP index
— not because they are good names. Every recipe added since uses the bare name.

**One recipe here has no twin, on purpose:** `apps/chat-playground` is a Gradio app, and Gradio is
Python-only. A TypeScript port would be a different application wearing a twin's folder name. It is
documented in [`README.md`](README.md); do not "close the gap".

## Cardinal rules

0. **`uv.lock` is NOT committed, and that is the point.** CI always re-resolves the current shipped
   packages, which is what makes this repo a black-box consumer rather than a museum. The cost is
   that a **local** checkout keeps whatever it resolved last time, so a local run can be green about
   a shelf nobody ships. `uv run python scripts/check_shelf.py` compares the installed cendor
   packages against PyPI and exits 1 on any mismatch — it needs network, so it is a **pre-flight for
   a live sweep or a release, not a CI gate**. Run it before you believe a measurement.

1. **Every recipe runs offline, with no API key.** CI has no secrets and never will. A recipe that
   needs a key to go green is a bug in the recipe. Offline is achieved with a fake provider-shaped
   client (`instrument()` identifies a client by its *shape*, not its class name) or a committed
   cassette fixture. A documented **live switch** (`RECORD=1`, `LIVE=1`, `OLLAMA_LIVE=1`,
   `USE_FOUNDRY_SDK=1`) may reach a real provider with YOUR key — never in CI.
   ⚠️ **Unlike the TypeScript twin, there is no `check-live-switches` gate here.** Over there a
   README footer promising a switch is asserted against the code that must read it; here that
   promise is on you. A README is not executable, and one that names a switch the code never reads
   fails nothing.

2. **Python 3.11 AND 3.13 are in the CI matrix, always.** 3.11 is the project's `requires-python`
   floor; 3.13 is the other end. A recipe green on only one proves nothing about the other.

3. **One `uv` project; framework and provider SDKs live in per-category `[dependency-groups]`, each
   with an upper bound.** The reason is in `pyproject.toml` itself: so CI can install (and break)
   them in isolation, and one framework's major/minor bump turns **only its own matrix cell** red
   instead of the whole repo's CI. `[tool.uv] package = false` — this project is never built or
   published.

4. **Money is `Decimal`, never a float.** `call.cost.amount` is a `Decimal`; keep it one. Format at
   the edge, compare as `Decimal`, round-trip through storage as a **string**.

5. **Recipes compose the libraries only through the documented seams** — `instrument()`, the
   `cendor.core` bus, the protocols. The libraries never import each other, and a recipe that
   reaches around that is teaching a shape the stack does not have.

6. **Honest claims.** Any cost printed comes from `prices.estimate(...)` on stated token counts. A
   framework *works alongside* Cendor; it is never an "official integration". `acttrace` produces
   **evidence to support** a compliance case — never a compliance guarantee.
   ⚠️ **A number in a README is only true on the shelf it was measured against.** Measured
   2026-08-02: `cendor-core` 1.20.0 made a mapped `refresh(source=…)` drop rows it cannot price, and
   `providers/bedrock`'s live aws count moved 76 → 71 the same day it was written down. Re-run any
   recipe whose README quotes a live figure after **any** core release, not only one you think is
   related.

7. **The 20 notebooks are EXECUTED in CI, not linted.** `pytest --nbmake` starts a kernel and runs
   every cell top to bottom, failing on the first exception. A notebook that is only ever read rots
   into a screenshot of code that used to work.

8. **A TypeScript-only capability gets a documented omission, never a fake Python sample** — and the
   reverse, which is the case that actually occurs here: `apps/chat-playground` is Gradio and has no
   twin, and `libs/cassette-semantic-drift` uses `local_embedding_scorer` (model2vec), which has no
   JS port. Say so; do not fake the other side. The parity matrix
   (`cendor-libs/docs/languages.md`) is the contract.

### CI shape, and the two holes in it

One job per recipe category — but **they are not all the same shape, and the difference decides
whether a new recipe is covered at all.** Measured 2026-08-02:

| Category job | Shape | A new recipe in it is… |
|---|---|---|
| `quickstarts` `providers` `governance` `sdk` `combos` `libs` | loops over `recipes/<cat>/*/main.py` | **covered the moment it lands** |
| `frameworks` `bridges` `observability` | a matrix **naming each recipe** (4 / 4 / 2), because each installs only its own dependency-group | **NOT covered — you must add a matrix entry** |
| `agents` `testing` `apps` | run their single recipe directly | not covered — add it explicitly |

Every recipe on disk *is* currently covered. The point is that in seven of the ten categories that is
true by enumeration, so it stops being true the moment somebody adds a recipe and does not notice.

The second hole is a new **category**: `recipes/<new>/…` would simply never be visited, and the
README's "every recipe runs green offline" would quietly stop being backed by anything. This repo
shipped exactly that once — four `bridges/` recipes CI had never executed.

⚠️ **Neither hole has a gate here.** The TypeScript twin has `check-recipe-coverage`, which fails
when a category is missing from its CI matrix; there is no Python equivalent. Adding a recipe to an
enumerated category, or adding a category at all, means editing `ci.yml` by hand — and nothing will
remind you.

**Two gates the `lint` job runs besides ruff (both added 2026-08-03, both with a proven negative control):**

- `scripts/check_print_encoding.py` — **no recipe PRINTS a character cp1252 cannot encode.** A
  `⚠️` inside a `print()` raises `UnicodeEncodeError` on a Windows console; the process dies. Every
  job in `ci.yml` is `ubuntu-latest`, so the matrix **structurally cannot see this class**, which is
  why a static check earns its place. It found a live offender the day it was written
  (`agents/m365-custom-engine-py` printed one in its vacuous-replay branch — the worst moment to
  crash, since that branch fires only when something already needs explaining). It walks the **AST**,
  not lines: a docstring explaining this hazard contains both `print(` and the glyph, and a
  line-based scan flags it. ⚠️ It does **not** claim the recipes run on Windows — printed string
  literals only. Typographic characters cp1252 covers (em dash, `…`, `·`) are deliberately fine.
- `scripts/check_readme_counts.py` — **the totals stated in README prose match the disk.** The
  recipe *table* is gated (by the site's card check, across both trees); the *sentences* were not,
  and had drifted two numbers behind — *"52 of the 53 recipes here"* against 54 on disk, with the
  table complete and correct. A number in prose rots silently because no gate reads prose.

`ruff` is the lint + format gate (line length 100). ⚠️ `*.md` is excluded **deliberately**, not to
dodge a failure: ruff 0.16 began reformatting the Python blocks inside every recipe README, and three
of the four rewrites it wanted made the teaching worse.

## Versioning — the org standard (see the workspace `CLAUDE.md`)

1. **A MAJOR bump needs Raghav's explicit approval. Never autonomous.** Propose it, say what breaks,
   wait. **Minor and patch need no approval** — ship them.
   ⚠️ **Unenforced here — the rule is on you.** Org-wide there is a `check-major-bump` gate (it reads
   an in-band `Approved-Major:` line in the changeset, or an `APPROVED-MAJOR` file naming the exact
   version), but that script is **not in this repo** and no job in `.github/workflows/ci.yml` runs
   it. Nor would it have anything to guard: the cookbook publishes nothing, so its own `version` is
   inert. What a major bump means *here* is the dependency **ranges the recipes pin** — the
   `cendor-*` ranges in `pyproject.toml`. Crossing one of those to a new major is the decision that
   needs approval.
2. **All libraries in one language share ONE major** — `cendor-*` move together. Minors and patches
   stay independent per package.
3. **Majors are NOT coupled across languages.** The parity matrix is the contract, not matching
   numbers.
4. **Use minors.** A new capability is a **minor**; a fix is a **patch**.

## The pin ritual

Python pins are **floors** (`>=x.y.z,<2.0`), not carets, and `uv.lock` is gitignored — so CI resolves
the newest release inside the floor every run. That makes a floor the only thing standing between a
recipe and an artifact that cannot do what its README says.

⚠️ **A floor that is too LOW is the failure mode, and it is completely silent.** Measured 2026-08-02:
the `cendor-tokenguard` floor sat at `>=1.6.3` right through the live-pricing release, so `uv.lock`
legally resolved **1.7.0** while **1.8.0** was published — and `StalePriceTableWarning`, which the
docs said had shipped, was **not importable**. Nothing failed. The same day, `cendor-core` sat a
patch behind at 1.19.1 while 1.19.2 was the release that stopped a missing output rate pricing a chat
model as free, so a recipe printing a `claude-3-haiku` cost was printing a wrong number.

So, after any `cendor-*` release that a recipe depends on:

1. **Raise the floor to the version that carries the capability**, and say in a comment *why* that
   version and not an earlier one. A floor with no reason attached gets lowered by the next person.
2. `uv lock --upgrade-package <pkg>` then `uv sync`, and **read the resolved version back**.
3. `uv run python scripts/check_shelf.py` — it compares installed against PyPI and is the only thing
   that catches "green about a shelf nobody ships".
4. Re-run every recipe whose README quotes a number that release could move (rule 7).

⚠️ **A local `uv sync` is not a shelf refresh on its own.** It honours the existing `uv.lock`;
`--upgrade-package` (or deleting the lock) is what re-resolves. CI has no lockfile at all, so a local
gate can be green against a shelf CI will never see — the mirror image of the TypeScript twin's
`package-lock.json` hazard, and the reason `check_shelf.py` exists.
