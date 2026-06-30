"""Evolve data pipeline commands: rules, signals, patterns, profile-digest, aggregates, evolve-write."""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from chatview.commands.analysis import _get_filtered_db, _get_messages_db
from chatview.commands.corrections import (
    _data_corrections, _data_decisions, _data_errors, _data_highlights,
)


# ---------------------------------------------------------------------------
# Shared category classifier for correction signals
# ---------------------------------------------------------------------------

_CATEGORY_PATTERNS = {
    "style": re.compile(
        r'太[简精粗]|太复杂|太臃肿|过度[设计复杂抽象]|'
        r'too (?:complex|verbose|long|simple|short)|overcomplicat|unnecessar',
        re.IGNORECASE),
    "scope": re.compile(
        r'不需要这个|多余|没必要|不是我说的|我说的是|我要的是|'
        r'not what I (?:asked|meant|wanted)|I meant|我没说|我没让你|谁让你',
        re.IGNORECASE),
    "accuracy": re.compile(
        r'不对[，。！\s]|错了[，。！\s]|你搞错|搞反了|你理解错|你没[看听懂理解]|应该是|'
        r'wrong|not right|you forgot|you missed|incorrect|mistaken',
        re.IGNORECASE),
    "workflow": re.compile(
        r'重新来|重做|回退|改回去|撤销|换一种|再看看|再想想|再试试|'
        r'revert|undo|roll\s*back|start over|try again',
        re.IGNORECASE),
}


def _classify_correction(text, signals):
    """Classify a correction into a category based on signal words."""
    for cat, pat in _CATEGORY_PATTERNS.items():
        if pat.search(text):
            return cat
        for s in signals:
            if pat.search(s):
                return cat
    return "workflow"  # default


def _write_evolve_cache(tab, data, cache_key=""):
    """Write evolve data to .cache/evolve/<tab>.json."""
    cache_dir = Path(__file__).resolve().parent.parent.parent / ".cache" / "evolve"
    cache_dir.mkdir(parents=True, exist_ok=True)
    suffix = f".{cache_key}" if cache_key else ""
    out_path = cache_dir / f"{tab}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(out_path)


