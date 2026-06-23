"""SQLite storage module — replaces .cache/index.json approach.

Single-file, no classes, thread-local connections, WAL mode.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
DB_PATH = CACHE_DIR / "sessions.db"

_local = threading.local()


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
def get_conn() -> sqlite3.Connection:
    """Return a thread-local sqlite3.Connection with WAL mode and Row factory."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def init_db():
    """Create all tables and indexes if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            title       TEXT,
            date        TEXT,
            last_date   TEXT,
            file_path   TEXT UNIQUE,
            file_size   INTEGER,
            file_mtime  REAL,
            user_message_count INTEGER,
            preview     TEXT,
            project     TEXT,
            project_name TEXT,
            source      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_date         ON sessions(date);
        CREATE INDEX IF NOT EXISTS idx_sessions_project_name ON sessions(project_name);
        CREATE INDEX IF NOT EXISTS idx_sessions_source       ON sessions(source);

        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            idx        INTEGER,
            role       TEXT,
            text       TEXT,
            ts         TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_messages_role    ON messages(role);

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            text,
            content=messages,
            content_rowid=id
        );

        CREATE TABLE IF NOT EXISTS aggregates (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            updated_at TEXT
        );
    """)
    conn.commit()


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

    conn.execute(
        """INSERT OR REPLACE INTO sessions
           (id, title, date, last_date, file_path, file_size, file_mtime,
            user_message_count, preview, project, project_name, source)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
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
        ),
    )

    # Delete old messages (cascades FTS via triggers would need manual rebuild;
    # we delete FTS rows manually here).
    old_ids = [r[0] for r in conn.execute(
        "SELECT id FROM messages WHERE session_id=?", (sid,)
    ).fetchall()]
    if old_ids:
        placeholders = ",".join("?" * len(old_ids))
        conn.execute(f"DELETE FROM messages_fts WHERE rowid IN ({placeholders})", old_ids)
        conn.execute("DELETE FROM messages WHERE session_id=?", (sid,))

    # Insert new messages (user + assistant)
    rows = []
    for item in user_texts:
        rows.append((sid, item.get("idx"), "user", item.get("text", ""), item.get("ts", "")))
    for item in assistant_snippets:
        rows.append((sid, item.get("idx"), "assistant", item.get("text", ""), item.get("ts", "")))

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

    conn.commit()


# ---------------------------------------------------------------------------
# FTS rebuild
# ---------------------------------------------------------------------------
def rebuild_fts():
    """Rebuild the FTS index from scratch."""
    conn = get_conn()
    conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
    conn.commit()


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
        # date is an ISO date string like "2026-06-01"; compare against session.date
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
    """Return user messages joined with session info.

    Returns dicts with: text, ts, project_name, source, session_id, title
    """
    conn = get_conn()
    if session_ids is not None:
        if not session_ids:
            return []
        placeholders = ",".join("?" * len(session_ids))
        sql = f"""
            SELECT m.text, m.ts, s.project_name, s.source, s.id AS session_id, s.title
            FROM messages m
            JOIN sessions s ON m.session_id = s.id
            WHERE m.role='user' AND m.session_id IN ({placeholders})
            ORDER BY m.ts DESC
            LIMIT ?
        """
        rows = conn.execute(sql, list(session_ids) + [limit]).fetchall()
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


def search_fts(query: str, limit=50) -> list:
    """Full-text search on messages. Returns dicts with message + session info."""
    conn = get_conn()
    sql = """
        SELECT m.id, m.session_id, m.idx, m.role, m.text, m.ts,
               s.title, s.project_name, s.source
        FROM messages_fts fts
        JOIN messages m ON fts.rowid = m.id
        JOIN sessions s ON m.session_id = s.id
        WHERE messages_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """
    try:
        rows = conn.execute(sql, [query, limit]).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        # Invalid FTS query syntax — return empty
        return []


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
    conn.commit()


def refresh_aggregates():
    """Compute and cache project_distribution, daily_activity, topic_by_project."""
    conn = get_conn()

    # project_distribution: [{project_name, source, count, total_msgs}]
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

    # daily_activity: [{day, sessions, msgs}] for last 90 days
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

    # topic_by_project: [{project_name, message_count}]
    rows = conn.execute("""
        SELECT s.project_name,
               COUNT(m.id) AS message_count
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id AND m.role='user'
        GROUP BY s.project_name
        ORDER BY message_count DESC
    """).fetchall()
    set_aggregate("topic_by_project", json.dumps([dict(r) for r in rows]))
