"""squeeze-persist-and-restore — restore the original after the process is gone.

squeeze is reversible because it keeps the original in a **content-addressed store**, keyed by the
hash of the content. The default store is in-process, which is the right default for a request
handler and the wrong one for anything that outlives a request: restart, and every handle you
persisted expands into a `KeyError`.

`use_store(SQLiteStore(path))` swaps the backend for a local file. Then a handle is portable:
`handle.to_dict()` is JSON, `Handle.from_dict(...)` rebuilds it, and `expand()` resolves through
whatever store is active *now*.

This recipe proves it across a **real process boundary** — it re-executes itself with `--restore`,
in a second Python process that shares nothing but the two files on disk. The child also tries the
same handle against a fresh in-memory store, and reports the failure, so the difference is measured
rather than described.

Offline: pure compression, no model call.

  uv run python recipes/libs/squeeze-persist-and-restore/main.py
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cendor.core import tokens
from cendor.squeeze import Handle, MemoryStore, compress, decompress, use_store
from cendor.squeeze.store import SQLiteStore

MODEL = "gpt-4o"


def incident_report(lines: int = 500) -> str:
    return "\n".join(
        f"2026-07-31T11:{i % 60:02}:{i % 60:02}Z WARN api-7 retry {i} upstream=payments "
        f"code=503 backoff_ms={100 * (i % 5)}"
        for i in range(lines)
    )


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def restore(workdir: Path) -> None:
    """The SECOND process. It has the files and nothing else — no objects, no store in memory."""
    saved = json.loads((workdir / "handle.json").read_text(encoding="utf-8"))
    handle = Handle.from_dict(saved["handle"])

    # (a) the default in-process store knows nothing about a previous process.
    use_store(MemoryStore())
    try:
        decompress(handle)
        memory_result = "expanded (unexpected)"
    except KeyError:
        memory_result = "KeyError - the in-process store died with the first process"

    # (b) the SQLite store has the original on disk.
    use_store(SQLiteStore(str(workdir / "originals.db")))
    restored = decompress(handle)

    print(f"  process 2 pid    : {os.getpid()} (a different interpreter)")
    print(f"  MemoryStore()    : {memory_result}")
    print(
        f"  SQLiteStore(...) : restored {len(restored):,} chars, "
        f"sha256 matches: {digest(restored) == saved['digest']}"
    )
    assert digest(restored) == saved["digest"], "the restored content is not the original"


def main() -> None:
    if "--restore" in sys.argv:
        restore(Path(sys.argv[sys.argv.index("--restore") + 1]))
        return

    workdir = Path(tempfile.mkdtemp(prefix="cendor-recipe-"))
    db = workdir / "originals.db"
    content = incident_report()

    use_store(SQLiteStore(str(db)))  # durable backend, before anything is compressed
    small, handle = compress(content, kind="logs", model=MODEL)
    (workdir / "handle.json").write_text(
        json.dumps({"handle": handle.to_dict(), "digest": digest(content)}), encoding="utf-8"
    )

    print(f"  process 1 pid    : {os.getpid()}")
    print(
        f"  compressed       : {tokens.count(content, MODEL):,} -> "
        f"{tokens.count(small, MODEL)} tokens ({handle.technique})"
    )
    print(f"  store on disk    : {db.name}, {db.stat().st_size:,} bytes")
    print(
        f"  handle.to_dict() : {len(json.dumps(handle.to_dict()))} bytes of JSON - "
        f"this is what you persist, not the original"
    )
    print("-- process ends here; everything in memory is lost ------------------")

    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--restore", str(workdir)],
        check=True,
        capture_output=True,
        text=True,
    )
    print(completed.stdout.rstrip())
    assert "sha256 matches: True" in completed.stdout, "the second process could not restore"


if __name__ == "__main__":
    main()
