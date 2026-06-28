import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import analyze  # noqa: E402  (must follow sys.path.insert above)
import db  # noqa: E402


class TwinIntegrityTestCase(unittest.TestCase):
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

    def _run_twin_batch(self, payload, expect_exit=False):
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps(payload))
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                if expect_exit:
                    with self.assertRaises(SystemExit):
                        analyze.cmd_twin_batch(None)
                else:
                    analyze.cmd_twin_batch(None)
        finally:
            sys.stdin = old_stdin
        return json.loads(out.getvalue())

    def test_duplicate_evidence_event_index_is_rejected_without_replacing_existing_row(self):
        db.cm_upsert("evidence_events", "ev_original", {
            "session_id": "s1",
            "event_index": 1,
            "lesson": "original lesson",
            "signal_type": "correction",
            "domain": "coding/scope",
        })

        with self.assertRaises(ValueError):
            db.cm_upsert("evidence_events", "ev_duplicate", {
                "session_id": "s1",
                "event_index": 1,
                "lesson": "duplicate lesson",
                "signal_type": "acceptance",
                "domain": "coding/scope",
            })

        self.assertEqual(db.cm_get("evidence_events", "ev_original")["lesson"], "original lesson")
        self.assertIsNone(db.cm_get("evidence_events", "ev_duplicate"))

    def test_twin_batch_rejects_invalid_link_and_rolls_back_prior_add(self):
        result = self._run_twin_batch({
            "operations": [
                {
                    "resource": "events",
                    "action": "add",
                    "data": {
                        "session_id": "s1",
                        "event_index": 1,
                        "lesson": "should roll back",
                        "signal_type": "correction",
                        "domain": "testing/rollback",
                    },
                },
                {"resource": "link", "action": "link", "from": "ev_missing", "to": "jc_missing"},
            ],
        }, expect_exit=True)

        self.assertFalse(result["ok"])
        self.assertEqual(db.cm_count("evidence_events"), 0)

    def test_twin_batch_rejects_cross_run_edit_and_link(self):
        db.cm_upsert("evidence_events", "ev_a", {
            "run_id": "run_a",
            "session_id": "s1",
            "event_index": 1,
            "lesson": "run a event",
            "signal_type": "correction",
            "domain": "coding/scope",
        })
        db.cm_upsert("judgment_cards", "jc_b", {
            "run_id": "run_b",
            "applies_when": "run b card",
            "judgment": "b judgment",
            "agent_action": "b action",
        })

        edit_result = self._run_twin_batch({
            "run_id": "run_b",
            "operations": [{
                "resource": "events",
                "action": "edit",
                "id": "ev_a",
                "data": {"lesson": "bad cross-run edit"},
            }],
        }, expect_exit=True)
        self.assertFalse(edit_result["ok"])
        self.assertEqual(db.cm_get("evidence_events", "ev_a")["lesson"], "run a event")

        link_result = self._run_twin_batch({
            "run_id": "run_b",
            "operations": [{
                "resource": "link",
                "action": "link",
                "from": "ev_a",
                "to": "jc_b",
            }],
        }, expect_exit=True)
        self.assertFalse(link_result["ok"])
        self.assertIsNone(db.cm_get("evidence_events", "ev_a").get("card_id"))

    def test_twin_compile_run_id_filters_cards_and_traits(self):
        db.cm_upsert("judgment_cards", "jc_a", {
            "run_id": "run_a",
            "applies_when": "A scenario",
            "judgment": "A judgment",
            "agent_action": "A action",
            "confidence": 0.9,
            "status": "confirmed",
        })
        db.cm_upsert("judgment_cards", "jc_b", {
            "run_id": "run_b",
            "applies_when": "B scenario",
            "judgment": "B judgment",
            "agent_action": "B action",
            "confidence": 0.9,
            "status": "confirmed",
        })
        db.cm_upsert("cognitive_traits", "ct_a", {
            "run_id": "run_a",
            "name": "Trait A",
            "category": "决策风格",
            "description": "Only run A",
            "strength": 0.9,
            "status": "confirmed",
        })
        db.cm_upsert("cognitive_traits", "ct_b", {
            "run_id": "run_b",
            "name": "Trait B",
            "category": "决策风格",
            "description": "Only run B",
            "strength": 0.9,
            "status": "confirmed",
        })

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            analyze.cmd_twin_compile(SimpleNamespace(run_id="run_a"))
        text = out.getvalue()

        self.assertIn("A scenario", text)
        self.assertIn("Trait A", text)
        self.assertNotIn("B scenario", text)
        self.assertNotIn("Trait B", text)

    def test_prune_stale_sessions_removes_sessions_messages_and_insights(self):
        meta = {
            "id": "stale",
            "title": "Stale",
            "date": "2026-06-26T10:00:00",
            "lastDate": "2026-06-26T10:00:00",
            "filePath": "/tmp/stale.jsonl",
            "fileSize": 10,
            "_mtime": 1,
            "userMessageCount": 1,
            "preview": "hello",
            "project": "demo",
            "projectName": "Demo",
            "source": "codex",
        }
        db.upsert_session(meta, [{"idx": 0, "text": "hello stale prune", "ts": "2026-06-26T10:00:00"}], [])
        db.get_conn().execute(
            "INSERT INTO insight_tool_usage(session_id, day, tool_name, count) VALUES (?,?,?,?)",
            ("stale", "2026-06-26", "Read", 1),
        )
        db.get_conn().commit()

        self.assertEqual(db.prune_stale_sessions(set()), 1)
        self.assertIsNone(db.get_session_meta("stale"))
        self.assertEqual(db.get_conn().execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
        self.assertEqual(db.get_conn().execute("SELECT COUNT(*) FROM insight_tool_usage").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
