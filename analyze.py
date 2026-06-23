#!/usr/bin/env python3
"""CLI tools for analyzing Claude Code / Codex conversation history.

Designed to be called by AI agents (Codex CLI, Claude Code) for efficient
data extraction from JSONL session files. Reuses server.py parsing logic.

Usage:
  python3 analyze.py <command> [options]

Commands:
  sessions      List sessions matching filters
  read          Read a session conversation (human-readable, -s for summary)
  search        Search user messages across sessions
  queries       Extract user messages only (--session for single, -k for keyword)
  corrections   Find user correction patterns (→ CLAUDE.md rules)
  decisions     Extract decision points from conversations
  errors        Extract error patterns from tool results
  stats         Show aggregate statistics
  files         Show most-edited files across sessions
  highlights    Per-session one-line summaries with correction/decision counts
"""

import argparse
import json
import os
import re
import sys
import io
from datetime import datetime
from pathlib import Path

# Import shared logic from server.py (same directory)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_index():
    """Build index silently (suppress server.py print statements)."""
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        server.build_index()
    finally:
        sys.stdout = old


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
    with server._index_lock:
        sessions = dict(server._index.get("sessions", {}))
    return _apply_filters(sessions, args)


def _get_filtered_db(args) -> list:
    """Return filtered sessions from SQLite DB as a list of dicts."""
    import db as _db
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
    import db as _db
    sessions = _get_filtered_db(args)
    if not sessions:
        return []
    sids = [s["id"] for s in sessions]
    conn = _db.get_conn()
    placeholders = ",".join("?" * len(sids))
    rows = conn.execute(f"""
        SELECT m.text, m.ts, m.role, m.idx, s.project_name, s.source, s.id AS session_id,
               s.title
        FROM messages m JOIN sessions s ON m.session_id = s.id
        WHERE m.session_id IN ({placeholders}) AND m.role = ?
        ORDER BY m.ts DESC LIMIT ?
    """, sids + [role, limit]).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_sessions(args):
    """List sessions matching filters."""
    filtered = _get_filtered(args)
    items = sorted(filtered.values(), key=lambda m: m.get("date", ""), reverse=True)
    items = items[:args.limit]

    if args.json:
        out = [{
            "id": m.get("id", ""), "title": m.get("title", ""),
            "project": m.get("projectName", ""), "source": m.get("source", "claude"),
            "date": m.get("date", "")[:19], "messages": m.get("userMessageCount", 0),
            "fileSize": m.get("fileSize", 0), "filePath": m.get("filePath", ""),
        } for m in items]
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"Found {len(filtered)} sessions (showing {len(items)}):\n")
        for m in items:
            src = m.get("source", "claude")[:3]
            date = m.get("date", "")[:10]
            title = m.get("title", "Untitled")[:55]
            msgs = m.get("userMessageCount", 0)
            sid = m.get("id", "")
            print(f"  [{src}] {date} {title:55s} {msgs:3d}msg  id:{sid}")


def cmd_read(args):
    """Read a session in human-readable format."""
    _init_index()

    session_id = args.session
    data = server.load_session(session_id)

    # Fallback: partial ID or path match
    if not data:
        with server._index_lock:
            sessions = server._index.get("sessions", {})
        for sid, m in sessions.items():
            if session_id in sid or session_id in m.get("filePath", ""):
                data = server.load_session(sid)
                if data:
                    break

    if not data:
        print(f"Session not found: {session_id}", file=sys.stderr)
        sys.exit(1)

    # Summary mode: user messages + last assistant text only (no tools at all)
    summary_mode = getattr(args, "summary", False)

    # Smart truncation: keep user messages + assistant text, fold tools
    # Pass 1: collect all turns with priority tagging
    turns = []  # [(priority, text)]  priority: 0=user, 1=assistant_text, 2=tool_summary
    tool_batch = []  # accumulate consecutive tools into one folded line

    def flush_tools():
        if tool_batch:
            if not summary_mode:
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
                    max_len = 600 if summary_mode else 1200
                    turns.append((1, f"\n--- ASSISTANT ---\n{b['text'][:max_len]}"))
                elif b.get("type") == "tool_use":
                    tool_batch.append(b.get("name", "?"))
                elif b.get("type") == "thinking":
                    tool_batch.append("thinking")

        elif msg_type == "tool_result":
            pass  # folded into tool_batch above

    flush_tools()

    # Pass 2: assemble output within budget
    max_chars = 12000
    header = f"# {data['title']}\n# {data.get('project', '')} | {data.get('date', '')[:19]} | {len(data.get('messages', []))} messages"
    output = [header]
    used = len(header)

    for priority, text in turns:
        if used + len(text) > max_chars:
            # Over budget: skip tools first, then truncate text
            if priority == 2:
                continue  # drop tool summaries first
            text = text[:max(200, max_chars - used)] + "\n[...]"
        output.append(text)
        used += len(text)
        if used > max_chars and priority > 0:
            output.append(f"\n[TRUNCATED — showing {used}/{sum(len(t) for _, t in turns)} chars, tools folded]")
            break

    print("\n".join(output))


def cmd_search(args):
    """Search user messages across sessions."""
    _init_index()
    results = server.search_sessions(args.query)

    # Apply additional filters
    with server._index_lock:
        sessions = server._index.get("sessions", {})

    now = datetime.now()
    days_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
    out = []

    for r in results:
        sid = r.get("sessionId", "")
        meta = sessions.get(sid, {})

        if args.source and args.source != "all":
            if meta.get("source", "claude") != args.source:
                continue
        if args.project and args.project.lower() not in meta.get("projectName", "").lower():
            continue
        if args.date and args.date != "all":
            date_str = meta.get("date", "")
            if date_str:
                try:
                    d = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    if (now - d).days > days_map.get(args.date, 9999):
                        continue
                except Exception:
                    pass
        out.append(r)

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
        _init_index()
        with server._index_lock:
            sessions = server._index.get("sessions", {})
        # Find session
        target = None
        for sid, m in sessions.items():
            if args.session in sid or args.session in m.get("filePath", ""):
                target = m
                break
        if not target:
            print(f"Session not found: {args.session}", file=sys.stderr)
            sys.exit(1)

        user_texts = target.get("userTexts", [])
        title = target.get("title", "Untitled")
        print(f"# User queries from: {title}")
        print(f"# {len(user_texts)} messages\n")
        for i, ut in enumerate(user_texts):
            ts = ut.get("ts", "")[:19]
            text = ut.get("text", "")
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


