"""AI engine abstraction layer — detect, run, and stream Codex / Claude CLI."""

import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from chatview.cli_resolver import (
    clear_cli_resolution_cache,
    get_cli_status,
    resolve_cli_path,
)


# ---------------------------------------------------------------------------
# Concurrency control (Issue 2.4)
# ---------------------------------------------------------------------------
_engine_semaphore = threading.Semaphore(3)  # Max 3 concurrent AI processes
_twin_semaphore = threading.Semaphore(1)  # Prevent overlapping twin analyses


# ---------------------------------------------------------------------------
# AI Engine detection and execution
#
# Auto-detection prefers Claude Code, then Codex (see _detect_ai_engine).
# When the engine is auto-selected (engine_override="auto") and Codex ends up
# being used, a Codex failure transparently falls back to Claude. An explicitly
# requested engine ("codex"/"claude") is never silently swapped.
# ---------------------------------------------------------------------------
_ai_engine_cache = None  # "codex" | "claude" | ""
_ai_engine_cache_ts = 0.0  # time.time() when _ai_engine_cache was set
_ENGINE_CACHE_TTL = 300  # seconds — re-check every 5 minutes


def _clear_ai_engine_cache():
    """Clear the cached engine detection so the next call re-evaluates."""
    global _ai_engine_cache, _ai_engine_cache_ts
    _ai_engine_cache = None
    _ai_engine_cache_ts = 0.0
    clear_cli_resolution_cache()


def _normalize_ai_engine(engine: str) -> str:
    """Normalize and validate the requested local AI CLI."""
    engine = (engine or "auto").strip().lower()
    if engine not in {"auto", "codex", "claude"}:
        raise ValueError(f"Invalid AI engine: {engine}")
    return engine


def _kill_process_group(proc):
    if not proc or proc.poll() is not None:
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


def _drain_text_pipe(pipe, sink, limit=12000):
    if not pipe:
        return
    try:
        for line in pipe:
            sink.append(line)
            while sum(len(s) for s in sink) > limit and sink:
                sink.pop(0)
    except Exception:
        pass


def _run_ai_command(cmd, *, prompt_input=None, timeout=300):
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if prompt_input is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=(os.name == "posix"),
    )
    try:
        stdout, stderr = proc.communicate(input=prompt_input, timeout=timeout)
        return stdout, stderr, proc.returncode
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        try:
            stdout, stderr = proc.communicate(timeout=1)
        except Exception:
            stdout, stderr = "", ""
        return stdout or "", (stderr or "") + f"\nTimeout after {timeout}s", 124


def _detect_ai_engine():
    """Auto-detect available AI CLI: Claude Code first, then Codex.

    Result is cached for ``_ENGINE_CACHE_TTL`` seconds.  Callers that discover
    a stale or failed engine should call ``_clear_ai_engine_cache()`` first.
    """
    global _ai_engine_cache, _ai_engine_cache_ts
    now = time.time()
    if _ai_engine_cache is not None and (now - _ai_engine_cache_ts) < _ENGINE_CACHE_TTL:
        return _ai_engine_cache
    _ai_engine_cache = None  # Force re-evaluation when TTL expired
    for name in ("claude", "codex"):
        status = get_cli_status(name)
        if status.get("ok"):
            _ai_engine_cache = name
            _ai_engine_cache_ts = time.time()
            print(f"AI engine: {name}")
            return _ai_engine_cache
    _ai_engine_cache = ""
    _ai_engine_cache_ts = time.time()
    return _ai_engine_cache


def _engine_executable(engine: str) -> str:
    path = resolve_cli_path(engine)
    if path:
        return path
    env_hint = "CHATVIEW_CLAUDE_BIN" if engine == "claude" else "CHATVIEW_CODEX_BIN"
    install_hint = (
        "Install Claude Code or set CHATVIEW_CLAUDE_BIN."
        if engine == "claude"
        else "Install Codex or set CHATVIEW_CODEX_BIN."
    )
    raise FileNotFoundError(f"{engine} CLI not found. {install_hint} ({env_hint})")


def _run_ai_engine(prompt, allow_write=False, timeout=300, engine_override="auto"):
    """Execute prompt via detected AI engine. Returns (stdout, stderr, returncode).

    Raises FileNotFoundError if no engine available.
    When auto-selected, falls back from Codex to Claude on Codex errors;
    an explicitly requested engine is not swapped.

    Acquires ``_engine_semaphore`` with a 5-second timeout first.
    """
    if not _engine_semaphore.acquire(timeout=5):
        raise TimeoutError(
            "AI engine busy — all 3 slots occupied. Please wait and retry."
        )
    try:
        return _run_ai_engine_unlocked(prompt, allow_write, timeout, engine_override)
    finally:
        _engine_semaphore.release()


