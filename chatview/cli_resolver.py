"""Resolve local AI CLI binaries and lightweight availability status."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path


_CACHE_TTL_SECONDS = 300
_PATH_CACHE: dict[str, tuple[float, str]] = {}
_STATUS_CACHE: dict[str, tuple[float, dict]] = {}

_ENGINE_ENV_VARS = {
    "claude": ("CHATVIEW_CLAUDE_BIN", "CLAUDE_BIN"),
    "codex": ("CHATVIEW_CODEX_BIN", "CODEX_BIN"),
}

_AUTH_COMMANDS = {
    "claude": ("auth", "status", "--json"),
    "codex": ("login", "status"),
}


def clear_cli_resolution_cache():
    """Clear cached CLI path and status data."""
    _PATH_CACHE.clear()
    _STATUS_CACHE.clear()


def _home() -> Path:
    return Path.home()


def _is_executable(path: str) -> bool:
    return bool(path) and Path(path).is_file() and os.access(path, os.X_OK)


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
    dirs.extend(sorted((home / ".nvm" / "versions" / "node").glob("*/bin")))
    dirs.extend(sorted((home / ".fnm" / "node-versions").glob("*/installation/bin")))
    dirs.extend(sorted((home / "miniconda3" / "envs").glob("*/bin")))
    dirs.extend(sorted((home / "anaconda3" / "envs").glob("*/bin")))
    return dirs


def _login_shell_candidates(engine: str, timeout: float = 2.0) -> list[str]:
    shells = []
    for shell in (os.environ.get("SHELL"), "/bin/zsh", "/bin/bash"):
        if shell and shell not in shells and _is_executable(shell):
            shells.append(shell)

    candidates = []
    for shell in shells:
        try:
            result = subprocess.run(
                [shell, "-ilc", f"command -v {engine}"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        candidates.extend(
            line.strip() for line in (result.stdout or "").splitlines() if line.strip()
        )
    return candidates


def _candidate_paths(engine: str, include_login_shell: bool = True) -> list[str]:
    if engine not in _ENGINE_ENV_VARS:
        raise ValueError(f"Invalid AI engine: {engine}")

    candidates = []
    for env_name in _ENGINE_ENV_VARS[engine]:
        value = os.environ.get(env_name, "").strip()
        if value:
            candidates.append(value)

    path_hit = shutil.which(engine)
    if path_hit:
        candidates.append(path_hit)

    candidates.extend(str(directory / engine) for directory in _common_bin_dirs())

    if include_login_shell:
        candidates.extend(_login_shell_candidates(engine))

    seen = set()
    deduped = []
    for candidate in candidates:
        path = str(Path(candidate).expanduser())
        if path not in seen:
            seen.add(path)
            deduped.append(path)
    return deduped


def resolve_cli_path(engine: str, *, include_login_shell: bool = True) -> str:
    """Return the executable path for an AI CLI, or an empty string."""
    now = time.time()
    cached = _PATH_CACHE.get(engine)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    for candidate in _candidate_paths(engine, include_login_shell=False):
        if _is_executable(candidate):
            _PATH_CACHE[engine] = (now, candidate)
            return candidate

    if include_login_shell:
        for candidate in _login_shell_candidates(engine):
            if _is_executable(candidate):
                _PATH_CACHE[engine] = (now, candidate)
                return candidate

    _PATH_CACHE[engine] = (now, "")
    return ""


def _run_local_check(cmd: list[str], timeout: float) -> tuple[bool, int | None, str, float]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.perf_counter() - started
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        return result.returncode == 0, result.returncode, output, elapsed
    except (OSError, subprocess.TimeoutExpired) as exc:
        elapsed = time.perf_counter() - started
        return False, None, str(exc), elapsed


def get_cli_status(engine: str, *, use_cache: bool = True) -> dict:
    """Return lightweight local CLI status.

    This intentionally uses only `--version` and auth-status subcommands. It
    does not run model-backed commands such as `claude -p` or `codex exec`.
    """
    now = time.time()
    cached = _STATUS_CACHE.get(engine)
    if use_cache and cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return dict(cached[1])

    path = resolve_cli_path(engine)
    status = {
        "engine": engine,
        "path": path,
        "installed": bool(path),
        "version_ok": False,
        "auth_ok": False,
        "ok": False,
        "version": "",
        "auth_message": "",
        "version_latency_ms": 0,
        "auth_latency_ms": 0,
    }
    if not path:
        _STATUS_CACHE[engine] = (now, status)
        return dict(status)

    version_ok, _, version_output, version_elapsed = _run_local_check(
        [path, "--version"], timeout=5
    )
    status["version_ok"] = version_ok
    status["version"] = version_output.splitlines()[0] if version_output else ""
    status["version_latency_ms"] = int(version_elapsed * 1000)

    auth_cmd = [path, *_AUTH_COMMANDS[engine]]
    auth_ok, _, auth_output, auth_elapsed = _run_local_check(auth_cmd, timeout=5)
    status["auth_ok"] = auth_ok
    status["auth_message"] = auth_output[:300]
    status["auth_latency_ms"] = int(auth_elapsed * 1000)
    status["ok"] = bool(status["installed"] and status["version_ok"] and status["auth_ok"])

    _STATUS_CACHE[engine] = (now, status)
    return dict(status)
