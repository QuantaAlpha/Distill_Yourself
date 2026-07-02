import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chatview import db
from chatview.db import core as dbcore
from chatview.commands import corrections


class CorrectionEventsTest(unittest.TestCase):
    def setUp(self):
        self._orig_db_path = dbcore.DB_PATH
        self._orig_cache_dir = dbcore.CACHE_DIR
        self._tmpdir = tempfile.mkdtemp()
        dbcore.CACHE_DIR = Path(self._tmpdir)
        dbcore.DB_PATH = Path(self._tmpdir) / "sessions.db"
        dbcore._local = threading.local()
        db.init_db()

    def tearDown(self):
        dbcore.DB_PATH = self._orig_db_path
        dbcore.CACHE_DIR = self._orig_cache_dir
        dbcore._local = threading.local()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _args(self):
        return SimpleNamespace(date="all", source="all", project="", json=True, limit=10)

    def _insert_session(self, sid, mtime, user_text, assistant_text):
        db.upsert_session(
            {
                "id": sid,
                "title": f"Session {sid}",
                "date": "2026-06-01T10:00:00",
                "lastDate": "2026-06-01T10:05:00",
                "filePath": f"/tmp/{sid}.jsonl",
                "fileSize": 100 + int(mtime),
                "_mtime": mtime,
                "userMessageCount": 1,
                "preview": user_text,
                "project": "proj",
                "projectName": "proj",
                "source": "claude",
            },
            [{"idx": 1, "text": user_text, "ts": "2026-06-01T10:00:00"}],
            [{"idx": 2, "text": assistant_text, "ts": "2026-06-01T10:01:00"}],
        )

    def test_cached_corrections_match_uncached_results(self):
        self._insert_session(
            "s1",
            1.0,
            "不是这样，应该是先讨论方案再改代码",
            "抱歉，我理解错了，先讨论方案。",
        )
        self._insert_session(
            "s2",
            2.0,
            "这个方案不合理，重新想一下",
            "你说得对，我漏了边界条件。",
        )

        args = self._args()
        expected = corrections._data_corrections_uncached(args)
        actual = corrections._data_corrections(args)

        self.assertEqual(actual, expected)

    def test_fresh_cache_does_not_reextract_sessions(self):
        self._insert_session(
            "s1",
            1.0,
            "不是这样，应该是先讨论方案再改代码",
            "抱歉，我理解错了，先讨论方案。",
        )
        args = self._args()

        corrections._data_corrections(args)

        with patch(
            "chatview.commands.corrections._extract_corrections_from_session",
            side_effect=AssertionError("fresh cache should not re-extract"),
        ):
            rows = corrections._data_corrections(args)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sessionId"], "s1")

    def test_stale_cache_reextracts_only_changed_session(self):
        self._insert_session(
            "s1",
            1.0,
            "不是这样，应该是先讨论方案再改代码",
            "抱歉，我理解错了，先讨论方案。",
        )
        self._insert_session(
            "s2",
            2.0,
            "这个方案不合理，重新想一下",
            "你说得对，我漏了边界条件。",
        )
        args = self._args()
        corrections._data_corrections(args)

        self._insert_session(
            "s1",
            3.0,
            "不要这样，应该保持核心数据完整",
            "收到，我刚才跑偏了。",
        )

        seen = []
        original = corrections._extract_corrections_from_session

        def record(meta, user_texts, assistant_snippets, regexes=None):
            seen.append(meta["id"])
            return original(meta, user_texts, assistant_snippets, regexes)

        with patch("chatview.commands.corrections._extract_corrections_from_session", record):
            rows = corrections._data_corrections(args)

        self.assertEqual(seen, ["s1"])
        self.assertEqual({r["sessionId"] for r in rows}, {"s1", "s2"})
        self.assertIn("保持核心数据完整", rows[0]["text"])


if __name__ == "__main__":
    unittest.main()
