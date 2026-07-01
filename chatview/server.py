"""HTTP server — routing, dispatch, and entry point.

Thin server that delegates all business logic to chatview submodules.
"""

import json
import os
import subprocess
import signal
import time
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path

from chatview.handlers.base import (
    _json_response,
    _error,
    _serve_file,
)
from chatview.handlers.data import (
    _get_projects,
    _get_sessions,
    _get_timeline,
    _get_stats,
    _get_analytics,
    _get_session_summary,
    _get_snippets,
    _get_file_evolution,
    _get_project_health,
)
from chatview.handlers.evolve import (
    _get_evolve_tab,
    _handle_evolve_stream,
    _handle_evolve_progress,
    _handle_evolve_run_events,
    _handle_evolve_cancel,
    _AI_TABS,
)
from chatview.handlers.chat import _handle_chat_stream, _handle_chat_legacy
from chatview.handlers.twin import (
    _handle_evolve_sync,
    _handle_twin_analyze,
    _handle_twin_sync,
    _handle_twin_resume,
    _handle_twin_cancel,
    _handle_twin_progress,
    _handle_twin_runs,
    _twin_run_info_for,
)
from chatview.index import (
    INDEX_CACHE,
    _cached,
    build_index,
    schedule_index_refresh_if_stale,
)
from chatview.session_loader import load_session
from chatview.search import search_sessions
from chatview.ai_engine import _select_cognitive_avatar
import chatview.db as _db

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
PORT = int(os.environ.get("PORT", 5757))


def _int_param(params, key, default, *, minimum=1, maximum=100000):
    """Parse a single query-string int with a safe fallback + clamp.

    parse_qs values are lists; an absent/empty/non-numeric value falls back to
    `default` instead of raising (which would otherwise surface as a 500)."""
    try:
        val = int(params.get(key, [str(default)])[0])
    except (ValueError, TypeError):
        val = default
    return max(minimum, min(val, maximum))


