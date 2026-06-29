"""Twin AI handler functions.

Extracted from server.py — handles twin cognitive handbook analysis pipeline,
evolve sync dispatch, and twin sync to CLAUDE.md.
"""

import json
import subprocess
import sys
import uuid
from pathlib import Path

from chatview.handlers.base import (
    _json_response, _error, _sse_event, _start_sse, _read_post_body,
)
from chatview.ai_engine import (
    _run_ai_engine_stream, _select_cognitive_avatar, _normalize_ai_engine,
)


def _handle_evolve_sync(handler):
    """Handle POST /api/evolve/sync — preview or execute sync to Claude Code."""
    from chatview.handlers.sync import (
        _evolve_sync_memory_preview, _evolve_sync_memory_execute,
        _evolve_sync_claude_md_preview, _evolve_sync_claude_md_execute,
    )
    from chatview import db as _db

    raw = _read_post_body(handler)
    if raw is None:
        return
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _error(handler, 400, "Invalid JSON")
        return

    action = data.get("action", "preview")
    targets = data.get("targets", [])
    scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
    source = scope.get("source", "all")
    date = scope.get("date", "7d")
    project = scope.get("project", "")
    try:
        engine = _normalize_ai_engine(scope.get("engine", "auto"))
    except ValueError as e:
        _error(handler, 400, str(e))
        return

    if action not in ("preview", "execute"):
        _error(handler, 400, "Invalid action")
        return

    result = {}

    if "memory" in targets:
        row = _db.evolve_get("memory", source, date, project, engine)
        if row:
            try:
                mem_data = row["data"]
                if action == "preview":
                    result["memory"] = _evolve_sync_memory_preview(mem_data)
                else:
                    result["memory"] = _evolve_sync_memory_execute(mem_data)
            except Exception as e:
                result["memory"] = {"error": str(e)}
        else:
            result["memory"] = {"error": "Memory cache not found — run Refresh first"}

    if "claude_md" in targets:
        row = _db.evolve_get("profile", source, date, project, engine)
        if row:
            try:
                prof_data = row["data"]
                if action == "preview":
                    result["claude_md"] = _evolve_sync_claude_md_preview(prof_data)
                else:
                    result["claude_md"] = _evolve_sync_claude_md_execute(prof_data)
            except Exception as e:
                result["claude_md"] = {"error": str(e)}
        else:
            result["claude_md"] = {"error": "Profile cache not found — run Refresh first"}

    result["ok"] = all("error" not in v for v in result.values() if isinstance(v, dict))
    _json_response(handler, result)


def _run_twin_ai_stage(handler, prompt: str, stage_label: str) -> bool:
    """Stream a Twin AI stage and stop on either exception or SSE error event."""
    stream = _run_ai_engine_stream(prompt, allow_write=True, timeout=600)
    try:
        for evt in stream:
            _sse_event(handler, evt)
            if evt.get("type") == "error":
                return False
        return True
    except BrokenPipeError:
        raise
    except Exception as e:
        _sse_event(handler, {"type": "error", "message": f"{stage_label} failed: {e}"})
        return False
    finally:
        stream.close()