def cmd_evolve_rules(args):
    """Generate rules data for Evolve Rules tab."""
    corrections = _data_corrections(args)[:200]

    # Group corrections by category -> build rules
    cat_groups = defaultdict(list)
    for c in corrections:
        cat = _classify_correction(c.get("text", ""), c.get("signals", []))
        cat_groups[cat].append(c)

    rules = []
    rule_id = 0
    for cat, items in cat_groups.items():
        # Sub-group by similar signal patterns to avoid one mega-rule per category
        signal_groups = defaultdict(list)
        for item in items:
            # Use first signal as grouping key
            key = item["signals"][0] if item.get("signals") else "general"
            signal_groups[key].append(item)

        for signal_key, group in signal_groups.items():
            if len(group) < 1:
                continue
            rule_id += 1
            freq = len(group)
            # Priority based on frequency
            if freq >= 5:
                priority = "P0"
            elif freq >= 2:
                priority = "P1"
            else:
                priority = "P2"

            # Build rule text from the most common correction
            representative = group[0]
            user_quote = representative.get("text", "")[:200]

            # Build evidence
            evidence = []
            for g in group[:5]:
                evidence.append({
                    "session": g.get("sessionId", ""),
                    "quote": g.get("text", "")[:150],
                })

            # Determine rule/why/positive/negative from context
            rule_text = f"\u7528\u6237\u7ea0\u6b63\uff1a{signal_key}"
            why = user_quote[:100] if user_quote else ""
            ai_text = representative.get("aiText", "")

            # Map Chinese category names
            cat_label = {"style": "\u98ce\u683c", "scope": "\u8303\u56f4", "accuracy": "\u51c6\u786e\u6027",
                         "workflow": "\u5de5\u4f5c\u6d41"}.get(cat, cat)

            rules.append({
                "id": f"r{rule_id}",
                "priority": priority,
                "category": cat_label,
                "rule": rule_text,
                "why": why,
                "positive": "",
                "negative": ai_text[:100] if ai_text else "",
                "evidence": evidence,
                "frequency": freq,
            })

    rules.sort(key=lambda r: {"P0": 0, "P1": 1, "P2": 2}.get(r["priority"], 9))
    result = {"rules": rules}

    out_path = _write_evolve_cache("rules", result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Generated {len(rules)} rules \u2192 {out_path}")


def cmd_evolve_signals(args):
    """Generate signals data for Evolve Signals tab."""
    corrections = _data_corrections(args)[:200]

    # Build timeline (group by date, count by category)
    date_counts = defaultdict(lambda: defaultdict(int))  # date -> {cat: count}
    events = []

    for i, c in enumerate(corrections):
        cat = _classify_correction(c.get("text", ""), c.get("signals", []))
        date = c.get("date", "")[:10]
        if date:
            date_counts[date][cat] += 1

        events.append({
            "id": f"c{i+1}",
            "date": date,
            "session": c.get("sessionId", ""),
            "type": cat,
            "userQuote": c.get("text", "")[:200],
            "aiIssue": c.get("aiText", "")[:150] if c.get("aiText") else "",
            "correction": "",
            "linkedRule": None,
        })

    timeline = sorted([
        {"date": d, "counts": dict(counts)}
        for d, counts in date_counts.items()
    ], key=lambda x: x["date"])

    result = {"timeline": timeline, "events": events[:100]}

    out_path = _write_evolve_cache("signals", result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Generated {len(timeline)} timeline entries, {len(events)} events \u2192 {out_path}")


def cmd_evolve_patterns(args):
    """Generate patterns data for Evolve Patterns tab."""
    corrections = _data_corrections(args)[:200]
    errors = _data_errors(args)[:100]

    bubbles = []
    cards = []
    pid = 0

    # 1. Error patterns -> "error" type bubbles
    for err in errors[:20]:
        pid += 1
        bubbles.append({
            "id": f"p{pid}",
            "label": err.get("pattern", "")[:30],
            "frequency": err.get("count", 1),
            "type": "error",
            "trend": "stable",
        })
        cards.append({
            "id": f"p{pid}",
            "description": err.get("sample", err.get("pattern", "")),
            "frequency": err.get("count", 1),
            "cost": f"{err.get('sessions', 1)} sessions affected",
            "suggestion": "\u68c0\u67e5\u9519\u8bef\u6839\u56e0\uff0c\u6dfb\u52a0\u9632\u5fa1\u6027\u5904\u7406",
            "sessions": [],
            "trend": "stable",
        })

    # 2. Correction patterns -> group by category for "workflow"/"efficiency" bubbles
    cat_counts = defaultdict(lambda: {"count": 0, "sessions": set(), "samples": []})
    for c in corrections:
        cat = _classify_correction(c.get("text", ""), c.get("signals", []))
        cat_counts[cat]["count"] += 1
        cat_counts[cat]["sessions"].add(c.get("sessionId", ""))
        if len(cat_counts[cat]["samples"]) < 3:
            cat_counts[cat]["samples"].append(c.get("text", "")[:100])

    cat_labels = {"style": "\u98ce\u683c\u95ee\u9898", "scope": "\u8303\u56f4\u8513\u5ef6", "accuracy": "\u51c6\u786e\u6027\u95ee\u9898",
                  "workflow": "\u5de5\u4f5c\u6d41\u95ee\u9898"}
    cat_types = {"style": "efficiency", "scope": "efficiency",
                 "accuracy": "knowledge_gap", "workflow": "workflow"}

    for cat, data in cat_counts.items():
        if data["count"] < 1:
            continue
        pid += 1
        bubbles.append({
            "id": f"p{pid}",
            "label": cat_labels.get(cat, cat),
            "frequency": data["count"],
            "type": cat_types.get(cat, "workflow"),
            "trend": "stable",
        })
        cards.append({
            "id": f"p{pid}",
            "description": f"{cat_labels.get(cat, cat)}\uff1a{'; '.join(data['samples'][:2])}",
            "frequency": data["count"],
            "cost": f"{len(data['sessions'])} sessions",
            "suggestion": f"\u5173\u6ce8 {cat_labels.get(cat, cat)} \u76f8\u5173\u7684\u91cd\u590d\u7ea0\u6b63",
            "sessions": list(data["sessions"])[:5],
            "trend": "stable",
        })

    bubbles.sort(key=lambda b: -b["frequency"])
    cards.sort(key=lambda c: -c["frequency"])
    result = {"bubbles": bubbles, "cards": cards}

    out_path = _write_evolve_cache("patterns", result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Generated {len(bubbles)} patterns \u2192 {out_path}")


# ---------------------------------------------------------------------------
# evolve-write: validated write/merge/delete for Evolve tab data
# ---------------------------------------------------------------------------

# Schema definitions: {field: {required_keys, optional_keys, type_checks}}
_EVOLVE_SCHEMAS = {
    "profile": {
        "top_fields": {"categories": list, "radar": dict},
        "categories_item": {"required": {"name": str}, "optional": {"icon": str, "tags": list, "items": list}},
        "categories_item_item": {"required": {"text": str}, "optional": {"confidence": str, "session": str}},
        "radar_dimension": {"required": {"name": str, "score": (int, float)}, "optional": {"evidence": str}},
        "id_field": None,  # categories matched by "name"
    },
    "memory": {
        "top_fields": {"nodes": list, "links": list, "cards": list},
        "node": {
            "required": {"id": str, "label": str},
            "optional": {"type": str, "frequency": (int, float), "confidence": str,
                         "priority": str, "status": str, "scope": str, "sessions": list}
        },
        "link": {
            "required": {"source": str, "target": str},
            "optional": {"strength": (int, float), "relation": str}
        },
        "card": {
            "required": {"id": str},
            "optional": {"trigger": str, "instruction": str, "avoid": str,
                         "content": str, "firstSeen": str, "lastSeen": str,
                         "lastValidated": str, "evidence": (str, list),
                         "conflictsWith": list}
        },
        "id_field": "id",
    },
    "rules": {
        "top_fields": {"rules": list},
        "rule": {"required": {"id": str, "rule": str}, "optional": {"priority": str, "category": str, "content": str, "why": str, "positive": str, "negative": str, "evidence": list, "frequency": (int, float)}},
        "id_field": "id",
    },
    "signals": {
        "top_fields": {"timeline": list, "events": list},
        "event": {"required": {"id": str}, "optional": {"date": str, "session": str, "type": str, "userQuote": str, "aiIssue": str, "correction": str, "linkedRule": (str, type(None))}},
        "timeline_item": {"required": {"date": str, "counts": dict}, "optional": {}},
        "id_field": "id",
    },
    "patterns": {
        "top_fields": {"bubbles": list, "cards": list},
        "bubble": {"required": {"id": str, "label": str}, "optional": {"frequency": (int, float), "type": str, "trend": str}},
        "card": {"required": {"id": str}, "optional": {"description": str, "frequency": (int, float), "cost": str, "suggestion": str, "sessions": list, "trend": str}},
        "id_field": "id",
    },
}


def _validate_evolve_data(tab, data):
    """Validate data against tab schema. Returns (ok, errors_list)."""
    schema = _EVOLVE_SCHEMAS.get(tab)
    if not schema:
        return False, [f"Unknown tab: {tab}"]

    if not isinstance(data, dict):
        return False, ["Data must be a JSON object"]

    errors = []
    top = schema["top_fields"]

    # Check top-level fields exist and have correct types
    for field, expected_type in top.items():
        if field not in data:
            data[field] = expected_type()  # auto-fill with empty
            continue
        if not isinstance(data[field], expected_type):
            errors.append(f"'{field}' must be {expected_type.__name__}, got {type(data[field]).__name__}")

    if errors:
        return False, errors

    # Validate items within arrays
    if tab == "profile":
        for i, cat in enumerate(data.get("categories", [])):
            errs = _check_item(f"categories[{i}]", cat, schema["categories_item"])
            errors.extend(errs)
            # Validate nested items
            for j, item in enumerate(cat.get("items", [])):
                if isinstance(item, str):
                    cat["items"][j] = {"text": item}  # auto-fix string->object
                elif isinstance(item, dict):
                    errors.extend(_check_item(f"categories[{i}].items[{j}]", item, schema["categories_item_item"]))
            # Validate tags
            if "tags" in cat and not isinstance(cat["tags"], list):
                errors.append(f"categories[{i}].tags must be array")
        for i, dim in enumerate(data.get("radar", {}).get("dimensions", [])):
            errs = _check_item(f"radar.dimensions[{i}]", dim, schema["radar_dimension"])
            errors.extend(errs)
            if "score" in dim:
                try:
                    s = float(dim["score"])
                    if not (0 <= s <= 1):
                        errors.append(f"radar.dimensions[{i}].score must be 0.0-1.0, got {s}")
                    dim["score"] = s
                except (TypeError, ValueError):
                    errors.append(f"radar.dimensions[{i}].score must be a number")
        # Ensure radar.dimensions exists
        if isinstance(data.get("radar"), dict) and "dimensions" not in data["radar"]:
            data["radar"]["dimensions"] = []

    elif tab == "memory":
        for i, n in enumerate(data.get("nodes", [])):
            errors.extend(_check_item(f"nodes[{i}]", n, schema["node"]))
        for i, link in enumerate(data.get("links", [])):
            errors.extend(_check_item(f"links[{i}]", link, schema["link"]))
        for i, c in enumerate(data.get("cards", [])):
            errors.extend(_check_item(f"cards[{i}]", c, schema["card"]))

    elif tab == "rules":
        for i, r in enumerate(data.get("rules", [])):
            errors.extend(_check_item(f"rules[{i}]", r, schema["rule"]))

    elif tab == "signals":
        for i, e in enumerate(data.get("events", [])):
            errors.extend(_check_item(f"events[{i}]", e, schema["event"]))
        for i, t in enumerate(data.get("timeline", [])):
            errors.extend(_check_item(f"timeline[{i}]", t, schema["timeline_item"]))

    elif tab == "patterns":
        for i, b in enumerate(data.get("bubbles", [])):
            errors.extend(_check_item(f"bubbles[{i}]", b, schema["bubble"]))
        for i, c in enumerate(data.get("cards", [])):
            errors.extend(_check_item(f"cards[{i}]", c, schema["card"]))

    return len(errors) == 0, errors


def _check_item(path, item, spec):
    """Check a single item against its spec {required, optional}."""
    if not isinstance(item, dict):
        return [f"{path}: must be an object, got {type(item).__name__}"]
    errors = []
    for key, expected in spec.get("required", {}).items():
        if key not in item:
            errors.append(f"{path}.{key}: required field missing")
        elif not isinstance(item[key], expected if isinstance(expected, tuple) else (expected,)):
            errors.append(f"{path}.{key}: expected {expected}, got {type(item[key]).__name__}")
    for key, expected in spec.get("optional", {}).items():
        if key in item and item[key] is not None:
            if not isinstance(item[key], expected if isinstance(expected, tuple) else (expected,)):
                errors.append(f"{path}.{key}: expected {expected}, got {type(item[key]).__name__}")
    return errors


def _read_evolve_cache(tab, cache_key=""):
    """Read existing cache for a tab, or return empty dict."""
    suffix = f".{cache_key}" if cache_key else ""
    cache_path = Path(__file__).resolve().parent.parent.parent / ".cache" / "evolve" / f"{tab}{suffix}.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _merge_evolve_data(tab, existing, new_data):
    """Merge new_data into existing data. Match by id/name, add new, update existing."""
    schema = _EVOLVE_SCHEMAS.get(tab, {})

    if tab == "profile":
        # Merge categories by name
        exist_cats = {c["name"]: c for c in existing.get("categories", [])}
        for cat in new_data.get("categories", []):
            name = cat.get("name", "")
            if name in exist_cats:
                # Update: merge tags and items
                old = exist_cats[name]
                old_tags = set(old.get("tags", []))
                old_tags.update(cat.get("tags", []))
                old["tags"] = list(old_tags)
                # Merge items by text (deduplicate)
                old_texts = {(it["text"] if isinstance(it, dict) else it) for it in old.get("items", [])}
                for item in cat.get("items", []):
                    text = item["text"] if isinstance(item, dict) else item
                    if text not in old_texts:
                        old["items"].append(item)
                if cat.get("icon"):
                    old["icon"] = cat["icon"]
            else:
                exist_cats[name] = cat
        existing["categories"] = list(exist_cats.values())

        # Merge radar dimensions by name
        if "radar" in new_data:
            if "radar" not in existing:
                existing["radar"] = {"dimensions": []}
            exist_dims = {d["name"]: d for d in existing["radar"].get("dimensions", [])}
            for dim in new_data.get("radar", {}).get("dimensions", []):
                exist_dims[dim["name"]] = dim  # replace on match
            existing["radar"]["dimensions"] = list(exist_dims.values())

    else:
        # Generic merge for tabs with id-based items
        for field in schema.get("top_fields", {}):
            if field not in new_data:
                continue
            if not isinstance(new_data[field], list):
                existing[field] = new_data[field]
                continue
            # Merge lists by id
            old_list = existing.get(field, [])
            if tab == "signals" and field == "timeline":
                # Timeline: merge by date
                old_by_date = {t["date"]: t for t in old_list}
                for t in new_data[field]:
                    old_by_date[t["date"]] = t
                existing[field] = sorted(old_by_date.values(), key=lambda x: x.get("date", ""))
            elif all(isinstance(item, dict) and "id" in item for item in new_data[field]):
                old_by_id = {item["id"]: item for item in old_list}
                for item in new_data[field]:
                    old_by_id[item["id"]] = item  # replace on match, add if new
                existing[field] = list(old_by_id.values())
            else:
                # No id field (e.g., links) — just replace
                existing[field] = new_data[field]

    return existing


def _delete_evolve_data(tab, existing, ids):
    """Delete items by id from existing data."""
    ids_set = set(ids)

    if tab == "profile":
        # Delete categories by name
        existing["categories"] = [c for c in existing.get("categories", []) if c.get("name") not in ids_set]
        # Delete radar dimensions by name
        if "radar" in existing:
            existing["radar"]["dimensions"] = [d for d in existing["radar"].get("dimensions", []) if d.get("name") not in ids_set]
    else:
        schema = _EVOLVE_SCHEMAS.get(tab, {})
        for field in schema.get("top_fields", {}):
            items = existing.get(field, [])
            if isinstance(items, list):
                existing[field] = [item for item in items if not (isinstance(item, dict) and item.get("id") in ids_set)]

    return existing


def cmd_profile_digest(args):
    """Generate a pre-computed profile digest for sub-agents."""
    from chatview import db as _db
    _db.init_db()

    result = {}

    # --- meta ---
    db_sessions = _get_filtered_db(args)
    total_sessions = len(db_sessions)
    src_counts = defaultdict(int)
    proj_counts = defaultdict(lambda: {"sessions": 0, "queries": 0})
    dates = []
    for s in db_sessions:
        src = s.get("source", "claude")
        src_counts[src] += 1
        pname = s.get("project_name") or "unknown"
        proj_counts[pname]["sessions"] += 1
        proj_counts[pname]["queries"] += s.get("user_message_count") or 0
        d = (s.get("date") or "")[:10]
        if d:
            dates.append(d)
    dates.sort()

    # Count total queries
    all_queries_raw = _get_messages_db(args, role="user", limit=99999)
    total_queries = len([q for q in all_queries_raw if len(q.get("text", "")) >= 3])

    result["meta"] = {
        "generated_at": datetime.now().isoformat()[:19],
        "date_range": [dates[0], dates[-1]] if dates else [],
        "session_count": total_sessions,
        "query_count": total_queries,
        "source_split": dict(src_counts),
    }

    # --- projects (top 5) ---
    top_projects = sorted(proj_counts.items(), key=lambda x: -x[1]["sessions"])[:5]
    result["projects"] = [
        {"name": name, "sessions": data["sessions"],
         "pct": round(data["sessions"] / max(total_sessions, 1) * 100),
         "queries": data["queries"]}
        for name, data in top_projects
    ]

    # --- correction episodes (grouped by signal cluster) ---
    corrections = _data_corrections(args)[:200]
    cat_groups = defaultdict(list)
    for c in corrections:
        cat = _classify_correction(c.get("text", ""), c.get("signals", []))
        cat_groups[cat].append(c)

    episodes = []
    for cat, items in cat_groups.items():
        # Sub-group by first signal word
        signal_groups = defaultdict(list)
        for item in items:
            key = item["signals"][0] if item.get("signals") else "general"
            signal_groups[key].append(item)

        for signal_key, group in signal_groups.items():
            if len(group) < 1:
                continue
            # Pick best sample: AI-confirmed first, then longest text
            group.sort(key=lambda x: (-int(x.get("aiConfirmed", False)), -len(x.get("text", ""))))
            rep = group[0]
            projects_seen = list(set(g.get("project", "") for g in group if g.get("project")))
            episodes.append({
                "category": cat,
                "signal": signal_key,
                "sample_text": rep.get("text", "")[:200],
                "repeat_count": len(group),
                "ai_confirmed_count": sum(1 for g in group if g.get("aiConfirmed")),
                "projects_seen": projects_seen[:5],
            })

    episodes.sort(key=lambda e: -e["repeat_count"])

    # Category totals
    by_category = defaultdict(int)
    by_subtype = defaultdict(int)
    for c in corrections:
        cat = _classify_correction(c.get("text", ""), c.get("signals", []))
        by_category[cat] += 1
        src = c.get("source", "user")
        kind = c.get("kind", "")
        if src == "user":
            by_subtype["user"] += 1
        elif kind == "correction":
            by_subtype["ai_correction"] += 1
        elif kind == "insight":
            by_subtype["ai_insight"] += 1

    confirmed_count = sum(1 for c in corrections if c.get("source") == "user" and c.get("aiConfirmed"))
    by_subtype["confirmed"] = confirmed_count

    result["corrections"] = {
        "total": len(corrections),
        "by_subtype": dict(by_subtype),
        "by_category": dict(by_category),
        "correction_rate_per_100_queries": round(len(corrections) / max(total_queries, 1) * 100, 1),
        "episodes": episodes[:15],
    }

    # --- positive signals (short user confirmations/approvals) ---
    _confirm_re = re.compile(
        r'^(\u53ef\u4ee5\u7684?|OK[\u7684\u4e86]?|\u597d[\u7684\u4e86]?|\u884c[\u7684\u4e86]?|\u5bf9[\u7684\u4e86]?|\u6ca1\u95ee\u9898|\u5c31\u8fd9\u6837|\u55ef|'
        r'yes|perfect|looks good|lgtm|exactly|great|approved|'
        r'\u8fd9\u4e2a[\u65b9\u6848\u4e0d]?\u9519|\u631a\u597d|\u4e0d\u9519|\u53ef\u4ee5|\u540c\u610f)',
        re.IGNORECASE)
    positive = []
    for q in all_queries_raw:
        text = q.get("text", "").strip()
        # Affirmative messages with enough context (skip bare "可以的" / "OK")
        if len(text) < 15 or len(text) > 60:
            continue
        if not _confirm_re.match(text):
            continue
        # Skip noise
        if text.startswith(("<", "{", "```", "#", "/")):
            continue
        positive.append({
            "user_text": text[:60],
            "project": q.get("project_name", ""),
            "date": (q.get("ts") or "")[:10],
        })
    # Deduplicate
    seen_texts = set()
    unique_positive = []
    for p in positive:
        key = p["user_text"][:20]
        if key not in seen_texts:
            seen_texts.add(key)
            unique_positive.append(p)
    result["positive_signals"] = unique_positive[:10]

    # --- decisions ---
    all_decisions = _data_decisions(args)[:200]

    result["decisions"] = {
        "total": len(all_decisions),
        "samples": [
            {"text": d.get("text", "")[:200], "date": d.get("date", ""), "project": d.get("project", "")}
            for d in all_decisions[:5]
        ],
    }

    # --- files ---
    from chatview.commands.analysis import _data_files
    all_files = _data_files(args)[:10]

    # Extension distribution
    ext_counts = defaultdict(int)
    for finfo in all_files:
        ext = os.path.splitext(finfo.get("path", ""))[-1] or ".other"
        ext_counts[ext] += finfo.get("edits", 0) + finfo.get("writes", 0)
    total_edits = sum(ext_counts.values()) or 1
    ext_dist = {ext: round(count / total_edits * 100) for ext, count in
                sorted(ext_counts.items(), key=lambda x: -x[1])[:6]}

    result["files"] = {
        "top_edited": [
            {"path": f.get("path", ""), "edits": f.get("edits", 0), "sessions": f.get("sessions", 0)}
            for f in all_files[:8]
        ],
        "extension_distribution": ext_dist,
    }

    # --- errors ---
    all_errors = _data_errors(args)[:5]

    result["errors"] = {
        "top": [
            {"pattern": e.get("pattern", ""), "count": e.get("count", 0), "sessions": e.get("sessions", 0)}
            for e in all_errors[:5]
        ],
    }

    # --- friction hotspots (top sessions by correction count) ---
    all_highlights = _data_highlights(args)[:999]

    hotspots = sorted(all_highlights, key=lambda h: -h.get("corrections", 0))
    result["friction_hotspots"] = [
        {"session_id": h["id"], "title": h.get("title", ""), "corrections": h.get("corrections", 0),
         "queries": h.get("messages", 0), "project": h.get("project", ""), "date": h.get("date", "")}
        for h in hotspots[:5] if h.get("corrections", 0) >= 2
    ]

    # --- query samples (representative user messages) ---
    # Select diverse samples: spread across projects, varied lengths
    valid_queries = [q for q in all_queries_raw
                     if len(q.get("text", "")) >= 10
                     and not q.get("text", "").strip().startswith(("<", "{", "```", "#"))]
    # Bucket by project, pick from each
    proj_buckets = defaultdict(list)
    for q in valid_queries:
        proj_buckets[q.get("project_name", "")].append(q)
    query_samples = []
    # Round-robin from each project
    proj_list = sorted(proj_buckets.keys(), key=lambda p: -len(proj_buckets[p]))
    idx = 0
    while len(query_samples) < 20 and idx < 200:
        for proj in proj_list:
            bucket = proj_buckets[proj]
            if idx < len(bucket):
                text = bucket[idx]["text"][:200].replace("\n", " ")
                query_samples.append({
                    "text": text,
                    "project": proj,
                    "date": (bucket[idx].get("ts") or "")[:10],
                })
            if len(query_samples) >= 20:
                break
        idx += 1

    result["query_samples"] = query_samples

    # --- high signal sessions (top 10 by corrections + decisions) ---
    top_sessions = sorted(all_highlights,
                          key=lambda h: -(h.get("corrections", 0) + h.get("decisions", 0)))[:10]
    result["high_signal_sessions"] = [
        {"id": h["id"], "title": h.get("title", ""), "topic": h.get("topic", ""),
         "corrections": h.get("corrections", 0), "decisions": h.get("decisions", 0),
         "messages": h.get("messages", 0), "project": h.get("project", ""),
         "date": h.get("date", ""), "source": h.get("source", "")}
        for h in top_sessions
    ]

    # --- session topic distribution (keyword-based) ---
    topic_patterns = {
        "bugfix": re.compile(r'fix|bug|\u4fee|\u62a5\u9519|error|broken|crash|\u574f\u4e86|\u4e0dwork|\u4e0d\u884c', re.I),
        "feature": re.compile(r'\u65b0\u589e|\u6dfb\u52a0|\u5b9e\u73b0|add|implement|create|build|\u5199\u4e00\u4e2a|\u505a\u4e00\u4e2a', re.I),
        "ui_design": re.compile(r'UI|\u6837\u5f0f|\u5e03\u5c40|\u989c\u8272|style|layout|design|CSS|\u524d\u7aef|\u9875\u9762', re.I),
        "architecture": re.compile(r'\u67b6\u6784|\u65b9\u6848|\u8bbe\u8ba1|\u91cd\u6784|refactor|schema|migrate|\u8fc1\u79fb', re.I),
        "research": re.compile(r'\u8c03\u7814|\u5206\u6790|research|investigate|\u5bf9\u6bd4|compare|\u770b\u770b', re.I),
        "review": re.compile(r'review|\u68c0\u67e5|\u9a8c\u8bc1|\u6d4b\u8bd5|test|verify|check', re.I),
        "config_ops": re.compile(r'\u914d\u7f6e|deploy|\u90e8\u7f72|install|\u5b89\u88c5|setup|\u73af\u5883', re.I),
    }
    topic_dist = defaultdict(int)
    for h in all_highlights:
        topic_text = h.get("topic", "") + " " + h.get("title", "")
        matched = False
        for topic_name, pat in topic_patterns.items():
            if pat.search(topic_text):
                topic_dist[topic_name] += 1
                matched = True
                break
        if not matched:
            topic_dist["other"] += 1

    result["session_topics"] = dict(sorted(topic_dist.items(), key=lambda x: -x[1]))

    # --- collaboration patterns ---
    collab = {"solo": 0, "multi_agent": 0, "with_codex": 0, "with_gemini": 0}
    for s in db_sessions:
        fp = s.get("file_path", "")
        if not fp or not os.path.exists(fp):
            collab["solo"] += 1
            continue
        has_agent = False
        has_codex = False
        has_gemini = False
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") != "assistant":
                        continue
                    for blk in (obj.get("message", {}).get("content", []) or []):
                        if not isinstance(blk, dict):
                            continue
                        if blk.get("type") == "tool_use":
                            if blk.get("name") == "Agent":
                                has_agent = True
                            inp = blk.get("input", {})
                            cmd = inp.get("command", "")
                            if "codex " in cmd or "codex exec" in cmd:
                                has_codex = True
                            if "gemini " in cmd:
                                has_gemini = True
        except Exception:
            pass
        if has_agent:
            collab["multi_agent"] += 1
        else:
            collab["solo"] += 1
        if has_codex:
            collab["with_codex"] += 1
        if has_gemini:
            collab["with_gemini"] += 1

    result["collaboration"] = collab

    # --- communication style ---
    zh_count = 0
    en_count = 0
    lengths = []
    for q in valid_queries[:500]:
        text = q.get("text", "")
        lengths.append(len(text))
        cjk = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
        if cjk > len(text) * 0.1:
            zh_count += 1
        else:
            en_count += 1
    total_lang = zh_count + en_count or 1
    lengths.sort()

    # Style samples: short directive-style messages
    style_candidates = [q for q in valid_queries
                        if 10 <= len(q.get("text", "")) <= 80
                        and not q.get("text", "").startswith(("#", "/", "```"))
                        and "[Request interrupted" not in q.get("text", "")]
    seen = set()
    style_samples = []
    for q in style_candidates:
        t = q["text"].strip().replace("\n", " ")[:80]
        if t not in seen:
            seen.add(t)
            style_samples.append(t)
        if len(style_samples) >= 8:
            break

    result["communication"] = {
        "language_mix": {"zh": round(zh_count / total_lang * 100), "en": round(en_count / total_lang * 100)},
        "msg_length": {
            "avg_chars": round(sum(lengths) / max(len(lengths), 1)),
            "median_chars": lengths[len(lengths) // 2] if lengths else 0,
        },
        "style_samples": style_samples,
    }

    # Output
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_aggregates(args):
    """Print pre-computed aggregates from SQLite DB as JSON."""
    from chatview import db as _db
    _db.init_db()
    keys = ["project_distribution", "daily_activity", "topic_by_project"]
    result = {}
    for k in keys:
        val = _db.get_aggregate(k)
        if val:
            result[k] = json.loads(val)
    if getattr(args, "json", False) or True:  # always JSON for this command
        print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_evolve_write(args):
    """Write/merge/delete Evolve tab data with schema validation.

    Modes:
      replace  -- Replace entire tab data (default)
      merge    -- Add new items and update existing ones (match by id/name)
      delete   -- Remove items by id/name

    Storage: writes directly to SQLite (evolve_cache table).
    Input: JSON from stdin (for replace/merge) or --ids flag (for delete).
    Output: "OK" on success, error details on failure.
    """
    from chatview import db as _db
    tab = args.tab
    mode = args.mode
    source = getattr(args, "source", "all") or "all"
    date = getattr(args, "date", "7d") or "7d"
    project = getattr(args, "project", "") or ""
    engine = getattr(args, "engine", "auto") or "auto"

    if tab not in _EVOLVE_SCHEMAS:
        print(f"ERROR: invalid tab '{tab}'. Valid: {', '.join(_EVOLVE_SCHEMAS.keys())}", file=sys.stderr)
        sys.exit(1)

    def _read_existing():
        row = _db.evolve_get(tab, source, date, project, engine)
        return row["data"] if row else {}

    if mode == "delete":
        ids = [i.strip() for i in (args.ids or "").split(",") if i.strip()]
        if not ids:
            print("ERROR: --ids required for delete mode (comma-separated)", file=sys.stderr)
            sys.exit(1)
        existing = _read_existing()
        if not existing:
            print("ERROR: no existing data to delete from", file=sys.stderr)
            sys.exit(1)
        result = _delete_evolve_data(tab, existing, ids)
        _db.evolve_upsert(tab, source, date, project, engine, json.dumps(result, ensure_ascii=False))
        print(f"OK: deleted {len(ids)} item(s) from {tab} \u2192 SQLite")
        return

    # Read JSON from stdin
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON input \u2014 {e}", file=sys.stderr)
        sys.exit(1)

    # Validate schema
    ok, errors = _validate_evolve_data(tab, data)
    if not ok:
        print(f"ERROR: schema validation failed ({len(errors)} issue(s)):", file=sys.stderr)
        for err in errors[:10]:
            print(f"  - {err}", file=sys.stderr)
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more", file=sys.stderr)
        sys.exit(1)

    if mode == "merge":
        existing = _read_existing()
        result = _merge_evolve_data(tab, existing, data) if existing else data
    else:
        result = data

    _db.evolve_upsert(tab, source, date, project, engine, json.dumps(result, ensure_ascii=False))
    print(f"OK: {mode} {tab} \u2192 SQLite")


def cmd_evolve_sync(args):
    """Sync staged Evolve data (SQLite) to Claude Code config files.

    Reuses chatview.handlers.sync so the written format matches the web app
    exactly (front matter, markers, filenames) \u2014 no drift.

      --tab memory   -> ~/.claude/memory/evolve_<id>.md (+ MEMORY.md index)
      --tab profile  -> ~/.claude/CLAUDE.md marked section

    Reads the same SQLite scope key that `evolve-write` wrote to. Default is
    preview (no writes); pass --execute to actually write.
    """
    from chatview import db as _db
    from chatview.handlers.sync import (
        _evolve_sync_memory_preview, _evolve_sync_memory_execute,
        _evolve_sync_claude_md_preview, _evolve_sync_claude_md_execute,
    )
    _db.init_db()

    tab = args.tab  # "memory" | "profile"
    source = getattr(args, "source", "all") or "all"
    date = getattr(args, "date", "7d") or "7d"
    project = getattr(args, "project", "") or ""
    engine = getattr(args, "engine", "auto") or "auto"
    execute = getattr(args, "execute", False)

    row = _db.evolve_get(tab, source, date, project, engine)
    if not row:
        print(json.dumps({
            "error": f"{tab} cache not found for scope "
                     f"(source={source}, date={date}, project={project or '-'}, engine={engine}). "
                     f"Stage it first: `evolve-write --tab {tab} --source {source} --date {date}`."
        }, ensure_ascii=False))
        sys.exit(1)

    data = row["data"]
    action = "execute" if execute else "preview"
    if tab == "memory":
        fn = _evolve_sync_memory_execute if execute else _evolve_sync_memory_preview
    else:  # profile -> CLAUDE.md
        fn = _evolve_sync_claude_md_execute if execute else _evolve_sync_claude_md_preview

    try:
        result = fn(data)
    except (KeyError, TypeError, ValueError) as e:
        print(json.dumps({
            "error": f"staged {tab} data is malformed: {type(e).__name__}: {e}. "
                     f"Re-stage with `evolve-write --tab {tab}`."
        }, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps({"tab": tab, "action": action, "result": result},
                     ensure_ascii=False, indent=2))