def _run_ai_engine_unlocked(
    prompt, allow_write=False, timeout=300, engine_override="auto"
):
    """Unlocked inner implementation of _run_ai_engine (caller owns semaphore)."""
    engine_override = _normalize_ai_engine(engine_override)
    engine = engine_override if engine_override != "auto" else _detect_ai_engine()
    if engine == "codex":
        sandbox = "workspace-write" if allow_write else "read-only"
        codex_bin = _engine_executable("codex")
        stdout, stderr, rc = _run_ai_command(
            [
                codex_bin,
                "--sandbox",
                sandbox,
                "exec",
                "--skip-git-repo-check",
                prompt,
            ],
            timeout=timeout,
        )
        # Fallback: if codex failed and engine was auto-detected, try claude
        if rc != 0 and engine_override == "auto":
            print(f"Codex failed (rc={rc}), falling back to claude")
            engine = "claude"
        else:
            return stdout, stderr, rc
    if engine == "claude":
        claude_bin = _engine_executable("claude")
        return _run_ai_command(
            [claude_bin, "-p"],
            prompt_input=prompt,
            timeout=timeout,
        )
    raise FileNotFoundError(
        "No AI engine found. Install Codex (npm i -g @openai/codex) "
        "or Claude Code (npm i -g @anthropic-ai/claude-code)."
    )


def _run_ai_engine_stream(
    prompt,
    allow_write=False,
    timeout=300,
    engine_override="auto",
    proc_ref=None,
    for_twin=False,
    on_proc_start=None,
):
    """Execute prompt via detected AI engine, yielding SSE events as JSONL lines arrive.

    Yields dicts: {"type": "tool", "name": ..., "status": ...}
                  {"type": "text", "content": ...}
                  {"type": "done", "content": ...}
                  {"type": "error", "message": ...}

    Auto-falls back from codex to claude on codex errors (e.g. usage limits)
    only when the engine was auto-selected.

    Acquires ``_engine_semaphore`` with a 5-second timeout before spawning
    the subprocess. If ``for_twin=True``, also acquires ``_twin_semaphore``
    (max 1) to prevent overlapping twin analyses.

    Args:
        proc_ref: Optional mutable list (e.g. [None]) that receives the
            subprocess.Popen object once it is created. Used by callers that
            need to terminate the process from another thread.
        for_twin: If True, also acquires the twin-specific semaphore.
        on_proc_start: Optional callback invoked synchronously with the
            subprocess.Popen object the instant it is created (before the
            first blocking read). Lets callers register the process for
            cancellation without waiting for the first streamed event — which
            matters on the codex→claude fallback path, where the proc is only
            created after an initial text event is yielded.
        for_twin: If True, also acquires the twin-specific semaphore.
    """
    acquired_engine = False
    acquired_twin = False
    try:
        if for_twin and not _twin_semaphore.acquire(timeout=5):
            yield {
                "type": "error",
                "message": "A twin analysis is already running. Please wait or cancel it first.",
            }
            return
        acquired_twin = for_twin
        if not _engine_semaphore.acquire(timeout=5):
            yield {
                "type": "error",
                "message": "AI engine busy — all 3 slots occupied. Please wait and retry.",
            }
            return
        acquired_engine = True
        yield from _run_ai_engine_stream_impl(
            prompt, allow_write, timeout, engine_override, proc_ref, on_proc_start
        )
    finally:
        if acquired_twin:
            _twin_semaphore.release()
        if acquired_engine:
            _engine_semaphore.release()


def _analyze_codex_probe(stdout: str, returncode: int):
    """Inspect a Codex health-probe result.

    Returns ``(ok, message)``. ``ok`` is False when the probe surfaced an
    error event (e.g. ``unexpected status 521``, usage limits) or a non-zero
    exit code, in which case ``message`` carries a short human-readable reason.
    """
    if returncode not in (0, None):
        return False, f"codex exited with code {returncode}"
    for line in (stdout or "").strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if obj.get("type") in ("error", "turn.failed"):
            msg = (
                obj.get("message")
                or (obj.get("error") or {}).get("message")
                or "codex health check failed"
            )
            return False, str(msg)
    return True, ""


