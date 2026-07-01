"""Evolve sync helper functions — memory and profile sync to Claude Code.

Extracted from server.py — pure Python format conversion, no HTTP handler needed.
"""

import re
from pathlib import Path

from chatview.utils.sync import _safe_write_claude_md

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CLAUDE_MD_PATH = Path.home() / ".claude" / "CLAUDE.md"
MEMORY_DIR = Path.home() / ".claude" / "memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
MEMORY_FILE = MEMORY_DIR / "evolve_sync.md"
MEMORY_MARKER_START = "<!-- evolve-sync:memory:start -->"
MEMORY_MARKER_END = "<!-- evolve-sync:memory:end -->"
SYNC_MARKER_START = "<!-- evolve-sync:profile:start -->"
SYNC_MARKER_END = "<!-- evolve-sync:profile:end -->"
RULES_MARKER_START = "<!-- evolve-sync:rules:start -->"
RULES_MARKER_END = "<!-- evolve-sync:rules:end -->"


def _sanitize_filename(text: str) -> str:
    """Convert text to a safe filename component."""
    clean = re.sub(r'[^\w\u4e00-\u9fff-]', '_', text)
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean[:60] if clean else "unnamed"


# ── Memory sync (single file) ──────────────────────────────────────────────

def _build_memory_section(mem_data: dict) -> str:
    """Build the full memory section content from evolve memory data."""
    nodes = {n["id"]: n for n in mem_data.get("nodes", [])}
    cards = {c["id"]: c for c in mem_data.get("cards", [])}

    lines = [MEMORY_MARKER_START, "---",
             "name: evolve-sync-memory",
             "description: Evolve AI 分析提取的用户偏好与行为模式",
             "type: feedback",
             "source: evolve-sync",
             "---", ""]

    count = 0
    for nid, node in nodes.items():
        if node.get("confidence") == "low" or node.get("status") == "stale":
            continue

        card = cards.get(nid, {})
        label = node.get("label", "")
        trigger = card.get("trigger", "")
        instruction = card.get("instruction", "")
        avoid = card.get("avoid", "")

        lines.append(f"### {label}")
        if trigger and instruction:
            lines.append(f"When: {trigger}")
            lines.append(f"Do: {instruction}")
            if avoid:
                lines.append(f"Avoid: {avoid}")
        else:
            body = card.get("content", label)
            if body and body != label:
                lines.append(body)

        # Evidence (compact)
        evidence = card.get("evidence", "")
        if isinstance(evidence, list) and evidence:
            for ev in evidence[:2]:
                if isinstance(ev, dict):
                    lines.append(f'- "{ev.get("quote", "")}" ({ev.get("date", "")})')
                else:
                    lines.append(f"- {ev}")

        # Meta (one line)
        meta = []
        if node.get("frequency"):
            meta.append(f"频次:{node['frequency']}")
        if node.get("priority"):
            meta.append(f"{node['priority']}")
        if card.get("lastSeen"):
            meta.append(f"最近:{card['lastSeen']}")
        if meta:
            lines.append(f"*{' | '.join(meta)}*")

        lines.append("")
        count += 1

    lines.append(MEMORY_MARKER_END)
    return "\n".join(lines) + "\n", count


def _evolve_sync_memory_preview(mem_data: dict) -> dict:
    """Generate preview of what memory sync would do."""
    section, count = _build_memory_section(mem_data)

    fpath = MEMORY_FILE
    current = fpath.read_text(encoding="utf-8") if fpath.exists() else ""

    if MEMORY_MARKER_START in current and MEMORY_MARKER_END in current:
        status = "replace"
    elif fpath.exists():
        status = "append"
    else:
        status = "create"

    diff = _build_sync_diff(fpath, MEMORY_MARKER_START, MEMORY_MARKER_END, section)

    return {
        "summary": {"items": count, "status": status},
        "diff": diff,
    }


def _evolve_sync_memory_execute(mem_data: dict) -> dict:
    """Write memory to single file."""
    section, count = _build_memory_section(mem_data)

    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    fpath = MEMORY_FILE

    if fpath.exists():
        existing = fpath.read_text(encoding="utf-8")
    else:
        existing = ""

    if MEMORY_MARKER_START in existing and MEMORY_MARKER_END in existing:
        start_idx = existing.index(MEMORY_MARKER_START)
        end_idx = existing.index(MEMORY_MARKER_END) + len(MEMORY_MARKER_END)
        new_text = existing[:start_idx] + section + existing[end_idx:]
        status = "replaced"
    elif existing:
        if not existing.endswith("\n\n"):
            existing = existing.rstrip("\n") + "\n\n"
        new_text = existing + section
        status = "appended"
    else:
        new_text = section
        status = "created"

    from chatview.utils.sync import atomic_write_text
    atomic_write_text(fpath, new_text, backup=False)

    # Ensure MEMORY.md index has a pointer
    _update_memory_index_single()

    return {"status": status, "items": count}