def cmd_corrections(args):
    """Find user correction / dissatisfaction patterns across sessions."""
    # Correction signal patterns (Chinese + English)
    patterns = [
        # Chinese: explicit correction
        r'不是这样', r'不对[，。！\s]', r'不要这样', r'你忘了', r'应该是',
        r'错了[，。！\s]', r'你搞错', r'这样不行', r'别这样做', r'重新来',
        r'不是我说的', r'你理解错', r'不需要这个', r'我说的是',
        r'你漏了', r'搞反了', r'改回去', r'撤销',
        # Chinese: soft/implicit correction
        r'不行[，。！\s]', r'太[简精粗]', r'回退', r'换一种', r'重做',
        r'这不是', r'那不对', r'不应该', r'你没[看听懂理解]', r'别搞',
        r'我要的是', r'请不要', r'停[下一]', r'算了',
        r'之前说[的过]', r'刚才说', r'你搞反', r'弄反',
        r'多余的?[，。！\s]', r'没必要', r'不是这个意思', r'理解偏了',
        r'过度[设计复杂抽象]', r'太复杂', r'太臃肿', r'没有达到',
        # Chinese: repeated errors / unresolved
        r'怎么又', r'又错了', r'又来了', r'还是不行', r'还是有问题',
        r'没修好', r'没解决', r'问题还在', r'bug还在',
        # Chinese: ask to retry / rethink
        r'你再看看', r'再想想', r'再试试', r'重新想',
        # Chinese: challenging AI assumptions
        r'我没说', r'我没让你', r'谁让你', r'哪里说了',
        # Chinese: dissatisfaction
        r'不合适', r'不合理', r'不是我想要', r'差太远',
        r'按我说的', r'照我说的',
        # English: explicit correction
        r'\b(?:that\'?s?|you\'?re?|this is|you.{0,5})wrong\b', r'\byou forgot\b', r"\bthat's not right\b",
        r"\bdon't do that\b", r"\bshouldn't have\b",
        r'\bnot what I (?:asked|meant|wanted)\b',
        r'\bI meant\b', r'\byou missed\b', r'\bplease (?:don\'t|stop)\b',
        r'\bactually,?\s+(?:I|it|the|we|that)\b',
        # English: soft/implicit correction
        r'\bno,?\s+(?:I|it|the|we|that|not)\b',
        r'\brevert\b', r'\bundo\b', r'\broll\s*back\b',
        r'\btoo (?:complex|verbose|long|simple|short)\b',
        r'\bnot (?:quite|exactly|correct)\b', r'\bclose but\b',
        r'\bthat\'s (?:not|wrong|overkill|redundant)\b',
        r'\bovercomplicat', r'\bunnecessar',
        r'\bI (?:already|never|didn\'t) (?:said|told|asked|want)\b',
        # English: persistent issues / retry
        r'\bstill (?:broken|not working|wrong|failing)\b',
        r"\bdoesn't work\b", r'\bnot working\b',
        r'\byou broke\b', r'\bthat broke\b',
        r'\btry again\b', r'\bstart over\b',
        r'\b(?:as |like )I said\b', r'\bI said\b',
        r'\bnope\b', r'\bnah\b',
    ]
    combined_re = re.compile('|'.join(patterns), re.IGNORECASE)

    # AI patterns split into correction (AI was wrong) vs insight (user's good idea)
    # Derived from systematic scan of 34889 real assistant responses

    # ── Correction: AI admitting mistakes / fixing errors ──
    ai_correction_patterns = [
        # Chinese: apology / direct admission
        r'抱歉', r'对不起', r'我理解错', r'我搞错', r'我的错',
        r'我的失误', r'是我的疏漏', r'说错了', r'我写错了',
        r'你是对的', r'感谢.{0,4}纠正',
        r'你说得对.{0,15}(?:我|确实|漏|错|没)',
        # Chinese: self-correction verbs
        r'我搞混', r'我混了', r'我跑偏', r'我漏写', r'我没看到',
        r'我误读', r'我误判', r'判断错了', r'看错了',
        # Chinese: acknowledging oversight
        r'我遗漏', r'我忽略了', r'漏掉了', r'确实漏了',
        r'没考虑到', r'需要修正', r'本该',
        r'纠正一下', r'让我重新', r'推倒重来', r'换个思路',
        r'精简过头', r'想当然', r'错误假设', r'之前以为',
        # Chinese: Codex-style action acknowledgment
        r'已修正', r'已修复', r'撤回', r'改回',
        r'收到.{0,6}(?:偏|错|漏|之前|刚才)',
        r'刚才.{0,8}(?:偏差|偏了|错|漏|搞)',
        # English: apology / direct admission
        r'\bI apologize\b', r'\bmy mistake\b', r'\bI was wrong\b',
        r'\bI misunderstood\b', r'\bmy bad\b',
        r'\bI overlooked\b', r'\bI missed\b',
        r'\bsorry.{0,10}(?:mistake|wrong|missed|overlooked|confusion)\b',
        r'\blet me (?:fix|correct|redo) (?:that|this|my)\b',
        r'\bthank.{0,6}(?:correcting|catching)\b',
        # English: self-correction
        r'\bI should have\b', r'\bI forgot\b',
        r"\bI didn't consider\b", r'\bupon (?:reflection|further review)\b',
        r'\bI realized\b', r'\bI incorrectly\b', r'\bI mistakenly\b',
        r'\bI stand corrected\b',
    ]

    # ── Insight: AI affirming user's good idea / observation ──
    ai_insight_patterns = [
        # Chinese: positive acknowledgment
        r'好(?:想法|主意|思路|建议|眼力)',
        r'好问题.{0,10}(?:让我|确实|我之前|我没|漏|错)',
        r'问得好', r'想法很好', r'完全正确', r'完全同意',
        r'确实如此', r'没想到', r'感谢.{0,4}指出',
        # Chinese: praising user's discovery
        r'你提醒得对', r'你抓到', r'你指出', r'你发现',
        r'你点(?:到|出)', r'判断对了', r'有道理',
        r'切中要害', r'说到点子上',
        # Chinese: realization
        r'啊.{0,3}我理解', r'懂了.{0,6}(?:我|之前|不该|原来)',
        # English: affirming user
        r'\bgood (?:catch|point|call|question|observation)\b',
        r'\bfair point\b', r'\bexcellent point\b',
        r'\bI see the (?:issue|problem)\b',
        r"\byou'?re right\b", r"\bI didn't think\b",
        r'\b(?:exactly|absolutely) right\b',
        r'\bthank.{0,6}pointing\b',
    ]

    ai_correction_re = re.compile('|'.join(ai_correction_patterns), re.IGNORECASE)
    ai_insight_re = re.compile('|'.join(ai_insight_patterns), re.IGNORECASE)
    # Combined for backward-compatible aiConfirmed check
    ai_ack_re = re.compile('|'.join(ai_correction_patterns + ai_insight_patterns), re.IGNORECASE)

    def _skip_noise(text):
        if len(text) < 5 or len(text) > 3000:
            return True
        if text.strip().startswith(("#", "```", "<", "{")):
            return True
        if "analyze.py" in text or "CLI tool" in text:
            return True
        if "Base directory for this skill:" in text or "skill:" in text[:30]:
            return True
        return False

    corrections = []
    seen_keys = set()  # deduplicate by (sid, idx)

    # Build per-session data from DB if available, else fall back to old index
    db_sessions = _get_filtered_db(args)
    if db_sessions:
        import db as _db
        _db.init_db()
        sids = [s["id"] for s in db_sessions]
        conn = _db.get_conn()
        placeholders = ",".join("?" * len(sids))
        msg_rows = conn.execute(f"""
            SELECT m.session_id, m.idx, m.role, m.text
            FROM messages m
            WHERE m.session_id IN ({placeholders})
            ORDER BY m.session_id, m.idx
        """, sids).fetchall()
        # Reconstruct per-session structure
        from collections import defaultdict
        sess_user = defaultdict(list)
        sess_asst = defaultdict(list)
        for r in msg_rows:
            entry = {"idx": r["idx"], "text": r["text"], "ts": ""}
            if r["role"] == "user":
                sess_user[r["session_id"]].append(entry)
            elif r["role"] == "assistant":
                sess_asst[r["session_id"]].append(entry)
        sessions_iter = {
            s["id"]: {
                "id": s["id"],
                "title": s.get("title", ""),
                "projectName": s.get("project_name", ""),
                "date": s.get("date", ""),
                "filePath": s.get("file_path", ""),
                "userTexts": sess_user[s["id"]],
                "assistantSnippets": sess_asst[s["id"]],
            }
            for s in db_sessions
        }
    else:
        sessions_iter = _get_filtered(args)

    for sid, meta in sessions_iter.items():
        user_texts = meta.get("userTexts", [])
        asst_snippets = meta.get("assistantSnippets", [])
        # Build idx -> snippet lookup for quick adjacency check
        asst_by_idx = {a["idx"]: a["text"] for a in asst_snippets}

        # Pass 1: User correction signals (+ check adjacent AI acknowledgment)
        for ut in user_texts:
            text = ut.get("text", "")
            if _skip_noise(text):
                continue
            matches = combined_re.findall(text)
            if not matches:
                continue
            key = (sid, ut["idx"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            # Check if AI acknowledged in next response
            ai_confirmed = False
            for offset in range(1, 4):  # check next 1-3 messages
                asst_text = asst_by_idx.get(ut["idx"] + offset, "")
                if asst_text and ai_ack_re.search(asst_text):
                    ai_confirmed = True
                    break
            corrections.append({
                "sessionId": sid,
                "title": meta.get("title", "")[:60],
                "project": meta.get("projectName", ""),
                "date": meta.get("date", "")[:10],
                "text": text[:400],
                "signals": list(set(matches))[:5],
                "source": "user",
                "aiConfirmed": ai_confirmed,
                "filePath": meta.get("filePath", ""),
            })

        # Pass 2: AI-only (no user pattern matched but AI acknowledged)
        # Build set of all user correction indices in this session for wider dedup
        user_corr_idxs = {k[1] for k in seen_keys if k[0] == sid}
        for asst in asst_snippets:
            asst_text = asst.get("text", "")
            # Try correction patterns first, then insight
            corr_matches = ai_correction_re.findall(asst_text)
            insight_matches = ai_insight_re.findall(asst_text)
            if not corr_matches and not insight_matches:
                continue
            # Check if near any user correction (±5 range) — same event, don't double count
            ai_idx = asst["idx"]
            already = any(abs(ai_idx - ui) <= 5 for ui in user_corr_idxs)
            if already:
                continue
            key = (sid, ai_idx)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            # Determine kind: correction takes priority over insight
            kind = "correction" if corr_matches else "insight"
            all_matches = corr_matches or insight_matches
            # Find the preceding user message for context
            preceding_user = ""
            for ut in reversed(user_texts):
                if ut["idx"] < asst["idx"]:
                    preceding_user = ut["text"][:200]
                    break
            corrections.append({
                "sessionId": sid,
                "title": meta.get("title", "")[:60],
                "project": meta.get("projectName", ""),
                "date": meta.get("date", "")[:10],
                "text": preceding_user or "(AI-side only)",
                "aiText": asst_text[:200],
                "signals": list(set(all_matches))[:3],
                "source": "ai",
                "kind": kind,
                "aiConfirmed": True,
                "filePath": meta.get("filePath", ""),
            })

    corrections.sort(key=lambda c: c.get("date", ""), reverse=True)

    # Stats
    user_src = [c for c in corrections if c.get("source") == "user"]
    ai_corr = [c for c in corrections if c.get("source") == "ai" and c.get("kind") == "correction"]
    ai_insight = [c for c in corrections if c.get("source") == "ai" and c.get("kind") == "insight"]
    confirmed = [c for c in user_src if c.get("aiConfirmed")]

    if args.json:
        print(json.dumps(corrections[:args.limit], ensure_ascii=False, indent=2))
    else:
        print(f"Found {len(corrections)} (user:{len(user_src)} ai-correction:{len(ai_corr)} ai-insight:{len(ai_insight)} confirmed:{len(confirmed)}):\n")
        for c in corrections[:args.limit]:
            signals = ", ".join(c["signals"])
            text = c['text'][:180].replace('\n', ' ')
            if c.get("source") == "user":
                src_tag = "👤"
                ack_tag = " ✓AI" if c.get("aiConfirmed") else ""
            elif c.get("kind") == "insight":
                src_tag = "💡"
                ack_tag = ""
            else:
                src_tag = "🤖"
                ack_tag = ""
            print(f"  {src_tag}{ack_tag} [{c['date']}] {c['project']} [{signals}]")
            print(f"    {text}")
            if c.get("source") == "ai" and c.get("aiText"):
                print(f"    🤖 {c['aiText'][:120].replace(chr(10), ' ')}")
            print(f"    sid:{c['sessionId']}")


def cmd_decisions(args):
    """Extract potential decision points from conversations."""
    # Tighter decision patterns — require decision-making context words
    decision_re = re.compile(
        r'(?:决定[了用采]|最终选|采用了?|放弃了?|'
        r'方案[AB12一二]|用.{1,20}还是|A还是B|'
        r'\bdecided\b|\blet\'s go with\b|\bshould we\b|'
        r'\bchoose\b|\btrade-?off\b|\bvs\.?\s)',
        re.IGNORECASE
    )

    decisions = []

    # Try DB first; fall back to old method if DB is empty
    db_rows = _get_messages_db(args, role="user", limit=99999)
    if db_rows:
        # Build a session-id → session meta lookup from DB
        db_sessions = {s["id"]: s for s in _get_filtered_db(args)}
        for row in db_rows:
            text = row.get("text", "")
            sid = row.get("session_id", "")
            meta = db_sessions.get(sid, {})
            # Skip noise
            if len(text) < 10 or len(text) > 2000:
                continue
            if text.strip().startswith(("<", "{", "```", "#")):
                continue
            if "analyze.py" in text or "CLI tool" in text or "工作流" in text[:50]:
                continue
            if text.strip().startswith(("You are review", "You have a CLI", "Search the web")):
                continue
            if text.strip().startswith(("toolu_", "a9bd", "Agent ")):
                continue
            if decision_re.search(text):
                decisions.append({
                    "sessionId": sid,
                    "title": meta.get("title", "")[:60],
                    "project": meta.get("project_name", ""),
                    "date": (meta.get("date") or "")[:10],
                    "text": text[:400],
                    "filePath": meta.get("file_path", ""),
                })
    else:
        filtered = _get_filtered(args)
        for sid, meta in filtered.items():
            for ut in meta.get("userTexts", []):
                text = ut.get("text", "")
                if len(text) < 10 or len(text) > 2000:
                    continue
                if text.strip().startswith(("<", "{", "```", "#")):
                    continue
                if "analyze.py" in text or "CLI tool" in text or "工作流" in text[:50]:
                    continue
                if text.strip().startswith(("You are review", "You have a CLI", "Search the web")):
                    continue
                if text.strip().startswith(("toolu_", "a9bd", "Agent ")):
                    continue
                if decision_re.search(text):
                    decisions.append({
                        "sessionId": sid,
                        "title": meta.get("title", "")[:60],
                        "project": meta.get("projectName", ""),
                        "date": meta.get("date", "")[:10],
                        "text": text[:400],
                        "filePath": meta.get("filePath", ""),
                    })

    decisions.sort(key=lambda d: d.get("date", ""), reverse=True)

    if args.json:
        print(json.dumps(decisions[:args.limit], ensure_ascii=False, indent=2))
    else:
        print(f"Found {len(decisions)} potential decision points:\n")
        for d in decisions[:args.limit]:
            print(f"  [{d['date']}] {d['project']} — {d['title']}")
            print(f"  > {d['text'][:250]}")
            print(f"  session: {d['sessionId']}")
            print()


def cmd_errors(args):
    """Extract error patterns from tool results across sessions."""
    filtered = _get_filtered(args)

    err_re = re.compile(
        r'((?:Traceback.*?:\s*)?'
        r'(?:(?:Error|Exception|TypeError|ValueError|KeyError|AttributeError|'
        r'ImportError|ModuleNotFoundError|NameError|IndexError|RuntimeError|'
        r'SyntaxError|FileNotFoundError|PermissionError|OSError|IOError|'
        r'ConnectionError|TimeoutError)'
        r'[:\s].{0,150}))',
        re.IGNORECASE
    )

    groups = {}  # normalized → {count, sessions, projects, sample}

    for sid, meta in filtered.items():
        fp = meta.get("filePath", "")
        source = meta.get("source", "claude")
        project = meta.get("projectName", "")
        if not fp or not os.path.exists(fp):
            continue

        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if source == "claude" and obj.get("type") == "user" and obj.get("toolUseResult"):
                        content = obj.get("message", {}).get("content", [])
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "tool_result":
                                    rt = block.get("content", "")
                                    if isinstance(rt, list):
                                        rt = json.dumps(rt)
                                    if isinstance(rt, str):
                                        for m in err_re.finditer(rt[:5000]):
                                            raw = m.group(1)
                                            # Skip source code patterns (not real errors)
                                            if 'except Exception' in raw or 'Exception as e' in raw:
                                                continue
                                            if 'raise ' in raw[:20] or 'class ' in raw[:20]:
                                                continue
                                            key = server._normalize_error(raw)
                                            if len(key) < 10:
                                                continue
                                            # Skip overly generic or source-code patterns
                                            if key.strip().rstrip(':') in ('Exception', 'Error', 'error'):
                                                continue
                                            if '${' in raw or '`);' in raw or 'throw new' in raw:
                                                continue
                                            if '# noqa' in raw or '{e}")' in raw or 'f"' in raw[:10]:
                                                continue
                                            if key not in groups:
                                                groups[key] = {"count": 0, "sessions": set(),
                                                               "projects": set(), "sample": m.group(1)[:200]}
                                            groups[key]["count"] += 1
                                            groups[key]["sessions"].add(sid)
                                            groups[key]["projects"].add(project)
        except Exception:
            continue

    sorted_errors = sorted(groups.items(), key=lambda x: -x[1]["count"])

    if args.json:
        out = [{"pattern": k, "count": v["count"], "sessions": len(v["sessions"]),
                "projects": sorted(v["projects"]), "sample": v["sample"]}
               for k, v in sorted_errors[:args.limit]]
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"Found {len(sorted_errors)} error patterns:\n")
        for key, data in sorted_errors[:args.limit]:
            projs = ", ".join(sorted(data["projects"]))
            print(f"  [{data['count']}x · {len(data['sessions'])} sessions] {projs}")
            print(f"  {data['sample']}")
            print()


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

    print(f"\nBy source:")
    for src, count in sorted(src_counts.items(), key=lambda x: -x[1]):
        print(f"  {src:8s} {count:5d} sessions")

    top_n = min(args.limit, len(proj_counts))
    print(f"\nBy project (top {top_n}):")
    for pname, count in sorted(proj_counts.items(), key=lambda x: -x[1])[:top_n]:
        pct = count / total * 100
        print(f"  {pname:40s} {count:4d} ({pct:.0f}%)")


def cmd_files(args):
    """Show most-edited files across sessions."""
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
                            name = server._CODEX_TOOL_NAMES.get(raw_name, raw_name)
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

    if args.json:
        out = [{"path": fp, **{k: v if not isinstance(v, set) else len(v) for k, v in data.items()}}
               for fp, data in sorted_files[:args.limit]]
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"Top edited files ({len(sorted_files)} total):\n")
        for fp, data in sorted_files[:args.limit]:
            print(f"  {fp}")
            print(f"    edits={data['edits']}  writes={data['writes']}  reads={data['reads']}  sessions={len(data['sessions'])}")
            print()