def _run_ai_engine_stream_impl(
    prompt,
    allow_write=False,
    timeout=300,
    engine_override="auto",
    proc_ref=None,
    on_proc_start=None,
):
    """Inner generator for _run_ai_engine_stream (caller owns semaphore)."""
    engine_override = _normalize_ai_engine(engine_override)
    engine = engine_override if engine_override != "auto" else _detect_ai_engine()
    if not engine:
        yield {"type": "error", "message": "No AI engine found"}
        return

    try:
        yield from _run_engine_stream_inner(
            engine, prompt, allow_write, timeout, proc_ref, on_proc_start
        )
    except FileNotFoundError as e:
        _clear_ai_engine_cache()
        evt = {"type": "error", "message": str(e)}
        if engine == "claude":
            evt["suggest_engine"] = "codex"
        elif engine == "codex":
            evt["suggest_engine"] = "claude"
        yield evt


def _run_engine_stream_inner(engine, prompt, allow_write, timeout, proc_ref=None,
                             on_proc_start=None):
    """Core streaming loop for a single engine. Yields event dicts.

    Args:
        proc_ref: Optional mutable list. If provided, proc_ref[0] is set to
            the subprocess.Popen object immediately after it is created.
        on_proc_start: Optional callback invoked with the Popen object the
            instant it is created (before the first blocking read).
    """
    if engine == "codex":
        sandbox = "workspace-write" if allow_write else "read-only"
        codex_bin = _engine_executable("codex")
        cmd = [
            codex_bin,
            "--sandbox",
            sandbox,
            "exec",
            "--json",
            "--skip-git-repo-check",
            prompt,
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            stdin=subprocess.DEVNULL,
            start_new_session=(os.name == "posix"),
        )
    else:  # claude
        claude_bin = _engine_executable("claude")
        cmd = [
            claude_bin,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--allowedTools",
            "Bash,Read,Grep,Glob,Write,Edit,Agent",
        ]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=(os.name == "posix"),
        )

        # Write prompt in a thread to avoid blocking on large prompts
        # (macOS pipe buffer is ~64KB, prompt can be 100KB+)
        def _feed_stdin():
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        threading.Thread(target=_feed_stdin, daemon=True).start()

    if proc_ref is not None:
        proc_ref[0] = proc
    if on_proc_start is not None:
        on_proc_start(proc)

    accumulated_text = ""
    stderr_tail = []
    stderr_thread = threading.Thread(
        target=_drain_text_pipe, args=(proc.stderr, stderr_tail), daemon=True
    )
    stderr_thread.start()
    try:
        import select as _select

        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                _kill_process_group(proc)
                yield {
                    "type": "timeout",
                    "content": accumulated_text,
                    "message": f"Timeout ({timeout // 60} min limit)",
                }
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
            _kill_process_group(proc)
        proc.wait()
        stderr_thread.join(timeout=1)

    if proc.returncode not in (0, None):
        stderr_text = "".join(stderr_tail).strip()
        detail = f": {stderr_text[:1000]}" if stderr_text else ""
        yield {
            "type": "error",
            "message": f"{engine} exited with code {proc.returncode}{detail}",
        }
        return

    # Auth-failure guard: Claude exits 0 even when not logged in.
    # Check accumulated text for known auth patterns before declaring success.
    if engine == "claude" and proc.returncode == 0:
        _auth_patterns = ("Not logged in", "authentication_failed", "Please run /login")
        if any(p in accumulated_text for p in _auth_patterns):
            _clear_ai_engine_cache()
            stderr_text = "".join(stderr_tail).strip()
            detail = f": {stderr_text[:500]}" if stderr_text else ""
            yield {
                "type": "error",
                "message": (
                    f"Claude is not authenticated.{detail}"
                    if detail
                    else "Claude is not authenticated. Please run /login in Claude Code."
                ),
            }
            return
        # Also check stderr for auth patterns
        stderr_text = "".join(stderr_tail)
        if any(p in stderr_text for p in _auth_patterns):
            _clear_ai_engine_cache()
            yield {
                "type": "error",
                "message": "Claude is not authenticated. Please run /login in Claude Code.",
            }
            return

    yield {"type": "done", "content": accumulated_text}


