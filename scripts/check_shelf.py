"""Assert the INSTALLED cendor packages match what is published on PyPI.

Why this exists: `uv.lock` is deliberately not committed here, so CI always re-resolves the current
shipped packages — but a *local* checkout keeps whatever it resolved last time. On 2026-07-31 a full
live validation sweep of this repo ran to completion, green, against `cendor-contextkit 1.0.3` while
1.1.0 had been published that morning. Nothing was wrong with the repo; the sweep was simply green
about a shelf nobody ships. A validation run should establish this before it measures anything.

    uv run python scripts/check_shelf.py          # exit 1 on any mismatch
    uv run python scripts/check_shelf.py --quiet   # only print problems

This needs network (it queries PyPI) and is therefore NOT part of the offline test suite. It is a
pre-flight for a maintainer doing a live sweep or a release, not a CI gate.
"""

from __future__ import annotations

import importlib.metadata as md
import json
import sys
import urllib.error
import urllib.request

PACKAGES = (
    "cendor-core",
    "cendor-contextkit",
    "cendor-squeeze",
    "cendor-tokenguard",
    "cendor-guardrails",
    "cendor-cassette",
    "cendor-acttrace",
    "cendor-libs",
    "cendor-sdk",
)
TIMEOUT = 15


def published(pkg: str) -> str | None:
    url = f"https://pypi.org/pypi/{pkg}/json"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return str(json.load(r)["info"]["version"])
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
        print(f"  {pkg:22} ?? could not reach PyPI: {type(exc).__name__}")
        return None


def installed(pkg: str) -> str | None:
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


def main() -> int:
    quiet = "--quiet" in sys.argv
    behind, unknown = [], []
    for pkg in PACKAGES:
        ins, pub = installed(pkg), published(pkg)
        if pub is None:
            unknown.append(pkg)
            continue
        if ins is None:
            if not quiet:
                print(f"  {pkg:22} not installed (published {pub})")
            continue
        if ins == pub:
            if not quiet:
                print(f"  {pkg:22} {ins}")
        else:
            behind.append((pkg, ins, pub))
            print(f"  {pkg:22} {ins}  <-- PUBLISHED {pub}")

    if behind:
        print(
            f"\n{len(behind)} package(s) behind the published shelf. A live sweep or a release run "
            "now measures a shelf nobody ships. Refresh with:\n"
            "    uv lock --upgrade && uv sync\n"
            "  (if that is a no-op: rm uv.lock && uv lock --refresh && uv sync)"
        )
        return 1
    if unknown:
        print(f"\n{len(unknown)} package(s) unverified — PyPI unreachable. Not asserting.")
        return 0
    if not quiet:
        print("\nshelf current: every cendor package matches PyPI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
