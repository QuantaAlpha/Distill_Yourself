#!/usr/bin/env python3
"""Diagnose local Claude/Codex CLI resolution without model calls.

This script intentionally only runs local discovery commands and `--version`.
It does not run `claude -p` or `codex exec`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


ENGINE_ENV_VARS = {
    "claude": ("CHATVIEW_CLAUDE_BIN", "CLAUDE_BIN"),
    "codex": ("CHATVIEW_CODEX_BIN", "CODEX_BIN"),
}

ENGINE_BIN_NAMES = {
    "claude": ("claude",),
    "codex": ("codex",),
}


@dataclass(frozen=True)
class Candidate:
    path: str
    source: str


def _home() -> Path:
    return Path.home()


def _common_bin_dirs() -> list[Path]:
    home = _home()
    dirs = [
        home / ".local" / "bin",
        home / ".npm-global" / "bin",
        home / "miniconda3" / "bin",
        home / "anaconda3" / "bin",
        home / ".volta" / "bin",
        home / ".bun" / "bin",
        home / ".yarn" / "bin",
        home / ".cargo" / "bin",
        home / ".asdf" / "shims",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path("/bin"),
        Path("/Applications/Codex.app/Contents/Resources"),
    ]
    dirs.extend(sorted((home / ".nvm" / "versions" / "node").glob("*/*")))
    dirs.extend(sorted((home / ".fnm" / "node-versions").glob("*/installation/bin")))
    dirs.extend(sorted((home / "miniconda3" / "envs").glob("*/bin")))
    dirs.extend(sorted((home / "anaconda3" / "envs").glob("*/bin")))
    return dirs


def _is_executable(path: str) -> bool:
    return bool(path) and Path(path).is_file() and os.access(path, os.X_OK)


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    seen: set[str] = set()
    result: list[Candidate] = []
    for candidate in candidates:
        key = str(Path(candidate.path).expanduser())
        if key in seen:
            continue
        seen.add(key)
        result.append(Candidate(key, candidate.source))
    return result


def _discover_with_login_shell(engine: str, timeout: float) -> list[Candidate]:
    shells = []
    for shell in (os.environ.get("SHELL"), "/bin/zsh", "/bin/bash"):
        if shell and shell not in shells and _is_executable(shell):
            shells.append(shell)

    candidates: list[Candidate] = []
    for shell in shells:
        try:
            proc = subprocess.run(
                [shell, "-ilc", f"command -v {engine}"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in (proc.stdout or "").splitlines():
            path = line.strip()
            if path:
                candidates.append(Candidate(path, f"login shell: {shell}"))
    return candidates


def collect_candidates(
    engine: str, *, include_login_shell: bool, shell_timeout: float
) -> list[Candidate]:
    candidates: list[Candidate] = []

    for env_name in ENGINE_ENV_VARS[engine]:
        value = os.environ.get(env_name, "").strip()
        if value:
            candidates.append(Candidate(value, f"env {env_name}"))

    path_hit = shutil.which(engine)
    if path_hit:
        candidates.append(Candidate(path_hit, "process PATH"))

    for directory in _common_bin_dirs():
        for bin_name in ENGINE_BIN_NAMES[engine]:
            candidates.append(Candidate(str(directory / bin_name), "common path"))

    if include_login_shell:
        candidates.extend(_discover_with_login_shell(engine, shell_timeout))

    return _dedupe(candidates)


def check_version(path: str, timeout: float) -> tuple[bool, float, int | None, str]:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.perf_counter() - started
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode == 0, elapsed, proc.returncode, output
    except (OSError, subprocess.TimeoutExpired) as exc:
        elapsed = time.perf_counter() - started
        return False, elapsed, None, str(exc)


def diagnose_engine(
    engine: str, *, include_login_shell: bool, shell_timeout: float, version_timeout: float
) -> bool:
    print(f"\n== {engine} ==")
    candidates = collect_candidates(
        engine, include_login_shell=include_login_shell, shell_timeout=shell_timeout
    )
    if not candidates:
        print("no candidates found")
        return False

    selected = None
    for candidate in candidates:
        exists = Path(candidate.path).exists()
        executable = _is_executable(candidate.path)
        mark = "candidate"
        if executable and selected is None:
            selected = candidate
            mark = "selected"
        print(f"{mark:9} {candidate.path} [{candidate.source}] exists={exists} executable={executable}")

    if selected is None:
        print("result: FAIL no executable candidate")
        return False

    ok, elapsed, rc, output = check_version(selected.path, version_timeout)
    output = output.replace("\n", " ")[:500]
    print(f"version: ok={ok} rc={rc} elapsed={elapsed:.3f}s output={output}")
    print(f"result: {'OK' if ok else 'FAIL'} selected={selected.path}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Claude/Codex CLI discovery without running model calls."
    )
    parser.add_argument(
        "--no-login-shell",
        action="store_true",
        help="Skip zsh/bash login-shell discovery.",
    )
    parser.add_argument("--shell-timeout", type=float, default=2.0)
    parser.add_argument("--version-timeout", type=float, default=5.0)
    args = parser.parse_args()

    print(f"cwd: {Path.cwd()}")
    print(f"SHELL: {os.environ.get('SHELL', '')}")
    print(f"PATH: {os.environ.get('PATH', '')}")

    include_login_shell = not args.no_login_shell
    results = [
        diagnose_engine(
            engine,
            include_login_shell=include_login_shell,
            shell_timeout=args.shell_timeout,
            version_timeout=args.version_timeout,
        )
        for engine in ("claude", "codex")
    ]
    return 0 if any(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
