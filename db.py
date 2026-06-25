"""SQLite storage module — replaces .cache/index.json approach.

Single-file, no classes, thread-local connections, WAL mode.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

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
        CREATE INDEX IF NOT EXISTS idx_messages_session      ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_messages_role         ON messages(role);
        CREATE INDEX IF NOT EXISTS idx_messages_session_role ON messages(session_id, role);

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

        -- =================================================================
        -- Cognitive Model tables (Digital Twin 4-layer pipeline)
        -- =================================================================

        -- L1: Episodes — structured events from conversations
        CREATE TABLE IF NOT EXISTS episodes (
            id          TEXT PRIMARY KEY,
            session_id  TEXT,
            event_index INTEGER,
            task_type   TEXT,
            ai_action   TEXT,
            user_reaction TEXT,
            resolution  TEXT,
            lesson      TEXT,
            signal_type TEXT,
            signal_intensity REAL,
            domain      TEXT,
            created_at  TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            UNIQUE(session_id, event_index)
        );
        CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id);
        CREATE INDEX IF NOT EXISTS idx_episodes_domain  ON episodes(domain);
        CREATE INDEX IF NOT EXISTS idx_episodes_signal  ON episodes(signal_type);

        -- L1→L2 refs: which episodes support which cognitive model items
        CREATE TABLE IF NOT EXISTS episode_refs (
            episode_id  TEXT,
            target_type TEXT,
            target_id   TEXT,
            PRIMARY KEY (episode_id, target_type, target_id),
            FOREIGN KEY (episode_id) REFERENCES episodes(id)
        );

        -- L2 Dim1: Value tensions
        CREATE TABLE IF NOT EXISTS cm_tensions (
            id          TEXT PRIMARY KEY,
            value_a     TEXT,
            value_b     TEXT,
            default_resolution TEXT,
            context_overrides  TEXT,
            confidence  REAL,
            episode_count INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'hypothesis',
            updated_at  TEXT
        );

        -- L2 Dim2: Causal principles
        CREATE TABLE IF NOT EXISTS cm_principles (
            id          TEXT PRIMARY KEY,
            statement   TEXT,
            cause       TEXT,
            effect      TEXT,
            domain      TEXT,
            tension_ids TEXT,
            confidence  REAL,
            status      TEXT DEFAULT 'hypothesis',
            episode_count INTEGER DEFAULT 0,
            updated_at  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_principles_domain ON cm_principles(domain);
        CREATE INDEX IF NOT EXISTS idx_principles_status ON cm_principles(status);

        -- L2 Dim3: Tradeoff matrix
        CREATE TABLE IF NOT EXISTS cm_tradeoffs (
            id          TEXT PRIMARY KEY,
            context     TEXT,
            protect     TEXT,
            sacrifice   TEXT,
            strategy    TEXT,
            confidence  REAL,
            episode_count INTEGER DEFAULT 0,
            updated_at  TEXT
        );

        -- L2 Dim4: Reasoning style
        CREATE TABLE IF NOT EXISTS cm_reasoning (
            id          TEXT PRIMARY KEY,
            dimension   TEXT,
            description TEXT,
            evidence    TEXT,
            confidence  REAL,
            updated_at  TEXT
        );

        -- L2 Dim5: Communication contract
        CREATE TABLE IF NOT EXISTS cm_communication (
            id          TEXT PRIMARY KEY,
            category    TEXT,
            description TEXT,
            domain      TEXT DEFAULT 'all',
            confidence  REAL,
            episode_count INTEGER DEFAULT 0,
            updated_at  TEXT
        );

        -- L2 Dim6: Role modes
        CREATE TABLE IF NOT EXISTS cm_roles (
            id          TEXT PRIMARY KEY,
            role        TEXT,
            behavior_profile TEXT,
            key_preferences  TEXT,
            autonomy_level   TEXT,
            confidence  REAL,
            episode_count INTEGER DEFAULT 0,
            updated_at  TEXT
        );

        -- L2 Dim7: Domain expertise
        CREATE TABLE IF NOT EXISTS cm_expertise (
            id          TEXT PRIMARY KEY,
            domain      TEXT,
            depth       TEXT,
            session_count INTEGER DEFAULT 0,
            key_patterns TEXT,
            autonomy_boundary TEXT,
            confidence  REAL,
            updated_at  TEXT
        );

        -- L3: Policies — compiled from L2 dimensions
        CREATE TABLE IF NOT EXISTS cm_policies (
            id          TEXT PRIMARY KEY,
            condition   TEXT,
            action      TEXT,
            exception   TEXT,
            rationale   TEXT,
            source_type TEXT,
            source_id   TEXT,
            domain      TEXT,
            role_mode   TEXT,
            confidence  REAL,
            status      TEXT DEFAULT 'active',
            evidence_summary TEXT,
            updated_at  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_policies_status ON cm_policies(status);
        CREATE INDEX IF NOT EXISTS idx_policies_source ON cm_policies(source_type, source_id);
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
# Single-session lookups
# ---------------------------------------------------------------------------
def get_session_meta(session_id: str) -> Optional[dict]:
    """Return a single session dict by exact or partial ID match."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if row:
        return dict(row)
    # Partial match fallback
    rows = conn.execute(
        "SELECT * FROM sessions WHERE id LIKE ? LIMIT 1",
        (f"%{session_id}%",),
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


# ---------------------------------------------------------------------------
# Cognitive Model — CRUD helpers
# ---------------------------------------------------------------------------

# Table registry: name → columns (excluding id, updated_at which are auto-managed)
_CM_TABLES = {
    "episodes": ["session_id", "event_index", "task_type", "ai_action",
                 "user_reaction", "resolution", "lesson", "signal_type",
                 "signal_intensity", "domain", "created_at"],
    "episode_refs": ["episode_id", "target_type", "target_id"],
    "cm_tensions": ["value_a", "value_b", "default_resolution",
                    "context_overrides", "confidence", "episode_count", "status"],
    "cm_principles": ["statement", "cause", "effect", "domain",
                      "tension_ids", "confidence", "status", "episode_count"],
    "cm_tradeoffs": ["context", "protect", "sacrifice", "strategy",
                     "confidence", "episode_count"],
    "cm_reasoning": ["dimension", "description", "evidence", "confidence"],
    "cm_communication": ["category", "description", "domain",
                         "confidence", "episode_count"],
    "cm_roles": ["role", "behavior_profile", "key_preferences",
                 "autonomy_level", "confidence", "episode_count"],
    "cm_expertise": ["domain", "depth", "session_count", "key_patterns",
                     "autonomy_boundary", "confidence"],
    "cm_policies": ["condition", "action", "exception", "rationale",
                    "source_type", "source_id", "domain", "role_mode",
                    "confidence", "status", "evidence_summary"],
}


def cm_upsert(table: str, item_id: str, data: dict):
    """Insert or update a cognitive model row."""
    conn = get_conn()
    cols = _CM_TABLES.get(table)
    if not cols:
        raise ValueError(f"Unknown CM table: {table}")

    now = datetime.utcnow().isoformat()
    has_updated = table not in ("episodes", "episode_refs")

    all_cols = ["id"] + [c for c in cols if c in data]
    if has_updated:
        all_cols.append("updated_at")

    vals = [item_id] + [data.get(c) for c in cols if c in data]
    if has_updated:
        vals.append(now)

    placeholders = ",".join("?" * len(all_cols))
    col_str = ",".join(all_cols)
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({col_str}) VALUES ({placeholders})",
        vals,
    )
    conn.commit()


