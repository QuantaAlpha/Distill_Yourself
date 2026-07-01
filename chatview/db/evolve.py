"""Evolve cache + run/progress storage helpers."""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from . import core as _core
from .core import get_conn

_LEGACY_EVOLVE_TABS = ("profile", "memory", "rules", "signals", "patterns")
_legacy_evolve_scanned_dirs = set()


def _utc_now() -> str:
    return datetime.utcnow().isoformat()


def _json_load(raw: str):
    try:
        return json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def _legacy_evolve_cache_dir() -> Path:
    return _core.CACHE_DIR / "evolve"


def _legacy_evolve_scope(tab: str) -> tuple[str, str, str, str]:
    """Canonical SQLite scope for migrated legacy cache rows."""
    return ("all", "7d", "", "legacy")


def _legacy_evolve_cache_row(tab: str) -> Optional[dict]:
    """Return an already-migrated legacy row from SQLite, if present."""
    source, date_range, project, engine = _legacy_evolve_scope(tab)
    row = evolve_get(tab, source, date_range, project, engine)
    if not row:
        return None
    return {
        "data": row["data"],
        "updated_at": row["updated_at"],
        "engine": engine,
    }


def _migrate_legacy_evolve_cache(tab: str, data: dict, updated_at: str) -> None:
    """Persist a legacy file-cache payload into SQLite once for future reads."""
    if not isinstance(data, dict):
        return
    source, date_range, project, engine = _legacy_evolve_scope(tab)
    conn = get_conn()
    row = conn.execute(
        """
        SELECT updated_at FROM evolve_cache
        WHERE tab=? AND source=? AND date_range=? AND project=? AND engine=?
    """,
        (tab, source, date_range, project, engine),
    ).fetchone()
    if row and row["updated_at"] >= updated_at:
        return
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO evolve_cache (tab, source, date_range, project, engine,
                                  data, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tab, source, date_range, project, engine)
        DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at
    """,
        (
            tab,
            source,
            date_range,
            project,
            engine,
            json.dumps(data, ensure_ascii=False),
            now,
            max(updated_at, now),
        ),
    )
    conn.commit()


def _legacy_evolve_cache_latest(tab: str) -> Optional[dict]:
    """Return the newest legacy file-cache entry for a tab, if any.

    Older builds stored evolve results in `.cache/evolve/<tab>.<hash>.json`
    instead of SQLite. Scope metadata is not recoverable from those filenames,
    so this helper is only used as a last-resort display fallback after SQLite
    misses for the current request.
    """
    migrated = _legacy_evolve_cache_row(tab)
    if migrated:
        return migrated
    cache_dir = _legacy_evolve_cache_dir()
    try:
        candidates = sorted(
            cache_dir.glob(f"{tab}*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue
            updated_at = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
            _migrate_legacy_evolve_cache(tab, data, updated_at)
            return {"data": data, "updated_at": updated_at, "engine": "legacy"}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return None


def migrate_all_legacy_evolve_cache(force: bool = False) -> int:
    """Eagerly migrate legacy `.cache/evolve/*.json` files into SQLite.

    Older builds only persisted evolve results on disk. Newer code reads from
    SQLite first, so migrate the newest legacy payload for each tab once per
    cache directory to keep previously generated Profile/Memory/Rules/Signals/
    Patterns data visible without waiting for a per-tab read fallback.
    """
    cache_dir = _legacy_evolve_cache_dir().resolve()
    if not force and cache_dir in _legacy_evolve_scanned_dirs:
        return 0

    migrated = 0
    for tab in _LEGACY_EVOLVE_TABS:
        row = _legacy_evolve_cache_latest(tab)
        if row:
            migrated += 1

    _legacy_evolve_scanned_dirs.add(cache_dir)
    return migrated


def evolve_upsert(
    tab: str, source: str, date_range: str, project: str, engine: str, data_json: str
):
    """Insert or replace evolve tab data for a given scope."""
    conn = get_conn()
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO evolve_cache (tab, source, date_range, project, engine,
                                  data, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tab, source, date_range, project, engine)
        DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at
    """,
        (
            tab,
            source or "all",
            date_range or "7d",
            project or "",
            engine or "auto",
            data_json,
            now,
            now,
        ),
    )
    conn.commit()


def evolve_get(
    tab: str, source: str, date_range: str, project: str, engine: str
) -> Optional[dict]:
    """Return {data, updated_at} for an exact scope, or None."""
    conn = get_conn()
    row = conn.execute(
        """
        SELECT data, updated_at FROM evolve_cache
        WHERE tab=? AND source=? AND date_range=? AND project=? AND engine=?
    """,
        (tab, source or "all", date_range or "7d", project or "", engine or "auto"),
    ).fetchone()
    if row:
        return {"data": json.loads(row["data"]), "updated_at": row["updated_at"]}
    return None


