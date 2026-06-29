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
    _json_response, _error, _serve_file, _start_sse, _sse_event,
    _read_post_body, log_message,
)
from chatview.handlers.data import (
    _get_projects, _get_sessions, _get_timeline, _get_stats,
    _get_analytics, _get_session_summary, _get_snippets,
    _get_file_evolution, _get_project_health,
)
from chatview.handlers.evolve import (
    _get_evolve_tab, _handle_evolve_stream, _AI_TABS,
)
from chatview.handlers.chat import _handle_chat_stream, _handle_chat_legacy
from chatview.handlers.twin import (
    _handle_evolve_sync, _handle_twin_analyze, _handle_twin_sync,
)
from chatview.index import (
    PROJECTS_DIR, CACHE_DIR, INDEX_CACHE,
    INDEX_STALE_CHECK_INTERVAL,
    _cached,
    _index_refresh_lock, _index_refresh_running,
    build_index, schedule_index_refresh_if_stale,
    _index_refresh_worker,
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
            sid = path[len("/api/session/"):]
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
            _json_response(self, _cached(f"summary:{sid}", lambda: _get_session_summary(self, sid)))
        elif path == "/api/snippets":
            _json_response(self, _cached("snippets", lambda: _get_snippets(self)))
        elif path == "/api/file-evolution":
            fp = params.get("file", [None])[0]
            _json_response(self, _cached(f"evolution:{fp}", lambda: _get_file_evolution(self, fp)))
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
            for name, cmd in [("claude", ["claude", "--version"]), ("codex", ["codex", "--version"])]:
                try:
                    result = subprocess.run(cmd, capture_output=True, timeout=5)
                    if result.returncode == 0:
                        engines.append(name)
                except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                    pass
            _json_response(self, {"engines": engines, "default": engines[0] if engines else "claude"})
        elif path == "/api/refresh":
            build_index()
            _json_response(self, {"ok": True})
        elif path == "/api/stats":
            _json_response(self, _get_stats(self))
        elif path.startswith("/api/evolve/"):
            tab = path[len("/api/evolve/"):]
            if tab not in ("rules", "signals", "patterns", "profile", "memory"):
                _error(self, 400, "Invalid evolve tab")
            else:
                refresh = params.get("refresh", ["0"])[0] == "1"
                source = params.get("source", ["all"])[0]
                date = params.get("date", ["7d"])[0]
                project = params.get("project", [""])[0]
                engine = params.get("engine", ["auto"])[0]
                lang = params.get("lang", ["zh"])[0]
                stream = params.get("stream", ["0"])[0] == "1"
                if stream and tab in _AI_TABS:
                    _handle_evolve_stream(self, tab, source, date, project, engine, lang)
                else:
                    _json_response(self, _get_evolve_tab(self, tab, refresh, source, date, project, engine, lang))
        # --- Cognitive Handbook (Digital Twin) endpoints ---
        elif path == "/api/twin/stats":
            _json_response(self, _db.get_twin_stats())
        elif path == "/api/twin/overview":
            overview = {}
            try:
                card_count = _db.cm_count("judgment_cards")
                card_items = _db.cm_get_all("judgment_cards", order="confidence DESC", limit=5)
                overview["cards"] = {"count": card_count, "items": card_items}
            except Exception:
                overview["cards"] = {"count": 0, "items": []}
            try:
                trait_count = _db.cm_count("cognitive_traits")
                trait_items = _db.cm_get_all("cognitive_traits", order="strength DESC", limit=50)
                overview["traits"] = {"count": trait_count, "items": trait_items}
            except Exception:
                overview["traits"] = {"count": 0, "items": []}
            try:
                event_count = _db.cm_count("evidence_events")
                event_items = _db.cm_get_all("evidence_events",
                                             order="signal_intensity DESC, created_at DESC", limit=3)
                overview["events"] = {"count": event_count, "items": event_items}
            except Exception:
                overview["events"] = {"count": 0, "items": []}
            try:
                cached = _db.evolve_latest("twin_avatar")
                overview["avatar_selection"] = cached["data"] if cached else None
            except Exception:
                overview["avatar_selection"] = None
            _json_response(self, overview)
        elif path == "/api/twin/avatar-selection":
            _db.init_db()
            selection = _select_cognitive_avatar(force=False)
            if selection:
                _json_response(self, selection)
            else:
                _error(self, 404, "No traits available for avatar selection")
        elif path == "/api/twin/events":
            signal_type = params.get("signal_type", [None])[0]
            domain = params.get("domain", [None])[0]
            limit = int(params.get("limit", ["200"])[0])
            where_parts, where_params = [], []
            if signal_type:
                where_parts.append("signal_type=?")
                where_params.append(signal_type)
            if domain:
                where_parts.append("domain LIKE ?")
                where_params.append(f"%{domain}%")
            where = " AND ".join(where_parts)
            items = _db.cm_get_all("evidence_events", where=where,
                                   params=tuple(where_params),
                                   order="signal_intensity DESC, created_at DESC", limit=limit)
            _json_response(self, {"events": items})
        elif path == "/api/twin/cards":
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
            _json_response(self, {"cards": items})
        elif path == "/api/twin/traits":
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
            _json_response(self, {"traits": items})
        elif path.startswith("/api/twin/card/"):
            card_id = path[len("/api/twin/card/"):]
            card = _db.cm_get("judgment_cards", card_id)
            if card is None:
                _error(self, 404, "Card not found")
            else:
                evidence = _db.cm_get_evidence_for_card(card_id)
                relations = _db.cm_get_card_relations(card_id)
                _json_response(self, {"card": card, "evidence": evidence, "relations": relations})
        elif path.startswith("/api/twin/trait/"):
            trait_id = path[len("/api/twin/trait/"):]
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
            cards = _db.cm_get_all("judgment_cards",
                                   where="status IN ('confirmed','emerging')",
                                   order="confidence DESC", limit=25)
            traits = _db.cm_get_all("cognitive_traits",
                                    where="status IN ('confirmed','emerging')",
                                    order="strength DESC", limit=15)
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
            _json_response(self, {
                "text": "\n".join(lines),
                "card_count": len(cards),
                "trait_count": len(traits),
            })
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

    def _do_POST_inner(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/chat/stream":
            _handle_chat_stream(self)
        elif parsed.path == "/api/chat":
            _handle_chat_legacy(self)
        elif parsed.path == "/api/evolve/sync":
            _handle_evolve_sync(self)
        elif parsed.path == "/api/twin/analyze":
            _handle_twin_analyze(self)
        elif parsed.path == "/api/twin/sync":
            _handle_twin_sync(self)
        else:
            _error(self, 404, "Not found")

    def log_message(self, format, *args):
        """Suppress default request logging for cleaner output."""
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _kill_existing(port):
    """Kill any process already listening on the port."""
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
