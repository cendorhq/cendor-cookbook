# CLAUDE.md — cendor-cookbook

The org constitution is the workspace-root `cendorhq/CLAUDE.md` — a maintainer's local multi-repo
checkout, **not published anywhere**, so don't go looking for it. This file exists so the rules below
travel WITH the repo: a session checked out here alone must still see them. Nothing here binds a
contributor — [`CONTRIBUTING.md`](CONTRIBUTING.md) is the contract for that.

- **No `Co-Authored-By` trailer** on commits (org-wide rule).

## Versioning — the org standard (see the workspace `CLAUDE.md`)

1. **A MAJOR bump needs Raghav's explicit approval. Never autonomous.** Propose it, say what breaks,
   wait. **Minor and patch need no approval** — ship them.
   ⚠️ **Unenforced here — the rule is on you.** Org-wide there is a `check-major-bump` gate (it reads
   an in-band `Approved-Major:` line in the changeset, or an `APPROVED-MAJOR` file naming the exact
   version), but that script is **not in this repo** and no job in `.github/workflows/ci.yml` runs it.
   Nor would it have anything to guard: the cookbook publishes nothing (`[tool.uv] package = false`,
   no changesets), so its own `version` is inert. What a major bump means *here* is the dependency
   **ranges the recipes pin** — `cendor-*` in `pyproject.toml` and `@cendor/*` in the three JS
   recipes' `package.json`. Crossing one of those to a new major is the decision that needs approval.
2. **All libraries in one language share ONE major** — `@cendor/*` move together, `cendor-*` move
   together. Minors and patches stay independent per package.
3. **Majors are NOT coupled across languages.** The parity matrix is the contract, not matching
   numbers.
4. **Use minors.** A new capability is a **minor**; a fix is a **patch**. Do not drift into
   patch-patch-patch-then-a-surprise-major — the version number has to carry information.
