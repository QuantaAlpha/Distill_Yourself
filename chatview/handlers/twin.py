"""Twin AI handler functions.

Extracted from server.py — handles twin cognitive handbook analysis pipeline,
evolve sync dispatch, and twin sync to CLAUDE.md.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from chatview.handlers.base import (
    _json_response,
    _error,
    _sse_event,
    _start_sse,
    _read_post_body,
)
from chatview.ai_engine import (
    _run_ai_engine_stream,
    _select_cognitive_avatar,
    _normalize_ai_engine,
)
from chatview.utils.sync import _safe_write_claude_md

# ---------------------------------------------------------------------------
# Active analysis state (for /api/twin/cancel)
# ---------------------------------------------------------------------------
_active_analyze_proc = None
_active_analyze_run_id = None
# 流水线整体运行中标志：覆盖 Stage4/5 及阶段间隙（这些阶段不注册 subprocess），
# 避免 /api/twin/progress 在这些时刻误报 running=False。
_active_analyze_pipeline = False
_active_analyze_cancel_requested = False
_cancelled_analyze_run_ids = set()
_analyze_lock = threading.Lock()


def _is_twin_analysis_running_locked() -> bool:
    """Return whether the active Twin run is still live.

    Caller must hold _analyze_lock.
    """
    if _active_analyze_run_id is None:
        return False
    proc_alive = False
    if _active_analyze_proc is not None:
        if hasattr(_active_analyze_proc, "poll"):
            try:
                proc_alive = _active_analyze_proc.poll() is None
            except Exception:
                proc_alive = False
        else:
            # Some tests use minimal fake process objects. If a proc-like
            # object is registered without poll(), treat it as active.
            proc_alive = True
    return proc_alive or _active_analyze_pipeline


def _is_twin_analysis_running() -> bool:
    with _analyze_lock:
        return _is_twin_analysis_running_locked()


def _is_twin_cancel_requested(run_id: str) -> bool:
    with _analyze_lock:
        return run_id in _cancelled_analyze_run_ids or (
            _active_analyze_run_id == run_id and _active_analyze_cancel_requested
        )


def _kill_twin_process(proc):
    """Best-effort terminate an active Twin subprocess; safe for None/fakes."""
    if proc is None:
        return
    try:
        if hasattr(proc, "poll") and proc.poll() is not None:
            return
    except Exception:
        pass
    try:
        if os.name == "posix" and getattr(proc, "pid", None) is not None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
        elif hasattr(proc, "terminate"):
            try:
                proc.terminate()
            except (ProcessLookupError, OSError):
                pass

        if hasattr(proc, "wait"):
            try:
                proc.wait(timeout=2)
                return
            except subprocess.TimeoutExpired:
                pass

        if os.name == "posix" and getattr(proc, "pid", None) is not None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
        elif hasattr(proc, "kill"):
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass

        if hasattr(proc, "wait"):
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
    except Exception:
        pass


def _handle_evolve_sync(handler):
    """Handle POST /api/evolve/sync — preview or execute sync to Claude Code."""
    from chatview.handlers.sync import (
        _evolve_sync_memory_preview,
        _evolve_sync_memory_execute,
        _evolve_sync_claude_md_preview,
        _evolve_sync_claude_md_execute,
    )
    from chatview import db as _db

    raw = _read_post_body(handler)
    if raw is None:
        return
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _error(handler, 400, "Invalid JSON")
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
        _error(handler, 400, str(e))
        return

    if action not in ("preview", "execute"):
        _error(handler, 400, "Invalid action")
        return

    result = {}

    if "memory" in targets:
        row = _db.evolve_get_shared("memory", source, date, project, engine)
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
        row = _db.evolve_get_shared("profile", source, date, project, engine)
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
            result["claude_md"] = {
                "error": "Profile cache not found — run Refresh first"
            }

    result["ok"] = all("error" not in v for v in result.values() if isinstance(v, dict))
    _json_response(handler, result)


def _run_twin_ai_stage(
    handler, prompt: str, stage_label: str, proc_ref=None, engine: str = "auto"
) -> bool:
    """Stream a Twin AI stage. When the client disconnects (BrokenPipeError),
    continue draining the stream so the AI process can complete and persist
    results to the database.

    Returns False when the client disconnects mid-stream (caller should stop
    sending further SSE events), but the AI process is allowed to finish.
    """
    def _on_proc_start(proc):
        # Register the live subprocess for cancellation the instant it is
        # created — not after the first streamed event — so /api/twin/cancel can
        # terminate it even during the codex→claude fallback's pre-stream gap,
        # where the proc is born after an initial text event has been yielded.
        if proc is not None and proc.poll() is None:
            with _analyze_lock:
                global _active_analyze_proc
                _active_analyze_proc = proc

    stream = _run_ai_engine_stream(
        prompt,
        allow_write=True,
        timeout=600,
        engine_override=engine,
        proc_ref=proc_ref,
        for_twin=True,
        on_proc_start=_on_proc_start,
    )
    disconnected = False
    try:
        for evt in stream:
            if disconnected:
                continue  # drain silently — AI process still writes to DB
            try:
                _sse_event(handler, evt)
            except BrokenPipeError:
                disconnected = True
            if evt.get("type") == "error":
                return False
        return True  # AI completed successfully, even if client disconnected
    except BrokenPipeError:
        # Already draining — let the finally block close the stream
        return False
    except Exception as e:
        if not disconnected:
            try:
                _sse_event(
                    handler, {"type": "error", "message": f"{stage_label} failed: {e}"}
                )
            except BrokenPipeError:
                pass
        return False
    finally:
        stream.close()


def _handle_twin_analyze(handler):
    """POST /api/twin/analyze — run 5-stage cognitive handbook extraction via AI.

    Supports checkpoint caching (Issue 2.1):
    - If resume=true, checks for a partial run via get_latest_checkpoint()
    - Stages already marked "completed" in the checkpoint are skipped
    - Each stage records "running"/"completed" status in twin_checkpoints
    """
    global _active_analyze_proc, _active_analyze_run_id
    global _active_analyze_pipeline, _active_analyze_cancel_requested
    from chatview import db as _db
    from chatview.handlers.base import _read_post_body
    import json as _json

    # Read lang + engine + resume from POST body if provided
    raw = _read_post_body(handler)
    lang = "zh"
    engine = "auto"
    resume = False
    requested_run_id = None
    if raw:
        try:
            body = _json.loads(raw)
            lang = body.get("lang", "zh")
            engine = body.get("engine", "auto")
            resume = body.get("resume", False)
            requested_run_id = body.get("run_id") or None
        except Exception:
            pass
    try:
        engine = _normalize_ai_engine(engine)
    except ValueError:
        engine = "auto"
    en = lang == "en"

    cli_path = str(Path(__file__).resolve().parent.parent.parent / "analyze.py")

    with _analyze_lock:
        if _is_twin_analysis_running_locked():
            _error(handler, 409, "Twin analysis is already running")
            return

    # ── Checkpoint / resume logic ──
    _db.init_db()
    run_id = None
    skip_stages = set()

    if resume:
        # Prefer the run_id explicitly requested by the client so a reopened tab
        # resumes the exact run it was tracking; fall back to the latest run.
        checkpoints = None
        if requested_run_id:
            stages = _db.get_checkpoint(requested_run_id)
            if stages:
                run_id = requested_run_id
                checkpoints = {str(k): v for k, v in stages.items()}
        if checkpoints is None:
            latest = _db.get_latest_checkpoint()
            if latest and latest.get("stages"):
                run_id = latest["run_id"]
                checkpoints = {str(k): v for k, v in latest["stages"].items()}
        if checkpoints:
            # Only skip stages that fully completed — failed / cancelled /
            # running stages are re-run so a resume can continue past an error.
            skip_stages = {
                int(stage)
                for stage, status in checkpoints.items()
                if status == "completed"
            }

    if run_id is None:
        run_id = "run_" + uuid.uuid4().hex[:12]

    # Register active run for cancellation (thread-safe)
    proc_ref: list = [None]
    with _analyze_lock:
        _active_analyze_run_id = run_id
        _active_analyze_proc = None
        _active_analyze_pipeline = True
        _active_analyze_cancel_requested = False
        _cancelled_analyze_run_ids.discard(run_id)

    def _run_stage(stage_num, msg_en, msg_zh, prompt_fn, is_ai=True):
        """Run a single pipeline stage with checkpointing.

        When the client disconnects (BrokenPipeError), the stage still runs
        silently so the AI process can complete and persist results to DB.
        """
        global _active_analyze_proc
        if _is_twin_cancel_requested(run_id):
            _db.save_checkpoint(run_id, stage_num, "cancelled")
            return False
        _db.save_checkpoint(run_id, stage_num, "running")
        msg = msg_en if en else msg_zh
        try:
            _sse_event(handler, {"type": "text", "content": msg})
        except BrokenPipeError:
            pass  # client gone — continue silently

        if stage_num in skip_stages:
            try:
                _sse_event(
                    handler,
                    {
                        "type": "text",
                        "content": "(skipped — already completed)\n"
                        if en
                        else "（已跳过——已完成）\n",
                    },
                )
            except BrokenPipeError:
                pass
            _db.save_checkpoint(run_id, stage_num, "completed")
            return True

        if is_ai:
            prompt = prompt_fn()
            proc_ref[0] = None
            try:
                ok = _run_twin_ai_stage(
                    handler,
                    prompt,
                    f"Stage {stage_num}",
                    proc_ref=proc_ref,
                    engine=engine,
                )
            except BrokenPipeError:
                ok = False
            finally:
                with _analyze_lock:
                    if _active_analyze_proc is proc_ref[0]:
                        _active_analyze_proc = None
            if not ok:
                status = "cancelled" if _is_twin_cancel_requested(run_id) else "failed"
                _db.save_checkpoint(run_id, stage_num, status)
                return False
        else:
            try:
                ok = prompt_fn()  # subprocess stages use the closure directly
            except BrokenPipeError:
                ok = True
            if ok is False:
                status = "cancelled" if _is_twin_cancel_requested(run_id) else "failed"
                _db.save_checkpoint(run_id, stage_num, status)
                return False
        if _is_twin_cancel_requested(run_id):
            _db.save_checkpoint(run_id, stage_num, "cancelled")
            return False
        _db.save_checkpoint(run_id, stage_num, "completed")
        return True

    try:
        _start_sse(handler)
        try:
            _sse_event(handler, {"type": "text", "content": f"Twin run_id: {run_id}\n"})
        except BrokenPipeError:
            pass  # client gone — stages will continue silently

        # Stage 1: Evidence event extraction
        if not _run_stage(
            1,
            "Stage 1/5: Extracting decision events (Evidence Events)...\n",
            "Stage 1/5: 从对话历史中提取决策事件 (Evidence Events)...\n",
            lambda: _build_twin_stage1_prompt(handler, cli_path, run_id, lang),
            is_ai=True,
        ):
            return

        # Stage 2: Judgment card distillation
        if not _run_stage(
            2,
            "\n\nStage 2/5: Distilling judgment cards...\n",
            "\n\nStage 2/5: 从事件中蒸馏判断卡 (Judgment Cards)...\n",
            lambda: _build_twin_stage2_prompt(handler, cli_path, run_id, lang),
            is_ai=True,
        ):
            return

        # Stage 3: Cognitive trait inference
        if not _run_stage(
            3,
            "\n\nStage 3/5: Inferring cognitive traits...\n",
            "\n\nStage 3/5: 从判断卡归纳认知特质 (Cognitive Traits)...\n",
            lambda: _build_twin_stage3_prompt(handler, cli_path, run_id, lang),
            is_ai=True,
        ):
            return

        # Stage 4: Compile Runtime Pack (pure Python, no AI)
        def _run_stage4():
            stage4_msg = (
                "\n\nStage 4/5: Compiling Runtime Pack...\n"
                if en
                else "\n\nStage 4/5: 编译 Runtime Pack (twin-compile)...\n"
            )
            try:
                _sse_event(handler, {"type": "text", "content": stage4_msg})
            except BrokenPipeError:
                pass
            try:
                proc = subprocess.Popen(
                    [
                        sys.executable,
                        cli_path,
                        "twin-compile",
                        "--run-id",
                        run_id,
                        "--lang",
                        lang,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=(os.name == "posix"),
                )
                with _analyze_lock:
                    if _active_analyze_run_id == run_id:
                        _active_analyze_proc = proc
                try:
                    stdout, stderr = proc.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    _kill_twin_process(proc)
                    try:
                        stdout, stderr = proc.communicate(timeout=2)
                    except Exception:
                        stdout, stderr = "", "timeout"
                finally:
                    with _analyze_lock:
                        if _active_analyze_proc is proc:
                            _active_analyze_proc = None
                if _is_twin_cancel_requested(run_id):
                    return False
                try:
                    _sse_event(
                        handler, {"type": "text", "content": stdout or "(no output)"}
                    )
                except BrokenPipeError:
                    pass
                if proc.returncode != 0:
                    msg = (stderr or stdout or "unknown error")[:500]
                    try:
                        _sse_event(
                            handler,
                            {"type": "error", "message": f"Stage 4 failed: {msg}"},
                        )
                    except BrokenPipeError:
                        pass
                    return False
                return True
            except Exception as e:
                try:
                    _sse_event(
                        handler, {"type": "error", "message": f"Stage 4 failed: {e}"}
                    )
                except BrokenPipeError:
                    pass
                return False

        if not _run_stage(4, "", "", _run_stage4, is_ai=False):
            return

        # Stage 5: AI-based cognitive avatar selection
        def _run_stage5():
            stage5_msg = (
                "\n\nStage 5/5: Matching cognitive model avatar...\n"
                if en
                else "\n\nStage 5/5: 匹配认知模型头像...\n"
            )
            try:
                _sse_event(handler, {"type": "text", "content": stage5_msg})
            except BrokenPipeError:
                pass
            try:
                avatar = _select_cognitive_avatar(
                    force=True, run_id=run_id, lang=lang, engine=engine
                )
                if avatar:
                    match_prefix = "Match result" if en else "匹配结果"
                    try:
                        _sse_event(
                            handler,
                            {
                                "type": "text",
                                "content": f"{match_prefix}: {avatar.get('model_name', '')} ({avatar.get('persona_id', '')})",
                            },
                        )
                    except BrokenPipeError:
                        pass
                else:
                    no_match_msg = (
                        "Failed to match cognitive model (can retry later)"
                        if en
                        else "未能匹配认知模型（可稍后重试）"
                    )
                    try:
                        _sse_event(handler, {"type": "text", "content": no_match_msg})
                    except BrokenPipeError:
                        pass
            except Exception as e:
                try:
                    _sse_event(
                        handler, {"type": "text", "content": f"头像匹配跳过: {e}"}
                    )
                except BrokenPipeError:
                    pass
            return True

        if not _run_stage(5, "", "", _run_stage5, is_ai=False):
            return

        # Summary
        stats = _db.get_twin_stats()
        summary_parts = []
        for t in ["evidence_events", "judgment_cards", "cognitive_traits"]:
            count = stats.get(t, {}).get("count", 0)
            if count > 0:
                label = t.replace("_", " ")
                summary_parts.append(f"{label}: {count}")

        no_data_msg = "No data" if en else "暂无数据"
        summary = ", ".join(summary_parts) if summary_parts else no_data_msg
        complete_msg = "Analysis complete" if en else "分析完成"
        try:
            _sse_event(
                handler,
                {"type": "text", "content": f"\n\n✅ {complete_msg} — {summary}"},
            )
            _sse_event(handler, {"type": "done", "content": summary})
        except BrokenPipeError:
            pass
    finally:
        # Always clear active analysis state
        with _analyze_lock:
            if _active_analyze_run_id == run_id:
                _active_analyze_proc = None
                _active_analyze_run_id = None
                _active_analyze_pipeline = False
                _active_analyze_cancel_requested = False
            _cancelled_analyze_run_ids.discard(run_id)


def _build_twin_stage1_prompt(
    handler, cli_path: str, run_id: str, lang: str = "zh"
) -> str:
    """Build prompt for Stage 1: Evidence event extraction from conversation history."""
    from chatview.handlers.evolve import _collect_profile_digest

    digest = _collect_profile_digest(handler, "all", "all", "", cli_path)

    lang_instruction = "All text in English" if lang == "en" else "All text in Chinese"

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
  twin-candidates       — Validate candidate operations without writing

# Current Run Scope

Run ID: {run_id}
All writes in this run MUST use `twin-batch` with top-level `"run_id": "{run_id}"`.

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
{{"run_id": "{run_id}", "operations": [
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
- IMPORTANT: For this run, use only `twin-batch` with run_id `{run_id}` for writes.
- {lang_instruction}
"""


