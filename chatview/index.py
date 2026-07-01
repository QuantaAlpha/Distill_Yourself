"""Index building, caching, and refresh logic.

Owns the global mutable index state (_index, _index_lock, etc.) and provides
build_index() / schedule_index_refresh_if_stale() for the rest of the app.
"""

import json
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration constants (mirrored from server.py)
# ---------------------------------------------------------------------------
PROJECTS_DIR = Path.home() / ".claude" / "projects"
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
INDEX_CACHE = CACHE_DIR / "index.json"
INDEX_SCHEMA_VERSION = 2  # bump when extract_metadata logic changes
MAX_SEARCH_WORKERS = 8

# Codex CLI paths
CODEX_DIR = Path.home() / ".codex"
CODEX_SESSIONS_DIR = CODEX_DIR / "sessions"
CODEX_ARCHIVED_DIR = CODEX_DIR / "archived_sessions"
CODEX_INDEX_FILE = CODEX_DIR / "session_index.jsonl"

# ---------------------------------------------------------------------------
# Shared mutable state (populated at startup)
# ---------------------------------------------------------------------------
_index = {"projects": {}, "sessions": {}, "_file_mtimes": {}}
_index_lock = threading.Lock()
# NOTE: _codex_titles lives in chatview.parsers.codex (populated by _load_codex_titles)

# Result cache for heavy endpoints (invalidated on index rebuild)
_result_cache = {}  # key -> (index_gen, result)
_index_gen = 0  # bumped on each build_index()
_cache_lock = threading.Lock()
_index_refresh_lock = threading.Lock()
_index_refresh_running = False
_last_index_stale_check = 0.0
INDEX_STALE_CHECK_INTERVAL = float(os.environ.get("INDEX_STALE_CHECK_INTERVAL", "10"))


def _cached(key, compute_fn):
    """Return cached result if index hasn't changed, else compute and cache.

    Uses double-checked locking with ``_cache_lock``:
    1. Fast path: check cache under lock; return hit.
    2. Release lock before computing (so concurrent misses run in parallel).
    3. Re-acquire lock and re-check before writing to avoid stale overwrites.
    """
    with _cache_lock:
        gen = _index_gen
        entry = _result_cache.get(key)
        if entry and entry[0] == gen:
            return entry[1]
    # Compute outside the lock to avoid serializing cache-miss computation
    result = compute_fn()
    with _cache_lock:
        # Re-check: another thread may have written while we were computing,
        # or the index gen may have advanced (in which case our result is stale).
        if _index_gen != gen:
            # Index changed during computation — don't write (caller still gets value)
            return result
        existing = _result_cache.get(key)
        if existing and existing[0] == gen:
            # Another thread already wrote the same generation — use theirs
            return existing[1]
        _result_cache[key] = (gen, result)
    return result


def _session_source_mtimes() -> dict:
    """Return source JSONL file mtimes for Claude and Codex sessions."""
    files = {}
    if PROJECTS_DIR.exists():
        for proj_dir in PROJECTS_DIR.iterdir():
            if not proj_dir.is_dir():
                continue
            for jsonl_file in proj_dir.glob("*.jsonl"):
                try:
                    files[str(jsonl_file)] = os.path.getmtime(jsonl_file)
                except OSError:
                    pass
    if CODEX_SESSIONS_DIR.exists():
        for jsonl_file in CODEX_SESSIONS_DIR.rglob("*.jsonl"):
            try:
                files[str(jsonl_file)] = os.path.getmtime(jsonl_file)
            except OSError:
                pass
    if CODEX_ARCHIVED_DIR.exists():
        for jsonl_file in CODEX_ARCHIVED_DIR.glob("*.jsonl"):
            try:
                files[str(jsonl_file)] = os.path.getmtime(jsonl_file)
            except OSError:
                pass
    return files


def _index_sources_changed() -> bool:
    """Check whether source files differ from the current in-memory index."""
    current = _session_source_mtimes()
    with _index_lock:
        indexed = dict(_index.get("_file_mtimes", {}))
    if len(current) != len(indexed):
        return True
    for path, mtime in current.items():
        if indexed.get(path) != mtime:
            return True
    return False


