#!/usr/bin/env python3
"""Claude Code Chat History Viewer — Local Server

Zero-dependency Python server that parses ~/.claude/projects/ JSONL files
and serves a web UI for browsing, searching, and reviewing conversations.
"""

import json
import os
import re
import sys
import time
import hashlib
import threading
import subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECTS_DIR = Path.home() / ".claude" / "projects"
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
INDEX_CACHE = CACHE_DIR / "index.json"
INDEX_SCHEMA_VERSION = 2  # bump when extract_metadata logic changes, to invalidate stale caches
STATIC_DIR = Path(__file__).resolve().parent / "static"
PORT = int(os.environ.get("PORT", 5757))
MAX_SEARCH_WORKERS = 8
MAX_TOOL_RESULT_LEN = 3000
MAX_THINKING_LEN = 800

# Codex CLI paths
CODEX_DIR = Path.home() / ".codex"
CODEX_SESSIONS_DIR = CODEX_DIR / "sessions"
CODEX_ARCHIVED_DIR = CODEX_DIR / "archived_sessions"
CODEX_INDEX_FILE = CODEX_DIR / "session_index.jsonl"

# Shared state (populated at startup)
_index = {"projects": {}, "sessions": {}, "_file_mtimes": {}}
_index_lock = threading.Lock()
_codex_titles = {}  # session_id -> thread_name

# Result cache for heavy endpoints (invalidated on index rebuild)
_result_cache = {}   # key -> (index_gen, result)
_index_gen = 0       # bumped on each build_index()

def _cached(key, compute_fn):
    """Return cached result if index hasn't changed, else compute and cache."""
    gen = _index_gen
    entry = _result_cache.get(key)
    if entry and entry[0] == gen:
        return entry[1]
    result = compute_fn()
    _result_cache[key] = (gen, result)
    return result


