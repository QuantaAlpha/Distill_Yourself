"""Database connection, schema initialization, and migrations."""

import re
import sqlite3
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache"
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
        conn.execute("PRAGMA busy_timeout=30000")
        _local.conn = conn
    return conn


# ---------------------------------------------------------------------------
# Bulk mode — suppress per-row commits during index rebuilds
# ---------------------------------------------------------------------------
def begin_bulk():
    """Enter bulk mode: maybe_commit() becomes a no-op until end_bulk()."""
    _local.bulk = True


def end_bulk():
    """Exit bulk mode and commit any pending writes."""
    _local.bulk = False
    get_conn().commit()


def bulk_commit():
    """Explicit mid-bulk commit (call periodically to bound transaction size)."""
    get_conn().commit()


def maybe_commit(conn: sqlite3.Connection):
    """Commit unless in bulk mode. Use instead of conn.commit() in CRUD helpers."""
    if not getattr(_local, "bulk", False):
        conn.commit()


# SQLite 限制单条语句的宿主参数个数（旧版默认 999，新版 32766）。会话数很多时
# 直接 IN(?,?,...) 会触发 "too many SQL variables"，因此统一按保守的 900 分批。
_IN_CHUNK_SIZE = 900


def query_in_chunks(
    conn, sql_template, ids, extra_params=(), chunk_size=_IN_CHUNK_SIZE
):
    """对 `IN ({placeholders})` 形式的 SELECT 按 id 分批执行并拼接结果。

    sql_template 必须且仅含一个 `{placeholders}` 占位槽。ids 会被切成多批（避免
    超过 SQLite 宿主参数上限），每批的行拼接返回。SQL 里的 ORDER BY / LIMIT 只对
    单批生效；需要全局排序或截断的调用方必须自行对合并结果再排序 / 截断。
    """
    rows = []
    extra = list(extra_params)
    for i in range(0, len(ids), chunk_size):
        chunk = list(ids[i : i + chunk_size])
        placeholders = ",".join("?" * len(chunk))
        sql = sql_template.format(placeholders=placeholders)
        rows.extend(conn.execute(sql, chunk + extra).fetchall())
    return rows


# ---------------------------------------------------------------------------
# SQL injection defense: whitelist tables/columns/definitions
# ---------------------------------------------------------------------------
_KNOWN_TABLES = frozenset(
    {
        "sessions",
        "messages",
        "evidence_events",
        "judgment_cards",
        "card_relations",
        "cognitive_traits",
        "evolve_cache",
        "aggregates",
        "insight_tool_usage",
        "insight_file_refs",
        "insight_errors",
        "insight_snippets",
        "messages_fts",
        "twin_checkpoints",
        "evolve_runs",
        "chat_cache",
    }
)

_KNOWN_COLUMNS = frozenset(
    {
        # sessions
        "id",
        "title",
        "date",
        "last_date",
        "file_path",
        "file_size",
        "file_mtime",
        "user_message_count",
        "preview",
        "project",
        "project_name",
        "source",
        "starred",
        # evidence_events
        "run_id",
        "session_id",
        "event_index",
        "card_id",
        "task_type",
        "ai_action",
        "user_reaction",
        "resolution",
        "lesson",
        "signal_type",
        "signal_intensity",
        "domain",
        "created_at",
        # judgment_cards
        "applies_when",
        "judgment",
        "agent_action",
        "exceptions",
        "tags",
        "confidence",
        "status",
        "evidence_count",
        "updated_at",
        # cognitive_traits
        "name",
        "category",
        "description",
        "strength",
        "supporting_card_ids",
        # card_relations
        "from_id",
        "to_id",
        "relation",
        # evolve_cache
        "tab",
        "source",
        "date_range",
        "project",
        "engine",
        "data",
        # aggregates
        "key",
        "value",
        # insight_*
        "day",
        "tool_name",
        "count",
        "file_path",
        "error_key",
        "language",
        "code",
        "context",
        "applied",
        # twin_checkpoints / chat_cache
        "stage",
        "started_at",
        "completed_at",
        "prompt_hash",
        "response",
        # evolve_runs
        "lang",
        "status",
        "snapshot",
        "error_message",
        "run_id",
    }
)

_VALID_DEFINITIONS = frozenset(
    {
        "TEXT",
        "INTEGER",
        "REAL",
        "BLOB",
        "TEXT NOT NULL",
        "INTEGER NOT NULL",
        "REAL NOT NULL",
        "TEXT DEFAULT ''",
        "INTEGER DEFAULT 0",
        "REAL DEFAULT 0.0",
    }
)


def _validate_table_name(table: str) -> None:
    """Raise ValueError if table is not in the known whitelist."""
    if table not in _KNOWN_TABLES:
        raise ValueError(f"Unknown or disallowed table: {table!r}")


def _validate_column_name(column: str) -> None:
    """Raise ValueError if column is not in the known whitelist."""
    if column not in _KNOWN_COLUMNS:
        raise ValueError(f"Unknown or disallowed column: {column!r}")