def evolve_get_shared(
    tab: str,
    source: str,
    date_range: str,
    project: str,
    engine: str = "auto",
) -> Optional[dict]:
    """Return the best cache row for display.

    Preference order:
    1. Exact engine match for the requested scope.
    2. Latest cache row for the same tab/source/date/project across any engine.
    """
    exact = evolve_get(tab, source, date_range, project, engine)
    if exact:
        return {
            "data": exact["data"],
            "updated_at": exact["updated_at"],
            "engine": engine or "auto",
        }

    conn = get_conn()
    row = conn.execute(
        """
        SELECT data, updated_at, engine FROM evolve_cache
        WHERE tab=? AND source=? AND date_range=? AND project=?
        ORDER BY updated_at DESC LIMIT 1
    """,
        (tab, source or "all", date_range or "7d", project or ""),
    ).fetchone()
    if row:
        return {
            "data": json.loads(row["data"]),
            "updated_at": row["updated_at"],
            "engine": row["engine"],
        }
    return _legacy_evolve_cache_latest(tab)


def evolve_latest(tab: str) -> Optional[dict]:
    """Return most recent data for a tab regardless of scope (for Twin)."""
    conn = get_conn()
    row = conn.execute(
        """
        SELECT data, updated_at FROM evolve_cache
        WHERE tab=? ORDER BY updated_at DESC LIMIT 1
    """,
        (tab,),
    ).fetchone()
    if row:
        return {"data": json.loads(row["data"]), "updated_at": row["updated_at"]}
    legacy = _legacy_evolve_cache_latest(tab)
    if legacy:
        return {"data": legacy["data"], "updated_at": legacy["updated_at"]}
    return None


def evolve_run_start(
    tab: str,
    source: str,
    date_range: str,
    project: str,
    engine: str,
    *,
    lang: str = "zh",
    snapshot: Optional[dict] = None,
    run_id: str = "",
) -> str:
    """Create a new evolve run row and return its run_id."""
    conn = get_conn()
    now = _utc_now()
    run_id = run_id or ("erun_" + uuid.uuid4().hex[:12])
    conn.execute(
        """
        INSERT INTO evolve_runs (
            run_id, tab, source, date_range, project, engine, lang,
            status, snapshot, error_message, created_at, updated_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            run_id,
            tab,
            source or "all",
            date_range or "7d",
            project or "",
            engine or "auto",
            lang or "zh",
            "running",
            json.dumps(snapshot or {}, ensure_ascii=False),
            "",
            now,
            now,
            None,
        ),
    )
    conn.commit()
    return run_id


def evolve_run_get(run_id: str) -> Optional[dict]:
    """Return a persisted evolve run row by run_id."""
    conn = get_conn()
    row = conn.execute(
        """
        SELECT run_id, tab, source, date_range, project, engine, lang,
               status, snapshot, error_message, created_at, updated_at, completed_at
        FROM evolve_runs WHERE run_id=?
    """,
        (run_id,),
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["snapshot"] = _json_load(result.get("snapshot"))
    return result


def evolve_run_update(
    run_id: str,
    *,
    status: Optional[str] = None,
    snapshot: Optional[dict] = None,
    error_message: Optional[str] = None,
) -> Optional[dict]:
    """Update an existing evolve run, merging snapshot fields when provided."""
    current = evolve_run_get(run_id)
    if not current:
        return None
    merged_snapshot = dict(current.get("snapshot") or {})
    if snapshot:
        merged_snapshot.update(snapshot)
    new_status = status or current.get("status") or "running"
    new_error = (
        current.get("error_message", "")
        if error_message is None
        else str(error_message or "")
    )
    now = _utc_now()
    completed_at = (
        now
        if new_status in ("completed", "failed", "cancelled")
        else current.get("completed_at")
    )
    conn = get_conn()
    conn.execute(
        """
        UPDATE evolve_runs
        SET status=?, snapshot=?, error_message=?, updated_at=?, completed_at=?
        WHERE run_id=?
    """,
        (
            new_status,
            json.dumps(merged_snapshot, ensure_ascii=False),
            new_error,
            now,
            completed_at,
            run_id,
        ),
    )
    conn.commit()
    return evolve_run_get(run_id)


def evolve_run_event_append(run_id: str, event: dict) -> Optional[dict]:
    """Append one replayable event for an evolve run and return the stored row."""
    if not run_id or not isinstance(event, dict):
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT COALESCE(MAX(event_index), 0) + 1 AS next_index "
        "FROM evolve_run_events WHERE run_id=?",
        (run_id,),
    ).fetchone()
    event_index = int(row["next_index"] or 1)
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO evolve_run_events (run_id, event_index, event, created_at)
        VALUES (?, ?, ?, ?)
    """,
        (run_id, event_index, json.dumps(event, ensure_ascii=False), now),
    )
    conn.commit()
    return {
        "run_id": run_id,
        "event_index": event_index,
        "event": event,
        "created_at": now,
    }


