"""Cognitive Model (Digital Twin) CRUD commands."""

import json
import sys
import uuid


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CM_VALID_TABLES = {
    "evidence_events",
    "judgment_cards",
    "card_relations",
    "cognitive_traits",
}

# Maps CLI-friendly names to actual table names
_TWIN_TABLE_MAP = {
    "cards": "judgment_cards",
    "traits": "cognitive_traits",
    "events": "evidence_events",
    "relations": "card_relations",
}

_TWIN_RESOURCE_TABLE = {
    "events": "evidence_events",
    "cards": "judgment_cards",
    "traits": "cognitive_traits",
}

_TWIN_REQUIRED_BY_RESOURCE = {
    "events": [
        "session_id",
        "event_index",
        "task_type",
        "ai_action",
        "user_reaction",
        "lesson",
    ],
    "cards": ["applies_when", "judgment", "agent_action"],
    "traits": ["name", "category", "description"],
}

# Searchable text columns per table
_TWIN_SEARCH_COLS = {
    "evidence_events": ["ai_action", "user_reaction", "resolution", "lesson", "domain"],
    "judgment_cards": [
        "applies_when",
        "judgment",
        "agent_action",
        "exceptions",
        "tags",
    ],
    "cognitive_traits": ["name", "category", "description"],
}

_TWIN_SEARCH_ORDER = {
    "evidence_events": "created_at DESC",
    "judgment_cards": "updated_at DESC",
    "cognitive_traits": "updated_at DESC",
}

_TWIN_MAX_OUTPUT_CHARS = 320_000  # ~80K tokens -- leave room for prompt + reasoning


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_twin_resource_data(resource: str, data: dict, partial: bool = False):
    if resource not in _TWIN_REQUIRED_BY_RESOURCE:
        raise ValueError(f"unknown resource: {resource}")
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    if partial:
        return
    missing = [
        k for k in _TWIN_REQUIRED_BY_RESOURCE[resource] if data.get(k) in (None, "")
    ]
    if missing:
        raise ValueError(
            f"missing required fields for {resource}: {', '.join(missing)}"
        )


def _run_id_compatible(left: dict, right: dict, run_id: str = "") -> bool:
    left_run = left.get("run_id") or ""
    right_run = right.get("run_id") or ""
    if run_id and left_run and left_run != run_id:
        return False
    if run_id and right_run and right_run != run_id:
        return False
    return not (left_run and right_run and left_run != right_run)


def _effective_run_id(*rows, requested: str = "") -> str:
    if requested:
        return requested
    for row in rows:
        run_id = (row or {}).get("run_id") or ""
        if run_id:
            return run_id
    return ""


def _twin_link(_db, from_id: str, to_id: str, run_id: str = "", commit: bool = True):
    if from_id.startswith(("ev_", "p_")):
        event = _db.cm_get("evidence_events", from_id)
        if not event:
            raise ValueError(f"Event not found: {from_id}")
        card = _db.cm_get("judgment_cards", to_id)
        if not card:
            raise ValueError(f"Card not found: {to_id}")
        if not _run_id_compatible(event, card, run_id):
            raise ValueError(
                f"Cross-run event\u2192card link rejected: {from_id} \u2192 {to_id}"
            )
        effective_run = _effective_run_id(event, card, requested=run_id)
        _db.cm_upsert("evidence_events", from_id, {"card_id": to_id}, commit=commit)
        if effective_run:
            count = _db.cm_count(
                "evidence_events",
                where="run_id=? AND card_id=?",
                params=(effective_run, to_id),
            )
        else:
            count = _db.cm_count("evidence_events", where="card_id=?", params=(to_id,))
        _db.cm_upsert("judgment_cards", to_id, {"evidence_count": count}, commit=commit)
        return {
            "ok": True,
            "link": f"{from_id} \u2192 {to_id}",
            "type": "event\u2192card",
            "evidence_count": count,
        }

    if from_id.startswith("jc_"):
        card = _db.cm_get("judgment_cards", from_id)
        if not card:
            raise ValueError(f"Card not found: {from_id}")
        trait = _db.cm_get("cognitive_traits", to_id)
        if not trait:
            raise ValueError(f"Trait not found: {to_id}")
        if not _run_id_compatible(card, trait, run_id):
            raise ValueError(
                f"Cross-run card\u2192trait link rejected: {from_id} \u2192 {to_id}"
            )
        existing_ids = json.loads(trait.get("supporting_card_ids") or "[]")
        if from_id not in existing_ids:
            existing_ids.append(from_id)
        _db.cm_upsert(
            "cognitive_traits",
            to_id,
            {
                "supporting_card_ids": json.dumps(existing_ids),
                "evidence_count": len(existing_ids),
            },
            commit=commit,
        )
        return {
            "ok": True,
            "link": f"{from_id} \u2192 {to_id}",
            "type": "card\u2192trait",
            "evidence_count": len(existing_ids),
        }

    raise ValueError(
        "Cannot determine link type. Use ev_/p_ prefix for events, jc_ for cards."
    )