# ---------------------------------------------------------------------------
# Project name decoding
# ---------------------------------------------------------------------------
def pretty_project_name(dirname: str) -> str:
    """Convert encoded dir name like '-Users-foo-Desktop-proj-bar' to readable name."""
    home_encoded = str(Path.home()).replace("/", "-").lstrip("-")
    name = dirname.lstrip("-")
    if name.startswith(home_encoded):
        name = name[len(home_encoded) :].lstrip("-")
    # Replace common prefixes for brevity
    for prefix in ("Desktop-proj-", "Desktop-personal-", "Desktop-", "Documents-"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    if not name:
        return "Global"
    return name


# ---------------------------------------------------------------------------
# JSONL Metadata Extraction (fast — for index building)
# ---------------------------------------------------------------------------
def extract_metadata(filepath: str) :
    """Quick scan of a JSONL file to extract session metadata."""
    title = None
    custom_title = None
    session_id = None
    first_ts = None
    last_ts = None
    user_texts = []  # (message_index, text, timestamp)
    assistant_snippets = []  # (message_index, first 300 chars of text)
    msg_index = 0
    # Insight extraction accumulators
    _tool_daily = {}     # (day, tool_name) -> count
    _file_refs = {}      # file_path -> count
    _error_list = []     # [(normalized_error, day)]
    _snippet_list = []   # [(lang, code, context, applied)]
    _code_re = re.compile(r'```(\w*)\n([\s\S]*?)```')
    _err_re = re.compile(
        r'((?:Traceback.*?:\s*)?'
        r'(?:(?:Error|Exception|TypeError|ValueError|KeyError|AttributeError|'
        r'ImportError|ModuleNotFoundError|NameError|IndexError|RuntimeError|'
        r'SyntaxError|FileNotFoundError|PermissionError|OSError|IOError|'
        r'ConnectionError|TimeoutError)'
        r'[:\s].{0,120}))',
        re.IGNORECASE
    )
    _prev_user_msg = ""

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = obj.get("type")

                if msg_type == "ai-title":
                    title = obj.get("aiTitle", "")
                    session_id = obj.get("sessionId", "")
                    continue

                # User-given session name (set via Claude Code). Written multiple
                # times per session; the last occurrence is the most recent name.
                if msg_type == "custom-title":
                    ct = obj.get("customTitle", "")
                    if ct:
                        custom_title = ct
                    if not session_id:
                        session_id = obj.get("sessionId", "")
                    continue

                if msg_type == "user" and not obj.get("toolUseResult"):
                    ts = obj.get("timestamp", "")
                    if not first_ts and ts:
                        first_ts = ts
                    last_ts = ts or last_ts
                    if not session_id:
                        session_id = obj.get("sessionId", "")

                    # Extract text content (filter system blocks, keep user text)
                    raw_content = obj.get("message", {}).get("content", [])
                    text = _extract_user_text(raw_content)
                    if text.strip():
                        user_texts.append(
                            {"idx": msg_index, "text": text[:2000], "ts": ts}
                        )
                    _prev_user_msg = text[:200] if text.strip() else _prev_user_msg
                    msg_index += 1

                elif msg_type == "assistant":
                    ts = obj.get("timestamp", "")
                    last_ts = ts or last_ts
                    # Extract first text snippet for correction detection
                    a_content = obj.get("message", {}).get("content", [])
                    a_texts = []
                    _code_blocks = []
                    _tool_writes = []
                    if isinstance(a_content, list):
                        for blk in a_content:
                            if isinstance(blk, dict) and blk.get("type") == "text":
                                t = blk.get("text", "").strip()
                                if t:
                                    a_texts.append(t)
                                # Insight: extract code snippets
                                for m in _code_re.finditer(blk.get("text", "")):
                                    lang = m.group(1) or ""
                                    code = m.group(2).strip()
                                    if 3 < len(code.split("\n")) <= 50 and len(code) > 30:
                                        _code_blocks.append({"lang": lang, "code": code[:1000]})
                            elif isinstance(blk, dict) and blk.get("type") == "tool_use":
                                # Insight: tool usage + file refs
                                tool_name = blk.get("name", "unknown")
                                day = (first_ts or "")[:10]
                                if day:
                                    key = (day, tool_name)
                                    _tool_daily[key] = _tool_daily.get(key, 0) + 1
                                inp = blk.get("input", {})
                                fp = inp.get("file_path") or inp.get("path") or ""
                                if fp and not fp.startswith("/tmp"):
                                    _file_refs[fp] = _file_refs.get(fp, 0) + 1
                                if tool_name in ("Edit", "Write"):
                                    w = inp.get("new_string", "") or inp.get("content", "")
                                    if w:
                                        _tool_writes.append(w[:2000])
                    elif isinstance(a_content, str) and a_content.strip():
                        a_texts.append(a_content.strip())
                    if a_texts:
                        snippet = a_texts[0][:300]
                        assistant_snippets.append({"idx": msg_index, "text": snippet, "ts": ts})
                    # Insight: determine applied status for code snippets
                    for cb in _code_blocks:
                        applied = False
                        if _tool_writes:
                            code_lines = set(cb["code"].strip().split("\n")[:10])
                            for tw in _tool_writes:
                                tw_lines = set(tw.strip().split("\n")[:20])
                                if len(code_lines & tw_lines) >= min(2, len(code_lines)):
                                    applied = True
                                    break
                        _snippet_list.append((cb["lang"], cb["code"], _prev_user_msg, applied))
                    msg_index += 1

                elif msg_type == "user" and obj.get("toolUseResult"):
                    # Insight: extract errors from tool results
                    content = obj.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for blk in content:
                            if isinstance(blk, dict) and blk.get("type") == "tool_result":
                                result_text = blk.get("content", "")
                                if isinstance(result_text, list):
                                    result_text = json.dumps(result_text)
                                if isinstance(result_text, str):
                                    day = (first_ts or "")[:10]
                                    for m in _err_re.finditer(result_text[:5000]):
                                        norm = _normalize_error(m.group(1))
                                        if len(norm) >= 10:
                                            _error_list.append((norm, day))
                    msg_index += 1

    except Exception:
        return None

    if not session_id:
        session_id = Path(filepath).stem

    # Title priority: user-given custom-title > ai-title > first user text.
    if custom_title:
        title = custom_title
    elif not title and user_texts:
        title = user_texts[0]["text"][:80]

    return {
        "id": session_id,
        "title": title or "Untitled",
        "date": first_ts or "",
        "lastDate": last_ts or "",
        "filePath": filepath,
        "fileSize": os.path.getsize(filepath),
        "userMessageCount": len(user_texts),
        "userTexts": user_texts,
        "assistantSnippets": assistant_snippets,
        "preview": user_texts[0]["text"][:200] if user_texts else "",
        # Insight data (consumed by build_index, not stored in _index cache)
        "_insight_tools": _tool_daily,
        "_insight_files": _file_refs,
        "_insight_errors": _error_list,
        "_insight_snippets": _snippet_list,
    }


def _extract_raw_text(content) -> str:
    """Extract raw text (before tag stripping) for system detection."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return ""


def _extract_text(content) -> str:
    """Extract plain text from message content (string or content blocks)."""
    if isinstance(content, str):
        return _strip_tags(content)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return _strip_tags(" ".join(parts))
    return ""


def _strip_tags(text: str) -> str:
    """Remove XML-like tags from Claude Code internal format."""
    cleaned = re.sub(r"<[^>]+>", "", text).strip()
    # Remove leading system noise lines
    lines = cleaned.split("\n")
    filtered = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip known system-generated lines
        if stripped.startswith(("The user opened the file", "The user selected the line")):
            continue
        filtered.append(line)
    return "\n".join(filtered).strip()


def _is_system_text(text: str) -> bool:
    """Check if a single text block is purely system-generated."""
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.startswith(("<ide_", "<system-reminder", "<command-")):
        return True
    return False


def _extract_user_text(content) -> str:
    """Extract user-authored text from content, skipping system-injected blocks."""
    if isinstance(content, str):
        return "" if _is_system_text(content) else _strip_tags(content)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if not _is_system_text(text):
                    parts.append(text)
        return _strip_tags(" ".join(parts))
    return ""


# ---------------------------------------------------------------------------
# Shared: truncate tool output (string or list with base64 images)
# ---------------------------------------------------------------------------
def _truncate_tool_output(output):
    """Truncate tool output, handling both string and list (Codex CUA) formats.
    Strips base64 image data and truncates text content."""
    if isinstance(output, list):
        cleaned = []
        for item in output:
            if isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type in ("input_image", "image") or "image_url" in item:
                    # Replace base64 image with placeholder
                    cleaned.append({"type": "image", "alt": "[Screenshot]"})
                elif "text" in item:
                    text = item.get("text", "")
                    if len(text) > MAX_TOOL_RESULT_LEN:
                        text = text[:MAX_TOOL_RESULT_LEN] + "…[truncated]"
                    cleaned.append({**item, "text": text})
                else:
                    cleaned.append(item)
            else:
                cleaned.append(item)
        return json.dumps(cleaned, ensure_ascii=False)
    if isinstance(output, str) and len(output) > MAX_TOOL_RESULT_LEN:
        return output[:MAX_TOOL_RESULT_LEN] + "…[truncated]"
    return output


# ---------------------------------------------------------------------------
# Codex CLI — helpers
# ---------------------------------------------------------------------------
def _load_codex_titles():
    """Load Codex session titles from session_index.jsonl."""
    global _codex_titles
    _codex_titles = {}
    if not CODEX_INDEX_FILE.exists():
        return
    try:
        with open(CODEX_INDEX_FILE, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    sid = obj.get("id", "")
                    name = obj.get("thread_name", "")
                    if sid and name:
                        _codex_titles[sid] = name
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass


def _codex_project_name(cwd: str) -> str:
    """Derive a readable project name from Codex session cwd."""
    if not cwd:
        return "Codex"
    home = str(Path.home())
    name = cwd
    if name.startswith(home):
        name = name[len(home):].lstrip("/")
    for prefix in ("Desktop/proj/", "Desktop/personal/", "Desktop/", "Documents/"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name or "Codex"


_CODEX_TOOL_NAMES = {
    "shell": "Bash", "exec_command": "Bash", "write_stdin": "Bash",
    "apply_patch": "Edit", "read_file": "Read", "write_file": "Write",
    "list_directory": "Glob",
}


# ---------------------------------------------------------------------------
# Codex CLI — metadata extraction
# ---------------------------------------------------------------------------
def extract_codex_metadata(filepath: str):
    """Quick scan of a Codex JSONL file to extract session metadata."""
    session_id = None
    first_ts = None
    last_ts = None
    cwd = None
    user_texts = []
    assistant_snippets = []
    msg_index = 0
    # Insight extraction accumulators
    _tool_daily = {}
    _file_refs = {}
    _error_list = []
    _err_re = re.compile(
        r'((?:Traceback.*?:\s*)?'
        r'(?:(?:Error|Exception|TypeError|ValueError|KeyError|AttributeError|'
        r'ImportError|ModuleNotFoundError|NameError|IndexError|RuntimeError|'
        r'SyntaxError|FileNotFoundError|PermissionError|OSError|IOError|'
        r'ConnectionError|TimeoutError)'
        r'[:\s].{0,120}))',
        re.IGNORECASE
    )

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = obj.get("timestamp", "")
                if not first_ts and ts:
                    first_ts = ts
                last_ts = ts or last_ts
                rec_type = obj.get("type")
                payload = obj.get("payload", {})

                if rec_type == "session_meta":
                    session_id = payload.get("id", "")
                    cwd = payload.get("cwd", "")

                elif rec_type == "event_msg" and payload.get("type") == "user_message":
                    text = payload.get("message", "")
                    if text.strip():
                        user_texts.append({"idx": msg_index, "text": text[:2000], "ts": ts})
                    msg_index += 1

                elif rec_type == "response_item":
                    p_type = payload.get("type")
                    if p_type == "message" and payload.get("role") == "assistant":
                        blocks = payload.get("content", [])
                        for blk in blocks:
                            if isinstance(blk, dict) and blk.get("type") == "output_text":
                                t = blk.get("text", "").strip()
                                if t:
                                    assistant_snippets.append({"idx": msg_index, "text": t[:300], "ts": ts})
                                    break
                        msg_index += 1
                    elif p_type in ("function_call", "custom_tool_call"):
                        # Insight: tool usage + file refs
                        raw_name = payload.get("name", "unknown")
                        tool_name = _CODEX_TOOL_NAMES.get(raw_name, raw_name)
                        day = (first_ts or "")[:10]
                        if day:
                            key = (day, tool_name)
                            _tool_daily[key] = _tool_daily.get(key, 0) + 1
                        args_str = payload.get("arguments", "{}")
                        try:
                            args = json.loads(args_str) if isinstance(args_str, str) else {}
                        except json.JSONDecodeError:
                            args = {}
                        fp = args.get("file_path") or args.get("path") or ""
                        if fp and not fp.startswith("/tmp"):
                            _file_refs[fp] = _file_refs.get(fp, 0) + 1
                        msg_index += 1
                    elif p_type in ("function_call_output", "custom_tool_call_output"):
                        # Insight: errors from tool output
                        output = payload.get("output", "")
                        if isinstance(output, str):
                            day = (first_ts or "")[:10]
                            for m in _err_re.finditer(output[:5000]):
                                norm = _normalize_error(m.group(1))
                                if len(norm) >= 10:
                                    _error_list.append((norm, day))
                        msg_index += 1
    except Exception:
        return None

    if not session_id:
        stem = Path(filepath).stem
        parts = stem.split("-")
        session_id = "-".join(parts[-5:]) if len(parts) >= 6 else stem

    title = _codex_titles.get(session_id, "")
    if not title and user_texts:
        title = user_texts[0]["text"][:80]

    return {
        "id": "codex-" + session_id,
        "title": title or "Untitled",
        "date": first_ts or "",
        "lastDate": last_ts or "",
        "filePath": filepath,
        "fileSize": os.path.getsize(filepath),
        "userMessageCount": len(user_texts),
        "userTexts": user_texts,
        "assistantSnippets": assistant_snippets,
        "preview": user_texts[0]["text"][:200] if user_texts else "",
        "source": "codex",
        "cwd": cwd or "",
        "_insight_tools": _tool_daily,
        "_insight_files": _file_refs,
        "_insight_errors": _error_list,
        "_insight_snippets": [],
    }


# ---------------------------------------------------------------------------
# Codex CLI — full session loading
# ---------------------------------------------------------------------------
def load_codex_session(session_id: str):
    """Load and parse a full Codex conversation by session ID."""
    with _index_lock:
        meta = _index.get("sessions", {}).get(session_id)
    if not meta or meta.get("source") != "codex":
        return None

    filepath = meta["filePath"]
    if not os.path.exists(filepath):
        return None

    messages = []

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = obj.get("timestamp", "")
            rec_type = obj.get("type")
            payload = obj.get("payload", {})

            # User message
            if rec_type == "event_msg" and payload.get("type") == "user_message":
                text = payload.get("message", "")
                if text.strip():
                    messages.append({
                        "id": payload.get("client_id", ""),
                        "type": "user",
                        "timestamp": ts,
                        "isSidechain": False,
                        "content": [{"type": "text", "text": text}],
                    })

            elif rec_type == "response_item":
                p_type = payload.get("type")

                # Assistant text
                if p_type == "message" and payload.get("role") == "assistant":
                    blocks = payload.get("content", [])
                    texts = [b.get("text", "") for b in blocks if b.get("type") == "output_text"]
                    text = "\n".join(texts)
                    if text.strip():
                        messages.append({
                            "id": "", "type": "assistant", "timestamp": ts,
                            "isSidechain": False,
                            "content": [{"type": "text", "text": text}],
                        })

                # Tool call
                elif p_type in ("function_call", "custom_tool_call"):
                    name = payload.get("name", "")
                    if p_type == "function_call":
                        args_str = payload.get("arguments", "{}")
                        try:
                            inp = json.loads(args_str)
                        except (json.JSONDecodeError, TypeError):
                            inp = {"raw": args_str}
                    else:
                        raw = payload.get("input", "")
                        inp = {"raw": raw[:500] + "…" if len(raw) > 500 else raw}
                    # Truncate large values
                    inp_display = {}
                    for k, v in inp.items():
                        if isinstance(v, str) and len(v) > 500:
                            inp_display[k] = v[:500] + "…[truncated]"
                        else:
                            inp_display[k] = v
                    messages.append({
                        "id": "", "type": "assistant", "timestamp": ts,
                        "isSidechain": False,
                        "content": [{
                            "type": "tool_use",
                            "name": _CODEX_TOOL_NAMES.get(name, name),
                            "id": payload.get("call_id", ""),
                            "input": inp_display,
                        }],
                    })

                # Tool result
                elif p_type in ("function_call_output", "custom_tool_call_output"):
                    output = payload.get("output", "")
                    output = _truncate_tool_output(output)
                    messages.append({
                        "id": "", "type": "tool_result", "timestamp": ts,
                        "isSidechain": False,
                        "content": [{
                            "type": "tool_result",
                            "toolUseId": payload.get("call_id", ""),
                            "content": output,
                        }],
                    })

    return {
        "id": session_id,
        "title": meta.get("title", "Untitled"),
        "project": meta.get("projectName", ""),
        "date": meta.get("date", ""),
        "filePath": filepath,
        "messages": messages,
        "source": "codex",
    }


# ---------------------------------------------------------------------------
# Insight DB storage (called during index build for changed sessions)
# ---------------------------------------------------------------------------
def _store_session_insights(meta):
    """Extract insight data from meta and store in DB."""
    import db as _db
    sid = meta["id"]
    project = meta.get("projectName", "")
    date_str = meta.get("date", "")

    _db.clear_session_insights(sid)

    tool_daily = meta.get("_insight_tools", {})
    if tool_daily:
        _db.bulk_insert_tool_usage([
            (sid, day, tool, count) for (day, tool), count in tool_daily.items()
        ])

    file_refs = meta.get("_insight_files", {})
    if file_refs:
        _db.bulk_insert_file_refs([
            (sid, fp, count, project) for fp, count in file_refs.items()
        ])

    error_list = meta.get("_insight_errors", [])
    if error_list:
        err_agg = {}
        for norm, day in error_list:
            if norm not in err_agg:
                err_agg[norm] = {"day": day, "count": 0}
            err_agg[norm]["count"] += 1
        _db.bulk_insert_errors([
            (sid, key, data["day"], project, data["count"])
            for key, data in err_agg.items()
        ])

    snippet_list = meta.get("_insight_snippets", [])
    if snippet_list:
        _db.bulk_insert_snippets([
            (sid, lang, code, context, date_str, int(applied))
            for lang, code, context, applied in snippet_list
        ])


# ---------------------------------------------------------------------------
# Index Building (with disk cache)
# ---------------------------------------------------------------------------
def build_index(force: bool = False) -> dict:
    """Scan all JSONL files and build/update the metadata index + SQLite DB."""
    global _index, _index_gen

    import db as _db
    _db.init_db()

    # Discover JSONL files
    jsonl_files = []
    if PROJECTS_DIR.exists():
        for proj_dir in sorted(PROJECTS_DIR.iterdir()):
            if not proj_dir.is_dir():
                continue
            for f in proj_dir.glob("*.jsonl"):
                jsonl_files.append((str(f), proj_dir.name))

    # Load cached index
    cached = {}
    if not force and INDEX_CACHE.exists():
        try:
            with open(INDEX_CACHE, "r") as f:
                cached = json.load(f)
            # Discard cache built by an older metadata schema (e.g. pre custom-title)
            if cached.get("_schema_version") != INDEX_SCHEMA_VERSION:
                cached = {}
        except Exception:
            cached = {}

    cached_mtimes = cached.get("_file_mtimes", {})
    cached_sessions = cached.get("sessions", {})

    # Determine which files need (re)parsing
    current_files = {}
    to_parse = []
    for fpath, proj_name in jsonl_files:
        mtime = os.path.getmtime(fpath)
        current_files[fpath] = mtime
        if fpath not in cached_mtimes or cached_mtimes[fpath] != mtime:
            to_parse.append((fpath, proj_name))

    print(f"Index: {len(jsonl_files)} files, {len(to_parse)} need parsing")

    # Parse files that changed (parallel)
    new_sessions = {}
    if to_parse:
        with ThreadPoolExecutor(max_workers=MAX_SEARCH_WORKERS) as pool:
            futures = {
                pool.submit(extract_metadata, fp): (fp, pn) for fp, pn in to_parse
            }
            for future in as_completed(futures):
                fp, pn = futures[future]
                try:
                    meta = future.result()
                    if meta:
                        meta["project"] = pn
                        meta["projectName"] = pretty_project_name(pn)
                        meta["source"] = "claude"
                        meta["_mtime"] = current_files.get(fp, 0)
                        new_sessions[meta["id"]] = meta
                        _db.upsert_session(meta, meta.get("userTexts", []), meta.get("assistantSnippets", []))
                        _store_session_insights(meta)
                except Exception as e:
                    print(f"Error parsing {fp}: {e}")

    # Merge with cache (keep unchanged sessions from cache) — O(N) via dict lookup
    new_by_path = {}
    for sid, meta in new_sessions.items():
        fp = meta.get("filePath")
        if fp:
            new_by_path[fp] = (sid, meta)
    cached_by_path = {}
    for sid, meta in cached_sessions.items():
        fp = meta.get("filePath")
        if fp:
            cached_by_path[fp] = (sid, meta)

    sessions = {}
    for fpath, proj_name in jsonl_files:
        if fpath in new_by_path:
            sid, meta = new_by_path[fpath]
            sessions[sid] = meta
        elif fpath in cached_by_path:
            sid, meta = cached_by_path[fpath]
            sessions[sid] = meta

    # ── Codex session scanning ──
    _load_codex_titles()
    codex_files = []
    if CODEX_SESSIONS_DIR.exists():
        for jsonl_file in CODEX_SESSIONS_DIR.rglob("*.jsonl"):
            codex_files.append(str(jsonl_file))
    if CODEX_ARCHIVED_DIR.exists():
        for jsonl_file in CODEX_ARCHIVED_DIR.glob("*.jsonl"):
            codex_files.append(str(jsonl_file))

    codex_to_parse = []
    for fpath in codex_files:
        mtime = os.path.getmtime(fpath)
        current_files[fpath] = mtime
        if fpath not in cached_mtimes or cached_mtimes[fpath] != mtime:
            codex_to_parse.append(fpath)

    print(f"Codex: {len(codex_files)} files, {len(codex_to_parse)} need parsing")

    codex_new = {}
    if codex_to_parse:
        with ThreadPoolExecutor(max_workers=MAX_SEARCH_WORKERS) as pool:
            futures = {pool.submit(extract_codex_metadata, fp): fp for fp in codex_to_parse}
            for future in as_completed(futures):
                fp = futures[future]
                try:
                    meta = future.result()
                    if meta:
                        meta["projectName"] = _codex_project_name(meta.get("cwd", ""))
                        meta["project"] = "codex"
                        meta["_mtime"] = current_files.get(fp, 0)
                        codex_new[meta["id"]] = meta
                        _db.upsert_session(meta, meta.get("userTexts", []), meta.get("assistantSnippets", []))
                        _store_session_insights(meta)
                except Exception as e:
                    print(f"Error parsing Codex {fp}: {e}")

    # Merge Codex sessions — O(N) via dict lookup
    codex_new_by_path = {}
    for sid, meta in codex_new.items():
        fp = meta.get("filePath")
        if fp:
            codex_new_by_path[fp] = (sid, meta)
    for fpath in codex_files:
        if fpath in codex_new_by_path:
            sid, meta = codex_new_by_path[fpath]
            sessions[sid] = meta
        elif fpath in cached_by_path:
            sid, meta = cached_by_path[fpath]
            sessions[sid] = meta

    # Build project grouping
    projects = {}
    for sid, meta in sessions.items():
        pname = meta.get("projectName", "unknown")
        if pname not in projects:
            projects[pname] = {"name": pname, "dirName": meta.get("project", ""), "sessionCount": 0}
        projects[pname]["sessionCount"] += 1

    index = {
        "_schema_version": INDEX_SCHEMA_VERSION,
        "projects": projects,
        "sessions": sessions,
        "_file_mtimes": current_files,
    }

    # Backfill DB from cached sessions (only if DB is missing entries)
    db_count = _db.get_conn().execute("SELECT count(*) FROM sessions").fetchone()[0]
    if db_count < len(sessions):
        backfill_count = 0
        for sid, meta in sessions.items():
            exists = _db.get_conn().execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone()
            if not exists:
                _db.upsert_session(meta, meta.get("userTexts", []), meta.get("assistantSnippets", []))
                backfill_count += 1
        if backfill_count:
            print(f"DB backfill: {backfill_count} sessions")

    # Backfill insight tables if most sessions lack insight data
    insight_sessions = _db.get_conn().execute(
        "SELECT COUNT(DISTINCT session_id) FROM insight_tool_usage"
    ).fetchone()[0]
    if insight_sessions < len(sessions) * 0.5 and len(sessions) > 0:
        # Collect session IDs already in insight tables
        existing_insight_sids = set(
            r[0] for r in _db.get_conn().execute(
                "SELECT DISTINCT session_id FROM insight_tool_usage"
            ).fetchall()
        )
        print(f"Backfilling insight tables ({len(sessions) - len(existing_insight_sids)} sessions)...")
        backfill_t = time.time()
        backfill_n = 0
        for sid, meta in sessions.items():
            if sid in existing_insight_sids:
                continue
            fp = meta.get("filePath", "")
            source = meta.get("source", "claude")
            if fp and os.path.exists(fp):
                try:
                    fresh = extract_codex_metadata(fp) if source == "codex" else extract_metadata(fp)
                    if fresh:
                        fresh["projectName"] = meta.get("projectName", "")
                        fresh["date"] = meta.get("date", "")
                        _store_session_insights(fresh)
                        backfill_n += 1
                except Exception:
                    pass
        print(f"  Insight backfill: {backfill_n} sessions in {time.time() - backfill_t:.1f}s")

    # Strip non-serializable insight data before cache write
    # NOTE: userTexts/assistantSnippets kept for now — analyze.py subprocess still reads them.
    # They can be stripped after analyze.py is refactored to use DB queries directly.
    for sid, meta in sessions.items():
        for k in ("_insight_tools", "_insight_files", "_insight_errors", "_insight_snippets"):
            meta.pop(k, None)

    # Save to cache
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(INDEX_CACHE, "w") as f:
            json.dump(index, f, ensure_ascii=False)
    except Exception as e:
        print(f"Cache write error: {e}")

    with _index_lock:
        _index = index
        _index_gen += 1
        _result_cache.clear()

    # Rebuild DB FTS + aggregates if anything changed
    if to_parse or codex_to_parse:
        try:
            _db.rebuild_fts()
            _db.refresh_aggregates()
        except Exception as e:
            print(f"DB post-process error: {e}")

    db_count = _db.get_conn().execute("SELECT count(*) FROM sessions").fetchone()[0]
    print(f"Index ready: {len(sessions)} sessions across {len(projects)} projects (DB: {db_count})")
    return index


# ---------------------------------------------------------------------------
# Session Loading (full parse for conversation view)
# ---------------------------------------------------------------------------
def load_session(session_id: str) :
    """Load and parse a full conversation by session ID."""
    with _index_lock:
        meta = _index.get("sessions", {}).get(session_id)
    if not meta:
        return None

    # Route Codex sessions to dedicated loader
    if meta.get("source") == "codex":
        return load_codex_session(session_id)

    filepath = meta["filePath"]
    if not os.path.exists(filepath):
        return None

    title = meta.get("title", "Untitled")
    project = meta.get("projectName", "")
    date = meta.get("date", "")
    return load_session_from_file(filepath, session_id, title, project, date)


def load_session_from_file(filepath: str, session_id: str, title: str = "",
                           project: str = "", date: str = ""):
    """Load and parse a full conversation from a JSONL file path."""
    if not os.path.exists(filepath):
        return None

    messages = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type")
            if msg_type not in ("user", "assistant"):
                continue

            msg_data = obj.get("message", {})
            content = msg_data.get("content", [])
            is_tool_result = bool(obj.get("toolUseResult"))

            parsed = {
                "id": obj.get("uuid", ""),
                "type": "tool_result" if is_tool_result else msg_type,
                "timestamp": obj.get("timestamp", ""),
                "isSidechain": obj.get("isSidechain", False),
                "content": _parse_content(content),
            }
            messages.append(parsed)

    return {
        "id": session_id,
        "title": title,
        "project": project,
        "date": date,
        "filePath": filepath,
        "messages": messages,
    }


def _parse_content(content) -> list:
    """Parse message content blocks into display-ready format."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]

    blocks = []
    if not isinstance(content, list):
        return blocks

    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")

        if btype == "text":
            text = block.get("text", "")
            if not text.strip():
                continue
            # Skip purely system blocks
            s = text.strip()
            if s.startswith(("<system-reminder", "<command-")):
                continue
            # Strip IDE/system tags, keep user content
            cleaned = _strip_tags(text)
            if cleaned.strip():
                blocks.append({"type": "text", "text": cleaned})

        elif btype == "image":
            blocks.append({"type": "image", "alt": "[Image attachment]"})

        elif btype == "tool_use":
            inp = block.get("input", {})
            tool_name = block.get("name", "")
            # Truncate large input values (but keep Agent prompt intact)
            inp_display = {}
            for k, v in inp.items():
                if isinstance(v, str) and len(v) > 500:
                    if tool_name == "Agent" and k == "prompt":
                        inp_display[k] = v
                    else:
                        inp_display[k] = v[:500] + "…[truncated]"
                else:
                    inp_display[k] = v
            blocks.append({
                "type": "tool_use",
                "name": block.get("name", ""),
                "id": block.get("id", ""),
                "input": inp_display,
            })

        elif btype == "tool_result":
            raw = block.get("content", "")
            raw = _truncate_tool_output(raw)
            blocks.append({
                "type": "tool_result",
                "toolUseId": block.get("tool_use_id", ""),
                "content": raw,
            })

        elif btype == "thinking":
            text = block.get("thinking", "")
            blocks.append({
                "type": "thinking",
                "text": text[:MAX_THINKING_LEN] + "…" if len(text) > MAX_THINKING_LEN else text,
            })

    return blocks


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def _tokenize_query(query: str) -> list:
    """Split query into tokens by whitespace and punctuation for fuzzy matching."""
    tokens = re.split(r"""[\s，。、！？；：""''（）【】《》,.!?;:()\[\]<>\-—…·]+""", query)
    return [t for t in tokens if len(t) >= 2]


def _fuzzy_match(text_lower: str, query_lower: str, tokens: list):
    """Returns (matched, score). Exact substring → 1.0, token-based → ratio."""
    if query_lower in text_lower:
        return True, 1.0
    if not tokens:
        return False, 0
    matched = sum(1 for t in tokens if t in text_lower)
    ratio = matched / len(tokens)
    # Adaptive threshold: fewer tokens → more lenient
    threshold = 0.4 if len(tokens) <= 3 else 0.6
    if ratio >= threshold:
        return True, ratio
    return False, 0


def search_sessions(query: str) -> list:
    """Search user messages via SQLite FTS5 + title fuzzy fallback."""
    if not query or len(query) < 2:
        return []

    import db as _db
    results = []
    seen = set()  # (session_id, idx) dedup

    # 1) FTS5 search on message content (fast, indexed)
    fts_rows = _db.search_fts(query, limit=100)
    for row in fts_rows:
        key = (row["session_id"], row["idx"])
        if key in seen:
            continue
        seen.add(key)
        text = row.get("text", "")
        results.append({
            "sessionId": row["session_id"],
            "title": row.get("title", "Untitled"),
            "project": row.get("project_name", ""),
            "date": row.get("ts", ""),
            "messageIndex": row["idx"],
            "snippet": _make_snippet(text, query.lower()),
            "timestamp": row.get("ts", ""),
            "matchType": "content",
            "score": 0.9,
        })

    # 2) Title fuzzy match (still in-memory, but lightweight — one string per session)
    query_lower = query.lower()
    tokens = _tokenize_query(query_lower)
    with _index_lock:
        sessions = dict(_index.get("sessions", {}))
    for sid, meta in sessions.items():
        title = meta.get("title", "Untitled")
        matched, score = _fuzzy_match(title.lower(), query_lower, tokens)
        if matched and (sid, 0) not in seen:
            seen.add((sid, 0))
            results.append({
                "sessionId": sid,
                "title": title,
                "project": meta.get("projectName", ""),
                "date": meta.get("date", ""),
                "messageIndex": 0,
                "snippet": title,
                "timestamp": meta.get("date", ""),
                "matchType": "title",
                "score": score,
            })

    results.sort(key=lambda r: (-r.get("score", 0), r.get("date", "")), reverse=False)
    return results[:100]


def _make_snippet(text: str, query: str, tokens: list = None, ctx: int = 80) -> str:
    """Create a context snippet around the first match."""
    idx = text.lower().find(query)
    if idx == -1 and tokens:
        # Find first matching token for snippet context
        for t in tokens:
            idx = text.lower().find(t)
            if idx != -1:
                break
    if idx == -1:
        return text[:160]
    start = max(0, idx - ctx)
    end = min(len(text), idx + len(query) + ctx)
    snippet = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
    return snippet


def _normalize_error(msg: str) -> str:
    """Normalize error message for grouping: strip paths, numbers, hashes."""
    s = msg.strip()
    # Remove file paths
    s = re.sub(r'(/[^\s:]+)', '<path>', s)
    # Remove line numbers
    s = re.sub(r'line \d+', 'line N', s, flags=re.IGNORECASE)
    # Remove hex addresses
    s = re.sub(r'0x[0-9a-f]+', '0xN', s, flags=re.IGNORECASE)
    return s[:150]



# ---------------------------------------------------------------------------
# AI Engine detection and execution (Codex → claude -p fallback)
# ---------------------------------------------------------------------------
_ai_engine_cache = None  # "codex" | "claude" | ""


def _normalize_ai_engine(engine: str) -> str:
    """Normalize and validate the requested local AI CLI."""
    engine = (engine or "auto").strip().lower()
    if engine not in {"auto", "codex", "claude"}:
        raise ValueError(f"Invalid AI engine: {engine}")
    return engine




def _detect_ai_engine():
    """Auto-detect available AI CLI: Claude Code first, then Codex."""
    global _ai_engine_cache
    if _ai_engine_cache is not None:
        return _ai_engine_cache
    for name, cmd in [("claude", ["claude", "--version"]), ("codex", ["codex", "--version"])]:
        try:
            subprocess.run(cmd, capture_output=True, timeout=5)
            _ai_engine_cache = name
            print(f"AI engine: {name}")
            return _ai_engine_cache
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
    _ai_engine_cache = ""
    return _ai_engine_cache


def _run_ai_engine(prompt, allow_write=False, timeout=300, engine_override="auto"):
    """Execute prompt via detected AI engine. Returns (stdout, stderr, returncode).
    Raises FileNotFoundError if no engine available.
    Auto-falls back from codex to claude on codex errors."""
    engine_override = _normalize_ai_engine(engine_override)
    engine = engine_override if engine_override != "auto" else _detect_ai_engine()
    if engine == "codex":
        sandbox = "workspace-write" if allow_write else "read-only"
        r = subprocess.run(
            ["codex", "--sandbox", sandbox, "--ask-for-approval", "never",
             "exec", "--skip-git-repo-check", prompt],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        # Fallback: if codex failed and engine was auto-detected, try claude
        if r.returncode != 0 and engine_override in ("auto", "", None):
            print(f"Codex failed (rc={r.returncode}), falling back to claude")
            engine = "claude"
        else:
            return r.stdout, r.stderr, r.returncode
    if engine == "claude":
        r = subprocess.run(
            ["claude", "-p"],
            input=prompt,
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout, r.stderr, r.returncode
    raise FileNotFoundError(
        "No AI engine found. Install Codex (npm i -g @openai/codex) "
        "or Claude Code (npm i -g @anthropic-ai/claude-code)."
    )


def _run_ai_engine_stream(prompt, allow_write=False, timeout=300, engine_override="auto"):
    """Execute prompt via detected AI engine, yielding SSE events as JSONL lines arrive.

    Yields dicts: {"type": "tool", "name": ..., "status": ...}
                  {"type": "text", "content": ...}
                  {"type": "done", "content": ...}
                  {"type": "error", "message": ...}

    Auto-falls back from codex to claude on codex errors (e.g. usage limits).
    """
    engine_override = _normalize_ai_engine(engine_override)
    engine = engine_override if engine_override != "auto" else _detect_ai_engine()
    if not engine:
        yield {"type": "error", "message": "No AI engine found"}
        return

    # For codex with auto-detection: quick health check before committing.
    # Codex retries internally (5x WS + 5x HTTP) which can take 30-60s.
    # Instead, run a fast test with a tiny prompt + 8s timeout.
    if engine == "codex" and engine_override in ("auto", "", None):
        try:
            test = subprocess.run(
                ["codex", "--sandbox", "read-only", "--ask-for-approval", "never",
                 "exec", "--json", "--skip-git-repo-check", "echo ok"],
                capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL,
            )
            # Check for error events in output
            has_error = False
            for line in test.stdout.strip().split("\n"):
                try:
                    obj = json.loads(line)
                    if obj.get("type") in ("error", "turn.failed"):
                        has_error = True
                        break
                except (json.JSONDecodeError, ValueError):
                    pass
            if test.returncode != 0 or has_error:
                raise RuntimeError("codex health check failed")
        except (subprocess.TimeoutExpired, RuntimeError, FileNotFoundError, OSError) as e:
            yield {"type": "text", "content": f"Codex unavailable, falling back to Claude...\n"}
            yield from _run_engine_stream_inner("claude", prompt, allow_write, timeout)
            return
        # Codex passed health check — use it
        yield from _run_engine_stream_inner("codex", prompt, allow_write, timeout)
        return

    yield from _run_engine_stream_inner(engine, prompt, allow_write, timeout)


def _run_engine_stream_inner(engine, prompt, allow_write, timeout):
    """Core streaming loop for a single engine. Yields event dicts."""
    if engine == "codex":
        sandbox = "workspace-write" if allow_write else "read-only"
        cmd = ["codex", "--sandbox", sandbox, "--ask-for-approval", "never",
               "exec", "--json", "--skip-git-repo-check", prompt]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, stdin=subprocess.DEVNULL,
        )
    else:  # claude
        cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose",
               "--allowedTools", "Bash,Read,Grep,Glob,Write,Edit,Agent"]
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        # Write prompt in a thread to avoid blocking on large prompts
        # (macOS pipe buffer is ~64KB, prompt can be 100KB+)
        import threading
        def _feed_stdin():
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass
        threading.Thread(target=_feed_stdin, daemon=True).start()

    accumulated_text = ""
    try:
        import select as _select
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                proc.kill()
                yield {"type": "timeout", "content": accumulated_text,
                       "message": f"Timeout ({timeout // 60} min limit)"}
                return
            ready, _, _ = _select.select([proc.stdout], [], [], min(remaining, 1.0))
            if ready:
                line = proc.stdout.readline()
                if not line:
                    break  # EOF
                line = line.strip()
                if not line:
                    continue
                evts = _parse_stream_event(engine, line)
                if evts:
                    if not isinstance(evts, list):
                        evts = [evts]
                    for evt in evts:
                        if evt["type"] == "text":
                            accumulated_text += evt["content"]
                        yield evt
            elif proc.poll() is not None:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    evts = _parse_stream_event(engine, line)
                    if evts:
                        if not isinstance(evts, list):
                            evts = [evts]
                        for evt in evts:
                            if evt["type"] == "text":
                                accumulated_text += evt["content"]
                            yield evt
                break
    except Exception as e:
        yield {"type": "error", "message": str(e)}
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()

    yield {"type": "done", "content": accumulated_text}


def _parse_stream_event(engine: str, line: str) -> dict:
    """Parse a JSONL line from Codex or Claude into a normalized event."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None

    if engine == "codex":
        evt_type = obj.get("type", "")
        # Tool execution started
        if evt_type == "item.started":
            item = obj.get("item", {})
            if item.get("type") == "command_execution":
                cmd = item.get("command", "")
                # Clean up shell wrapper
                if cmd.startswith("/bin/"):
                    parts = cmd.split('"', 1)
                    cmd = parts[1].rstrip('"') if len(parts) > 1 else cmd
                return {"type": "tool", "name": "Bash", "status": "running",
                        "detail": cmd[:200]}
        # Tool execution completed
        elif evt_type == "item.completed":
            item = obj.get("item", {})
            if item.get("type") == "command_execution":
                output = item.get("aggregated_output", "")
                return {"type": "tool", "name": "Bash", "status": "done",
                        "detail": output or ""}
            elif item.get("type") == "agent_message":
                text = item.get("text", "")
                if text:
                    return {"type": "text", "content": text}
        # Codex error / turn failed (e.g. usage limit)
        elif evt_type in ("error", "turn.failed"):
            msg = obj.get("message", "") or obj.get("error", {}).get("message", "")
            return {"type": "error", "message": f"codex: {msg}" if msg else "codex: unknown error"}
        # Turn completed (usage stats)
        elif evt_type == "turn.completed":
            usage = obj.get("usage", {})
            return {"type": "usage", "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0)}

    elif engine == "claude":
        evt_type = obj.get("type", "")
        # Assistant message — may contain multiple content blocks (text + tool_use)
        if evt_type == "assistant":
            msg = obj.get("message", {})
            content_blocks = msg.get("content", [])
            events = []
            pending_text = []
            for blk in content_blocks:
                if not isinstance(blk, dict):
                    continue
                if blk.get("type") == "text":
                    pending_text.append(blk.get("text", ""))
                elif blk.get("type") == "tool_use":
                    # Flush pending text before tool
                    if pending_text:
                        events.append({"type": "text", "content": "\n".join(pending_text)})
                        pending_text = []
                    name = blk.get("name", "")
                    inp = blk.get("input", {})
                    detail = ""
                    if name in ("Bash", "bash"):
                        detail = inp.get("command", "")[:200]
                    elif name in ("Read", "read_file"):
                        detail = inp.get("file_path", "")
                    elif name in ("Edit", "Write"):
                        detail = inp.get("file_path", "")
                    elif name in ("Grep", "Glob"):
                        detail = inp.get("pattern", "")
                    elif name == "Agent":
                        desc = inp.get("description", "")
                        prompt = inp.get("prompt", "")
                        detail = desc if desc else (prompt[:300] if prompt else "")
                    event = {"type": "tool", "name": name, "status": "running",
                             "detail": detail, "_tool_use_id": blk.get("id", "")}
                    if name == "Agent" and inp.get("prompt"):
                        event["prompt"] = inp["prompt"]
                    events.append(event)
            # Flush trailing text
            if pending_text:
                events.append({"type": "text", "content": "\n".join(pending_text)})
            return events if events else None
        # Tool result — mark corresponding tool as done
        elif evt_type == "user":
            msg = obj.get("message", {})
            content_blocks = msg.get("content", [])
            events = []
            for blk in content_blocks:
                if isinstance(blk, dict) and blk.get("type") == "tool_result":
                    output = blk.get("content", "")
                    # Truncate output for display
                    if isinstance(output, list):
                        output = " ".join(
                            b.get("text", "") for b in output if isinstance(b, dict)
                        )
                    events.append({"type": "tool", "name": "", "status": "done",
                                   "detail": str(output),
                                   "_tool_use_id": blk.get("tool_use_id", "")})
            return events if events else None
        # Final result
        elif evt_type == "result":
            result_text = obj.get("result", "")
            if result_text:
                return {"type": "result", "content": result_text}

    return None


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------
class ChatViewerHandler(SimpleHTTPRequestHandler):
    """Handles API requests and serves static files."""

    def do_GET(self):
        try:
            self._do_GET_inner()
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                self._error(500, f"Internal server error: {type(e).__name__}")
            except Exception:
                pass

    def _do_GET_inner(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # API routes
        if path == "/api/projects":
            self._json_response(self._get_projects())
        elif path == "/api/sessions":
            project = params.get("project", [None])[0]
            self._json_response(self._get_sessions(project))
        elif path.startswith("/api/session/"):
            sid = path[len("/api/session/") :]
            data = load_session(sid)
            if data:
                self._json_response(data)
            else:
                self._error(404, "Session not found")
        elif path == "/api/search":
            q = params.get("q", [""])[0]
            self._json_response(search_sessions(q))
        elif path == "/api/timeline":
            self._json_response(self._get_timeline())
        elif path == "/api/analytics":
            self._json_response(_cached("analytics", self._get_analytics))
        elif path == "/api/insights":
            self._json_response({"similar": [], "chain": [], "decisions": []})
        elif path == "/api/session-summary":
            sid = params.get("session", [None])[0]
            self._json_response(_cached(f"summary:{sid}", lambda: self._get_session_summary(sid)))
        elif path == "/api/snippets":
            self._json_response(_cached("snippets", self._get_snippets))
        elif path == "/api/file-evolution":
            fp = params.get("file", [None])[0]
            self._json_response(_cached(f"evolution:{fp}", lambda: self._get_file_evolution(fp)))
        elif path == "/api/project-health":
            self._json_response(self._get_project_health())
        elif path == "/api/refresh":
            build_index()
            self._json_response({"ok": True})
        elif path == "/api/stats":
            self._json_response(self._get_stats())
        elif path.startswith("/api/evolve/"):
            tab = path[len("/api/evolve/"):]
            if tab not in ("rules", "signals", "patterns", "profile", "memory"):
                self._error(400, "Invalid evolve tab")
            else:
                refresh = params.get("refresh", ["0"])[0] == "1"
                source = params.get("source", ["all"])[0]
                date = params.get("date", ["7d"])[0]
                project = params.get("project", [""])[0]
                engine = params.get("engine", ["auto"])[0]
                stream = params.get("stream", ["0"])[0] == "1"
                if stream and tab in self._AI_TABS:
                    self._handle_evolve_stream(tab, source, date, project, engine)
                else:
                    self._json_response(self._get_evolve_tab(tab, refresh, source, date, project, engine))
        # --- Cognitive Handbook (Digital Twin) endpoints ---
        elif path == "/api/twin/stats":
            import db as _db
            self._json_response(_db.get_twin_stats())
        elif path == "/api/twin/overview":
            import db as _db
            overview = {}
            # Cards overview
            try:
                card_count = _db.cm_count("judgment_cards")
                card_items = _db.cm_get_all("judgment_cards", order="confidence DESC", limit=5)
                overview["cards"] = {"count": card_count, "items": card_items}
            except Exception:
                overview["cards"] = {"count": 0, "items": []}
            # Traits overview
            try:
                trait_count = _db.cm_count("cognitive_traits")
                trait_items = _db.cm_get_all("cognitive_traits", order="strength DESC", limit=50)
                overview["traits"] = {"count": trait_count, "items": trait_items}
            except Exception:
                overview["traits"] = {"count": 0, "items": []}
            # Events overview (count + top 3 high-signal)
            try:
                event_count = _db.cm_count("evidence_events")
                event_items = _db.cm_get_all("evidence_events",
                                             order="signal_intensity DESC, created_at DESC", limit=3)
                overview["events"] = {"count": event_count, "items": event_items}
            except Exception:
                overview["events"] = {"count": 0, "items": []}
            self._json_response(overview)
        elif path == "/api/twin/events":
            import db as _db
            signal = params.get("signal_type", [None])[0]
            domain = params.get("domain", [None])[0]
            limit = int(params.get("limit", ["200"])[0])
            where_parts, where_params = [], []
            if signal:
                where_parts.append("signal_type=?")
                where_params.append(signal)
            if domain:
                where_parts.append("domain LIKE ?")
                where_params.append(f"%{domain}%")
            where = " AND ".join(where_parts)
            items = _db.cm_get_all("evidence_events", where=where,
                                   params=tuple(where_params),
                                   order="signal_intensity DESC, created_at DESC", limit=limit)
            self._json_response({"events": items})
        elif path == "/api/twin/cards":
            import db as _db
            status = params.get("status", [None])[0]
            tag = params.get("tag", [None])[0]
            sort = params.get("sort", ["confidence"])[0]
            limit = int(params.get("limit", ["500"])[0])
            where_parts, where_params = [], []
            if status:
                where_parts.append("status=?")
                where_params.append(status)
            if tag:
                where_parts.append("tags LIKE ?")
                where_params.append(f"%{tag}%")
            where = " AND ".join(where_parts)
            order = "confidence DESC" if sort == "confidence" else "updated_at DESC"
            items = _db.cm_get_all("judgment_cards", where=where,
                                   params=tuple(where_params), order=order, limit=limit)
            self._json_response({"cards": items})
        elif path == "/api/twin/traits":
            import db as _db
            status = params.get("status", [None])[0]
            category = params.get("category", [None])[0]
            limit = int(params.get("limit", ["500"])[0])
            where_parts, where_params = [], []
            if status:
                where_parts.append("status=?")
                where_params.append(status)
            if category:
                where_parts.append("category=?")
                where_params.append(category)
            where = " AND ".join(where_parts)
            items = _db.cm_get_all("cognitive_traits", where=where,
                                   params=tuple(where_params), order="strength DESC", limit=limit)
            self._json_response({"traits": items})
        elif path.startswith("/api/twin/card/"):
            import db as _db
            card_id = path[len("/api/twin/card/"):]
            card = _db.cm_get("judgment_cards", card_id)
            if card is None:
                self._error(404, "Card not found")
            else:
                evidence = _db.cm_get_evidence_for_card(card_id)
                relations = _db.cm_get_card_relations(card_id)
                self._json_response({"card": card, "evidence": evidence, "relations": relations})
        elif path.startswith("/api/twin/trait/"):
            import db as _db
            trait_id = path[len("/api/twin/trait/"):]
            trait = _db.cm_get("cognitive_traits", trait_id)
            if trait is None:
                self._error(404, "Trait not found")
            else:
                # Load supporting cards
                card_ids = []
                try:
                    card_ids = json.loads(trait.get("supporting_card_ids") or "[]")
                except (json.JSONDecodeError, TypeError):
                    pass
                cards = [_db.cm_get("judgment_cards", cid) for cid in card_ids if cid]
                cards = [c for c in cards if c]
                self._json_response({"trait": trait, "supporting_cards": cards})
        elif path == "/api/twin/runtime-preview":
            import db as _db
            cards = _db.cm_get_all("judgment_cards",
                                   where="status IN ('confirmed','emerging')",
                                   order="confidence DESC", limit=25)
            traits = _db.cm_get_all("cognitive_traits",
                                    where="status IN ('confirmed','emerging')",
                                    order="strength DESC", limit=15)
            # Render NL text (same logic as twin-compile)
            lines = []
            if traits:
                lines.append("## 关于这位用户\n")
                for t in traits:
                    lines.append(f"**{t.get('name','')}**。{t.get('description','')}\n")
            if cards:
                lines.append("\n## 场景判断\n")
                for c in cards:
                    when = c.get("applies_when") or ""
                    judgment = c.get("judgment") or ""
                    action = c.get("agent_action") or ""
                    exceptions = c.get("exceptions") or ""
                    lines.append(f"**{when}**：{judgment}")
                    if action:
                        lines.append(f"→ {action}")
                    if exceptions:
                        lines.append(f"例外：{exceptions}")
                    lines.append("")
            self._json_response({
                "text": "\n".join(lines),
                "card_count": len(cards),
                "trait_count": len(traits),
            })
        else:
            # Serve static files (with path traversal protection)
            if path == "/":
                path = "/index.html"
            file_path = (STATIC_DIR / path.lstrip("/")).resolve()
            # SECURITY: Ensure resolved path is under STATIC_DIR (relative_to raises ValueError if not)
            try:
                file_path.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self._error(403, "Forbidden")
                return
            if file_path.exists() and file_path.is_file():
                self._serve_file(file_path)
            else:
                self._error(404, "Not found")

    def _get_projects(self) -> list:
        with _index_lock:
            projects = _index.get("projects", {})
        result = sorted(projects.values(), key=lambda p: p["name"])
        return result

    def _get_sessions(self, project: str) -> list:
        with _index_lock:
            sessions = _index.get("sessions", {})
        result = []
        for sid, meta in sessions.items():
            if project and meta.get("projectName") != project:
                continue
            result.append({
                "id": sid,
                "title": meta.get("title", "Untitled"),
                "project": meta.get("projectName", ""),
                "date": meta.get("date", ""),
                "userMessageCount": meta.get("userMessageCount", 0),
                "fileSize": meta.get("fileSize", 0),
                "source": meta.get("source", "claude"),
            })
        result.sort(key=lambda s: s.get("date", ""), reverse=True)
        return result

    def _get_timeline(self) -> dict:
        """Group sessions by date for the activity timeline view."""
        with _index_lock:
            sessions = _index.get("sessions", {})

        days = {}  # "YYYY-MM-DD" -> {sessions: [...], stats}
        for sid, meta in sessions.items():
            date_str = meta.get("date", "")
            if not date_str:
                continue
            try:
                day = date_str[:10]  # "YYYY-MM-DD"
                # Validate format
                datetime.strptime(day, "%Y-%m-%d")
            except (ValueError, IndexError):
                continue

            if day not in days:
                days[day] = {"date": day, "sessions": [], "totalMessages": 0}

            days[day]["sessions"].append({
                "id": sid,
                "title": meta.get("title", "Untitled"),
                "project": meta.get("projectName", ""),
                "source": meta.get("source", "claude"),
                "userMessageCount": meta.get("userMessageCount", 0),
                "date": date_str,
                "lastDate": meta.get("lastDate", ""),
            })
            days[day]["totalMessages"] += meta.get("userMessageCount", 0)

        # Sort sessions within each day by date desc
        for day_data in days.values():
            day_data["sessions"].sort(key=lambda s: s.get("date", ""), reverse=True)
            day_data["sessionCount"] = len(day_data["sessions"])

        # Return sorted by date desc
        result = sorted(days.values(), key=lambda d: d["date"], reverse=True)
        return {"days": result}

    def _get_stats(self) -> dict:
        with _index_lock:
            return {
                "totalSessions": len(_index.get("sessions", {})),
                "totalProjects": len(_index.get("projects", {})),
            }

    # Tabs that use direct Python analysis (no AI engine needed)
    _DIRECT_TABS = set()
    # Tabs that need AI (Codex / claude -p) to generate
    _AI_TABS = {"profile", "memory", "rules", "signals", "patterns"}

    def _get_evolve_tab(self, tab: str, refresh: bool, source: str, date: str, project: str, engine: str = "auto") -> dict:
        """Get evolve tab data: serve DB cache or run AI engine to generate."""
        import db as _db
        try:
            engine = _normalize_ai_engine(engine)
        except ValueError as e:
            return self._evolve_fallback(tab, str(e))

        # If not refreshing, serve from DB
        if not refresh:
            row = _db.evolve_get(tab, source, date, project, engine)
            if row:
                return row["data"]

        if tab in self._DIRECT_TABS:
            return self._evolve_direct(tab, source, date, project)
        else:
            return self._evolve_via_ai(tab, source, date, project, engine)

    def _evolve_direct(self, tab: str, source: str, date: str, project: str) -> dict:
        """Run analyze.py directly for rules/signals/patterns."""
        cmd = [
            sys.executable, str(Path(__file__).parent / "analyze.py"),
            f"evolve-{tab}", "--json",
            "--source", source, "--date", date,
        ]
        if project:
            cmd.extend(["--project", project])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            pass

        fallbacks = {
            "rules": {"rules": []},
            "signals": {"timeline": [], "events": []},
            "patterns": {"bubbles": [], "cards": []},
        }
        return fallbacks.get(tab, {})

    def _evolve_via_ai(self, tab: str, source: str, date: str, project: str, engine: str = "auto") -> dict:
        """Run AI engine to analyze conversations; AI writes result to SQLite via evolve-write CLI."""
        import db as _db
        cli_path = str(Path(__file__).resolve().parent / "analyze.py")
        prompt = self._build_evolve_prompt(tab, source, date, project, cli_path, engine)

        try:
            _run_ai_engine(prompt, allow_write=True, timeout=600, engine_override=engine)
        except FileNotFoundError as e:
            return self._evolve_fallback(tab, str(e))
        except subprocess.TimeoutExpired:
            return self._evolve_fallback(tab, "timeout")
        except Exception as e:
            return self._evolve_fallback(tab, str(e))

        # AI wrote to SQLite via evolve-write CLI — read it back
        row = _db.evolve_get(tab, source, date, project, engine)
        if row:
            return row["data"]

        engine_name = _detect_ai_engine() or "AI"
        return self._evolve_fallback(tab, f"{engine_name} did not produce valid output")

    def _handle_evolve_stream(self, tab: str, source: str, date: str, project: str, engine: str = "auto"):
        """SSE streaming for AI evolve tabs (profile/memory)."""
        import db as _db
        try:
            engine = _normalize_ai_engine(engine)
        except ValueError as e:
            self._start_sse()
            self._sse_event({"type": "error", "message": str(e)})
            return
        cli_path = str(Path(__file__).resolve().parent / "analyze.py")
        prompt = self._build_evolve_prompt(tab, source, date, project, cli_path, engine)

        self._start_sse()
        stream = _run_ai_engine_stream(prompt, allow_write=True, timeout=600, engine_override=engine)
        try:
            for evt in stream:
                self._sse_event(evt)
        except BrokenPipeError:
            return
        except Exception as e:
            try:
                self._sse_event({"type": "error", "message": str(e)})
            except BrokenPipeError:
                return
            return
        finally:
            stream.close()

        # AI wrote to SQLite via evolve-write CLI — read it back
        try:
            row = _db.evolve_get(tab, source, date, project, engine)
            if row:
                self._sse_event({"type": "evolve_result", "data": row["data"]})
            else:
                self._sse_event({"type": "error", "message": "AI did not write result to database"})
        except BrokenPipeError:
            return

    def _evolve_fallback(self, tab: str, reason: str) -> dict:
        """Return empty data with error info."""
        fallbacks = {
            "profile": {"categories": [], "radar": {"dimensions": []}, "_error": reason},
            "memory": {"nodes": [], "links": [], "cards": [], "_error": reason},
            "rules": {"rules": [], "_error": reason},
            "signals": {"timeline": [], "events": [], "_error": reason},
            "patterns": {"bubbles": [], "cards": [], "_error": reason},
        }
        return fallbacks.get(tab, {"_error": reason})

    def _collect_stats(self, source: str, date: str, project: str, cli_path: str) -> str:
        """Pre-collect stats only (small, ~1KB) for embedding in prompt."""
        cmd = [sys.executable, cli_path, "stats", "--date", date, "--source", source]
        if project:
            cmd.extend(["--project", project])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            return r.stdout if r.returncode == 0 else ""
        except Exception:
            return ""

    def _collect_profile_digest(self, source: str, date: str, project: str, cli_path: str) -> str:
        """Run profile-digest command and return JSON string."""
        import subprocess
        cmd = [sys.executable, cli_path, "profile-digest",
               "--date", date, "--source", source]
        if project:
            cmd.extend(["--project", project])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _collect_aggregates(self) -> str:
        """Pre-collect trimmed aggregates (~2KB) for embedding in prompt."""
        import db as _db
        try:
            _db.init_db()
            parts = []
            # Top 15 projects by session count
            pd_raw = _db.get_aggregate("project_distribution")
            if pd_raw:
                pd = json.loads(pd_raw)
                top = sorted(pd, key=lambda x: -x["count"])[:15]
                parts.append("Project distribution (top 15):")
                parts.append(json.dumps(top, ensure_ascii=False))
            # Daily activity (last 14 days)
            da_raw = _db.get_aggregate("daily_activity")
            if da_raw:
                da = json.loads(da_raw)
                recent = da[-14:] if len(da) > 14 else da
                parts.append("Daily activity (last 14d):")
                parts.append(json.dumps(recent, ensure_ascii=False))
            return "\n".join(parts)
        except Exception:
            return ""

    def _build_evolve_prompt(self, tab: str, source: str, date: str, project: str, cli_path: str, engine: str = "auto") -> str:
        """Build a prompt that instructs the AI to progressively explore data via CLI tools."""
        cli_flags = f"--date {date} --source {source}"
        if project:
            cli_flags += f' --project "{project}"'

        write_cmd = f"python3 {cli_path} evolve-write --tab {tab} --source {source} --date {date} --engine {engine}"
        if project:
            write_cmd += f' --project "{project}"'

        # All AI tabs benefit from pre-computed digest (corrections, friction, queries, decisions)
        digest = self._collect_profile_digest(source, date, project, cli_path)

        parts = [
            "# Background",
            "",
            "You are part of an AI self-evolution system called 'Chat Viewer Evolve'.",
            "It analyzes a user's past AI conversation history (from Claude Code and Codex CLI sessions)",
            "to extract insights about the user — their preferences, work patterns, recurring mistakes, and collaboration style.",
            "",
        ]

        digest_cmd = f"python3 {cli_path} profile-digest --date {date} --source {source}" + (f' --project "{project}"' if project else "")
        if tab in ("profile", "memory") and digest:
            # Digest-based flow: main agent sees full digest, sub-agents run command to get it
            parts.extend([
                "# Pre-computed Profile Digest",
                "",
                "Below is a pre-computed overview of the user's conversation history.",
                "Use it to understand the data landscape and decide how to split work across sub-agents.",
                "",
                digest,
                "",
                "# Execution Strategy",
                "",
                "Dispatch 2-3 sub-agents (via Agent tool) in parallel.",
                "Each agent's prompt MUST include:",
                f"  - Digest command: `{digest_cmd}` (agent runs this FIRST to get the overview)",
                f"  - Full CLI tool: `python3 {cli_path} <command> --date {date} --source {source}" + (f' --project "{project}"' if project else "") + "`",
                "  - Its assigned focus area, which digest sections to start from, and exploration instructions",
                "",
                "CLI commands available for exploration:",
                f"  python3 {cli_path} read <id> -s   — Read a specific session (summary mode, see conversation context)",
                f"  python3 {cli_path} search <q>     — Full-text search across sessions",
                f"  python3 {cli_path} corrections     — Raw correction data with signal words and AI responses",
                f"  python3 {cli_path} queries          — User messages across sessions",
                f"  python3 {cli_path} highlights       — Sessions ranked by correction/decision density",
                "",
                "Each agent has a DISTINCT focus area — no overlap. Suggested split:",
                "  - Agent 1: correction_episodes + friction_hotspots + errors → behavioral rules and pain points",
                "  - Agent 2: query_samples + decisions + positive_signals → work patterns and preferences",
                "  - Agent 3: files + collaboration + communication + session_topics → technical profile and style",
                "",
                "## Agent workflow (IMPORTANT — digest is the map, not the destination)",
                "",
                "Each agent MUST follow this 3-step process:",
                "1. ORIENT: Run `profile-digest` to get the overview. Identify exploration targets from their focus sections.",
                "   Examples: friction_hotspots session IDs, correction episode signals, high-signal sessions.",
                "2. EXPLORE: Deep-dive into targets using CLI tools. This is the CORE step — don't skip it.",
                "   - Read 3-5 high-signal sessions via `read <id> -s` to understand WHY patterns exist",
                "   - Search for keywords from correction episodes to find more instances",
                "   - Run `corrections` or `queries` to see raw data beyond the digest's summary",
                "   - Look for context the digest can't capture: what triggered a correction, what the user wanted instead",
                "3. SYNTHESIZE: Combine digest statistics + exploration findings → specific, evidence-backed insights.",
                "   Bad: '用户纠正了8次' (just restating digest). Good: '用户对AI擅自扩展scope高度敏感，",
                "   在3个不同项目中反复中断实施要求回到明确边界，触发场景是AI修bug时顺便重构相邻代码'",
                "",
                "After all agents return, synthesize their findings and write the result.",
                "IMPORTANT: wait for ALL agent results before writing. Do not end your turn until evolve-write succeeds.",
                "",
            ])
        else:
            # CLI exploration flow: for rules/signals/patterns tabs
            cli_flags = f"--date {date} --source {source}"
            if project:
                cli_flags += f' --project "{project}"'

            stats = self._collect_stats(source, date, project, cli_path)
            aggregates = self._collect_aggregates()

            # Count sessions
            with _index_lock:
                sessions = dict(_index.get("sessions", {}))
            now = datetime.now()
            days_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
            max_days = days_map.get(date, 99999)
            session_count = 0
            for m in sessions.values():
                if source != "all" and m.get("source", "claude") != source:
                    continue
                if project and project not in m.get("projectName", ""):
                    continue
                d = m.get("date", "")
                if d and max_days < 99999:
                    try:
                        age = (now - datetime.fromisoformat(d.replace("Z", "+00:00").replace("+00:00", "").rstrip("Z"))).days
                        if age > max_days:
                            continue
                    except (ValueError, TypeError):
                        pass
                session_count += 1

            parts.extend([
                "The conversation data is stored as JSONL files under ~/.claude/projects/ (Claude Code) and ~/.codex/ (Codex CLI).",
                "Each 'session' is one conversation between the user and an AI assistant. Sessions contain:",
                "- User messages (requests, questions, feedback, corrections)",
                "- Assistant messages (responses, code, explanations)",
                "- Tool calls (Bash commands, file reads/edits, web searches)",
                "",
                "Your job: explore this conversation history using the CLI tool below, find patterns, and produce structured JSON output.",
                "",
                "# CLI Tool",
                "",
                f"  python3 {cli_path} <command> [options]",
                "",
                "Commands:",
                "  stats        — Overview: session count, message count, date range, top projects",
                "  sessions     — List sessions with titles, dates, message counts",
                "  queries      — Extract user questions/requests across sessions",
                "  corrections  — Find where the user corrected/rejected AI output (50+ signal words)",
                "  highlights   — Sessions ranked by correction frequency (high corr = friction)",
                "  decisions    — Key decisions and turning points in conversations",
                "  files        — Most frequently touched files across sessions",
                "  aggregates   — Pre-computed project distribution + daily activity (JSON, fast)",
                "  read <id>    — Read full conversation of a specific session (use -s for summary)",
                "  search <q>   — Full-text search across all sessions",
                "",
                f"Options: --date {date} --source {source}" + (f' --project "{project}"' if project else "") + " --limit N",
                f"Scope: {session_count} sessions in range",
                "",
            ])

            if stats:
                parts.extend(["# Pre-collected Data (do NOT re-run these)", "", "=== STATS ===", stats, ""])
            if aggregates:
                parts.extend(["=== AGGREGATES ===", aggregates, ""])
            if digest:
                parts.extend([
                    "",
                    "# Pre-computed Profile Digest (corrections, friction, queries, decisions — do NOT re-run profile-digest)",
                    "",
                    digest,
                    "",
                ])

            claude_dir = str(Path.home() / ".claude" / "projects")
            codex_dir = str(Path.home() / ".codex")
            parts.extend([
                "# Execution Strategy",
                "",
                "Dispatch 2-3 sub-agents (via Agent tool) in parallel. Use the stats and aggregates above to decide the split — do NOT re-run stats/aggregates in agents.",
                "Each agent's prompt MUST include:",
                f"  - CLI tool: python3 {cli_path} <command> {cli_flags}",
                f"  - Data sources: conversation history ONLY — the CLI above, or files under {claude_dir} and {codex_dir}. Do NOT access any other directories or personal files.",
                "  - Background context: briefly explain that they are analyzing AI conversation history to find user patterns/preferences.",
                "",
                "Efficiency rules for agents:",
                "- Batch multiple CLI commands in one Bash call (e.g. echo '=== queries ==='; python3 ... queries --limit 80; echo '=== corrections ==='; python3 ... corrections --limit 80).",
                "- Use `read -s <id>` to get context for interesting sessions. Use `search <keyword>` for targeted exploration.",
                "- Do NOT run stats or aggregates — that data is already provided above.",
                "",
                "Each agent must have a DISTINCT focus area — no overlap. Split based on the overview data, not a fixed template.",
                "After all agents return, synthesize their findings and write the result.",
                "IMPORTANT: wait for ALL agent results before writing. Do not end your turn until evolve-write succeeds.",
                "",
            ])

        if tab == "profile":
            parts.extend([
                "TASK: Build a USER PROFILE — about the PERSON, not their projects.",
                "Profile should cover: who they are, how they work, what they care about, their style and preferences.",
                "Projects are evidence, not categories. Focus on behavioral patterns across projects.",
                "",
                f"Write result via: {write_cmd} --mode replace <<'EVOLVE_EOF'",
                "JSON schema:",
                '{"categories": [{"name": "分类名", "icon": "emoji", "tags": ["标签"],',
                '  "items": [{"text": "具体描述", "confidence": "high|medium|low"}]}],',
                ' "radar": {"dimensions": [{"name": "领域", "score": 0.0-1.0, "evidence": "简述依据"}]}}',
                "",
                "分类方向（参考，不限于此）：职业身份、工作风格、AI协作偏好、沟通与决策习惯、技术审美、工程标准等",
                "质量要求：",
                "- 6-8 categories, 30+ items, 丰富的 tags",
                "- items 要具体，提到行为模式和偏好，不要泛泛概括",
                "- 示例：✗「用户关注前端开发」 ✓「反复要求仿 ChatGPT 消息流式布局，重视工具卡片折叠、自动滚动等交互细节」",
                "- 所有内容用中文，不需要引用用户原话",
            ])
        elif tab == "memory":
            parts.extend([
                "TASK: Extract EXECUTABLE behavioral preferences as a memory network.",
                "",
                "Memory answers: 'What should the next AI agent do differently?'",
                "Memory is NOT Profile — do NOT include: project descriptions, tech stack facts, domain interests, communication style observations.",
                "Only include items that can be written as: 'When [trigger], do [instruction]' — with optional 'avoid [what not to do]'.",
                "",
                f"Write result via: {write_cmd} --mode replace <<'EVOLVE_EOF'",
                "JSON schema:",
                "",
                "```json",
                '{"nodes": [{"id": "m1", "label": "短标签(4-8字)", "type": "preference|workflow|tooling|design|communication",',
                '  "frequency": N, "confidence": "high|medium|low", "priority": "P0|P1|P2",',
                '  "status": "active", "scope": "coding|review|design|research|all"}],',
                ' "links": [{"source": "m1", "target": "m2", "strength": 0.0-1.0, "relation": "supports|conflicts|refines"}],',
                ' "cards": [{"id": "m1",',
                '  "trigger": "什么场景触发这条记忆",',
                '  "instruction": "AI 应该怎么做",',
                '  "avoid": "AI 不应该做什么(可为空字符串)",',
                '  "content": "完整描述(向后兼容,可从trigger+instruction生成)",',
                '  "firstSeen": "YYYY-MM-DD", "lastSeen": "YYYY-MM-DD",',
                '  "evidence": [{"quote": "用户原话", "sessionId": "session-id", "date": "YYYY-MM-DD"}],',
                '  "conflictsWith": ["m6"]}]}',
                "```",
                "",
                "质量要求：",
                "- 10-15 条 memory, 每条必须有明确的 trigger + instruction",
                "- avoid 字段可选：有需要就填，没有可为空字符串",
                "- type 必须用英文：preference / workflow / tooling / design / communication",
                "- evidence 必须是数组，每条含 quote + sessionId + date",
                "- 准入门槛：如果不能写成 'When X, do Y' 的指令，它属于 Profile 而非 Memory",
                "  ✗ Memory: '使用Python全栈开发' → 归 Profile",
                "  ✗ Memory: '主力项目是对话历史可视化工具' → 归 Profile",
                "  ✓ Memory: trigger='AI修bug时准备顺便改相邻代码', instruction='仅做请求的改动，不扩展范围'",
                "- 矛盾处理：发现两条 memory 表面冲突时，用 trigger 区分适用场景，用 conflictsWith 标注关联",
                "  例：'先方案后执行' 和 '端到端自主授权' 不冲突——前者适用于开放设计任务，后者适用于用户明确授权时",
                "- 只提取跨项目通用的偏好",
                "- 所有描述用中文",
            ])
        elif tab == "rules":
            # Same prompt as the "规则生成" preset in app.js
            parts.extend([
                "分析所有对话中用户纠正AI的场景，自动生成CLAUDE.md规则。",
                "",
                "**工作流（按顺序执行）**：",
                "1. 先运行 `corrections` 获取所有纠正样本（已含50+种中英文信号词检测）",
                "2. 运行 `highlights` 找高纠正数的会话（corr≥3的重点关注）",
                "3. 对高纠正会话运行 `read -s <id>` 看上下文（理解纠正原因）",
                "4. 补充搜索 `search \"不行\"` `search \"太精简\"` `search \"应该是\"` 等关键词",
                "",
                "**输出要求**：",
                "1. 聚类相似纠正，提取模式",
                "2. 为每个模式生成规则：规则内容 | 触发场景 | 来源频次",
                "3. 按出现频率排序，标注优先级 P0/P1/P2",
                "4. 格式参考 CLAUDE.md 规则写法（可直接粘贴使用）",
                "",
                "5. 只提取跨项目通用的规则，如果某条规则只在单一项目/技术栈中出现且换个项目不适用，不要入选",
                "",
                "每条规则附至少一条原始纠正引用（用户原话）和 session ID 作为证据。",
                "",
                f"最终结果通过以下命令写入：{write_cmd} --mode replace <<'EVOLVE_EOF'",
                "JSON schema:",
                '{"rules": [{"id": "r1", "priority": "P0|P1|P2", "category": "准确性|风格|范围|工作流",',
                '  "rule": "规则标题", "why": "来源场景", "frequency": N,',
                '  "evidence": [{"quote": "用户原话", "session": "session-id"}]}]}',
            ])
        elif tab == "signals":
            parts.extend([
                "TASK: 提取用户纠正 AI 的信号事件，构建纠正时间线。",
                "",
                "**工作流**：",
                "1. 运行 `corrections` 获取所有纠正样本",
                "2. 运行 `highlights` 找高纠正频次的会话",
                "3. 对关键会话运行 `read -s <id>` 看具体上下文",
                "4. 补充 `search` 搜索关键纠正词（如「不对」「不行」「太复杂」「应该是」）",
                "",
                "**分析重点**：",
                "- 每个纠正事件归类：style（风格）、scope（范围）、accuracy（准确性）、workflow（工作流）、overengineering（过度工程）",
                "- 按日期聚合为时间线（每天各类型纠正数），观察趋势变化",
                "- 关联到具体的 session ID 和用户原话",
                "",
                f"最终结果通过以下命令写入：{write_cmd} --mode replace <<'EVOLVE_EOF'",
                "JSON schema:",
                '{"timeline": [{"date": "YYYY-MM-DD", "counts": {"style": N, "scope": N, "accuracy": N, "workflow": N}}],',
                ' "events": [{"id": "s1", "date": "YYYY-MM-DD", "session": "session-id",',
                '   "type": "style|scope|accuracy|workflow|overengineering",',
                '   "userQuote": "用户原话", "aiIssue": "AI做错了什么", "correction": "应该怎么做",',
                '   "linkedRule": null}]}',
                "",
                "质量要求：",
                "- events 按时间倒序，每个附 session ID + 用户原话",
                "- timeline 覆盖查询日期范围内每天的统计",
                "- 所有描述用中文",
            ])
        elif tab == "patterns":
            parts.extend([
                "TASK: 发现用户与 AI 协作中的重复模式 — 反复出现的问题、低效环节、知识盲区。",
                "",
                "**工作流**：",
                "1. 运行 `corrections` 和 `highlights` 获取纠正数据",
                "2. 运行 `queries` 看用户高频提问模式",
                "3. 运行 `files` 看热点文件（反复修改暗示问题模式）",
                "4. 对有趣的会话运行 `read -s <id>` 深入分析",
                "5. 用 `search` 搜索重复出现的关键词",
                "",
                "**分析重点**：",
                "- 归类模式：error（反复犯错）、efficiency（低效环节）、knowledge_gap（知识盲区）、workflow（工作流瓶颈）",
                "- 量化频率，判断趋势（increasing/stable/decreasing）",
                "- 给出改进建议和估算成本（如「每次多花 5 分钟调试」）",
                "",
                f"最终结果通过以下命令写入：{write_cmd} --mode replace <<'EVOLVE_EOF'",
                "JSON schema:",
                '{"bubbles": [{"id": "p1", "label": "模式名称", "type": "error|efficiency|knowledge_gap|workflow",',
                '   "frequency": N, "trend": "increasing|stable|decreasing"}],',
                ' "cards": [{"id": "p1", "description": "详细描述", "frequency": N,',
                '   "trend": "increasing|stable|decreasing", "cost": "估算影响",',
                '   "suggestion": "改进建议", "sessions": ["session-id"]}]}',
                "",
                "质量要求：",
                "- bubbles 和 cards 的 id 一一对应",
                "- 每个模式附具体 session 引用",
                "- 关注真正反复出现的模式（≥2次），不要列一次性事件",
                "- 所有内容用中文",
            ])

        parts.extend([
            "",
            "RULES:",
            "- NEVER truncate CLI output with head/tail. Use --limit if output is too large.",
            "- evolve-write validates JSON schema. If it fails, read the error and fix.",
        ])

        return "\n".join(parts)

    def _get_analytics(self) -> dict:
        """Compute analytics from pre-aggregated DB tables."""
        import db as _db
        home = str(Path.home())

        # File hotspots (top 50)
        raw_hotspots = _db.query_file_hotspots(50)
        hotspots = []
        for row in raw_hotspots:
            fp = row["file_path"]
            short = fp.replace(home, "~") if fp.startswith(home) else fp
            projects = [p for p in (row.get("projects") or "").split(",") if p]
            hotspots.append({
                "path": short,
                "fullPath": fp,
                "count": row["total_count"],
                "sessionCount": row["session_count"],
                "projects": projects,
            })

        # Tool heatmap (last 30 days)
        raw_tools = _db.query_tool_heatmap()
        tool_daily = {}
        for row in raw_tools:
            day = row["day"]
            tool_daily.setdefault(day, {})[row["tool_name"]] = row["total"]

        sorted_days = sorted(tool_daily.keys(), reverse=True)[:30]
        tool_totals = {}
        for day_tools in tool_daily.values():
            for t, c in day_tools.items():
                tool_totals[t] = tool_totals.get(t, 0) + c
        sorted_tools = sorted(tool_totals.keys(), key=lambda t: -tool_totals.get(t, 0))[:15]

        heatmap = {
            "days": sorted_days,
            "tools": sorted_tools,
            "data": {day: {t: tool_daily.get(day, {}).get(t, 0) for t in sorted_tools} for day in sorted_days},
            "totals": {t: tool_totals.get(t, 0) for t in sorted_tools},
        }

        # Error patterns (top 30)
        raw_errors = _db.query_error_patterns(30)
        errors = []
        for row in raw_errors:
            projects = [p for p in (row.get("projects") or "").split(",") if p]
            errors.append({
                "pattern": row["error_key"][:200],
                "count": row["total_count"],
                "sessionCount": row["session_count"],
                "projects": projects,
                "firstSeen": row.get("first_seen", ""),
                "lastSeen": row.get("last_seen", ""),
            })

        return {"hotspots": hotspots, "heatmap": heatmap, "errors": errors}

    def _get_session_summary(self, session_id: str) -> dict:
        """F11: Request vs Reality — first user request vs files actually changed."""
        with _index_lock:
            sessions = _index.get("sessions", {})
        meta = sessions.get(session_id)
        if not meta:
            return {"request": "", "files": [], "tools": {}}

        filepath = meta.get("filePath", "")
        source = meta.get("source", "claude")
        if not filepath or not os.path.exists(filepath):
            return {"request": "", "files": [], "tools": {}}

        first_user_msg = ""
        files_touched = {}  # path -> {reads, edits, writes}
        tool_counts = {}

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if source == "claude":
                        msg_type = obj.get("type")
                        if msg_type == "user" and not obj.get("toolUseResult") and not first_user_msg:
                            content = obj.get("message", {}).get("content", [])
                            first_user_msg = _extract_user_text(content)[:500]
                        elif msg_type == "assistant":
                            content = obj.get("message", {}).get("content", [])
                            if isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "tool_use":
                                        name = block.get("name", "")
                                        tool_counts[name] = tool_counts.get(name, 0) + 1
                                        inp = block.get("input", {})
                                        fp = inp.get("file_path") or inp.get("path") or ""
                                        if fp and not fp.startswith("/tmp"):
                                            home = str(Path.home())
                                            short = fp.replace(home, "~") if fp.startswith(home) else fp
                                            if short not in files_touched:
                                                files_touched[short] = {"reads": 0, "edits": 0, "writes": 0}
                                            if name in ("Read", "Glob", "Grep"):
                                                files_touched[short]["reads"] += 1
                                            elif name == "Edit":
                                                files_touched[short]["edits"] += 1
                                            elif name == "Write":
                                                files_touched[short]["writes"] += 1
                    elif source == "codex":
                        rec_type = obj.get("type")
                        payload = obj.get("payload", {})
                        if rec_type == "event_msg" and payload.get("type") == "user_message" and not first_user_msg:
                            first_user_msg = payload.get("message", "")[:500]
                        elif rec_type == "response_item" and payload.get("type") in ("function_call", "custom_tool_call"):
                            raw_name = payload.get("name", "")
                            name = _CODEX_TOOL_NAMES.get(raw_name, raw_name)
                            tool_counts[name] = tool_counts.get(name, 0) + 1
        except Exception:
            pass

        # Sort files: most edits first
        file_list = sorted(
            [{"path": fp, **counts} for fp, counts in files_touched.items()],
            key=lambda x: -(x["edits"] + x["writes"]),
        )[:30]

        return {"request": first_user_msg, "files": file_list, "tools": tool_counts}

    def _get_snippets(self) -> dict:
        """Solution Snippet Library from pre-aggregated DB."""
        import db as _db
        raw = _db.query_snippets(150)
        snippets = []
        for row in raw:
            snippets.append({
                "sessionId": row["session_id"],
                "sessionTitle": row.get("session_title") or "Untitled",
                "project": row.get("project") or "",
                "language": row.get("language") or "",
                "code": row.get("code") or "",
                "context": row.get("context") or "",
                "date": row.get("date") or "",
                "applied": bool(row.get("applied")),
            })
        return {"snippets": snippets}

    def _get_file_evolution(self, file_path: str) -> dict:
        """F13: Cross-session edit timeline for a specific file."""
        if not file_path:
            return {"file": "", "events": []}

        with _index_lock:
            sessions = dict(_index.get("sessions", {}))

        basename = os.path.basename(file_path)
        events = []

        for sid, meta in sessions.items():
            filepath = meta.get("filePath", "")
            source = meta.get("source", "claude")
            if not filepath or not os.path.exists(filepath):
                continue

            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    prev_user_msg = ""
                    for line in f:
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        msg_type = obj.get("type")
                        if source == "claude":
                            if msg_type == "user" and not obj.get("toolUseResult"):
                                content = obj.get("message", {}).get("content", [])
                                prev_user_msg = _extract_user_text(content)[:200]
                            elif msg_type == "assistant":
                                content = obj.get("message", {}).get("content", [])
                                if isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict) and block.get("type") == "tool_use":
                                            name = block.get("name", "")
                                            inp = block.get("input", {})
                                            fp = inp.get("file_path") or inp.get("path") or ""
                                            if fp and os.path.basename(fp) == basename and name in ("Edit", "Write"):
                                                events.append({
                                                    "sessionId": sid,
                                                    "sessionTitle": meta.get("title", ""),
                                                    "project": meta.get("projectName", ""),
                                                    "date": meta.get("date", ""),
                                                    "tool": name,
                                                    "context": prev_user_msg,
                                                })
            except Exception:
                continue

        events.sort(key=lambda e: e.get("date", ""))
        return {"file": file_path, "basename": basename, "events": events[:50]}

    def _get_project_health(self) -> dict:
        """F14: Project Health Dashboard — cross-project aggregate metrics."""
        with _index_lock:
            sessions = dict(_index.get("sessions", {}))

        projects = {}
        now = datetime.now()

        for sid, meta in sessions.items():
            pname = meta.get("projectName", "unknown")
            source = meta.get("source", "claude")
            date_str = meta.get("date", "")
            msgs = meta.get("userMessageCount", 0)

            if pname not in projects:
                projects[pname] = {
                    "name": pname,
                    "source": source,
                    "sessionCount": 0,
                    "totalMessages": 0,
                    "firstSeen": date_str,
                    "lastSeen": date_str,
                    "recentSessions": 0,  # last 7 days
                    "sessions_by_week": {},
                }
            p = projects[pname]
            p["sessionCount"] += 1
            p["totalMessages"] += msgs
            if date_str and (not p["firstSeen"] or date_str < p["firstSeen"]):
                p["firstSeen"] = date_str
            if date_str and (not p["lastSeen"] or date_str > p["lastSeen"]):
                p["lastSeen"] = date_str

            # Recent activity
            if date_str:
                try:
                    d = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    if (now - d).days <= 7:
                        p["recentSessions"] += 1
                    # Week bucket
                    week_key = d.strftime("%Y-W%W")
                    p["sessions_by_week"][week_key] = p["sessions_by_week"].get(week_key, 0) + 1
                except Exception:
                    pass

        # Compute staleness and trend
        result = []
        for pname, p in projects.items():
            staleness = 999
            if p["lastSeen"]:
                try:
                    last = datetime.fromisoformat(p["lastSeen"].replace("Z", "+00:00")).replace(tzinfo=None)
                    staleness = (now - last).days
                except Exception:
                    pass

            # Activity trend: compare last 2 weeks
            weeks = sorted(p["sessions_by_week"].keys())
            trend = "stable"
            if len(weeks) >= 2:
                last_week = p["sessions_by_week"].get(weeks[-1], 0)
                prev_week = p["sessions_by_week"].get(weeks[-2], 0)
                if last_week > prev_week * 1.5:
                    trend = "up"
                elif last_week < prev_week * 0.5:
                    trend = "down"

            result.append({
                "name": pname,
                "source": p["source"],
                "sessionCount": p["sessionCount"],
                "totalMessages": p["totalMessages"],
                "firstSeen": p["firstSeen"][:10] if p["firstSeen"] else "",
                "lastSeen": p["lastSeen"][:10] if p["lastSeen"] else "",
                "staleDays": staleness,
                "recentSessions": p["recentSessions"],
                "trend": trend,
            })

        result.sort(key=lambda p: (-p["recentSessions"], p["staleDays"]))
        return {"projects": result}

    def _json_response(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        # No CORS — local-only server, same-origin requests only
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, filepath: Path):
        ext = filepath.suffix.lower()
        mime = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".json": "application/json",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }.get(ext, "application/octet-stream")

        data = filepath.read_bytes()
        self.send_response(200)
        ct = f"{mime}; charset=utf-8" if mime.startswith("text/") or mime.endswith("javascript") or mime.endswith("json") else mime
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, code: int, msg: str):
        body = json.dumps({"error": msg}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _sse_event(self, data: dict):
        """Write a single SSE event and flush."""
        payload = json.dumps(data, ensure_ascii=False)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _start_sse(self):
        """Send SSE response headers."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def do_POST(self):
        try:
            self._do_POST_inner()
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                self._error(500, f"Internal server error: {type(e).__name__}")
            except Exception:
                pass

    def _do_POST_inner(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/chat/stream":
            self._handle_chat_stream()
        elif parsed.path == "/api/chat":
            self._handle_chat_legacy()
        elif parsed.path == "/api/evolve/sync":
            self._handle_evolve_sync()
        elif parsed.path == "/api/twin/analyze":
            self._handle_twin_analyze()
        elif parsed.path == "/api/twin/sync":
            self._handle_twin_sync()
        else:
            self._error(404, "Not found")

    MAX_POST_BODY = 10 * 1024 * 1024  # 10 MB

    def _read_post_body(self):
        try:
            content_len = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            self._error(400, "Invalid Content-Length")
            return None
        if content_len < 0 or content_len > self.MAX_POST_BODY:
            self._error(413, f"Request body too large (max {self.MAX_POST_BODY // 1024 // 1024}MB)")
            return None
        return self.rfile.read(content_len)

    def _handle_chat_stream(self):
        """SSE streaming chat endpoint."""
        raw = self._read_post_body()
        if raw is None:
            return  # error already sent
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self._error(400, "Invalid JSON")
            return

        prompt = data.get("prompt", "")
        context_type = data.get("contextType", "")
        session_id = data.get("sessionId", "")
        scope = data.get("scope", {})
        messages = data.get("messages", [])

        if not prompt:
            self._error(400, "No prompt")
            return

        full_prompt = self._build_chat_prompt(prompt, context_type, session_id, scope, messages)
        self._start_sse()

        # Global analysis needs more time (sub-agents, CLI exploration)
        chat_timeout = int(data.get("timeout", 900))
        chat_timeout = max(60, min(chat_timeout, 1800))  # clamp 1min-30min
        stream = _run_ai_engine_stream(full_prompt, allow_write=False, timeout=chat_timeout)
        try:
            for evt in stream:
                self._sse_event(evt)
        except BrokenPipeError:
            return
        except Exception as e:
            try:
                self._sse_event({"type": "error", "message": str(e)})
            except BrokenPipeError:
                pass
        finally:
            stream.close()

    def _handle_chat_legacy(self):
        """Original blocking chat endpoint (kept for compatibility)."""
        raw = self._read_post_body()
        if raw is None:
            return
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self._error(400, "Invalid JSON")
            return

        prompt = data.get("prompt", "")
        context_type = data.get("contextType", "")
        session_id = data.get("sessionId", "")
        scope = data.get("scope", {})
        messages = data.get("messages", [])

        if not prompt:
            self._error(400, "No prompt")
            return

        full_prompt = self._build_chat_prompt(prompt, context_type, session_id, scope, messages)

        try:
            legacy_timeout = int(data.get("timeout", 900))
            legacy_timeout = max(60, min(legacy_timeout, 1800))
            stdout, stderr, _ = _run_ai_engine(full_prompt, allow_write=False, timeout=legacy_timeout)
            output = stdout.strip()
            if not output and stderr:
                stderr = stderr.strip()
                noise = ["plugin manifest", "MCP", "Warning", "shutdown"]
                lines = [l for l in stderr.split("\n") if not any(n in l for n in noise)]
                if lines:
                    output = "Error: " + "\n".join(lines[:5])
                else:
                    output = "(No output)"
            if not output:
                output = "(No output)"
        except FileNotFoundError as e:
            output = f"Error: {e}"
        except subprocess.TimeoutExpired:
            output = f"Error: Request timed out ({legacy_timeout // 60} min limit)"
        except Exception as e:
            output = f"Error: {str(e)}"

        self._json_response({"response": output})

    @staticmethod
    def _compress_chat_history(messages: list) -> str:
        """Compress chat history into a bounded transcript for prompt inclusion."""
        if not messages or not isinstance(messages, list):
            return ""
        MAX_TOTAL_CHARS = 200_000  # ~50k tokens budget
        ASSISTANT_TRUNCATE = 3000  # per-message cap for assistant

        # Filter and validate
        valid = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role", "")
            content = m.get("content", "")
            if role not in ("user", "assistant") or not isinstance(content, str):
                continue
            # Skip error/abort messages
            if content.startswith("**Error:**") or content.endswith("*(已停止)*"):
                continue
            valid.append((role, content))

        if not valid:
            return ""

        # Truncate long assistant messages
        processed = []
        for role, content in valid:
            if role == "assistant" and len(content) > ASSISTANT_TRUNCATE:
                content = content[:ASSISTANT_TRUNCATE - 200] + "\n...[truncated]...\n" + content[-150:]
            processed.append((role, content))

        # Check total size; if over budget, keep head 2 + as many tail as fit
        total = sum(len(c) for _, c in processed)
        if total > MAX_TOTAL_CHARS and len(processed) > 4:
            head = processed[:2]
            head_size = sum(len(c) for _, c in head)
            remaining = MAX_TOTAL_CHARS - head_size - 100  # 100 for omission marker
            tail = []
            for role, content in reversed(processed[2:]):
                if remaining - len(content) < 0 and tail:
                    break
                tail.insert(0, (role, content))
                remaining -= len(content)
            omitted = len(processed) - len(head) - len(tail)
            processed = head + [(None, f"[... {omitted} earlier messages omitted ...]")] + tail

        # Format as numbered transcript
        lines = []
        idx = 1
        for role, content in processed:
            if role is None:
                lines.append(content)
            else:
                label = "User" if role == "user" else "Assistant"
                lines.append(f"[{idx}] {label}:\n{content}")
                idx += 1

        return "\n\n".join(lines)

    def _build_chat_prompt(self, prompt: str, context_type: str, session_id: str, scope: dict = None, messages: list = None) -> str:
        """Build a context-enriched prompt for the AI engine with rich metadata and CLI tools."""
        cli_path = str(Path(__file__).resolve().parent / "analyze.py")
        context_parts = [
            f"You have a CLI tool for analyzing conversation history: python3 {cli_path} <command> [options]",
            "Commands: sessions, read <id> [-s summary], search <query>, queries [--session <id>] [-k keyword], corrections, decisions, errors, stats, files, highlights",
            "Each command supports: --date (1d|7d|30d|90d|all) --source (claude|codex|all) --project <name> --limit N --json",
            "USE THESE TOOLS to efficiently analyze data instead of reading raw JSONL files directly.",
            "",
            "Data directories (JSONL session files):",
            f"  Claude Code: {PROJECTS_DIR}/*/  (one subfolder per project)",
            f"  Codex CLI:   {CODEX_SESSIONS_DIR}/  and  {CODEX_ARCHIVED_DIR}/",
            "",
        ]

        if context_type == "session" and session_id:
            with _index_lock:
                meta = _index.get("sessions", {}).get(session_id)
            if meta:
                fp = meta.get("filePath", "")
                title = meta.get("title", "Untitled")
                project = meta.get("projectName", "")
                source = meta.get("source", "claude")
                msg_count = meta.get("userMessageCount", 0)

                context_parts.append("--- Analysis Context ---")
                context_parts.append("")
                context_parts.append(f"You are analyzing a {source} session: '{title}' from project '{project}'.")
                context_parts.append(f"Quick read: python3 {cli_path} read {session_id}")
                context_parts.append(f"Session file (JSONL): {fp}")
                context_parts.append(f"User messages: {msg_count}")

                # Include user message previews for quick context (from DB)
                import db as _db
                user_msgs = _db.get_session_messages(session_id, role="user")
                if user_msgs:
                    context_parts.append("\nConversation outline (user messages preview):")
                    for i, msg in enumerate(user_msgs[:12]):
                        text = (msg.get("text", "") or "")[:200].replace("\n", " ")
                        context_parts.append(f"  [{i+1}] {text}")

                context_parts.append(f"\nPrefer using the CLI tool (python3 {cli_path} read {session_id}) over reading raw JSONL.")
                context_parts.append("If you need raw JSONL: each line is a JSON object with type (user/assistant), message.content[] blocks (text/tool_use/thinking), timestamp.")

        elif context_type == "global":
            scope = scope or {}
            # Default to last 7 days unless explicitly set
            if not scope.get("date"):
                scope["date"] = "7d"
            # Build CLI flags hint for Codex
            cli_flags = []
            if scope.get("date"):
                cli_flags.append(f"--date {scope['date']}")
            if scope.get("source") and scope["source"] != "all":
                cli_flags.append(f"--source {scope['source']}")
            if scope.get("project"):
                cli_flags.append(f"--project \"{scope['project']}\"")
            flags_str = " ".join(cli_flags) if cli_flags else ""
            context_parts.append("--- Analysis Context ---")
            context_parts.append("")
            context_parts.append(f"Current scope filters: {flags_str or '(none)'}")
            context_parts.append(f"IMPORTANT: Always pass these flags to the CLI tool. Example: python3 {cli_path} stats {flags_str}")
            context_parts.append("")

            with _index_lock:
                sessions = dict(_index.get("sessions", {}))

            # Apply scope filters
            filtered = {}
            now = datetime.now()
            for sid, m in sessions.items():
                if scope.get("project") and m.get("projectName") != scope["project"]:
                    continue
                if scope.get("source") and scope["source"] != "all" and m.get("source", "claude") != scope["source"]:
                    continue
                if scope.get("date") and scope["date"] != "all":
                    date_str = m.get("date", "")
                    if date_str:
                        try:
                            d = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                            days_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
                            max_days = days_map.get(scope["date"], 9999)
                            if (now - d).days > max_days:
                                continue
                        except Exception:
                            pass
                filtered[sid] = m

            total = len(filtered)
            # Project breakdown
            proj_counts = {}
            for sid, m in filtered.items():
                pname = m.get("projectName", "unknown")
                proj_counts[pname] = proj_counts.get(pname, 0) + 1

            scope_desc = []
            if scope.get("project"):
                scope_desc.append(f"project={scope['project']}")
            if scope.get("date") and scope["date"] != "all":
                scope_desc.append(f"time={scope['date']}")
            if scope.get("source") and scope["source"] != "all":
                scope_desc.append(f"source={scope['source']}")

            context_parts.append(f"Scope: {total} sessions{' (filter: ' + ', '.join(scope_desc) + ')' if scope_desc else ''}.")
            # Compact project breakdown
            top_projects = sorted(proj_counts.items(), key=lambda x: -x[1])[:10]
            context_parts.append("Projects: " + ", ".join(f"{p}({c})" for p, c in top_projects))
            context_parts.append("")

            # Pre-computed data: digest + stats + aggregates (same as Evolve)
            source = scope.get("source", "all")
            date = scope.get("date", "7d")
            project = scope.get("project", "")

            digest = self._collect_profile_digest(source, date, project, cli_path)
            if digest:
                context_parts.append("# Pre-computed Profile Digest (data overview — do NOT re-run profile-digest)")
                context_parts.append(digest)
                context_parts.append("")

            stats = self._collect_stats(source, date, project, cli_path)
            if stats:
                context_parts.append("# Pre-collected Stats (do NOT re-run stats)")
                context_parts.append(stats)
                context_parts.append("")

            aggregates = self._collect_aggregates()
            if aggregates:
                context_parts.append("# Pre-collected Aggregates (do NOT re-run aggregates)")
                context_parts.append(aggregates)
                context_parts.append("")

            # Sub-agent guidance for complex analysis
            if total > 10:
                digest_cmd = f"python3 {cli_path} profile-digest --date {date} --source {source}" + (f' --project "{project}"' if project else "")
                context_parts.extend([
                    "# Execution Strategy",
                    "",
                    "For complex analysis tasks, dispatch 2-3 sub-agents (via Agent tool) in parallel for efficiency.",
                    "Each agent's prompt MUST include:",
                    f"  - Digest command: `{digest_cmd}` (agent runs this to get the overview)",
                    f"  - CLI tool: `python3 {cli_path} <command> {flags_str}`",
                    "  - Its assigned focus area and specific exploration instructions",
                    "",
                    "Efficiency rules:",
                    "- Use the digest above as a map — skip to relevant sections, don't re-scan everything.",
                    "- Batch CLI commands in one Bash call (e.g. echo '=== A ==='; python3 ... ; echo '=== B ==='; python3 ...)",
                    "- Use `read -s <id>` for session context, `search <keyword>` for targeted exploration.",
                    "- Do NOT re-run stats/aggregates/profile-digest — that data is already above.",
                    "",
                ])

        # Append chat history if available (multi-turn context)
        chat_history = self._compress_chat_history(messages) if messages else ""
        if chat_history:
            context_parts.append("")
            context_parts.append("--- Chat History ---")
            context_parts.append("")
            context_parts.append(chat_history)

        if context_parts:
            return "\n".join(context_parts) + "\n\n--- User Request ---\n" + prompt
        return prompt

    def _handle_evolve_sync(self):
        """Handle POST /api/evolve/sync — preview or execute sync to Claude Code."""
        import db as _db
        raw = self._read_post_body()
        if raw is None:
            return
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self._error(400, "Invalid JSON")
            return

        action = data.get("action", "preview")
        targets = data.get("targets", [])
        scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
        source = scope.get("source", "all")
        date = scope.get("date", "7d")
        project = scope.get("project", "")
        try:
            engine = _normalize_ai_engine(scope.get("engine", "auto"))
        except ValueError as e:
            self._error(400, str(e))
            return

        if action not in ("preview", "execute"):
            self._error(400, "Invalid action")
            return

        result = {}

        if "memory" in targets:
            row = _db.evolve_get("memory", source, date, project, engine)
            if row:
                try:
                    mem_data = row["data"]
                    if action == "preview":
                        result["memory"] = _evolve_sync_memory_preview(mem_data)
                    else:
                        result["memory"] = _evolve_sync_memory_execute(mem_data)
                except Exception as e:
                    result["memory"] = {"error": str(e)}
            else:
                result["memory"] = {"error": "Memory cache not found — run Refresh first"}

        if "claude_md" in targets:
            row = _db.evolve_get("profile", source, date, project, engine)
            if row:
                try:
                    prof_data = row["data"]
                    if action == "preview":
                        result["claude_md"] = _evolve_sync_claude_md_preview(prof_data)
                    else:
                        result["claude_md"] = _evolve_sync_claude_md_execute(prof_data)
                except Exception as e:
                    result["claude_md"] = {"error": str(e)}
            else:
                result["claude_md"] = {"error": "Profile cache not found — run Refresh first"}

        result["ok"] = all("error" not in v for v in result.values() if isinstance(v, dict))
        self._json_response(result)

    def _run_twin_ai_stage(self, prompt: str, stage_label: str) -> bool:
        """Stream a Twin AI stage and stop on either exception or SSE error event."""
        stream = _run_ai_engine_stream(prompt, allow_write=True, timeout=600)
        try:
            for evt in stream:
                self._sse_event(evt)
                if evt.get("type") == "error":
                    return False
            return True
        except BrokenPipeError:
            raise
        except Exception as e:
            self._sse_event({"type": "error", "message": f"{stage_label} failed: {e}"})
            return False
        finally:
            stream.close()

    def _handle_twin_analyze(self):
        """POST /api/twin/analyze — run 4-stage cognitive handbook extraction via AI."""
        import db as _db
        cli_path = str(Path(__file__).resolve().parent / "analyze.py")

        self._start_sse()

        # Stage 1: Evidence event extraction
        self._sse_event({"type": "text", "content": "Stage 1/4: 从对话历史中提取决策事件 (Evidence Events)...\n"})

        stage1_prompt = self._build_twin_stage1_prompt(cli_path)
        try:
            if not self._run_twin_ai_stage(stage1_prompt, "Stage 1"):
                return
        except BrokenPipeError:
            return

        # Stage 2: Judgment card distillation
        self._sse_event({"type": "text", "content": "\n\nStage 2/4: 从事件中蒸馏判断卡 (Judgment Cards)...\n"})

        stage2_prompt = self._build_twin_stage2_prompt(cli_path)
        try:
            if not self._run_twin_ai_stage(stage2_prompt, "Stage 2"):
                return
        except BrokenPipeError:
            return

        # Stage 3: Cognitive trait inference
        self._sse_event({"type": "text", "content": "\n\nStage 3/4: 从判断卡归纳认知特质 (Cognitive Traits)...\n"})

        stage3_prompt = self._build_twin_stage3_prompt(cli_path)
        try:
            if not self._run_twin_ai_stage(stage3_prompt, "Stage 3"):
                return
        except BrokenPipeError:
            return

        # Stage 4: Compile Runtime Pack (pure Python, no AI)
        self._sse_event({"type": "text", "content": "\n\nStage 4/4: 编译 Runtime Pack (twin-compile)...\n"})
        try:
            r = subprocess.run(
                [sys.executable, cli_path, "twin-compile"],
                capture_output=True, text=True, timeout=30,
            )
            self._sse_event({"type": "text", "content": r.stdout or "(no output)"})
            if r.returncode != 0:
                msg = (r.stderr or r.stdout or "unknown error")[:500]
                self._sse_event({"type": "error", "message": f"Stage 4 failed: {msg}"})
                return
        except Exception as e:
            self._sse_event({"type": "error", "message": f"Stage 4 failed: {e}"})
            return

        # Summary
        _db.init_db()
        stats = _db.get_twin_stats()
        summary_parts = []
        for t in ["evidence_events", "judgment_cards", "cognitive_traits"]:
            count = stats.get(t, {}).get("count", 0)
            if count > 0:
                label = t.replace("_", " ")
                summary_parts.append(f"{label}: {count}")

        summary = ", ".join(summary_parts) if summary_parts else "暂无数据"
        try:
            self._sse_event({"type": "text", "content": f"\n\n✅ 分析完成 — {summary}"})
            self._sse_event({"type": "done", "content": summary})
        except BrokenPipeError:
            pass

    def _build_twin_stage1_prompt(self, cli_path: str) -> str:
        """Build prompt for Stage 1: Evidence event extraction from conversation history."""
        digest = self._collect_profile_digest("all", "all", "", cli_path)

        return f"""# Background

You are extracting structured EVIDENCE EVENTS from a user's AI conversation history.
An evidence event records: what the AI did → how the user reacted → what lesson was learned.

# CLI Tool

  python3 {cli_path} <command> [options]

Commands for exploration:
  corrections    — Find where the user corrected/rejected AI output (50+ signal words)
  queries        — Extract user questions/requests across sessions
  highlights     — Sessions ranked by correction frequency
  read <id> -s   — Read a specific session (summary mode)
  search <q>     — Full-text search across sessions

Commands for reading existing data:
  twin-events [--domain X] [--signal Y] [--limit N] --json  — List existing evidence events
  twin-get events <id>                                      — Get a single event by ID
  twin-search events --q "keyword" --json                   — Search events by keyword

Commands for writing:
  twin-add events       — Add a new event (JSON from stdin, auto-generates ID)
  twin-edit events <id> — Edit an existing event (JSON from stdin, overwrites)
  twin-batch            — Execute multiple add/edit operations in one call

# Pre-computed Profile Digest

{digest}

# Task

1. First, run `python3 {cli_path} twin-events --json` to see ALL existing events. Check what's already been captured — avoid duplicates.
2. Run `python3 {cli_path} corrections --limit 100` to get all correction events.
3. Run `python3 {cli_path} highlights --limit 20` to find high-signal sessions.
4. For the top 5-8 most interesting sessions, run `python3 {cli_path} read <id> -s` to understand context.
5. Also run `python3 {cli_path} queries --limit 50` and look for acceptance patterns — cases where the user did NOT correct the AI (positive signals).

From these, extract new evidence events. Compare with existing events — if an event already exists for the same session and similar situation, use `twin-edit` to update/enrich it. Only `twin-add` genuinely new events.

Write events using the CRUD tools:

# Add a new event:
python3 {cli_path} twin-add events <<'EOF'
{{
  "session_id": "actual-session-id",
  "event_index": 1,
  "task_type": "coding|review|design|research|communication",
  "ai_action": "AI did what (1 sentence)",
  "user_reaction": "User reacted how (1 sentence)",
  "resolution": "What happened in the end",
  "lesson": "What we learned from this (reusable insight)",
  "signal_type": "correction|acceptance|escalation|question",
  "signal_intensity": 0.0-1.0,
  "domain": "domain tag (e.g., coding/scope, review/verification, design/architecture)"
}}
EOF

# Edit an existing event (e.g. enrich lesson, update intensity):
python3 {cli_path} twin-edit events <event_id> <<'EOF'
{{"lesson": "improved lesson text", "signal_intensity": 0.85}}
EOF

# Or use batch for multiple operations at once:
python3 {cli_path} twin-batch <<'EOF'
{{"operations": [
  {{"resource": "events", "action": "add", "data": {{...}}}},
  {{"resource": "events", "action": "edit", "id": "ev_xxx", "data": {{...}}}}
]}}
EOF

Quality requirements:
- MUST include real session_id from the corrections/highlights data
- signal_intensity: 0.9+ for explicit strong corrections, 0.5-0.8 for mild corrections, 0.3-0.5 for acceptance signals
- domain: use slash format like "coding/scope", "review/neutrality", "design/simplicity"
- lesson: write as a reusable insight, not specific to one case
- Balance: include BOTH correction episodes AND acceptance episodes (positive signals)
- IMPORTANT: Always check existing events first. If a similar event exists, use twin-edit to enrich it rather than creating a duplicate with twin-add.
- All text in Chinese
"""

    def _build_twin_stage2_prompt(self, cli_path: str) -> str:
        """Build prompt for Stage 2: Judgment card distillation from evidence events."""
        import db as _db
        _db.init_db()

        # Get existing cards for dedup
        existing_cards = _db.cm_get_all("judgment_cards", limit=100)
        events = _db.cm_get_all("evidence_events", order="created_at DESC", limit=100)
        events_json = json.dumps([dict(e) for e in events], ensure_ascii=False, default=str)

        # Get latest Profile/Memory as supplementary input from SQLite.
        profile_summary = ""
        memory_summary = ""
        try:
            pr = _db.evolve_latest("profile")
            if pr:
                cats = [c.get("name", "") for c in pr["data"].get("categories", [])]
                profile_summary = f"Existing Profile categories: {', '.join(cats)}"
        except Exception:
            pass
        try:
            mr = _db.evolve_latest("memory")
            if mr:
                labels = [n.get("label", "") for n in mr["data"].get("nodes", [])]
                memory_summary = f"Existing Memory labels: {', '.join(labels)}"
        except Exception:
            pass

        existing_cards_str = ""
        if existing_cards:
            lines = []
            for c in existing_cards[:30]:
                lines.append(f"  id={c.get('id','')} applies_when={json.dumps(c.get('applies_when',''), ensure_ascii=False)} "
                             f"judgment={json.dumps((c.get('judgment','') or '')[:80], ensure_ascii=False)} "
                             f"tags={c.get('tags','')} status={c.get('status','')} confidence={c.get('confidence','')}")
            existing_cards_str = "\n".join(lines)
        else:
            existing_cards_str = "  (empty — no existing cards)"

        return f"""# Background

You are distilling JUDGMENT CARDS from structured evidence events extracted from a user's AI conversation history.
A judgment card captures a situation-specific judgment pattern: when does this apply → how the user thinks about it → what the AI should do.

# CLI Tool

  python3 {cli_path} <command>

Commands for reading:
  twin-cards [--status X] [--tag Y] --json    — List all existing judgment cards
  twin-get cards <id>                         — Get a single card with linked events
  twin-search cards --q "keyword" --json      — Search cards by keyword
  twin-events --json                          — List all evidence events

Commands for writing:
  twin-add cards        — Add a new card (JSON from stdin)
  twin-edit cards <id>  — Edit an existing card (JSON from stdin, overwrites)
  twin-link <event_id> <card_id>  — Link an event to a card
  twin-batch            — Execute multiple operations in one call

# Evidence Events (input data)

{events_json}

# Supplementary data

{profile_summary}
{memory_summary}

# Existing Judgment Cards (for dedup — merge if similar, insert if new)

{existing_cards_str}

# Task

Analyze the events above and distill judgment cards. This is INCREMENTAL — you are updating an existing knowledge base, not building from scratch.

**Workflow:**

1. First review the existing cards above carefully.
2. For each cluster of related events, decide:
   - **If a similar card already exists** → use `twin-edit cards <id>` to refine it (improve judgment text, update confidence, etc.)
   - **If it's a genuinely new pattern** → use `twin-add cards` to create a new card
3. After creating/updating cards, link events to cards using `twin-link <event_id> <card_id>`

**Writing examples:**

# Add a new card:
python3 {cli_path} twin-add cards <<'EOF'
{{
  "applies_when": "触发场景（1-2句）",
  "judgment": "用户的推理逻辑（自然语言段落，2-4句）",
  "agent_action": "AI 应该怎么做（1-2句）",
  "exceptions": "例外条件",
  "tags": "[\\"tag1\\", \\"tag2\\"]",
  "confidence": 0.7,
  "status": "hypothesis",
  "evidence_count": 1
}}
EOF

# Edit an existing card (e.g. strengthen with new evidence):
python3 {cli_path} twin-edit cards jc_xxx <<'EOF'
{{
  "judgment": "refined judgment text...",
  "confidence": 0.85,
  "status": "emerging",
  "evidence_count": 3
}}
EOF

# Link events to cards:
python3 {cli_path} twin-link ev_xxx jc_yyy

# Or batch multiple operations:
python3 {cli_path} twin-batch <<'EOF'
{{"operations": [
  {{"resource": "cards", "action": "add", "data": {{...}}}},
  {{"resource": "cards", "action": "edit", "id": "jc_xxx", "data": {{...}}}},
  {{"resource": "link", "action": "link", "from": "ev_xxx", "to": "jc_yyy"}}
]}}
EOF

# Key design principles

- **judgment field is natural language**: Merge the user's values, causal reasoning into a coherent paragraph. The consumer is an LLM — NL is its most efficient input format.
- **agent_action is executable**: Write it as a concrete instruction the AI can follow, not an abstract principle.
- **Tags for retrieval**: Use consistent tag vocabulary (scope, style, communication, design, review, testing, etc.)
- **Status rules**: first appearance → "hypothesis"; supported by 2+ events from different contexts → "emerging"; 3+ events across projects → "confirmed"
- **All text in Chinese**
- **Dedup carefully**: Two events about "不要改无关文件" and "只改必要代码" should merge into one card, not create two. Use `twin-edit` to merge, not `twin-add` to duplicate.
"""

    def _build_twin_stage3_prompt(self, cli_path: str) -> str:
        """Build prompt for Stage 3: Cognitive trait inference from judgment cards."""
        import db as _db
        _db.init_db()

        cards = _db.cm_get_all("judgment_cards", order="confidence DESC", limit=100)
        cards_json = json.dumps([dict(c) for c in cards], ensure_ascii=False, default=str)

        existing_traits = _db.cm_get_all("cognitive_traits", limit=50)
        existing_str = ""
        if existing_traits:
            lines = []
            for t in existing_traits[:20]:
                lines.append(f"  id={t.get('id','')} name={json.dumps(t.get('name',''), ensure_ascii=False)} "
                             f"category={t.get('category','')} status={t.get('status','')} strength={t.get('strength','')}")
            existing_str = "\n".join(lines)
        else:
            existing_str = "  (empty — no existing traits)"

        return f"""# Background

You are inferring COGNITIVE TRAITS from judgment cards. Traits are personality-level characteristics
that explain WHY the user makes certain judgments. Multiple cards pointing to the same underlying
pattern should be abstracted into one trait.

# CLI Tool

  python3 {cli_path} <command>

Commands for reading:
  twin-traits [--category X] [--status X] --json  — List existing cognitive traits
  twin-get traits <id>                             — Get a single trait by ID
  twin-search traits --q "keyword" --json          — Search traits by keyword
  twin-cards --json                                — List all judgment cards

Commands for writing:
  twin-add traits        — Add a new trait (JSON from stdin)
  twin-edit traits <id>  — Edit an existing trait (JSON from stdin, overwrites)
  twin-link <card_id> <trait_id>  — Link a card to a trait
  twin-batch             — Execute multiple operations in one call

# Judgment Cards (input data)

{cards_json}

# Existing Cognitive Traits (for dedup)

{existing_str}

# Task

Analyze the judgment cards above and infer cognitive traits. This is INCREMENTAL — update existing traits or add new ones.

Categories:
- **价值取向**: What the user protects/sacrifices (e.g., 极简主义, 最小影响原则)
- **决策风格**: How the user makes judgments (e.g., 证据先行, 风险厌恶, 谨慎型)
- **协作模式**: How the user works with AI (e.g., 高控制偏好, 主导型, 方案先行)
- **能力边界**: Domain expertise levels (e.g., 后端专家/前端学习中)
- **思维模式**: Cognitive habits (e.g., 系统性思维, 发散-收敛型)

**Workflow:**

1. Review existing traits above.
2. For each group of related cards:
   - **If a similar trait exists** → `twin-edit traits <id>` to refine description, update strength
   - **If genuinely new** → `twin-add traits`
3. Link supporting cards to traits: `twin-link jc_xxx ct_yyy`

**Writing examples:**

# Add a new trait:
python3 {cli_path} twin-add traits <<'EOF'
{{
  "name": "特质名称",
  "category": "价值取向|决策风格|协作模式|能力边界|思维模式",
  "description": "自然语言描述（2-4句）",
  "strength": 0.7,
  "supporting_card_ids": "[\\"jc_xxx\\", \\"jc_yyy\\"]",
  "status": "emerging",
  "evidence_count": 2
}}
EOF

# Edit an existing trait:
python3 {cli_path} twin-edit traits ct_xxx <<'EOF'
{{
  "description": "refined description...",
  "strength": 0.85,
  "status": "confirmed"
}}
EOF

# Key principles
- **Each trait must be supported by ≥2 cards**: Don't infer traits from a single card
- **description is natural language**: Explain the trait so an AI can predict behavior in new scenarios
- **supporting_card_ids must reference real card IDs** from the input data above
- **Dedup carefully**: If a similar trait exists, use twin-edit to enrich it, not twin-add to duplicate
- **Status follows card evidence**: all hypothesis cards → hypothesis; emerging/confirmed cards → emerging/confirmed
- **All text in Chinese**
"""

    def _handle_twin_sync(self):
        """POST /api/twin/sync — compile runtime pack from cards+traits into CLAUDE.md."""
        import db as _db

        CM_MARKER_START = "<!-- cognitive-handbook:start -->"
        CM_MARKER_END = "<!-- cognitive-handbook:end -->"

        try:
            cards = _db.cm_get_all(
                "judgment_cards",
                where="status IN ('confirmed','emerging')",
                order="confidence DESC",
                limit=25,
            )
            traits = _db.cm_get_all(
                "cognitive_traits",
                where="status IN ('confirmed','emerging')",
                order="strength DESC",
                limit=15,
            )
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})
            return

        # Build CLAUDE.md section — render as natural language
        lines = [CM_MARKER_START, "## Cognitive Handbook (Auto-sync)", ""]

        if traits:
            lines.append("### 关于这位用户")
            lines.append("")
            for t in traits:
                name = t.get("name") or ""
                desc = t.get("description") or ""
                lines.append(f"**{name}**。{desc}")
                lines.append("")

        if cards:
            lines.append("### 场景判断")
            lines.append("")
            for c in cards:
                when = c.get("applies_when") or ""
                judgment = c.get("judgment") or ""
                action = c.get("agent_action") or ""
                exceptions = c.get("exceptions") or ""
                lines.append(f"**{when}**：{judgment}")
                if action:
                    lines.append(f"→ {action}")
                if exceptions:
                    lines.append(f"例外：{exceptions}")
                lines.append("")

        lines.append(CM_MARKER_END)
        section = "\n".join(lines) + "\n"

        CLAUDE_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = CLAUDE_MD_PATH.read_text(encoding="utf-8") if CLAUDE_MD_PATH.exists() else ""

        if CM_MARKER_START in existing and CM_MARKER_END in existing:
            start_idx = existing.index(CM_MARKER_START)
            end_idx = existing.index(CM_MARKER_END) + len(CM_MARKER_END)
            new_text = existing[:start_idx] + section + existing[end_idx:]
            claude_md_status = "replaced"
        else:
            if existing and not existing.endswith("\n\n"):
                existing = existing.rstrip("\n") + "\n\n"
            new_text = existing + section
            claude_md_status = "appended"
        CLAUDE_MD_PATH.write_text(new_text, encoding="utf-8")

        self._json_response({
            "ok": True,
            "cards_synced": len(cards),
            "traits_synced": len(traits),
            "claude_md": {"status": claude_md_status, "lines": len(section.strip().split("\n"))},
        })

    def log_message(self, format, *args):
        """Suppress default request logging for cleaner output."""
        pass


