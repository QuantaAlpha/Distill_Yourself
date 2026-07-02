"""Session CRUD, FTS search, and query helpers."""

import re
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from .core import get_conn, maybe_commit, query_in_chunks


# ---------------------------------------------------------------------------
# Session upsert
# ---------------------------------------------------------------------------
def upsert_session(meta: dict, user_texts: list, assistant_snippets: list):
    """Insert or replace a session and its messages.

    meta keys: id, title, date, lastDate, filePath, fileSize, _mtime,
               userMessageCount, preview, project, projectName, source
    user_texts / assistant_snippets: list of {idx, text, ts}
    """
    conn = get_conn()
    sid = meta["id"]

    # Remove old title FTS entry BEFORE the REPLACE (which changes rowid).
    # Use FTS5 external-content delete command with old values for correctness.
    old_row = conn.execute(
        "SELECT rowid, title, project_name FROM sessions WHERE id=?", (sid,)
    ).fetchone()
    if old_row:
        conn.execute(
            "INSERT INTO sessions_fts(sessions_fts, rowid, title, project_name) VALUES('delete', ?,?,?)",
            (old_row["rowid"], old_row["title"] or "", old_row["project_name"] or ""),
        )

    conn.execute(
        """INSERT OR REPLACE INTO sessions
           (id, title, date, last_date, file_path, file_size, file_mtime,
            user_message_count, preview, project, project_name, source, starred)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,
            COALESCE((SELECT starred FROM sessions WHERE id=?),0))""",
        (
            sid,
            meta.get("title", ""),
            meta.get("date", ""),
            meta.get("lastDate", ""),
            meta.get("filePath", ""),
            meta.get("fileSize"),
            meta.get("_mtime"),
            meta.get("userMessageCount", 0),
            meta.get("preview", ""),
            meta.get("project", ""),
            meta.get("projectName", ""),
            meta.get("source", "claude"),
            sid,  # for COALESCE subquery to preserve existing starred value
        ),
    )
    # Insert new title FTS entry after the session row exists.
    session_rowid = conn.execute(
        "SELECT rowid FROM sessions WHERE id=?", (sid,)
    ).fetchone()["rowid"]
    conn.execute(
        "INSERT INTO sessions_fts(rowid, title, project_name) VALUES (?,?,?)",
        (session_rowid, meta.get("title", ""), meta.get("projectName", "")),
    )

    # Delete old messages (cascades FTS via triggers would need manual rebuild;
    # we delete FTS rows manually here).
    old_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM messages WHERE session_id=?", (sid,)
        ).fetchall()
    ]
    if old_ids:
        # 单个会话的消息数也可能超过 SQLite 宿主参数上限，分批删 FTS 行。
        for i in range(0, len(old_ids), 900):
            chunk = old_ids[i : i + 900]
            placeholders = ",".join("?" * len(chunk))
            conn.execute(
                f"DELETE FROM messages_fts WHERE rowid IN ({placeholders})", chunk
            )
        conn.execute("DELETE FROM messages WHERE session_id=?", (sid,))

    # Insert new messages (user + assistant)
    rows = []
    for item in user_texts:
        rows.append(
            (sid, item.get("idx"), "user", item.get("text", ""), item.get("ts", ""))
        )
    for item in assistant_snippets:
        rows.append(
            (
                sid,
                item.get("idx"),
                "assistant",
                item.get("text", ""),
                item.get("ts", ""),
            )
        )

    if rows:
        conn.executemany(
            "INSERT INTO messages (session_id, idx, role, text, ts) VALUES (?,?,?,?,?)",
            rows,
        )
        # Sync FTS
        new_ids = conn.execute(
            "SELECT id, text FROM messages WHERE session_id=? ORDER BY id",
            (sid,),
        ).fetchall()
        conn.executemany(
            "INSERT INTO messages_fts(rowid, text) VALUES (?,?)",
            [(r["id"], r["text"]) for r in new_ids],
        )

    maybe_commit(conn)


# ---------------------------------------------------------------------------
# FTS rebuild
# ---------------------------------------------------------------------------
def rebuild_fts():
    """Rebuild the FTS index from scratch."""
    conn = get_conn()
    conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
    conn.execute("INSERT INTO sessions_fts(sessions_fts) VALUES('rebuild')")
    maybe_commit(conn)


