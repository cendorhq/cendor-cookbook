# squeeze-persist-and-restore — restore the original after the process is gone

**The pain.** You compressed a 40 KB incident report down to 30 tokens, stored the handle in your
database, and shipped. Next week someone asks what the original said — and `expand()` raises
`KeyError`, because the store that held it lived in a process that exited days ago.

**What this shows.** squeeze is reversible because it keeps the original in a **content-addressed
store**, keyed by the hash of the content. The default store is in-process: right for a request
handler, wrong for anything that outlives one. `use_store(SQLiteStore(path))` swaps it for a local
file, and then the handle is portable — `handle.to_dict()` is JSON, `Handle.from_dict(...)` rebuilds
it, and `expand()` resolves through whatever store is active *now*.

Proven across a **real process boundary**: the recipe re-executes itself with `--restore`, in a
second Python interpreter that shares nothing but two files on disk. That child also tries the same
handle against a fresh `MemoryStore()`, so the failure mode is measured rather than described.

Closes `SQLiteStore` and `decompress`, which no other recipe exercises.

## Run it

```bash
uv run python recipes/libs/squeeze-persist-and-restore/main.py
```

## Expected output

```text
  process 1 pid    : 6524
  compressed       : 15,999 -> 30 tokens (normalize+dedup)
  store on disk    : originals.db, 53,248 bytes
  handle.to_dict() : 206 bytes of JSON - this is what you persist, not the original
-- process ends here; everything in memory is lost ------------------
  process 2 pid    : 41880 (a different interpreter)
  MemoryStore()    : KeyError - the in-process store died with the first process
  SQLiteStore(...) : restored 41,689 chars, sha256 matches: True
```

(The pids differ every run — that is the point.)

Read the last two lines together. Same handle, same file, two stores: the in-memory one cannot help
and says so immediately; the SQLite one returns all 41,689 characters, and the sha256 matches the
digest recorded before the first process exited.

**What you persist is the 206-byte handle, not the original.** The original is in the store, deduped
by content hash — so the same document compressed twice costs one copy. That is the trade squeeze
makes: storage for tokens.

`decompress(handle)` and `handle.expand()` are the same call. The store must be set **before**
anything is compressed, or the original lands in the in-process default.

Libraries: `core`, `squeeze` · Offline ✓ · [← all recipes](../../../README.md)