def _update_memory_index_single():
    """Ensure evolve_sync.md is listed in MEMORY.md."""
    if not MEMORY_INDEX.exists():
        return
    existing = MEMORY_INDEX.read_text(encoding="utf-8")
    fname = "evolve_sync.md"
    if fname.lower() in existing.lower():
        return
    if not existing.endswith("\n"):
        existing += "\n"
    existing += f"| [{fname}]({fname}) | feedback | Evolve AI 分析提取的用户偏好 |\n"
    from chatview.utils.sync import atomic_write_text
    atomic_write_text(MEMORY_INDEX, existing, backup=False)


# ── Profile sync (CLAUDE.md) ──────────────────────────────────────────────

def _evolve_sync_claude_md_preview(prof_data: dict) -> dict:
    """Generate preview of what CLAUDE.md sync would do."""
    categories = prof_data.get("categories", [])
    radar = prof_data.get("radar", {})
    dims = radar.get("dimensions", [])

    item_count = sum(
        len([i for i in cat.get("items", []) if i.get("confidence") != "low"])
        for cat in categories
    )

    section = _build_profile_section(prof_data)
    line_count = len(section.strip().split("\n"))
    status = "replace" if _claude_md_has_marker() else "append"
    diff = _build_sync_diff(CLAUDE_MD_PATH, SYNC_MARKER_START, SYNC_MARKER_END, section)

    return {
        "status": status,
        "categories": len(categories),
        "radar_dims": len(dims),
        "items": item_count,
        "lines": line_count,
        "diff": diff,
    }


def _evolve_sync_claude_md_execute(prof_data: dict) -> dict:
    """Write profile section to CLAUDE.md."""
    section = _build_profile_section(prof_data)

    CLAUDE_MD_PATH.parent.mkdir(parents=True, exist_ok=True)

    if CLAUDE_MD_PATH.exists():
        existing = CLAUDE_MD_PATH.read_text(encoding="utf-8")
    else:
        existing = ""

    if SYNC_MARKER_START in existing and SYNC_MARKER_END in existing:
        start_idx = existing.index(SYNC_MARKER_START)
        end_idx = existing.index(SYNC_MARKER_END) + len(SYNC_MARKER_END)
        new_text = existing[:start_idx] + section + existing[end_idx:]
        status = "replaced"
    else:
        if existing and not existing.endswith("\n\n"):
            existing = existing.rstrip("\n") + "\n\n"
        new_text = existing + section
        status = "appended"

    _safe_write_claude_md(
        new_text, marker_start=SYNC_MARKER_START, marker_end=SYNC_MARKER_END
    )
    line_count = len(section.strip().split("\n"))
    return {"status": status, "lines": line_count}


def _build_profile_section(prof_data: dict) -> str:
    """Build the markdown section for CLAUDE.md from profile data."""
    lines = [SYNC_MARKER_START, "## User Profile (Evolve Auto-sync)", ""]

    for cat in prof_data.get("categories", []):
        icon = cat.get("icon", "")
        name = cat.get("name", "")
        tags = cat.get("tags", [])
        items = [i for i in cat.get("items", []) if i.get("confidence") != "low"]

        if not items:
            continue

        lines.append(f"### {icon} {name}")
        if tags:
            lines.append(f"- **标签**: {', '.join(tags)}")
        for item in items:
            lines.append(f"- {item['text']}")
        lines.append("")

    lines.append(SYNC_MARKER_END)
    return "\n".join(lines) + "\n"


def _claude_md_has_marker() -> bool:
    """Check if CLAUDE.md already has the evolve sync marker."""
    if not CLAUDE_MD_PATH.exists():
        return False
    text = CLAUDE_MD_PATH.read_text(encoding="utf-8")
    return SYNC_MARKER_START in text and SYNC_MARKER_END in text


# ── Rules sync (CLAUDE.md) ────────────────────────────────────────────────

def _build_rules_section(rules_data: dict) -> str:
    """Build CLAUDE.md section from rules data."""
    rules = rules_data.get("rules", [])
    lines = [RULES_MARKER_START, "## Rules (Evolve Auto-sync)", ""]

    for r in rules:
        rule_text = r.get("rule", "")
        why = r.get("why", "")
        priority = r.get("priority", "")
        category = r.get("category", "")
        tag = f"[{priority}]" if priority else ""
        if category:
            tag += f" [{category}]"
        lines.append(f"- {tag} {rule_text}")
        if why:
            lines.append(f"  - Why: {why}")

    lines.append("")
    lines.append(RULES_MARKER_END)
    return "\n".join(lines) + "\n"