def verify_fts_integrity() -> bool:
    """Return whether FTS row counts match their content tables."""
    conn = get_conn()
    messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    messages_fts = conn.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0]
    sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    sessions_fts = conn.execute("SELECT COUNT(*) FROM sessions_fts").fetchone()[0]
    return messages == messages_fts and sessions == sessions_fts


def prune_stale_sessions(valid_file_paths) -> int:
    """Remove sessions whose source file no longer exists in the current scan."""
    conn = get_conn()
    valid = set(valid_file_paths or [])
    rows = conn.execute("SELECT id, file_path FROM sessions").fetchall()
    stale_ids = [r["id"] for r in rows if r["file_path"] not in valid]
    if not stale_ids:
        return 0

    # 分批规避 SQLite 宿主参数上限：先批量取出待删消息的 rowid 删 FTS，再分批删各表。
    msg_ids = [
        r["id"]
        for r in query_in_chunks(
            conn,
            "SELECT id FROM messages WHERE session_id IN ({placeholders})",
            stale_ids,
        )
    ]
    for i in range(0, len(msg_ids), 900):
        chunk = msg_ids[i : i + 900]
        ph = ",".join("?" * len(chunk))
        conn.execute(f"DELETE FROM messages_fts WHERE rowid IN ({ph})", chunk)
    stale_rowids = [r["rowid"] for r in query_in_chunks(
        conn, "SELECT rowid FROM sessions WHERE id IN ({placeholders})", stale_ids
    )]
    for i in range(0, len(stale_rowids), 900):
        chunk = stale_rowids[i : i + 900]
        ph = ",".join("?" * len(chunk))
        conn.execute(f"DELETE FROM sessions_fts WHERE rowid IN ({ph})", chunk)

    for table in (
        "messages",
        "insight_tool_usage",
        "insight_file_refs",
        "insight_errors",
        "insight_snippets",
        "correction_events",
        "correction_session_state",
    ):
        for i in range(0, len(stale_ids), 900):
            chunk = stale_ids[i : i + 900]
            ph = ",".join("?" * len(chunk))
            conn.execute(f"DELETE FROM {table} WHERE session_id IN ({ph})", chunk)
    for i in range(0, len(stale_ids), 900):
        chunk = stale_ids[i : i + 900]
        ph = ",".join("?" * len(chunk))
        conn.execute(f"DELETE FROM sessions WHERE id IN ({ph})", chunk)
    maybe_commit(conn)
    return len(stale_ids)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def get_filtered_sessions(source="all", project="", date="", max_days=99999) -> list:
    """Return list of session dicts filtered by source/project/date range."""
    conn = get_conn()
    clauses = []
    params = []

    if source and source != "all":
        clauses.append("source=?")
        params.append(source)

    if project:
        clauses.append("project_name=?")
        params.append(project)

    if date:
        clauses.append("date >= ?")
        params.append(date)

    if max_days < 99999:
        cutoff = (datetime.utcnow() - timedelta(days=max_days)).strftime("%Y-%m-%d")
        clauses.append("date >= ?")
        params.append(cutoff)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM sessions {where} ORDER BY date DESC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_user_queries(session_ids=None, limit=200) -> list:
    """Return user messages joined with session info."""
    conn = get_conn()
    if session_ids is not None:
        if not session_ids:
            return []
        # 会话数可能超过 SQLite 宿主参数上限，按 id 分批查询；批内 ORDER BY/LIMIT 仅对
        # 单批生效，合并后再做全局 ts 降序并截断到 limit。
        rows = query_in_chunks(
            conn,
            """
            SELECT m.text, m.ts, s.project_name, s.source, s.id AS session_id, s.title
            FROM messages m
            JOIN sessions s ON m.session_id = s.id
            WHERE m.role='user' AND m.session_id IN ({placeholders})
            ORDER BY m.ts DESC
            LIMIT ?
        """,
            list(session_ids),
            extra_params=(limit,),
        )
        result = [dict(r) for r in rows]
        result.sort(key=lambda r: r.get("ts") or "", reverse=True)
        return result[:limit]
    else:
        sql = """
            SELECT m.text, m.ts, s.project_name, s.source, s.id AS session_id, s.title
            FROM messages m
            JOIN sessions s ON m.session_id = s.id
            WHERE m.role='user'
            ORDER BY m.ts DESC
            LIMIT ?
        """
        rows = conn.execute(sql, [limit]).fetchall()
        return [dict(r) for r in rows]