def _index_refresh_worker(reason: str):
    global _index_refresh_running
    try:
        t0 = time.time()
        build_index()
        print(f"Index refreshed ({reason}) in {time.time() - t0:.1f}s")
    except Exception as e:
        print(f"Index refresh error ({reason}): {e}")
    finally:
        with _index_refresh_lock:
            _index_refresh_running = False


def schedule_index_refresh_if_stale(
    reason: str = "stale-check", force_check: bool = False
) -> bool:
    """Start a background index refresh if source JSONL files changed."""
    global _index_refresh_running, _last_index_stale_check
    now = time.time()
    with _index_refresh_lock:
        if _index_refresh_running:
            return False
        if (
            not force_check
            and now - _last_index_stale_check < INDEX_STALE_CHECK_INTERVAL
        ):
            return False
        _last_index_stale_check = now

    if not _index_sources_changed():
        return False

    with _index_refresh_lock:
        if _index_refresh_running:
            return False
        _index_refresh_running = True
    threading.Thread(target=_index_refresh_worker, args=(reason,), daemon=True).start()
    return True


def _post_process_db_refresh(_db, force: bool, changed: bool):
    """Refresh derived DB state after source files changed."""
    if not changed:
        return
    if force or not _db.verify_fts_integrity():
        _db.rebuild_fts()
    _db.refresh_aggregates()