def _validate_column_definition(definition: str) -> None:
    """Raise ValueError if definition is not in the known whitelist."""
    norm = " ".join(definition.strip().upper().split())
    if norm not in _VALID_DEFINITIONS:
        raise ValueError(f"Unknown or disallowed column definition: {definition!r}")


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

        CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
            title,
            project_name,
            content=sessions,
            content_rowid=rowid
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

        -- L1: Evidence Events
        CREATE TABLE IF NOT EXISTS evidence_events (
            id          TEXT PRIMARY KEY,
            run_id      TEXT,
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
            UNIQUE(run_id, session_id, event_index)
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_session ON evidence_events(session_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_domain  ON evidence_events(domain);
        CREATE INDEX IF NOT EXISTS idx_evidence_signal  ON evidence_events(signal_type);
        CREATE INDEX IF NOT EXISTS idx_evidence_card    ON evidence_events(card_id);

        -- L2: Judgment Cards
        CREATE TABLE IF NOT EXISTS judgment_cards (
            id              TEXT PRIMARY KEY,
            run_id          TEXT,
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

        -- L2: Card Relations
        CREATE TABLE IF NOT EXISTS card_relations (
            from_id     TEXT,
            to_id       TEXT,
            relation    TEXT,
            PRIMARY KEY (from_id, to_id, relation),
            FOREIGN KEY (from_id) REFERENCES judgment_cards(id),
            FOREIGN KEY (to_id) REFERENCES judgment_cards(id)
        );

        -- L3: Cognitive Traits
        CREATE TABLE IF NOT EXISTS cognitive_traits (
            id                  TEXT PRIMARY KEY,
            run_id              TEXT,
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

        -- =================================================================
        -- Evolve cache
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

        -- =================================================================
        -- Evolve run/progress tracking
        -- =================================================================
        CREATE TABLE IF NOT EXISTS evolve_runs (
            run_id         TEXT PRIMARY KEY,
            tab            TEXT NOT NULL,
            source         TEXT NOT NULL DEFAULT 'all',
            date_range     TEXT NOT NULL DEFAULT '7d',
            project        TEXT NOT NULL DEFAULT '',
            engine         TEXT NOT NULL DEFAULT 'auto',
            lang           TEXT NOT NULL DEFAULT 'zh',
            status         TEXT NOT NULL DEFAULT 'running',
            snapshot       TEXT NOT NULL DEFAULT '{}',
            error_message  TEXT NOT NULL DEFAULT '',
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            completed_at   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_evolve_runs_scope
            ON evolve_runs(tab, source, date_range, project, engine, updated_at);
        CREATE INDEX IF NOT EXISTS idx_evolve_runs_status
            ON evolve_runs(status, updated_at);

        -- =================================================================
        -- Twin analysis checkpoint tracking
        -- =================================================================
        CREATE TABLE IF NOT EXISTS twin_checkpoints (
            run_id TEXT NOT NULL,
            stage INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            started_at TEXT,
            completed_at TEXT,
            PRIMARY KEY (run_id, stage)
        );

        -- =================================================================
        -- AI Chat response cache
        -- =================================================================
        CREATE TABLE IF NOT EXISTS chat_cache (
            prompt_hash TEXT PRIMARY KEY,
            response TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    _ensure_column(conn, "evidence_events", "run_id", "TEXT")
    _ensure_column(conn, "judgment_cards", "run_id", "TEXT")
    _ensure_column(conn, "cognitive_traits", "run_id", "TEXT")
    _ensure_column(conn, "sessions", "starred", "INTEGER DEFAULT 0")
    _migrate_evidence_run_unique(conn)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence_events(run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_session ON evidence_events(session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_domain ON evidence_events(domain)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_signal ON evidence_events(signal_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_card ON evidence_events(card_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_run ON judgment_cards(run_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_traits_run ON cognitive_traits(run_id)"
    )
    _ensure_sessions_fts(conn)
    conn.commit()
    try:
        from . import evolve as _evolve

        _evolve.migrate_all_legacy_evolve_cache()
    except Exception:
        pass


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str):
    _validate_table_name(table)
    _validate_column_name(column)
    _validate_column_definition(definition)
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_evidence_run_unique(conn: sqlite3.Connection):
    """Replace legacy UNIQUE(session_id,event_index) with run-scoped uniqueness."""
    indexes = conn.execute("PRAGMA index_list(evidence_events)").fetchall()
    has_legacy_unique = False
    for idx in indexes:
        name = idx[1]
        unique = idx[2]
        if not unique:
            continue
        # Guard: index name must be alphanumeric + underscore only
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            continue
        cols = [r[2] for r in conn.execute(f"PRAGMA index_info({name})").fetchall()]
        if cols == ["session_id", "event_index"]:
            has_legacy_unique = True
            break
    if not has_legacy_unique:
        return

    conn.execute("ALTER TABLE evidence_events RENAME TO evidence_events_legacy")
    conn.execute("""
        CREATE TABLE evidence_events (
            id          TEXT PRIMARY KEY,
            run_id      TEXT,
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
            UNIQUE(run_id, session_id, event_index)
        )
    """)
    legacy_cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(evidence_events_legacy)").fetchall()
    }
    select_run = "run_id" if "run_id" in legacy_cols else "NULL AS run_id"
    conn.execute(f"""
        INSERT OR IGNORE INTO evidence_events
        (id, run_id, session_id, event_index, card_id, task_type, ai_action,
         user_reaction, resolution, lesson, signal_type, signal_intensity, domain, created_at)
        SELECT id, {select_run}, session_id, event_index, card_id, task_type, ai_action,
               user_reaction, resolution, lesson, signal_type, signal_intensity, domain, created_at
        FROM evidence_events_legacy
    """)
    conn.execute("DROP TABLE evidence_events_legacy")


def _ensure_sessions_fts(conn: sqlite3.Connection):
    """Populate the title FTS table when migrating an existing cache DB."""
    session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    if session_count == 0:
        return
    # For external-content FTS5 tables, COUNT(*) can read from the content
    # table even when the FTS shadow index is empty. Check docsize instead.
    indexed_count = conn.execute("SELECT COUNT(*) FROM sessions_fts_docsize").fetchone()[0]
    if indexed_count == 0:
        conn.execute("INSERT INTO sessions_fts(sessions_fts) VALUES('rebuild')")