def cmd_highlights(args):
    """Per-session one-line highlights: topic, key signals, message count."""
    # Reuse correction + decision regexes for signal counting
    correction_re = re.compile(
        r'不是这样|不对[，。！\s]|不要这样|你忘了|应该是|错了[，。！\s]|你搞错|这样不行|别这样做|重新来|'
        r'不是我说的|你理解错|不需要这个|我说的是|你漏了|搞反了|改回去|撤销|'
        r'不行[，。！\s]|太[简精粗]|回退|换一种|重做|这不是|那不对|不应该|你没[看听懂理解]|别搞|'
        r'我要的是|请不要|停[下一]|算了|'
        r'\bwrong\b|\byou forgot\b|\bthat\'s not right\b|\bdon\'t do that\b|\bshouldn\'t have\b|'
        r'\bnot what I (?:asked|meant|wanted)\b|\bI meant\b|\byou missed\b|\bplease (?:don\'t|stop)\b|'
        r'\bactually,?\s+(?:I|it|the|we|that)\b|\bno,?\s+(?:I|it|the|we|that|not)\b|'
        r'\brevert\b|\bundo\b|\broll\s*back\b',
        re.IGNORECASE
    )
    decision_re = re.compile(
        r'决定|选择|方案|approach|decided|choose|option|trade-?off|vs\.?|versus|'
        r'用.+还是|should we|let\'s go with|我们用|最终选|采用|放弃',
        re.IGNORECASE
    )

    # Try DB first; fall back to old method if DB is empty
    db_sessions = _get_filtered_db(args)
    if db_sessions:
        import db as _db
        _db.init_db()
        # Load user messages in bulk for all sessions
        sids = [s["id"] for s in db_sessions]
        conn = _db.get_conn()
        placeholders = ",".join("?" * len(sids))
        msg_rows = conn.execute(f"""
            SELECT session_id, text FROM messages
            WHERE session_id IN ({placeholders}) AND role='user'
            ORDER BY session_id, idx
        """, sids).fetchall()
        # Group messages by session
        from collections import defaultdict
        sess_texts = defaultdict(list)
        for r in msg_rows:
            sess_texts[r["session_id"]].append(r["text"])

        items = sorted(db_sessions, key=lambda s: s.get("date", ""), reverse=True)
        items = items[:args.limit]

        if not args.json:
            print(f"Highlights for {len(items)} sessions:\n")

        results = []
        for s in items:
            sid = s["id"]
            title = (s.get("title") or "Untitled")[:50]
            project = s.get("project_name", "")
            source = (s.get("source", "claude") or "claude")[:3]
            date = (s.get("date") or "")[:10]
            msg_count = s.get("user_message_count") or 0

            corrections = 0
            decisions = 0
            topics = []
            for text in sess_texts.get(sid, []):
                if len(text) < 3 or text.strip().startswith(("<", "{", "```")):
                    continue
                if correction_re.search(text):
                    corrections += 1
                if decision_re.search(text):
                    decisions += 1
                if not topics and len(text) > 10 and not text.startswith(("#", "```")):
                    topics.append(text[:80].replace("\n", " "))

            topic = topics[0] if topics else title
            signals = []
            if corrections:
                signals.append(f"corr:{corrections}")
            if decisions:
                signals.append(f"dec:{decisions}")
            sig_str = " ".join(signals) if signals else "-"

            if args.json:
                results.append({
                    "id": sid, "date": date, "source": source, "project": project,
                    "title": title, "topic": topic, "messages": msg_count,
                    "corrections": corrections, "decisions": decisions,
                })
            else:
                print(f"  [{source}] {date} {msg_count:3d}msg {sig_str:12s} {project[:20]:20s} | {topic}")
    else:
        filtered = _get_filtered(args)
        items = sorted(filtered.values(), key=lambda m: m.get("date", ""), reverse=True)
        items = items[:args.limit]

        if not args.json:
            print(f"Highlights for {len(items)} sessions:\n")

        results = []
        for m in items:
            sid = m.get("id", "")
            title = m.get("title", "Untitled")[:50]
            project = m.get("projectName", "")
            source = m.get("source", "claude")[:3]
            date = m.get("date", "")[:10]
            msg_count = m.get("userMessageCount", 0)

            corrections = 0
            decisions = 0
            topics = []
            for ut in m.get("userTexts", []):
                text = ut.get("text", "")
                if len(text) < 3 or text.strip().startswith(("<", "{", "```")):
                    continue
                if correction_re.search(text):
                    corrections += 1
                if decision_re.search(text):
                    decisions += 1
                if not topics and len(text) > 10 and not text.startswith(("#", "```")):
                    topics.append(text[:80].replace("\n", " "))

            topic = topics[0] if topics else title
            signals = []
            if corrections:
                signals.append(f"corr:{corrections}")
            if decisions:
                signals.append(f"dec:{decisions}")
            sig_str = " ".join(signals) if signals else "-"

            if args.json:
                results.append({
                    "id": sid, "date": date, "source": source, "project": project,
                    "title": title, "topic": topic, "messages": msg_count,
                    "corrections": corrections, "decisions": decisions,
                })
            else:
                print(f"  [{source}] {date} {msg_count:3d}msg {sig_str:12s} {project[:20]:20s} | {topic}")

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Evolve — structured data for Evolve page visualizations
# ---------------------------------------------------------------------------