def _sanitize_fts_query(query: str) -> str:
    """Sanitize a user query for FTS5 MATCH: wrap each token in double quotes."""
    tokens = re.split(r"[\s,;]+", query.strip())
    sanitized = []
    for t in tokens:
        clean = re.sub(r'["\*\(\)\{\}\[\]^~:]', "", t)
        if clean:
            sanitized.append(f'"{clean}"')
    return " ".join(sanitized) if sanitized else ""


def search_fts(query: str, limit=50) -> list:
    """Full-text search on messages. Returns dicts with message + session info."""
    conn = get_conn()
    fts_sql = """
        SELECT m.id, m.session_id, m.idx, m.role, m.text, m.ts,
               s.title, s.project_name, s.source
        FROM messages_fts fts
        JOIN messages m ON fts.rowid = m.id
        JOIN sessions s ON m.session_id = s.id
        WHERE messages_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """
    safe_query = _sanitize_fts_query(query)
    if safe_query:
        try:
            rows = conn.execute(fts_sql, [safe_query, limit]).fetchall()
            if rows:
                return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            pass

    # Fallback: LIKE-based search
    like_sql = """
        SELECT m.id, m.session_id, m.idx, m.role, m.text, m.ts,
               s.title, s.project_name, s.source
        FROM messages m
        JOIN sessions s ON m.session_id = s.id
        WHERE m.text LIKE ?
        ORDER BY m.ts DESC
        LIMIT ?
    """
    try:
        rows = conn.execute(like_sql, [f"%{query}%", limit]).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def search_title_fts(query: str, limit=50) -> list:
    """Full-text search on session titles and project names."""
    conn = get_conn()
    fts_sql = """
        SELECT s.id AS session_id, s.title, s.project_name, s.date, s.source,
               bm25(sessions_fts, 0.7, 1.8) AS rank
        FROM sessions_fts
        JOIN sessions s ON sessions_fts.rowid = s.rowid
        WHERE sessions_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """
    safe_query = _sanitize_fts_query(query)
    if not safe_query:
        return []
    try:
        rows = conn.execute(fts_sql, [safe_query, limit]).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


# ---------------------------------------------------------------------------
# Single-session lookups
# ---------------------------------------------------------------------------
def rename_session(session_id: str, new_title: str) -> bool:
    """Rename a session and update the FTS entry. Returns True if found."""
    conn = get_conn()
    old_row = conn.execute(
        "SELECT rowid, title, project_name FROM sessions WHERE id=?", (session_id,)
    ).fetchone()
    if not old_row:
        return False
    # Delete old FTS entry
    conn.execute(
        "INSERT INTO sessions_fts(sessions_fts, rowid, title, project_name) VALUES('delete', ?,?,?)",
        (old_row["rowid"], old_row["title"] or "", old_row["project_name"] or ""),
    )
    # Update session title
    conn.execute("UPDATE sessions SET title=? WHERE id=?", (new_title, session_id))
    # Insert new FTS entry
    conn.execute(
        "INSERT INTO sessions_fts(rowid, title, project_name) VALUES (?,?,?)",
        (old_row["rowid"], new_title, old_row["project_name"] or ""),
    )
    maybe_commit(conn)
    return True


def get_session_meta(session_id: str) -> Optional[dict]:
    """Return a single session dict by exact ID match only.  Returns None if not found."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    return dict(row) if row else None


def get_session_by_partial_id(partial_id: str) -> Optional[dict]:
    """Return a single session dict by partial ID match (substring via =).

    Searches for the first session whose id matches ``partial_id`` as a
    substring.  Returns None if no session matches.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM sessions WHERE id LIKE ? LIMIT 1",
        (f"%{partial_id}%",),
    ).fetchall()
    return dict(rows[0]) if rows else None


def get_session_messages(session_id: str, role: str = "") -> list:
    """Return messages for a session, optionally filtered by role."""
    conn = get_conn()
    if role:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id=? AND role=? ORDER BY idx",
            (session_id, role),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY idx",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_message_window(session_id: str, start_idx: int, end_idx: int) -> list:
    """Return messages in an inclusive idx window for a session."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT * FROM messages
        WHERE session_id=? AND idx BETWEEN ? AND ?
        ORDER BY idx
        """,
        (session_id, start_idx, end_idx),
    ).fetchall()
    return [dict(r) for r in rows]
