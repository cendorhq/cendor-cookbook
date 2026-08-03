#!/usr/bin/env python
"""Gate - no recipe PRINTS a character a Windows console cannot encode.

    uv run python scripts/check_print_encoding.py           # fail on any offender
    uv run python scripts/check_print_encoding.py --list    # show every non-ASCII printed char

WHY, measured 2026-08-03. A warning glyph inside a `print()` raises `UnicodeEncodeError` on a
Windows console, whose default encoding is cp1252. It is not a warning and not mojibake - the
process dies. `recipes/frameworks/azure-foundry-otel-export/main.py` did exactly that while it
was being written: every assertion in it passed, and it crashed on the very last line.

And CI structurally cannot see it. `.github/workflows/ci.yml` runs 14 jobs, every one of them
`ubuntu-latest`, zero on Windows. So a recipe that dies on the first line a Windows reader runs
stays green here forever. That asymmetry - a whole class of failure the matrix cannot reach - is
why a cheap static check earns its place. It found a live offender the day it was written
(`agents/m365-custom-engine-py`, in its vacuous-replay branch).

WHAT IT DOES NOT CLAIM. This is not a "recipes work on Windows" gate and must never be described
as one. It checks string *literals* that reach `print(...)`. It says nothing about path handling,
subprocess quoting, line endings, or a glyph arriving through a variable. Proving a recipe runs on
Windows needs a Windows job in the matrix: a bigger change and a different claim.

WHY THE AST, NOT A REGEX. A line scan has a false positive that bites at once: a docstring
explaining this hazard contains both `print(` and the glyph on one line. Measured while writing
this gate. The AST asks the precise question - is this literal an argument to a `print` call.

THE ALLOWED SET. cp1252 is a Latin-1 superset, so the typography the recipes use is fine and is
NOT flagged: em/en dash, curly quotes, ellipsis, bullet, non-breaking space. Flagged is everything
outside it: emoji, box drawing, arrows, check marks, the warning sign. If you want one in output,
spell the intent (`OK` / `->` / `WARNING`) or move the note to the README, which is only read.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"


def _is_print(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
    )


def _printed_literals(tree: ast.AST) -> list[tuple[int, str]]:
    """Every string literal that is (transitively) an argument to a ``print(...)`` call.

    Covers f-string fragments, implicit concatenation and a literal inside a ``.join(...)``,
    because all of them reach the console.
    """
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not _is_print(node):
            continue
        args = [*node.args, *(kw.value for kw in node.keywords)]
        for arg in args:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    line = getattr(sub, "lineno", node.lineno)
                    out.append((line, sub.value))
    return out


def _unencodable(text: str) -> set[str]:
    """The characters cp1252 cannot represent - the ones that raise on a Windows console."""
    bad = set()
    for ch in text:
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            bad.add(ch)
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list every non-ASCII printed char")
    args = ap.parse_args()

    offenders: list[str] = []
    files = 0
    prints = 0
    safe_non_ascii: set[str] = set()

    for path in sorted(RECIPES.glob("*/*/*.py")):
        files += 1
        rel = path.relative_to(ROOT)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            # A recipe that cannot parse is a different, louder problem - say so, don't skip it.
            offenders.append(f"{rel}: does not parse ({exc})")
            continue
        for lineno, text in _printed_literals(tree):
            prints += 1
            bad = _unencodable(text)
            safe_non_ascii |= {c for c in text if ord(c) > 0x7F} - bad
            if not bad:
                continue
            shown = " ".join(f"U+{ord(c):04X}" for c in sorted(bad))
            offenders.append(
                f"{rel}:{lineno}: prints {shown} - cp1252 cannot encode it, so this "
                f"raises UnicodeEncodeError on a Windows console"
            )

    if args.list and safe_non_ascii:
        print("non-ASCII characters that ARE printed and are safe (cp1252 covers them):")
        for c in sorted(safe_non_ascii):
            print(f"  U+{ord(c):04X}  {c!r}")

    verdict = "FAIL" if offenders else "PASS"
    print(
        f"check_print_encoding: {verdict} - {files} recipe file(s), "
        f"{prints} printed literal(s), {len(offenders)} offender(s)"
    )
    for o in offenders:
        print(f"  {o}", file=sys.stderr)
    if offenders:
        print(
            "\nSpell the intent in ASCII (OK / -> / WARNING), or move the note to the docstring "
            "or README - those are read, never encoded to a console.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
