"""Aggregates and insight table CRUD helpers."""

import json
from datetime import datetime

from .core import get_conn, maybe_commit


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------
def get_aggregate(key: str):
    """Read a value from the aggregates table. Returns string or None."""
    conn = get_conn()
    row = conn.execute("SELECT value FROM aggregates WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_aggregate(key: str, value: str):
    """Upsert a key/value into aggregates."""
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO aggregates (key, value, updated_at) VALUES (?,?,?)",
        (key, value, now),
    )
    maybe_commit(conn)


def refresh_aggregates():
    """Compute and cache project_distribution, daily_activity, topic_by_project."""
    conn = get_conn()

    # project_distribution
    rows = conn.execute("""
        SELECT s.project_name, s.source,
               COUNT(DISTINCT s.id) AS count,
               COUNT(m.id)          AS total_msgs
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id
        GROUP BY s.project_name, s.source
        ORDER BY count DESC
    """).fetchall()
    set_aggregate("project_distribution", json.dumps([dict(r) for r in rows]))

    # daily_activity (last 90 days)
    rows = conn.execute("""
        SELECT substr(s.date, 1, 10) AS day,
               COUNT(DISTINCT s.id) AS sessions,
               COUNT(m.id)          AS msgs
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id
        WHERE s.date >= date('now', '-90 days')
        GROUP BY day
        ORDER BY day
    """).fetchall()
    set_aggregate("daily_activity", json.dumps([dict(r) for r in rows]))

    # topic_by_project
    rows = conn.execute("""
        SELECT s.project_name,
               COUNT(m.id) AS message_count
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id AND m.role='user'
        GROUP BY s.project_name
        ORDER BY message_count DESC
    """).fetchall()
    set_aggregate("topic_by_project", json.dumps([dict(r) for r in rows]))


# ---------------------------------------------------------------------------
# Insight tables — CRUD helpers
# ---------------------------------------------------------------------------
def clear_session_insights(session_id: str):
    """Delete all insight rows for a session (before re-extraction)."""
    conn = get_conn()
    for table in (
        "insight_tool_usage",
        "insight_file_refs",
        "insight_errors",
        "insight_snippets",
    ):
        conn.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
    maybe_commit(conn)


def bulk_insert_tool_usage(rows: list):
    """Insert rows: [(session_id, day, tool_name, count), ...]"""
    if not rows:
        return
    conn = get_conn()
    conn.executemany(
        "INSERT OR REPLACE INTO insight_tool_usage (session_id, day, tool_name, count) VALUES (?,?,?,?)",
        rows,
    )
    maybe_commit(conn)


def bulk_insert_file_refs(rows: list):
    """Insert rows: [(session_id, file_path, count, project), ...]"""
    if not rows:
        return
    conn = get_conn()
    conn.executemany(
        "INSERT OR REPLACE INTO insight_file_refs (session_id, file_path, count, project) VALUES (?,?,?,?)",
        rows,
    )
    maybe_commit(conn)


def bulk_insert_errors(rows: list):
    """Insert rows: [(session_id, error_key, day, project, count), ...]"""
    if not rows:
        return
    conn = get_conn()
    conn.executemany(
        "INSERT OR REPLACE INTO insight_errors (session_id, error_key, day, project, count) VALUES (?,?,?,?,?)",
        rows,
    )
    maybe_commit(conn)


def bulk_insert_snippets(rows: list):
    """Insert rows: [(session_id, language, code, context, date, applied), ...]"""
    if not rows:
        return
    conn = get_conn()
    conn.executemany(
        "INSERT INTO insight_snippets (session_id, language, code, context, date, applied) VALUES (?,?,?,?,?,?)",
        rows,
    )
    maybe_commit(conn)


def query_tool_heatmap():
    """Return tool usage aggregated by day (last 30 days) for heatmap."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT day, tool_name, SUM(count) as total
        FROM insight_tool_usage
        WHERE day >= date('now', '-30 days')
        GROUP BY day, tool_name
        ORDER BY day DESC
    """).fetchall()
    return [dict(r) for r in rows]


def query_file_hotspots(limit=50):
    """Return top files by access count across all sessions."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT file_path,
               SUM(count) as total_count,
               COUNT(DISTINCT session_id) as session_count,
               GROUP_CONCAT(DISTINCT project) as projects
        FROM insight_file_refs
        GROUP BY file_path
        ORDER BY total_count DESC
        LIMIT ?
    """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def query_error_patterns(limit=30):
    """Return top error patterns aggregated across sessions."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT error_key,
               SUM(count) as total_count,
               COUNT(DISTINCT session_id) as session_count,
               GROUP_CONCAT(DISTINCT project) as projects,
               MIN(day) as first_seen,
               MAX(day) as last_seen
        FROM insight_errors
        GROUP BY error_key
        ORDER BY total_count DESC
        LIMIT ?
    """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def query_snippets(limit=150):
    """Return code snippets sorted by applied first, then newest."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT s.session_id, ses.title as session_title, ses.project_name as project,
               s.language, s.code, s.context, s.date, s.applied
        FROM insight_snippets s
        LEFT JOIN sessions ses ON ses.id = s.session_id
        ORDER BY s.applied DESC, s.date DESC
        LIMIT ?
    """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_session_tool_usage(session_id: str) -> dict:
    """Return tool usage counts for a single session: {tool_name: count}."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT tool_name, SUM(count) as total FROM insight_tool_usage "
        "WHERE session_id=? GROUP BY tool_name",
        (session_id,),
    ).fetchall()
    return {r["tool_name"]: r["total"] for r in rows}


def get_session_file_refs(session_id: str) -> dict:
    """Return file reference counts for a single session: {file_path: count}."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT file_path, count FROM insight_file_refs WHERE session_id=?",
        (session_id,),
    ).fetchall()
    return {r["file_path"]: r["count"] for r in rows}


def get_sessions_for_file(file_path: str) -> list:
    """Return list of session_ids that reference a given file path."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT session_id FROM insight_file_refs WHERE file_path=?",
        (file_path,),
    ).fetchall()
    return [r["session_id"] for r in rows]