def _handle_twin_analyze(handler):
    """POST /api/twin/analyze — run 4-stage cognitive handbook extraction via AI."""
    from chatview import db as _db
    from chatview.handlers.base import _read_post_body
    import json as _json

    # Read lang from POST body if provided
    raw = _read_post_body(handler)
    lang = "zh"
    if raw:
        try:
            body = _json.loads(raw)
            lang = body.get("lang", "zh")
        except Exception:
            pass
    en = lang == "en"

    cli_path = str(Path(__file__).resolve().parent.parent.parent / "analyze.py")
    run_id = "run_" + uuid.uuid4().hex[:12]

    _start_sse(handler)
    _sse_event(handler, {"type": "text", "content": f"Twin run_id: {run_id}\n"})

    # Stage 1: Evidence event extraction
    stage1_msg = "Stage 1/5: Extracting decision events (Evidence Events)...\n" if en else "Stage 1/5: 从对话历史中提取决策事件 (Evidence Events)...\n"
    _sse_event(handler, {"type": "text", "content": stage1_msg})

    stage1_prompt = _build_twin_stage1_prompt(handler, cli_path, run_id)
    try:
        if not _run_twin_ai_stage(handler, stage1_prompt, "Stage 1"):
            return
    except BrokenPipeError:
        return

    # Stage 2: Judgment card distillation
    stage2_msg = "\n\nStage 2/5: Distilling judgment cards...\n" if en else "\n\nStage 2/5: 从事件中蒸馏判断卡 (Judgment Cards)...\n"
    _sse_event(handler, {"type": "text", "content": stage2_msg})

    stage2_prompt = _build_twin_stage2_prompt(handler, cli_path, run_id)
    try:
        if not _run_twin_ai_stage(handler, stage2_prompt, "Stage 2"):
            return
    except BrokenPipeError:
        return

    # Stage 3: Cognitive trait inference
    stage3_msg = "\n\nStage 3/5: Inferring cognitive traits...\n" if en else "\n\nStage 3/5: 从判断卡归纳认知特质 (Cognitive Traits)...\n"
    _sse_event(handler, {"type": "text", "content": stage3_msg})

    stage3_prompt = _build_twin_stage3_prompt(handler, cli_path, run_id)
    try:
        if not _run_twin_ai_stage(handler, stage3_prompt, "Stage 3"):
            return
    except BrokenPipeError:
        return

    # Stage 4: Compile Runtime Pack (pure Python, no AI)
    stage4_msg = "\n\nStage 4/5: Compiling Runtime Pack...\n" if en else "\n\nStage 4/5: 编译 Runtime Pack (twin-compile)...\n"
    _sse_event(handler, {"type": "text", "content": stage4_msg})
    try:
        r = subprocess.run(
            [sys.executable, cli_path, "twin-compile", "--run-id", run_id],
            capture_output=True, text=True, timeout=30,
        )
        _sse_event(handler, {"type": "text", "content": r.stdout or "(no output)"})
        if r.returncode != 0:
            msg = (r.stderr or r.stdout or "unknown error")[:500]
            _sse_event(handler, {"type": "error", "message": f"Stage 4 failed: {msg}"})
            return
    except Exception as e:
        _sse_event(handler, {"type": "error", "message": f"Stage 4 failed: {e}"})
        return

    # Stage 5: AI-based cognitive avatar selection
    stage5_msg = "\n\nStage 5/5: Matching cognitive model avatar...\n" if en else "\n\nStage 5/5: 匹配认知模型头像...\n"
    _sse_event(handler, {"type": "text", "content": stage5_msg})
    try:
        avatar = _select_cognitive_avatar(force=True, run_id=run_id)
        if avatar:
            match_prefix = "Match result" if en else "匹配结果"
            _sse_event(handler, {"type": "text", "content": f"{match_prefix}: {avatar.get('model_name','')} ({avatar.get('persona_id','')})"})
        else:
            no_match_msg = "Failed to match cognitive model (can retry later)" if en else "未能匹配认知模型（可稍后重试）"
            _sse_event(handler, {"type": "text", "content": no_match_msg})
    except Exception as e:
        _sse_event(handler, {"type": "text", "content": f"头像匹配跳过: {e}"})

    # Summary
    _db.init_db()
    stats = _db.get_twin_stats()
    summary_parts = []
    for t in ["evidence_events", "judgment_cards", "cognitive_traits"]:
        count = stats.get(t, {}).get("count", 0)
        if count > 0:
            label = t.replace("_", " ")
            summary_parts.append(f"{label}: {count}")

    no_data_msg = "No data" if en else "暂无数据"
    summary = ", ".join(summary_parts) if summary_parts else no_data_msg
    complete_msg = "Analysis complete" if en else "分析完成"
    try:
        _sse_event(handler, {"type": "text", "content": f"\n\n✅ {complete_msg} — {summary}"})
        _sse_event(handler, {"type": "done", "content": summary})
    except BrokenPipeError:
        pass


