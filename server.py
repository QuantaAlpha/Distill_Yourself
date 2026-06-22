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
STATIC_DIR = Path(__file__).resolve().parent / "static"
PORT = int(os.environ.get("PORT", 8080))
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
    session_id = None
    first_ts = None
    last_ts = None
    user_texts = []  # (message_index, text, timestamp)
    assistant_snippets = []  # (message_index, first 300 chars of text)
    msg_index = 0

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
                    msg_index += 1

                elif msg_type == "assistant":
                    ts = obj.get("timestamp", "")
                    last_ts = ts or last_ts
                    # Extract first text snippet for correction detection
                    a_content = obj.get("message", {}).get("content", [])
                    a_texts = []
                    if isinstance(a_content, list):
                        for blk in a_content:
                            if isinstance(blk, dict) and blk.get("type") == "text":
                                t = blk.get("text", "").strip()
                                if t:
                                    a_texts.append(t)
                    elif isinstance(a_content, str) and a_content.strip():
                        a_texts.append(a_content.strip())
                    if a_texts:
                        snippet = a_texts[0][:300]
                        assistant_snippets.append({"idx": msg_index, "text": snippet, "ts": ts})
                    msg_index += 1

                elif msg_type == "user" and obj.get("toolUseResult"):
                    msg_index += 1

    except Exception:
        return None

    if not session_id:
        session_id = Path(filepath).stem

    # Fallback title: first user text (76% of sessions lack ai-title)
    if not title and user_texts:
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
                    elif p_type in ("function_call", "custom_tool_call",
                                    "function_call_output", "custom_tool_call_output"):
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
                    if isinstance(output, str) and len(output) > MAX_TOOL_RESULT_LEN:
                        output = output[:MAX_TOOL_RESULT_LEN] + "…[truncated]"
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
# Index Building (with disk cache)
# ---------------------------------------------------------------------------
def build_index(force: bool = False) -> dict:
    """Scan all JSONL files and build/update the metadata index."""
    global _index, _index_gen

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
                        new_sessions[meta["id"]] = meta
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
                        codex_new[meta["id"]] = meta
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
        "projects": projects,
        "sessions": sessions,
        "_file_mtimes": current_files,
    }

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

    print(f"Index ready: {len(sessions)} sessions across {len(projects)} projects")
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

    messages = []
    title = meta.get("title", "Untitled")

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
        "project": meta.get("projectName", ""),
        "date": meta.get("date", ""),
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
            # Truncate large input values
            inp_display = {}
            for k, v in inp.items():
                if isinstance(v, str) and len(v) > 500:
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
            if isinstance(raw, list):
                raw = json.dumps(raw, ensure_ascii=False)
            if isinstance(raw, str) and len(raw) > MAX_TOOL_RESULT_LEN:
                raw = raw[:MAX_TOOL_RESULT_LEN] + "…[truncated]"
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
    tokens = re.split(r'[\s，。、！？；：""''（）【】《》,.!?;:()\[\]<>\-—…·]+', query)
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
    """Search user messages across all sessions with fuzzy matching."""
    if not query or len(query) < 2:
        return []

    query_lower = query.lower()
    tokens = _tokenize_query(query_lower)
    results = []

    with _index_lock:
        sessions = dict(_index.get("sessions", {}))

    for sid, meta in sessions.items():
        title = meta.get("title", "Untitled")
        # Match on title
        matched, score = _fuzzy_match(title.lower(), query_lower, tokens)
        if matched:
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
        # Match on user message content
        for ut in meta.get("userTexts", []):
            matched, score = _fuzzy_match(ut["text"].lower(), query_lower, tokens)
            if matched:
                results.append({
                    "sessionId": sid,
                    "title": title,
                    "project": meta.get("projectName", ""),
                    "date": meta.get("date", ""),
                    "messageIndex": ut["idx"],
                    "snippet": _make_snippet(ut["text"], query_lower, tokens),
                    "timestamp": ut.get("ts", ""),
                    "matchType": "content",
                    "score": score,
                })

    # Sort by score desc, then by date desc for same-score results
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