# Shared category classifier for correction signals
_CATEGORY_PATTERNS = {
    "style": re.compile(
        r'太[简精粗]|太复杂|太臃肿|过度[设计复杂抽象]|'
        r'too (?:complex|verbose|long|simple|short)|overcomplicat|unnecessar',
        re.IGNORECASE),
    "scope": re.compile(
        r'不需要这个|多余|没必要|不是我说的|我说的是|我要的是|'
        r'not what I (?:asked|meant|wanted)|I meant|我没说|我没让你|谁让你',
        re.IGNORECASE),
    "accuracy": re.compile(
        r'不对[，。！\s]|错了[，。！\s]|你搞错|搞反了|你理解错|你没[看听懂理解]|应该是|'
        r'wrong|not right|you forgot|you missed|incorrect|mistaken',
        re.IGNORECASE),
    "workflow": re.compile(
        r'重新来|重做|回退|改回去|撤销|换一种|再看看|再想想|再试试|'
        r'revert|undo|roll\s*back|start over|try again',
        re.IGNORECASE),
}


def _classify_correction(text, signals):
    """Classify a correction into a category based on signal words."""
    for cat, pat in _CATEGORY_PATTERNS.items():
        if pat.search(text):
            return cat
        for s in signals:
            if pat.search(s):
                return cat
    return "workflow"  # default


