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
import db


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
            "message": {"content": [{"type": "text", "text": "Hello from the API test"}]},
        },
        {
            "type": "assistant",
            "timestamp": "2026-06-10T10:01:00Z",
            "message": {"content": [{"type": "text", "text": "Hi, I can help with that."}]},
        },
    ]


# ---------------------------------------------------------------------------
# Test fixture: spin up a server on an ephemeral port
# ---------------------------------------------------------------------------

class APITestCase(unittest.TestCase):
    """Base class that boots the server with a temp projects dir."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp()

        # Create a fake projects dir with one session file
        proj_dir = os.path.join(cls._tmpdir, "projects", "test-proj")
        os.makedirs(proj_dir)
        session_file = os.path.join(proj_dir, "session.jsonl")
        with open(session_file, "w", encoding="utf-8") as f:
            for obj in _make_session_jsonl():
                f.write(json.dumps(obj) + "\n")

        # Monkey-patch server globals to point at temp dir
        cls._orig_projects_dir = server.PROJECTS_DIR
        cls._orig_cache_dir = server.CACHE_DIR
        cls._orig_index_cache = server.INDEX_CACHE
        cls._orig_db_path = db.DB_PATH
        cls._orig_db_cache_dir = db.CACHE_DIR

        server.PROJECTS_DIR = Path(cls._tmpdir) / "projects"
        server.CACHE_DIR = Path(cls._tmpdir) / ".cache"
        server.INDEX_CACHE = server.CACHE_DIR / "index.json"
        db.CACHE_DIR = Path(cls._tmpdir) / ".cache"
        db.DB_PATH = db.CACHE_DIR / "sessions.db"
        db._local = threading.local()

        # Build index with the temp data
        server._index = {"projects": {}, "sessions": {}, "_file_mtimes": {}}
        server.build_index(force=True)

        # Start server on port 0 (OS picks a free port)
        ThreadingHTTPServer.allow_reuse_address = True
        cls._server = ThreadingHTTPServer(("127.0.0.1", 0), server.ChatViewerHandler)
        cls._port = cls._server.server_address[1]
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        # Restore
        server.PROJECTS_DIR = cls._orig_projects_dir
        server.CACHE_DIR = cls._orig_cache_dir
        server.INDEX_CACHE = cls._orig_index_cache
        db.DB_PATH = cls._orig_db_path
        db.CACHE_DIR = cls._orig_db_cache_dir
        db._local = threading.local()
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


if __name__ == "__main__":
    unittest.main()
