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
from chatview.commands.retrieval import (
    find_repeats_data,
    is_noise_text,
    read_window_data,
    read_windows_data,
    search_plus_data,
    session_brief_data,
)
from chatview.db import core as dbcore


class RetrievalToolTestCase(unittest.TestCase):
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

    def _args(self, **overrides):
        defaults = {
            "source": "all",
            "project": "",
            "date": "all",
            "limit": 10,
            "json": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def _insert_session(self, sid, title, project, user_texts, assistant_texts=None):
        meta = {
            "id": sid,
            "title": title,
            "date": "2026-07-01",
            "lastDate": "2026-07-01",
            "filePath": f"/tmp/{sid}.jsonl",
            "fileSize": 100,
            "_mtime": 1.0,
            "userMessageCount": len(user_texts),
            "preview": user_texts[0]["text"] if user_texts else "",
            "project": project,
            "projectName": project,
            "source": "codex",
        }
        db.upsert_session(meta, user_texts, assistant_texts or [])


class TestSearchPlusData(RetrievalToolTestCase):
    def test_finds_chinese_synonym_query_that_plain_fts_misses(self):
        self._insert_session(
            "memory-scope",
            "Memory preference sync",
            "distill-yourself",
            [
                {
                    "idx": 0,
                    "text": "请把我的偏好写入 memory，之后回答要先确认 scope，不要擅自扩大范围。",
                    "ts": "2026-07-01T10:00:00Z",
                }
            ],
        )
        self._insert_session(
            "frontend-check",
            "Frontend verification",
            "claude_chat_view",
            [
                {
                    "idx": 0,
                    "text": "这个改动需要用 Playwright 截图验证移动端和桌面端。",
                    "ts": "2026-07-01T11:00:00Z",
                }
            ],
        )

        plain = db.search_fts("记忆偏好", limit=10)
        self.assertEqual(plain, [])

        results = search_plus_data("记忆偏好", self._args())

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["sessionId"], "memory-scope")
        self.assertGreater(results[0]["score"], 0)
        self.assertIn("token", ",".join(results[0]["reasons"]))

    def test_title_project_matches_are_returned_when_content_does_not_match(self):
        self._insert_session(
            "title-only",
            "Review PR title from legacy cache",
            "distill-yourself",
            [{"idx": 0, "text": "No matching acronym in this message", "ts": "2026-07-01T10:00:00Z"}],
        )

        results = search_plus_data("PR", self._args())

        self.assertTrue(any(r["sessionId"] == "title-only" for r in results))
        row = next(r for r in results if r["sessionId"] == "title-only")
        self.assertIn("title_project", row["reasons"])

    def test_marks_agent_artifacts_without_hard_filtering(self):
        self._insert_session(
            "agent-artifact",
            "You are Agent 1 for Chat Viewer Evolve memory extraction",
            "claude_chat_view",
            [
                {
                    "idx": 0,
                    "text": "Digest points to repeated correction clusters around 过度设计 and workflow misses.",
                    "ts": "2026-07-01T10:00:00Z",
                }
            ],
        )
        self._insert_session(
            "real-user-signal",
            "Real correction",
            "claude_chat_view",
            [
                {
                    "idx": 0,
                    "text": "不要过度设计，也别新增没有要求的抽象；最小改动即可。",
                    "ts": "2026-07-01T11:00:00Z",
                }
            ],
        )

        results = search_plus_data("不要 过度设计", self._args())
        ids = [r["sessionId"] for r in results]

        self.assertLess(ids.index("real-user-signal"), ids.index("agent-artifact"))
        artifact = next(r for r in results if r["sessionId"] == "agent-artifact")
        self.assertEqual(artifact["artifactReason"], "agent_prompt")

    def test_skips_token_scan_when_exact_clean_user_matches_are_enough(self):
        self._insert_session(
            "exact-a",
            "Exact preference A",
            "distill-yourself",
            [{
                "idx": 0,
                "text": "不要过度设计，先用最小方案验证。",
                "ts": "2026-07-01T10:00:00Z",
            }],
        )
        self._insert_session(
            "exact-b",
            "Exact preference B",
            "distill-yourself",
            [{
                "idx": 0,
                "text": "不要过度设计，也不要引入额外框架。",
                "ts": "2026-07-01T11:00:00Z",
            }],
        )

        with patch("chatview.db.query_in_chunks", side_effect=AssertionError("token scan should be skipped")):
            results = search_plus_data("不要过度设计", self._args(limit=20))

        self.assertEqual({r["sessionId"] for r in results[:2]}, {"exact-a", "exact-b"})

    def test_exact_user_evidence_ranks_above_assistant_echo(self):
        self._insert_session(
            "user-evidence",
            "User preference",
            "distill-yourself",
            [{
                "idx": 0,
                "text": "不要过度设计，保持最小改动。",
                "ts": "2026-07-01T10:00:00Z",
            }],
        )
        self._insert_session(
            "assistant-echo",
            "Assistant echo",
            "distill-yourself",
            [],
            [{
                "idx": 0,
                "text": "我会遵守：不要过度设计，保持最小改动。",
                "ts": "2026-07-01T11:00:00Z",
            }],
        )

        results = search_plus_data("不要过度设计", self._args(limit=10))

        self.assertEqual(results[0]["sessionId"], "user-evidence")
        self.assertEqual(results[0]["role"], "user")


