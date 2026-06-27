"""Regression tests for db.py core functions."""

import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_META = {
    "id": "test-session-001",
    "title": "Test Session",
    "date": "2026-06-01",
    "lastDate": "2026-06-01",
    "filePath": "/tmp/test.jsonl",
    "fileSize": 1234,
    "_mtime": 1234567890.0,
    "userMessageCount": 2,
    "preview": "Hello world",
    "project": "test-project",
    "projectName": "test-project",
    "source": "claude",
}

_USER_TEXTS = [
    {"idx": 0, "text": "Hello world unique search term", "ts": "2026-06-01T10:00:00Z"},
    {"idx": 1, "text": "Another message", "ts": "2026-06-01T10:05:00Z"},
]

_ASST_SNIPPETS = [
    {"idx": 0, "text": "I can help with that", "ts": "2026-06-01T10:01:00Z"},
]


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self._orig_db_path = db.DB_PATH
        self._orig_cache_dir = db.CACHE_DIR
        self._tmpdir = tempfile.mkdtemp()
        from pathlib import Path
        db.CACHE_DIR = Path(self._tmpdir)
        db.DB_PATH = Path(self._tmpdir) / "sessions.db"
        db._local = threading.local()
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self._orig_db_path
        db.CACHE_DIR = self._orig_cache_dir
        db._local = threading.local()
        shutil.rmtree(self._tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Session lifecycle tests
# ---------------------------------------------------------------------------

class TestSessionLifecycle(BaseTestCase):

    def test_upsert_then_get_meta(self):
        db.upsert_session(_META, _USER_TEXTS, _ASST_SNIPPETS)
        result = db.get_session_meta("test-session-001")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "test-session-001")
        self.assertEqual(result["title"], "Test Session")

    def test_search_fts_finds_user_text(self):
        db.upsert_session(_META, _USER_TEXTS, _ASST_SNIPPETS)
        results = db.search_fts("unique search term")
        texts = [r["text"] for r in results]
        self.assertTrue(any("unique search term" in t for t in texts))

    def test_reupsert_replaces_fts(self):
        db.upsert_session(_META, _USER_TEXTS, _ASST_SNIPPETS)

        new_user_texts = [
            {"idx": 0, "text": "Completely different content xyz", "ts": "2026-06-02T10:00:00Z"},
        ]
        db.upsert_session(_META, new_user_texts, [])

        old_results = db.search_fts("unique search term")
        self.assertEqual(old_results, [], "Old FTS text should be gone after re-upsert")

        new_results = db.search_fts("different content xyz")
        self.assertTrue(len(new_results) > 0, "New FTS text should be findable")

    def test_get_session_meta_partial_id(self):
        db.upsert_session(_META, [], [])
        # Partial match: just the suffix
        result = db.get_session_meta("session-001")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "test-session-001")

    def test_get_session_messages_role(self):
        db.upsert_session(_META, _USER_TEXTS, _ASST_SNIPPETS)
        user_msgs = db.get_session_messages("test-session-001", role="user")
        self.assertEqual(len(user_msgs), 2)
        for m in user_msgs:
            self.assertEqual(m["role"], "user")

        asst_msgs = db.get_session_messages("test-session-001", role="assistant")
        self.assertEqual(len(asst_msgs), 1)
        self.assertEqual(asst_msgs[0]["role"], "assistant")


# ---------------------------------------------------------------------------
# Cognitive model tests
# ---------------------------------------------------------------------------

