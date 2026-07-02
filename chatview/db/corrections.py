"""Correction event cache helpers."""

import json
from datetime import datetime

from .core import get_conn, maybe_commit, query_in_chunks


def _session_message_stats(session_ids: list[str]) -> dict:
    if not session_ids:
        return {}
    conn = get_conn()
    rows = query_in_chunks(
        conn,
        """
        SELECT session_id, COUNT(*) AS message_count, MAX(id) AS max_message_id
        FROM messages
        WHERE session_id IN ({placeholders})
        GROUP BY session_id
        """,
        session_ids,
    )
    return {
        r["session_id"]: {
            "message_count": r["message_count"] or 0,
            "max_message_id": r["max_message_id"] or 0,
        }
        for r in rows
    }


def stale_correction_sessions(sessions: list[dict], extractor_version: str) -> list[dict]:
    """Return sessions whose cached correction events are missing or stale."""
    if not sessions:
        return []
    conn = get_conn()
    session_ids = [s["id"] for s in sessions]
    state_rows = query_in_chunks(
        conn,
        """
        SELECT *
        FROM correction_session_state
        WHERE session_id IN ({placeholders})
        """,
        session_ids,
    )
    states = {r["session_id"]: dict(r) for r in state_rows}
    msg_stats = _session_message_stats(session_ids)

    stale = []
    for session in sessions:
        sid = session["id"]
        state = states.get(sid)
        stats = msg_stats.get(sid, {"message_count": 0, "max_message_id": 0})
        if not state:
            stale.append(session)
            continue
        if state.get("extractor_version") != extractor_version:
            stale.append(session)
            continue
        comparisons = (
            ("file_path", session.get("file_path")),
            ("file_size", session.get("file_size")),
            ("file_mtime", session.get("file_mtime")),
            ("user_message_count", session.get("user_message_count")),
            ("message_count", stats.get("message_count")),
            ("max_message_id", stats.get("max_message_id")),
        )
        if any(state.get(key) != value for key, value in comparisons):
            stale.append(session)
    return stale


def replace_correction_events(
    session: dict, events: list[dict], extractor_version: str
) -> None:
    """Replace cached correction events for one session and mark it current."""
    conn = get_conn()
    sid = session["id"]
    conn.execute("DELETE FROM correction_events WHERE session_id=?", (sid,))
    for event in events:
        conn.execute(
            """
            INSERT OR REPLACE INTO correction_events
            (session_id, message_idx, source, kind, date, project, title, text, ai_text,
             signals, ai_confirmed, file_path, extractor_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                sid,
                event.get("message_idx"),
                event.get("source", ""),
                event.get("kind", ""),
                event.get("date", ""),
                event.get("project", ""),
                event.get("title", ""),
                event.get("text", ""),
                event.get("aiText", ""),
                json.dumps(event.get("signals", []), ensure_ascii=False),
                1 if event.get("aiConfirmed") else 0,
                event.get("filePath", ""),
                extractor_version,
            ),
        )
    stats = _session_message_stats([sid]).get(
        sid, {"message_count": 0, "max_message_id": 0}
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO correction_session_state
        (session_id, extractor_version, file_path, file_size, file_mtime, user_message_count,
         message_count, max_message_id, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            sid,
            extractor_version,
            session.get("file_path"),
            session.get("file_size"),
            session.get("file_mtime"),
            session.get("user_message_count"),
            stats.get("message_count"),
            stats.get("max_message_id"),
            datetime.now().isoformat()[:19],
        ),
    )
    maybe_commit(conn)


def query_correction_events(sessions: list[dict], extractor_version: str) -> list[dict]:
    """Return cached correction events for the provided sessions."""
    if not sessions:
        return []
    conn = get_conn()
    session_ids = [s["id"] for s in sessions]
    session_order = {sid: i for i, sid in enumerate(session_ids)}
    rows = query_in_chunks(
        conn,
        """
        SELECT *
        FROM correction_events
        WHERE session_id IN ({placeholders}) AND extractor_version=?
        ORDER BY session_id, message_idx
        """,
        session_ids,
        extra_params=(extractor_version,),
    )
    events = []
    for row in rows:
        signals = []
        try:
            signals = json.loads(row["signals"] or "[]")
        except json.JSONDecodeError:
            signals = []
        item = {
            "sessionId": row["session_id"],
            "title": row["title"] or "",
            "project": row["project"] or "",
            "date": row["date"] or "",
            "text": row["text"] or "",
            "signals": signals,
            "source": row["source"] or "",
            "aiConfirmed": bool(row["ai_confirmed"]),
            "filePath": row["file_path"] or "",
        }
        if row["ai_text"]:
            item["aiText"] = row["ai_text"]
        if row["kind"]:
            item["kind"] = row["kind"]
        item["_sort_session"] = session_order.get(row["session_id"], len(session_order))
        item["_sort_source"] = 0 if row["source"] == "user" else 1
        item["_sort_idx"] = row["message_idx"] or 0
        events.append(item)
    events.sort(key=lambda c: (c["_sort_session"], c["_sort_source"], c["_sort_idx"]))
    events.sort(key=lambda c: c.get("date", ""), reverse=True)
    for event in events:
        event.pop("_sort_session", None)
        event.pop("_sort_source", None)
        event.pop("_sort_idx", None)
    return events