class TestFindRepeatsData(RetrievalToolTestCase):
    def test_promotes_anchored_direct_tasks_and_demotes_generic_research_matches(self):
        duplicate_text = (
            "现在有一个任务，你派多个子agent，还有CodeX去充分地搜索AutoResearch这块的最新工作。"
            "就是Agent层面的AutoResearch，如何自动实验、自进化、自己完成复杂任务。"
        )
        self._insert_session(
            "direct-a",
            "AutoResearch task",
            "research/auto",
            [{"idx": 0, "text": duplicate_text, "ts": "2026-07-01T10:00:00Z"}],
        )
        self._insert_session(
            "direct-b",
            "AutoResearch task duplicate",
            "research/auto",
            [{"idx": 0, "text": duplicate_text, "ts": "2026-07-01T11:00:00Z"}],
        )
        self._insert_session(
            "generic-workflow",
            "Finance research workflow",
            "finance/invest",
            [{
                "idx": 0,
                "text": (
                    "research/{股票代码}__{研究任务id}/manifest.json，"
                    "你自己维护 research_log 和 evidence_refs。"
                ),
                "ts": "2026-07-01T12:00:00Z",
            }],
        )
        self._insert_session(
            "artifact",
            "Tool notification",
            "research/auto",
            [{
                "idx": 0,
                "text": "<output-file>/tmp/auto-research/tasks/x.output</output-file> Background command \"Codex deep research\"",
                "ts": "2026-07-01T13:00:00Z",
            }],
        )

        data = find_repeats_data("你自己做auto research", self._args(limit=10))

        strong_ids = {
            example["sessionId"]
            for cluster in data["buckets"]["strong_evidence"]
            for example in cluster["examples"]
        }
        weak_ids = {
            example["sessionId"]
            for cluster in data["buckets"]["weak_matches"]
            for example in cluster["examples"]
        }
        artifact_ids = {
            example["sessionId"]
            for cluster in data["buckets"]["artifacts"]
            for example in cluster["examples"]
        }

        self.assertIn("direct-a", strong_ids)
        self.assertIn("generic-workflow", weak_ids)
        self.assertIn("artifact", artifact_ids)
        top = data["buckets"]["strong_evidence"][0]
        self.assertEqual(top["support"], 2)
        self.assertEqual(top["episodeSupport"], 1)
        self.assertTrue(top["memoryEligible"])
        self.assertIn("topic_anchor", top["whyRanked"]["matchedSlots"])

    def test_title_only_topic_anchor_does_not_promote_generic_message_to_strong(self):
        self._insert_session(
            "title-anchor-only",
            "Stream async results during auto-research execution",
            "claude-chat-view",
            [{
                "idx": 0,
                "text": "你自己测试一下，这样改了之后数据维度有没有变得更加丰富。",
                "ts": "2026-07-01T10:00:00Z",
            }],
        )

        data = find_repeats_data("你自己做auto research", self._args(limit=10))

        strong_ids = {
            example["sessionId"]
            for cluster in data["buckets"]["strong_evidence"]
            for example in cluster["examples"]
        }
        related_ids = {
            example["sessionId"]
            for cluster in data["buckets"]["related_context"]
            for example in cluster["examples"]
        }
        self.assertNotIn("title-anchor-only", strong_ids)
        self.assertIn("title-anchor-only", related_ids)

    def test_chinese_subagent_instruction_is_marked_as_artifact(self):
        self._insert_session(
            "subagent-prompt",
            "梳理 Agentic AutoResearch 架构",
            "research/auto",
            [{
                "idx": 0,
                "text": (
                    "你是技术架构梳理子 agent。任务：不要写泛泛趋势，请从技术机制角度梳理 "
                    "Agentic AutoResearch 的典型架构，到自进化、评估器和执行沙盒。"
                ),
                "ts": "2026-07-01T10:00:00Z",
            }],
        )

        data = find_repeats_data("你自己做auto research", self._args(limit=10))

        artifact_ids = {
            example["sessionId"]
            for cluster in data["buckets"]["artifacts"]
            for example in cluster["examples"]
        }
        strong_ids = {
            example["sessionId"]
            for cluster in data["buckets"]["strong_evidence"]
            for example in cluster["examples"]
        }
        self.assertIn("subagent-prompt", artifact_ids)
        self.assertNotIn("subagent-prompt", strong_ids)

    def test_agent_status_update_is_not_strong_user_evidence(self):
        self._insert_session(
            "agent-status",
            "更新AutoResearch故事版HTML",
            "research/auto",
            [{
                "idx": 0,
                "text": (
                    "我已经派了 3 个并行子 agent：一个看 AI Scientist/自动实验，一个看工程代码代理与长程任务，"
                    "一个看系统架构模块。它们跑的时候我先拆现有 HTML。"
                ),
                "ts": "2026-07-01T10:00:00Z",
            }],
        )

        data = find_repeats_data("你自己做auto research", self._args(limit=10))

        strong_ids = {
            example["sessionId"]
            for cluster in data["buckets"]["strong_evidence"]
            for example in cluster["examples"]
        }
        related_ids = {
            example["sessionId"]
            for cluster in data["buckets"]["related_context"]
            for example in cluster["examples"]
        }
        self.assertNotIn("agent-status", strong_ids)
        self.assertIn("agent-status", related_ids)


