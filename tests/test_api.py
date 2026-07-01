"""HTTP API smoke tests for server.py endpoints.

Starts the server in a background thread with a temp directory containing
a minimal JSONL session file, then exercises key API endpoints.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


# ---------------------------------------------------------------------------
# Minimal JSONL fixture
# ---------------------------------------------------------------------------


def _make_session_jsonl(session_id="test-api-sess-001"):
    """Return a list of JSONL dicts that form a valid session."""
    return [
        {"type": "ai-title", "aiTitle": "API Test Session", "sessionId": session_id},
        {
            "type": "user",
            "timestamp": "2026-06-10T10:00:00Z",
            "sessionId": session_id,
            "message": {
                "content": [{"type": "text", "text": "Hello from the API test"}]
            },
        },
        {
            "type": "assistant",
            "timestamp": "2026-06-10T10:01:00Z",
            "message": {
                "content": [{"type": "text", "text": "Hi, I can help with that."}]
            },
        },
    ]


def _make_codex_jsonl(
    session_id="019f-search-refresh-test", text="fresh codex search phrase"
):
    """Return JSONL dicts for a minimal Codex rollout session."""
    return [
        {
            "timestamp": "2026-06-10T11:00:00Z",
            "type": "session_meta",
            "payload": {"id": session_id, "cwd": str(Path.cwd())},
        },
        {
            "timestamp": "2026-06-10T11:00:01Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": text},
        },
    ]


# ---------------------------------------------------------------------------
# Test fixture: spin up a server on an ephemeral port
# ---------------------------------------------------------------------------


class APITestCase(unittest.TestCase):
    """Base class that boots the server with a temp projects dir."""

    @classmethod
    def setUpClass(cls):
        from chatview import index as _idx
        from chatview.db import core as _dbcore

        cls._tmpdir = tempfile.mkdtemp()

        # Create a fake projects dir with one session file
        proj_dir = os.path.join(cls._tmpdir, "projects", "test-proj")
        os.makedirs(proj_dir)
        session_file = os.path.join(proj_dir, "session.jsonl")
        with open(session_file, "w", encoding="utf-8") as f:
            for obj in _make_session_jsonl():
                f.write(json.dumps(obj) + "\n")

        # Save originals from the actual modules where they live
        cls._orig_projects_dir = _idx.PROJECTS_DIR
        cls._orig_cache_dir = _idx.CACHE_DIR
        cls._orig_index_cache = _idx.INDEX_CACHE
        cls._orig_codex_sessions = _idx.CODEX_SESSIONS_DIR
        cls._orig_codex_archived = _idx.CODEX_ARCHIVED_DIR
        cls._orig_index = _idx._index
        cls._orig_db_path = _dbcore.DB_PATH
        cls._orig_db_cache_dir = _dbcore.CACHE_DIR

        # Patch the actual chatview.index module globals
        _idx.PROJECTS_DIR = Path(cls._tmpdir) / "projects"
        _idx.CACHE_DIR = Path(cls._tmpdir) / ".cache"
        _idx.INDEX_CACHE = _idx.CACHE_DIR / "index.json"
        # Isolate Codex dirs to avoid scanning real user data
        _idx.CODEX_SESSIONS_DIR = Path(cls._tmpdir) / "codex_sessions"
        _idx.CODEX_ARCHIVED_DIR = Path(cls._tmpdir) / "codex_archived"
        # Patch the actual chatview.db.core module globals
        _dbcore.CACHE_DIR = Path(cls._tmpdir) / ".cache"
        _dbcore.DB_PATH = _dbcore.CACHE_DIR / "sessions.db"
        _dbcore._local = threading.local()

        # Build index with the temp data
        _idx._index = {"projects": {}, "sessions": {}, "_file_mtimes": {}}
        server.build_index(force=True)

        # Start server on port 0 (OS picks a free port)
        ThreadingHTTPServer.allow_reuse_address = True
        cls._server = ThreadingHTTPServer(("127.0.0.1", 0), server.ChatViewerHandler)
        cls._port = cls._server.server_address[1]
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

    def setUp(self):
        """Keep each test isolated while preserving the indexed session fixture."""
        from chatview import db as _db

        _db.init_db()
        conn = _db.get_conn()
        for table in (
            "evolve_cache",
            "evolve_run_events",
            "evolve_runs",
            "evidence_events",
            "judgment_cards",
            "card_relations",
            "cognitive_traits",
            "twin_checkpoints",
            "chat_cache",
        ):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        legacy_cache_dir = Path(self._tmpdir) / ".cache" / "evolve"
        if legacy_cache_dir.exists():
            for path in legacy_cache_dir.glob("*.json"):
                path.unlink()

    @classmethod
    def tearDownClass(cls):
        from chatview import index as _idx
        from chatview.db import core as _dbcore

        cls._server.shutdown()
        # Restore actual module globals
        _idx.PROJECTS_DIR = cls._orig_projects_dir
        _idx.CACHE_DIR = cls._orig_cache_dir
        _idx.INDEX_CACHE = cls._orig_index_cache
        _idx.CODEX_SESSIONS_DIR = cls._orig_codex_sessions
        _idx.CODEX_ARCHIVED_DIR = cls._orig_codex_archived
        _idx._index = cls._orig_index
        _dbcore.DB_PATH = cls._orig_db_path
        _dbcore.CACHE_DIR = cls._orig_db_cache_dir
        _dbcore._local = threading.local()
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _get(self, path):
        """GET helper; returns (status_code, parsed_json)."""
        url = f"http://127.0.0.1:{self._port}{path}"
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode("utf-8")) if e.fp else {}
            return e.code, body

    def _post(self, path, data, headers=None):
        """POST helper; returns (status_code, parsed_json_or_bytes)."""
        url = f"http://127.0.0.1:{self._port}{path}"
        body = json.dumps(data).encode("utf-8") if isinstance(data, dict) else data
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            raw = resp.read()
            try:
                return resp.status, json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return resp.status, raw
        except urllib.error.HTTPError as e:
            raw = e.read() if e.fp else b""
            try:
                return e.code, json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return e.code, raw


# ---------------------------------------------------------------------------
# Actual tests
# ---------------------------------------------------------------------------


class TestGetSessions(APITestCase):
    def test_returns_list(self):
        code, body = self._get("/api/sessions")
        self.assertEqual(code, 200)
        self.assertIsInstance(body, list)

    def test_sessions_have_expected_keys(self):
        code, body = self._get("/api/sessions")
        self.assertEqual(code, 200)
        if body:
            s = body[0]
            for key in ("id", "title", "project", "date", "source"):
                self.assertIn(key, s, f"Session missing key '{key}'")


class TestGetProjects(APITestCase):
    def test_returns_list(self):
        code, body = self._get("/api/projects")
        self.assertEqual(code, 200)
        self.assertIsInstance(body, list)


class TestSearch(APITestCase):
    def test_search_returns_list(self):
        code, body = self._get("/api/search?q=Hello")
        self.assertEqual(code, 200)
        self.assertIsInstance(body, list)

    def test_search_result_shape(self):
        code, body = self._get("/api/search?q=Hello")
        self.assertEqual(code, 200)
        if body:
            r = body[0]
            for key in ("sessionId", "title", "snippet", "matchType"):
                self.assertIn(key, r, f"Search result missing key '{key}'")

    def test_search_empty_query_returns_empty(self):
        """Empty or very short queries return empty list."""
        code, body = self._get("/api/search?q=")
        self.assertEqual(code, 200)
        self.assertEqual(body, [])

    def test_session_check_refreshes_stale_index_for_new_codex_session(self):
        code, before = self._get("/api/sessions/check")
        self.assertEqual(code, 200)

        from chatview import index as _idx

        os.makedirs(_idx.CODEX_SESSIONS_DIR, exist_ok=True)
        session_file = (
            _idx.CODEX_SESSIONS_DIR
            / "rollout-2026-06-10T11-00-00-019f-search-refresh-test.jsonl"
        )
        fresh_text = "fresh codex search phrase"
        with open(session_file, "w", encoding="utf-8") as f:
            for obj in _make_codex_jsonl(text=fresh_text):
                f.write(json.dumps(obj) + "\n")

        code, _ = self._get("/api/sessions/check")
        self.assertEqual(code, 200)

        deadline = time.time() + 5
        latest = before
        while time.time() < deadline:
            code, latest = self._get("/api/sessions/check")
            self.assertEqual(code, 200)
            if latest.get("count", 0) > before.get("count", 0):
                break
            time.sleep(0.05)
        self.assertGreater(latest.get("count", 0), before.get("count", 0))

        while time.time() < deadline:
            code, body = self._get("/api/search?q=fresh%20codex%20search%20phrase")
            self.assertEqual(code, 200)
            if any(fresh_text in result.get("snippet", "") for result in body):
                break
            time.sleep(0.05)
        self.assertTrue(
            any(fresh_text in result.get("snippet", "") for result in body),
            f"Expected session polling to refresh new Codex session, got {body}",
        )


class TestGetStats(APITestCase):
    def test_returns_dict(self):
        code, body = self._get("/api/stats")
        self.assertEqual(code, 200)
        self.assertIsInstance(body, dict)

    def test_stats_keys(self):
        code, body = self._get("/api/stats")
        self.assertEqual(code, 200)
        self.assertIn("totalSessions", body)
        self.assertIn("totalProjects", body)


class TestEvolveEngineSelection(APITestCase):
    def test_evolve_cache_falls_back_to_legacy_file_when_sqlite_empty(self):
        from chatview import db as _db

        legacy_dir = Path(self._tmpdir) / ".cache" / "evolve"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        with open(legacy_dir / "profile.legacy-test.json", "w", encoding="utf-8") as f:
            json.dump({"categories": [{"title": "Legacy profile"}]}, f)

        code, body = self._get(
            "/api/evolve/profile?source=all&date=7d&project=&engine=auto&lang=zh"
        )
        self.assertEqual(code, 200)
        self.assertEqual(body.get("categories"), [{"title": "Legacy profile"}])
        migrated = _db.evolve_get("profile", "all", "7d", "", "legacy")
        self.assertIsNotNone(migrated)
        self.assertEqual(
            migrated["data"].get("categories"), [{"title": "Legacy profile"}]
        )

    def test_evolve_cache_falls_back_to_latest_same_scope_across_engines(self):
        from chatview import db as _db

        _db.init_db()
        _db.evolve_upsert(
            "profile",
            "all",
            "7d",
            "",
            "claude",
            json.dumps({"categories": [{"title": "Claude only"}]}),
        )

        code, body = self._get(
            "/api/evolve/profile?source=all&date=7d&project=&engine=codex&lang=zh"
        )
        self.assertEqual(code, 200)
        self.assertEqual(body.get("categories"), [{"title": "Claude only"}])

    def test_evolve_cache_returns_exact_engine_match(self):
        from chatview import db as _db

        _db.init_db()
        _db.evolve_upsert(
            "profile",
            "all",
            "7d",
            "",
            "codex",
            json.dumps({"categories": [{"title": "Codex result"}]}),
        )

        code, body = self._get(
            "/api/evolve/profile?source=all&date=7d&project=&engine=codex&lang=zh"
        )
        self.assertEqual(code, 200)
        self.assertEqual(body.get("categories"), [{"title": "Codex result"}])

    def test_evolve_cache_prefers_exact_engine_over_shared_fallback(self):
        from chatview import db as _db

        _db.init_db()
        _db.evolve_upsert(
            "profile",
            "all",
            "7d",
            "",
            "auto",
            json.dumps({"categories": [{"title": "Shared auto result"}]}),
        )
        _db.evolve_upsert(
            "profile",
            "all",
            "7d",
            "",
            "claude",
            json.dumps({"categories": [{"title": "Exact claude result"}]}),
        )

        code, body = self._get(
            "/api/evolve/profile?source=all&date=7d&project=&engine=claude&lang=zh"
        )
        self.assertEqual(code, 200)
        self.assertEqual(body.get("categories"), [{"title": "Exact claude result"}])


class TestEvolveProgress(APITestCase):
    def test_progress_without_run_returns_null(self):
        code, body = self._get(
            "/api/evolve/progress?tab=profile&source=all&date=7d&project=&engine=auto"
        )
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertFalse(body["running"])
        self.assertIsNone(body["run"])

    def test_progress_returns_latest_exact_scope_run(self):
        from chatview import db as _db

        _db.init_db()
        run_id = _db.evolve_run_start(
            "profile",
            "all",
            "7d",
            "",
            "claude",
            lang="zh",
            snapshot={"text": "Analyzing profile...", "step_count": 2},
        )
        _db.evolve_run_update(
            run_id,
            status="failed",
            snapshot={
                "text": "Analyzing profile...",
                "step_count": 2,
                "error": "codex unavailable",
            },
            error_message="codex unavailable",
        )

        code, body = self._get(
            "/api/evolve/progress?tab=profile&source=all&date=7d&project=&engine=claude"
        )
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertFalse(body["running"])
        self.assertEqual(body["run"]["run_id"], run_id)
        self.assertEqual(body["run"]["status"], "failed")
        self.assertEqual(body["run"]["snapshot"]["step_count"], 2)
        self.assertEqual(body["run"]["error_message"], "codex unavailable")

    def test_progress_falls_back_to_latest_same_scope_run_across_engines(self):
        from chatview import db as _db

        _db.init_db()
        run_id = _db.evolve_run_start(
            "profile",
            "all",
            "7d",
            "",
            "auto",
            lang="zh",
            snapshot={"text": "Shared run", "step_count": 1},
        )
        _db.evolve_run_update(
            run_id,
            status="completed",
            snapshot={"text": "Shared run", "result": {"categories": []}},
        )

        code, body = self._get(
            "/api/evolve/progress?tab=profile&source=all&date=7d&project=&engine=claude"
        )
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["run"]["run_id"], run_id)
        self.assertEqual(body["run"]["engine"], "auto")

    def test_progress_without_tab_returns_scope_map(self):
        from chatview import db as _db

        _db.init_db()
        run_id = _db.evolve_run_start(
            "memory",
            "all",
            "7d",
            "",
            "auto",
            lang="zh",
            snapshot={"text": "Memory run"},
        )
        _db.evolve_run_update(
            run_id,
            status="completed",
            snapshot={"text": "Memory run", "result": {"nodes": [], "links": []}},
        )

        code, body = self._get(
            "/api/evolve/progress?source=all&date=7d&project=&engine=auto"
        )
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertIn("tabs", body)
        self.assertIn("memory", body["tabs"])
        self.assertEqual(body["tabs"]["memory"]["run"]["run_id"], run_id)
        self.assertEqual(body["tabs"]["memory"]["run"]["status"], "completed")

    def test_progress_returns_cache_and_marks_inactive_running_stale(self):
        from chatview import db as _db

        _db.init_db()
        _db.evolve_upsert(
            "memory",
            "all",
            "7d",
            "",
            "auto",
            json.dumps({"nodes": [{"id": "saved-memory"}], "links": []}),
        )
        run_id = _db.evolve_run_start(
            "memory",
            "all",
            "7d",
            "",
            "auto",
            lang="zh",
            snapshot={"text": "old in-flight memory run", "step_count": 1},
        )

        code, body = self._get(
            "/api/evolve/progress?source=all&date=7d&project=&engine=auto"
        )
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertIn("memory", body["tabs"])
        self.assertFalse(body["tabs"]["memory"]["running"])
        self.assertTrue(body["tabs"]["memory"]["stale"])
        self.assertEqual(body["tabs"]["memory"]["run"]["run_id"], run_id)
        self.assertEqual(
            body["tabs"]["memory"]["cache"]["data"]["nodes"],
            [{"id": "saved-memory"}],
        )

    def test_progress_returns_legacy_cache_when_sqlite_empty(self):
        from chatview import db as _db

        legacy_dir = Path(self._tmpdir) / ".cache" / "evolve"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        with open(legacy_dir / "memory.legacy-test.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "nodes": [{"id": "legacy-memory"}],
                    "links": [],
                    "cards": [{"id": "legacy-card"}],
                },
                f,
            )

        code, body = self._get(
            "/api/evolve/progress?source=all&date=7d&project=&engine=auto"
        )
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertIn("memory", body["tabs"])
        self.assertFalse(body["tabs"]["memory"]["running"])
        self.assertFalse(body["tabs"]["memory"]["stale"])
        self.assertIsNone(body["tabs"]["memory"]["run"])
        self.assertEqual(
            body["tabs"]["memory"]["cache"]["data"]["nodes"],
            [{"id": "legacy-memory"}],
        )
        migrated = _db.evolve_get("memory", "all", "7d", "", "legacy")
        self.assertIsNotNone(migrated)
        self.assertEqual(
            migrated["data"].get("nodes"),
            [{"id": "legacy-memory"}],
        )

    def test_run_events_endpoint_replays_events_after_since_index(self):
        from chatview import db as _db

        _db.init_db()
        run_id = _db.evolve_run_start(
            "memory",
            "all",
            "7d",
            "",
            "codex",
            lang="zh",
            snapshot={"text": "restoring", "step_count": 1},
        )
        _db.evolve_run_event_append(run_id, {"type": "run", "run_id": run_id})
        _db.evolve_run_event_append(
            run_id, {"type": "tool", "name": "Bash", "status": "running"}
        )
        _db.evolve_run_event_append(
            run_id, {"type": "text", "content": "partial answer"}
        )

        code, body = self._get(f"/api/evolve/run-events?run_id={run_id}&since=1")
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["run_id"], run_id)
        self.assertEqual(body["next_index"], 3)
        self.assertEqual(
            [event["event"]["type"] for event in body["events"]],
            ["tool", "text"],
        )
        self.assertEqual(body["events"][0]["event_index"], 2)

    def test_progress_includes_persisted_event_count_for_recovered_run(self):
        from chatview import db as _db

        _db.init_db()
        run_id = _db.evolve_run_start(
            "memory",
            "all",
            "7d",
            "",
            "codex",
            lang="zh",
            snapshot={"text": "restoring", "step_count": 1},
        )
        _db.evolve_run_event_append(run_id, {"type": "run", "run_id": run_id})
        _db.evolve_run_event_append(run_id, {"type": "text", "content": "hello"})

        code, body = self._get(
            "/api/evolve/progress?tab=memory&source=all&date=7d&project=&engine=codex"
        )
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["run"]["run_id"], run_id)
        self.assertEqual(body["event_count"], 2)


class TestEvolveCancel(APITestCase):
    def test_cancel_without_active_run_returns_error(self):
        code, body = self._post(
            "/api/evolve/cancel",
            {
                "tab": "profile",
                "scope": {
                    "source": "all",
                    "date": "7d",
                    "project": "",
                    "engine": "auto",
                },
            },
        )
        self.assertEqual(code, 200)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "No active analysis")

    def test_cancel_ignores_stale_running_row_without_active_backend_run(self):
        from chatview import db as _db
        from chatview.handlers import evolve as _evolve

        _db.init_db()
        run_id = _db.evolve_run_start(
            "profile",
            "all",
            "7d",
            "",
            "auto",
            lang="zh",
            snapshot={"text": "stale run"},
        )

        code, body = self._post(
            "/api/evolve/cancel",
            {
                "tab": "profile",
                "scope": {
                    "source": "all",
                    "date": "7d",
                    "project": "",
                    "engine": "auto",
                },
            },
        )
        self.assertEqual(code, 200)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "No active analysis")
        self.assertNotIn(run_id, _evolve._active_evolve_runs)


class TestEvolveRunLiveness(APITestCase):
    def test_starting_run_without_proc_is_temporarily_active(self):
        from chatview import db as _db
        from chatview.handlers import evolve as _evolve

        _db.init_db()
        run_id = _db.evolve_run_start(
            "profile",
            "all",
            "7d",
            "",
            "auto",
            lang="zh",
            snapshot={"text": "starting"},
        )
        _evolve._active_evolve_runs[run_id] = {
            "tab": "profile",
            "source": "all",
            "date": "7d",
            "project": "",
            "engine": "auto",
            "proc": None,
            "starting": True,
            "finalizing": False,
            "phase_started_at": time.time(),
        }

        run = _db.evolve_run_get(run_id)
        self.assertTrue(_evolve._is_evolve_run_active(run))

    def test_starting_run_without_proc_expires_to_stale(self):
        from chatview import db as _db
        from chatview.handlers import evolve as _evolve

        _db.init_db()
        run_id = _db.evolve_run_start(
            "profile",
            "all",
            "7d",
            "",
            "auto",
            lang="zh",
            snapshot={"text": "starting"},
        )
        _evolve._active_evolve_runs[run_id] = {
            "tab": "profile",
            "source": "all",
            "date": "7d",
            "project": "",
            "engine": "auto",
            "proc": None,
            "starting": True,
            "finalizing": False,
            "phase_started_at": time.time()
            - (_evolve._EVOLVE_STARTING_GRACE_SECONDS + 5),
        }

        run = _db.evolve_run_get(run_id)
        self.assertFalse(_evolve._is_evolve_run_active(run))

    def test_finalizing_run_without_proc_is_temporarily_active(self):
        from chatview import db as _db
        from chatview.handlers import evolve as _evolve

        _db.init_db()
        run_id = _db.evolve_run_start(
            "memory",
            "all",
            "7d",
            "",
            "auto",
            lang="zh",
            snapshot={"text": "finishing"},
        )
        _evolve._active_evolve_runs[run_id] = {
            "tab": "memory",
            "source": "all",
            "date": "7d",
            "project": "",
            "engine": "auto",
            "proc": None,
            "starting": False,
            "finalizing": True,
            "phase_started_at": time.time(),
        }

        run = _db.evolve_run_get(run_id)
        self.assertTrue(_evolve._is_evolve_run_active(run))


class TestGetSessionNotFound(APITestCase):
    def test_nonexistent_session_returns_404(self):
        code, body = self._get("/api/session/nonexistent-id-zzz-does-not-exist")
        self.assertEqual(code, 404)
        self.assertIn("error", body)


class TestPostChatOversized(APITestCase):
    def test_oversized_body_returns_413(self):
        # MAX_POST_BODY is 10 MB; send Content-Length exceeding that
        url = f"http://127.0.0.1:{self._port}/api/chat"
        req = urllib.request.Request(url, data=b"x", method="POST")
        req.add_header("Content-Type", "application/json")
        # Lie about content length to trigger the 413 check
        req.add_header("Content-Length", str(11 * 1024 * 1024))
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("Expected HTTPError 413")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 413)


class TestTwinResume(APITestCase):
    def test_empty_db_returns_ok_false(self):
        """When no twin data exists, resume returns ok=False with null run."""
        code, body = self._post("/api/twin/resume", {"lang": "en"})
        self.assertEqual(code, 200)
        self.assertFalse(body["ok"])
        self.assertIsNone(body["run"])

    def test_with_run_data_returns_run_info(self):
        """When twin data exists, resume returns latest run_id and stats."""
        from chatview import db as _db

        _db.init_db()
        run_id = "run_test_resume_001"
        # Insert an evidence event with known run_id
        _db.cm_upsert(
            "evidence_events",
            "ev_test_resume_001",
            {
                "run_id": run_id,
                "session_id": "sess-1",
                "event_index": 1,
                "signal_type": "correction",
                "signal_intensity": 0.8,
                "domain": "coding/test",
                "lesson": "test lesson",
            },
        )
        # Insert a judgment card with same run_id
        _db.cm_upsert(
            "judgment_cards",
            "jc_test_resume_001",
            {
                "run_id": run_id,
                "applies_when": "test scenario",
                "judgment": "test judgment",
                "confidence": 0.7,
                "status": "hypothesis",
            },
        )
        # Insert a trait with same run_id
        _db.cm_upsert(
            "cognitive_traits",
            "ct_test_resume_001",
            {
                "run_id": run_id,
                "name": "Test Trait",
                "category": "价值取向",
                "description": "test description",
                "strength": 0.8,
                "status": "emerging",
            },
        )
        for stage in range(1, 6):
            _db.save_checkpoint(run_id, stage, "completed")

        code, body = self._post("/api/twin/resume", {"lang": "en"})
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertIsNotNone(body["run"])
        self.assertEqual(body["run"]["run_id"], run_id)
        self.assertEqual(body["run"]["status"], "completed")
        self.assertEqual(body["run"]["stats"]["events"], 1)
        self.assertEqual(body["run"]["stats"]["cards"], 1)
        self.assertEqual(body["run"]["stats"]["traits"], 1)


class TestTwinCancel(APITestCase):
    def test_no_active_analysis_returns_error(self):
        """Cancel with no active analysis returns ok=False with error message."""
        code, body = self._post("/api/twin/cancel", {"run_id": "run_nonexistent"})
        self.assertEqual(code, 200)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "No active analysis")

    def test_cancel_without_run_id_works_when_no_active(self):
        """Cancel without run_id still returns no-active error cleanly."""
        code, body = self._post("/api/twin/cancel", {})
        self.assertEqual(code, 200)
        self.assertFalse(body["ok"])
        self.assertIn("error", body)


class TestTwinResumeCheckpointOnly(APITestCase):
    def test_checkpoint_only_interrupted_run_is_resumable(self):
        """A failed early-stage run with no extracted rows still appears in resume."""
        from chatview import db as _db

        _db.init_db()
        run_id = "run_checkpoint_only_resume"
        _db.save_checkpoint(run_id, 1, "failed")

        code, body = self._post("/api/twin/resume", {"lang": "en"})
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["run"]["run_id"], run_id)
        self.assertEqual(body["run"]["status"], "interrupted")
        self.assertEqual(body["run"]["stats"], {"events": 0, "cards": 0, "traits": 0})
        self.assertEqual(body["run"]["checkpoints"], {"1": "failed"})


# ---------------------------------------------------------------------------
# Tier-2: run_id run-scoping (twin views / sync / avatar scope to active run)
# ---------------------------------------------------------------------------


def _seed_event(run_id, eid, idx, created_at=None):
    from chatview import db as _db

    data = {
        "run_id": run_id,
        "session_id": "sess-scope",
        "event_index": idx,
        "signal_type": "correction",
        "signal_intensity": 0.8,
        "domain": "coding/test",
        "lesson": f"lesson {eid}",
    }
    if created_at is not None:
        data["created_at"] = created_at
    _db.cm_upsert("evidence_events", eid, data)


def _seed_card(run_id, cid, when, judgment, status="confirmed"):
    from chatview import db as _db

    _db.cm_upsert(
        "judgment_cards",
        cid,
        {
            "run_id": run_id,
            "applies_when": when,
            "judgment": judgment,
            "confidence": 0.7,
            "status": status,
        },
    )


def _seed_trait(run_id, tid, name, status="confirmed"):
    from chatview import db as _db

    _db.cm_upsert(
        "cognitive_traits",
        tid,
        {
            "run_id": run_id,
            "name": name,
            "category": "价值取向",
            "description": f"desc {tid}",
            "strength": 0.8,
            "status": status,
        },
    )


class TestTwinRunScopingReads(APITestCase):
    """run_id query param scopes cards/traits/events/overview/runtime-preview."""

    RUN_A = "run_scope_A"
    RUN_B = "run_scope_B"
    RUN_C = "run_scope_C"

    def setUp(self):
        super().setUp()
        from chatview import db as _db

        _db.init_db()
        # Run A: 2 of each. Run B: 1 of each. Totals = 3.
        _seed_card(self.RUN_A, "jc_a1", "when a1", "judge a1")
        _seed_card(self.RUN_A, "jc_a2", "when a2", "judge a2")
        _seed_card(self.RUN_B, "jc_b1", "when b1", "judge b1")
        _seed_trait(self.RUN_A, "ct_a1", "Trait A1")
        _seed_trait(self.RUN_A, "ct_a2", "Trait A2")
        _seed_trait(self.RUN_B, "ct_b1", "Trait B1")
        _seed_event(self.RUN_A, "ev_a1", 1)
        _seed_event(self.RUN_A, "ev_a2", 2)
        _seed_event(self.RUN_B, "ev_b1", 3)

    def test_cards_scoped_by_run_id(self):
        _, body = self._get(f"/api/twin/cards?run_id={self.RUN_A}")
        self.assertEqual(len(body["cards"]), 2)
        self.assertTrue(all(c["run_id"] == self.RUN_A for c in body["cards"]))
        _, allb = self._get("/api/twin/cards")
        self.assertEqual(len(allb["cards"]), 3)

    def test_traits_scoped_by_run_id(self):
        _, body = self._get(f"/api/twin/traits?run_id={self.RUN_A}")
        self.assertEqual(len(body["traits"]), 2)
        _, allb = self._get("/api/twin/traits")
        self.assertEqual(len(allb["traits"]), 3)

    def test_events_scoped_by_run_id(self):
        _, body = self._get(f"/api/twin/events?run_id={self.RUN_A}")
        self.assertEqual(len(body["events"]), 2)
        _, allb = self._get("/api/twin/events")
        self.assertEqual(len(allb["events"]), 3)

    def test_overview_counts_scoped_by_run_id(self):
        _, body = self._get(f"/api/twin/overview?run_id={self.RUN_A}")
        self.assertEqual(body["cards"]["count"], 2)
        self.assertEqual(body["traits"]["count"], 2)
        self.assertEqual(body["events"]["count"], 2)
        _, allb = self._get("/api/twin/overview")
        self.assertEqual(allb["cards"]["count"], 3)
        self.assertEqual(allb["traits"]["count"], 3)
        self.assertEqual(allb["events"]["count"], 3)

    def test_overview_without_run_id_prefers_latest_completed_run_when_available(self):
        from chatview import db as _db

        for stage in range(1, 6):
            _db.save_checkpoint(self.RUN_A, stage, "completed")
        for stage in range(1, 6):
            _db.save_checkpoint(self.RUN_C, stage, "completed")
        for stage in range(1, 3):
            _db.save_checkpoint(self.RUN_B, stage, "completed")
        _db.save_checkpoint(self.RUN_B, 3, "cancelled")

        _, body = self._get("/api/twin/overview")
        self.assertEqual(body["cards"]["count"], 2)
        self.assertEqual(body["traits"]["count"], 2)
        self.assertEqual(body["events"]["count"], 2)
        self.assertEqual(body["run_id"], self.RUN_A)

    def test_overview_without_run_id_can_fallback_to_partial_run_with_data(self):
        from chatview import db as _db

        for stage in range(1, 6):
            _db.save_checkpoint(self.RUN_C, stage, "completed")
        _db.save_checkpoint(self.RUN_B, 1, "completed")
        _db.save_checkpoint(self.RUN_B, 2, "cancelled")

        _, body = self._get("/api/twin/overview")
        self.assertEqual(body["cards"]["count"], 1)
        self.assertEqual(body["traits"]["count"], 1)
        self.assertEqual(body["events"]["count"], 1)
        self.assertEqual(body["run_id"], self.RUN_B)

    def test_twin_runs_default_limit_is_ten(self):
        from chatview import db as _db

        for i in range(12):
            _db.save_checkpoint(f"history_{i:02d}", 1, "completed")

        _, body = self._get("/api/twin/runs")
        self.assertEqual(len(body["runs"]), 10)

    def test_runtime_preview_scoped_by_run_id(self):
        _, body = self._get(f"/api/twin/runtime-preview?run_id={self.RUN_A}")
        self.assertEqual(body["card_count"], 2)
        self.assertEqual(body["trait_count"], 2)
        _, allb = self._get("/api/twin/runtime-preview")
        self.assertEqual(allb["card_count"], 3)
        self.assertEqual(allb["trait_count"], 3)

    def test_unknown_run_id_returns_empty_200(self):
        for ep in ("cards", "traits", "events"):
            code, body = self._get(f"/api/twin/{ep}?run_id=run_does_not_exist")
            self.assertEqual(code, 200)
            self.assertEqual(len(body[ep]), 0)
        code, ov = self._get("/api/twin/overview?run_id=run_does_not_exist")
        self.assertEqual(code, 200)
        self.assertEqual(ov["cards"]["count"], 0)

    def test_hostile_run_id_is_bound_param(self):
        import urllib.parse

        hostile = urllib.parse.quote("zzz' OR 1=1 --")
        code, body = self._get(f"/api/twin/cards?run_id={hostile}")
        self.assertEqual(code, 200)
        # Bound param => literal match => zero rows, NOT all rows, NOT a 500.
        self.assertEqual(len(body["cards"]), 0)


class TestTwinResumeLatestTrait(APITestCase):
    """resume must consider cognitive_traits.updated_at (no created_at column)."""

    RUN_OLD = "run_old_event"
    RUN_NEW = "run_new_trait"

    def setUp(self):
        super().setUp()
        from chatview import db as _db

        _db.init_db()
        # Old run: only an event, created long ago.
        _seed_event(self.RUN_OLD, "ev_old", 1, created_at="2020-01-01T00:00:00")
        # New run: only a trait (auto updated_at = now), no events/cards.
        _seed_trait(self.RUN_NEW, "ct_new", "Fresh Trait", status="emerging")

    def test_resume_picks_run_with_latest_trait(self):
        code, body = self._post("/api/twin/resume", {"lang": "en"})
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        # Buggy resume (MAX(created_at) on traits => NULL) would return RUN_OLD.
        self.assertEqual(body["run"]["run_id"], self.RUN_NEW)


class TestTwinAvatarScoping(APITestCase):
    """avatar-selection + overview avatar scope to run_id, no global fallback."""

    RUN_A = "run_av_A"
    RUN_B = "run_av_B"
    AVATAR = {"persona_id": "alpha", "model_id": "m1"}

    def setUp(self):
        super().setUp()
        from chatview import db as _db

        _db.init_db()
        _seed_trait(self.RUN_A, "ct_av_a1", "Av Trait A1", status="confirmed")
        _seed_trait(self.RUN_A, "ct_av_a2", "Av Trait A2", status="emerging")
        _seed_trait(self.RUN_B, "ct_av_b1", "Av Trait B1", status="confirmed")
        # Force traits old so the avatar cache (stamped now) is always fresher,
        # regardless of utcnow()/now() timezone skew between cm_upsert/evolve_upsert.
        conn = _db.get_conn()
        conn.execute("UPDATE cognitive_traits SET updated_at='2000-01-01T00:00:00'")
        conn.commit()
        # Avatar cache exists ONLY for run A (scope project=run_id).
        _db.evolve_upsert(
            "twin_avatar", "all", "all", self.RUN_A, "auto", json.dumps(self.AVATAR)
        )

    def test_avatar_selection_scoped_to_run(self):
        code, body = self._get(f"/api/twin/avatar-selection?run_id={self.RUN_A}")
        self.assertEqual(code, 200)
        self.assertEqual(body["persona_id"], "alpha")

    def test_avatar_selection_global_has_no_cache(self):
        # No run_id => project="" scope => no cache => 404 (not a cross-run leak).
        code, _ = self._get("/api/twin/avatar-selection")
        self.assertEqual(code, 404)

    def test_overview_avatar_scoped_to_run(self):
        _, a = self._get(f"/api/twin/overview?run_id={self.RUN_A}")
        self.assertIsNotNone(a["avatar_selection"])
        self.assertEqual(a["avatar_selection"]["persona_id"], "alpha")
        # Run B has no avatar cache and must NOT fall back to evolve_latest.
        _, b = self._get(f"/api/twin/overview?run_id={self.RUN_B}")
        self.assertIsNone(b["avatar_selection"])
        # No run_id may still use the global latest cache.
        _, g = self._get("/api/twin/overview")
        self.assertIsNotNone(g["avatar_selection"])


class TestTwinSyncScoping(APITestCase):
    """sync scopes to run_id AND never touches the real ~/.claude/CLAUDE.md."""

    RUN_A = "run_sync_A"
    RUN_B = "run_sync_B"

    def setUp(self):
        super().setUp()
        _seed_card(self.RUN_A, "jc_sync_a", "WHEN_ALPHA", "JUDGE_ALPHA")
        _seed_trait(self.RUN_A, "ct_sync_a", "TRAIT_ALPHA")
        _seed_card(self.RUN_B, "jc_sync_b", "WHEN_BETA", "JUDGE_BETA")
        _seed_trait(self.RUN_B, "ct_sync_b", "TRAIT_BETA")

    def test_sync_scoped_and_real_file_untouched(self):
        tmp_md = Path(self._tmpdir) / "synced_CLAUDE.md"
        real_md = Path.home() / ".claude" / "CLAUDE.md"
        before_exists = real_md.exists()
        before_content = real_md.read_text(encoding="utf-8") if before_exists else None

        os.environ["CHATVIEW_CLAUDE_MD"] = str(tmp_md)
        try:
            code, body = self._post(
                "/api/twin/sync", {"run_id": self.RUN_A, "lang": "en"}
            )
            self.assertEqual(code, 200)
            self.assertTrue(body["ok"])
            self.assertEqual(body["cards_synced"], 1)
            self.assertEqual(body["traits_synced"], 1)

            written = tmp_md.read_text(encoding="utf-8")
            self.assertIn("JUDGE_ALPHA", written)
            self.assertIn("TRAIT_ALPHA", written)
            self.assertNotIn("JUDGE_BETA", written)
            self.assertNotIn("TRAIT_BETA", written)
        finally:
            os.environ.pop("CHATVIEW_CLAUDE_MD", None)

        # Safety: the user's real global prefs file must be untouched.
        self.assertEqual(real_md.exists(), before_exists)
        if before_exists:
            self.assertEqual(real_md.read_text(encoding="utf-8"), before_content)


if __name__ == "__main__":
    unittest.main()