def _select_cognitive_avatar(force=False, run_id="", lang="zh", cache_only=False, engine="auto"):
    """Select cognitive avatar via AI. Returns selection dict or None.

    Checks evolve_cache for existing selection; if stale or missing, calls AI
    with traits + stripped cognitive_models.json to pick the best match.

    Args:
        cache_only: When True, never invoke the AI. Return a cached selection
            if present, otherwise None. Used by latency-sensitive GET handlers
            that must not block on a multi-minute AI call in the request thread.
    """
    from chatview import db as _db

    _db.init_db()

    CACHE_TAB = "twin_avatar"
    CACHE_SCOPE = {
        "source": "all",
        "date_range": "all",
        "project": run_id or "",
        "engine": "auto",
    }

    # Check if traits exist
    where = "status IN ('confirmed','emerging')"
    params = ()
    if run_id:
        where += " AND run_id=?"
        params = (run_id,)
    traits = _db.cm_get_all(
        "cognitive_traits", where=where, params=params, order="strength DESC", limit=15
    )
    if not traits:
        return None

    # Check freshness: compare traits updated_at vs cache updated_at
    if not force:
        cached = _db.evolve_get(CACHE_TAB, **CACHE_SCOPE)
        if cached:
            traits_max_updated = max(
                (t.get("updated_at") or "" for t in traits), default=""
            )
            if not traits_max_updated or cached["updated_at"] >= traits_max_updated:
                return cached["data"]

    # Cache-only callers must never trigger the (slow) AI selection below.
    if cache_only:
        return None

    # Load cognitive models JSON (stripped for prompt)
    models_path = (
        Path(__file__).resolve().parent.parent
        / "static"
        / "assets"
        / "cognitive-avatars"
        / "v2"
        / "cognitive_models.json"
    )
    try:
        with open(models_path, "r", encoding="utf-8") as f:
            models_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    compact_models = []
    for m in models_data.get("models", []):
        binding = m.get("avatar_binding", {})
        primary = binding.get("primary_visual_persona", {})
        compact_models.append(
            {
                "id": m["id"],
                "axis": m.get("axis", ""),
                "summary": m.get("summary", ""),
                "signals": m.get("signals", []),
                "thinking_mode": m.get("thinking_mode", []),
                "persona_id": primary.get("persona_id", ""),
            }
        )

    traits_json = json.dumps(
        [
            {
                "name": t.get("name", ""),
                "category": t.get("category", ""),
                "description": t.get("description", ""),
                "strength": t.get("strength", 0.65),
                "status": t.get("status", ""),
            }
            for t in traits
        ],
        ensure_ascii=False,
    )

    models_json = json.dumps(compact_models, ensure_ascii=False)

    if lang == "en":
        prompt = f"""You are a cognitive model matching expert. Based on the user's cognitive traits,
select the best match from 48 cognitive models.

## User Cognitive Traits

{traits_json}

## Available Cognitive Models (48)

{models_json}

## Task

Select the TOP 3 models that best match the user's cognitive traits. Consider:
- Alignment between classification axes and trait categories
- Semantic similarity between signals and user behavior descriptions
- Match degree between thinking_mode and user's thinking patterns

Also generate a **personalized type name** (persona_title) for the top-ranked model.
Do not copy the model name verbatim — instead, create a more fitting label based on the
user's trait combination (4-8 words, e.g. "Minimalist Architect", "Evidence-Driven Pragmatist").

## Output Format (JSON only, no other text)

{{"persona_title": "personalized type name", "selections": [{{"model_id": "cm_XXX", "confidence": 0.9, "rationale": "one-sentence rationale"}}, {{"model_id": "cm_XXX", "confidence": 0.7, "rationale": "one-sentence rationale"}}, {{"model_id": "cm_XXX", "confidence": 0.5, "rationale": "one-sentence rationale"}}]}}"""
    else:
        prompt = f"""你是一个认知模型匹配专家。根据用户的认知特质，从 48 个认知模型中选出最匹配的。

## 用户认知特质

{traits_json}

## 可选认知模型（48 个）

{models_json}

## 任务

选出最匹配用户认知特质的 TOP 3 模型。考虑：
- 分类轴与特质类别的对应关系
- signals 与用户行为描述的语义相似度
- thinking_mode 与用户思维模式的匹配度

同时为排名第一的模型生成一个**个性化的类型名称**（persona_title），不要照搬模型名，而是根据用户特质组合起一个更贴切的称呼（4-8个字，比如"极简架构师"、"证据驱动的实用派"）。

## 输出格式（仅输出 JSON，不要其他文字）

{{"persona_title": "个性化类型名称", "selections": [{{"model_id": "cm_XXX", "confidence": 0.9, "rationale": "一句话理由"}}, {{"model_id": "cm_XXX", "confidence": 0.7, "rationale": "一句话理由"}}, {{"model_id": "cm_XXX", "confidence": 0.5, "rationale": "一句话理由"}}]}}"""

    try:
        stdout, stderr, rc = _run_ai_engine(prompt, allow_write=False, timeout=120,
                                            engine_override=engine)
    except FileNotFoundError:
        return None

    if rc != 0 or not stdout:
        return None

    # Parse AI response — robust JSON extraction
    text = stdout.strip()

    def _extract_json(text: str) -> Optional[dict]:
        """Scan text for the first valid JSON object with expected keys."""
        depth = 0
        in_str = False
        escape = False
        start = -1
        for i, ch in enumerate(text):
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not escape:
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = text[start : i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict) and "selections" in obj:
                            return obj
                    except json.JSONDecodeError:
                        pass
                    start = -1
        return None

    result = _extract_json(text)
    if result is None:
        return None

    selections = result.get("selections", [])
    if not selections:
        return None

    # Validate primary model_id and look up full model info from original JSON
    primary = selections[0]
    model_id = primary.get("model_id", "")
    full_lookup = {m["id"]: m for m in models_data.get("models", [])}
    prompt_ids = {m["id"] for m in compact_models}
    if model_id not in prompt_ids or model_id not in full_lookup:
        return None

    full_model = full_lookup[model_id]
    persona_id = (
        full_model.get("avatar_binding", {})
        .get("primary_visual_persona", {})
        .get("persona_id", "")
    )
    selection = {
        "model_id": model_id,
        "model_name": full_model.get("name", ""),
        "persona_id": persona_id,
        "persona_name": full_model.get("avatar_binding", {})
        .get("primary_visual_persona", {})
        .get("persona_name", ""),
        "persona_title": result.get("persona_title", ""),
        "confidence": primary.get("confidence", 0),
        "rationale": primary.get("rationale", ""),
        "runner_up_ids": [
            s["model_id"] for s in selections[1:] if s.get("model_id") in prompt_ids
        ],
    }

    # Persist to evolve_cache
    _db.evolve_upsert(
        CACHE_TAB, **CACHE_SCOPE, data_json=json.dumps(selection, ensure_ascii=False)
    )
    return selection