class TestReadWindowData(RetrievalToolTestCase):
    def test_returns_messages_around_requested_index(self):
        self._insert_session(
            "window-session",
            "Window",
            "distill-yourself",
            [
                {"idx": 0, "text": "first user", "ts": "2026-07-01T10:00:00Z"},
                {"idx": 2, "text": "second user correction", "ts": "2026-07-01T10:02:00Z"},
            ],
            [
                {"idx": 1, "text": "assistant answer", "ts": "2026-07-01T10:01:00Z"},
                {"idx": 3, "text": "assistant fix", "ts": "2026-07-01T10:03:00Z"},
            ],
        )

        data = read_window_data("window-session", idx=2, radius=1)

        self.assertEqual(data["sessionId"], "window-session")
        self.assertEqual([m["idx"] for m in data["messages"]], [1, 2, 3])
        self.assertEqual([m["role"] for m in data["messages"]], ["assistant", "user", "assistant"])

    def test_reads_window_without_loading_full_session(self):
        self._insert_session(
            "window-session",
            "Window",
            "distill-yourself",
            [
                {"idx": 0, "text": "first user", "ts": "2026-07-01T10:00:00Z"},
                {"idx": 2, "text": "second user correction", "ts": "2026-07-01T10:02:00Z"},
            ],
            [
                {"idx": 1, "text": "assistant answer", "ts": "2026-07-01T10:01:00Z"},
                {"idx": 3, "text": "assistant fix", "ts": "2026-07-01T10:03:00Z"},
            ],
        )

        with patch("chatview.db.get_session_messages", side_effect=AssertionError("full session load")):
            data = read_window_data("window-session", idx=2, radius=1)

        self.assertEqual([m["idx"] for m in data["messages"]], [1, 2, 3])

    def test_batch_returns_multiple_windows(self):
        self._insert_session(
            "window-session",
            "Window",
            "distill-yourself",
            [
                {"idx": 0, "text": "first user", "ts": "2026-07-01T10:00:00Z"},
                {"idx": 2, "text": "second user correction", "ts": "2026-07-01T10:02:00Z"},
            ],
            [
                {"idx": 1, "text": "assistant answer", "ts": "2026-07-01T10:01:00Z"},
                {"idx": 3, "text": "assistant fix", "ts": "2026-07-01T10:03:00Z"},
            ],
        )

        data = read_windows_data([
            {"session": "window-session", "idx": 0, "radius": 0},
            {"session": "window-session", "idx": 2, "radius": 1},
        ])

        self.assertEqual(len(data["windows"]), 2)
        self.assertEqual([m["idx"] for m in data["windows"][0]["messages"]], [0])
        self.assertEqual([m["idx"] for m in data["windows"][1]["messages"]], [1, 2, 3])