# ---------------------------------------------------------------------------
# Evolve Sync — pure Python format conversion
# ---------------------------------------------------------------------------
CLAUDE_MD_PATH = Path.home() / ".claude" / "CLAUDE.md"
MEMORY_DIR = Path.home() / ".claude" / "memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
SYNC_MARKER_START = "<!-- evolve-sync:profile:start -->"
SYNC_MARKER_END = "<!-- evolve-sync:profile:end -->"


def _sanitize_filename(text: str) -> str:
    """Convert text to a safe filename component."""
    # Keep alphanumeric, Chinese chars, hyphens, underscores
    clean = re.sub(r'[^\w\u4e00-\u9fff-]', '_', text)
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean[:60] if clean else "unnamed"


def _evolve_sync_memory_preview(mem_data: dict) -> dict:
    """Generate preview of what memory sync would do."""
    nodes = {n["id"]: n for n in mem_data.get("nodes", [])}
    cards = {c["id"]: c for c in mem_data.get("cards", [])}
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    files = []
    for nid, node in nodes.items():
        if node.get("confidence") == "low":
            files.append({"id": nid, "filename": "", "label": node.get("label", ""), "status": "skip"})
            continue
        fname = f"evolve_{nid}.md"
        fpath = MEMORY_DIR / fname
        status = "update" if fpath.exists() else "create"
        files.append({"id": nid, "filename": fname, "label": node.get("label", ""), "status": status})

    summary = {"create": 0, "update": 0, "skip": 0}
    for f in files:
        summary[f["status"]] = summary.get(f["status"], 0) + 1

    return {"files": files, "summary": summary}


