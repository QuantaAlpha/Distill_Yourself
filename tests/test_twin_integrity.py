import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import analyze
import db
import server


class TwinIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cache_dir = db.CACHE_DIR
        self.old_db_path = db.DB_PATH
        self.old_server_cache_dir = server.CACHE_DIR
        self.old_conn = getattr(db._local, "conn", None)
        if self.old_conn is not None:
            self.old_conn.close()
            db._local.conn = None
        db.CACHE_DIR = Path(self.tmp.name)
        db.DB_PATH = db.CACHE_DIR / "sessions.db"
        server.CACHE_DIR = Path(self.tmp.name)
        db.init_db()

    def tearDown(self):
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None
        db.CACHE_DIR = self.old_cache_dir
        db.DB_PATH = self.old_db_path
        server.CACHE_DIR = self.old_server_cache_dir
        if self.old_conn is not None:
            db._local.conn = None
        self.tmp.cleanup()

    def test_duplicate_evidence_event_index_is_rejected_without_replacing_existing_row(self):
        db.cm_upsert("evidence_events", "ev_original", {
            "session_id": "s1",
            "event_index": 1,
            "lesson": "original lesson",
        })

        with self.assertRaises(ValueError):
            db.cm_upsert("evidence_events", "ev_duplicate", {
                "session_id": "s1",
                "event_index": 1,
                "lesson": "duplicate lesson",
            })

        self.assertEqual(db.cm_get("evidence_events", "ev_original")["lesson"], "original lesson")
        self.assertIsNone(db.cm_get("evidence_events", "ev_duplicate"))

    def test_evidence_event_index_can_repeat_across_runs(self):
        base = {
            "session_id": "s1",
            "event_index": 1,
            "lesson": "scoped lesson",
            "signal_type": "correction",
            "domain": "coding/scope",
        }
        db.cm_upsert("evidence_events", "ev_run_a", {**base, "run_id": "run_a"})
        db.cm_upsert("evidence_events", "ev_run_b", {**base, "run_id": "run_b"})

        self.assertEqual(db.cm_count("evidence_events"), 2)
        self.assertEqual(db.cm_get("evidence_events", "ev_run_a")["run_id"], "run_a")
        self.assertEqual(db.cm_get("evidence_events", "ev_run_b")["run_id"], "run_b")

    def test_twin_batch_rejects_invalid_link_and_rolls_back_prior_add(self):
        payload = {
            "operations": [
                {
                    "resource": "events",
                    "action": "add",
                    "data": {
                        "session_id": "s1",
                        "event_index": 1,
                        "lesson": "should roll back",
                        "signal_type": "correction",
                        "domain": "testing/scope",
                    },
                },
                {
                    "action": "link",
                    "from": "ev_missing",
                    "to": "jc_missing",
                },
            ]
        }

        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps(payload))
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                with self.assertRaises(SystemExit):
                    analyze.cmd_twin_batch(None)
        finally:
            sys.stdin = old_stdin

        result = json.loads(out.getvalue())
        self.assertFalse(result["ok"])
        self.assertEqual(result["succeeded"], 0)
        self.assertEqual(result["results"][-1]["index"], 1)
        self.assertTrue(result["results"][-1]["rolled_back"])
        self.assertEqual(db.cm_count("evidence_events"), 0)
        self.assertEqual(db.cm_count("judgment_cards"), 0)

    def test_twin_write_rolls_back_and_exits_on_error(self):
        payload = {
            "table": "evidence_events",
            "operations": [
                {
                    "action": "insert",
                    "id": "ev_original",
                    "data": {
                        "session_id": "s1",
                        "event_index": 1,
                        "lesson": "should roll back",
                    },
                },
                {
                    "action": "insert",
                    "id": "ev_duplicate",
                    "data": {
                        "session_id": "s1",
                        "event_index": 1,
                        "lesson": "duplicate should fail",
                    },
                },
            ],
        }

        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps(payload))
        err = io.StringIO()
        try:
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(err):
                    analyze.cmd_twin_write(None)
        finally:
            sys.stdin = old_stdin

        self.assertIn("rolled back", err.getvalue())
        self.assertEqual(db.cm_count("evidence_events"), 0)

    def test_twin_candidates_validates_without_writing(self):
        payload = {
            "candidates": [
                {
                    "resource": "events",
                    "data": {
                        "session_id": "s1",
                        "event_index": 1,
                        "lesson": "prefer scoped changes",
                        "signal_type": "correction",
                        "domain": "coding/scope",
                    },
                }
            ]
        }

        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps(payload))
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                analyze.cmd_twin_candidates(None)
        finally:
            sys.stdin = old_stdin

        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(db.cm_count("evidence_events"), 0)

    def test_twin_candidates_rejects_missing_required_fields(self):
        payload = {"candidates": [{"resource": "events", "data": {"session_id": "s1"}}]}

        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps(payload))
        out = io.StringIO()
        try:
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stdout(out):
                    analyze.cmd_twin_candidates(None)
        finally:
            sys.stdin = old_stdin

        result = json.loads(out.getvalue())
        self.assertFalse(result["ok"])
        self.assertIn("lesson", result["results"][0]["missing"])

    def test_twin_batch_stamps_run_id_and_records_dag(self):
        payload = {
            "run_id": "run_scope_a",
            "operations": [{
                "resource": "events",
                "action": "add",
                "data": {
                    "session_id": "s1",
                    "event_index": 1,
                    "lesson": "scoped lesson",
                    "signal_type": "correction",
                    "domain": "coding/scope",
                },
            }],
        }

        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps(payload))
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                analyze.cmd_twin_batch(None)
        finally:
            sys.stdin = old_stdin

        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        row = db.cm_get("evidence_events", result["results"][0]["id"])
        self.assertEqual(row["run_id"], "run_scope_a")

        task_id = db.twin_task_upsert("run_scope_a", 1, "done", {"input": "sessions"}, finished=True)
        artifact_id = db.twin_artifact_record("run_scope_a", task_id, 1, "stage_counts", payload={"events": 1})
        conn = db.get_conn()
        self.assertEqual(conn.execute("SELECT run_id FROM twin_tasks WHERE task_id=?", (task_id,)).fetchone()["run_id"], "run_scope_a")
        self.assertEqual(conn.execute("SELECT run_id FROM twin_artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()["run_id"], "run_scope_a")

    def test_stage_prompts_and_counts_are_run_scoped(self):
        db.cm_upsert("evidence_events", "ev_in", {
            "run_id": "run_in",
            "session_id": "s1",
            "event_index": 1,
            "lesson": "inside run",
            "signal_type": "correction",
            "domain": "coding/scope",
        })
        db.cm_upsert("evidence_events", "ev_out", {
            "run_id": "run_out",
            "session_id": "s2",
            "event_index": 1,
            "lesson": "outside run",
            "signal_type": "acceptance",
            "domain": "research/scope",
        })
        db.cm_upsert("judgment_cards", "jc_in", {
            "run_id": "run_in",
            "applies_when": "inside card",
            "judgment": "inside judgment",
            "agent_action": "inside action",
        })
        db.cm_upsert("judgment_cards", "jc_out", {
            "run_id": "run_out",
            "applies_when": "outside card",
            "judgment": "outside judgment",
            "agent_action": "outside action",
        })

        class DummyHandler:
            def _collect_profile_digest(self, *args, **kwargs):
                return ""

        stage2 = server.ChatViewerHandler._build_twin_stage2_prompt(DummyHandler(), "analyze.py", "run_in")
        stage3 = server.ChatViewerHandler._build_twin_stage3_prompt(DummyHandler(), "analyze.py", "run_in")
        stage1 = server.ChatViewerHandler._build_twin_stage1_prompt(
            DummyHandler(), "analyze.py", "run_in", "all", "7d", "", "auto"
        )
        counts = server.ChatViewerHandler._stage_counts(DummyHandler(), 2, "run_in")

        self.assertIn("twin-events --run-id run_in", stage1)
        self.assertIn("inside run", stage2)
        self.assertNotIn("outside run", stage2)
        self.assertIn("inside card", stage3)
        self.assertNotIn("outside card", stage3)
        self.assertTrue(counts["cursor"]["run_scoped"])
        self.assertEqual(counts["events"], 1)

    def test_prune_stale_sessions_removes_messages_and_insights(self):
        meta = {
            "id": "s_stale",
            "title": "Stale",
            "date": "2026-06-26T10:00:00",
            "lastDate": "2026-06-26T10:00:00",
            "filePath": "/tmp/stale.jsonl",
            "fileSize": 10,
            "_mtime": 1,
            "userMessageCount": 1,
            "preview": "hello",
            "project": "demo",
            "projectName": "Demo Project",
            "source": "codex",
        }
        db.upsert_session(meta, [{"idx": 0, "text": "hello", "ts": "2026-06-26T10:00:00"}], [])
        db.get_conn().execute(
            "INSERT INTO insight_tool_usage(session_id, day, tool_name, count) VALUES (?,?,?,?)",
            ("s_stale", "2026-06-26", "Read", 1),
        )
        db.get_conn().commit()

        self.assertEqual(db.prune_stale_sessions(set()), 1)
        self.assertIsNone(db.get_session_meta("s_stale"))
        self.assertEqual(db.get_conn().execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
        self.assertEqual(db.get_conn().execute("SELECT COUNT(*) FROM insight_tool_usage").fetchone()[0], 0)

    def test_project_filter_is_substring_and_stats_json_is_machine_readable(self):
        meta = {
            "id": "s_project",
            "title": "Project",
            "date": "2026-06-26T10:00:00",
            "lastDate": "2026-06-26T10:00:00",
            "filePath": "/tmp/project.jsonl",
            "fileSize": 10,
            "_mtime": 1,
            "userMessageCount": 1,
            "preview": "hello",
            "project": "demo",
            "projectName": "Distill Yourself",
            "source": "codex",
        }
        db.upsert_session(meta, [{"idx": 0, "text": "how to test", "ts": "2026-06-26T10:00:00"}], [])

        class Args:
            source = "all"
            project = "distill"
            date = "all"
            limit = 10
            json = True

        self.assertEqual(len(db.get_filtered_sessions(project="distill")), 1)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            analyze.cmd_stats(Args())
        data = json.loads(out.getvalue())
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["byProject"]["Distill Yourself"], 1)

    def test_twin_run_persists_stage_metadata_and_latest(self):
        db.twin_run_upsert(
            "run_a",
            {"source": "codex", "date": "7d", "project": "Demo"},
            start_stage=1,
            current_stage=1,
            status="running",
            stage_meta={"1": {"status": "running"}},
        )
        db.twin_run_update_stage(
            "run_a",
            current_stage=2,
            status="timeout",
            stage_meta={"1": {"status": "done", "elapsed_seconds": 2.5}},
            last_error="Stage 2 timed out",
        )

        run = db.twin_run_get("run_a")
        self.assertEqual(run["status"], "timeout")
        self.assertEqual(run["current_stage"], 2)
        self.assertEqual(run["scope"]["project"], "Demo")
        self.assertEqual(run["stage_meta"]["1"]["status"], "done")
        self.assertEqual(run["last_error"], "Stage 2 timed out")
        self.assertEqual(db.twin_run_latest()["run_id"], "run_a")

        db.twin_run_upsert(
            "run_a",
            {"source": "codex", "date": "7d", "project": "Demo"},
            start_stage=2,
            current_stage=2,
            status="running",
        )
        resumed = db.twin_run_get("run_a")
        self.assertEqual(resumed["stage_meta"]["1"]["status"], "done")

    def test_twin_scope_snapshot_freezes_filtered_inputs(self):
        old_index = server._index
        old_index_gen = server._index_gen
        try:
            server._index_gen = 42
            server._index = {
                "sessions": {
                    "s1": {
                        "id": "s1",
                        "source": "codex",
                        "projectName": "Demo",
                        "date": "2026-06-26T10:00:00",
                        "lastDate": "2026-06-26T10:30:00",
                    },
                    "s2": {
                        "id": "s2",
                        "source": "claude",
                        "projectName": "Other",
                        "date": "2026-06-26T09:00:00",
                    },
                }
            }

            snap = server._twin_scope_snapshot("codex", "all", "Demo", "auto")
        finally:
            server._index = old_index
            server._index_gen = old_index_gen

        self.assertEqual(snap["index_gen"], 42)
        self.assertEqual(snap["session_count"], 1)
        self.assertEqual(snap["latest_session_ts"], "2026-06-26T10:30:00")
        self.assertEqual(snap["source"], "codex")
        self.assertEqual(snap["project"], "Demo")
        self.assertEqual(len(snap["session_ids_hash"]), 16)

    def test_evolve_stream_error_event_does_not_emit_stale_cache(self):
        db.evolve_upsert(
            "profile",
            "all",
            "7d",
            "",
            "auto",
            json.dumps({"categories": [{"title": "stale"}]}),
        )

        old_stream = server._run_ai_engine_stream

        def fake_stream(*args, **kwargs):
            yield {"type": "error", "message": "No AI engine"}

        class DummyHandler:
            def __init__(self):
                self.events = []

            def _start_sse(self):
                self.started = True

            def _sse_event(self, evt):
                self.events.append(evt)

            def _build_evolve_prompt(self, *args, **kwargs):
                return "prompt"

        dummy = DummyHandler()
        try:
            server._run_ai_engine_stream = fake_stream
            server.ChatViewerHandler._handle_evolve_stream(dummy, "profile", "all", "7d", "", "auto")
        finally:
            server._run_ai_engine_stream = old_stream

        self.assertEqual(dummy.events, [{"type": "error", "message": "No AI engine"}])

    def test_evolve_stream_timeout_does_not_emit_stale_cache(self):
        db.evolve_upsert(
            "profile",
            "all",
            "7d",
            "",
            "auto",
            json.dumps({"categories": [{"title": "stale"}]}),
        )

        old_stream = server._run_ai_engine_stream

        def fake_stream(*args, **kwargs):
            yield {"type": "timeout", "message": "Timeout", "content": "partial"}

        class DummyHandler:
            def __init__(self):
                self.events = []

            def _start_sse(self):
                self.started = True

            def _sse_event(self, evt):
                self.events.append(evt)

            def _build_evolve_prompt(self, *args, **kwargs):
                return "prompt"

        dummy = DummyHandler()
        try:
            server._run_ai_engine_stream = fake_stream
            server.ChatViewerHandler._handle_evolve_stream(dummy, "profile", "all", "7d", "", "auto")
        finally:
            server._run_ai_engine_stream = old_stream

        self.assertEqual(dummy.events, [{"type": "timeout", "message": "Timeout", "content": "partial"}])

    def test_evolve_ai_nonzero_exit_does_not_return_stale_cache(self):
        db.evolve_upsert(
            "profile",
            "all",
            "7d",
            "",
            "auto",
            json.dumps({"categories": [{"title": "stale"}]}),
        )

        old_run = server._run_ai_engine

        def fake_run(*args, **kwargs):
            return "", "engine failed", 1

        class DummyHandler:
            def _build_evolve_prompt(self, *args, **kwargs):
                return "prompt"

            def _evolve_fallback(self, tab, reason):
                return server.ChatViewerHandler._evolve_fallback(self, tab, reason)

        try:
            server._run_ai_engine = fake_run
            data = server.ChatViewerHandler._evolve_via_ai(DummyHandler(), "profile", "all", "7d", "", "auto")
        finally:
            server._run_ai_engine = old_run

        self.assertEqual(data["categories"], [])
        self.assertIn("engine failed", data["_error"])

    def test_twin_ai_stage_timeout_fails_without_stage_done(self):
        old_stream = server._run_ai_engine_stream

        def fake_stream(*args, **kwargs):
            yield {"type": "timeout", "message": "Timeout", "content": "partial"}

        class DummyHandler:
            def __init__(self):
                self.events = []
                self.state = {"run_id": "run_timeout"}
                self.persisted = []

            def _set_twin_run_state(self, **updates):
                self.state.update(updates)

            def _get_twin_run_state(self):
                return self.state

            def _persist_twin_stage(self, *args, **kwargs):
                self.persisted.append((args, kwargs))

            def _sse_event(self, evt):
                self.events.append(evt)

            def _stage_counts(self, stage_num, run_id=""):
                return {}

        dummy = DummyHandler()
        try:
            server._run_ai_engine_stream = fake_stream
            ok = server.ChatViewerHandler._run_twin_ai_stage(dummy, "prompt", "Stage 2", "run_timeout", 2, "auto")
        finally:
            server._run_ai_engine_stream = old_stream

        self.assertFalse(ok)
        self.assertEqual(dummy.state["status"], "timeout")
        self.assertTrue(any(evt.get("type") == "timeout" for evt in dummy.events))
        self.assertFalse(any(evt.get("type") == "stage_done" for evt in dummy.events))


if __name__ == "__main__":
    unittest.main()