def _twin_truncated_json(rows: list, table: str, total: int, limit: int):
    """Output JSON with truncation by char budget, not just row count."""
    # First apply row limit
    if len(rows) > limit:
        rows = rows[:limit]
    # Then apply char budget: serialize incrementally and cut when over budget
    included = []
    char_count = 0
    for r in rows:
        item_json = json.dumps(r, ensure_ascii=False, default=str)
        if char_count + len(item_json) > _TWIN_MAX_OUTPUT_CHARS and included:
            break
        included.append(r)
        char_count += len(item_json)

    result: dict = {"items": included, "count": len(included), "total": total}
    if len(included) < total:
        result["truncated"] = True
        result["shown_chars"] = char_count
        result["hint"] = (
            f"Showing {len(included)} of {total} (char budget {_TWIN_MAX_OUTPUT_CHARS:,}). "
            f"Use twin-search {table} --q '...' or --domain/--tag to filter."
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_twin_stats(args):
    """Show Cognitive Handbook statistics."""
    from chatview import db as _db

    _db.init_db()
    stats = _db.get_twin_stats()

    if getattr(args, "json", False):
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    print("=== Cognitive Handbook (Digital Twin) Stats ===\n")
    fmt = "  {:<20s} {:>6s}  {:<20s}  {}"
    print(fmt.format("Table", "Count", "Confidence (avg/min/max)", "Last Updated"))
    print("  " + "-" * 70)
    for table, info in stats.items():
        count = info.get("count", 0)
        conf = info.get("confidence")
        conf_str = ""
        if conf:
            conf_str = f"{conf['avg']:.2f} / {conf['min']:.2f} / {conf['max']:.2f}"
        last = (info.get("last_updated") or "")[:16]
        print(fmt.format(table, str(count), conf_str, last))


def cmd_twin_events(args):
    """List evidence events from the evidence_events table."""
    from chatview import db as _db

    _db.init_db()

    where_parts, params = [], []
    if getattr(args, "domain", ""):
        where_parts.append("domain=?")
        params.append(args.domain)
    if getattr(args, "signal", ""):
        where_parts.append("signal_type=?")
        params.append(args.signal)
    if getattr(args, "session", ""):
        where_parts.append("session_id LIKE ?")
        params.append(f"%{args.session}%")
    if getattr(args, "run_id", ""):
        where_parts.append("run_id=?")
        params.append(args.run_id)

    where = " AND ".join(where_parts) if where_parts else ""
    total = _db.cm_count("evidence_events", where=where, params=tuple(params))
    rows = _db.cm_get_all(
        "evidence_events",
        where=where,
        params=tuple(params),
        order="created_at DESC",
        limit=args.limit,
    )

    if getattr(args, "json", False):
        _twin_truncated_json(rows, "events", total, args.limit)
        return

    print(f"=== Evidence Events ({len(rows)}/{total}) ===\n")
    fmt = "  {:<16s}  {:<14s}  {:<16s}  {:<12s}  {}"
    print(fmt.format("ID", "Session", "Task Type", "Signal", "Lesson"))
    print("  " + "-" * 80)
    for r in rows:
        sid = (r.get("session_id") or "")[:12]
        lesson = (r.get("lesson") or "")[:50]
        print(
            fmt.format(
                (r.get("id") or "")[:16],
                sid,
                (r.get("task_type") or "")[:16],
                (r.get("signal_type") or "")[:12],
                lesson,
            )
        )
    if total > args.limit:
        print(
            f"\n  (showing {args.limit} of {total} \u2014 use --limit N or twin-search events --q '...')"
        )


def cmd_twin_cards(args):
    """List judgment cards."""
    from chatview import db as _db

    _db.init_db()

    where_parts, params = [], []
    if getattr(args, "status", ""):
        where_parts.append("status=?")
        params.append(args.status)
    if getattr(args, "tag", ""):
        where_parts.append("tags LIKE ?")
        params.append(f"%{args.tag}%")
    if getattr(args, "run_id", ""):
        where_parts.append("run_id=?")
        params.append(args.run_id)
    min_conf = getattr(args, "min_confidence", None)
    if min_conf is not None:
        where_parts.append("confidence>=?")
        params.append(min_conf)

    where = " AND ".join(where_parts) if where_parts else ""
    limit = getattr(args, "limit", 50)
    total = _db.cm_count("judgment_cards", where=where, params=tuple(params))
    rows = _db.cm_get_all(
        "judgment_cards",
        where=where,
        params=tuple(params),
        order="confidence DESC",
        limit=limit,
    )

    if getattr(args, "json", False):
        _twin_truncated_json(rows, "cards", total, limit)
        return

    print(f"=== Judgment Cards ({len(rows)}/{total}) ===\n")
    for r in rows:
        rid = r.get("id", "")
        conf = r.get("confidence")
        conf_str = f"  conf={conf:.2f}" if conf is not None else ""
        status = r.get("status", "")
        status_str = f"  [{status}]" if status else ""
        when = (r.get("applies_when") or "")[:60]
        print(f"  [{rid}]{status_str}{conf_str}  {when}")
    if total > limit:
        print(
            f"\n  (showing {limit} of {total} \u2014 use --limit N or twin-search cards --q '...')"
        )


def cmd_twin_traits(args):
    """List cognitive traits."""
    from chatview import db as _db

    _db.init_db()

    where_parts, params = [], []
    if getattr(args, "status", ""):
        where_parts.append("status=?")
        params.append(args.status)
    if getattr(args, "category", ""):
        where_parts.append("category=?")
        params.append(args.category)
    if getattr(args, "run_id", ""):
        where_parts.append("run_id=?")
        params.append(args.run_id)

    where = " AND ".join(where_parts) if where_parts else ""
    total = _db.cm_count("cognitive_traits", where=where, params=tuple(params))
    rows = _db.cm_get_all(
        "cognitive_traits",
        where=where,
        params=tuple(params),
        order="strength DESC",
        limit=args.limit,
    )

    if getattr(args, "json", False):
        _twin_truncated_json(rows, "traits", total, args.limit)
        return

    print(f"=== Cognitive Traits ({len(rows)}/{total}) ===\n")
    for r in rows:
        rid = r.get("id", "")
        strength = r.get("strength")
        str_str = f"{strength:.2f}" if strength is not None else "  -"
        status = r.get("status") or ""
        category = r.get("category") or ""
        name = (r.get("name") or "")[:30]
        desc = (r.get("description") or "")[:50]
        print(f"  [{rid}] [{status}] strength={str_str}  [{category}] {name}")
        print(f"    {desc}")
        print()
    if total > args.limit:
        print(
            f"  (showing {args.limit} of {total} \u2014 use --limit N or twin-search traits --q '...')"
        )


def cmd_twin_write(args):
    """Write/update/delete Cognitive Model entries from JSON stdin."""
    from chatview import db as _db

    _db.init_db()

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON \u2014 {e}", file=sys.stderr)
        sys.exit(1)

    table = payload.get("table", "")
    if table not in _CM_VALID_TABLES:
        print(
            f"ERROR: invalid table '{table}'. Valid: {', '.join(sorted(_CM_VALID_TABLES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    operations = payload.get("operations", [])
    inserted, updated, deleted, errors = 0, 0, 0, []
    conn = _db.get_conn()

    try:
        conn.execute("BEGIN")
        for op in operations:
            action = op.get("action", "")
            if table == "card_relations":
                if action == "insert":
                    d = op.get("data", {})
                    conn.execute(
                        "INSERT OR IGNORE INTO card_relations (from_id, to_id, relation) VALUES (?,?,?)",
                        (d["from_id"], d["to_id"], d["relation"]),
                    )
                    inserted += 1
                elif action == "delete":
                    d = op.get("data", {})
                    conn.execute(
                        "DELETE FROM card_relations WHERE from_id=? AND to_id=? AND relation=?",
                        (
                            d.get("from_id", ""),
                            d.get("to_id", ""),
                            d.get("relation", ""),
                        ),
                    )
                    deleted += 1
                else:
                    raise ValueError(
                        f"card_relations supports insert/delete, got: {action}"
                    )
            elif action in ("insert", "update"):
                item_id = op.get("id") or ("p_" + uuid.uuid4().hex[:8])
                _db.cm_upsert(table, item_id, op.get("data", {}), commit=False)
                if action == "insert":
                    inserted += 1
                else:
                    updated += 1
            elif action == "delete":
                _db.cm_delete(table, op["id"], commit=False)
                deleted += 1
            else:
                raise ValueError(f"unknown action: {action}")
        conn.commit()
    except Exception as e:
        conn.rollback()
        errors.append(str(e))

    print(f"OK: {table} \u2014 inserted={inserted} updated={updated} deleted={deleted}")
    if errors:
        for err in errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        sys.exit(1)


def cmd_twin_compile(args):
    """Compile Runtime Pack from judgment cards + cognitive traits -> NL text."""
    from chatview import db as _db

    _db.init_db()

    run_id = getattr(args, "run_id", "") or ""
    lang = getattr(args, "lang", "zh") or "zh"
    where = "status IN ('confirmed','emerging')"
    params = ()
    if run_id:
        where += " AND run_id=?"
        params = (run_id,)

    # Select top cards by confidence x status weight
    cards = _db.cm_get_all(
        "judgment_cards", where=where, params=params, order="confidence DESC", limit=25
    )
    traits = _db.cm_get_all(
        "cognitive_traits", where=where, params=params, order="strength DESC", limit=15
    )

    if not cards and not traits:
        empty_msg = "No confirmed/emerging cards or traits to compile."
        print(empty_msg)
        return

    # Section headers
    if lang == "en":
        traits_header = "About This User"
        cards_header = "Situational Judgments"
        exception_label = "Exception: "
        pack_title = "Runtime Pack"
    else:
        traits_header = "\u5173\u4e8e\u8fd9\u4f4d\u7528\u6237"
        cards_header = "\u573a\u666f\u5224\u65ad"
        exception_label = "\u4f8b\u5916\uff1a"
        pack_title = "Runtime Pack"

    # Render traits section
    lines = []
    if traits:
        lines.append(traits_header)
        for t in traits:
            name = t.get("name") or ""
            desc = t.get("description") or ""
            lines.append(f"{name}\u3002{desc}")
        lines.append("")

    # Render cards section
    if cards:
        lines.append(cards_header)
        for c in cards:
            when = c.get("applies_when") or ""
            judgment = c.get("judgment") or ""
            action = c.get("agent_action") or ""
            exceptions = c.get("exceptions") or ""
            entry = f"\u2022 {when}\uff1a{judgment} {action}"
            if exceptions:
                entry += f" {exception_label}{exceptions}"
            lines.append(entry)

    pack = "\n".join(lines)
    scope = f", run_id={run_id}" if run_id else ""
    print(f"=== {pack_title} ({len(cards)} cards, {len(traits)} traits{scope}) ===\n")
    print(pack)


# ---------------------------------------------------------------------------
# Twin CRUD tools -- get / search / add / edit / link / batch
# ---------------------------------------------------------------------------


def cmd_twin_get(args):
    """Get a single event/card/trait by ID."""
    from chatview import db as _db

    _db.init_db()
    table = _TWIN_RESOURCE_TABLE.get(args.resource)
    if not table:
        print(
            f"ERROR: unknown resource '{args.resource}'. Use: events, cards, traits",
            file=sys.stderr,
        )
        sys.exit(1)
    row = _db.cm_get(table, args.id)
    if not row:
        print(json.dumps({"error": f"Not found: {args.resource}/{args.id}"}))
        sys.exit(1)
    # For cards, also include linked events
    if args.resource == "cards":
        linked = _db.cm_get_evidence_for_card(args.id)
        row["linked_events"] = linked
    print(json.dumps(row, ensure_ascii=False, indent=2, default=str))


def cmd_twin_search(args):
    """Search events/cards/traits by keyword across text fields."""
    from chatview import db as _db

    _db.init_db()
    table = _TWIN_RESOURCE_TABLE.get(args.resource)
    if not table:
        print(
            f"ERROR: unknown resource '{args.resource}'. Use: events, cards, traits",
            file=sys.stderr,
        )
        sys.exit(1)

    cols = _TWIN_SEARCH_COLS[table]
    q = args.q
    # Build WHERE clause: match keyword in any text column
    where_parts = [f"{c} LIKE ?" for c in cols]
    where = "(" + " OR ".join(where_parts) + ")"
    params = tuple(f"%{q}%" for _ in cols)

    total = _db.cm_count(table, where=where, params=params)
    rows = _db.cm_get_all(
        table,
        where=where,
        params=params,
        order=_TWIN_SEARCH_ORDER[table],
        limit=args.limit,
    )
    _twin_truncated_json(rows, args.resource, total, args.limit)


def cmd_twin_add(args):
    """Add a new event/card/trait. Reads JSON from stdin."""
    from chatview import db as _db

    _db.init_db()
    table = _TWIN_RESOURCE_TABLE.get(args.resource)
    if not table:
        print(
            f"ERROR: unknown resource '{args.resource}'. Use: events, cards, traits",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON \u2014 {e}", file=sys.stderr)
        sys.exit(1)

    # Auto-generate ID
    prefix = {"events": "ev_", "cards": "jc_", "traits": "ct_"}[args.resource]
    item_id = prefix + uuid.uuid4().hex[:8]

    # Duplicate hint: search for similar items
    hints = []
    cols = _TWIN_SEARCH_COLS[table]
    for col in cols:
        val = data.get(col, "")
        if val and len(val) > 10:
            # Take first significant phrase
            snippet = val[:30]
            where = f"{col} LIKE ?"
            dupes = _db.cm_get_all(
                table, where=where, params=(f"%{snippet}%",), limit=3
            )
            for d in dupes:
                hint_id = d.get("id", "")
                if hint_id not in [h["id"] for h in hints]:
                    hints.append(
                        {
                            "id": hint_id,
                            "match_field": col,
                            "preview": (d.get(col) or "")[:80],
                        }
                    )

    _db.cm_upsert(table, item_id, data)
    result = {"ok": True, "id": item_id, "resource": args.resource, "action": "added"}
    if hints:
        result["possible_duplicates"] = hints[:5]
        result["hint"] = (
            "Similar items found. Consider using twin-edit to merge instead."
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_twin_edit(args):
    """Edit an existing event/card/trait. Reads full JSON from stdin, overwrites."""
    from chatview import db as _db

    _db.init_db()
    table = _TWIN_RESOURCE_TABLE.get(args.resource)
    if not table:
        print(
            f"ERROR: unknown resource '{args.resource}'. Use: events, cards, traits",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check exists
    existing = _db.cm_get(table, args.id)
    if not existing:
        print(
            json.dumps(
                {
                    "error": f"Not found: {args.resource}/{args.id}. Use twin-add to create new."
                }
            )
        )
        sys.exit(1)

    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON \u2014 {e}", file=sys.stderr)
        sys.exit(1)

    _db.cm_upsert(table, args.id, data)
    print(
        json.dumps(
            {"ok": True, "id": args.id, "resource": args.resource, "action": "updated"},
            ensure_ascii=False,
        )
    )


def cmd_twin_link(args):
    """Link an event to a card, or a card to a trait."""
    from chatview import db as _db

    _db.init_db()

    try:
        result = _twin_link(
            _db, args.from_id, args.to_id, run_id=getattr(args, "run_id", "") or ""
        )
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


def cmd_twin_batch(args):
    """Execute multiple twin operations in one call. Reads JSON from stdin."""
    from chatview import db as _db

    _db.init_db()

    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON \u2014 {e}", file=sys.stderr)
        sys.exit(1)

    operations = payload.get("operations", [])
    run_id = payload.get("run_id", "") or ""
    results = []
    conn = _db.get_conn()

    try:
        conn.execute("BEGIN")
        for i, op in enumerate(operations):
            resource = op.get("resource", "")
            action = op.get("action", "")
            table = _TWIN_RESOURCE_TABLE.get(resource)

            if action == "add":
                if not table:
                    raise ValueError(f"unknown resource: {resource}")
                prefix = {"events": "ev_", "cards": "jc_", "traits": "ct_"}[resource]
                item_id = prefix + uuid.uuid4().hex[:8]
                data = dict(op.get("data", {}) or {})
                if run_id:
                    data.setdefault("run_id", run_id)
                _validate_twin_resource_data(resource, data, partial=False)
                _db.cm_upsert(table, item_id, data, commit=False)
                results.append(
                    {"index": i, "ok": True, "id": item_id, "action": "added"}
                )

            elif action == "edit":
                if not table:
                    raise ValueError(f"unknown resource: {resource}")
                item_id = op.get("id", "")
                existing = _db.cm_get(table, item_id)
                if not existing:
                    raise ValueError(f"not found: {item_id}")
                if (
                    run_id
                    and existing.get("run_id")
                    and existing.get("run_id") != run_id
                ):
                    raise ValueError(
                        f"cross-run edit rejected for {item_id}: existing run_id={existing.get('run_id')} request run_id={run_id}"
                    )
                data = dict(op.get("data", {}) or {})
                if run_id:
                    data.setdefault("run_id", run_id)
                merged = dict(existing)
                merged.update({k: v for k, v in data.items() if v is not None})
                _validate_twin_resource_data(resource, merged, partial=False)
                _db.cm_upsert(table, item_id, data, commit=False)
                results.append(
                    {"index": i, "ok": True, "id": item_id, "action": "updated"}
                )

            elif action == "link":
                link_result = _twin_link(
                    _db,
                    op.get("from", ""),
                    op.get("to", ""),
                    run_id=run_id,
                    commit=False,
                )
                results.append({"index": i, **link_result})

            else:
                raise ValueError(f"unknown action: {action}")
        conn.commit()
    except Exception as e:
        conn.rollback()
        results.append({"index": len(results), "error": str(e)})

    ok_count = sum(1 for r in results if r.get("ok"))
    err_count = sum(1 for r in results if "error" in r)
    print(
        json.dumps(
            {
                "ok": err_count == 0,
                "total": len(operations),
                "succeeded": ok_count,
                "failed": err_count,
                "run_id": run_id,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if err_count:
        sys.exit(1)


def cmd_twin_candidates(args):
    """Validate candidate Twin operations without writing to SQLite."""
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON \u2014 {e}", file=sys.stderr)
        sys.exit(1)

    operations = payload.get("operations", [])
    results = []
    for i, op in enumerate(operations):
        resource = op.get("resource", "")
        action = op.get("action", "")
        try:
            if action in ("add", "edit"):
                _validate_twin_resource_data(
                    resource, op.get("data", {}) or {}, partial=(action == "edit")
                )
            elif action == "link":
                if not op.get("from") or not op.get("to"):
                    raise ValueError("link requires from and to")
            else:
                raise ValueError(f"unknown action: {action}")
            results.append({"index": i, "ok": True})
        except Exception as e:
            results.append({"index": i, "error": str(e)})

    failed = sum(1 for r in results if "error" in r)
    print(
        json.dumps(
            {
                "ok": failed == 0,
                "total": len(operations),
                "failed": failed,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if failed:
        sys.exit(1)
