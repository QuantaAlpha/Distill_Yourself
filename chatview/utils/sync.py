"""Safe CLAUDE.md write utility — backup, lock, verify, and cleanup.

Shared by ``chatview/handlers/sync.py`` and ``chatview/handlers/twin.py`` for
all writes to ``~/.claude/CLAUDE.md``.
"""

import fcntl
import shutil
import time
from pathlib import Path
from typing import Optional, Union

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
CLAUDE_MD_PATH = Path.home() / ".claude" / "CLAUDE.md"
BACKUP_SUFFIX = ".bak."
MAX_BACKUP_AGE_DAYS = 7
MAX_BACKUP_COUNT = 5


# ---------------------------------------------------------------------------
# Backup management
# ---------------------------------------------------------------------------


def _backup_path(target_path: Optional[Path] = None, ts: Optional[float] = None) -> Path:
    """Return the backup file path with a timestamp suffix."""
    path = target_path or CLAUDE_MD_PATH
    ts = ts or time.time()
    return path.with_name(f"{path.name}{BACKUP_SUFFIX}{int(ts)}")


def _cleanup_old_backups(
    target_path: Optional[Path] = None,
    max_age_days: int = MAX_BACKUP_AGE_DAYS,
    max_count: int = MAX_BACKUP_COUNT,
) -> int:
    """Clean up backups older than ``max_age_days``, keeping at most ``max_count`` newest.

    Returns the number of backups deleted.
    """
    path = target_path or CLAUDE_MD_PATH
    backup_dir = path.parent
    if not backup_dir.exists():
        return 0

    pattern = f"{path.name}{BACKUP_SUFFIX}*"
    backups: list[tuple[float, Path]] = []
    for p in backup_dir.glob(pattern):
        # Parse timestamp from filename: CLAUDE.md.bak.<timestamp>
        try:
            ts_str = p.name.split(BACKUP_SUFFIX, 1)[1]
            ts = int(ts_str)
            backups.append((ts, p))
        except (ValueError, IndexError):
            continue

    # Sort by timestamp ascending (oldest first)
    backups.sort(key=lambda x: x[0])

    now = time.time()
    cutoff = now - max_age_days * 86400
    deleted = 0

    # Delete files older than max_age_days
    remaining: list[tuple[float, Path]] = []
    for ts, p in backups:
        if ts < cutoff:
            try:
                p.unlink()
                deleted += 1
            except OSError:
                pass
        else:
            remaining.append((ts, p))

    # If we still have more than max_count, delete the oldest
    if len(remaining) > max_count:
        remaining.sort(key=lambda x: x[0])  # oldest first
        for _, p in remaining[:-max_count]:
            try:
                p.unlink()
                deleted += 1
            except OSError:
                pass

    return deleted


# ---------------------------------------------------------------------------
# Safe write
# ---------------------------------------------------------------------------


def _safe_write_claude_md(
    content: str,
    *,
    marker_start: str = "",
    marker_end: str = "",
    verify_markers: bool = True,
    target_path: Optional[Union[str, Path]] = None,
) -> dict:
    """Write ``content`` to ``~/.claude/CLAUDE.md`` with backup, lock, and verification.

    Args:
        content: The new content to write.
        marker_start: Expected marker string that should appear in the written content.
        marker_end: Expected marker string that should appear in the written content.
        verify_markers: If True, verify that ``marker_start`` and ``marker_end`` are
            present after writing. If either is missing, restore from backup and
            raise RuntimeError.
        target_path: Optional destination path. Defaults to ``~/.claude/CLAUDE.md``.

    Returns:
        A dict with keys:
          - "backup_path": Path to the backup file (str) or None.
          - "restored": True if content was restored from backup after failed verification.

    Raises:
        RuntimeError: If verification fails (markers not found) and no backup exists
            to restore from.
        OSError: If file operations fail.
    """
    path = Path(target_path) if target_path else CLAUDE_MD_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Create backup
    backup = _backup_path(path)
    if path.exists():
        shutil.copy2(str(path), str(backup))

    # 2. Acquire exclusive file lock
    lock_path = path.with_name(f".{path.name}.lock")
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            # 3. Write content
            path.write_text(content, encoding="utf-8")

            # 4. Verify markers
            if verify_markers and marker_start and marker_end:
                written = path.read_text(encoding="utf-8")
                if marker_start not in written or marker_end not in written:
                    # Restore from backup
                    if path.exists() and backup.exists():
                        shutil.copy2(str(backup), str(path))
                        raise RuntimeError(
                            f"Verification failed: markers ({marker_start!r}, {marker_end!r}) "
                            f"not found in written content. Restored from {backup}."
                        )
                    raise RuntimeError(
                        f"Verification failed: markers ({marker_start!r}, {marker_end!r}) "
                        f"not found in written content and no backup available."
                    )
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)

    # 5. Clean up old backups (best-effort)
    try:
        _cleanup_old_backups(path)
    except OSError:
        pass

    return {
        "backup_path": str(backup) if backup.exists() else None,
        "restored": False,
    }
