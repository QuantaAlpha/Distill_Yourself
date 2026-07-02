import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chatview import cli_resolver


class TestCliResolver(unittest.TestCase):
    def setUp(self):
        cli_resolver.clear_cli_resolution_cache()

    def tearDown(self):
        cli_resolver.clear_cli_resolution_cache()

    def _make_executable(self, directory: Path, name: str) -> Path:
        path = directory / name
        path.write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_common_path_finds_claude_when_process_path_misses_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "miniconda3" / "bin"
            bin_dir.mkdir(parents=True)
            expected = self._make_executable(bin_dir, "claude")

            with patch.object(cli_resolver, "_home", return_value=Path(tmp)), patch.dict(
                os.environ, {"PATH": "/usr/bin:/bin"}, clear=False
            ):
                self.assertEqual(cli_resolver.resolve_cli_path("claude"), str(expected))

    def test_common_path_hit_does_not_start_login_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "miniconda3" / "bin"
            bin_dir.mkdir(parents=True)
            expected = self._make_executable(bin_dir, "claude")

            with patch.object(cli_resolver, "_home", return_value=Path(tmp)), patch.dict(
                os.environ, {"PATH": "/usr/bin:/bin"}, clear=False
            ), patch.object(
                cli_resolver,
                "_login_shell_candidates",
                side_effect=AssertionError("login shell should not run"),
            ):
                self.assertEqual(cli_resolver.resolve_cli_path("claude"), str(expected))

    def test_env_path_takes_precedence_over_common_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_bin = root / "env" / "bin"
            common_bin = root / "miniconda3" / "bin"
            env_bin.mkdir(parents=True)
            common_bin.mkdir(parents=True)
            expected = self._make_executable(env_bin, "claude")
            self._make_executable(common_bin, "claude")

            with patch.object(cli_resolver, "_home", return_value=root), patch.dict(
                os.environ,
                {"CHATVIEW_CLAUDE_BIN": str(expected), "PATH": "/usr/bin:/bin"},
                clear=False,
            ):
                self.assertEqual(cli_resolver.resolve_cli_path("claude"), str(expected))

    def test_auth_status_uses_lightweight_commands(self):
        calls = []

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return Result()

        with tempfile.TemporaryDirectory() as tmp:
            path = self._make_executable(Path(tmp), "codex")
            with patch.object(cli_resolver, "resolve_cli_path", return_value=str(path)), patch(
                "subprocess.run", side_effect=fake_run
            ):
                status = cli_resolver.get_cli_status("codex")

        self.assertTrue(status["ok"])
        self.assertEqual(calls, [[str(path), "--version"], [str(path), "login", "status"]])


if __name__ == "__main__":
    unittest.main()