def build_index(force: bool = False) -> dict:
    """Scan all JSONL files and build/update the metadata index + SQLite DB."""
    global _index, _index_gen

    from chatview.parsers.claude import extract_metadata, pretty_project_name
    from chatview.parsers.codex import (
        _load_codex_titles,
        _codex_project_name,
        extract_codex_metadata,
        _store_session_insights,
    )
    from chatview import db as _db

    _db.init_db()

    # Discover JSONL files
    jsonl_files = []
    if PROJECTS_DIR.exists():
        for proj_dir in sorted(PROJECTS_DIR.iterdir()):
            if not proj_dir.is_dir():
                continue
            for f in proj_dir.glob("*.jsonl"):
                jsonl_files.append((str(f), proj_dir.name))

    # Load cached index
    cached = {}
    if not force and INDEX_CACHE.exists():
        try:
            with open(INDEX_CACHE, "r") as f:
                cached = json.load(f)
            # Discard cache built by an older metadata schema (e.g. pre custom-title)
            if cached.get("_schema_version") != INDEX_SCHEMA_VERSION:
                cached = {}
        except Exception:
            cached = {}

    cached_mtimes = cached.get("_file_mtimes", {})
    cached_sessions = cached.get("sessions", {})

    # Determine which files need (re)parsing
    current_files = {}
    to_parse = []
    for fpath, proj_name in jsonl_files:
        mtime = os.path.getmtime(fpath)
        current_files[fpath] = mtime
        if fpath not in cached_mtimes or cached_mtimes[fpath] != mtime:
            to_parse.append((fpath, proj_name))

    print(f"Index: {len(jsonl_files)} files, {len(to_parse)} need parsing")

    # Parse files that changed (parallel)
    new_sessions = {}
    if to_parse:
        _db.begin_bulk()
        bulk_n = 0
        try:
            with ThreadPoolExecutor(max_workers=MAX_SEARCH_WORKERS) as pool:
                futures = {
                    pool.submit(extract_metadata, fp): (fp, pn) for fp, pn in to_parse
                }
                for future in as_completed(futures):
                    fp, pn = futures[future]
                    try:
                        meta = future.result()
                        if meta:
                            meta["project"] = pn
                            meta["projectName"] = pretty_project_name(pn)
                            meta["source"] = "claude"
                            meta["_mtime"] = current_files.get(fp, 0)
                            new_sessions[meta["id"]] = meta
                            _db.upsert_session(
                                meta,
                                meta.get("userTexts", []),
                                meta.get("assistantSnippets", []),
                            )
                            _store_session_insights(meta)
                            bulk_n += 1
                            if bulk_n % 50 == 0:
                                _db.bulk_commit()
                    except Exception as e:
                        print(f"Error parsing {fp}: {e}")
        finally:
            _db.end_bulk()

    # Merge with cache (keep unchanged sessions from cache) — O(N) via dict lookup
    new_by_path = {}
    for sid, meta in new_sessions.items():
        fp = meta.get("filePath")
        if fp:
            new_by_path[fp] = (sid, meta)
    cached_by_path = {}
    for sid, meta in cached_sessions.items():
        fp = meta.get("filePath")
        if fp:
            cached_by_path[fp] = (sid, meta)

    sessions = {}
    for fpath, proj_name in jsonl_files:
        if fpath in new_by_path:
            sid, meta = new_by_path[fpath]
            sessions[sid] = meta
        elif fpath in cached_by_path:
            sid, meta = cached_by_path[fpath]
            sessions[sid] = meta

    # ── Codex session scanning ──
    _load_codex_titles()
    codex_files = []
    if CODEX_SESSIONS_DIR.exists():
        for jsonl_file in CODEX_SESSIONS_DIR.rglob("*.jsonl"):
            codex_files.append(str(jsonl_file))
    if CODEX_ARCHIVED_DIR.exists():
        for jsonl_file in CODEX_ARCHIVED_DIR.glob("*.jsonl"):
            codex_files.append(str(jsonl_file))

    codex_to_parse = []
    for fpath in codex_files:
        mtime = os.path.getmtime(fpath)
        current_files[fpath] = mtime
        if fpath not in cached_mtimes or cached_mtimes[fpath] != mtime:
            codex_to_parse.append(fpath)

    print(f"Codex: {len(codex_files)} files, {len(codex_to_parse)} need parsing")

    codex_new = {}
    if codex_to_parse:
        _db.begin_bulk()
        bulk_n = 0
        try:
            with ThreadPoolExecutor(max_workers=MAX_SEARCH_WORKERS) as pool:
                futures = {
                    pool.submit(extract_codex_metadata, fp): fp for fp in codex_to_parse
                }
                for future in as_completed(futures):
                    fp = futures[future]
                    try:
                        meta = future.result()
                        if meta:
                            meta["projectName"] = _codex_project_name(meta.get("cwd", ""))
                            meta["project"] = "codex"
                            meta["_mtime"] = current_files.get(fp, 0)
                            codex_new[meta["id"]] = meta
                            _db.upsert_session(
                                meta,
                                meta.get("userTexts", []),
                                meta.get("assistantSnippets", []),
                            )
                            _store_session_insights(meta)
                            bulk_n += 1
                            if bulk_n % 50 == 0:
                                _db.bulk_commit()
                    except Exception as e:
                        print(f"Error parsing Codex {fp}: {e}")
        finally:
            _db.end_bulk()

    # Merge Codex sessions — O(N) via dict lookup
    codex_new_by_path = {}
    for sid, meta in codex_new.items():
        fp = meta.get("filePath")
        if fp:
            codex_new_by_path[fp] = (sid, meta)
    for fpath in codex_files:
        if fpath in codex_new_by_path:
            sid, meta = codex_new_by_path[fpath]
            sessions[sid] = meta
        elif fpath in cached_by_path:
            sid, meta = cached_by_path[fpath]
            sessions[sid] = meta

    # Build project grouping
    projects = {}
    for sid, meta in sessions.items():
        pname = meta.get("projectName", "unknown")
        if pname not in projects:
            projects[pname] = {
                "name": pname,
                "dirName": meta.get("project", ""),
                "sessionCount": 0,
            }
        projects[pname]["sessionCount"] += 1

    index = {
        "_schema_version": INDEX_SCHEMA_VERSION,
        "projects": projects,
        "sessions": sessions,
        "_file_mtimes": current_files,
    }

    pruned_count = _db.prune_stale_sessions(current_files.keys())
    if pruned_count:
        print(f"DB prune: {pruned_count} stale sessions")

    # Backfill DB from cached sessions (only if DB is missing entries)
    db_count = _db.get_conn().execute("SELECT count(*) FROM sessions").fetchone()[0]
    if db_count < len(sessions):
        _db.begin_bulk()
        backfill_count = 0
        try:
            for sid, meta in sessions.items():
                exists = (
                    _db.get_conn()
                    .execute("SELECT 1 FROM sessions WHERE id=?", (sid,))
                    .fetchone()
                )
                if not exists:
                    _db.upsert_session(
                        meta, meta.get("userTexts", []), meta.get("assistantSnippets", [])
                    )
                    backfill_count += 1
                    if backfill_count % 50 == 0:
                        _db.bulk_commit()
        finally:
            _db.end_bulk()
        if backfill_count:
            print(f"DB backfill: {backfill_count} sessions")

    # Backfill insight tables if most sessions lack insight data
    insight_sessions = (
        _db.get_conn()
        .execute("SELECT COUNT(DISTINCT session_id) FROM insight_tool_usage")
        .fetchone()[0]
    )
    if insight_sessions < len(sessions) * 0.5 and len(sessions) > 0:
        # Collect session IDs already in insight tables
        existing_insight_sids = set(
            r[0]
            for r in _db.get_conn()
            .execute("SELECT DISTINCT session_id FROM insight_tool_usage")
            .fetchall()
        )
        print(
            f"Backfilling insight tables ({len(sessions) - len(existing_insight_sids)} sessions)..."
        )
        backfill_t = time.time()
        backfill_n = 0
        _db.begin_bulk()
        try:
            for sid, meta in sessions.items():
                if sid in existing_insight_sids:
                    continue
                fp = meta.get("filePath", "")
                source = meta.get("source", "claude")
                if fp and os.path.exists(fp):
                    try:
                        fresh = (
                            extract_codex_metadata(fp)
                            if source == "codex"
                            else extract_metadata(fp)
                        )
                        if fresh:
                            fresh["projectName"] = meta.get("projectName", "")
                            fresh["date"] = meta.get("date", "")
                            _store_session_insights(fresh)
                            backfill_n += 1
                            if backfill_n % 50 == 0:
                                _db.bulk_commit()
                    except Exception:
                        pass
        finally:
            _db.end_bulk()
        print(
            f"  Insight backfill: {backfill_n} sessions in {time.time() - backfill_t:.1f}s"
        )

    # Strip non-serializable insight data before cache write
    # NOTE: userTexts/assistantSnippets kept for now — analyze.py subprocess still reads them.
    # They can be stripped after analyze.py is refactored to use DB queries directly.
    for sid, meta in sessions.items():
        for k in (
            "_insight_tools",
            "_insight_files",
            "_insight_errors",
            "_insight_snippets",
        ):
            meta.pop(k, None)

    # Save to cache
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(INDEX_CACHE, "w") as f:
            json.dump(index, f, ensure_ascii=False)
    except Exception as e:
        print(f"Cache write error: {e}")

    with _index_lock:
        _index = index
        _index_gen += 1
        _result_cache.clear()

    # Upserts/prunes maintain FTS incrementally; rebuild only on force or drift.
    if new_sessions or codex_new or pruned_count:
        try:
            _post_process_db_refresh(
                _db,
                force=force,
                changed=bool(new_sessions or codex_new or pruned_count),
            )
        except Exception as e:
            print(f"DB post-process error: {e}")

    db_count = _db.get_conn().execute("SELECT count(*) FROM sessions").fetchone()[0]
    print(
        f"Index ready: {len(sessions)} sessions across {len(projects)} projects (DB: {db_count})"
    )

    # Clean up stale evolve cache entries (Issue 2.2)
    try:
        deleted = _db.cleanup_old_cache(max_age_days=30)
        if deleted:
            print(f"Evolve cache cleanup: {deleted} stale entries removed")
    except Exception as e:
        print(f"Evolve cache cleanup error: {e}")

    return index
