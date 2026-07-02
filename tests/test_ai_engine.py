"""Tests for the AI engine abstraction layer (chatview/ai_engine.py).

Covers Group C — 双引擎适配:
  1. Codex JSONL 错误事件解析抽成可测试的纯函数 _analyze_codex_probe。
  2. stream 热路径不再执行模型级健康检查。
  3. 统一 codex 工具事件解析粒度（file_change / web_search / mcp_tool_call / reasoning）。
"""

import json
import unittest

from chatview import ai_engine


class TestAnalyzeCodexErrorParsing(unittest.TestCase):
    def test_detects_521_error_event(self):
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started"}),
                json.dumps(
                    {"type": "error", "message": "unexpected status 521 from server"}
                ),
            ]
        )
        ok, msg = ai_engine._analyze_codex_probe(stdout, 0)
        self.assertFalse(ok)
        self.assertIn("521", msg)

    def test_detects_turn_failed_event(self):
        stdout = json.dumps(
            {"type": "turn.failed", "error": {"message": "usage limit reached"}}
        )
        ok, msg = ai_engine._analyze_codex_probe(stdout, 0)
        self.assertFalse(ok)
        self.assertIn("usage limit", msg)

    def test_detects_nonzero_returncode(self):
        ok, msg = ai_engine._analyze_codex_probe("", 1)
        self.assertFalse(ok)

    def test_healthy_output_returns_ok(self):
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started"}),
                json.dumps(
                    {"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}
                ),
                json.dumps({"type": "turn.completed", "usage": {}}),
            ]
        )
        ok, msg = ai_engine._analyze_codex_probe(stdout, 0)
        self.assertTrue(ok)


class TestExplicitCodexUnhealthy(unittest.TestCase):
    def test_explicit_codex_starts_without_preflight_probe(self):
        """显式 codex 不应先跑模型级健康检查；真实请求负责返回错误。"""
        inner_called = []

        orig_run = ai_engine.subprocess.run
        orig_inner = ai_engine._run_engine_stream_inner

        def _fake_run(*a, **k):
            raise AssertionError("subprocess.run preflight should not be called")

        def _fake_inner(engine, *a, **k):
            inner_called.append(engine)
            yield {"type": "error", "message": "codex: unexpected status 521"}

        ai_engine.subprocess.run = _fake_run
        ai_engine._run_engine_stream_inner = _fake_inner
        try:
            events = list(
                ai_engine._run_ai_engine_stream_impl(
                    "hi", allow_write=False, timeout=60, engine_override="codex"
                )
            )
        finally:
            ai_engine.subprocess.run = orig_run
            ai_engine._run_engine_stream_inner = orig_inner

        self.assertEqual(inner_called, ["codex"])
        errs = [e for e in events if e.get("type") == "error"]
        self.assertTrue(errs, f"expected an error event, got {events}")
        self.assertIn("521", errs[0].get("message", ""))

    def test_auto_codex_starts_without_preflight_probe(self):
        """auto 选中 codex 后也不应先跑模型级健康检查。"""
        inner_called = []

        orig_run = ai_engine.subprocess.run
        orig_inner = ai_engine._run_engine_stream_inner
        orig_detect = ai_engine._detect_ai_engine

        ai_engine.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("subprocess.run preflight should not be called")
        )
        ai_engine._detect_ai_engine = lambda: "codex"

        def _fake_inner(engine, *a, **k):
            inner_called.append(engine)
            yield {"type": "done", "content": ""}

        ai_engine._run_engine_stream_inner = _fake_inner
        try:
            list(
                ai_engine._run_ai_engine_stream_impl(
                    "hi", allow_write=False, timeout=60, engine_override="auto"
                )
            )
        finally:
            ai_engine.subprocess.run = orig_run
            ai_engine._run_engine_stream_inner = orig_inner
            ai_engine._detect_ai_engine = orig_detect

        self.assertEqual(inner_called, ["codex"])


class TestCodexToolEventParsing(unittest.TestCase):
    def test_command_execution_started(self):
        line = json.dumps(
            {"type": "item.started", "item": {"type": "command_execution", "command": "ls"}}
        )
        evt = ai_engine._parse_stream_event("codex", line)
        self.assertEqual(evt["type"], "tool")
        self.assertEqual(evt["name"], "Bash")

    def test_file_change_completed(self):
        line = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "file_change",
                    "changes": [{"path": "foo.py", "kind": "edit"}],
                },
            }
        )
        evt = ai_engine._parse_stream_event("codex", line)
        self.assertEqual(evt["type"], "tool")
        self.assertIn(evt["name"], ("Edit", "Write"))
        self.assertIn("foo.py", evt["detail"])

    def test_web_search_event(self):
        line = json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "web_search", "query": "python asyncio"},
            }
        )
        evt = ai_engine._parse_stream_event("codex", line)
        self.assertEqual(evt["type"], "tool")
        self.assertEqual(evt["name"], "WebSearch")
        self.assertIn("asyncio", evt["detail"])

    def test_mcp_tool_call_event(self):
        line = json.dumps(
            {
                "type": "item.started",
                "item": {"type": "mcp_tool_call", "server": "fs", "tool": "read"},
            }
        )
        evt = ai_engine._parse_stream_event("codex", line)
        self.assertEqual(evt["type"], "tool")
        self.assertIn("read", evt["detail"])

    def test_reasoning_emitted_as_text(self):
        line = json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "reasoning", "text": "thinking about it"},
            }
        )
        evt = ai_engine._parse_stream_event("codex", line)
        self.assertEqual(evt["type"], "text")
        self.assertIn("thinking", evt["content"])

    def test_codex_response_item_spawn_agent_becomes_tool_event(self):
        line = json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "arguments": json.dumps(
                        {
                            "agent_type": "explorer",
                            "message": "你是 Chat Viewer Evolve 的子分析 agent。",
                        },
                        ensure_ascii=False,
                    ),
                },
            },
            ensure_ascii=False,
        )
        evt = ai_engine._parse_stream_event("codex", line)
        self.assertEqual(evt["type"], "tool")
        self.assertEqual(evt["name"], "Agent")
        self.assertEqual(evt["status"], "running")
        self.assertIn("spawn_agent", evt["detail"])

    def test_codex_response_item_wait_agent_output_becomes_done_tool_event(self):
        line = json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "output": json.dumps(
                        {
                            "status": {
                                "019f1e69-a8d1": {
                                    "completed": "第一批候选 memory 如下"
                                }
                            }
                        },
                        ensure_ascii=False,
                    ),
                    "call_id": "call_wait",
                },
            },
            ensure_ascii=False,
        )
        evt = ai_engine._parse_stream_event("codex", line)
        self.assertEqual(evt["type"], "tool")
        self.assertEqual(evt["status"], "done")
        self.assertIn("第一批候选", evt["detail"])

    def test_codex_event_msg_agent_message_becomes_text(self):
        line = json.dumps(
            {
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "message": "第二个 agent 的结果也回来了",
                },
            },
            ensure_ascii=False,
        )
        evt = ai_engine._parse_stream_event("codex", line)
        self.assertEqual(evt["type"], "text")
        self.assertIn("第二个 agent", evt["content"])


if __name__ == "__main__":
    unittest.main()