def _record_error(patterns: dict, raw_msg: str, sid: str, day: str, project: str):
    """Record an error pattern occurrence."""
    key = _normalize_error(raw_msg)
    if len(key) < 10:
        return
    if key not in patterns:
        patterns[key] = {"count": 0, "sessions": set(), "projects": set(), "first": day, "last": day}
    patterns[key]["count"] += 1
    patterns[key]["sessions"].add(sid)
    patterns[key]["projects"].add(project)
    if day and day < patterns[key]["first"]:
        patterns[key]["first"] = day
    if day and day > patterns[key]["last"]:
        patterns[key]["last"] = day


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------
class ChatViewerHandler(SimpleHTTPRequestHandler):
    """Handles API requests and serves static files."""

    def do_GET(self):
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
                self._json_response(self._get_evolve_tab(tab, refresh, source, date, project))
        else:
            # Serve static files (with path traversal protection)
            if path == "/":
                path = "/index.html"
            file_path = (STATIC_DIR / path.lstrip("/")).resolve()
            # SECURITY: Ensure resolved path is under STATIC_DIR
            if not str(file_path).startswith(str(STATIC_DIR.resolve())):
                self._error(403, "Forbidden")
            elif file_path.exists() and file_path.is_file():
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
                "preview": meta.get("preview", ""),
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

    # Tabs that use direct Python analysis (no Codex needed)
    _DIRECT_TABS = {"rules", "signals", "patterns"}
    # Tabs that need AI (Codex) to generate
    _AI_TABS = {"profile", "memory"}

    def _get_evolve_tab(self, tab: str, refresh: bool, source: str, date: str, project: str) -> dict:
        """Get evolve tab data: serve cache or run analyze.py / Codex to generate."""
        cache_path = CACHE_DIR / "evolve" / f"{tab}.json"

        # If not refreshing and cache exists, serve it
        if not refresh and cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        if tab in self._DIRECT_TABS:
            return self._evolve_direct(tab, source, date, project)
        else:
            return self._evolve_via_codex(tab, source, date, project, cache_path)

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

    def _evolve_via_codex(self, tab: str, source: str, date: str, project: str, cache_path: Path) -> dict:
        """Run Codex CLI to analyze conversations and write results via evolve-write."""
        cli_path = str(Path(__file__).resolve().parent / "analyze.py")
        prompt = self._build_evolve_codex_prompt(tab, source, date, project, cli_path)

        try:
            subprocess.run(
                ["codex", "--sandbox", "workspace-write", "--ask-for-approval", "never",
                 "exec", "--skip-git-repo-check", prompt],
                capture_output=True, text=True, timeout=300,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return self._evolve_fallback(tab, "codex CLI not found")
        except subprocess.TimeoutExpired:
            return self._evolve_fallback(tab, "timeout")
        except Exception as e:
            return self._evolve_fallback(tab, str(e))

        # After Codex finishes, read the cache file it wrote via evolve-write
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        return self._evolve_fallback(tab, "Codex did not produce valid output")

    def _evolve_fallback(self, tab: str, reason: str) -> dict:
        """Return empty data with error info."""
        fallbacks = {
            "profile": {"categories": [], "radar": {"dimensions": []}, "_error": reason},
            "memory": {"nodes": [], "links": [], "cards": [], "_error": reason},
        }
        return fallbacks.get(tab, {"_error": reason})

    def _build_evolve_codex_prompt(self, tab: str, source: str, date: str, project: str, cli_path: str) -> str:
        """Build a prompt that instructs Codex to analyze conversations and write results via evolve-write."""
        # Build CLI flags for data querying
        cli_flags = f"--date {date} --source {source}"
        if project:
            cli_flags += f' --project "{project}"'

        # Get filtered session summary for context
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

        write_cmd = f"python3 {cli_path} evolve-write --tab {tab}"

        parts = [
            f"You have a CLI tool for analyzing conversation history: python3 {cli_path} <command> [options]",
            f"Commands: sessions, read <id> [-s summary], search <query>, queries [--session <id>] [-k keyword], corrections, decisions, errors, stats, files, highlights",
            f"Each command supports: --date --source --project --limit --json",
            "",
            f"Current scope: {cli_flags} ({session_count} sessions)",
            "",
            f"STEP 1: Use the CLI to gather data. Example:",
            f"  python3 {cli_path} queries {cli_flags} --limit 80",
            f"  python3 {cli_path} highlights {cli_flags}",
            f"  python3 {cli_path} stats {cli_flags}",
            "",
            f"STEP 2: Write your analysis result using the evolve-write command.",
            f"  The command reads JSON from stdin and validates the schema.",
            f"  If validation fails, you will see specific error messages — fix the JSON and retry.",
            "",
        ]

        if tab == "profile":
            parts.extend([
                f"TASK: Analyze conversation history and extract a user profile.",
                "",
                f"Write command (pipe JSON via heredoc):",
                f'  {write_cmd} --mode replace <<\'EVOLVE_EOF\'',
                f'  {{your JSON here}}',
                f'  EVOLVE_EOF',
                "",
                "Required JSON schema:",
                '{',
                '  "categories": [',
                '    {"name": "分类名", "icon": "emoji",',
                '     "tags": ["标签1", "标签2"],',
                '     "items": [{"text": "具体描述", "confidence": "high|medium|low"}]',
                '    }',
                '  ],',
                '  "radar": {',
                '    "dimensions": [',
                '      {"name": "领域名称", "score": 0.0-1.0, "evidence": "判断依据简述"}',
                '    ]',
                '  }',
                '}',
                "",
                "分类规则：",
                "- 根据对话实际内容自行归类（基本信息、技术栈、沟通风格、工作习惯、当前关注等）",
                "- tags: 短标签（技术名词等），items: 具体描述句",
                "- radar: 基于用户涉及的具体能力领域，5-8 个维度，score 基于深度和频率",
                "- 所有内容用中文",
            ])
        elif tab == "memory":
            parts.extend([
                f"TASK: Analyze conversation history and extract user preferences/habits as a memory network.",
                "",
                f"Write command (pipe JSON via heredoc):",
                f'  {write_cmd} --mode replace <<\'EVOLVE_EOF\'',
                f'  {{your JSON here}}',
                f'  EVOLVE_EOF',
                "",
                "Required JSON schema:",
                '{',
                '  "nodes": [{"id": "m1", "label": "偏好简述", "type": "偏好|工作流|工具|设计|沟通", "frequency": N, "confidence": "high|medium|low"}],',
                '  "links": [{"source": "m1", "target": "m2", "strength": 0.0-1.0}],',
                '  "cards": [{"id": "m1", "content": "完整描述", "firstSeen": "YYYY-MM-DD", "lastSeen": "YYYY-MM-DD", "evidence": "用户原话引用"}]',
                '}',
                "",
                "提取信号：明确偏好、反复选择模式、工具偏好、风格选择、工作流习惯。",
                "每条记忆要具体可操作，不要泛泛而谈。所有内容用中文。",
                "nodes 和 cards 的 id 必须一一对应。",
            ])

        parts.extend([
            "",
            "IMPORTANT:",
            "- The evolve-write command validates the JSON schema. If it fails, read the error message and fix.",
            "- Do NOT output the JSON to stdout. Use the evolve-write command to write it.",
            "- Analyze sufficient conversations before generating — use queries/highlights/stats first.",
        ])

        return "\n".join(parts)

    def _get_analytics(self) -> dict:
        """Compute analytics: file hotspots, tool usage heatmap, error patterns."""
        with _index_lock:
            sessions = dict(_index.get("sessions", {}))

        file_freq = {}      # file_path -> {count, sessions, projects}
        tool_daily = {}     # "YYYY-MM-DD" -> {tool_name -> count}
        error_patterns = {} # normalized_error -> {count, sessions, first, last, sample}

        # Regex for common errors
        err_re = re.compile(
            r'((?:Traceback.*?:\s*)?'
            r'(?:(?:Error|Exception|TypeError|ValueError|KeyError|AttributeError|'
            r'ImportError|ModuleNotFoundError|NameError|IndexError|RuntimeError|'
            r'SyntaxError|FileNotFoundError|PermissionError|OSError|IOError|'
            r'ConnectionError|TimeoutError)'
            r'[:\s].{0,120}))',
            re.IGNORECASE
        )

        for sid, meta in sessions.items():
            filepath = meta.get("filePath", "")
            if not filepath or not os.path.exists(filepath):
                continue

            date_str = meta.get("date", "")
            day = date_str[:10] if date_str else ""
            source = meta.get("source", "claude")
            project = meta.get("projectName", "")

            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        msg_type = obj.get("type")

                        # -- Claude Code tool usage --
                        if source == "claude" and msg_type == "assistant":
                            content = obj.get("message", {}).get("content", [])
                            if not isinstance(content, list):
                                continue
                            for block in content:
                                if not isinstance(block, dict):
                                    continue
                                if block.get("type") == "tool_use":
                                    tool_name = block.get("name", "unknown")
                                    inp = block.get("input", {})
                                    # Tool daily count
                                    if day:
                                        tool_daily.setdefault(day, {})
                                        tool_daily[day][tool_name] = tool_daily[day].get(tool_name, 0) + 1
                                    # File hotspot
                                    fp = inp.get("file_path") or inp.get("path") or ""
                                    if fp and not fp.startswith("/tmp"):
                                        file_freq.setdefault(fp, {"count": 0, "sessions": set(), "projects": set()})
                                        file_freq[fp]["count"] += 1
                                        file_freq[fp]["sessions"].add(sid)
                                        file_freq[fp]["projects"].add(project)
                                elif block.get("type") == "tool_result":
                                    pass  # handled below

                        # -- Claude Code tool results (errors) --
                        if source == "claude" and msg_type == "user" and obj.get("toolUseResult"):
                            content = obj.get("message", {}).get("content", [])
                            if isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "tool_result":
                                        result_text = block.get("content", "")
                                        if isinstance(result_text, list):
                                            result_text = json.dumps(result_text)
                                        if isinstance(result_text, str):
                                            for m in err_re.finditer(result_text[:5000]):
                                                _record_error(error_patterns, m.group(1), sid, day, project)

                        # -- Codex tool usage --
                        if source == "codex":
                            rec_type = obj.get("type")
                            payload = obj.get("payload", {})
                            if rec_type == "response_item":
                                p_type = payload.get("type", "")
                                if p_type in ("function_call", "custom_tool_call"):
                                    raw_name = payload.get("name", "unknown")
                                    tool_name = _CODEX_TOOL_NAMES.get(raw_name, raw_name)
                                    if day:
                                        tool_daily.setdefault(day, {})
                                        tool_daily[day][tool_name] = tool_daily[day].get(tool_name, 0) + 1
                                    # File from codex args
                                    args_str = payload.get("arguments", "{}")
                                    try:
                                        args = json.loads(args_str) if isinstance(args_str, str) else {}
                                    except json.JSONDecodeError:
                                        args = {}
                                    fp = args.get("file_path") or args.get("path") or ""
                                    if fp and not fp.startswith("/tmp"):
                                        file_freq.setdefault(fp, {"count": 0, "sessions": set(), "projects": set()})
                                        file_freq[fp]["count"] += 1
                                        file_freq[fp]["sessions"].add(sid)
                                        file_freq[fp]["projects"].add(project)
                                elif p_type in ("function_call_output", "custom_tool_call_output"):
                                    output = payload.get("output", "")
                                    if isinstance(output, str):
                                        for m in err_re.finditer(output[:5000]):
                                            _record_error(error_patterns, m.group(1), sid, day, project)

            except Exception:
                continue

        # Serialize file hotspots (top 50)
        hotspots = []
        for fp, data in sorted(file_freq.items(), key=lambda x: -x[1]["count"])[:50]:
            # Shorten path
            home = str(Path.home())
            short = fp.replace(home, "~") if fp.startswith(home) else fp
            hotspots.append({
                "path": short,
                "fullPath": fp,
                "count": data["count"],
                "sessionCount": len(data["sessions"]),
                "projects": sorted(data["projects"]),
            })

        # Serialize tool heatmap (last 30 days)
        sorted_days = sorted(tool_daily.keys(), reverse=True)[:30]
        all_tools = set()
        for day_tools in tool_daily.values():
            all_tools.update(day_tools.keys())
        # Sort tools by total frequency
        tool_totals = {}
        for day_tools in tool_daily.values():
            for t, c in day_tools.items():
                tool_totals[t] = tool_totals.get(t, 0) + c
        sorted_tools = sorted(all_tools, key=lambda t: -tool_totals.get(t, 0))[:15]

        heatmap = {
            "days": sorted_days,
            "tools": sorted_tools,
            "data": {day: {t: tool_daily.get(day, {}).get(t, 0) for t in sorted_tools} for day in sorted_days},
            "totals": {t: tool_totals.get(t, 0) for t in sorted_tools},
        }

        # Serialize errors (top 30)
        errors = []
        for key, data in sorted(error_patterns.items(), key=lambda x: -x[1]["count"])[:30]:
            errors.append({
                "pattern": key[:200],
                "count": data["count"],
                "sessionCount": len(data["sessions"]),
                "projects": sorted(data["projects"]),
                "firstSeen": data["first"],
                "lastSeen": data["last"],
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
        """F12: Solution Snippet Library — extract code blocks with Applied detection."""
        with _index_lock:
            sessions = dict(_index.get("sessions", {}))

        snippets = []
        code_re = re.compile(r'```(\w*)\n([\s\S]*?)```')

        for sid, meta in sessions.items():
            filepath = meta.get("filePath", "")
            source = meta.get("source", "claude")
            if source != "claude" or not filepath or not os.path.exists(filepath):
                continue

            project = meta.get("projectName", "")
            title = meta.get("title", "Untitled")
            prev_user_msg = ""

            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        msg_type = obj.get("type")
                        if msg_type == "user" and not obj.get("toolUseResult"):
                            content = obj.get("message", {}).get("content", [])
                            prev_user_msg = _extract_user_text(content)[:200]
                        elif msg_type == "assistant":
                            content = obj.get("message", {}).get("content", [])
                            if not isinstance(content, list):
                                continue
                            # Collect code blocks and tool_use in this turn
                            code_blocks = []
                            tool_writes = []  # content from Edit/Write tool_use
                            for block in content:
                                if not isinstance(block, dict):
                                    continue
                                if block.get("type") == "text":
                                    text = block.get("text", "")
                                    for m in code_re.finditer(text):
                                        lang = m.group(1) or ""
                                        code = m.group(2).strip()
                                        if 3 < len(code.split("\n")) <= 50 and len(code) > 30:
                                            code_blocks.append({"lang": lang, "code": code[:1000]})
                                elif block.get("type") == "tool_use":
                                    name = block.get("name", "")
                                    if name in ("Edit", "Write"):
                                        inp = block.get("input", {})
                                        # Collect written content for matching
                                        w = inp.get("new_string", "") or inp.get("content", "")
                                        if w:
                                            tool_writes.append(w[:2000])

                            # Determine applied status for each code block
                            for cb in code_blocks:
                                applied = False
                                if tool_writes:
                                    # Check if any tool write overlaps with this code
                                    code_lines = set(cb["code"].strip().split("\n")[:10])
                                    for tw in tool_writes:
                                        tw_lines = set(tw.strip().split("\n")[:20])
                                        overlap = code_lines & tw_lines
                                        if len(overlap) >= min(2, len(code_lines)):
                                            applied = True
                                            break
                                snippets.append({
                                    "sessionId": sid,
                                    "sessionTitle": title,
                                    "project": project,
                                    "language": cb["lang"],
                                    "code": cb["code"],
                                    "context": prev_user_msg,
                                    "date": meta.get("date", ""),
                                    "applied": applied,
                                })
            except Exception:
                continue

            if len(snippets) >= 300:
                break

        # Sort: applied first, then by date
        snippets.sort(key=lambda s: (not s.get("applied", False), s.get("date", "")), reverse=False)
        snippets.sort(key=lambda s: (-int(s.get("applied", False)), s.get("date", "")), reverse=False)
        # Re-sort properly
        snippets.sort(key=lambda s: (-int(s.get("applied", False)), s.get("date", "")))
        snippets.reverse()
        # Actually: applied first (desc), then date desc
        snippets.sort(key=lambda s: (not s.get("applied", False), ""), reverse=False)
        snippets.sort(key=lambda s: s.get("date", ""), reverse=True)
        snippets.sort(key=lambda s: -int(s.get("applied", False)))
        return {"snippets": snippets[:150]}

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

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/chat":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._error(400, "Invalid JSON")
                return

            prompt = data.get("prompt", "")
            context_type = data.get("contextType", "")  # "session" or "global"
            session_id = data.get("sessionId", "")
            scope = data.get("scope", {})  # {project, date, source} for global

            if not prompt:
                self._error(400, "No prompt")
                return

            # Build context-aware prompt
            full_prompt = self._build_chat_prompt(prompt, context_type, session_id, scope)

            # Execute Codex CLI
            try:
                result = subprocess.run(
                    ["codex", "--sandbox", "read-only", "--ask-for-approval", "never",
                     "exec", "--skip-git-repo-check", full_prompt],
                    capture_output=True, text=True, timeout=300,
                    stdin=subprocess.DEVNULL,
                )
                output = result.stdout.strip()
                if not output and result.stderr:
                    # Filter out noise from stderr
                    stderr = result.stderr.strip()
                    noise = ["plugin manifest", "MCP", "Warning", "shutdown"]
                    lines = [l for l in stderr.split("\n") if not any(n in l for n in noise)]
                    if lines:
                        output = "Error: " + "\n".join(lines[:5])
                    else:
                        output = "(No output)"
                if not output:
                    output = "(No output)"
            except FileNotFoundError:
                output = "Error: `codex` CLI not found. Install it with `npm install -g @openai/codex`"
            except subprocess.TimeoutExpired:
                output = "Error: Request timed out (5 min limit)"
            except Exception as e:
                output = f"Error: {str(e)}"

            self._json_response({"response": output})
        else:
            self._error(404, "Not found")

    def _build_chat_prompt(self, prompt: str, context_type: str, session_id: str, scope: dict = None) -> str:
        """Build a context-enriched prompt for Codex with rich metadata and CLI tools."""
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

                context_parts.append(f"You are analyzing a {source} session: '{title}' from project '{project}'.")
                context_parts.append(f"Quick read: python3 {cli_path} read {session_id}")
                context_parts.append(f"Session file (JSONL): {fp}")
                context_parts.append(f"User messages: {msg_count}")

                # Include user message previews for quick context
                user_texts = meta.get("userTexts", [])
                if user_texts:
                    context_parts.append("\nConversation outline (user messages preview):")
                    for i, ut in enumerate(user_texts[:12]):
                        text = ut.get("text", "")[:200].replace("\n", " ")
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
            context_parts.append(f"Current scope filters: {flags_str or '(none)'}")
            context_parts.append(f"IMPORTANT: Always pass these flags to the CLI tool. Example: python3 {cli_path} stats {flags_str}")
            context_parts.append(f"Start with: python3 {cli_path} stats {flags_str}")
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

        if context_parts:
            return "\n".join(context_parts) + "\n\n--- User Request ---\n" + prompt
        return prompt

    def log_message(self, format, *args):
        """Suppress default request logging for cleaner output."""
        pass


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


def _watch_and_reload(server):
    """Watch source files for changes and auto-restart."""
    watch_files = [
        Path(__file__).resolve(),
        STATIC_DIR / "app.js",
        STATIC_DIR / "evolve.js",
        STATIC_DIR / "style.css",
        STATIC_DIR / "index.html",
    ]
    mtimes = {str(f): f.stat().st_mtime for f in watch_files if f.exists()}

    while True:
        time.sleep(1.5)
        for f in watch_files:
            if not f.exists():
                continue
            cur = f.stat().st_mtime
            key = str(f)
            if key in mtimes and cur != mtimes[key]:
                print(f"\n  ⟳ {f.name} changed — restarting...")
                server.shutdown()
                os.execv(sys.argv[0] if sys.argv[0].endswith('.py') else sys.executable,
                         [sys.executable, str(Path(__file__).resolve())] + sys.argv[1:])
            mtimes[key] = cur


def main():
    print(f"Claude Chat Viewer")
    print(f"Scanning {PROJECTS_DIR} ...")

    _kill_existing(PORT)

    t0 = time.time()
    build_index()
    print(f"Index built in {time.time() - t0:.1f}s")

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", PORT), ChatViewerHandler)
    print(f"\n  → http://localhost:{PORT}")
    print(f"  Auto-reload: watching source files for changes\n")

    # Start file watcher in background
    watcher = threading.Thread(target=_watch_and_reload, args=(server,), daemon=True)
    watcher.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    import sys
    main()
