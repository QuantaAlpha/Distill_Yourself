"""Evolve sync helper functions — memory and profile sync to Claude Code.

Extracted from server.py — pure Python format conversion, no HTTP handler needed.
"""

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (mirrored from server.py module-level constants)
# ---------------------------------------------------------------------------
CLAUDE_MD_PATH = Path.home() / ".claude" / "CLAUDE.md"
MEMORY_DIR = Path.home() / ".claude" / "memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
SYNC_MARKER_START = "<!-- evolve-sync:profile:start -->"
SYNC_MARKER_END = "<!-- evolve-sync:profile:end -->"


def _sanitize_filename(text: str) -> str:
    """Convert text to a safe filename component."""
    # Keep alphanumeric, Chinese chars, hyphens, underscores
    clean = re.sub(r'[^\w\u4e00-\u9fff-]', '_', text)
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean[:60] if clean else "unnamed"


def _evolve_sync_memory_preview(mem_data: dict) -> dict:
    """Generate preview of what memory sync would do.

    Pure read-only: does not create directories or files. The directory is
    created by _evolve_sync_memory_execute when actually writing.
    """
    nodes = {n["id"]: n for n in mem_data.get("nodes", [])}

    files = []
    for nid, node in nodes.items():
        if node.get("confidence") == "low":
            files.append({"id": nid, "filename": "", "label": node.get("label", ""), "status": "skip"})
            continue
        fname = f"evolve_{nid}.md"
        fpath = MEMORY_DIR / fname
        status = "update" if fpath.exists() else "create"
        files.append({"id": nid, "filename": fname, "label": node.get("label", ""), "status": status})

    summary = {"create": 0, "update": 0, "skip": 0}
    for f in files:
        summary[f["status"]] = summary.get(f["status"], 0) + 1

    return {"files": files, "summary": summary}


def _evolve_sync_memory_execute(mem_data: dict) -> dict:
    """Write memory files from evolve data."""
    nodes = {n["id"]: n for n in mem_data.get("nodes", [])}
    cards = {c["id"]: c for c in mem_data.get("cards", [])}
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    created, updated = 0, 0
    written_files = []

    for nid, node in nodes.items():
        if node.get("confidence") == "low":
            continue
        if node.get("status") == "stale":
            continue

        card = cards.get(nid, {})
        label = node.get("label", "")
        name_kebab = _sanitize_filename(label)
        fname = f"evolve_{nid}.md"
        fpath = MEMORY_DIR / fname

        is_update = fpath.exists()

        # Build content: prefer trigger/instruction format, fall back to v1 content
        trigger = card.get("trigger", "")
        instruction = card.get("instruction", "")
        avoid = card.get("avoid", "")

        if trigger and instruction:
            body = f"When: {trigger}\nDo: {instruction}"
            if avoid:
                body += f"\nAvoid: {avoid}"
        else:
            body = card.get("content", label)

        content_lines = [
            "---",
            f"name: {name_kebab}",
            f"description: {label}",
            "type: feedback",
            "source: evolve-sync",
            "---",
            "",
            body,
        ]

        # Evidence
        evidence = card.get("evidence", "")
        if isinstance(evidence, list) and evidence:
            content_lines.extend(["", "**Evidence:**"])
            for ev in evidence[:3]:
                if isinstance(ev, dict):
                    q = ev.get("quote", "")
                    sid = ev.get("sessionId", "")
                    d = ev.get("date", "")
                    content_lines.append(f'- "{q}" ({sid}, {d})')
                else:
                    content_lines.append(f"- {ev}")
        elif isinstance(evidence, str) and evidence:
            content_lines.extend(["", f"**Evidence:** {evidence}"])

        meta_parts = []
        if card.get("firstSeen"):
            meta_parts.append(f"**First seen:** {card['firstSeen']}")
        if card.get("lastSeen"):
            meta_parts.append(f"**Last seen:** {card['lastSeen']}")
        if node.get("frequency"):
            meta_parts.append(f"**Frequency:** {node['frequency']}")
        if node.get("priority"):
            meta_parts.append(f"**Priority:** {node['priority']}")
        if meta_parts:
            content_lines.append(" | ".join(meta_parts))

        content_lines.append("")  # trailing newline
        fpath.write_text("\n".join(content_lines), encoding="utf-8")
        written_files.append(fname)

        if is_update:
            updated += 1
        else:
            created += 1

    # Update MEMORY.md index
    _update_memory_index(written_files, nodes)

    return {"created": created, "updated": updated}


def _update_memory_index(written_files: list, nodes: dict):
    """Add new evolve entries to MEMORY.md if not already listed."""
    if not MEMORY_INDEX.exists():
        return

    existing_text = MEMORY_INDEX.read_text(encoding="utf-8")
    existing_lower = existing_text.lower()
    new_lines = []

    for fname in written_files:
        if fname.lower() in existing_lower:
            continue
        # Find the node for this file
        nid = fname.replace("evolve_", "").replace(".md", "")
        node = nodes.get(nid, {})
        label = node.get("label", fname)
        new_lines.append(f"| [{fname}]({fname}) | feedback | {label} |")

    if new_lines:
        # Append to file
        if not existing_text.endswith("\n"):
            existing_text += "\n"
        existing_text += "\n".join(new_lines) + "\n"
        MEMORY_INDEX.write_text(existing_text, encoding="utf-8")


def _evolve_sync_claude_md_preview(prof_data: dict) -> dict:
    """Generate preview of what CLAUDE.md sync would do."""
    categories = prof_data.get("categories", [])
    radar = prof_data.get("radar", {})
    dims = radar.get("dimensions", [])

    # Count items (excluding low confidence)
    item_count = sum(
        len([i for i in cat.get("items", []) if i.get("confidence") != "low"])
        for cat in categories
    )

    # Generate the section to estimate lines
    section = _build_profile_section(prof_data)
    line_count = len(section.strip().split("\n"))

    status = "replace" if _claude_md_has_marker() else "append"

    return {
        "status": status,
        "categories": len(categories),
        "radar_dims": len(dims),
        "items": item_count,
        "lines": line_count,
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
        # Replace between markers
        start_idx = existing.index(SYNC_MARKER_START)
        end_idx = existing.index(SYNC_MARKER_END) + len(SYNC_MARKER_END)
        new_text = existing[:start_idx] + section + existing[end_idx:]
        status = "replaced"
    else:
        # Append
        if existing and not existing.endswith("\n\n"):
            existing = existing.rstrip("\n") + "\n\n"
        new_text = existing + section
        status = "appended"

    CLAUDE_MD_PATH.write_text(new_text, encoding="utf-8")
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

    # Radar
    dims = prof_data.get("radar", {}).get("dimensions", [])
    if dims:
        lines.append("### 📊 能力雷达")
        lines.append("| 领域 | 评分 | 依据 |")
        lines.append("|------|------|------|")
        for dim in dims:
            score = dim.get("score", 0)
            name = dim.get("name", "")
            evidence = dim.get("evidence", "")
            lines.append(f"| {name} | {score:.2f} | {evidence} |")
        lines.append("")

    lines.append(SYNC_MARKER_END)
    return "\n".join(lines) + "\n"


def _claude_md_has_marker() -> bool:
    """Check if CLAUDE.md already has the evolve sync marker."""
    if not CLAUDE_MD_PATH.exists():
        return False
    text = CLAUDE_MD_PATH.read_text(encoding="utf-8")
    return SYNC_MARKER_START in text