def _build_twin_stage2_prompt(
    handler, cli_path: str, run_id: str, lang: str = "zh"
) -> str:
    """Build prompt for Stage 2: Judgment card distillation from evidence events."""
    from chatview import db as _db

    _db.init_db()

    # Get current-run cards/events only; cross-run data is not Stage 2 input.
    existing_cards = _db.cm_get_all(
        "judgment_cards", where="run_id=?", params=(run_id,), limit=100
    )
    events = _db.cm_get_all(
        "evidence_events",
        where="run_id=?",
        params=(run_id,),
        order="created_at DESC",
        limit=100,
    )
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
            lines.append(
                f"  id={c.get('id', '')} applies_when={json.dumps(c.get('applies_when', ''), ensure_ascii=False)} "
                f"judgment={json.dumps((c.get('judgment', '') or '')[:80], ensure_ascii=False)} "
                f"tags={c.get('tags', '')} status={c.get('status', '')} confidence={c.get('confidence', '')}"
            )
        existing_cards_str = "\n".join(lines)
    else:
        existing_cards_str = "  (empty — no existing cards)"

    lang_instruction = "All text in English" if lang == "en" else "All text in Chinese"
    applies_when_example = (
        "Trigger scenario (1-2 sentences)" if lang == "en" else "触发场景（1-2句）"
    )
    judgment_example = (
        "User's reasoning logic (natural language paragraph, 2-4 sentences)"
        if lang == "en"
        else "用户的推理逻辑（自然语言段落，2-4句）"
    )
    agent_action_example = (
        "What the AI should do (1-2 sentences)"
        if lang == "en"
        else "AI 应该怎么做（1-2句）"
    )
    exceptions_example = "Exception conditions" if lang == "en" else "例外条件"

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