def _evolve_sync_rules_preview(rules_data: dict) -> dict:
    """Generate preview of rules sync to CLAUDE.md."""
    rules = rules_data.get("rules", [])
    section = _build_rules_section(rules_data)
    line_count = len(section.strip().split("\n"))

    existing = CLAUDE_MD_PATH.read_text(encoding="utf-8") if CLAUDE_MD_PATH.exists() else ""
    status = "replace" if (RULES_MARKER_START in existing and RULES_MARKER_END in existing) else "append"
    diff = _build_sync_diff(CLAUDE_MD_PATH, RULES_MARKER_START, RULES_MARKER_END, section)

    return {
        "status": status,
        "rules_count": len(rules),
        "lines": line_count,
        "diff": diff,
    }


def _evolve_sync_rules_execute(rules_data: dict) -> dict:
    """Write rules section to CLAUDE.md."""
    section = _build_rules_section(rules_data)

    CLAUDE_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = CLAUDE_MD_PATH.read_text(encoding="utf-8") if CLAUDE_MD_PATH.exists() else ""

    if RULES_MARKER_START in existing and RULES_MARKER_END in existing:
        start_idx = existing.index(RULES_MARKER_START)
        end_idx = existing.index(RULES_MARKER_END) + len(RULES_MARKER_END)
        new_text = existing[:start_idx] + section + existing[end_idx:]
        status = "replaced"
    else:
        if existing and not existing.endswith("\n\n"):
            existing = existing.rstrip("\n") + "\n\n"
        new_text = existing + section
        status = "appended"

    _safe_write_claude_md(
        new_text, marker_start=RULES_MARKER_START, marker_end=RULES_MARKER_END
    )
    return {"status": status, "rules_count": len(rules_data.get("rules", []))}


# ── Diff helpers ──────────────────────────────────────────────────────────

def _build_sync_diff(file_path, marker_start, marker_end, new_section, context_lines=3):
    """Build diff data for sync preview: current vs new content with context."""
    path = Path(file_path)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    all_lines = existing.rstrip("\n").split("\n") if existing else []
    new_section_lines = new_section.rstrip("\n").split("\n")

    if marker_start in existing and marker_end in existing:
        start_idx = existing.index(marker_start)
        end_idx = existing.index(marker_end) + len(marker_end)

        start_line = existing[:start_idx].count("\n")
        end_line = existing[:end_idx].count("\n")

        ctx_start = max(0, start_line - context_lines)
        ctx_end = min(len(all_lines), end_line + 1 + context_lines)

        old_section_lines = all_lines[start_line:end_line + 1]

        current = []
        new = []

        for i in range(ctx_start, start_line):
            current.append({"ln": i + 1, "text": all_lines[i], "type": "context"})
            new.append({"ln": i + 1, "text": all_lines[i], "type": "context"})

        for i, line in enumerate(old_section_lines):
            current.append({"ln": start_line + i + 1, "text": line, "type": "remove"})

        for i, line in enumerate(new_section_lines):
            new.append({"ln": start_line + i + 1, "text": line, "type": "add"})

        for i in range(end_line + 1, ctx_end):
            current.append({"ln": i + 1, "text": all_lines[i], "type": "context"})
            new.append({"ln": start_line + len(new_section_lines) + (i - end_line), "text": all_lines[i], "type": "context"})

        return {
            "file": f"~/.claude/memory/{path.name}" if "memory" in str(path) else f"~/.claude/{path.name}",
            "action": "replace",
            "current": current,
            "new": new,
        }
    else:
        if not existing:
            return {
                "file": f"~/.claude/memory/{path.name}" if "memory" in str(path) else f"~/.claude/{path.name}",
                "action": "create",
                "current": [],
                "new": [{"ln": i + 1, "text": line, "type": "add"} for i, line in enumerate(new_section_lines)],
            }

        total = len(all_lines)
        ctx_start = max(0, total - context_lines)
        current = []
        new = []

        for i in range(ctx_start, total):
            current.append({"ln": i + 1, "text": all_lines[i], "type": "context"})
            new.append({"ln": i + 1, "text": all_lines[i], "type": "context"})

        for i, line in enumerate(new_section_lines):
            new.append({"ln": total + i + 1, "text": line, "type": "add"})

        return {
            "file": f"~/.claude/memory/{path.name}" if "memory" in str(path) else f"~/.claude/{path.name}",
            "action": "append",
            "current": current,
            "new": new,
        }


def build_twin_sync_diff(claude_md_path, marker_start, marker_end, section):
    """Build diff for twin sync preview — called from twin.py handler."""
    return _build_sync_diff(claude_md_path, marker_start, marker_end, section)