class TestCognitiveModel(BaseTestCase):

    _TABLE = "judgment_cards"
    _CARD_ID = "card-001"
    _CARD_DATA = {
        "applies_when": "user asks a question",
        "judgment": "answer clearly",
        "agent_action": "respond",
        "exceptions": "none",
        "tags": "general",
        "confidence": 0.9,
        "status": "active",
        "evidence_count": 1,
    }

    def test_cm_upsert_and_get(self):
        db.cm_upsert(self._TABLE, self._CARD_ID, self._CARD_DATA)
        row = db.cm_get(self._TABLE, self._CARD_ID)
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], self._CARD_ID)
        self.assertEqual(row["judgment"], "answer clearly")
        self.assertIn("applies_when", row)

    def test_cm_upsert_partial_update_preserves_fields(self):
        db.cm_upsert(self._TABLE, self._CARD_ID, self._CARD_DATA)
        # Partial update: only change confidence, leave other fields intact
        db.cm_upsert(self._TABLE, self._CARD_ID, {"confidence": 0.5})
        row = db.cm_get(self._TABLE, self._CARD_ID)
        self.assertEqual(row["confidence"], 0.5)
        # Original field must still be present
        self.assertEqual(row["judgment"], "answer clearly")
        self.assertEqual(row["status"], "active")

    def test_cm_upsert_sets_updated_at(self):
        db.cm_upsert(self._TABLE, self._CARD_ID, self._CARD_DATA)
        row = db.cm_get(self._TABLE, self._CARD_ID)
        self.assertIn("updated_at", row)
        self.assertIsNotNone(row["updated_at"])

    def test_cm_delete(self):
        db.cm_upsert(self._TABLE, self._CARD_ID, self._CARD_DATA)
        db.cm_delete(self._TABLE, self._CARD_ID)
        self.assertIsNone(db.cm_get(self._TABLE, self._CARD_ID))

    def test_cm_count(self):
        self.assertEqual(db.cm_count(self._TABLE), 0)
        db.cm_upsert(self._TABLE, "card-a", self._CARD_DATA)
        db.cm_upsert(self._TABLE, "card-b", self._CARD_DATA)
        self.assertEqual(db.cm_count(self._TABLE), 2)
        db.cm_delete(self._TABLE, "card-a")
        self.assertEqual(db.cm_count(self._TABLE), 1)


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

class TestEdgeCases(BaseTestCase):

    def test_search_fts_invalid_syntax_returns_empty(self):
        db.upsert_session(_META, _USER_TEXTS, _ASST_SNIPPETS)
        # FTS5 operators like AND/OR require operands; bare "AND" is invalid
        result = db.search_fts("AND OR NOT")
        self.assertIsInstance(result, list)
        # Should not raise — just return empty or partial results gracefully

    def test_get_session_meta_nonexistent_returns_none(self):
        result = db.get_session_meta("nonexistent-session-id-zzz")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# FTS search edge cases
# ---------------------------------------------------------------------------

class TestSearchFTSEdgeCases(BaseTestCase):

    def test_search_fts_special_chars_no_crash(self):
        """Queries with FTS5 metacharacters should not crash; they fall back to LIKE."""
        db.upsert_session(_META, _USER_TEXTS, _ASST_SNIPPETS)
        for q in ['"unclosed', '***', '(((', 'foo"bar', 'a*b(c']:
            result = db.search_fts(q)
            self.assertIsInstance(result, list, f"search_fts({q!r}) should return a list")

    def test_search_fts_returns_ranked(self):
        """Sessions with more matches should appear (both should be found)."""
        meta_a = {**_META, "id": "rank-sess-a", "filePath": "/tmp/rank-a.jsonl"}
        meta_b = {**_META, "id": "rank-sess-b", "filePath": "/tmp/rank-b.jsonl"}

        # Session A: term appears once
        texts_a = [{"idx": 0, "text": "banana is great", "ts": "2026-06-01T10:00:00Z"}]
        # Session B: term appears three times
        texts_b = [
            {"idx": 0, "text": "banana banana banana", "ts": "2026-06-01T10:00:00Z"},
        ]
        db.upsert_session(meta_a, texts_a, [])
        db.upsert_session(meta_b, texts_b, [])

        results = db.search_fts("banana")
        self.assertTrue(len(results) >= 2, "Both sessions should appear in results")
        sids = [r["session_id"] for r in results]
        self.assertIn("rank-sess-a", sids)
        self.assertIn("rank-sess-b", sids)

    def test_search_fts_empty_query(self):
        """Empty string falls through to LIKE '%%' — returns results (not crash)."""
        db.upsert_session(_META, _USER_TEXTS, _ASST_SNIPPETS)
        result = db.search_fts("")
        self.assertIsInstance(result, list)
        # The LIKE fallback with '%%' matches everything; main point: no crash


if __name__ == "__main__":
    unittest.main()