class TestSessionBriefData(RetrievalToolTestCase):
    def test_returns_compact_session_summary_and_noise_counts(self):
        self._insert_session(
            "brief-session",
            "Brief me",
            "distill-yourself",
            [
                {"idx": 0, "text": "请先分析历史偏好，再给我一个结论。", "ts": "2026-07-01T10:00:00Z"},
                {"idx": 2, "text": "<task-notification>toolu_123</task-notification>", "ts": "2026-07-01T10:02:00Z"},
                {"idx": 3, "text": "不要展开太多，保留证据就好。", "ts": "2026-07-01T10:03:00Z"},
            ],
            [
                {"idx": 1, "text": "我会先看证据。", "ts": "2026-07-01T10:01:00Z"},
            ],
        )

        data = session_brief_data("brief-session", self._args(limit=3))

        self.assertEqual(data["sessionId"], "brief-session")
        self.assertEqual(data["counts"]["user"], 3)
        self.assertEqual(data["counts"]["assistant"], 1)
        self.assertEqual(data["counts"]["artifacts"], 1)
        self.assertEqual([m["idx"] for m in data["userMessages"]], [0, 3])
        self.assertEqual(data["lastUserMessage"]["idx"], 3)


class TestNoiseText(unittest.TestCase):
    def test_flags_system_and_tool_noise(self):
        self.assertTrue(is_noise_text("<task-notification>\n<task-id>x</task-id>\ntoolu_123"))
        self.assertTrue(is_noise_text("This session is being continued from a previous conversation.\nSummary:"))
        self.assertTrue(is_noise_text("You are independently re-testing a frontend optimization."))
        self.assertTrue(is_noise_text("You are Agent 1 for Chat Viewer Evolve memory extraction."))
        self.assertTrue(is_noise_text("你是一个严格、独立的标注员。任务：判断每条用户消息是否在纠正 AI。"))
        self.assertTrue(is_noise_text("x" * 2000 + "Pre-collected Data (do NOT re-run these)"))
        self.assertTrue(is_noise_text("pre-computed project distribution + daily activity as JSON\n=== STATS ==="))

    def test_keeps_real_user_preference_signal(self):
        self.assertFalse(is_noise_text("不要过度设计，也别新增没有要求的抽象；最小改动即可。"))


if __name__ == "__main__":
    unittest.main()
