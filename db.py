"""SQLite storage module — replaces .cache/index.json approach.

Single-file, no classes, thread-local connections, WAL mode.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
DB_PATH = CACHE_DIR / "sessions.db"

_local = threading.local()


def _utc_now() -> datetime:
    """Return current UTC time without timezone suffix for legacy DB strings."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
        -- Insights pre-aggregated tables (incremental via file_mtime)
        -- =================================================================

        -- Tool usage: one row per (session, day, tool)
        CREATE TABLE IF NOT EXISTS insight_tool_usage (
            session_id  TEXT NOT NULL,
            day         TEXT NOT NULL,
            tool_name   TEXT NOT NULL,
            count       INTEGER DEFAULT 1,
            PRIMARY KEY (session_id, day, tool_name),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_tool_usage_day ON insight_tool_usage(day);

        -- File references: one row per (session, file_path)
        CREATE TABLE IF NOT EXISTS insight_file_refs (
            session_id  TEXT NOT NULL,
            file_path   TEXT NOT NULL,
            count       INTEGER DEFAULT 1,
            project     TEXT,
            PRIMARY KEY (session_id, file_path),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_file_refs_path ON insight_file_refs(file_path);

        -- Error occurrences: one row per (session, normalized_error)
        CREATE TABLE IF NOT EXISTS insight_errors (
            session_id  TEXT NOT NULL,
            error_key   TEXT NOT NULL,
            day         TEXT,
            project     TEXT,
            count       INTEGER DEFAULT 1,
            PRIMARY KEY (session_id, error_key),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_errors_key ON insight_errors(error_key);

        -- Snippets: one row per code block
        CREATE TABLE IF NOT EXISTS insight_snippets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            language    TEXT,
            code        TEXT,
            context     TEXT,
            date        TEXT,
            applied     INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_snippets_session ON insight_snippets(session_id);

        -- =================================================================
        -- Cognitive Handbook tables (Digital Twin 4-layer pipeline)
        -- L1: evidence_events  L2: judgment_cards + card_relations
        -- L3: cognitive_traits  L4: runtime pack (computed, not stored)
        -- =================================================================

        -- L1: Evidence Events — structured decision events from conversations
        CREATE TABLE IF NOT EXISTS evidence_events (
            id          TEXT PRIMARY KEY,
            session_id  TEXT,
            event_index INTEGER,
            card_id     TEXT,
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
            FOREIGN KEY (card_id) REFERENCES judgment_cards(id) ON DELETE SET NULL,
            UNIQUE(session_id, event_index)
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_session ON evidence_events(session_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_domain  ON evidence_events(domain);
        CREATE INDEX IF NOT EXISTS idx_evidence_signal  ON evidence_events(signal_type);
        CREATE INDEX IF NOT EXISTS idx_evidence_card    ON evidence_events(card_id);

        -- L2: Judgment Cards — situation-specific judgment patterns
        CREATE TABLE IF NOT EXISTS judgment_cards (
            id              TEXT PRIMARY KEY,
            applies_when    TEXT,
            judgment        TEXT,
            agent_action    TEXT,
            exceptions      TEXT,
            tags            TEXT,
            confidence      REAL,
            status          TEXT DEFAULT 'hypothesis',
            evidence_count  INTEGER DEFAULT 0,
            created_at      TEXT,
            updated_at      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_cards_status ON judgment_cards(status);
        CREATE INDEX IF NOT EXISTS idx_cards_confidence ON judgment_cards(confidence);

        -- L2: Card Relations — lightweight relationship tracking between cards
        CREATE TABLE IF NOT EXISTS card_relations (
            from_id     TEXT,
            to_id       TEXT,
            relation    TEXT,
            PRIMARY KEY (from_id, to_id, relation),
            FOREIGN KEY (from_id) REFERENCES judgment_cards(id),
            FOREIGN KEY (to_id) REFERENCES judgment_cards(id)
        );

        -- L3: Cognitive Traits — personality/cognitive characteristics inferred from cards
        CREATE TABLE IF NOT EXISTS cognitive_traits (
            id                  TEXT PRIMARY KEY,
            name                TEXT,
            category            TEXT,
            description         TEXT,
            strength            REAL,
            supporting_card_ids TEXT,
            status              TEXT DEFAULT 'hypothesis',
            evidence_count      INTEGER DEFAULT 0,
            updated_at          TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_traits_category ON cognitive_traits(category);
        CREATE INDEX IF NOT EXISTS idx_traits_status ON cognitive_traits(status);

        -- Twin analysis run checkpoints for interactive timeout recovery.
        CREATE TABLE IF NOT EXISTS twin_runs (
            run_id          TEXT PRIMARY KEY,
            scope_json      TEXT,
            start_stage     INTEGER DEFAULT 1,
            current_stage   INTEGER DEFAULT 1,
            status          TEXT,
            stage_meta_json TEXT,
            last_error      TEXT,
            started_at      TEXT,
            updated_at      TEXT,
            finished_at     TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_twin_runs_updated ON twin_runs(updated_at);
        CREATE INDEX IF NOT EXISTS idx_twin_runs_status ON twin_runs(status);

        -- =================================================================
        -- Evolve cache — single source of truth for AI-generated tab data
        -- =================================================================
        CREATE TABLE IF NOT EXISTS evolve_cache (
            tab         TEXT NOT NULL,
            source      TEXT NOT NULL DEFAULT 'all',
            date_range  TEXT NOT NULL DEFAULT '7d',
            project     TEXT NOT NULL DEFAULT '',
            engine      TEXT NOT NULL DEFAULT 'auto',
            data        TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            PRIMARY KEY (tab, source, date_range, project, engine)
        );
        CREATE INDEX IF NOT EXISTS idx_evolve_tab     ON evolve_cache(tab);
        CREATE INDEX IF NOT EXISTS idx_evolve_updated  ON evolve_cache(updated_at);
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
        cutoff = (_utc_now() - timedelta(days=max_days)).strftime("%Y-%m-%d")
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
    now = _utc_now().isoformat()
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
# Insight tables — CRUD helpers
# ---------------------------------------------------------------------------
def clear_session_insights(session_id: str):
    """Delete all insight rows for a session (before re-extraction)."""
    conn = get_conn()
    for table in ("insight_tool_usage", "insight_file_refs", "insight_errors", "insight_snippets"):
        conn.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
    conn.commit()


def bulk_insert_tool_usage(rows: list):
    """Insert rows: [(session_id, day, tool_name, count), ...]"""
    if not rows:
        return
    conn = get_conn()
    conn.executemany(
        "INSERT OR REPLACE INTO insight_tool_usage (session_id, day, tool_name, count) VALUES (?,?,?,?)",
        rows,
    )
    conn.commit()


def bulk_insert_file_refs(rows: list):
    """Insert rows: [(session_id, file_path, count, project), ...]"""
    if not rows:
        return
    conn = get_conn()
    conn.executemany(
        "INSERT OR REPLACE INTO insight_file_refs (session_id, file_path, count, project) VALUES (?,?,?,?)",
        rows,
    )
    conn.commit()


def bulk_insert_errors(rows: list):
    """Insert rows: [(session_id, error_key, day, project, count), ...]"""
    if not rows:
        return
    conn = get_conn()
    conn.executemany(
        "INSERT OR REPLACE INTO insight_errors (session_id, error_key, day, project, count) VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()


def bulk_insert_snippets(rows: list):
    """Insert rows: [(session_id, language, code, context, date, applied), ...]"""
    if not rows:
        return
    conn = get_conn()
    conn.executemany(
        "INSERT INTO insight_snippets (session_id, language, code, context, date, applied) VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()


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
    rows = conn.execute("""
        SELECT file_path,
               SUM(count) as total_count,
               COUNT(DISTINCT session_id) as session_count,
               GROUP_CONCAT(DISTINCT project) as projects
        FROM insight_file_refs
        GROUP BY file_path
        ORDER BY total_count DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def query_error_patterns(limit=30):
    """Return top error patterns aggregated across sessions."""
    conn = get_conn()
    rows = conn.execute("""
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
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def query_snippets(limit=150):
    """Return code snippets sorted by applied first, then newest."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT s.session_id, ses.title as session_title, ses.project_name as project,
               s.language, s.code, s.context, s.date, s.applied
        FROM insight_snippets s
        LEFT JOIN sessions ses ON ses.id = s.session_id
        ORDER BY s.applied DESC, s.date DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Cognitive Model — CRUD helpers
# ---------------------------------------------------------------------------

# Table registry: name → columns (excluding id, updated_at which are auto-managed)
_CM_TABLES = {
    "evidence_events": ["session_id", "event_index", "card_id", "task_type",
                        "ai_action", "user_reaction", "resolution", "lesson",
                        "signal_type", "signal_intensity", "domain", "created_at"],
    "judgment_cards": ["applies_when", "judgment", "agent_action", "exceptions",
                       "tags", "confidence", "status", "evidence_count", "created_at"],
    "card_relations": ["from_id", "to_id", "relation"],
    "cognitive_traits": ["name", "category", "description", "strength",
                         "supporting_card_ids", "status", "evidence_count"],
}


def cm_upsert(table: str, item_id: str, data: dict, commit: bool = True):
    """Insert or update a cognitive model row. Partial updates are safe — existing
    fields are preserved when not provided in data."""
    conn = get_conn()
    cols = _CM_TABLES.get(table)
    if not cols:
        raise ValueError(f"Unknown CM table: {table}")

    now = _utc_now().isoformat()
    has_updated = table not in ("evidence_events", "card_relations")

    # Auto-fill created_at on insert for tables that have it
    if "created_at" in cols and "created_at" not in data:
        data = {**data, "created_at": now}

    # Check if row exists — if so, merge with existing data to avoid dropping fields
    existing = conn.execute(f"SELECT * FROM {table} WHERE id=?", (item_id,)).fetchone()
    if existing:
        merged = dict(existing)
        merged.update({k: v for k, v in data.items() if v is not None})
        if has_updated:
            merged["updated_at"] = now
        all_cols = [c for c in ["id"] + cols + (["updated_at"] if has_updated else []) if c in merged]
        vals = [merged[c] for c in all_cols]
        update_cols = [c for c in all_cols if c != "id"]
        if update_cols:
            assignments = ",".join(f"{c}=?" for c in update_cols)
            conn.execute(
                f"UPDATE {table} SET {assignments} WHERE id=?",
                [merged[c] for c in update_cols] + [item_id],
            )
    else:
        if table == "evidence_events":
            session_id = data.get("session_id")
            event_index = data.get("event_index")
            if session_id is not None and event_index is not None:
                conflict = conn.execute(
                    "SELECT id FROM evidence_events WHERE session_id=? AND event_index=?",
                    (session_id, event_index),
                ).fetchone()
                if conflict and conflict["id"] != item_id:
                    raise ValueError(
                        "evidence event already exists for "
                        f"session_id={session_id!r}, event_index={event_index!r}: {conflict['id']}"
                    )
        all_cols = ["id"] + [c for c in cols if c in data]
        if has_updated:
            all_cols.append("updated_at")
        vals = [item_id] + [data.get(c) for c in cols if c in data]
        if has_updated:
            vals.append(now)
        placeholders = ",".join("?" * len(all_cols))
        col_str = ",".join(all_cols)
        conn.execute(
            f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})",
            vals,
        )
    if commit:
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


def cm_add_card_relation(from_id: str, to_id: str, relation: str):
    """Add a relation between two judgment cards."""
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO card_relations (from_id, to_id, relation) "
        "VALUES (?,?,?)",
        (from_id, to_id, relation),
    )
    conn.commit()


def cm_get_evidence_for_card(card_id: str) -> list:
    """Get all evidence events linked to a judgment card."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM evidence_events WHERE card_id=? ORDER BY created_at DESC",
        (card_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def cm_get_card_relations(card_id: str) -> list:
    """Get all relations involving a card (as source or target)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM card_relations WHERE from_id=? OR to_id=?",
        (card_id, card_id),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Twin run checkpoints
# ---------------------------------------------------------------------------
def twin_run_upsert(run_id: str, scope: dict, start_stage: int = 1,
                    current_stage: int = 1, status: str = "running",
                    stage_meta: Optional[dict] = None, last_error: str = "",
                    finished_at: str = ""):
    """Insert or update a Twin analysis run checkpoint."""
    conn = get_conn()
    now = _utc_now().isoformat()
    existing = conn.execute(
        "SELECT started_at, stage_meta_json FROM twin_runs WHERE run_id=?",
        (run_id,),
    ).fetchone()
    started_at = existing["started_at"] if existing else now
    if stage_meta is None and existing:
        stage_meta_json = existing["stage_meta_json"] or "{}"
    else:
        stage_meta_json = json.dumps(stage_meta or {}, ensure_ascii=False)
    conn.execute(
        """INSERT INTO twin_runs
           (run_id, scope_json, start_stage, current_stage, status, stage_meta_json,
            last_error, started_at, updated_at, finished_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(run_id) DO UPDATE SET
             scope_json=excluded.scope_json,
             start_stage=excluded.start_stage,
             current_stage=excluded.current_stage,
             status=excluded.status,
             stage_meta_json=excluded.stage_meta_json,
             last_error=excluded.last_error,
             updated_at=excluded.updated_at,
             finished_at=excluded.finished_at""",
        (
            run_id,
            json.dumps(scope or {}, ensure_ascii=False),
            int(start_stage),
            int(current_stage),
            status,
            stage_meta_json,
            last_error or "",
            started_at,
            now,
            finished_at or "",
        ),
    )
    conn.commit()


def twin_run_update_stage(run_id: str, current_stage: int = None,
                          status: str = None, stage_meta: Optional[dict] = None,
                          last_error: str = None, finished: bool = False):
    """Update mutable Twin run fields."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM twin_runs WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        raise ValueError(f"Twin run not found: {run_id}")
    meta = {}
    if row["stage_meta_json"]:
        try:
            meta = json.loads(row["stage_meta_json"])
        except Exception:
            meta = {}
    if stage_meta:
        meta.update(stage_meta)
    now = _utc_now().isoformat()
    conn.execute(
        """UPDATE twin_runs
           SET current_stage=?, status=?, stage_meta_json=?, last_error=?,
               updated_at=?, finished_at=?
           WHERE run_id=?""",
        (
            int(current_stage if current_stage is not None else row["current_stage"]),
            status if status is not None else row["status"],
            json.dumps(meta, ensure_ascii=False),
            last_error if last_error is not None else row["last_error"],
            now,
            now if finished else row["finished_at"],
            run_id,
        ),
    )
    conn.commit()


def _row_to_twin_run(row) -> Optional[dict]:
    if not row:
        return None
    out = dict(row)
    try:
        out["scope"] = json.loads(out.pop("scope_json") or "{}")
    except Exception:
        out["scope"] = {}
    try:
        out["stage_meta"] = json.loads(out.pop("stage_meta_json") or "{}")
    except Exception:
        out["stage_meta"] = {}
    return out


def twin_run_get(run_id: str) -> Optional[dict]:
    """Return one persisted Twin run."""
    conn = get_conn()
    return _row_to_twin_run(conn.execute("SELECT * FROM twin_runs WHERE run_id=?", (run_id,)).fetchone())


def twin_run_latest() -> Optional[dict]:
    """Return the most recently updated Twin run."""
    conn = get_conn()
    return _row_to_twin_run(conn.execute("SELECT * FROM twin_runs ORDER BY updated_at DESC LIMIT 1").fetchone())


def get_twin_stats() -> dict:
    """Return cognitive handbook statistics."""
    conn = get_conn()
    stats = {}
    _CONF_TABLES = {"judgment_cards", "cognitive_traits"}
    _UPDATED_TABLES = {"judgment_cards", "cognitive_traits"}
    for table in _CM_TABLES:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        stats[table] = {"count": count}
        if table in _CONF_TABLES:
            try:
                conf_col = "confidence" if table == "judgment_cards" else "strength"
                rows = conn.execute(
                    f"SELECT AVG({conf_col}) as avg_conf, "
                    f"MIN({conf_col}) as min_conf, MAX({conf_col}) as max_conf "
                    f"FROM {table} WHERE {conf_col} IS NOT NULL"
                ).fetchone()
                if rows and rows["avg_conf"] is not None:
                    stats[table]["confidence"] = {
                        "avg": round(rows["avg_conf"], 2),
                        "min": round(rows["min_conf"], 2),
                        "max": round(rows["max_conf"], 2),
                    }
            except sqlite3.OperationalError:
                pass
        if table in _UPDATED_TABLES:
            try:
                row = conn.execute(
                    f"SELECT MAX(updated_at) as last FROM {table}"
                ).fetchone()
                if row and row["last"]:
                    stats[table]["last_updated"] = row["last"]
            except sqlite3.OperationalError:
                pass
    return stats


# ---------------------------------------------------------------------------
# Evolve cache
# ---------------------------------------------------------------------------
def evolve_upsert(tab: str, source: str, date_range: str, project: str,
                  engine: str, data_json: str):
    """Insert or replace evolve tab data for a given scope."""
    conn = get_conn()
    now = _utc_now().isoformat()
    conn.execute("""
        INSERT INTO evolve_cache (tab, source, date_range, project, engine,
                                  data, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tab, source, date_range, project, engine)
        DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at
    """, (tab, source or "all", date_range or "7d", project or "",
          engine or "auto", data_json, now, now))
    conn.commit()


def evolve_get(tab: str, source: str, date_range: str, project: str,
               engine: str) -> Optional[dict]:
    """Return {data, updated_at} for an exact scope, or None."""
    conn = get_conn()
    row = conn.execute("""
        SELECT data, updated_at FROM evolve_cache
        WHERE tab=? AND source=? AND date_range=? AND project=? AND engine=?
    """, (tab, source or "all", date_range or "7d", project or "",
          engine or "auto")).fetchone()
    if row:
        return {"data": json.loads(row["data"]), "updated_at": row["updated_at"]}
    return None


def evolve_latest(tab: str) -> Optional[dict]:
    """Return most recent data for a tab regardless of scope (for Twin)."""
    conn = get_conn()
    row = conn.execute("""
        SELECT data, updated_at FROM evolve_cache
        WHERE tab=? ORDER BY updated_at DESC LIMIT 1
    """, (tab,)).fetchone()
    if row:
        return {"data": json.loads(row["data"]), "updated_at": row["updated_at"]}
    return None