def _codex_tool_event(item: dict, status: str):
    """Map a Codex non-command item into a normalized ``tool`` event.

    Brings Codex tool-event granularity closer to Claude's by recognizing
    file changes, web searches, and MCP tool calls in addition to Bash
    commands. Returns None for item types that carry no useful tool signal.
    """
    it = item.get("type", "")
    if it == "file_change":
        changes = item.get("changes") or []
        paths = []
        kind = "Edit"
        for ch in changes:
            if isinstance(ch, dict):
                if ch.get("path"):
                    paths.append(ch["path"])
                if ch.get("kind") in ("add", "create"):
                    kind = "Write"
        return {
            "type": "tool",
            "name": kind,
            "status": status,
            "detail": ", ".join(paths)[:200],
        }
    if it == "web_search":
        return {
            "type": "tool",
            "name": "WebSearch",
            "status": status,
            "detail": str(item.get("query", ""))[:200],
        }
    if it == "mcp_tool_call":
        server = item.get("server", "")
        tool = item.get("tool", "")
        detail = f"{server}.{tool}".strip(".")
        return {
            "type": "tool",
            "name": "MCP",
            "status": status,
            "detail": detail[:200],
        }
    return None


def _compact_json_payload(value, limit=200):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, (dict, list)):
                text = json.dumps(parsed, ensure_ascii=False)
        except (TypeError, ValueError):
            pass
    return text.replace("\n", " ")[:limit]


def _codex_function_call_event(payload: dict):
    name = payload.get("name", "") or "tool"
    raw_args = payload.get("arguments") or ""
    args = {}
    if isinstance(raw_args, str) and raw_args:
        try:
            args = json.loads(raw_args)
        except (TypeError, ValueError):
            args = {}
    if name == "exec_command":
        detail = args.get("cmd") if isinstance(args, dict) else raw_args
        return {
            "type": "tool",
            "name": "Bash",
            "status": "running",
            "detail": _compact_json_payload(detail),
        }
    if name in ("spawn_agent", "wait_agent"):
        if name == "wait_agent" and isinstance(args, dict):
            targets = args.get("targets") or []
            detail = f"wait_agent {len(targets)} agents"
        elif isinstance(args, dict):
            detail = f"{name} {args.get('agent_type', '')}: {args.get('message', '')}"
        else:
            detail = name
        return {
            "type": "tool",
            "name": "Agent",
            "status": "running",
            "detail": _compact_json_payload(detail),
        }
    return {
        "type": "tool",
        "name": "Tool",
        "status": "running",
        "detail": _compact_json_payload(name),
    }


