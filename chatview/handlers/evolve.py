"""Evolve tab handlers — extracted from ChatViewerHandler."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from chatview.ai_engine import (
    _detect_ai_engine,
    _normalize_ai_engine,
    _run_ai_engine,
    _run_ai_engine_stream,
)
from chatview.handlers.base import _sse_event, _start_sse
from chatview import index as _idx

# Tab classification (moved from class attrs)
_DIRECT_TABS = set()
_EVOLVE_TABS = ("profile", "memory", "rules", "signals", "patterns")
_AI_TABS = set(_EVOLVE_TABS)


# ---------------------------------------------------------------------------
# Active evolve analysis state (for /api/evolve/cancel + /api/evolve/progress)
# ---------------------------------------------------------------------------
_active_evolve_runs = {}  # {run_id: {"tab", "source", "date", "project", "engine", "proc", "starting", "finalizing", "phase_started_at"}}
_cancelled_evolve_run_ids = set()
_evolve_lock = threading.Lock()
_EVOLVE_STARTING_GRACE_SECONDS = 45
_EVOLVE_FINALIZING_GRACE_SECONDS = 15


def _persist_evolve_event(run_id: str, event: dict):
    """Best-effort append of one replayable run event."""
    if not run_id or not isinstance(event, dict):
        return
    try:
        from chatview import db as _db

        _db.evolve_run_event_append(run_id, event)
    except Exception:
        pass


def _get_evolve_tab(
    handler,
    tab: str,
    refresh: bool,
    source: str,
    date: str,
    project: str,
    engine: str = "auto",
    lang: str = "zh",
    timeout: int = 900,
) -> dict:
    """Get evolve tab data: serve DB cache or run AI engine to generate."""
    from chatview import db as _db

    try:
        engine = _normalize_ai_engine(engine)
    except ValueError as e:
        return _evolve_fallback(handler, tab, str(e))

    # If not refreshing, serve only the exact engine scope requested by the UI.
    # Execution engine still comes from the UI, but existing tab results should
    # remain visible across engine switches. Prefer an exact engine match when
    # present; otherwise fall back to the latest cache for the same scope.
    if not refresh:
        row = _db.evolve_get_shared(tab, source, date, project, engine)
        if row:
            return row["data"]
        return _evolve_fallback(handler, tab, "no_cache")

    if tab in _DIRECT_TABS:
        return _evolve_direct(handler, tab, source, date, project)
    else:
        return _evolve_via_ai(
            handler, tab, source, date, project, engine, lang, timeout
        )


def _evolve_direct(handler, tab: str, source: str, date: str, project: str) -> dict:
    """Run analyze.py directly for rules/signals/patterns."""
    cmd = [
        sys.executable,
        str(Path(__file__).parents[1].parent / "analyze.py"),
        f"evolve-{tab}",
        "--json",
        "--source",
        source,
        "--date",
        date,
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


def _evolve_via_ai(
    handler,
    tab: str,
    source: str,
    date: str,
    project: str,
    engine: str = "auto",
    lang: str = "zh",
    timeout: int = 900,
) -> dict:
    """Run AI engine to analyze conversations; AI writes result to SQLite via evolve-write CLI."""
    from chatview import db as _db

    cli_path = str(Path(__file__).parents[1].parent / "analyze.py")
    prompt = _build_evolve_prompt(
        handler, tab, source, date, project, cli_path, engine, lang
    )

    try:
        _run_ai_engine(
            prompt, allow_write=True, timeout=timeout, engine_override=engine
        )
    except FileNotFoundError as e:
        return _evolve_fallback(handler, tab, str(e))
    except subprocess.TimeoutExpired:
        return _evolve_fallback(handler, tab, "timeout")
    except Exception as e:
        return _evolve_fallback(handler, tab, str(e))

    # AI wrote to SQLite via evolve-write CLI — read it back
    row = _db.evolve_get(tab, source, date, project, engine)
    if row:
        return row["data"]

    engine_name = _detect_ai_engine() or "AI"
    return _evolve_fallback(
        handler,
        tab,
        f"{engine_name} 已运行但未写入有效结果（可能是分析中断或输出不符合 schema）",
    )


def _handle_evolve_stream(
    handler,
    tab: str,
    source: str,
    date: str,
    project: str,
    engine: str = "auto",
    lang: str = "zh",
    timeout: int = 900,
):
    """SSE streaming for AI evolve tabs (profile/memory).

    When the client disconnects (BrokenPipeError), the stream is drained
    silently so the AI process can complete and persist results to SQLite.
    """
    from chatview import db as _db

    try:
        engine = _normalize_ai_engine(engine)
    except ValueError as e:
        _start_sse(handler)
        _sse_event(handler, {"type": "error", "message": str(e)})
        return
    cli_path = str(Path(__file__).parents[1].parent / "analyze.py")
    prompt = _build_evolve_prompt(
        handler, tab, source, date, project, cli_path, engine, lang
    )
    run_id = _db.evolve_run_start(
        tab,
        source,
        date,
        project,
        engine,
        lang=lang,
        snapshot={
            "tab": tab,
            "scope": {
                "source": source or "all",
                "date": date or "7d",
                "project": project or "",
                "engine": engine,
                "lang": lang or "zh",
            },
            "events": [],
            "text": "",
            "step_count": 0,
            "usage": {"input": 0, "output": 0},
        },
    )
    with _evolve_lock:
        _cancelled_evolve_run_ids.discard(run_id)
        _active_evolve_runs[run_id] = {
            "tab": tab,
            "source": source or "all",
            "date": date or "7d",
            "project": project or "",
            "engine": engine,
            "proc": None,
            "starting": True,
            "finalizing": False,
            "phase_started_at": time.time(),
        }

    _start_sse(handler)
    run_evt = {"type": "run", "run_id": run_id}
    _persist_evolve_event(run_id, run_evt)
    _sse_event(handler, run_evt)
    proc_ref = [None]

    def _on_proc_start(proc):
        should_kill = False
        with _evolve_lock:
            should_kill = run_id in _cancelled_evolve_run_ids
            active = _active_evolve_runs.get(run_id)
            if active is not None:
                active["proc"] = proc
                active["starting"] = False
                active["finalizing"] = False
                active["phase_started_at"] = time.time()
        if should_kill:
            _kill_evolve_process(proc)

    stream = _run_ai_engine_stream(
        prompt,
        allow_write=True,
        timeout=timeout,
        engine_override=engine,
        proc_ref=proc_ref,
        on_proc_start=_on_proc_start,
    )
    disconnected = False
    last_error = None  # track last error/timeout reason for DB-empty fallback
    event_tail = []
    step_count = 0
    text_chunks = []
    usage_input = 0
    usage_output = 0
    stream_finished = False
    try:
        for evt in stream:
            with _evolve_lock:
                cancelled = run_id in _cancelled_evolve_run_ids
            if cancelled:
                _persist_evolve_event(
                    run_id, {"type": "error", "message": "Cancelled by user"}
                )
                _db.evolve_run_update(
                    run_id,
                    status="cancelled",
                    snapshot={
                        "events": event_tail,
                        "text": "".join(text_chunks)[-12000:],
                        "step_count": step_count,
                        "usage": {"input": usage_input, "output": usage_output},
                        "cancelled": True,
                    },
                    error_message="Cancelled by user",
                )
                return
            etype = evt.get("type") if isinstance(evt, dict) else None
            if etype == "tool" and evt.get("status") == "running":
                step_count += 1
            if etype == "text":
                text_chunks.append(evt.get("content") or "")
            if etype == "usage":
                usage_input += int(evt.get("input_tokens") or 0)
                usage_output += int(evt.get("output_tokens") or 0)
            if etype in ("error", "timeout"):
                last_error = evt.get("message") or etype
            _persist_evolve_event(run_id, evt)
            if etype in ("tool", "error", "timeout", "result", "done"):
                event_tail.append(evt)
                event_tail = event_tail[-12:]
            snapshot = {
                "tab": tab,
                "scope": {
                    "source": source or "all",
                    "date": date or "7d",
                    "project": project or "",
                    "engine": engine,
                    "lang": lang or "zh",
                },
                "events": event_tail,
                "text": "".join(text_chunks)[-12000:],
                "step_count": step_count,
                "usage": {"input": usage_input, "output": usage_output},
            }
            _db.evolve_run_update(run_id, status="running", snapshot=snapshot)
            if disconnected:
                continue  # drain silently — AI process still writes to DB
            try:
                _sse_event(handler, evt)
            except BrokenPipeError:
                disconnected = True
        stream_finished = True
    except Exception as e:
        last_error = str(e)
        _persist_evolve_event(run_id, {"type": "error", "message": last_error})
        _db.evolve_run_update(
            run_id,
            status="failed",
            snapshot={
                "events": event_tail,
                "text": "".join(text_chunks)[-12000:],
                "step_count": step_count,
                "usage": {"input": usage_input, "output": usage_output},
            },
            error_message=last_error,
        )
        if not disconnected:
            try:
                _sse_event(handler, {"type": "error", "message": str(e)})
            except BrokenPipeError:
                return
        return
    finally:
        stream.close()
        with _evolve_lock:
            if run_id in _cancelled_evolve_run_ids:
                _active_evolve_runs.pop(run_id, None)
                _cancelled_evolve_run_ids.discard(run_id)
            elif stream_finished and run_id in _active_evolve_runs:
                _active_evolve_runs[run_id]["proc"] = None
                _active_evolve_runs[run_id]["starting"] = False
                _active_evolve_runs[run_id]["finalizing"] = True
                _active_evolve_runs[run_id]["phase_started_at"] = time.time()
            else:
                _active_evolve_runs.pop(run_id, None)

    # AI wrote to SQLite via evolve-write CLI — read it back
    with _evolve_lock:
        cancelled = run_id in _cancelled_evolve_run_ids
    if cancelled:
        _db.evolve_run_update(
            run_id,
            status="cancelled",
            snapshot={
                "events": event_tail,
                "text": "".join(text_chunks)[-12000:],
                "step_count": step_count,
                "usage": {"input": usage_input, "output": usage_output},
                "cancelled": True,
            },
            error_message="Cancelled by user",
        )
        with _evolve_lock:
            _active_evolve_runs.pop(run_id, None)
        return
    try:
        row = _db.evolve_get(tab, source, date, project, engine)
        if row:
            result_evt = {"type": "evolve_result", "data": row["data"]}
            _persist_evolve_event(run_id, result_evt)
            _db.evolve_run_update(
                run_id,
                status="completed",
                snapshot={
                    "events": event_tail,
                    "text": "".join(text_chunks)[-12000:],
                    "step_count": step_count,
                    "usage": {"input": usage_input, "output": usage_output},
                    "result": row["data"],
                },
                error_message="",
            )
            if not disconnected:
                _sse_event(handler, result_evt)
        elif last_error:
            error_evt = {"type": "error", "message": last_error}
            _persist_evolve_event(run_id, error_evt)
            _db.evolve_run_update(
                run_id,
                status="failed",
                snapshot={
                    "events": event_tail,
                    "text": "".join(text_chunks)[-12000:],
                    "step_count": step_count,
                    "usage": {"input": usage_input, "output": usage_output},
                },
                error_message=last_error,
            )
            if not disconnected:
                try:
                    _sse_event(handler, error_evt)
                except BrokenPipeError:
                    pass
            return
        else:
            msg = "AI 已运行但未写入有效结果（可能是分析中断或输出不符合 schema）"
            error_evt = {"type": "error", "message": msg}
            _persist_evolve_event(run_id, error_evt)
            _db.evolve_run_update(
                run_id,
                status="failed",
                snapshot={
                    "events": event_tail,
                    "text": "".join(text_chunks)[-12000:],
                    "step_count": step_count,
                    "usage": {"input": usage_input, "output": usage_output},
                },
                error_message=msg,
            )
            if not disconnected:
                _sse_event(
                    handler,
                    error_evt,
                )
    except BrokenPipeError:
        return
    finally:
        with _evolve_lock:
            _active_evolve_runs.pop(run_id, None)
            _cancelled_evolve_run_ids.discard(run_id)


def _latest_evolve_run_info(
    tab: str = "",
    source: str = "all",
    date: str = "7d",
    project: str = "",
    engine: str = "auto",
):
    """Return the latest persisted evolve run for a tab/scope, or per-tab map."""
    from chatview import db as _db

    _db.init_db()
    if tab:
        return _db.evolve_run_latest_shared(tab, source, date, project, engine)
    return _db.evolve_runs_latest_for_scope_shared(source, date, project, engine)


def _is_evolve_run_active(run: dict) -> bool:
    """Return whether a persisted run still has a live backend request/process."""
    if not run or run.get("status") != "running":
        return False
    with _evolve_lock:
        active = _active_evolve_runs.get(run["run_id"])
    if not active:
        return False
    proc = active.get("proc")
    if proc is None:
        phase_started_at = active.get("phase_started_at") or 0
        elapsed = time.time() - float(phase_started_at or 0)
        if active.get("starting"):
            return elapsed < _EVOLVE_STARTING_GRACE_SECONDS
        if active.get("finalizing"):
            return elapsed < _EVOLVE_FINALIZING_GRACE_SECONDS
        return False
    try:
        return proc.poll() is None
    except Exception:
        return False


def _evolve_progress_entry(
    tab: str,
    source: str,
    date: str,
    project: str,
    engine: str,
    run: Optional[dict] = None,
) -> dict:
    """Build a progress payload entry for one tab, including saved cache."""
    from chatview import db as _db

    if run is None:
        run = _latest_evolve_run_info(tab, source, date, project, engine)
    running = _is_evolve_run_active(run) if run else False
    stale = bool(run and run.get("status") == "running" and not running)
    cache = _db.evolve_get_shared(tab, source, date, project, engine)
    event_count = _db.evolve_run_event_count(run["run_id"]) if run else 0
    return {
        "running": running,
        "stale": stale,
        "run": run,
        "cache": cache,
        "event_count": event_count,
    }


def _handle_evolve_progress(handler, params):
    """GET /api/evolve/progress — recover latest persisted evolve run(s)."""

    tab = params.get("tab", [""])[0]
    source = params.get("source", ["all"])[0]
    date = params.get("date", ["7d"])[0]
    project = params.get("project", [""])[0]
    engine = params.get("engine", ["auto"])[0]
    try:
        engine = _normalize_ai_engine(engine)
    except ValueError:
        engine = "auto"

    if tab:
        entry = _evolve_progress_entry(tab, source, date, project, engine)
        _json_payload = {"ok": True, **entry}
        from chatview.handlers.base import _json_response

        _json_response(handler, _json_payload)
        return

    tabs = _latest_evolve_run_info("", source, date, project, engine)
    payload_tabs = {}
    any_running = False
    for name in _EVOLVE_TABS:
        entry = _evolve_progress_entry(
            name, source, date, project, engine, run=tabs.get(name)
        )
        any_running = any_running or entry["running"]
        if entry["run"] or entry["cache"]:
            payload_tabs[name] = entry
    from chatview.handlers.base import _json_response

    _json_response(handler, {"ok": True, "running": any_running, "tabs": payload_tabs})


def _handle_evolve_run_events(handler, params):
    """GET /api/evolve/run-events — replay persisted stream events for a run."""
    from chatview import db as _db
    from chatview.handlers.base import _json_response

    run_id = params.get("run_id", [""])[0]
    try:
        since = int(params.get("since", ["0"])[0] or 0)
    except (TypeError, ValueError):
        since = 0
    try:
        limit = int(params.get("limit", ["500"])[0] or 500)
    except (TypeError, ValueError):
        limit = 500

    run = _db.evolve_run_get(run_id) if run_id else None
    events = _db.evolve_run_events(run_id, since=since, limit=limit) if run else []
    next_index = events[-1]["event_index"] if events else max(0, since)
    _json_response(
        handler,
        {
            "ok": True,
            "run_id": run_id,
            "run": run,
            "events": events,
            "next_index": next_index,
            "event_count": _db.evolve_run_event_count(run_id) if run else 0,
        },
    )


def _kill_evolve_process(proc):
    """Best-effort terminate an active evolve subprocess."""
    if not proc:
        return
    try:
        if proc.poll() is not None:
            return
    except Exception:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            pass


def _handle_evolve_cancel(handler, raw_body):
    """POST /api/evolve/cancel — cancel a running evolve analysis."""
    from chatview import db as _db
    from chatview.handlers.base import _json_response

    try:
        data = json.loads(raw_body or "{}")
    except (json.JSONDecodeError, ValueError, TypeError):
        _json_response(handler, {"ok": False, "error": "Invalid JSON"})
        return

    tab = data.get("tab", "")
    scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
    source = scope.get("source", "all")
    date = scope.get("date", "7d")
    project = scope.get("project", "")
    engine = scope.get("engine", "auto")
    run = (
        _db.evolve_run_latest_shared(tab, source, date, project, engine)
        if tab
        else None
    )
    if not run:
        _json_response(handler, {"ok": False, "error": "No active analysis"})
        return

    with _evolve_lock:
        active = _active_evolve_runs.get(run["run_id"])
    if not active or not _is_evolve_run_active(run):
        with _evolve_lock:
            _active_evolve_runs.pop(run["run_id"], None)
        _json_response(handler, {"ok": False, "error": "No active analysis"})
        return

    with _evolve_lock:
        _cancelled_evolve_run_ids.add(run["run_id"])
    if active.get("proc") is not None:
        _kill_evolve_process(active["proc"])
    _db.evolve_run_update(
        run["run_id"],
        status="cancelled",
        snapshot={"cancelled": True},
        error_message="Cancelled by user",
    )
    with _evolve_lock:
        _active_evolve_runs.pop(run["run_id"], None)
    _json_response(handler, {"ok": True, "run_id": run["run_id"]})


def _evolve_fallback(handler, tab: str, reason: str) -> dict:
    """Return empty data with error info."""
    fallbacks = {
        "profile": {"categories": [], "radar": {"dimensions": []}, "_error": reason},
        "memory": {"nodes": [], "links": [], "cards": [], "_error": reason},
        "rules": {"rules": [], "_error": reason},
        "signals": {"timeline": [], "events": [], "_error": reason},
        "patterns": {"bubbles": [], "cards": [], "_error": reason},
    }
    return fallbacks.get(tab, {"_error": reason})


def _collect_stats(handler, source: str, date: str, project: str, cli_path: str) -> str:
    """Pre-collect stats only (small, ~1KB) for embedding in prompt."""
    cmd = [sys.executable, cli_path, "stats", "--date", date, "--source", source]
    if project:
        cmd.extend(["--project", project])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _collect_profile_digest(
    handler, source: str, date: str, project: str, cli_path: str
) -> str:
    """Run profile-digest command and return JSON string."""
    import subprocess

    cmd = [
        sys.executable,
        cli_path,
        "profile-digest",
        "--date",
        date,
        "--source",
        source,
    ]
    if project:
        cmd.extend(["--project", project])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _collect_aggregates(handler) -> str:
    """Pre-collect trimmed aggregates (~2KB) for embedding in prompt."""
    from chatview import db as _db

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


def _build_evolve_prompt(
    handler,
    tab: str,
    source: str,
    date: str,
    project: str,
    cli_path: str,
    engine: str = "auto",
    lang: str = "zh",
) -> str:
    """Build a prompt that instructs the AI to progressively explore data via CLI tools."""
    cli_flags = f"--date {date} --source {source}"
    if project:
        cli_flags += f' --project "{project}"'

    write_cmd = f"python3 {cli_path} evolve-write --tab {tab} --source {source} --date {date} --engine {engine}"
    if project:
        write_cmd += f' --project "{project}"'

    # All AI tabs benefit from pre-computed digest (corrections, friction, queries, decisions)
    digest = _collect_profile_digest(handler, source, date, project, cli_path)

    parts = [
        "# Background",
        "",
        "You are part of an AI self-evolution system called 'Chat Viewer Evolve'.",
        "It analyzes a user's past AI conversation history (from Claude Code and Codex CLI sessions)",
        "to extract insights about the user — their preferences, work patterns, recurring mistakes, and collaboration style.",
        "",
    ]

    digest_cmd = (
        f"python3 {cli_path} profile-digest --date {date} --source {source}"
        + (f' --project "{project}"' if project else "")
    )
    if tab in ("profile", "memory") and digest:
        # Digest-based flow: main agent sees full digest, sub-agents run command to get it
        parts.extend(
            [
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
                f"  - Full CLI tool: `python3 {cli_path} <command> --date {date} --source {source}"
                + (f' --project "{project}"' if project else "")
                + "`",
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
            ]
        )
    else:
        # CLI exploration flow: for rules/signals/patterns tabs
        cli_flags = f"--date {date} --source {source}"
        if project:
            cli_flags += f' --project "{project}"'

        stats = _collect_stats(handler, source, date, project, cli_path)
        aggregates = _collect_aggregates(handler)

        # Count sessions
        with _idx._index_lock:
            sessions = dict(_idx._index.get("sessions", {}))
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
                    age = (
                        now
                        - datetime.fromisoformat(
                            d.replace("Z", "+00:00").replace("+00:00", "").rstrip("Z")
                        )
                    ).days
                    if age > max_days:
                        continue
                except (ValueError, TypeError):
                    pass
            session_count += 1

        parts.extend(
            [
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
                f"Options: --date {date} --source {source}"
                + (f' --project "{project}"' if project else "")
                + " --limit N",
                f"Scope: {session_count} sessions in range",
                "",
            ]
        )

        if stats:
            parts.extend(
                [
                    "# Pre-collected Data (do NOT re-run these)",
                    "",
                    "=== STATS ===",
                    stats,
                    "",
                ]
            )
        if aggregates:
            parts.extend(["=== AGGREGATES ===", aggregates, ""])
        if digest:
            parts.extend(
                [
                    "",
                    "# Pre-computed Profile Digest (corrections, friction, queries, decisions — do NOT re-run profile-digest)",
                    "",
                    digest,
                    "",
                ]
            )

        claude_dir = str(Path.home() / ".claude" / "projects")
        codex_dir = str(Path.home() / ".codex")
        parts.extend(
            [
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
            ]
        )

    if tab == "profile":
        en = lang == "en"
        cat_name = "category name" if en else "分类名"
        desc_name = "specific description" if en else "具体描述"
        dim_name = "dimension" if en else "领域"
        evidence_name = "brief evidence" if en else "简述依据"
        cat_directions = (
            "Category directions (reference): professional identity, work style, AI collaboration preferences, "
            "communication habits, technical aesthetics, engineering standards, etc."
            if en
            else "分类方向（参考，不限于此）：职业身份、工作风格、AI协作偏好、沟通与决策习惯、技术审美、工程标准等"
        )
        lang_rule = (
            "- All content in English. Do not quote user's original words directly."
            if en
            else "- 所有内容用中文，不需要引用用户原话"
        )
        parts.extend(
            [
                "TASK: Build a USER PROFILE — about the PERSON, not their projects.",
                "Profile should cover: who they are, how they work, what they care about, their style and preferences.",
                "Projects are evidence, not categories. Focus on behavioral patterns across projects.",
                "",
                f"Write result via: {write_cmd} --mode replace <<'EVOLVE_EOF'",
                "JSON schema:",
                "{"
                + f'"categories": [{{"name": "{cat_name}", "icon": "emoji", "tags": ["标签"],',
                f'  "items": [{{"text": "{desc_name}", "confidence": "high|medium|low"}}]}}],',
                f' "radar": {{"dimensions": [{{"name": "{dim_name}", "score": 0.0-1.0, "evidence": "{evidence_name}"}}]}}'
                + "}",
                "",
                cat_directions,
                "质量要求：",
                "- 6-8 categories, 30+ items, 丰富的 tags",
                "- items 要具体，提到行为模式和偏好，不要泛泛概括",
                "- 示例：✗「用户关注前端开发」 ✓「反复要求仿 ChatGPT 消息流式布局，重视工具卡片折叠、自动滚动等交互细节」",
                lang_rule,
            ]
        )
    elif tab == "memory":
        en = lang == "en"
        trigger_ex = (
            "what scenario triggers this memory" if en else "什么场景触发这条记忆"
        )
        instruction_ex = "what AI should do" if en else "AI 应该怎么做"
        avoid_ex = (
            "what AI should not do (can be empty)"
            if en
            else "AI 不应该做什么(可为空字符串)"
        )
        content_ex = (
            "full description (backward-compatible, can be generated from trigger+instruction)"
            if en
            else "完整描述(向后兼容,可从trigger+instruction生成)"
        )
        quote_ex = "user's original words" if en else "用户原话"
        lang_rule = "- All descriptions in English" if en else "- 所有描述用中文"
        parts.extend(
            [
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
                f'  "trigger": "{trigger_ex}",',
                f'  "instruction": "{instruction_ex}",',
                f'  "avoid": "{avoid_ex}",',
                f'  "content": "{content_ex}",',
                '  "firstSeen": "YYYY-MM-DD", "lastSeen": "YYYY-MM-DD",',
                f'  "evidence": [{{"quote": "{quote_ex}", "sessionId": "session-id", "date": "YYYY-MM-DD"}}],',
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
                lang_rule,
            ]
        )
    elif tab == "rules":
        en = lang == "en"
        rule_title = "rule title" if en else "规则标题"
        source_scenario = "source scenario" if en else "来源场景"
        quote_ex = "user's original words" if en else "用户原话"
        # Same prompt as the "规则生成" preset in app.js
        parts.extend(
            [
                "分析所有对话中用户纠正AI的场景，自动生成CLAUDE.md规则。",
                "",
                "**工作流（按顺序执行）**：",
                "1. 先运行 `corrections` 获取所有纠正样本（已含50+种中英文信号词检测）",
                "2. 运行 `highlights` 找高纠正数的会话（corr≥3的重点关注）",
                "3. 对高纠正会话运行 `read -s <id>` 看上下文（理解纠正原因）",
                '4. 补充搜索 `search "不行"` `search "太精简"` `search "应该是"` 等关键词',
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
                f'  "rule": "{rule_title}", "why": "{source_scenario}", "frequency": N,',
                f'  "evidence": [{{"quote": "{quote_ex}", "session": "session-id"}}]}}]}}',
            ]
        )
    elif tab == "signals":
        en = lang == "en"
        user_quote_ex = "user's original words" if en else "用户原话"
        ai_issue_ex = "what AI did wrong" if en else "AI做错了什么"
        correction_ex = "what should be done" if en else "应该怎么做"
        lang_rule = "- All descriptions in English" if en else "- 所有描述用中文"
        parts.extend(
            [
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
                f'   "userQuote": "{user_quote_ex}", "aiIssue": "{ai_issue_ex}", "correction": "{correction_ex}",',
                '   "linkedRule": null}]}',
                "",
                "质量要求：",
                "- events 按时间倒序，每个附 session ID + 用户原话",
                "- timeline 覆盖查询日期范围内每天的统计",
                lang_rule,
            ]
        )
    elif tab == "patterns":
        en = lang == "en"
        pattern_name = "pattern name" if en else "模式名称"
        detail_desc = "detailed description" if en else "详细描述"
        cost_ex = "estimated impact" if en else "估算影响"
        suggestion_ex = "improvement suggestion" if en else "改进建议"
        lang_rule = "- All content in English" if en else "- 所有内容用中文"
        parts.extend(
            [
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
                "{"
                + f'"bubbles": [{{"id": "p1", "label": "{pattern_name}", "type": "error|efficiency|knowledge_gap|workflow",',
                '   "frequency": N, "trend": "increasing|stable|decreasing"}],',
                f' "cards": [{{"id": "p1", "description": "{detail_desc}", "frequency": N,',
                f'   "trend": "increasing|stable|decreasing", "cost": "{cost_ex}",',
                f'   "suggestion": "{suggestion_ex}", "sessions": ["session-id"]}}]'
                + "}",
                "",
                "质量要求：",
                "- bubbles 和 cards 的 id 一一对应",
                "- 每个模式附具体 session 引用",
                "- 关注真正反复出现的模式（≥2次），不要列一次性事件",
                lang_rule,
            ]
        )

    parts.extend(
        [
            "",
            "RULES:",
            "- NEVER truncate CLI output with head/tail. Use --limit if output is too large.",
            "- evolve-write validates JSON schema. If it fails, read the error and fix.",
        ]
    )

    return "\n".join(parts)