def _evolve_sync_memory_execute(mem_data: dict) -> dict:
    """Write memory files from evolve data."""
    nodes = {n["id"]: n for n in mem_data.get("nodes", [])}
    cards = {c["id"]: c for c in mem_data.get("cards", [])}
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    created, updated = 0, 0
    written_files = []

    for nid, node in nodes.items():
        if node.get("confidence") == "low":
            continue
        if node.get("status") == "stale":
            continue

        card = cards.get(nid, {})
        label = node.get("label", "")
        name_kebab = _sanitize_filename(label)
        fname = f"evolve_{nid}.md"
        fpath = MEMORY_DIR / fname

        is_update = fpath.exists()

        # Build content: prefer trigger/instruction format, fall back to v1 content
        trigger = card.get("trigger", "")
        instruction = card.get("instruction", "")
        avoid = card.get("avoid", "")

        if trigger and instruction:
            body = f"When: {trigger}\nDo: {instruction}"
            if avoid:
                body += f"\nAvoid: {avoid}"
        else:
            body = card.get("content", label)

        content_lines = [
            "---",
            f"name: {name_kebab}",
            f"description: {label}",
            "type: feedback",
            "source: evolve-sync",
            "---",
            "",
            body,
        ]

        # Evidence
        evidence = card.get("evidence", "")
        if isinstance(evidence, list) and evidence:
            content_lines.extend(["", "**Evidence:**"])
            for ev in evidence[:3]:
                if isinstance(ev, dict):
                    q = ev.get("quote", "")
                    sid = ev.get("sessionId", "")
                    d = ev.get("date", "")
                    content_lines.append(f'- "{q}" ({sid}, {d})')
                else:
                    content_lines.append(f"- {ev}")
        elif isinstance(evidence, str) and evidence:
            content_lines.extend(["", f"**Evidence:** {evidence}"])

        meta_parts = []
        if card.get("firstSeen"):
            meta_parts.append(f"**First seen:** {card['firstSeen']}")
        if card.get("lastSeen"):
            meta_parts.append(f"**Last seen:** {card['lastSeen']}")
        if node.get("frequency"):
            meta_parts.append(f"**Frequency:** {node['frequency']}")
        if node.get("priority"):
            meta_parts.append(f"**Priority:** {node['priority']}")
        if meta_parts:
            content_lines.append(" | ".join(meta_parts))

        content_lines.append("")  # trailing newline
        fpath.write_text("\n".join(content_lines), encoding="utf-8")
        written_files.append(fname)

        if is_update:
            updated += 1
        else:
            created += 1

    # Update MEMORY.md index
    _update_memory_index(written_files, nodes)

    return {"created": created, "updated": updated}


