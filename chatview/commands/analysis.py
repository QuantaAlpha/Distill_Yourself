"""Core analysis commands: sessions, read, search, queries, stats, files."""

import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from chatview import index as _idx
from chatview.index import build_index
from chatview.session_loader import load_session_from_file
from chatview.parsers.codex import _CODEX_TOOL_NAMES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_index():
    """Build index silently (suppress print statements)."""
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        build_index()
    finally:
        sys.stdout = old


def cmd_refresh(args):
    """Force a re-index: scan JSONL, rebuild SQLite + aggregates.

    Mirrors the web app's /api/refresh. Run this before commands that only
    read the SQLite cache (aggregates / profile-digest) when sessions may
    have changed since the last index.
    """
    want_json = getattr(args, "json", False)
    force = getattr(args, "force", False)
    if want_json:
        # build_index() prints progress to stdout — suppress it so --json
        # output stays pure JSON that json.loads() can consume.
        old = sys.stdout
        sys.stdout = io.StringIO()
        try:
            index = build_index(force=force)
        finally:
            sys.stdout = old
    else:
        index = build_index(force=force)

    summary = {
        "sessions": len(index.get("sessions", {})),
        "projects": len(index.get("projects", {})),
    }
    if want_json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"OK: index refreshed — {summary['sessions']} sessions")


def cmd_install_skill(args):
    """Copy the bundled distill-yourself skill into Claude Code (and Codex) skills dir.

    Source is shipped alongside the package at <root>/skills/distill-yourself.
    Targets: ~/.claude/skills/distill-yourself, and ~/.codex/skills/distill-yourself
    if ~/.codex exists. Pass --force to overwrite an existing copy.
    """
    import shutil

    src = Path(__file__).resolve().parents[2] / "skills" / "distill-yourself"
    if not src.is_dir():
        print(f"ERROR: bundled skill not found at {src}", file=sys.stderr)
        sys.exit(1)

    targets = [Path.home() / ".claude" / "skills" / "distill-yourself"]
    if (Path.home() / ".codex").is_dir():
        targets.append(Path.home() / ".codex" / "skills" / "distill-yourself")

    force = getattr(args, "force", False)
    for dst in targets:
        if dst.exists():
            if not force:
                print(f"SKIP: {dst} already exists (use --force to overwrite)")
                continue
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        print(f"OK: installed skill -> {dst}")


def _apply_filters(sessions: dict, args) -> dict:
    """Filter sessions by date/source/project from CLI args."""
    filtered = {}
    now = datetime.now()
    days_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}

    for sid, m in sessions.items():
        # Source
        if args.source and args.source != "all":
            if m.get("source", "claude") != args.source:
                continue
        # Project
        if args.project:
            if args.project.lower() not in m.get("projectName", "").lower():
                continue
        # Date
        if args.date and args.date != "all":
            date_str = m.get("date", "")
            if date_str:
                try:
                    d = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    max_days = days_map.get(args.date, 9999)
                    if (now - d).total_seconds() > max_days * 86400:
                        continue
                except Exception:
                    pass
        filtered[sid] = m
    return filtered


def _get_filtered(args) -> dict:
    """Build index + apply filters."""
    _init_index()
    with _idx._index_lock:
        sessions = dict(_idx._index.get("sessions", {}))
    return _apply_filters(sessions, args)


def _get_filtered_db(args) -> list:
    """Return filtered sessions from SQLite DB as a list of dicts."""
    from chatview import db as _db
    _db.init_db()
    days_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
    max_days = days_map.get(getattr(args, "date", ""), 99999)
    return _db.get_filtered_sessions(
        source=getattr(args, "source", "all"),
        project=getattr(args, "project", ""),
        max_days=max_days,
    )