def _build_twin_stage1_prompt(handler, cli_path: str, run_id: str) -> str:
    """Build prompt for Stage 1: Evidence event extraction from conversation history."""
    from chatview.handlers.evolve import _collect_profile_digest
    digest = _collect_profile_digest(handler, "all", "all", "", cli_path)

    return f"""# Background

You are extracting structured EVIDENCE EVENTS from a user's AI conversation history.
An evidence event records: what the AI did → how the user reacted → what lesson was learned.

# CLI Tool

  python3 {cli_path} <command> [options]

Commands for exploration:
  corrections    — Find where the user corrected/rejected AI output (50+ signal words)
  queries        — Extract user questions/requests across sessions
  highlights     — Sessions ranked by correction frequency
  read <id> -s   — Read a specific session (summary mode)
  search <q>     — Full-text search across sessions

Commands for reading existing data:
  twin-events [--domain X] [--signal Y] [--limit N] --json  — List existing evidence events
  twin-get events <id>                                      — Get a single event by ID
  twin-search events --q "keyword" --json                   — Search events by keyword

Commands for writing:
  twin-add events       — Add a new event (JSON from stdin, auto-generates ID)
  twin-edit events <id> — Edit an existing event (JSON from stdin, overwrites)
  twin-batch            — Execute multiple add/edit operations in one call
  twin-candidates       — Validate candidate operations without writing

# Current Run Scope

Run ID: {run_id}
All writes in this run MUST use `twin-batch` with top-level `"run_id": "{run_id}"`.

# Pre-computed Profile Digest

{digest}

# Task

1. First, run `python3 {cli_path} twin-events --json` to see ALL existing events. Check what's already been captured — avoid duplicates.
2. Run `python3 {cli_path} corrections --limit 100` to get all correction events.
3. Run `python3 {cli_path} highlights --limit 20` to find high-signal sessions.
4. For the top 5-8 most interesting sessions, run `python3 {cli_path} read <id> -s` to understand context.
5. Also run `python3 {cli_path} queries --limit 50` and look for acceptance patterns — cases where the user did NOT correct the AI (positive signals).

From these, extract new evidence events. Compare with existing events — if an event already exists for the same session and similar situation, use `twin-edit` to update/enrich it. Only `twin-add` genuinely new events.

Write events using the CRUD tools:

# Add a new event:
python3 {cli_path} twin-add events <<'EOF'
{{
  "session_id": "actual-session-id",
  "event_index": 1,
  "task_type": "coding|review|design|research|communication",
  "ai_action": "AI did what (1 sentence)",
  "user_reaction": "User reacted how (1 sentence)",
  "resolution": "What happened in the end",
  "lesson": "What we learned from this (reusable insight)",
  "signal_type": "correction|acceptance|escalation|question",
  "signal_intensity": 0.0-1.0,
  "domain": "domain tag (e.g., coding/scope, review/verification, design/architecture)"
}}
EOF

# Edit an existing event (e.g. enrich lesson, update intensity):
python3 {cli_path} twin-edit events <event_id> <<'EOF'
{{"lesson": "improved lesson text", "signal_intensity": 0.85}}
EOF

# Or use batch for multiple operations at once:
python3 {cli_path} twin-batch <<'EOF'
{{"run_id": "{run_id}", "operations": [
  {{"resource": "events", "action": "add", "data": {{...}}}},
  {{"resource": "events", "action": "edit", "id": "ev_xxx", "data": {{...}}}}
]}}
EOF

Quality requirements:
- MUST include real session_id from the corrections/highlights data
- signal_intensity: 0.9+ for explicit strong corrections, 0.5-0.8 for mild corrections, 0.3-0.5 for acceptance signals
- domain: use slash format like "coding/scope", "review/neutrality", "design/simplicity"
- lesson: write as a reusable insight, not specific to one case
- Balance: include BOTH correction episodes AND acceptance episodes (positive signals)
- IMPORTANT: Always check existing events first. If a similar event exists, use twin-edit to enrich it rather than creating a duplicate with twin-add.
- IMPORTANT: For this run, use only `twin-batch` with run_id `{run_id}` for writes.
- All text in Chinese
"""


