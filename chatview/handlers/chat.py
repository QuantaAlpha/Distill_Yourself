"""Chat endpoint handlers — extracted from ChatViewerHandler."""

import json
import subprocess
from datetime import datetime
from pathlib import Path

from chatview.ai_engine import _run_ai_engine, _run_ai_engine_stream
from chatview.handlers.base import _json_response, _error, _sse_event, _start_sse, _read_post_body
from chatview.handlers.evolve import _collect_aggregates, _collect_profile_digest, _collect_stats
from chatview import index as _idx
from chatview.index import (
    CODEX_ARCHIVED_DIR,
    CODEX_SESSIONS_DIR,
    PROJECTS_DIR,
)


def _handle_chat_stream(handler):
    """SSE streaming chat endpoint."""
    raw = _read_post_body(handler)
    if raw is None:
        return  # error already sent
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _error(handler,400, "Invalid JSON")
        return

    prompt = data.get("prompt", "")
    context_type = data.get("contextType", "")
    session_id = data.get("sessionId", "")
    scope = data.get("scope", {})
    messages = data.get("messages", [])

    if not prompt:
        _error(handler,400, "No prompt")
        return

    full_prompt = _build_chat_prompt(handler, prompt, context_type, session_id, scope, messages)
    _start_sse(handler)

    # Global analysis needs more time (sub-agents, CLI exploration)
    chat_timeout = int(data.get("timeout", 900))
    chat_timeout = max(60, min(chat_timeout, 1800))  # clamp 1min-30min
    stream = _run_ai_engine_stream(full_prompt, allow_write=False, timeout=chat_timeout)
    try:
        for evt in stream:
            _sse_event(handler,evt)
    except BrokenPipeError:
        return
    except Exception as e:
        try:
            _sse_event(handler,{"type": "error", "message": str(e)})
        except BrokenPipeError:
            pass
    finally:
        stream.close()


def _handle_chat_legacy(handler):
    """Original blocking chat endpoint (kept for compatibility)."""
    raw = _read_post_body(handler)
    if raw is None:
        return
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _error(handler,400, "Invalid JSON")
        return

    prompt = data.get("prompt", "")
    context_type = data.get("contextType", "")
    session_id = data.get("sessionId", "")
    scope = data.get("scope", {})
    messages = data.get("messages", [])

    if not prompt:
        _error(handler,400, "No prompt")
        return

    full_prompt = _build_chat_prompt(handler, prompt, context_type, session_id, scope, messages)

    try:
        legacy_timeout = int(data.get("timeout", 900))
        legacy_timeout = max(60, min(legacy_timeout, 1800))
        stdout, stderr, _ = _run_ai_engine(full_prompt, allow_write=False, timeout=legacy_timeout)
        output = stdout.strip()
        if not output and stderr:
            stderr = stderr.strip()
            noise = ["plugin manifest", "MCP", "Warning", "shutdown"]
            lines = [line for line in stderr.split("\n") if not any(n in line for n in noise)]
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

    _json_response(handler,{"response": output})


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
        if content.startswith("**Error:**") or content.endswith("*(已停止)*") or content.endswith("*(stopped)*"):
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


def _build_chat_prompt(handler, prompt: str, context_type: str, session_id: str, scope: dict = None, messages: list = None) -> str:
    """Build a context-enriched prompt for the AI engine with rich metadata and CLI tools."""
    cli_path = str(Path(__file__).parents[1].parent / "analyze.py")
    lang = (scope or {}).get("lang", "zh")
    if lang == "en":
        prompt = prompt + "\n\nIMPORTANT: All your output text must be in English. Keep JSON keys unchanged. Translate all labels, descriptions, summaries into English unless they are direct quotes from the user's conversation history."
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
        with _idx._index_lock:
            meta = _idx._index.get("sessions", {}).get(session_id)
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
            from chatview import db as _db
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

        with _idx._index_lock:
            sessions = dict(_idx._index.get("sessions", {}))

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

        digest = _collect_profile_digest(handler, source, date, project, cli_path)
        if digest:
            context_parts.append("# Pre-computed Profile Digest (data overview — do NOT re-run profile-digest)")
            context_parts.append(digest)
            context_parts.append("")

        stats = _collect_stats(handler, source, date, project, cli_path)
        if stats:
            context_parts.append("# Pre-collected Stats (do NOT re-run stats)")
            context_parts.append(stats)
            context_parts.append("")

        aggregates = _collect_aggregates(handler)
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
    chat_history = _compress_chat_history(messages) if messages else ""
    if chat_history:
        context_parts.append("")
        context_parts.append("--- Chat History ---")
        context_parts.append("")
        context_parts.append(chat_history)

    if context_parts:
        return "\n".join(context_parts) + "\n\n--- User Request ---\n" + prompt
    return prompt