def _get_corrections_raw(args):
    """Run corrections logic and return raw list (reuse cmd_corrections internals)."""
    # We need to call cmd_corrections but capture the data, not print it.
    # Easiest: set args.json=True, capture stdout, parse.
    import copy
    fake_args = copy.copy(args)
    fake_args.json = True
    fake_args.limit = 200
    old_stdout = sys.stdout
    sys.stdout = buf = io.StringIO()
    try:
        cmd_corrections(fake_args)
    finally:
        sys.stdout = old_stdout
    try:
        return json.loads(buf.getvalue())
    except json.JSONDecodeError:
        return []


def _get_errors_raw(args):
    """Run errors logic and return raw list."""
    import copy
    fake_args = copy.copy(args)
    fake_args.json = True
    fake_args.limit = 100
    old_stdout = sys.stdout
    sys.stdout = buf = io.StringIO()
    try:
        cmd_errors(fake_args)
    finally:
        sys.stdout = old_stdout
    try:
        return json.loads(buf.getvalue())
    except json.JSONDecodeError:
        return []


def _write_evolve_cache(tab, data):
    """Write evolve data to .cache/evolve/<tab>.json."""
    cache_dir = Path(__file__).resolve().parent / ".cache" / "evolve"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_path = cache_dir / f"{tab}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(out_path)


