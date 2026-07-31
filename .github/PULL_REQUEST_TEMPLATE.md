<!-- Thanks for the PR. The full recipe standard is in CONTRIBUTING.md. -->

## What & why

<!-- Which recipe, and what pain does it prove away? Link the related issue. Explain the *why* — that
     is the part a reviewer cannot reconstruct from the diff. -->

Recipe(s): <!-- e.g. recipes/governance/pii-guardrail -->

## The one hard gate: it runs green offline

CI has **no secrets, ever**. A recipe must produce its money shot with no API key in the environment
and no network call to a model provider.

```bash
# Python — with NO key set. Add `--group <name>` if the recipe needs a framework/host SDK.
uv run python recipes/<category>/<name>/main.py
uv run pytest recipes/<category>/<name>        # only if the recipe ships a test file


# Lint (whole repo)
uv run ruff check .
uv run ruff format --check .
```

- [ ] The recipe printed its money shot **with no key set** and no provider network call
- [ ] `uv run ruff check .` and `uv run ruff format --check .` (run each bare and read the exit code — never pipe a gate into `tail`/`grep` and chain off `&&`)
- [ ] `uv run pytest recipes/<category>/<name>` is green (if it ships a test file)

## Checklist

- [ ] `README.md` follows the house shape: the **pain** (2–3 lines) → **what it shows** → the **run command** → an **expected-output** snippet containing the money shot
- [ ] The README's expected-output snippet matches what the recipe actually prints, character for character
- [ ] `main.py` is roughly 80 lines or fewer and is copy-paste runnable from the repo root
- [ ] Any framework, host, or provider SDK I added lives in **its own dependency-group** with an upper bound at the next breaking release
- [ ] **CI actually runs my recipe.** Every directory under `recipes/` must be reachable from a job in `.github/workflows/ci.yml` — a new category, or a recipe needing a new group, needs that job added or extended. Four recipes once shipped promising "runs green offline" that CI had never executed
- [ ] I did **not** rename an existing recipe folder — those names are an API the cendor.ai `/cookbook` page deep-links to
- [ ] I did not bump the `cendor-*` ranges in `pyproject.toml` across a **major** — that is a maintainer decision

## Honest claims

- [ ] No invented metrics. Every cost printed traces to `prices.estimate(...)` on stated token counts, and money is `Decimal`, never a float
- [ ] Libraries are composed only through the documented seams (`instrument()`, the `cendor.core` bus, protocols) — no `import cendor.<toolA>` from inside `cendor.<toolB>` glue
- [ ] A framework is described as *working alongside* Cendor — never an "official integration" — and nothing claims regulatory compliance (`acttrace` produces *evidence to support* a case)
- [ ] No credential, key, or `.env` in the diff — including inside a committed cassette
- [ ] Commit messages are conventional-ish with a body, and carry **no `Co-Authored-By` trailer**
