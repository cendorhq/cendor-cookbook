#!/usr/bin/env python
"""Gate - the totals stated in README prose match what is on disk.

    uv run python scripts/check_readme_counts.py

WHY, measured 2026-08-03. The README carries a *table* listing every recipe (gated by
`cendor-site/scripts/check-recipe-cards.mjs` across both trees) and, separately, *sentences
stating totals*. Nothing read the sentences, so they drifted: the parity line said "52 of the 53
recipes here" while the tree held 54 and the table listed all 54. The table was right; the prose
was two numbers stale. The TypeScript twin had the same defect, one number further behind.

A number in prose rots silently because no gate reads prose. This reads it.

Checked:
  "N of the M recipes here have a TypeScript twin"  -> M = recipe dirs, N = those with a twin
  "N recipes ship a `notebook.ipynb`"               -> recipe dirs containing a notebook

Twin resolution uses the four documented folder-name exceptions - the same list this repo's
CLAUDE.md and the site's card gate carry. A fifth undocumented divergence therefore fails here
too, which is the point: the list lives in three places and all three must agree.

HONEST LIMIT. This checks the arithmetic, not the claim. It cannot tell you the sentence is
*true* - only that its numbers match the filesystem.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
README = ROOT / "README.md"
JS_RECIPES = ROOT.parent / "cendor-cookbook-js" / "recipes"

#: The four documented folder-name divergences (this repo's CLAUDE.md; mirrored in the site gate).
ALIASES = {
    "quickstarts/core": "quickstarts/core-js",
    "sdk/governed-agent": "sdk/governed-agent-js",
    "agents/m365-custom-engine-py": "agents/m365-custom-engine-js",
    "testing/pytest-cassette": "testing/vitest-cassette",
}

PARITY_RE = re.compile(r"(\d+)\s+of\s+the\s+(\d+)\s+recipes here have a TypeScript twin")
NOTEBOOK_RE = re.compile(r"\*\*(\d+)\s+recipes ship a `notebook\.ipynb`")


def recipe_dirs(root: pathlib.Path) -> set[str]:
    return {f"{d.parent.name}/{d.name}" for d in root.glob("*/*") if d.is_dir()}


def main() -> int:
    text = README.read_text(encoding="utf-8")
    here = recipe_dirs(RECIPES)
    problems: list[str] = []
    skipped = ""

    m = PARITY_RE.search(text)
    if m is None:
        problems.append(
            "the parity sentence is gone - if it was reworded deliberately, "
            "update this gate in the same commit rather than leaving it matching nothing"
        )
    elif not JS_RECIPES.exists():
        skipped = f" (parity leg skipped - no sibling checkout at {JS_RECIPES})"
    else:
        stated_twinned, stated_total = int(m.group(1)), int(m.group(2))
        there = recipe_dirs(JS_RECIPES)
        twinned = sum(1 for r in here if ALIASES.get(r, r) in there)
        if stated_total != len(here):
            problems.append(f"README says {stated_total} recipes here; the tree has {len(here)}")
        if stated_twinned != twinned:
            problems.append(f"README says {stated_twinned} have a TypeScript twin; {twinned} do")

    m = NOTEBOOK_RE.search(text)
    if m is None:
        problems.append("the notebook-count sentence is gone - update this gate if deliberate")
    else:
        actual = sum(1 for r in here if (RECIPES / r / "notebook.ipynb").exists())
        if int(m.group(1)) != actual:
            problems.append(f"README says {m.group(1)} recipes ship a notebook; {actual} do")

    verdict = "FAIL" if problems else "PASS"
    print(
        f"check_readme_counts: {verdict} - {len(here)} recipe(s) on disk, "
        f"{len(problems)} stale count(s){skipped}"
    )
    for p in problems:
        print(f"  {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