def _build_twin_stage2_prompt(handler, cli_path: str, run_id: str) -> str:
    """Build prompt for Stage 2: Judgment card distillation from evidence events."""
    from chatview import db as _db
    _db.init_db()

    # Get current-run cards/events only; cross-run data is not Stage 2 input.
    existing_cards = _db.cm_get_all("judgment_cards", where="run_id=?", params=(run_id,), limit=100)
    events = _db.cm_get_all("evidence_events", where="run_id=?", params=(run_id,),
                            order="created_at DESC", limit=100)
    events_json = json.dumps([dict(e) for e in events], ensure_ascii=False, default=str)

    # Get latest Profile/Memory as supplementary input from SQLite.
    profile_summary = ""
    memory_summary = ""
    try:
        pr = _db.evolve_latest("profile")
        if pr:
            cats = [c.get("name", "") for c in pr["data"].get("categories", [])]
            profile_summary = f"Existing Profile categories: {', '.join(cats)}"
    except Exception:
        pass
    try:
        mr = _db.evolve_latest("memory")
        if mr:
            labels = [n.get("label", "") for n in mr["data"].get("nodes", [])]
            memory_summary = f"Existing Memory labels: {', '.join(labels)}"
    except Exception:
        pass

    existing_cards_str = ""
    if existing_cards:
        lines = []
        for c in existing_cards[:30]:
            lines.append(f"  id={c.get('id','')} applies_when={json.dumps(c.get('applies_when',''), ensure_ascii=False)} "
                         f"judgment={json.dumps((c.get('judgment','') or '')[:80], ensure_ascii=False)} "
                         f"tags={c.get('tags','')} status={c.get('status','')} confidence={c.get('confidence','')}")
        existing_cards_str = "\n".join(lines)
    else:
        existing_cards_str = "  (empty — no existing cards)"

    return f"""# Background

You are distilling JUDGMENT CARDS from structured evidence events extracted from a user's AI conversation history.
A judgment card captures a situation-specific judgment pattern: when does this apply → how the user thinks about it → what the AI should do.

# CLI Tool

  python3 {cli_path} <command>

Commands for reading:
  twin-cards [--status X] [--tag Y] --json    — List all existing judgment cards
  twin-get cards <id>                         — Get a single card with linked events
  twin-search cards --q "keyword" --json      — Search cards by keyword
  twin-events --json                          — List all evidence events

Commands for writing:
  twin-add cards        — Add a new card (JSON from stdin)
  twin-edit cards <id>  — Edit an existing card (JSON from stdin, overwrites)
  twin-link <event_id> <card_id>  — Link an event to a card
  twin-batch            — Execute multiple operations in one call

# Current Run Scope

Run ID: {run_id}
All writes/links in this stage MUST use `twin-batch` with top-level `"run_id": "{run_id}"`.

# Evidence Events (input data)

{events_json}

# Supplementary data

{profile_summary}
{memory_summary}

# Existing Judgment Cards (for dedup — merge if similar, insert if new)

{existing_cards_str}

# Task

Analyze the events above and distill judgment cards. This is INCREMENTAL — you are updating an existing knowledge base, not building from scratch.

**Workflow:**

1. First review the existing cards above carefully.
2. For each cluster of related events, decide:
   - **If a similar card already exists** → use `twin-edit cards <id>` to refine it (improve judgment text, update confidence, etc.)
   - **If it's a genuinely new pattern** → use `twin-add cards` to create a new card
3. After creating/updating cards, link events to cards using `twin-link <event_id> <card_id>`

**Writing examples:**

# Add a new card:
python3 {cli_path} twin-add cards <<'EOF'
{{
  "applies_when": "触发场景（1-2句）",
  "judgment": "用户的推理逻辑（自然语言段落，2-4句）",
  "agent_action": "AI 应该怎么做（1-2句）",
  "exceptions": "例外条件",
  "tags": "[\\"tag1\\", \\"tag2\\"]",
  "confidence": 0.7,
  "status": "hypothesis",
  "evidence_count": 1
}}
EOF

# Edit an existing card (e.g. strengthen with new evidence):
python3 {cli_path} twin-edit cards jc_xxx <<'EOF'
{{
  "judgment": "refined judgment text...",
  "confidence": 0.85,
  "status": "emerging",
  "evidence_count": 3
}}
EOF

# Link events to cards:
python3 {cli_path} twin-link ev_xxx jc_yyy

# Or batch multiple operations:
python3 {cli_path} twin-batch <<'EOF'
{{"run_id": "{run_id}", "operations": [
  {{"resource": "cards", "action": "add", "data": {{...}}}},
  {{"resource": "cards", "action": "edit", "id": "jc_xxx", "data": {{...}}}},
  {{"resource": "link", "action": "link", "from": "ev_xxx", "to": "jc_yyy"}}
]}}
EOF

# Key design principles

- **judgment field is natural language**: Merge the user's values, causal reasoning into a coherent paragraph. The consumer is an LLM — NL is its most efficient input format.
- **agent_action is executable**: Write it as a concrete instruction the AI can follow, not an abstract principle.
- **Tags for retrieval**: Use consistent tag vocabulary (scope, style, communication, design, review, testing, etc.)
- **Status rules**: first appearance → "hypothesis"; supported by 2+ events from different contexts → "emerging"; 3+ events across projects → "confirmed"
- **All text in Chinese**
- **Dedup carefully**: Two events about "不要改无关文件" and "只改必要代码" should merge into one card, not create two. Use `twin-edit` to merge, not `twin-add` to duplicate.
"""