def _get_messages_db(args, role="user", limit=99999) -> list:
    """Return messages for filtered sessions from SQLite DB."""
    from chatview import db as _db
    sessions = _get_filtered_db(args)
    if not sessions:
        return []
    sids = [s["id"] for s in sessions]
    conn = _db.get_conn()
    # 会话数可能超过 SQLite 宿主参数上限，按 id 分批查询。每批的 ORDER BY/LIMIT 只对
    # 单批生效，因此合并后再做全局排序（ts 降序）并截断到 limit。
    rows = _db.query_in_chunks(conn, """
        SELECT m.text, m.ts, m.role, m.idx, s.project_name, s.source, s.id AS session_id,
               s.title
        FROM messages m JOIN sessions s ON m.session_id = s.id
        WHERE m.session_id IN ({placeholders}) AND m.role = ?
        ORDER BY m.ts DESC LIMIT ?
    """, sids, extra_params=(role, limit))
    result = [dict(r) for r in rows]
    result.sort(key=lambda r: r.get("ts") or "", reverse=True)
    return result[:limit]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_sessions(args):
    """List sessions matching filters."""
    db_sessions = _get_filtered_db(args)
    total = len(db_sessions)
    items = db_sessions[:args.limit]

    if args.json:
        out = [{
            "id": m.get("id", ""), "title": m.get("title", ""),
            "project": m.get("project_name", ""), "source": m.get("source", "claude"),
            "date": (m.get("date") or "")[:19], "messages": m.get("user_message_count", 0),
            "fileSize": m.get("file_size", 0), "filePath": m.get("file_path", ""),
        } for m in items]
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"Found {total} sessions (showing {len(items)}):\n")
        for m in items:
            src = (m.get("source") or "claude")[:3]
            date = (m.get("date") or "")[:10]
            title = (m.get("title") or "Untitled")[:55]
            msgs = m.get("user_message_count") or 0
            sid = m.get("id", "")
            print(f"  [{src}] {date} {title:55s} {msgs:3d}msg  id:{sid}")