def _update_memory_index(written_files: list, nodes: dict):
    """Add new evolve entries to MEMORY.md if not already listed."""
    if not MEMORY_INDEX.exists():
        return

    existing_text = MEMORY_INDEX.read_text(encoding="utf-8")
    existing_lower = existing_text.lower()
    new_lines = []

    for fname in written_files:
        if fname.lower() in existing_lower:
            continue
        # Find the node for this file
        nid = fname.replace("evolve_", "").replace(".md", "")
        node = nodes.get(nid, {})
        label = node.get("label", fname)
        new_lines.append(f"| [{fname}]({fname}) | feedback | {label} |")

    if new_lines:
        # Append to file
        if not existing_text.endswith("\n"):
            existing_text += "\n"
        existing_text += "\n".join(new_lines) + "\n"
        MEMORY_INDEX.write_text(existing_text, encoding="utf-8")


def _evolve_sync_claude_md_preview(prof_data: dict) -> dict:
    """Generate preview of what CLAUDE.md sync would do."""
    categories = prof_data.get("categories", [])
    radar = prof_data.get("radar", {})
    dims = radar.get("dimensions", [])

    # Count items (excluding low confidence)
    item_count = sum(
        len([i for i in cat.get("items", []) if i.get("confidence") != "low"])
        for cat in categories
    )

    # Generate the section to estimate lines
    section = _build_profile_section(prof_data)
    line_count = len(section.strip().split("\n"))

    status = "replace" if _claude_md_has_marker() else "append"

    return {
        "status": status,
        "categories": len(categories),
        "radar_dims": len(dims),
        "items": item_count,
        "lines": line_count,
    }