def _build_twin_stage3_prompt(handler, cli_path: str, run_id: str) -> str:
    """Build prompt for Stage 3: Cognitive trait inference from judgment cards."""
    from chatview import db as _db
    _db.init_db()

    cards = _db.cm_get_all("judgment_cards", where="run_id=?", params=(run_id,),
                           order="confidence DESC", limit=100)
    cards_json = json.dumps([dict(c) for c in cards], ensure_ascii=False, default=str)

    existing_traits = _db.cm_get_all("cognitive_traits", where="run_id=?", params=(run_id,), limit=50)
    existing_str = ""
    if existing_traits:
        lines = []
        for t in existing_traits[:20]:
            lines.append(f"  id={t.get('id','')} name={json.dumps(t.get('name',''), ensure_ascii=False)} "
                         f"category={t.get('category','')} status={t.get('status','')} strength={t.get('strength','')}")
        existing_str = "\n".join(lines)
    else:
        existing_str = "  (empty — no existing traits)"

    return f"""# Background

You are inferring COGNITIVE TRAITS from judgment cards. Traits are personality-level characteristics
that explain WHY the user makes certain judgments. Multiple cards pointing to the same underlying
pattern should be abstracted into one trait.

# CLI Tool

  python3 {cli_path} <command>

Commands for reading:
  twin-traits [--category X] [--status X] --json  — List existing cognitive traits
  twin-get traits <id>                             — Get a single trait by ID
  twin-search traits --q "keyword" --json          — Search traits by keyword
  twin-cards --json                                — List all judgment cards

Commands for writing:
  twin-add traits        — Add a new trait (JSON from stdin)
  twin-edit traits <id>  — Edit an existing trait (JSON from stdin, overwrites)
  twin-link <card_id> <trait_id>  — Link a card to a trait
  twin-batch             — Execute multiple operations in one call

# Current Run Scope

Run ID: {run_id}
All writes/links in this stage MUST use `twin-batch` with top-level `"run_id": "{run_id}"`.

# Judgment Cards (input data)

{cards_json}

# Existing Cognitive Traits (for dedup)

{existing_str}

# Task

Analyze the judgment cards above and infer cognitive traits. This is INCREMENTAL — update existing traits or add new ones.

Categories:
- **价值取向**: What the user protects/sacrifices (e.g., 极简主义, 最小影响原则)
- **决策风格**: How the user makes judgments (e.g., 证据先行, 风险厌恶, 谨慎型)
- **协作模式**: How the user works with AI (e.g., 高控制偏好, 主导型, 方案先行)
- **能力边界**: Domain expertise levels (e.g., 后端专家/前端学习中)
- **思维模式**: Cognitive habits (e.g., 系统性思维, 发散-收敛型)

**Workflow:**

1. Review existing traits above.
2. For each group of related cards:
   - **If a similar trait exists** → `twin-edit traits <id>` to refine description, update strength
   - **If genuinely new** → `twin-add traits`
3. Link supporting cards to traits: `twin-link jc_xxx ct_yyy`

**Writing examples:**

# Add a new trait:
python3 {cli_path} twin-add traits <<'EOF'
{{
  "name": "特质名称",
  "category": "价值取向|决策风格|协作模式|能力边界|思维模式",
  "description": "自然语言描述（2-4句）",
  "strength": 0.7,
  "supporting_card_ids": "[\\"jc_xxx\\", \\"jc_yyy\\"]",
  "status": "emerging",
  "evidence_count": 2
}}
EOF

# Edit an existing trait:
python3 {cli_path} twin-edit traits ct_xxx <<'EOF'
{{
  "description": "refined description...",
  "strength": 0.85,
  "status": "confirmed"
}}
EOF

# Key principles
- **Each trait must be supported by ≥2 cards**: Don't infer traits from a single card
- **description is natural language**: Explain the trait so an AI can predict behavior in new scenarios
- **supporting_card_ids must reference real card IDs** from the input data above
- **Dedup carefully**: If a similar trait exists, use twin-edit to enrich it, not twin-add to duplicate
- **Status follows card evidence**: all hypothesis cards → hypothesis; emerging/confirmed cards → emerging/confirmed
- **All text in Chinese**
"""