def evolve_run_events(run_id: str, since: int = 0, limit: int = 500) -> list[dict]:
    """Return replayable events with event_index greater than ``since``."""
    if not run_id:
        return []
    try:
        since = max(0, int(since or 0))
    except (TypeError, ValueError):
        since = 0
    try:
        limit = max(1, min(int(limit or 500), 2000))
    except (TypeError, ValueError):
        limit = 500
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT run_id, event_index, event, created_at
        FROM evolve_run_events
        WHERE run_id=? AND event_index>?
        ORDER BY event_index ASC
        LIMIT ?
    """,
        (run_id, since, limit),
    ).fetchall()
    result = []
    for row in rows:
        result.append(
            {
                "run_id": row["run_id"],
                "event_index": row["event_index"],
                "event": _json_load(row["event"]),
                "created_at": row["created_at"],
            }
        )
    return result


def evolve_run_event_count(run_id: str) -> int:
    """Return persisted event count for a run."""
    if not run_id:
        return 0
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM evolve_run_events WHERE run_id=?",
        (run_id,),
    ).fetchone()
    return int(row["count"] or 0)


def evolve_run_latest(
    tab: str, source: str, date_range: str, project: str, engine: str
) -> Optional[dict]:
    """Return the latest persisted evolve run for an exact scope."""
    conn = get_conn()
    row = conn.execute(
        """
        SELECT run_id FROM evolve_runs
        WHERE tab=? AND source=? AND date_range=? AND project=? AND engine=?
        ORDER BY updated_at DESC LIMIT 1
    """,
        (tab, source or "all", date_range or "7d", project or "", engine or "auto"),
    ).fetchone()
    if not row:
        return None
    return evolve_run_get(row["run_id"])


def evolve_run_latest_shared(
    tab: str,
    source: str,
    date_range: str,
    project: str,
    engine: str = "auto",
) -> Optional[dict]:
    """Return the best run row for display/recovery.

    Preference order:
    1. Exact engine match for the requested scope.
    2. Latest run for the same tab/source/date/project across any engine.
    """
    exact = evolve_run_latest(tab, source, date_range, project, engine)
    if exact:
        return exact

    conn = get_conn()
    row = conn.execute(
        """
        SELECT run_id FROM evolve_runs
        WHERE tab=? AND source=? AND date_range=? AND project=?
        ORDER BY updated_at DESC LIMIT 1
    """,
        (tab, source or "all", date_range or "7d", project or ""),
    ).fetchone()
    if not row:
        return None
    return evolve_run_get(row["run_id"])


def evolve_runs_latest_for_scope(
    source: str, date_range: str, project: str, engine: str
) -> dict:
    """Return the latest run per tab for an exact scope (tab omitted)."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT run_id, tab
        FROM evolve_runs
        WHERE source=? AND date_range=? AND project=? AND engine=?
        ORDER BY updated_at DESC
    """,
        (source or "all", date_range or "7d", project or "", engine or "auto"),
    ).fetchall()
    result = {}
    for row in rows:
        tab = row["tab"]
        if tab in result:
            continue
        run = evolve_run_get(row["run_id"])
        if run:
            result[tab] = run
    return result


def evolve_runs_latest_for_scope_shared(
    source: str, date_range: str, project: str, engine: str = "auto"
) -> dict:
    """Return the best run per tab for display/recovery.

    For each tab, prefer the requested engine's run; otherwise fall back to the
    latest run for the same source/date/project across any engine.
    """
    result = evolve_runs_latest_for_scope(source, date_range, project, engine)
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT run_id, tab
        FROM evolve_runs
        WHERE source=? AND date_range=? AND project=?
        ORDER BY updated_at DESC
    """,
        (source or "all", date_range or "7d", project or ""),
    ).fetchall()
    for row in rows:
        tab = row["tab"]
        if tab in result:
            continue
        run = evolve_run_get(row["run_id"])
        if run:
            result[tab] = run
    return result


def cleanup_old_cache(max_age_days: int = 30) -> int:
    """Delete stale rows from evolve_cache and evolve_runs."""
    conn = get_conn()
    cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).isoformat()
    cache_result = conn.execute(
        "DELETE FROM evolve_cache WHERE updated_at < ?",
        (cutoff,),
    )
    conn.execute(
        "DELETE FROM evolve_runs WHERE updated_at < ? AND status != 'running'",
        (cutoff,),
    )
    conn.commit()
    return cache_result.rowcount