def cmd_read(args):
    """Read a session in human-readable format."""
    from chatview import db as _db
    _db.init_db()

    session_id = args.session
    summary_mode = getattr(args, "summary", False)

    # Resolve session meta from DB (supports partial ID match)
    meta = _db.get_session_meta(session_id)
    if not meta:
        print(f"Session not found: {session_id}", file=sys.stderr)
        sys.exit(1)

    sid = meta["id"]
    title = meta.get("title") or "Untitled"
    project = meta.get("project_name") or ""
    date = (meta.get("date") or "")[:19]

    # Summary mode: read directly from DB messages (no JSONL needed)
    if summary_mode:
        messages = _db.get_session_messages(sid)
        turns = []
        for msg in messages:
            role = msg.get("role", "")
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            ts = (msg.get("ts") or "")[:16]
            if role == "user":
                turns.append((0, f"\n--- USER [{ts}] ---\n{text[:600]}"))
            elif role == "assistant":
                turns.append((1, f"\n--- ASSISTANT ---\n{text[:600]}"))

        header = f"# {title}\n# {project} | {date} | {len(messages)} messages (summary)"
        output = [header]
        used = len(header)
        max_chars = 12000

        for priority, text in turns:
            if used + len(text) > max_chars:
                text = text[:max(200, max_chars - used)] + "\n[...]"
            output.append(text)
            used += len(text)
            if used > max_chars:
                output.append(f"\n[TRUNCATED — {used} chars shown]")
                break

        print("\n".join(output))
        return

    # Full mode: load from JSONL file (need tool details)
    filepath = meta.get("file_path", "")
    if not filepath or not os.path.exists(filepath):
        print(f"Session file not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    data = load_session_from_file(filepath, sid, title, project, date)
    if not data:
        print(f"Failed to load session: {session_id}", file=sys.stderr)
        sys.exit(1)

    # Smart truncation: keep user messages + assistant text, fold tools
    turns = []
    tool_batch = []

    def flush_tools():
        if tool_batch:
            names = {}
            for t in tool_batch:
                names[t] = names.get(t, 0) + 1
            summary = ", ".join(f"{n}×{c}" if c > 1 else n for n, c in names.items())
            turns.append((2, f"  [tools: {summary}]"))
            tool_batch.clear()

    for msg in data.get("messages", []):
        msg_type = msg.get("type", "")
        content = msg.get("content", [])

        if msg_type == "user":
            flush_tools()
            texts = [b.get("text", "") for b in content if b.get("type") == "text"]
            text = "\n".join(t for t in texts if t.strip())
            if text.strip():
                ts = msg.get("timestamp", "")[:16] if msg.get("timestamp") else ""
                turns.append((0, f"\n--- USER [{ts}] ---\n{text[:600]}"))

        elif msg_type == "assistant":
            for b in content:
                if b.get("type") == "text" and b.get("text", "").strip():
                    flush_tools()
                    turns.append((1, f"\n--- ASSISTANT ---\n{b['text'][:1200]}"))
                elif b.get("type") == "tool_use":
                    tool_batch.append(b.get("name", "?"))
                elif b.get("type") == "thinking":
                    tool_batch.append("thinking")

        elif msg_type == "tool_result":
            pass

    flush_tools()

    max_chars = 12000
    header = f"# {title}\n# {project} | {date} | {len(data.get('messages', []))} messages"
    output = [header]
    used = len(header)

    for priority, text in turns:
        if used + len(text) > max_chars:
            if priority == 2:
                continue
            text = text[:max(200, max_chars - used)] + "\n[...]"
        output.append(text)
        used += len(text)
        if used > max_chars and priority > 0:
            output.append(f"\n[TRUNCATED — showing {used}/{sum(len(t) for _, t in turns)} chars, tools folded]")
            break

    print("\n".join(output))


def cmd_search(args):
    """Search user messages across sessions (via FTS)."""
    from chatview import db as _db
    _db.init_db()

    # Use FTS for the core search
    fts_results = _db.search_fts(args.query, limit=500)

    # Apply CLI filters (source/project/date)
    now = datetime.now()
    days_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
    out = []

    for r in fts_results:
        if args.source and args.source != "all":
            if (r.get("source") or "claude") != args.source:
                continue
        if args.project and args.project.lower() not in (r.get("project_name") or "").lower():
            continue
        if args.date and args.date != "all":
            date_str = r.get("ts") or ""
            if date_str:
                try:
                    d = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    if (now - d).days > days_map.get(args.date, 9999):
                        continue
                except Exception:
                    pass

        # Build output record
        text = r.get("text", "")
        snippet = text[:200] if text else ""
        out.append({
            "sessionId": r.get("session_id", ""),
            "title": r.get("title", ""),
            "project": r.get("project_name", ""),
            "date": (r.get("ts") or "")[:19],
            "messageIndex": r.get("idx", 0),
            "snippet": snippet,
            "matchType": r.get("role", "content"),
            "score": 0,
        })

    if args.json:
        print(json.dumps(out[:args.limit], ensure_ascii=False, indent=2))
    else:
        print(f"Found {len(out)} matches for '{args.query}':\n")
        for r in out[:args.limit]:
            date = r.get("date", "")[:10]
            print(f"  [{date}] {r.get('title', '')[:60]}")
            print(f"  {r.get('project', '')} · match: {r.get('matchType', '')}")
            print(f"  > {r.get('snippet', '')[:200]}")
            print(f"  session: {r.get('sessionId', '')}")
            print()


def cmd_queries(args):
    """Extract user queries/messages only — across sessions or from one session."""
    # Single session mode
    if args.session:
        from chatview import db as _db
        _db.init_db()
        meta = _db.get_session_meta(args.session)
        if not meta:
            print(f"Session not found: {args.session}", file=sys.stderr)
            sys.exit(1)

        user_msgs = _db.get_session_messages(meta["id"], role="user")
        title = meta.get("title") or "Untitled"
        print(f"# User queries from: {title}")
        print(f"# {len(user_msgs)} messages\n")
        for i, msg in enumerate(user_msgs):
            ts = (msg.get("ts") or "")[:19]
            text = msg.get("text", "")
            if args.keyword and args.keyword.lower() not in text.lower():
                continue
            print(f"[{i+1}] {ts}")
            print(text[:500])
            print()
        return

    # Cross-session mode: extract all user queries
    # Try DB first; fall back to old method if DB is empty
    db_rows = _get_messages_db(args, role="user", limit=99999)
    if db_rows:
        all_queries = []
        for row in db_rows:
            text = row.get("text", "")
            if len(text) < 3:
                continue
            if text.strip().startswith(("<", "{", "```")):
                continue
            if args.keyword and args.keyword.lower() not in text.lower():
                continue
            all_queries.append({
                "sessionId": row.get("session_id", ""),
                "title": row.get("title", "")[:50],
                "project": row.get("project_name", ""),
                "source": row.get("source", "claude"),
                "date": (row.get("ts") or "")[:16],
                "text": text[:400],
            })
    else:
        filtered = _get_filtered(args)
        items = sorted(filtered.values(), key=lambda m: m.get("date", ""), reverse=True)
        all_queries = []
        for m in items:
            sid = m.get("id", "")
            title = m.get("title", "")[:50]
            project = m.get("projectName", "")
            source = m.get("source", "claude")
            for ut in m.get("userTexts", []):
                text = ut.get("text", "")
                if len(text) < 3:
                    continue
                if text.strip().startswith(("<", "{", "```")):
                    continue
                if args.keyword and args.keyword.lower() not in text.lower():
                    continue
                all_queries.append({
                    "sessionId": sid,
                    "title": title,
                    "project": project,
                    "source": source,
                    "date": ut.get("ts", "")[:16],
                    "text": text[:400],
                })

    all_queries.sort(key=lambda q: q.get("date", ""), reverse=True)
    shown = all_queries[:args.limit]

    if args.json:
        print(json.dumps(shown, ensure_ascii=False, indent=2))
    else:
        print(f"Found {len(all_queries)} user queries (showing {len(shown)}):\n")
        for q in shown:
            text = q['text'][:150].replace('\n', ' ')
            print(f"  [{q['date']}] {q['project']} | {text}")
            print(f"    sid:{q['sessionId']}")


def cmd_stats(args):
    """Show aggregate statistics."""
    # Try DB first; fall back to old method if DB is empty
    db_sessions = _get_filtered_db(args)
    if db_sessions:
        total = len(db_sessions)
        proj_counts = {}
        src_counts = {}
        total_msgs = 0
        total_size = 0
        dates = []
        for s in db_sessions:
            pname = s.get("project_name") or "unknown"
            proj_counts[pname] = proj_counts.get(pname, 0) + 1
            src = s.get("source", "claude")
            src_counts[src] = src_counts.get(src, 0) + 1
            total_msgs += s.get("user_message_count") or 0
            total_size += s.get("file_size") or 0
            if s.get("date"):
                dates.append(s["date"][:10])
    else:
        filtered = _get_filtered(args)
        total = len(filtered)
        if total == 0:
            print("No sessions match the filters.")
            return
        proj_counts = {}
        src_counts = {}
        total_msgs = 0
        total_size = 0
        dates = []
        for sid, m in filtered.items():
            pname = m.get("projectName", "unknown")
            proj_counts[pname] = proj_counts.get(pname, 0) + 1
            src = m.get("source", "claude")
            src_counts[src] = src_counts.get(src, 0) + 1
            total_msgs += m.get("userMessageCount", 0)
            total_size += m.get("fileSize", 0)
            if m.get("date"):
                dates.append(m["date"][:10])

    if total == 0:
        print("No sessions match the filters.")
        return

    dates.sort()

    print("=== Statistics ===\n")
    print(f"  Sessions:       {total}")
    print(f"  User messages:  {total_msgs}")
    print(f"  Data size:      {total_size / 1048576:.1f} MB")
    if dates:
        print(f"  Date range:     {dates[0]} → {dates[-1]}")

    print("\nBy source:")
    for src, count in sorted(src_counts.items(), key=lambda x: -x[1]):
        print(f"  {src:8s} {count:5d} sessions")

    top_n = min(args.limit, len(proj_counts))
    print(f"\nBy project (top {top_n}):")
    for pname, count in sorted(proj_counts.items(), key=lambda x: -x[1])[:top_n]:
        pct = count / total * 100
        print(f"  {pname:40s} {count:4d} ({pct:.0f}%)")


def _data_files(args):
    """Compute file data and return as a list of dicts (sorted by edits+writes desc)."""
    filtered = _get_filtered(args)

    file_freq = {}

    for sid, meta in filtered.items():
        fp = meta.get("filePath", "")
        source = meta.get("source", "claude")
        if not fp or not os.path.exists(fp):
            continue
        # Codex uses different tool formats — basic support via function_call args
        is_codex = source == "codex"

        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Claude tool_use blocks
                    if not is_codex and obj.get("type") == "assistant":
                        content = obj.get("message", {}).get("content", [])
                        if not isinstance(content, list):
                            continue
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                name = block.get("name", "")
                                inp = block.get("input", {})
                                path = inp.get("file_path") or inp.get("path") or ""
                                if path and not path.startswith("/tmp"):
                                    home = str(Path.home())
                                    short = path.replace(home, "~") if path.startswith(home) else path
                                    if short not in file_freq:
                                        file_freq[short] = {"count": 0, "sessions": set(),
                                                            "edits": 0, "reads": 0, "writes": 0}
                                    file_freq[short]["count"] += 1
                                    file_freq[short]["sessions"].add(sid)
                                    if name in ("Read", "Glob", "Grep"):
                                        file_freq[short]["reads"] += 1
                                    elif name in ("Edit", "MultiEdit"):
                                        file_freq[short]["edits"] += 1
                                    elif name == "Write":
                                        file_freq[short]["writes"] += 1

                    # Codex function_call blocks
                    if is_codex and obj.get("type") == "response_item":
                        payload = obj.get("payload", {})
                        if payload.get("type") in ("function_call", "custom_tool_call"):
                            raw_name = payload.get("name", "")
                            name = _CODEX_TOOL_NAMES.get(raw_name, raw_name)
                            args_str = payload.get("arguments", "{}")
                            try:
                                tool_args = json.loads(args_str) if isinstance(args_str, str) else {}
                            except json.JSONDecodeError:
                                tool_args = {}
                            path = tool_args.get("file_path") or tool_args.get("path") or ""
                            if path and not path.startswith("/tmp"):
                                home = str(Path.home())
                                short = path.replace(home, "~") if path.startswith(home) else path
                                if short not in file_freq:
                                    file_freq[short] = {"count": 0, "sessions": set(),
                                                        "edits": 0, "reads": 0, "writes": 0}
                                file_freq[short]["count"] += 1
                                file_freq[short]["sessions"].add(sid)
                                if name in ("Read", "Glob", "Grep"):
                                    file_freq[short]["reads"] += 1
                                elif name in ("Edit", "MultiEdit"):
                                    file_freq[short]["edits"] += 1
                                elif name == "Write":
                                    file_freq[short]["writes"] += 1
        except Exception:
            continue

    sorted_files = sorted(file_freq.items(), key=lambda x: -(x[1]["edits"] + x[1]["writes"]))
    return [{"path": fp, **{k: v if not isinstance(v, set) else len(v) for k, v in data.items()}}
            for fp, data in sorted_files]


def cmd_files(args):
    """Show most-edited files across sessions."""
    files = _data_files(args)
    shown = files[:args.limit]
    if args.json:
        print(json.dumps(shown, ensure_ascii=False, indent=2))
    else:
        print(f"Top edited files ({len(files)} total):\n")
        for data in shown:
            print(f"  {data['path']}")
            print(f"    edits={data['edits']}  writes={data['writes']}  reads={data['reads']}  sessions={data['sessions']}")
            print()