def _handle_twin_sync(handler):
    """POST /api/twin/sync — compile runtime pack from cards+traits into CLAUDE.md."""
    from chatview import db as _db

    CLAUDE_MD_PATH = Path.home() / ".claude" / "CLAUDE.md"
    CM_MARKER_START = "<!-- cognitive-handbook:start -->"
    CM_MARKER_END = "<!-- cognitive-handbook:end -->"

    try:
        cards = _db.cm_get_all(
            "judgment_cards",
            where="status IN ('confirmed','emerging')",
            order="confidence DESC",
            limit=25,
        )
        traits = _db.cm_get_all(
            "cognitive_traits",
            where="status IN ('confirmed','emerging')",
            order="strength DESC",
            limit=15,
        )
    except Exception as e:
        _json_response(handler, {"ok": False, "error": str(e)})
        return

    # Build CLAUDE.md section — render as natural language
    lines = [CM_MARKER_START, "## Cognitive Handbook (Auto-sync)", ""]

    if traits:
        lines.append("### 关于这位用户")
        lines.append("")
        for t in traits:
            name = t.get("name") or ""
            desc = t.get("description") or ""
            lines.append(f"**{name}**。{desc}")
            lines.append("")

    if cards:
        lines.append("### 场景判断")
        lines.append("")
        for c in cards:
            when = c.get("applies_when") or ""
            judgment = c.get("judgment") or ""
            action = c.get("agent_action") or ""
            exceptions = c.get("exceptions") or ""
            lines.append(f"**{when}**：{judgment}")
            if action:
                lines.append(f"→ {action}")
            if exceptions:
                lines.append(f"例外：{exceptions}")
            lines.append("")

    lines.append(CM_MARKER_END)
    section = "\n".join(lines) + "\n"

    CLAUDE_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = CLAUDE_MD_PATH.read_text(encoding="utf-8") if CLAUDE_MD_PATH.exists() else ""

    if CM_MARKER_START in existing and CM_MARKER_END in existing:
        start_idx = existing.index(CM_MARKER_START)
        end_idx = existing.index(CM_MARKER_END) + len(CM_MARKER_END)
        new_text = existing[:start_idx] + section + existing[end_idx:]
        claude_md_status = "replaced"
    else:
        if existing and not existing.endswith("\n\n"):
            existing = existing.rstrip("\n") + "\n\n"
        new_text = existing + section
        claude_md_status = "appended"
    CLAUDE_MD_PATH.write_text(new_text, encoding="utf-8")

    _json_response(handler, {
        "ok": True,
        "cards_synced": len(cards),
        "traits_synced": len(traits),
        "claude_md": {"status": claude_md_status, "lines": len(section.strip().split("\n"))},
    })
