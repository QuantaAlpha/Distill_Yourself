import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import analyze
import db


class TestValidateEvolveMechanism(unittest.TestCase):
    """Tests for the validation mechanism itself."""

    def test_unknown_tab_returns_error(self):
        ok, errors = analyze._validate_evolve_data("nonexistent", {})
        self.assertFalse(ok)
        self.assertEqual(len(errors), 1)
        self.assertIn("Unknown tab", errors[0])
        self.assertIn("nonexistent", errors[0])

    def test_non_dict_data_returns_error(self):
        ok, errors = analyze._validate_evolve_data("rules", ["not", "a", "dict"])
        self.assertFalse(ok)
        self.assertEqual(len(errors), 1)
        self.assertIn("JSON object", errors[0])

    def test_empty_dict_autofills_and_passes(self):
        # _validate_evolve_data auto-fills missing top-level fields with empty defaults
        data = {}
        ok, errors = analyze._validate_evolve_data("rules", data)
        self.assertTrue(ok)
        self.assertEqual(errors, [])
        # Side effect: auto-filled key should now exist
        self.assertIn("rules", data)


class TestValidateEvolveProfile(unittest.TestCase):
    """Tests for the 'profile' tab — the most complex schema."""

    def _make_valid_profile(self):
        return {
            "categories": [{"name": "Test", "items": [{"text": "item1"}]}],
            "radar": {"dimensions": [{"name": "skill", "score": 0.5}]},
        }

    def test_valid_minimal_profile_passes(self):
        ok, errors = analyze._validate_evolve_data("profile", self._make_valid_profile())
        self.assertTrue(ok, f"Expected valid, got errors: {errors}")
        self.assertEqual(errors, [])

    def test_category_missing_required_name_fails(self):
        data = {
            "categories": [{}],          # missing "name"
            "radar": {"dimensions": []},
        }
        ok, errors = analyze._validate_evolve_data("profile", data)
        self.assertFalse(ok)
        combined = " ".join(errors)
        self.assertIn("required", combined)

    def test_radar_score_out_of_range_fails(self):
        data = {
            "categories": [],
            "radar": {"dimensions": [{"name": "x", "score": 1.5}]},
        }
        ok, errors = analyze._validate_evolve_data("profile", data)
        self.assertFalse(ok)
        combined = " ".join(errors)
        self.assertIn("0.0-1.0", combined)


class TestValidateEvolveRules(unittest.TestCase):
    """Tests for the 'rules' tab — simplest schema."""

    def test_valid_rules_passes(self):
        data = {"rules": [{"id": "r1", "rule": "Do X"}]}
        ok, errors = analyze._validate_evolve_data("rules", data)
        self.assertTrue(ok, f"Expected valid, got errors: {errors}")
        self.assertEqual(errors, [])

    def test_rule_missing_required_id_fails(self):
        data = {"rules": [{"rule": "Do X"}]}   # missing "id"
        ok, errors = analyze._validate_evolve_data("rules", data)
        self.assertFalse(ok)
        combined = " ".join(errors)
        self.assertIn("required field missing", combined)


# ---------------------------------------------------------------------------
# Tests for _data_corrections and _data_errors
# ---------------------------------------------------------------------------

class _AnalyzeDBTestCase(unittest.TestCase):
    """Base that sets up a temp SQLite DB and isolates PROJECTS_DIR for analyze functions."""

    def setUp(self):
        import server as _server
        self._orig_db_path = db.DB_PATH
        self._orig_cache_dir = db.CACHE_DIR
        self._orig_projects_dir = _server.PROJECTS_DIR
        self._orig_index_cache = _server.INDEX_CACHE
        self._orig_server_cache_dir = _server.CACHE_DIR
        self._orig_codex_sessions = _server.CODEX_SESSIONS_DIR
        self._orig_codex_archived = _server.CODEX_ARCHIVED_DIR
        self._orig_codex_index = _server.CODEX_INDEX_FILE
        self._tmpdir = tempfile.mkdtemp()
        db.CACHE_DIR = Path(self._tmpdir)
        db.DB_PATH = Path(self._tmpdir) / "sessions.db"
        db._local = threading.local()
        db.init_db()
        # Point all dirs to empty temp dir so build_index finds nothing
        _server.PROJECTS_DIR = Path(self._tmpdir) / "projects"
        _server.PROJECTS_DIR.mkdir()
        _server.CACHE_DIR = Path(self._tmpdir) / ".cache"
        _server.INDEX_CACHE = _server.CACHE_DIR / "index.json"
        _server.CODEX_SESSIONS_DIR = Path(self._tmpdir) / "codex_sessions"
        _server.CODEX_ARCHIVED_DIR = Path(self._tmpdir) / "codex_archived"
        _server.CODEX_INDEX_FILE = Path(self._tmpdir) / "codex_index.jsonl"
        _server._index = {"projects": {}, "sessions": {}, "_file_mtimes": {}}

    def tearDown(self):
        import server as _server
        db.DB_PATH = self._orig_db_path
        db.CACHE_DIR = self._orig_cache_dir
        db._local = threading.local()
        _server.PROJECTS_DIR = self._orig_projects_dir
        _server.INDEX_CACHE = self._orig_index_cache
        _server.CACHE_DIR = self._orig_server_cache_dir
        _server.CODEX_SESSIONS_DIR = self._orig_codex_sessions
        _server.CODEX_ARCHIVED_DIR = self._orig_codex_archived
        _server.CODEX_INDEX_FILE = self._orig_codex_index
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @staticmethod
    def _default_args(**overrides):
        defaults = {"source": "all", "project": "", "date": "all",
                    "limit": 50, "json": False}
        defaults.update(overrides)
        return SimpleNamespace(**defaults)


class TestDataCorrectionsReturnsList(_AnalyzeDBTestCase):

    def test_empty_db_returns_empty_list(self):
        result = analyze._data_corrections(self._default_args())
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_with_session_returns_list(self):
        """Insert a session with a user correction signal; expect a non-empty list."""
        meta = {
            "id": "corr-sess-1", "title": "Corrections", "date": "2026-06-10",
            "lastDate": "2026-06-10", "filePath": "/tmp/corr.jsonl",
            "fileSize": 100, "_mtime": 1.0, "userMessageCount": 1,
            "preview": "", "project": "p", "projectName": "p", "source": "claude",
        }
        user_texts = [
            {"idx": 0, "text": "That's wrong, you missed the point", "ts": "2026-06-10T10:00:00Z"},
        ]
        asst_snippets = [
            {"idx": 1, "text": "I apologize for the mistake", "ts": "2026-06-10T10:01:00Z"},
        ]
        db.upsert_session(meta, user_texts, asst_snippets)

        result = analyze._data_corrections(self._default_args())
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0, "Should detect at least one correction signal")


class TestDataErrorsReturnsList(_AnalyzeDBTestCase):

    def test_empty_db_returns_empty_list(self):
        result = analyze._data_errors(self._default_args())
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
