"""Tests for evolve stream handler behavior.

Ported from main with adaptations for integrate's DB API and stream semantics:

- Integrate uses evolve_run_start/evolve_run_update for run lifecycle tracking.
- Integrate does NOT short-circuit the stream on first DB write: it drains the
  full stream then emits evolve_result once after stream_finished.
- Accordingly, the early-result test is replaced with an after-stream test.
"""

import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from chatview import db
from chatview.db import core as _dbcore
from chatview.handlers import evolve


class _FakeHandler:
    def __init__(self):
        self.wfile = io.BytesIO()
        self.status = None
        self.headers = []

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.headers.append((key, value))

    def end_headers(self):
        pass


class _FakeStream:
    """Simulates an AI stream that writes to evolve_cache mid-stream and then finishes."""

    def __init__(self):
        self.closed = False

    def __iter__(self):
        yield {"type": "text", "content": "before write"}
        db.evolve_upsert(
            "memory",
            "all",
            "7d",
            "",
            "codex",
            json.dumps({"nodes": [{"id": "m1", "label": "done"}], "links": [], "cards": []}),
        )
        yield {"type": "tool", "name": "Bash", "status": "done", "detail": "OK: replace memory"}
        yield {"type": "text", "content": "post-write lingering analysis"}

    def close(self):
        self.closed = True


class TestEvolveStream(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.orig_db_path = _dbcore.DB_PATH
        self.orig_cache_dir = _dbcore.CACHE_DIR
        _dbcore.CACHE_DIR = Path(self.tmpdir.name)
        _dbcore.DB_PATH = Path(self.tmpdir.name) / "sessions.db"
        _dbcore._local = threading.local()
        db.init_db()

    def tearDown(self):
        _dbcore.DB_PATH = self.orig_db_path
        _dbcore.CACHE_DIR = self.orig_cache_dir
        _dbcore._local = threading.local()
        self.tmpdir.cleanup()

    def test_evolve_stream_emits_result_after_full_stream_completes(self):
        """After stream finishes, handler reads DB and emits evolve_result SSE event.

        Integrate drains the full stream (no early exit on write), then emits
        evolve_result once after stream_finished=True.
        """
        handler = _FakeHandler()
        stream = _FakeStream()

        with patch.object(evolve, "_build_evolve_prompt", return_value="prompt"), \
             patch.object(evolve, "_run_ai_engine_stream", return_value=stream):
            evolve._handle_evolve_stream(handler, "memory", "all", "7d", "", "codex", "zh")

        body = handler.wfile.getvalue().decode("utf-8")
        self.assertIn('"type": "evolve_result"', body)
        self.assertIn('"id": "m1"', body)
        # Unlike main, integrate drains the full stream before emitting result,
        # so post-write events do appear in the SSE output.
        self.assertTrue(stream.closed)

    def test_evolve_stream_closes_stream_on_completion(self):
        """Stream.close() is always called after _handle_evolve_stream returns."""
        handler = _FakeHandler()
        stream = _FakeStream()

        with patch.object(evolve, "_build_evolve_prompt", return_value="prompt"), \
             patch.object(evolve, "_run_ai_engine_stream", return_value=stream):
            evolve._handle_evolve_stream(handler, "memory", "all", "7d", "", "codex", "zh")

        self.assertTrue(stream.closed)

    def test_evolve_stream_persists_to_db_even_if_client_disconnects(self):
        """When client disconnects (BrokenPipeError on send), stream is still drained
        and the result is persisted to DB."""

        class _BrokenAfterFirstWfile:
            """File-like object that raises BrokenPipeError after first write."""
            def __init__(self):
                self._writes = 0

            def write(self, data):
                self._writes += 1
                if self._writes > 1:
                    raise BrokenPipeError("client gone")
                return len(data)

            def flush(self):
                pass

        handler = _FakeHandler()
        handler.wfile = _BrokenAfterFirstWfile()
        stream = _FakeStream()

        with patch.object(evolve, "_build_evolve_prompt", return_value="prompt"), \
             patch.object(evolve, "_run_ai_engine_stream", return_value=stream):
            evolve._handle_evolve_stream(handler, "memory", "all", "7d", "", "codex", "zh")

        # DB should still have the result regardless of client disconnect
        row = db.evolve_get("memory", "all", "7d", "", "codex")
        self.assertIsNotNone(row)
        self.assertEqual(row["data"]["nodes"][0]["id"], "m1")
        self.assertTrue(stream.closed)

    def test_evolve_stream_persists_events_for_replay(self):
        """Every streamed evolve event is persisted so a refreshed page can replay it."""

        class _ReplayStream:
            def close(self):
                self.closed = True

            def __iter__(self):
                yield {"type": "tool", "name": "Bash", "status": "running"}
                yield {"type": "text", "content": "thinking"}
                db.evolve_upsert(
                    "memory",
                    "all",
                    "7d",
                    "",
                    "codex",
                    json.dumps({"nodes": [{"id": "m1"}], "links": [], "cards": []}),
                )

        handler = _FakeHandler()
        stream = _ReplayStream()

        with patch.object(evolve, "_build_evolve_prompt", return_value="prompt"), \
             patch.object(evolve, "_run_ai_engine_stream", return_value=stream):
            evolve._handle_evolve_stream(handler, "memory", "all", "7d", "", "codex", "zh")

        runs = db.evolve_runs_latest_for_scope("all", "7d", "", "codex")
        run_id = runs["memory"]["run_id"]
        events = db.evolve_run_events(run_id)
        self.assertEqual(
            [entry["event"]["type"] for entry in events],
            ["run", "tool", "text", "evolve_result"],
        )
        self.assertEqual([entry["event_index"] for entry in events], [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
