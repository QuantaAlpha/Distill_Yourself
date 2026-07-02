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
        from chatview.db import core as _dbcore
        self._orig_db_path = _dbcore.DB_PATH
        self._orig_cache_dir = _dbcore.CACHE_DIR
        self._tmpdir = tempfile.mkdtemp()
        from pathlib import Path
        _dbcore.CACHE_DIR = Path(self._tmpdir)
        _dbcore.DB_PATH = Path(self._tmpdir) / "sessions.db"
        _dbcore._local = threading.local()
        db.init_db()

    def tearDown(self):
        from chatview.db import core as _dbcore
        _dbcore.DB_PATH = self._orig_db_path
        _dbcore.CACHE_DIR = self._orig_cache_dir
        _dbcore._local = threading.local()
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
            analyze.cmd_twin_compile(SimpleNamespace(run_id="run_a", lang="zh"))
        text = out.getvalue()

        self.assertIn("A scenario", text)
        self.assertIn("Trait A", text)
        self.assertNotIn("B scenario", text)
        self.assertNotIn("Trait B", text)

    def test_twin_search_uses_valid_sort_columns_for_all_resources(self):
        db.cm_upsert("evidence_events", "ev_search", {
            "session_id": "s1",
            "event_index": 1,
            "lesson": "regression gate lesson",
            "signal_type": "correction",
            "domain": "testing/search",
        })
        db.cm_upsert("judgment_cards", "jc_search", {
            "applies_when": "regression gate needed",
            "judgment": "add a regression test",
            "agent_action": "write the test first",
        })
        db.cm_upsert("cognitive_traits", "ct_search", {
            "name": "Regression Gate",
            "category": "testing",
            "description": "prefers a regression gate before fixes",
        })

        for resource, query, expected_id in (
            ("events", "regression gate lesson", "ev_search"),
            ("cards", "regression gate needed", "jc_search"),
            ("traits", "Regression Gate", "ct_search"),
        ):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                analyze.cmd_twin_search(
                    SimpleNamespace(resource=resource, q=query, limit=10)
                )
            data = json.loads(out.getvalue())
            self.assertTrue(
                any(item["id"] == expected_id for item in data["items"]),
                resource,
            )

    def test_twin_cancel_preserves_stage_data_and_marks_checkpoint_cancelled(self):
        """Cancelling a running analysis must NOT delete completed stage data;
        it should keep events/cards/traits and mark the run's checkpoint so a
        later resume can continue instead of restarting from stage 1."""
        from chatview.handlers import twin as _twin

        run_id = "run_cancel_test"
        # Seed completed stage-1 data + a checkpoint state.
        db.cm_upsert("evidence_events", "ev_keep", {
            "run_id": run_id,
            "session_id": "s1",
            "event_index": 1,
            "lesson": "keep me",
            "signal_type": "correction",
            "domain": "coding/scope",
        })
        db.save_checkpoint(run_id, 1, "completed")
        db.save_checkpoint(run_id, 2, "running")

        class _FakeProc:
            pid = -99999  # nonexistent pgid → killpg raises, handled gracefully

            def wait(self, timeout=None):
                return 0

        # Register an active run.
        with _twin._analyze_lock:
            _twin._active_analyze_proc = _FakeProc()
            _twin._active_analyze_run_id = run_id

        captured = {}

        class _FakeHandler:
            def __init__(self):
                self.wfile = io.BytesIO()
                self.headers = {}

            def send_response(self, code):
                captured["code"] = code

            def send_header(self, *a, **k):
                pass

            def end_headers(self):
                pass

            @property
            def rfile(self):
                return io.BytesIO(json.dumps({"run_id": run_id}).encode())

        # _read_post_body reads Content-Length from headers; emulate no-body path.
        handler = _FakeHandler()
        handler.headers = {"Content-Length": "0"}

        try:
            _twin._handle_twin_cancel(handler)
        finally:
            with _twin._analyze_lock:
                _twin._active_analyze_proc = None
                _twin._active_analyze_run_id = None

        # Data must survive cancellation.
        self.assertEqual(db.cm_count("evidence_events"), 1)
        self.assertEqual(db.cm_get("evidence_events", "ev_keep")["lesson"], "keep me")
        # The completed stage stays completed; the running stage is marked cancelled.
        cps = db.get_checkpoint(run_id)
        self.assertEqual(cps.get(1), "completed")
        self.assertEqual(cps.get(2), "cancelled")

    def test_twin_resume_uses_checkpoint_run_id_as_authority(self):
        """Resume must treat twin_checkpoints as the authoritative run source so a
        cancelled run (data preserved, stages marked cancelled) reports the same
        run_id and a resumable 'partial' status."""
        from chatview.handlers import twin as _twin

        run_id = "run_resume_auth"
        db.cm_upsert("evidence_events", "ev_r", {
            "run_id": run_id,
            "session_id": "s1",
            "event_index": 1,
            "lesson": "stage1 done",
            "signal_type": "correction",
            "domain": "coding/scope",
        })
        db.save_checkpoint(run_id, 1, "completed")
        db.save_checkpoint(run_id, 2, "cancelled")

        class _FakeHandler:
            def __init__(self):
                self.wfile = io.BytesIO()
                self.headers = {"Content-Length": "0"}

            def send_response(self, code):
                pass

            def send_header(self, *a, **k):
                pass

            def end_headers(self):
                pass

        handler = _FakeHandler()
        _twin._handle_twin_resume(handler)
        resp = json.loads(handler.wfile.getvalue().decode())

        self.assertTrue(resp["ok"])
        self.assertEqual(resp["run"]["run_id"], run_id)
        # status reflects partial progress, and checkpoints are surfaced.
        self.assertIn(resp["run"]["status"], ("partial", "interrupted"))
        self.assertEqual(resp["run"]["checkpoints"].get("1"), "completed")

    def test_twin_progress_reports_running_state_and_checkpoints(self):
        """GET /api/twin/progress lets a reopened tab re-attach to a background
        run: it must report whether an analysis is still running plus the
        per-stage checkpoint map so the UI can rebuild progress without
        restarting from stage 1."""
        from chatview.handlers import twin as _twin

        run_id = "run_progress_test"
        db.cm_upsert("evidence_events", "ev_p", {
            "run_id": run_id,
            "session_id": "s1",
            "event_index": 1,
            "lesson": "stage1 done",
            "signal_type": "correction",
            "domain": "coding/scope",
        })
        db.save_checkpoint(run_id, 1, "completed")
        db.save_checkpoint(run_id, 2, "running")

        class _FakeProc:
            def poll(self):
                return None  # still running

        # Simulate a live background run.
        with _twin._analyze_lock:
            _twin._active_analyze_proc = _FakeProc()
            _twin._active_analyze_run_id = run_id

        class _FakeHandler:
            def __init__(self):
                self.wfile = io.BytesIO()
                self.headers = {"Content-Length": "0"}
                self.path = "/api/twin/progress"

            def send_response(self, code):
                pass

            def send_header(self, *a, **k):
                pass

            def end_headers(self):
                pass

        handler = _FakeHandler()
        try:
            _twin._handle_twin_progress(handler)
        finally:
            with _twin._analyze_lock:
                _twin._active_analyze_proc = None
                _twin._active_analyze_run_id = None

        resp = json.loads(handler.wfile.getvalue().decode())
        self.assertTrue(resp["ok"])
        self.assertTrue(resp["running"])
        self.assertEqual(resp["run"]["run_id"], run_id)
        self.assertEqual(resp["run"]["checkpoints"].get("1"), "completed")
        self.assertEqual(resp["run"]["checkpoints"].get("2"), "running")

    def test_twin_progress_reports_not_running_when_idle(self):
        """When no analysis is active, progress reports running=False but still
        surfaces the latest run so the UI can show stored results."""
        from chatview.handlers import twin as _twin

        run_id = "run_idle"
        db.cm_upsert("evidence_events", "ev_i", {
            "run_id": run_id,
            "session_id": "s1",
            "event_index": 1,
            "lesson": "done",
            "signal_type": "correction",
            "domain": "coding/scope",
        })
        db.save_checkpoint(run_id, 1, "completed")

        with _twin._analyze_lock:
            _twin._active_analyze_proc = None
            _twin._active_analyze_run_id = None

        class _FakeHandler:
            def __init__(self):
                self.wfile = io.BytesIO()
                self.headers = {"Content-Length": "0"}
                self.path = "/api/twin/progress"

            def send_response(self, code):
                pass

            def send_header(self, *a, **k):
                pass

            def end_headers(self):
                pass

        handler = _FakeHandler()
        _twin._handle_twin_progress(handler)
        resp = json.loads(handler.wfile.getvalue().decode())
        self.assertTrue(resp["ok"])
        self.assertFalse(resp["running"])

    def test_twin_runs_lists_recent_runs_newest_first_and_capped(self):
        """GET /api/twin/runs returns at most 10 distinct runs, newest first,
        each with derived status/stats/checkpoints so the UI can render a
        recent-history list below the current progress summary."""
        from chatview.handlers import twin as _twin

        # Seed 12 runs with ascending created_at so ordering is deterministic.
        for i in range(1, 13):
            run_id = f"run_{i:02d}"
            db.cm_upsert("evidence_events", f"ev_{i}", {
                "run_id": run_id,
                "session_id": "s1",
                "event_index": i,
                "lesson": f"lesson {i}",
                "signal_type": "correction",
                "domain": "coding/scope",
                "created_at": f"2026-06-{10 + i:02d}T10:00:00",
            })
            db.save_checkpoint(run_id, 1, "completed")

        class _FakeHandler:
            def __init__(self):
                self.wfile = io.BytesIO()
                self.headers = {"Content-Length": "0"}
                self.path = "/api/twin/runs"

            def send_response(self, code):
                pass

            def send_header(self, *a, **k):
                pass

            def end_headers(self):
                pass

        handler = _FakeHandler()
        _twin._handle_twin_runs(handler)
        resp = json.loads(handler.wfile.getvalue().decode())

        self.assertTrue(resp["ok"])
        runs = resp["runs"]
        # Capped at 10 and newest first.
        self.assertEqual(len(runs), 10)
        self.assertEqual(runs[0]["run_id"], "run_12")
        self.assertEqual(runs[-1]["run_id"], "run_03")
        # Each run carries derived stats + checkpoints + a timestamp.
        self.assertEqual(runs[0]["stats"]["events"], 1)
        self.assertEqual(runs[0]["checkpoints"].get("1"), "completed")
        self.assertTrue(runs[0]["ts"])

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