# Current Run Scope

Run ID: {run_id}
All writes/links in this stage MUST use `twin-batch` with top-level `"run_id": "{run_id}"`.

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
  "applies_when": "{applies_when_example}",
  "judgment": "{judgment_example}",
  "agent_action": "{agent_action_example}",
  "exceptions": "{exceptions_example}",
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
{{"run_id": "{run_id}", "operations": [
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
- **{lang_instruction}**
- **Dedup carefully**: Two events about "不要改无关文件" and "只改必要代码" should merge into one card, not create two. Use `twin-edit` to merge, not `twin-add` to duplicate.
"""


def _build_twin_stage3_prompt(
    handler, cli_path: str, run_id: str, lang: str = "zh"
) -> str:
    """Build prompt for Stage 3: Cognitive trait inference from judgment cards."""
    from chatview import db as _db

    _db.init_db()

    cards = _db.cm_get_all(
        "judgment_cards",
        where="run_id=?",
        params=(run_id,),
        order="confidence DESC",
        limit=100,
    )
    cards_json = json.dumps([dict(c) for c in cards], ensure_ascii=False, default=str)

    existing_traits = _db.cm_get_all(
        "cognitive_traits", where="run_id=?", params=(run_id,), limit=50
    )
    existing_str = ""
    if existing_traits:
        lines = []
        for t in existing_traits[:20]:
            lines.append(
                f"  id={t.get('id', '')} name={json.dumps(t.get('name', ''), ensure_ascii=False)} "
                f"category={t.get('category', '')} status={t.get('status', '')} strength={t.get('strength', '')}"
            )
        existing_str = "\n".join(lines)
    else:
        existing_str = "  (empty — no existing traits)"

    lang_instruction = "All text in English" if lang == "en" else "All text in Chinese"
    if lang == "en":
        categories_block = """Categories:
- **Values**: What the user protects/sacrifices (e.g., minimalism, least-impact principle)
- **Decision Style**: How the user makes judgments (e.g., evidence-first, risk-averse, cautious)
- **Collaboration Mode**: How the user works with AI (e.g., high-control preference, dominant, proposal-first)
- **Capability Boundaries**: Domain expertise levels (e.g., backend expert / learning frontend)
- **Thinking Mode**: Cognitive habits (e.g., systematic thinking, divergent-convergent)"""
        trait_name_example = "Trait Name"
        trait_categories = "Values|Decision Style|Collaboration Mode|Capability Boundaries|Thinking Mode"
        trait_desc_example = "Natural language description (2-4 sentences)"
    else:
        categories_block = """Categories:
- **价值取向**: What the user protects/sacrifices (e.g., 极简主义, 最小影响原则)
- **决策风格**: How the user makes judgments (e.g., 证据先行, 风险厌恶, 谨慎型)
- **协作模式**: How the user works with AI (e.g., 高控制偏好, 主导型, 方案先行)
- **能力边界**: Domain expertise levels (e.g., 后端专家/前端学习中)
- **思维模式**: Cognitive habits (e.g., 系统性思维, 发散-收敛型)"""
        trait_name_example = "特质名称"
        trait_categories = "价值取向|决策风格|协作模式|能力边界|思维模式"
        trait_desc_example = "自然语言描述（2-4句）"

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

# Current Run Scope

Run ID: {run_id}
All writes/links in this stage MUST use `twin-batch` with top-level `"run_id": "{run_id}"`.

# Judgment Cards (input data)

{cards_json}

# Existing Cognitive Traits (for dedup)

{existing_str}

# Task

Analyze the judgment cards above and infer cognitive traits. This is INCREMENTAL — update existing traits or add new ones.

{categories_block}

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
  "name": "{trait_name_example}",
  "category": "{trait_categories}",
  "description": "{trait_desc_example}",
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
- **{lang_instruction}**
"""


def _twin_run_info_for(run_id):
    """Compute {run_id, status, stats, checkpoints} for a single run_id.

    Counts evidence_events / judgment_cards / cognitive_traits rows, infers a
    status from data completeness, then reconciles with twin_checkpoints (the
    authoritative source for failure/cancel state). Shared by
    _latest_twin_run_info and the recent-runs listing.
    """
    from chatview import db as _db

    stats = {}
    stat_keys = {
        "evidence_events": "events",
        "judgment_cards": "cards",
        "cognitive_traits": "traits",
    }
    try:
        conn = _db.get_conn()
        for table, key in stat_keys.items():
            try:
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
                stats[key] = count
            except Exception:
                stats[key] = 0
    except Exception:
        stats = {"events": 0, "cards": 0, "traits": 0}

    # Infer status from data completeness
    has_events = stats.get("events", 0) > 0
    has_cards = stats.get("cards", 0) > 0
    has_traits = stats.get("traits", 0) > 0
    if has_traits and has_cards:
        status = "completed"
    elif has_events or has_cards:
        status = "partial"
    else:
        status = "empty"

    # Include checkpoint info from twin_checkpoints table. Checkpoints are the
    # authoritative source for failure/cancel state — row counts alone cannot
    # tell a failed run apart from a completed one.
    checkpoints = _db.get_checkpoint(run_id)
    checkpoint_info = {str(k): v for k, v in checkpoints.items()} if checkpoints else {}

    # Reconcile with checkpoints — a failed/cancelled stage must not be
    # reported as "completed" (the UI would otherwise show "Analysis complete").
    # Only override when the run is not genuinely finished (< 5 completed).
    cp_values = set(checkpoint_info.values())
    completed_stages = sum(1 for v in checkpoint_info.values() if v == "completed")
    if completed_stages < 5:
        if "failed" in cp_values:
            status = "failed"
        elif completed_stages > 0:
            # Resumable progress: some stages completed, the rest were
            # cancelled or never ran. Report "partial" so resume can continue
            # from the checkpoint instead of looking like a dead-end cancel.
            status = "partial"
        elif "cancelled" in cp_values:
            status = "cancelled"
        elif status == "completed":
            status = "partial"

    return {
        "run_id": run_id,
        "status": status,
        "stats": stats,
        "checkpoints": checkpoint_info,
    }


def _latest_twin_run_info():
    """Compute info about the most recent twin analysis run.

    Shared by /api/twin/resume and /api/twin/progress. Queries
    evidence_events, judgment_cards, and cognitive_traits for the latest
    run_id, derives stats + a status, and merges twin_checkpoints state.

    Returns a run dict ({run_id, status, stats, checkpoints}) or None when no
    run data and no checkpoint exists.
    """
    from chatview import db as _db

    _db.init_db()

    # Each table's recency column differs: cognitive_traits has only updated_at.
    # A wrong/missing column raises OperationalError (caught by the inner except
    # below), silently dropping that table from "latest run" selection, so resume
    # would not be authoritative.
    table_ts = {
        "evidence_events": "created_at",
        "judgment_cards": "created_at",
        "cognitive_traits": "updated_at",
    }
    latest_run_id = None
    latest_created = ""

    try:
        conn = _db.get_conn()
        for table, ts_col in table_ts.items():
            try:
                row = conn.execute(
                    f"SELECT run_id, MAX({ts_col}) as latest FROM {table} "
                    f"WHERE run_id IS NOT NULL AND run_id != ''"
                ).fetchone()
                if row and row["latest"] and row["latest"] > latest_created:
                    latest_created = row["latest"]
                    latest_run_id = row["run_id"]
            except Exception:
                continue
    except Exception:
        return None

    if not latest_run_id:
        checkpoint = _db.get_latest_checkpoint()
        if not checkpoint:
            return None
        checkpoint_info = {str(k): v for k, v in checkpoint.get("stages", {}).items()}
        return {
            "run_id": checkpoint["run_id"],
            "status": "interrupted",
            "stats": {"events": 0, "cards": 0, "traits": 0},
            "checkpoints": checkpoint_info,
        }

    return _twin_run_info_for(latest_run_id)


def _handle_twin_resume(handler):
    """POST /api/twin/resume — return info about the most recent twin analysis run.

    Queries evidence_events, judgment_cards, and cognitive_traits tables for
    the latest run_id and returns stats. Includes checkpoint data (Issue 2.1).
    Returns {ok: false, run: null} if no run data exists.
    """
    run = _latest_twin_run_info()
    if run is None:
        _json_response(handler, {"ok": False, "run": None})
        return
    _json_response(handler, {"ok": True, "run": run})


def _handle_twin_runs(handler):
    """GET /api/twin/runs — list the most recent twin analysis runs.

    Returns up to 10 distinct run_ids (newest first) with their derived
    {run_id, status, stats, checkpoints, ts}, so the UI can render a recent
    history list below the current progress summary.
    """
    from chatview import db as _db

    _db.init_db()
    limit = 10
    try:
        from urllib.parse import urlparse, parse_qs

        qs = parse_qs(urlparse(getattr(handler, "path", "")).query)
        if qs.get("limit"):
            limit = max(1, min(20, int(qs["limit"][0])))
    except Exception:
        limit = 10

    runs = []
    try:
        recent = _db.list_recent_run_ids(limit)
    except Exception:
        recent = []
    for entry in recent:
        run_id = entry.get("run_id")
        if not run_id:
            continue
        info = _twin_run_info_for(run_id)
        info["ts"] = entry.get("ts") or ""
        runs.append(info)

    _json_response(handler, {"ok": True, "runs": runs})


def _handle_twin_progress(handler):
    """GET /api/twin/progress — let a reopened tab re-attach to a background run.

    Reports whether an analysis is still running (the AI subprocess keeps
    writing to the DB even after the original SSE client disconnected) plus
    the latest run + per-stage checkpoint map, so the UI can rebuild progress
    without restarting from stage 1.
    """
    requested_run_id = ""
    try:
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(getattr(handler, "path", "")).query)
        requested_run_id = (qs.get("run_id") or [""])[0] or ""
    except Exception:
        requested_run_id = ""

    with _analyze_lock:
        active_run_id = _active_analyze_run_id
        running = _is_twin_analysis_running_locked()

    if requested_run_id:
        run = _twin_run_info_for(requested_run_id)
        if running and active_run_id == requested_run_id:
            run["status"] = "running"
        running = running and active_run_id == requested_run_id
    elif running and active_run_id:
        # Prefer the active run over "latest" persisted data; a new run may not
        # have written rows yet, while an older completed run still exists.
        run = _twin_run_info_for(active_run_id)
        run["status"] = "running"
    else:
        run = _latest_twin_run_info()

    _json_response(
        handler,
        {"ok": True, "running": running, "run": run},
    )


def _handle_twin_cancel(handler):
    """POST /api/twin/cancel — cancel a running twin analysis.

    Reads optional run_id from POST body. If provided and doesn't match the
    active run, returns an error. Terminates the active subprocess gracefully
    (SIGTERM then SIGKILL if needed) and clears module state.
    """
    global _active_analyze_proc, _active_analyze_run_id
    global _active_analyze_pipeline, _active_analyze_cancel_requested
    from chatview.handlers.base import _read_post_body
    import json as _json

    # Read run_id from body if provided
    raw = _read_post_body(handler)
    requested_run_id = None
    if raw:
        try:
            body = _json.loads(raw)
            requested_run_id = body.get("run_id")
        except Exception:
            pass

    with _analyze_lock:
        proc = _active_analyze_proc
        active_run_id = _active_analyze_run_id
        pipeline_active = _active_analyze_pipeline

        # Check if there's an active run (a live subprocess OR the pipeline is
        # still progressing through a non-AI stage).
        if active_run_id is None or not _is_twin_analysis_running_locked():
            _json_response(handler, {"ok": False, "error": "No active analysis"})
            return

        # Validate run_id if provided
        if requested_run_id and requested_run_id != active_run_id:
            _json_response(handler, {"ok": False, "error": "Run ID mismatch"})
            return

    # Mark cancellation before killing so the worker thread records cancelled
    # rather than failed if it observes the terminated process.
    with _analyze_lock:
        if _active_analyze_run_id == active_run_id:
            _active_analyze_cancel_requested = True
            _cancelled_analyze_run_ids.add(active_run_id)

    # Terminate the process (outside the lock to avoid holding it during waits).
    _kill_twin_process(proc)

    # Clear active state but PRESERVE completed-stage data so a later resume can
    # continue instead of restarting from stage 1 (wasting time + tokens).
    with _analyze_lock:
        run_to_clean = None
        if proc is not None or not pipeline_active:
            _active_analyze_proc = None
            run_to_clean = _active_analyze_run_id
            _active_analyze_run_id = None
            _active_analyze_pipeline = False
            _active_analyze_cancel_requested = False

    # Mark any non-completed checkpoint stages as "cancelled" (keep completed
    # stages + their evidence_events / judgment_cards / cognitive_traits rows).
    if run_to_clean:
        try:
            from chatview import db as _db

            _db.init_db()
            stages = _db.get_checkpoint(run_to_clean)
            for stage, status in stages.items():
                if status not in ("completed",):
                    _db.save_checkpoint(run_to_clean, stage, "cancelled")
        except Exception:
            pass  # best-effort; data is preserved regardless

    _json_response(handler, {"ok": True, "cancelled": True})


def _handle_twin_sync(handler):
    """POST /api/twin/sync — compile runtime pack from cards+traits into CLAUDE.md.

    Supports action: "preview" (returns diff without writing) and "execute" (writes).
    """
    from chatview import db as _db
    from chatview.handlers.base import _read_post_body
    from chatview.handlers.sync import build_twin_sync_diff
    import json as _json

    if _is_twin_analysis_running():
        _json_response(
            handler,
            {
                "ok": False,
                "error": "Twin analysis is running; sync is disabled until it finishes",
            },
        )
        return

    # Read lang from POST body if provided
    raw = _read_post_body(handler)
    lang = "zh"
    run_id = ""
    action = "execute"
    if raw:
        try:
            body = _json.loads(raw)
            lang = body.get("lang", "zh")
            run_id = body.get("run_id", "") or ""
            action = body.get("action", "execute")
        except Exception:
            pass

    CLAUDE_MD_PATH = Path(
        os.environ.get("CHATVIEW_CLAUDE_MD") or (Path.home() / ".claude" / "CLAUDE.md")
    )
    CM_MARKER_START = "<!-- cognitive-handbook:start -->"
    CM_MARKER_END = "<!-- cognitive-handbook:end -->"

    sync_where = "status IN ('confirmed','emerging')"
    sync_params = ()
    if run_id:
        sync_where += " AND run_id=?"
        sync_params = (run_id,)
    try:
        cards = _db.cm_get_all(
            "judgment_cards",
            where=sync_where,
            params=sync_params,
            order="confidence DESC",
            limit=25,
        )
        traits = _db.cm_get_all(
            "cognitive_traits",
            where=sync_where,
            params=sync_params,
            order="strength DESC",
            limit=15,
        )
    except Exception as e:
        _json_response(handler, {"ok": False, "error": str(e)})
        return

    # Build CLAUDE.md section — render as natural language
    if lang == "en":
        lines = [CM_MARKER_START, "## Cognitive Handbook (Auto-sync)", ""]
        traits_header = "### About This User"
        cards_header = "### Situational Judgments"
        exception_label = "Exception: "
    else:
        lines = [CM_MARKER_START, "## Cognitive Handbook (Auto-sync)", ""]
        traits_header = "### 关于这位用户"
        cards_header = "### 场景判断"
        exception_label = "例外："

    if traits:
        lines.append(traits_header)
        lines.append("")
        for t in traits:
            name = t.get("name") or ""
            desc = t.get("description") or ""
            lines.append(f"**{name}**。{desc}")
            lines.append("")

    if cards:
        lines.append(cards_header)
        lines.append("")
        for c in cards:
            when = c.get("applies_when") or ""
            judgment = c.get("judgment") or ""
            act = c.get("agent_action") or ""
            exceptions = c.get("exceptions") or ""
            lines.append(f"**{when}**：{judgment}")
            if act:
                lines.append(f"→ {act}")
            if exceptions:
                lines.append(f"{exception_label}{exceptions}")
            lines.append("")

    lines.append(CM_MARKER_END)
    section = "\n".join(lines) + "\n"

    # Preview mode: return diff without writing
    if action == "preview":
        diff = build_twin_sync_diff(CLAUDE_MD_PATH, CM_MARKER_START, CM_MARKER_END, section)
        _json_response(handler, {
            "ok": True,
            "diff": diff,
            "cards_count": len(cards),
            "traits_count": len(traits),
        })
        return

    # Execute mode: write to file
    CLAUDE_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        CLAUDE_MD_PATH.read_text(encoding="utf-8") if CLAUDE_MD_PATH.exists() else ""
    )

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

    _safe_write_claude_md(
        new_text,
        marker_start=CM_MARKER_START,
        marker_end=CM_MARKER_END,
        target_path=CLAUDE_MD_PATH,
    )

    _json_response(
        handler,
        {
            "ok": True,
            "cards_synced": len(cards),
            "traits_synced": len(traits),
            "claude_md": {
                "status": claude_md_status,
                "lines": len(section.strip().split("\n")),
            },
        },
    )