def _select_default_twin_overview_run_id():
    """Choose the best renderable run for the default Twin overview."""
    try:
        recent = _db.list_recent_run_ids(20)
    except Exception:
        recent = []

    candidates = []
    for index, entry in enumerate(recent):
        run_id = entry.get("run_id")
        if not run_id:
            continue
        try:
            info = _twin_run_info_for(run_id)
        except Exception:
            continue
        stats = info.get("stats") or {}
        total = (stats.get("events") or 0) + (stats.get("cards") or 0) + (stats.get("traits") or 0)
        if total <= 0:
            continue
        checkpoints = info.get("checkpoints") or {}
        if not checkpoints:
            continue
        completed_stages = sum(1 for status in checkpoints.values() if status == "completed")
        status = info.get("status") or ""
        if completed_stages >= 5:
            rank = 0
        elif status in ("partial", "interrupted") or completed_stages > 0:
            rank = 1
        else:
            rank = 2
        candidates.append((rank, index, run_id))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


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
                _error(self, 500, f"Internal server error: {type(e).__name__}")
            except Exception:
                pass

    def _do_GET_inner(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # API routes
        if path == "/api/projects":
            _json_response(self, _get_projects(self))
        elif path == "/api/sessions":
            project = params.get("project", [None])[0]
            _json_response(self, _get_sessions(self, project))
        elif path.startswith("/api/session/"):
            sid = path[len("/api/session/") :]
            data = load_session(sid)
            if data:
                _json_response(self, data)
            else:
                _error(self, 404, "Session not found")
        elif path == "/api/search":
            q = params.get("q", [""])[0]
            _json_response(self, search_sessions(q))
        elif path == "/api/timeline":
            _json_response(self, _get_timeline(self))
        elif path == "/api/analytics":
            _json_response(self, _cached("analytics", lambda: _get_analytics(self)))
        elif path == "/api/insights":
            _json_response(self, {"similar": [], "chain": [], "decisions": []})
        elif path == "/api/session-summary":
            sid = params.get("session", [None])[0]
            _json_response(
                self, _cached(f"summary:{sid}", lambda: _get_session_summary(self, sid))
            )
        elif path == "/api/snippets":
            _json_response(self, _cached("snippets", lambda: _get_snippets(self)))
        elif path == "/api/file-evolution":
            fp = params.get("file", [None])[0]
            _json_response(
                self, _cached(f"evolution:{fp}", lambda: _get_file_evolution(self, fp))
            )
        elif path == "/api/project-health":
            _json_response(self, _get_project_health(self))
        elif path == "/api/sessions/check":
            schedule_index_refresh_if_stale(reason="sessions-check", force_check=True)
            from chatview import index as _idx_mod

            with _idx_mod._index_lock:
                gen = _idx_mod._index_gen
                count = len(_idx_mod._index.get("sessions", {}))
            _json_response(self, {"gen": gen, "count": count})
        elif path == "/api/engines":
            engines = []
            for name, cmd in [
                ("claude", ["claude", "--version"]),
                ("codex", ["codex", "--version"]),
            ]:
                try:
                    result = subprocess.run(cmd, capture_output=True, timeout=5)
                    if result.returncode == 0:
                        engines.append(name)
                except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                    pass
            _json_response(
                self,
                {"engines": ["auto"] + engines, "default": "auto"},
            )
        elif path == "/api/refresh":
            build_index()
            _json_response(self, {"ok": True})
        elif path == "/api/stats":
            _json_response(self, _get_stats(self))
        elif path.startswith("/api/evolve/"):
            if path == "/api/evolve/progress":
                _handle_evolve_progress(self, params)
                return
            if path == "/api/evolve/run-events":
                _handle_evolve_run_events(self, params)
                return
            tab = path[len("/api/evolve/") :]
            if tab not in ("rules", "signals", "patterns", "profile", "memory"):
                _error(self, 400, "Invalid evolve tab")
            else:
                refresh = params.get("refresh", ["0"])[0] == "1"
                source = params.get("source", ["all"])[0]
                date = params.get("date", ["7d"])[0]
                project = params.get("project", [""])[0]
                engine = params.get("engine", ["auto"])[0]
                lang = params.get("lang", ["zh"])[0]
                try:
                    timeout = int(params.get("timeout", ["900"])[0])
                except (ValueError, TypeError):
                    timeout = 900
                timeout = max(60, min(timeout, 3600))
                stream = params.get("stream", ["0"])[0] == "1"
                if stream and tab in _AI_TABS:
                    _handle_evolve_stream(
                        self, tab, source, date, project, engine, lang, timeout
                    )
                else:
                    _json_response(
                        self,
                        _get_evolve_tab(
                            self,
                            tab,
                            refresh,
                            source,
                            date,
                            project,
                            engine,
                            lang,
                            timeout,
                        ),
                    )
        # --- Cognitive Handbook (Digital Twin) endpoints ---
        elif path == "/api/twin/stats":
            _json_response(self, _db.get_twin_stats())
        elif path == "/api/twin/progress":
            _handle_twin_progress(self)
        elif path == "/api/twin/runs":
            _handle_twin_runs(self)
        elif path == "/api/twin/overview":
            overview = {}
            requested_run_id = params.get("run_id", [None])[0]
            run_id = requested_run_id or _select_default_twin_overview_run_id()
            # When a run is explicit, or a completed run exists, scope to it.
            # Otherwise fall back to legacy global aggregation.
            _ow = ("run_id=?", (run_id,)) if run_id else ("", ())
            overview["run_id"] = run_id
            try:
                card_count = _db.cm_count("judgment_cards", where=_ow[0], params=_ow[1])
                card_items = _db.cm_get_all(
                    "judgment_cards",
                    where=_ow[0],
                    params=_ow[1],
                    order="confidence DESC",
                    limit=5,
                )
                overview["cards"] = {"count": card_count, "items": card_items}
            except Exception:
                overview["cards"] = {"count": 0, "items": []}
            try:
                trait_count = _db.cm_count(
                    "cognitive_traits", where=_ow[0], params=_ow[1]
                )
                trait_items = _db.cm_get_all(
                    "cognitive_traits",
                    where=_ow[0],
                    params=_ow[1],
                    order="strength DESC",
                    limit=50,
                )
                overview["traits"] = {"count": trait_count, "items": trait_items}
            except Exception:
                overview["traits"] = {"count": 0, "items": []}
            try:
                event_count = _db.cm_count(
                    "evidence_events", where=_ow[0], params=_ow[1]
                )
                event_items = _db.cm_get_all(
                    "evidence_events",
                    where=_ow[0],
                    params=_ow[1],
                    order="signal_intensity DESC, created_at DESC",
                    limit=3,
                )
                overview["events"] = {"count": event_count, "items": event_items}
            except Exception:
                overview["events"] = {"count": 0, "items": []}
            try:
                # run-scoped avatar matches the write scope used by
                # _select_cognitive_avatar (project=run_id); no global fallback.
                if run_id:
                    cached = _db.evolve_get("twin_avatar", "all", "all", run_id, "auto")
                else:
                    cached = _db.evolve_latest("twin_avatar")
                overview["avatar_selection"] = cached["data"] if cached else None
            except Exception:
                overview["avatar_selection"] = None
            _json_response(self, overview)
        elif path == "/api/twin/avatar-selection":
            _db.init_db()
            lang = params.get("lang", ["zh"])[0]
            run_id = params.get("run_id", [None])[0] or ""
            # GET 必须快速返回：只读缓存，绝不在请求线程内触发耗时 AI 选择
            # （AI 选择由 twin 分析的后台 SSE 流以 force=True 预先计算并写缓存）。
            selection = _select_cognitive_avatar(
                force=False, lang=lang, cache_only=True, run_id=run_id
            )
            if selection:
                _json_response(self, selection)
            else:
                _error(self, 404, "No traits available for avatar selection")
        elif path == "/api/twin/events":
            signal_type = params.get("signal_type", [None])[0]
            domain = params.get("domain", [None])[0]
            run_id = params.get("run_id", [None])[0]
            limit = _int_param(params, "limit", 200)
            where_parts, where_params = [], []
            if signal_type:
                where_parts.append("signal_type=?")
                where_params.append(signal_type)
            if domain:
                where_parts.append("domain LIKE ?")
                where_params.append(f"%{domain}%")
            if run_id:
                where_parts.append("run_id=?")
                where_params.append(run_id)
            where = " AND ".join(where_parts)
            items = _db.cm_get_all(
                "evidence_events",
                where=where,
                params=tuple(where_params),
                order="signal_intensity DESC, created_at DESC",
                limit=limit,
            )
            _json_response(self, {"events": items})
        elif path == "/api/twin/cards":
            status = params.get("status", [None])[0]
            tag = params.get("tag", [None])[0]
            sort = params.get("sort", ["confidence"])[0]
            run_id = params.get("run_id", [None])[0]
            limit = _int_param(params, "limit", 500)
            where_parts, where_params = [], []
            if status:
                where_parts.append("status=?")
                where_params.append(status)
            if tag:
                where_parts.append("tags LIKE ?")
                where_params.append(f"%{tag}%")
            if run_id:
                where_parts.append("run_id=?")
                where_params.append(run_id)
            where = " AND ".join(where_parts)
            order = "confidence DESC" if sort == "confidence" else "updated_at DESC"
            items = _db.cm_get_all(
                "judgment_cards",
                where=where,
                params=tuple(where_params),
                order=order,
                limit=limit,
            )
            _json_response(self, {"cards": items})
        elif path == "/api/twin/traits":
            status = params.get("status", [None])[0]
            category = params.get("category", [None])[0]
            run_id = params.get("run_id", [None])[0]
            limit = _int_param(params, "limit", 500)
            where_parts, where_params = [], []
            if status:
                where_parts.append("status=?")
                where_params.append(status)
            if category:
                where_parts.append("category=?")
                where_params.append(category)
            if run_id:
                where_parts.append("run_id=?")
                where_params.append(run_id)
            where = " AND ".join(where_parts)
            items = _db.cm_get_all(
                "cognitive_traits",
                where=where,
                params=tuple(where_params),
                order="strength DESC",
                limit=limit,
            )
            _json_response(self, {"traits": items})
        elif path.startswith("/api/twin/card/"):
            card_id = path[len("/api/twin/card/") :]
            card = _db.cm_get("judgment_cards", card_id)
            if card is None:
                _error(self, 404, "Card not found")
            else:
                evidence = _db.cm_get_evidence_for_card(card_id)
                relations = _db.cm_get_card_relations(card_id)
                _json_response(
                    self, {"card": card, "evidence": evidence, "relations": relations}
                )
        elif path.startswith("/api/twin/trait/"):
            trait_id = path[len("/api/twin/trait/") :]
            trait = _db.cm_get("cognitive_traits", trait_id)
            if trait is None:
                _error(self, 404, "Trait not found")
            else:
                card_ids = []
                try:
                    card_ids = json.loads(trait.get("supporting_card_ids") or "[]")
                except (json.JSONDecodeError, TypeError):
                    pass
                cards = [_db.cm_get("judgment_cards", cid) for cid in card_ids if cid]
                cards = [c for c in cards if c]
                _json_response(self, {"trait": trait, "supporting_cards": cards})
        elif path == "/api/twin/runtime-preview":
            lang = params.get("lang", ["zh"])[0]
            run_id = params.get("run_id", [None])[0]
            rp_where = "status IN ('confirmed','emerging')"
            rp_params = ()
            if run_id:
                rp_where += " AND run_id=?"
                rp_params = (run_id,)
            cards = _db.cm_get_all(
                "judgment_cards",
                where=rp_where,
                params=rp_params,
                order="confidence DESC",
                limit=25,
            )
            traits = _db.cm_get_all(
                "cognitive_traits",
                where=rp_where,
                params=rp_params,
                order="strength DESC",
                limit=15,
            )
            if lang == "en":
                traits_header = "## About This User\n"
                cards_header = "\n## Situational Judgments\n"
                exception_label = "Exception: "
            else:
                traits_header = "## 关于这位用户\n"
                cards_header = "\n## 场景判断\n"
                exception_label = "例外："
            lines = []
            if traits:
                lines.append(traits_header)
                for t in traits:
                    lines.append(
                        f"**{t.get('name', '')}**。{t.get('description', '')}\n"
                    )
            if cards:
                lines.append(cards_header)
                for c in cards:
                    when = c.get("applies_when") or ""
                    judgment = c.get("judgment") or ""
                    action = c.get("agent_action") or ""
                    exceptions = c.get("exceptions") or ""
                    lines.append(f"**{when}**：{judgment}")
                    if action:
                        lines.append(f"→ {action}")
                    if exceptions:
                        lines.append(f"{exception_label}{exceptions}")
                    lines.append("")
            _json_response(
                self,
                {
                    "text": "\n".join(lines),
                    "card_count": len(cards),
                    "trait_count": len(traits),
                },
            )
        else:
            # Serve static files (with path traversal protection)
            if path == "/":
                path = "/index.html"
            file_path = (STATIC_DIR / path.lstrip("/")).resolve()
            try:
                file_path.relative_to(STATIC_DIR.resolve())
            except ValueError:
                _error(self, 403, "Forbidden")
                return
            if file_path.exists() and file_path.is_file():
                _serve_file(self, file_path)
            else:
                _error(self, 404, "Not found")

    def do_POST(self):
        try:
            self._do_POST_inner()
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                _error(self, 500, f"Internal server error: {type(e).__name__}")
            except Exception:
                pass

    def do_DELETE(self):
        try:
            self._do_DELETE_inner()
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                _error(self, 500, f"Internal server error: {type(e).__name__}")
            except Exception:
                pass

    def _do_POST_inner(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/chat/stream":
            _handle_chat_stream(self)
        elif parsed.path == "/api/chat":
            _handle_chat_legacy(self)
        elif parsed.path == "/api/evolve/sync":
            _handle_evolve_sync(self)
        elif parsed.path == "/api/evolve/cancel":
            from chatview.handlers.base import _read_post_body

            raw = _read_post_body(self)
            if raw is None:
                return
            _handle_evolve_cancel(self, raw)
        elif parsed.path == "/api/twin/analyze":
            _handle_twin_analyze(self)
        elif parsed.path == "/api/twin/resume":
            _handle_twin_resume(self)
        elif parsed.path == "/api/twin/cancel":
            _handle_twin_cancel(self)
        elif parsed.path == "/api/twin/sync":
            _handle_twin_sync(self)
        elif parsed.path == "/api/session/rename":
            from chatview.handlers.base import _read_post_body
            from chatview import db as _db

            raw = _read_post_body(self)
            if raw is None:
                return  # _read_post_body already sent error
            try:
                body = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                _error(self, 400, "Invalid JSON")
                return
            sid = body.get("id", "") if isinstance(body, dict) else ""
            title = body.get("title", "") if isinstance(body, dict) else ""
            if not isinstance(sid, str) or not isinstance(title, str):
                _error(self, 400, "id and title must be strings")
                return
            title = title.strip()
            if not sid or not title:
                _error(self, 400, "Missing id or title")
                return
            if not _db.rename_session(sid, title):
                _error(self, 404, "Session not found")
                return
            # Update in-memory index
            from chatview import index as _idx

            with _idx._index_lock:
                sessions = _idx._index.get("sessions", {})
                if sid in sessions:
                    sessions[sid]["title"] = title
                _idx._index_gen += 1
            _json_response(self, {"ok": True})
        elif parsed.path.startswith("/api/session/") and parsed.path.endswith("/star"):
            sid = parsed.path[len("/api/session/") : -len("/star")]
            import chatview.db as _db

            conn = _db.get_conn()
            row = conn.execute(
                "SELECT starred FROM sessions WHERE id=?", (sid,)
            ).fetchone()
            if row is None:
                _error(self, 404, "Session not found")
            else:
                new_val = 0 if row["starred"] else 1
                conn.execute("UPDATE sessions SET starred=? WHERE id=?", (new_val, sid))
                conn.commit()
                _json_response(self, {"ok": True, "starred": bool(new_val)})
        else:
            _error(self, 404, "Not found")

    def _do_DELETE_inner(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/session/"):
            sid = path[len("/api/session/") :]
            from chatview.handlers.data import _delete_session

            result = _delete_session(sid)
            if result.get("ok"):
                _json_response(self, result)
            else:
                _error(self, 404, result.get("error", "Not found"))
        else:
            _error(self, 404, "Not found")

    def log_message(self, format, *args):
        """Suppress default request logging for cleaner output."""
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _cmdline_matches(pid: int) -> bool:
    """Check if process PID's command line contains 'chatview' or 'server.py'.

    Uses psutil if available; otherwise falls back to /proc/<pid>/cmdline on
    Linux or 'ps -p <pid> -o command=' on macOS/BSD.
    """
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return False
    try:
        import psutil

        try:
            proc = psutil.Process(pid_int)
            cmdline = " ".join(proc.cmdline())
            return "chatview" in cmdline or "server.py" in cmdline
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
    except ImportError:
        pass
    # Fallback: read /proc/<pid>/cmdline (Linux)
    try:
        with open(f"/proc/{pid_int}/cmdline", "rb") as f:
            raw = f.read()
        cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace")
        return "chatview" in cmdline or "server.py" in cmdline
    except (FileNotFoundError, PermissionError, OSError):
        pass
    # Fallback: ps -p <pid> -o command= (macOS / BSD)
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid_int), "-o", "command="],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        return "chatview" in out or "server.py" in out
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        OSError,
    ):
        pass
    # If we cannot determine the command line, be safe: do NOT kill
    return False