def _codex_function_output_event(payload: dict):
    output = payload.get("output")
    if output is None:
        output = payload.get("content")
    detail = _compact_json_payload(output, limit=1200)
    name = "Tool"
    try:
        parsed = json.loads(output) if isinstance(output, str) else output
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, dict) and (
        "status" in parsed or "agent_id" in parsed or "nickname" in parsed
    ):
        name = "Agent"
    elif detail.startswith("Chunk ID:") or "Process exited with code" in detail:
        name = "Bash"
    return {
        "type": "tool",
        "name": name,
        "status": "done",
        "detail": detail,
    }


def _parse_stream_event(engine: str, line: str) -> dict:
    """Parse a JSONL line from Codex or Claude into a normalized event."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None

    if engine == "codex":
        evt_type = obj.get("type", "")
        if evt_type == "event_msg":
            payload = obj.get("payload") or {}
            payload_type = payload.get("type")
            if payload_type in ("agent_message", "reasoning"):
                text = payload.get("message") or payload.get("text") or payload.get("summary") or ""
                if text:
                    return {"type": "text", "content": text}
            if payload_type == "task_complete":
                text = payload.get("message") or payload.get("result") or payload.get("output") or ""
                if text:
                    return {"type": "text", "content": _compact_json_payload(text, limit=1200)}
        if evt_type == "response_item":
            payload = obj.get("payload") or {}
            payload_type = payload.get("type")
            if payload_type in ("function_call", "custom_tool_call"):
                return _codex_function_call_event(payload)
            if payload_type in ("function_call_output", "custom_tool_call_output"):
                return _codex_function_output_event(payload)
        # Tool execution started
        if evt_type == "item.started":
            item = obj.get("item", {})
            it = item.get("type")
            if it == "command_execution":
                cmd = item.get("command", "")
                # Clean up shell wrapper
                if cmd.startswith("/bin/"):
                    parts = cmd.split('"', 1)
                    cmd = parts[1].rstrip('"') if len(parts) > 1 else cmd
                return {
                    "type": "tool",
                    "name": "Bash",
                    "status": "running",
                    "detail": cmd[:200],
                }
            return _codex_tool_event(item, "running")
        # Tool execution completed
        elif evt_type == "item.completed":
            item = obj.get("item", {})
            it = item.get("type")
            if it == "command_execution":
                output = item.get("aggregated_output", "")
                return {
                    "type": "tool",
                    "name": "Bash",
                    "status": "done",
                    "detail": output or "",
                }
            elif it == "agent_message":
                text = item.get("text", "")
                if text:
                    return {"type": "text", "content": text}
            elif it == "reasoning":
                text = item.get("text", "") or item.get("summary", "")
                if text:
                    return {"type": "text", "content": text}
            else:
                return _codex_tool_event(item, "done")
        # Codex error / turn failed (e.g. usage limit)
        elif evt_type in ("error", "turn.failed"):
            msg = obj.get("message", "") or obj.get("error", {}).get("message", "")
            return {
                "type": "error",
                "message": f"codex: {msg}" if msg else "codex: unknown error",
            }
        # Turn completed (usage stats)
        elif evt_type == "turn.completed":
            usage = obj.get("usage", {})
            return {
                "type": "usage",
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }

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
                        events.append(
                            {"type": "text", "content": "\n".join(pending_text)}
                        )
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
                    event = {
                        "type": "tool",
                        "name": name,
                        "status": "running",
                        "detail": detail,
                        "_tool_use_id": blk.get("id", ""),
                    }
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
                    events.append(
                        {
                            "type": "tool",
                            "name": "",
                            "status": "done",
                            "detail": str(output),
                            "_tool_use_id": blk.get("tool_use_id", ""),
                        }
                    )
            return events if events else None
        # Final result
        elif evt_type == "result":
            # Check for explicit error flag (e.g. auth failure)
            if obj.get("is_error") or obj.get("error"):
                msg = obj.get("result", "") or obj.get("error", "")
                return {"type": "error", "message": f"claude: {msg}"}
            result_text = obj.get("result", "")
            if result_text:
                return {"type": "result", "content": result_text}

    return None