def cmd_evolve_rules(args):
    """Generate rules data for Evolve Rules tab."""
    corrections = _get_corrections_raw(args)

    # Group corrections by category → build rules
    from collections import defaultdict
    cat_groups = defaultdict(list)
    for c in corrections:
        cat = _classify_correction(c.get("text", ""), c.get("signals", []))
        cat_groups[cat].append(c)

    rules = []
    rule_id = 0
    for cat, items in cat_groups.items():
        # Sub-group by similar signal patterns to avoid one mega-rule per category
        signal_groups = defaultdict(list)
        for item in items:
            # Use first signal as grouping key
            key = item["signals"][0] if item.get("signals") else "general"
            signal_groups[key].append(item)

        for signal_key, group in signal_groups.items():
            if len(group) < 1:
                continue
            rule_id += 1
            freq = len(group)
            # Priority based on frequency
            if freq >= 5:
                priority = "P0"
            elif freq >= 2:
                priority = "P1"
            else:
                priority = "P2"

            # Build rule text from the most common correction
            representative = group[0]
            user_quote = representative.get("text", "")[:200]

            # Build evidence
            evidence = []
            for g in group[:5]:
                evidence.append({
                    "session": g.get("sessionId", ""),
                    "quote": g.get("text", "")[:150],
                })

            # Determine rule/why/positive/negative from context
            rule_text = f"用户纠正：{signal_key}"
            why = user_quote[:100] if user_quote else ""
            ai_text = representative.get("aiText", "")

            # Map Chinese category names
            cat_label = {"style": "风格", "scope": "范围", "accuracy": "准确性",
                         "workflow": "工作流"}.get(cat, cat)

            rules.append({
                "id": f"r{rule_id}",
                "priority": priority,
                "category": cat_label,
                "rule": rule_text,
                "why": why,
                "positive": "",
                "negative": ai_text[:100] if ai_text else "",
                "evidence": evidence,
                "frequency": freq,
            })

    rules.sort(key=lambda r: {"P0": 0, "P1": 1, "P2": 2}.get(r["priority"], 9))
    result = {"rules": rules}

    out_path = _write_evolve_cache("rules", result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Generated {len(rules)} rules → {out_path}")


def cmd_evolve_signals(args):
    """Generate signals data for Evolve Signals tab."""
    corrections = _get_corrections_raw(args)

    # Build timeline (group by date, count by category)
    from collections import defaultdict
    date_counts = defaultdict(lambda: defaultdict(int))  # date → {cat: count}
    events = []

    for i, c in enumerate(corrections):
        cat = _classify_correction(c.get("text", ""), c.get("signals", []))
        date = c.get("date", "")[:10]
        if date:
            date_counts[date][cat] += 1

        events.append({
            "id": f"c{i+1}",
            "date": date,
            "session": c.get("sessionId", ""),
            "type": cat,
            "userQuote": c.get("text", "")[:200],
            "aiIssue": c.get("aiText", "")[:150] if c.get("aiText") else "",
            "correction": "",
            "linkedRule": None,
        })

    timeline = sorted([
        {"date": d, "counts": dict(counts)}
        for d, counts in date_counts.items()
    ], key=lambda x: x["date"])

    result = {"timeline": timeline, "events": events[:100]}

    out_path = _write_evolve_cache("signals", result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Generated {len(timeline)} timeline entries, {len(events)} events → {out_path}")


def cmd_evolve_patterns(args):
    """Generate patterns data for Evolve Patterns tab."""
    corrections = _get_corrections_raw(args)
    errors = _get_errors_raw(args)

    from collections import defaultdict

    bubbles = []
    cards = []
    pid = 0

    # 1. Error patterns → "error" type bubbles
    for err in errors[:20]:
        pid += 1
        bubbles.append({
            "id": f"p{pid}",
            "label": err.get("pattern", "")[:30],
            "frequency": err.get("count", 1),
            "type": "error",
            "trend": "stable",
        })
        cards.append({
            "id": f"p{pid}",
            "description": err.get("sample", err.get("pattern", "")),
            "frequency": err.get("count", 1),
            "cost": f"{err.get('sessions', 1)} sessions affected",
            "suggestion": "检查错误根因，添加防御性处理",
            "sessions": [],
            "trend": "stable",
        })

    # 2. Correction patterns → group by category for "workflow"/"efficiency" bubbles
    cat_counts = defaultdict(lambda: {"count": 0, "sessions": set(), "samples": []})
    for c in corrections:
        cat = _classify_correction(c.get("text", ""), c.get("signals", []))
        cat_counts[cat]["count"] += 1
        cat_counts[cat]["sessions"].add(c.get("sessionId", ""))
        if len(cat_counts[cat]["samples"]) < 3:
            cat_counts[cat]["samples"].append(c.get("text", "")[:100])

    cat_labels = {"style": "风格问题", "scope": "范围蔓延", "accuracy": "准确性问题",
                  "workflow": "工作流问题"}
    cat_types = {"style": "efficiency", "scope": "efficiency",
                 "accuracy": "knowledge_gap", "workflow": "workflow"}

    for cat, data in cat_counts.items():
        if data["count"] < 1:
            continue
        pid += 1
        bubbles.append({
            "id": f"p{pid}",
            "label": cat_labels.get(cat, cat),
            "frequency": data["count"],
            "type": cat_types.get(cat, "workflow"),
            "trend": "stable",
        })
        cards.append({
            "id": f"p{pid}",
            "description": f"{cat_labels.get(cat, cat)}：{'; '.join(data['samples'][:2])}",
            "frequency": data["count"],
            "cost": f"{len(data['sessions'])} sessions",
            "suggestion": f"关注 {cat_labels.get(cat, cat)} 相关的重复纠正",
            "sessions": list(data["sessions"])[:5],
            "trend": "stable",
        })

    bubbles.sort(key=lambda b: -b["frequency"])
    cards.sort(key=lambda c: -c["frequency"])
    result = {"bubbles": bubbles, "cards": cards}

    out_path = _write_evolve_cache("patterns", result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Generated {len(bubbles)} patterns → {out_path}")


# ---------------------------------------------------------------------------
# evolve-write: validated write/merge/delete for Evolve tab data
# ---------------------------------------------------------------------------

# Schema definitions: {field: {required_keys, optional_keys, type_checks}}
_EVOLVE_SCHEMAS = {
    "profile": {
        "top_fields": {"categories": list, "radar": dict},
        "categories_item": {"required": {"name": str}, "optional": {"icon": str, "tags": list, "items": list}},
        "categories_item_item": {"required": {"text": str}, "optional": {"confidence": str, "session": str}},
        "radar_dimension": {"required": {"name": str, "score": (int, float)}, "optional": {"evidence": str}},
        "id_field": None,  # categories matched by "name"
    },
    "memory": {
        "top_fields": {"nodes": list, "links": list, "cards": list},
        "node": {"required": {"id": str, "label": str}, "optional": {"type": str, "frequency": (int, float), "confidence": str, "sessions": list}},
        "link": {"required": {"source": str, "target": str}, "optional": {"strength": (int, float)}},
        "card": {"required": {"id": str, "content": str}, "optional": {"firstSeen": str, "lastSeen": str, "evidence": str}},
        "id_field": "id",
    },
    "rules": {
        "top_fields": {"rules": list},
        "rule": {"required": {"id": str, "rule": str}, "optional": {"priority": str, "category": str, "why": str, "positive": str, "negative": str, "evidence": list, "frequency": (int, float)}},
        "id_field": "id",
    },
    "signals": {
        "top_fields": {"timeline": list, "events": list},
        "event": {"required": {"id": str}, "optional": {"date": str, "session": str, "type": str, "userQuote": str, "aiIssue": str, "correction": str, "linkedRule": (str, type(None))}},
        "timeline_item": {"required": {"date": str, "counts": dict}, "optional": {}},
        "id_field": "id",
    },
    "patterns": {
        "top_fields": {"bubbles": list, "cards": list},
        "bubble": {"required": {"id": str, "label": str}, "optional": {"frequency": (int, float), "type": str, "trend": str}},
        "card": {"required": {"id": str}, "optional": {"description": str, "frequency": (int, float), "cost": str, "suggestion": str, "sessions": list, "trend": str}},
        "id_field": "id",
    },
}


def _validate_evolve_data(tab, data):
    """Validate data against tab schema. Returns (ok, errors_list)."""
    schema = _EVOLVE_SCHEMAS.get(tab)
    if not schema:
        return False, [f"Unknown tab: {tab}"]

    if not isinstance(data, dict):
        return False, ["Data must be a JSON object"]

    errors = []
    top = schema["top_fields"]

    # Check top-level fields exist and have correct types
    for field, expected_type in top.items():
        if field not in data:
            data[field] = expected_type()  # auto-fill with empty
            continue
        if not isinstance(data[field], expected_type):
            errors.append(f"'{field}' must be {expected_type.__name__}, got {type(data[field]).__name__}")

    if errors:
        return False, errors

    # Validate items within arrays
    if tab == "profile":
        for i, cat in enumerate(data.get("categories", [])):
            errs = _check_item(f"categories[{i}]", cat, schema["categories_item"])
            errors.extend(errs)
            # Validate nested items
            for j, item in enumerate(cat.get("items", [])):
                if isinstance(item, str):
                    cat["items"][j] = {"text": item}  # auto-fix string→object
                elif isinstance(item, dict):
                    errors.extend(_check_item(f"categories[{i}].items[{j}]", item, schema["categories_item_item"]))
            # Validate tags
            if "tags" in cat and not isinstance(cat["tags"], list):
                errors.append(f"categories[{i}].tags must be array")
        for i, dim in enumerate(data.get("radar", {}).get("dimensions", [])):
            errs = _check_item(f"radar.dimensions[{i}]", dim, schema["radar_dimension"])
            errors.extend(errs)
            if "score" in dim:
                try:
                    s = float(dim["score"])
                    if not (0 <= s <= 1):
                        errors.append(f"radar.dimensions[{i}].score must be 0.0-1.0, got {s}")
                    dim["score"] = s
                except (TypeError, ValueError):
                    errors.append(f"radar.dimensions[{i}].score must be a number")
        # Ensure radar.dimensions exists
        if isinstance(data.get("radar"), dict) and "dimensions" not in data["radar"]:
            data["radar"]["dimensions"] = []

    elif tab == "memory":
        for i, n in enumerate(data.get("nodes", [])):
            errors.extend(_check_item(f"nodes[{i}]", n, schema["node"]))
        for i, l in enumerate(data.get("links", [])):
            errors.extend(_check_item(f"links[{i}]", l, schema["link"]))
        for i, c in enumerate(data.get("cards", [])):
            errors.extend(_check_item(f"cards[{i}]", c, schema["card"]))

    elif tab == "rules":
        for i, r in enumerate(data.get("rules", [])):
            errors.extend(_check_item(f"rules[{i}]", r, schema["rule"]))

    elif tab == "signals":
        for i, e in enumerate(data.get("events", [])):
            errors.extend(_check_item(f"events[{i}]", e, schema["event"]))
        for i, t in enumerate(data.get("timeline", [])):
            errors.extend(_check_item(f"timeline[{i}]", t, schema["timeline_item"]))

    elif tab == "patterns":
        for i, b in enumerate(data.get("bubbles", [])):
            errors.extend(_check_item(f"bubbles[{i}]", b, schema["bubble"]))
        for i, c in enumerate(data.get("cards", [])):
            errors.extend(_check_item(f"cards[{i}]", c, schema["card"]))

    return len(errors) == 0, errors


def _check_item(path, item, spec):
    """Check a single item against its spec {required, optional}."""
    if not isinstance(item, dict):
        return [f"{path}: must be an object, got {type(item).__name__}"]
    errors = []
    for key, expected in spec.get("required", {}).items():
        if key not in item:
            errors.append(f"{path}.{key}: required field missing")
        elif not isinstance(item[key], expected if isinstance(expected, tuple) else (expected,)):
            errors.append(f"{path}.{key}: expected {expected}, got {type(item[key]).__name__}")
    for key, expected in spec.get("optional", {}).items():
        if key in item and item[key] is not None:
            if not isinstance(item[key], expected if isinstance(expected, tuple) else (expected,)):
                errors.append(f"{path}.{key}: expected {expected}, got {type(item[key]).__name__}")
    return errors


def _read_evolve_cache(tab):
    """Read existing cache for a tab, or return empty dict."""
    cache_path = Path(__file__).resolve().parent / ".cache" / "evolve" / f"{tab}.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _merge_evolve_data(tab, existing, new_data):
    """Merge new_data into existing data. Match by id/name, add new, update existing."""
    schema = _EVOLVE_SCHEMAS.get(tab, {})

    if tab == "profile":
        # Merge categories by name
        exist_cats = {c["name"]: c for c in existing.get("categories", [])}
        for cat in new_data.get("categories", []):
            name = cat.get("name", "")
            if name in exist_cats:
                # Update: merge tags and items
                old = exist_cats[name]
                old_tags = set(old.get("tags", []))
                old_tags.update(cat.get("tags", []))
                old["tags"] = list(old_tags)
                # Merge items by text (deduplicate)
                old_texts = {(it["text"] if isinstance(it, dict) else it) for it in old.get("items", [])}
                for item in cat.get("items", []):
                    text = item["text"] if isinstance(item, dict) else item
                    if text not in old_texts:
                        old["items"].append(item)
                if cat.get("icon"):
                    old["icon"] = cat["icon"]
            else:
                exist_cats[name] = cat
        existing["categories"] = list(exist_cats.values())

        # Merge radar dimensions by name
        if "radar" in new_data:
            if "radar" not in existing:
                existing["radar"] = {"dimensions": []}
            exist_dims = {d["name"]: d for d in existing["radar"].get("dimensions", [])}
            for dim in new_data.get("radar", {}).get("dimensions", []):
                exist_dims[dim["name"]] = dim  # replace on match
            existing["radar"]["dimensions"] = list(exist_dims.values())

    else:
        # Generic merge for tabs with id-based items
        for field in schema.get("top_fields", {}):
            if field not in new_data:
                continue
            if not isinstance(new_data[field], list):
                existing[field] = new_data[field]
                continue
            # Merge lists by id
            old_list = existing.get(field, [])
            if tab == "signals" and field == "timeline":
                # Timeline: merge by date
                old_by_date = {t["date"]: t for t in old_list}
                for t in new_data[field]:
                    old_by_date[t["date"]] = t
                existing[field] = sorted(old_by_date.values(), key=lambda x: x.get("date", ""))
            elif all(isinstance(item, dict) and "id" in item for item in new_data[field]):
                old_by_id = {item["id"]: item for item in old_list}
                for item in new_data[field]:
                    old_by_id[item["id"]] = item  # replace on match, add if new
                existing[field] = list(old_by_id.values())
            else:
                # No id field (e.g., links) — just replace
                existing[field] = new_data[field]

    return existing


def _delete_evolve_data(tab, existing, ids):
    """Delete items by id from existing data."""
    ids_set = set(ids)

    if tab == "profile":
        # Delete categories by name
        existing["categories"] = [c for c in existing.get("categories", []) if c.get("name") not in ids_set]
        # Delete radar dimensions by name
        if "radar" in existing:
            existing["radar"]["dimensions"] = [d for d in existing["radar"].get("dimensions", []) if d.get("name") not in ids_set]
    else:
        schema = _EVOLVE_SCHEMAS.get(tab, {})
        for field in schema.get("top_fields", {}):
            items = existing.get(field, [])
            if isinstance(items, list):
                existing[field] = [item for item in items if not (isinstance(item, dict) and item.get("id") in ids_set)]

    return existing


def cmd_evolve_write(args):
    """Write/merge/delete Evolve tab data with schema validation.

    Modes:
      replace  — Replace entire tab data (default)
      merge    — Add new items and update existing ones (match by id/name)
      delete   — Remove items by id/name

    Input: JSON from stdin (for replace/merge) or --ids flag (for delete).
    Output: "OK" on success, error details on failure.
    """
    tab = args.tab
    mode = args.mode

    if tab not in _EVOLVE_SCHEMAS:
        print(f"ERROR: invalid tab '{tab}'. Valid: {', '.join(_EVOLVE_SCHEMAS.keys())}", file=sys.stderr)
        sys.exit(1)

    if mode == "delete":
        ids = [i.strip() for i in (args.ids or "").split(",") if i.strip()]
        if not ids:
            print("ERROR: --ids required for delete mode (comma-separated)", file=sys.stderr)
            sys.exit(1)
        existing = _read_evolve_cache(tab)
        if not existing:
            print("ERROR: no existing data to delete from", file=sys.stderr)
            sys.exit(1)
        result = _delete_evolve_data(tab, existing, ids)
        out_path = _write_evolve_cache(tab, result)
        print(f"OK: deleted {len(ids)} item(s) from {tab} → {out_path}")
        return

    # Read JSON from stdin
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON input — {e}", file=sys.stderr)
        sys.exit(1)

    # Validate schema
    ok, errors = _validate_evolve_data(tab, data)
    if not ok:
        print(f"ERROR: schema validation failed ({len(errors)} issue(s)):", file=sys.stderr)
        for err in errors[:10]:
            print(f"  - {err}", file=sys.stderr)
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more", file=sys.stderr)
        sys.exit(1)

    if mode == "merge":
        existing = _read_evolve_cache(tab)
        result = _merge_evolve_data(tab, existing, data) if existing else data
    else:
        result = data

    out_path = _write_evolve_cache(tab, result)
    print(f"OK: {mode} {tab} → {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CLI tools for analyzing Claude Code / Codex conversation history.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 analyze.py sessions --date 7d --source claude
  python3 analyze.py read <session-id>
  python3 analyze.py search "redis cache" --date 30d
  python3 analyze.py corrections --date 7d --project myproject
  python3 analyze.py errors --date 30d
  python3 analyze.py decisions --date 7d
  python3 analyze.py stats
  python3 analyze.py files --date 7d
  python3 analyze.py highlights --date 7d
""")
    # Shared filter args (added to every subcommand)
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--date", default="7d",
                        help="Time filter: 1d, 7d, 30d, 90d, all (default: 7d)")
    shared.add_argument("--source", default="all",
                        help="Source filter: claude, codex, all (default: all)")
    shared.add_argument("--project", default="",
                        help="Filter by project name (substring match)")
    shared.add_argument("--limit", type=int, default=50,
                        help="Max results (default: 50)")
    shared.add_argument("--json", action="store_true",
                        help="Output as JSON")
    shared.add_argument("--save", default="",
                        help="Save full output to file (prints summary + path instead)")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    sub.add_parser("sessions", parents=[shared], help="List sessions matching filters")

    p_read = sub.add_parser("read", parents=[shared], help="Read a session (human-readable)")
    p_read.add_argument("session", help="Session ID or partial match")
    p_read.add_argument("-v", "--verbose", action="store_true",
                        help="Include tool inputs and results")
    p_read.add_argument("-s", "--summary", action="store_true",
                        help="Summary mode: user messages + assistant conclusions only (no tools)")

    p_search = sub.add_parser("search", parents=[shared], help="Search user messages")
    p_search.add_argument("query", help="Search query")

    p_queries = sub.add_parser("queries", parents=[shared], help="Extract user queries only (no AI responses)")
    p_queries.add_argument("--session", default="", help="Session ID to extract from (omit for cross-session)")
    p_queries.add_argument("--keyword", "-k", default="", help="Filter queries containing keyword")

    sub.add_parser("corrections", parents=[shared], help="Find user correction patterns")
    sub.add_parser("decisions", parents=[shared], help="Find decision points in conversations")
    sub.add_parser("errors", parents=[shared], help="Extract error patterns from tool results")
    sub.add_parser("stats", parents=[shared], help="Show aggregate statistics")
    sub.add_parser("files", parents=[shared], help="Show most-edited files")
    sub.add_parser("highlights", parents=[shared], help="Per-session one-line highlights with signal counts")
    sub.add_parser("evolve-rules", parents=[shared], help="Generate rules JSON for Evolve page")
    sub.add_parser("evolve-signals", parents=[shared], help="Generate signals JSON for Evolve page")
    sub.add_parser("evolve-patterns", parents=[shared], help="Generate patterns JSON for Evolve page")

    p_ew = sub.add_parser("evolve-write", help="Write/merge/delete Evolve tab data (validated)")
    p_ew.add_argument("--tab", required=True, choices=["profile", "memory", "rules", "signals", "patterns"],
                       help="Target tab")
    p_ew.add_argument("--mode", default="replace", choices=["replace", "merge", "delete"],
                       help="Write mode: replace (full), merge (add/update), delete (remove by id)")
    p_ew.add_argument("--ids", default="", help="Comma-separated ids/names for delete mode")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmds = {
        "sessions": cmd_sessions, "read": cmd_read, "search": cmd_search,
        "queries": cmd_queries, "corrections": cmd_corrections,
        "decisions": cmd_decisions, "errors": cmd_errors,
        "stats": cmd_stats, "files": cmd_files, "highlights": cmd_highlights,
        "evolve-rules": cmd_evolve_rules, "evolve-signals": cmd_evolve_signals,
        "evolve-patterns": cmd_evolve_patterns, "evolve-write": cmd_evolve_write,
    }

    save_path = getattr(args, "save", "")
    if save_path:
        # Capture stdout, save full output to file, print summary
        import io
        old_stdout = sys.stdout
        sys.stdout = buf = io.StringIO()
        # Remove limit when saving — get all data
        if hasattr(args, "limit"):
            args.limit = 99999
        cmds[args.command](args)
        full_output = buf.getvalue()
        sys.stdout = old_stdout
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(full_output)
        line_count = full_output.count("\n")
        char_count = len(full_output)
        print(f"Saved {line_count} lines ({char_count} chars) to {save_path}")
        print(f"Use: cat {save_path}  or  sed -n '1,100p' {save_path}  to read in segments")
    else:
        cmds[args.command](args)


if __name__ == "__main__":
    main()