def _kill_existing(port: int) -> None:
    """Kill any process already listening on the port whose command line matches.

    Only terminates processes whose command line contains 'chatview' or
    'server.py' to avoid killing unrelated processes on the same port.
    """
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f":{port}"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        if out:
            for pid in out.split("\n"):
                pid = pid.strip()
                if pid and pid != str(os.getpid()) and _cmdline_matches(pid):
                    os.kill(int(pid), signal.SIGTERM)
            time.sleep(0.3)
            print(f"  Killed old process on port {port}")
    except (subprocess.CalledProcessError, OSError):
        pass


def main():
    print("Claude Chat Viewer")

    _kill_existing(PORT)

    # Load cached index synchronously (fast -- just JSON read)
    from chatview import index as _idx

    if INDEX_CACHE.exists():
        try:
            with open(INDEX_CACHE) as f:
                cached = json.load(f)
            with _idx._index_lock:
                _idx._index = cached
                _idx._index_gen += 1
            sessions_n = len(cached.get("sessions", {}))
            print(f"Loaded {sessions_n} sessions from cache")
        except Exception as e:
            print(f"Cache load error: {e}")

    # Start server immediately so it can serve from cache
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", PORT), ChatViewerHandler)
    print(f"\n  → http://localhost:{PORT}\n")

    # Build/refresh index in background
    def _bg_index():
        _idx._index_refresh_running = True
        _idx._index_refresh_worker("startup")
        while True:
            time.sleep(_idx.INDEX_STALE_CHECK_INTERVAL)
            _idx.schedule_index_refresh_if_stale(reason="background")

    threading.Thread(target=_bg_index, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