def _evolve_sync_claude_md_execute(prof_data: dict) -> dict:
    """Write profile section to CLAUDE.md."""
    section = _build_profile_section(prof_data)

    CLAUDE_MD_PATH.parent.mkdir(parents=True, exist_ok=True)

    if CLAUDE_MD_PATH.exists():
        existing = CLAUDE_MD_PATH.read_text(encoding="utf-8")
    else:
        existing = ""

    if SYNC_MARKER_START in existing and SYNC_MARKER_END in existing:
        # Replace between markers
        start_idx = existing.index(SYNC_MARKER_START)
        end_idx = existing.index(SYNC_MARKER_END) + len(SYNC_MARKER_END)
        new_text = existing[:start_idx] + section + existing[end_idx:]
        status = "replaced"
    else:
        # Append
        if existing and not existing.endswith("\n\n"):
            existing = existing.rstrip("\n") + "\n\n"
        new_text = existing + section
        status = "appended"

    CLAUDE_MD_PATH.write_text(new_text, encoding="utf-8")
    line_count = len(section.strip().split("\n"))
    return {"status": status, "lines": line_count}


def _build_profile_section(prof_data: dict) -> str:
    """Build the markdown section for CLAUDE.md from profile data."""
    lines = [SYNC_MARKER_START, "## User Profile (Evolve Auto-sync)", ""]

    for cat in prof_data.get("categories", []):
        icon = cat.get("icon", "")
        name = cat.get("name", "")
        tags = cat.get("tags", [])
        items = [i for i in cat.get("items", []) if i.get("confidence") != "low"]

        if not items:
            continue

        lines.append(f"### {icon} {name}")
        if tags:
            lines.append(f"- **标签**: {', '.join(tags)}")
        for item in items:
            lines.append(f"- {item['text']}")
        lines.append("")

    # Radar
    dims = prof_data.get("radar", {}).get("dimensions", [])
    if dims:
        lines.append("### 📊 能力雷达")
        lines.append("| 领域 | 评分 | 依据 |")
        lines.append("|------|------|------|")
        for dim in dims:
            score = dim.get("score", 0)
            name = dim.get("name", "")
            evidence = dim.get("evidence", "")
            lines.append(f"| {name} | {score:.2f} | {evidence} |")
        lines.append("")

    lines.append(SYNC_MARKER_END)
    return "\n".join(lines) + "\n"


def _claude_md_has_marker() -> bool:
    """Check if CLAUDE.md already has the evolve sync marker."""
    if not CLAUDE_MD_PATH.exists():
        return False
    text = CLAUDE_MD_PATH.read_text(encoding="utf-8")
    return SYNC_MARKER_START in text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _kill_existing(port):
    """Kill any process already listening on the port."""
    import signal
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f":{port}"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        if out:
            for pid in out.split("\n"):
                pid = pid.strip()
                if pid and pid != str(os.getpid()):
                    os.kill(int(pid), signal.SIGTERM)
            time.sleep(0.3)
            print(f"  Killed old process on port {port}")
    except (subprocess.CalledProcessError, OSError):
        pass



def main():
    print(f"Claude Chat Viewer")
    print(f"Scanning {PROJECTS_DIR} ...")

    _kill_existing(PORT)

    t0 = time.time()
    build_index()
    print(f"Index built in {time.time() - t0:.1f}s")

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", PORT), ChatViewerHandler)
    print(f"\n  → http://localhost:{PORT}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    import sys
    main()