def cm_get(table: str, item_id: str) -> Optional[dict]:
    """Get a single row by id."""
    conn = get_conn()
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (item_id,)).fetchone()
    return dict(row) if row else None


def cm_get_all(table: str, where: str = "", params: tuple = (), order: str = "",
               limit: int = 500) -> list:
    """Get all rows from a CM table with optional filters."""
    conn = get_conn()
    sql = f"SELECT * FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if order:
        sql += f" ORDER BY {order}"
    sql += f" LIMIT {limit}"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def cm_delete(table: str, item_id: str):
    """Delete a single row by id."""
    conn = get_conn()
    conn.execute(f"DELETE FROM {table} WHERE id=?", (item_id,))
    conn.commit()


def cm_count(table: str, where: str = "", params: tuple = ()) -> int:
    """Count rows in a CM table."""
    conn = get_conn()
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return conn.execute(sql, params).fetchone()[0]


def cm_add_ref(episode_id: str, target_type: str, target_id: str):
    """Add an episode → target reference."""
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO episode_refs (episode_id, target_type, target_id) "
        "VALUES (?,?,?)",
        (episode_id, target_type, target_id),
    )
    conn.commit()


def cm_get_refs_for_target(target_type: str, target_id: str) -> list:
    """Get all episodes linked to a cognitive model item."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT e.* FROM episodes e
           JOIN episode_refs r ON e.id = r.episode_id
           WHERE r.target_type=? AND r.target_id=?
           ORDER BY e.created_at DESC""",
        (target_type, target_id),
    ).fetchall()
    return [dict(r) for r in rows]


def get_twin_stats() -> dict:
    """Return cognitive model statistics."""
    conn = get_conn()
    stats = {}
    for table in _CM_TABLES:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        stats[table] = {"count": count}
        # confidence distribution for tables that have it
        if table not in ("episodes", "episode_refs"):
            try:
                rows = conn.execute(
                    f"SELECT AVG(confidence) as avg_conf, "
                    f"MIN(confidence) as min_conf, MAX(confidence) as max_conf "
                    f"FROM {table} WHERE confidence IS NOT NULL"
                ).fetchone()
                if rows and rows["avg_conf"] is not None:
                    stats[table]["confidence"] = {
                        "avg": round(rows["avg_conf"], 2),
                        "min": round(rows["min_conf"], 2),
                        "max": round(rows["max_conf"], 2),
                    }
            except sqlite3.OperationalError:
                pass
        # last updated
        if table not in ("episodes", "episode_refs"):
            try:
                row = conn.execute(
                    f"SELECT MAX(updated_at) as last FROM {table}"
                ).fetchone()
                if row and row["last"]:
                    stats[table]["last_updated"] = row["last"]
            except sqlite3.OperationalError:
                pass
    return stats
