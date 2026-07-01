"""Higher-recall retrieval commands for history distillation workflows."""

import json
import re
import sqlite3
from datetime import datetime
from math import log2


_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_SPLIT_RE = re.compile(r"[\s,;，。！？、:/_\-]+")

_SYNONYMS = {
    "记忆": ["memory", "记住", "偏好"],
    "偏好": ["memory", "习惯"],
    "范围": ["scope"],
    "确认": ["确认", "confirm"],
    "历史": ["history"],
    "搜索": ["search", "检索"],
    "召回": ["recall"],
    "准确": ["accuracy", "精准"],
    "截图": ["screenshot", "Playwright"],
    "验证": ["verify", "test", "测试"],
    "前端": ["frontend", "UI"],
    "回写": ["sync", "memory"],
    "工具": ["tool", "CLI"],
    "纠正": ["correction", "修正"],
    "趋势": ["trend"],
}

_NOISE_PATTERNS = [
    ("task_notification", re.compile(r"<task-notification|</task-id>|<output-file>|toolu_", re.I)),
    ("continuation_summary", re.compile(r"This session is being continued from a previous conversation|Summary:\s*\n", re.I)),
    ("ide_context", re.compile(r"# Context from my IDE setup|Active file:|Open tabs:", re.I)),
    ("retrieval_work_product", re.compile(
        r"Pre-collected Data \(do NOT re-run these\)|Full-text search across all sessions Options:|"
        r"pre-computed project distribution \+ daily activity as JSON|=== STATS ===",
        re.I,
    )),
    ("agent_prompt", re.compile(
        r"You are Agent\b|You are independently|You are review|You are extracting structured|"
        r"You have a CLI tool for analyzing conversation history|Acceptance self-test|"
        r"Base directory for this skill|你是一个严格、独立的标注员|任务：判断每条|"
        r"你是.{0,80}(?:子\s*agent|subagent)|任务：不要写泛泛趋势",
        re.I,
    )),
    ("structured_noise", re.compile(r"(?:^|\n)\s*(?:<|\{|\[Request interrupted|```|toolu_)", re.I)),
]


def query_tokens(query: str) -> list:
    """Return deduplicated lexical tokens plus small CJK bigrams and synonyms."""
    raw_tokens = [t for t in _SPLIT_RE.split((query or "").strip()) if len(t) >= 2]
    tokens = []
    for token in raw_tokens:
        tokens.append(token)
        tokens.extend(_SYNONYMS.get(token, []))
        for cjk in _CJK_RE.findall(token):
            if len(cjk) >= 4:
                tokens.extend(cjk[i:i + 2] for i in range(len(cjk) - 1))
    deduped = []
    seen = set()
    for token in tokens:
        key = token.lower()
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        deduped.append(token)
    return deduped


def is_noise_text(text: str) -> bool:
    """Return True when text is likely orchestration/system noise, not user signal."""
    sample = (text or "")[:5000]
    return any(pattern.search(sample) for _, pattern in _NOISE_PATTERNS)


def _noise_reason(text: str) -> str:
    sample = (text or "")[:5000]
    for reason, pattern in _NOISE_PATTERNS:
        if pattern.search(sample):
            return reason
    return ""


def _sanitize_fts_token(token: str) -> str:
    return re.sub(r'["*\(\)\{\}\[\]^~:]', "", token)


def _fts_or_rows(query: str, limit: int) -> list:
    """FTS OR candidate retrieval. Returns raw message rows."""
    from chatview import db as _db

    tokens = [_sanitize_fts_token(t) for t in query_tokens(query)]
    tokens = [t for t in tokens if t]
    if not tokens:
        return []
    match = " OR ".join(f'"{t}"' for t in tokens[:12])
    sql = """
        SELECT m.id, m.session_id, m.idx, m.role, m.text, m.ts,
               s.title, s.project_name, s.source
        FROM messages_fts fts
        JOIN messages m ON fts.rowid = m.id
        JOIN sessions s ON m.session_id = s.id
        WHERE messages_fts MATCH ?
        LIMIT ?
    """
    try:
        rows = _db.get_conn().execute(sql, [match, limit]).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def _eligible_session_ids(args) -> set:
    from chatview import db as _db

    days_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
    max_days = days_map.get(getattr(args, "date", ""), 99999)
    sessions = _db.get_filtered_sessions(
        source=getattr(args, "source", "all"),
        project=getattr(args, "project", ""),
        max_days=max_days,
    )
    return {s["id"] for s in sessions}


def _make_snippet(text: str, query: str, tokens: list, ctx: int = 80) -> str:
    lower = (text or "").lower()
    probes = [query.lower()] + [t.lower() for t in tokens]
    idx = -1
    probe_len = len(query)
    for probe in probes:
        if not probe:
            continue
        idx = lower.find(probe)
        if idx != -1:
            probe_len = len(probe)
            break
    if idx == -1:
        return (text or "")[:180]
    start = max(0, idx - ctx)
    end = min(len(text), idx + probe_len + ctx)
    return ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")


def _add_candidate(candidates: dict, row: dict, query: str, tokens: list, reason: str, base_score: float):
    sid = row.get("session_id") or row.get("sessionId")
    idx = row.get("idx", 0) or 0
    key = (sid, idx)
    text = row.get("text") or row.get("snippet") or ""
    title = row.get("title") or "Untitled"
    project = row.get("project_name") or row.get("project") or ""
    hay = f"{title} {project} {text}".lower()
    token_hits = [t for t in tokens if t.lower() in hay]
    score = base_score + len(token_hits) * 3
    role = row.get("role", "")
    if role == "user":
        score += 8
    elif role == "assistant":
        score -= 8
    if query.lower() in hay:
        score += 12
    if token_hits and text and all(t.lower() in text.lower() for t in token_hits[:2]):
        score += 3
    artifact_reason = _noise_reason(f"{title}\n{text}")
    if artifact_reason:
        score -= 18
        reason = f"{reason}:artifact_downranked"

    existing = candidates.get(key)
    if existing:
        existing["score"] += score
        existing["reasons"].add(reason)
        existing["tokenHits"].update(token_hits)
        if artifact_reason and not existing.get("artifactReason"):
            existing["artifactReason"] = artifact_reason
        return

    item = {
        "sessionId": sid,
        "title": title,
        "project": project,
        "source": row.get("source", ""),
        "date": (row.get("ts") or row.get("date") or "")[:19],
        "messageIndex": idx,
        "role": role,
        "snippet": _make_snippet(text or title, query, tokens),
        "score": score,
        "reasons": {reason},
        "tokenHits": set(token_hits),
    }
    if artifact_reason:
        item["artifactReason"] = artifact_reason
    candidates[key] = item


def _has_enough_clean_exact_user_matches(candidates: dict, query: str, limit: int) -> bool:
    """Return True when expensive token scan is unlikely to improve top evidence."""
    needed = min(3, max(2, limit // 10))
    q = (query or "").strip().lower()
    if len(q) < 2:
        return False

    clean_exact = 0
    for item in candidates.values():
        if item.get("role") != "user" or item.get("artifactReason"):
            continue
        if "message_fts" not in item.get("reasons", set()):
            continue
        snippet = (item.get("snippet") or "").lower()
        if q not in snippet:
            continue
        clean_exact += 1
        if clean_exact >= needed:
            return True
    return False


def _token_scan_rows(eligible: set, tokens: list) -> list:
    """Return a bounded role=user token-scan pool using SQL LIKE prefiltering."""
    from chatview import db as _db

    if not tokens:
        return []
    like_terms = _dedupe_lower(tokens)[:10]
    like_clauses = []
    like_params = []
    for term in like_terms:
        like_clauses.append("(m.text LIKE ? OR s.title LIKE ? OR s.project_name LIKE ?)")
        value = f"%{term}%"
        like_params.extend([value, value, value])

    token_where = " OR ".join(like_clauses) if like_clauses else "1=1"
    rows = _db.query_in_chunks(_db.get_conn(), f"""
        SELECT m.session_id, m.idx, m.role, m.text, m.ts,
               s.title, s.project_name, s.source
        FROM messages m JOIN sessions s ON m.session_id = s.id
        WHERE m.session_id IN ({{placeholders}})
          AND m.role = 'user'
          AND ({token_where})
    """, list(eligible), extra_params=tuple(like_params))
    return [dict(row) for row in rows]


def search_plus_data(query: str, args) -> list:
    """Return ranked hybrid search results with match reasons."""
    if not query or len(query.strip()) < 2:
        return []

    from chatview import db as _db

    _db.init_db()
    eligible = _eligible_session_ids(args)
    if not eligible:
        return []

    limit = max(getattr(args, "limit", 50), 1)
    tokens = query_tokens(query)
    candidates = {}

    # 1. Existing exact/AND-ish FTS path.
    for row in _db.search_fts(query, limit=max(limit * 6, 100)):
        if row["session_id"] in eligible:
            _add_candidate(candidates, row, query, tokens, "message_fts", 30)

    # 2. Wider FTS OR path.
    for row in _fts_or_rows(query, limit=max(limit * 10, 150)):
        if row["session_id"] in eligible:
            _add_candidate(candidates, row, query, tokens, "fts_or", 14)

    # 3. Title/project FTS path.
    for row in _db.search_title_fts(query, limit=max(limit * 6, 100)):
        if row["session_id"] not in eligible:
            continue
        title_row = {
            "session_id": row["session_id"],
            "idx": 0,
            "text": f"{row.get('title', '')} {row.get('project_name', '')}",
            "title": row.get("title", ""),
            "project_name": row.get("project_name", ""),
            "source": row.get("source", ""),
            "date": row.get("date", ""),
            "role": "session",
        }
        _add_candidate(candidates, title_row, query, tokens, "title_project", 22)

    # 4. Token scan catches compact Chinese phrases and synonym rewrites.
    # It is the expensive path, so skip it when exact FTS already produced
    # enough clean user evidence for the requested result size.
    if tokens and not _has_enough_clean_exact_user_matches(candidates, query, limit):
        for data in _token_scan_rows(eligible, tokens):
            hay = f"{data.get('title', '')} {data.get('project_name', '')} {data.get('text', '')}".lower()
            hits = [t for t in tokens if t.lower() in hay]
            if not hits:
                continue
            # A single synonym hit is useful for short Chinese queries, but score keeps it below exact FTS.
            base = 6 if len(hits) == 1 else 10
            _add_candidate(candidates, data, query, tokens, "token_scan", base)

    results = []
    for item in candidates.values():
        item["reasons"] = sorted(item["reasons"])
        item["tokenHits"] = sorted(item["tokenHits"])
        item["score"] = round(item["score"], 2)
        results.append(item)
    results.sort(key=lambda r: (r["score"], 1 if r.get("role") == "user" else 0, r.get("date", "")), reverse=True)
    return results[:limit]


_LATIN_RE = re.compile(r"[a-z0-9]+", re.I)
_PATHY_RE = re.compile(
    r"(/tmp/|/private/|~?/\.|[A-Za-z0-9_-]+/[A-Za-z0-9_{}.-]+|"
    r"\.jsonl?\b|\.py\b|\.ts\b|--[a-z0-9-]+|\{[^}]{1,80}\})",
    re.I,
)
_USER_REQUEST_RE = re.compile(
    r"你(?:先|再|帮|自己|派|去|继续|列|想|可以|需要|觉得|看|分析|测试|做|跑)|"
    r"帮我|让你|请|麻烦|能不能|是不是|怎么样|我要|我想|我的意思",
    re.I,
)


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _compact_for_phrase(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", (text or "").lower()).strip()


def _has_latin_token(text: str, token: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(token.lower())}(?![a-z0-9])", (text or "").lower()) is not None


def _has_phrase(text: str, phrase: str) -> bool:
    phrase = (phrase or "").strip()
    if not phrase:
        return False
    lower = (text or "").lower()
    p_lower = phrase.lower()
    if _has_cjk(phrase):
        return p_lower in lower
    normalized_phrase = _compact_for_phrase(phrase)
    if " " in normalized_phrase:
        return normalized_phrase in _compact_for_phrase(text)
    if "-" in p_lower or "_" in p_lower:
        return normalized_phrase in _compact_for_phrase(text)
    if p_lower == "autoresearch":
        return p_lower in re.sub(r"[^a-z0-9]+", "", lower)
    return _has_latin_token(text, p_lower)


def _matched_terms(text: str, terms: list) -> list:
    return [term for term in terms if _has_phrase(text, term)]


def _analyze_repeat_query(query: str) -> dict:
    q = query or ""
    latin = [t.lower() for t in _LATIN_RE.findall(q)]
    cjk_terms = []
    for cjk in _CJK_RE.findall(q):
        if len(cjk) >= 2:
            cjk_terms.append(cjk)
            if len(cjk) >= 4:
                cjk_terms.extend(cjk[i:i + 2] for i in range(len(cjk) - 1))

    has_auto_research = (
        "autoresearch" in q.lower()
        or "auto-research" in q.lower()
        or ("auto" in latin and "research" in latin)
    )
    if has_auto_research:
        topic_anchors = [
            "AutoResearch",
            "auto-research",
            "auto research",
            "autoresearch",
            "自动实验",
            "自进化研究",
            "AI Scientist",
        ]
        generic_terms = ["research", "研究", "自己", "你自己", "自动", "auto"]
        intent_terms = [
            "你自己做",
            "自己做",
            "你自己",
            "派多个子agent",
            "多个子agent",
            "多agent",
            "subagent",
            "自动实验",
            "自进化",
            "自己完成",
            "复杂任务",
        ]
    else:
        stop = {"the", "and", "for", "with", "you", "your", "自己", "一下", "帮我", "查询", "搜索", "分析"}
        topic_anchors = [t for t in latin if len(t) >= 4 and t not in stop]
        topic_anchors.extend(t for t in cjk_terms if t not in stop and len(t) >= 2)
        generic_terms = [t for t in query_tokens(q) if len(t) >= 2]
        intent_terms = ["自己做", "帮我", "分析", "搜索", "调研", "实现", "优化", "完成"]

    def dedupe(items):
        out = []
        seen = set()
        for item in items:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    return {
        "topicAnchors": dedupe(topic_anchors),
        "intentTerms": dedupe(intent_terms),
        "genericTerms": dedupe(generic_terms),
    }


def _extract_request_span(text: str) -> tuple:
    markers = [
        "## My request for Codex:",
        "## My request for Claude:",
        "My request for Codex:",
        "My request:",
    ]
    for marker in markers:
        pos = (text or "").find(marker)
        if pos != -1:
            return (text[pos + len(marker):].strip(), True)
    return text or "", False


def _min_distance(text: str, left_terms: list, right_terms: list):
    lower = (text or "").lower()
    positions_left = []
    positions_right = []
    for term in left_terms:
        idx = lower.find(term.lower())
        if idx >= 0:
            positions_left.append(idx)
    for term in right_terms:
        idx = lower.find(term.lower())
        if idx >= 0:
            positions_right.append(idx)
    if not positions_left or not positions_right:
        return None
    return min(abs(a - b) for a in positions_left for b in positions_right)


def _looks_technical_spec(text: str) -> bool:
    sample = text or ""
    if _PATHY_RE.search(sample):
        return True
    return sample.count("{") + sample.count("}") >= 4 or sample.count("/") >= 5


def _has_user_request_cue(text: str) -> bool:
    return _USER_REQUEST_RE.search(text or "") is not None


def _canonical_repeat_text(text: str) -> str:
    value = (text or "").lower()
    value = re.sub(r"/(?:private/)?tmp/[^\s<>\"']+", "<tmp-path>", value)
    value = re.sub(r"[0-9a-f]{16,}", "<hex>", value)
    value = re.sub(r"\d{4}-\d{2}-\d{2}[t\s]\d{2}:\d{2}:\d{2}(?:z)?", "<timestamp>", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()[:500]


def _repeat_candidate_from_row(row: dict, analysis: dict, query: str) -> dict:
    text = row.get("text") or ""
    title = row.get("title") or ""
    project = row.get("project_name") or ""
    text_sample = text[:6000]
    full = f"{title}\n{project}\n{text_sample}"
    span, extracted_request = _extract_request_span(text)
    span_sample = span[:6000]
    meta_text = f"{title}\n{project}"
    match_text = f"{meta_text}\n{span_sample}"

    artifact_reason = _noise_reason(full)
    request_cue = _has_user_request_cue(span_sample)
    topic_hits_span = _matched_terms(span_sample, analysis["topicAnchors"])
    topic_hits_meta = _matched_terms(meta_text, analysis["topicAnchors"])
    topic_hits = []
    for term in topic_hits_span + topic_hits_meta:
        if term not in topic_hits:
            topic_hits.append(term)
    intent_hits = _matched_terms(span_sample, analysis["intentTerms"])
    generic_hits = _matched_terms(match_text, analysis["genericTerms"])
    distance = _min_distance(span_sample, topic_hits_span, intent_hits)
    close_topic_intent = distance is not None and distance <= 160

    penalties = []
    if artifact_reason:
        penalties.append(artifact_reason)
    if extracted_request and artifact_reason == "ide_context":
        penalties.append("request_span_extracted")
    technical_spec = _looks_technical_spec(span_sample)
    if technical_spec:
        penalties.append("technical_spec_shape")

    if artifact_reason and not (extracted_request and topic_hits_span):
        item_class = artifact_reason
        bucket = "artifacts"
        tier = "artifact"
    elif topic_hits_span and request_cue and (intent_hits or close_topic_intent) and not technical_spec:
        item_class = "direct_task"
        bucket = "strong_evidence"
        tier = "A"
    elif topic_hits:
        item_class = "related_support"
        bucket = "related_context"
        tier = "B"
    elif generic_hits and (len(generic_hits) >= 2 or intent_hits):
        item_class = "technical_spec" if technical_spec else "weak_keyword"
        bucket = "weak_matches"
        tier = "C"
    else:
        return {}

    matched_slots = []
    if topic_hits:
        matched_slots.append("topic_anchor")
    if topic_hits_span:
        matched_slots.append("message_topic_anchor")
    elif topic_hits_meta:
        matched_slots.append("metadata_topic_anchor")
    if intent_hits:
        matched_slots.append("intent")
    if request_cue:
        matched_slots.append("user_request_cue")
    if generic_hits:
        matched_slots.append("generic_keyword")
    if close_topic_intent:
        matched_slots.append("topic_intent_proximity")

    score = 0.0
    if topic_hits_span:
        score += 70 + min(len(topic_hits), 3) * 5
    elif topic_hits_meta:
        score += 48 + min(len(topic_hits_meta), 3) * 4
    if intent_hits:
        score += 18 + min(len(intent_hits), 3) * 4
    if request_cue:
        score += 8
    if close_topic_intent:
        score += 10
    score += min(len(generic_hits), 4) * 2
    if technical_spec:
        score -= 22
    if artifact_reason:
        score -= 35
    if bucket == "weak_matches":
        score = min(score, 38)
    if bucket == "artifacts":
        score = min(score, 20)

    return {
        "sessionId": row.get("session_id"),
        "title": title or "Untitled",
        "project": project,
        "source": row.get("source") or "",
        "date": (row.get("ts") or "")[:19],
        "messageIndex": row.get("idx") or 0,
        "text": text,
        "snippet": _make_snippet(span_sample, query, analysis["topicAnchors"] + analysis["genericTerms"]),
        "canonical": _canonical_repeat_text(span_sample),
        "bucket": bucket,
        "tier": tier,
        "class": item_class,
        "score": score,
        "artifactReason": artifact_reason,
        "topicHits": topic_hits,
        "intentHits": intent_hits,
        "genericHits": generic_hits,
        "matchedSlots": matched_slots,
        "penalties": penalties,
    }


def _cluster_repeat_candidates(candidates: list, limit: int) -> dict:
    grouped = {}
    for item in candidates:
        key = (item["bucket"], item["canonical"] or f"{item['sessionId']}:{item['messageIndex']}")
        grouped.setdefault(key, []).append(item)

    buckets = {
        "strong_evidence": [],
        "related_context": [],
        "weak_matches": [],
        "artifacts": [],
    }
    for (bucket, canonical), items in grouped.items():
        support = len(items)
        unique_episodes = {item["canonical"] for item in items}
        projects = {item["project"] for item in items if item.get("project")}
        class_counts = {}
        penalties = set()
        topic_hits = set()
        intent_hits = set()
        generic_hits = set()
        matched_slots = set()
        for item in items:
            class_counts[item["class"]] = class_counts.get(item["class"], 0) + 1
            penalties.update(p for p in item.get("penalties", []) if p)
            topic_hits.update(item.get("topicHits", []))
            intent_hits.update(item.get("intentHits", []))
            generic_hits.update(item.get("genericHits", []))
            matched_slots.update(item.get("matchedSlots", []))

        score = max(item["score"] for item in items) + log2(support + 1) * 4
        if bucket == "weak_matches":
            score = min(score, 42)
        if bucket == "artifacts":
            score = min(score, 22)

        examples = []
        for item in sorted(items, key=lambda x: (x["score"], x["date"]), reverse=True)[:3]:
            examples.append({
                "sessionId": item["sessionId"],
                "title": item["title"],
                "project": item["project"],
                "source": item["source"],
                "date": item["date"],
                "messageIndex": item["messageIndex"],
                "classification": item["class"],
                "artifactReason": item["artifactReason"],
                "snippet": item["snippet"],
            })

        memory_eligible = bucket == "strong_evidence" and support >= 1 and "topic_anchor" in matched_slots
        clusters = buckets[bucket]
        clusters.append({
            "id": "",
            "tier": items[0]["tier"],
            "support": support,
            "episodeSupport": len(unique_episodes),
            "projectCount": len(projects),
            "score": round(score, 2),
            "classCounts": class_counts,
            "memoryEligible": memory_eligible,
            "whyRanked": {
                "matchedSlots": sorted(matched_slots),
                "topicHits": sorted(topic_hits),
                "intentHits": sorted(intent_hits),
                "genericHits": sorted(generic_hits),
                "penalties": sorted(penalties),
            },
            "examples": examples,
        })

    for bucket, clusters in buckets.items():
        clusters.sort(key=lambda c: (c["score"], c["support"]), reverse=True)
        for i, cluster in enumerate(clusters[:limit], 1):
            cluster["id"] = f"{bucket}-{i}"
        buckets[bucket] = clusters[:limit]
    return buckets


def _dedupe_lower(items: list) -> list:
    out = []
    seen = set()
    for item in items:
        value = (item or "").strip()
        if len(value) < 2:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _fts_or_term_rows(terms: list, limit: int) -> list:
    """FTS OR retrieval from explicit terms instead of raw user query."""
    from chatview import db as _db

    tokens = [_sanitize_fts_token(t) for t in _dedupe_lower(terms)]
    tokens = [t for t in tokens if t]
    if not tokens:
        return []
    match = " OR ".join(f'"{t}"' for t in tokens[:32])
    sql = """
        SELECT m.id, m.session_id, m.idx, m.role, m.text, m.ts,
               s.title, s.project_name, s.source
        FROM messages_fts fts
        JOIN messages m ON fts.rowid = m.id
        JOIN sessions s ON m.session_id = s.id
        WHERE messages_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """
    try:
        rows = _db.get_conn().execute(sql, [match, limit]).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def _metadata_anchor_session_ids(args, anchors: list) -> set:
    """Return sessions whose title/project carries a topic anchor."""
    from chatview import db as _db

    days_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
    max_days = days_map.get(getattr(args, "date", ""), 99999)
    sessions = _db.get_filtered_sessions(
        source=getattr(args, "source", "all"),
        project=getattr(args, "project", ""),
        max_days=max_days,
    )
    ids = set()
    for session in sessions:
        meta_text = f"{session.get('title', '')}\n{session.get('project_name', '')}"
        if _matched_terms(meta_text, anchors):
            ids.add(session["id"])
    return ids


def _generic_weak_rows(eligible: set, analysis: dict, limit: int) -> list:
    """Return a bounded weak-match pool via small FTS, leaving filtering to rerank."""
    generic = analysis.get("genericTerms", [])
    if "research" in [g.lower() for g in generic] or "研究" in generic:
        terms = [term for term in ["research", "研究"] if term in generic or term == "research"]
    else:
        terms = generic[:2]
    rows = []
    for row in _fts_or_term_rows(terms, limit=max(limit * 50, 500)):
        if row.get("session_id") in eligible:
            rows.append(row)
    return rows


def _repeat_candidate_rows(args, eligible: set, analysis: dict, limit: int) -> list:
    from chatview import db as _db

    rows_by_key = {}
    for row in _fts_or_term_rows(analysis.get("topicAnchors", []), limit=max(limit * 200, 2000)):
        if row.get("session_id") not in eligible:
            continue
        rows_by_key[(row.get("session_id"), row.get("idx"))] = row

    anchor_session_ids = _metadata_anchor_session_ids(args, analysis.get("topicAnchors", [])) & eligible
    if anchor_session_ids:
        rows = _db.query_in_chunks(_db.get_conn(), """
            SELECT m.session_id, m.idx, m.role, m.text, m.ts,
                   s.title, s.project_name, s.source
            FROM messages m JOIN sessions s ON m.session_id = s.id
            WHERE m.session_id IN ({placeholders}) AND m.role = 'user'
        """, list(anchor_session_ids))
        for row in rows:
            data = dict(row)
            rows_by_key[(data.get("session_id"), data.get("idx"))] = data

    for row in _generic_weak_rows(eligible, analysis, limit):
        rows_by_key[(row.get("session_id"), row.get("idx"))] = row

    return list(rows_by_key.values())


def find_repeats_data(query: str, args) -> dict:
    """Find repeated/related history evidence with tiered reranking."""
    started = datetime.now()
    from chatview import db as _db

    _db.init_db()
    eligible = _eligible_session_ids(args)
    analysis = _analyze_repeat_query(query)
    if not eligible:
        return {
            "query": query,
            "analysis": analysis,
            "stats": {"scannedUserMessages": 0, "candidates": 0, "clusters": 0, "elapsedMs": 0},
            "buckets": {"strong_evidence": [], "related_context": [], "weak_matches": [], "artifacts": []},
        }

    rows = _repeat_candidate_rows(args, eligible, analysis, limit=max(getattr(args, "limit", 20), 1))

    candidates = []
    for row in rows:
        item = _repeat_candidate_from_row(dict(row), analysis, query)
        if item:
            candidates.append(item)

    limit = max(getattr(args, "limit", 20), 1)
    buckets = _cluster_repeat_candidates(candidates, limit)
    cluster_count = sum(len(items) for items in buckets.values())
    elapsed = int((datetime.now() - started).total_seconds() * 1000)
    return {
        "query": query,
        "analysis": analysis,
        "stats": {
            "scannedUserMessages": len(rows),
            "candidates": len(candidates),
            "clusters": cluster_count,
            "elapsedMs": elapsed,
        },
        "buckets": buckets,
    }


def read_window_data(session_id: str, idx: int, radius: int = 2) -> dict:
    """Return DB-backed message context around a message index."""
    from chatview import db as _db

    _db.init_db()
    meta = _db.get_session_meta(session_id)
    if not meta:
        raise KeyError(f"Session not found: {session_id}")
    sid = meta["id"]
    radius = max(0, int(radius))
    start = idx - radius
    end = idx + radius
    messages = [
        {
            "idx": m.get("idx"),
            "role": m.get("role", ""),
            "ts": m.get("ts", ""),
            "text": m.get("text", ""),
        }
        for m in _db.get_message_window(sid, start, end)
    ]
    return {
        "sessionId": sid,
        "title": meta.get("title") or "Untitled",
        "project": meta.get("project_name") or "",
        "source": meta.get("source") or "",
        "date": meta.get("date") or "",
        "targetIndex": idx,
        "radius": radius,
        "messages": messages,
    }


def read_windows_data(requests: list) -> dict:
    """Return multiple read-window results in one call."""
    windows = []
    for i, request in enumerate(requests or []):
        session = request.get("session") or request.get("sessionId")
        if not session:
            raise ValueError(f"Batch item {i} missing session")
        if "idx" not in request:
            raise ValueError(f"Batch item {i} missing idx")
        radius = request.get("radius", 2)
        windows.append(read_window_data(session, int(request["idx"]), int(radius)))
    return {"windows": windows}


def _brief_message(msg: dict, title: str, max_chars: int = 220) -> dict:
    text = msg.get("text", "") or ""
    reason = _noise_reason(f"{title}\n{text}")
    return {
        "idx": msg.get("idx"),
        "role": msg.get("role", ""),
        "ts": msg.get("ts", ""),
        "artifactReason": reason,
        "snippet": text[:max_chars].replace("\n", " "),
    }


def session_brief_data(session_id: str, args) -> dict:
    """Return a compact session-level summary for retrieval triage."""
    from chatview import db as _db

    _db.init_db()
    meta = _db.get_session_meta(session_id)
    if not meta:
        raise KeyError(f"Session not found: {session_id}")

    sid = meta["id"]
    title = meta.get("title") or "Untitled"
    limit = max(getattr(args, "limit", 8), 1)
    messages = _db.get_session_messages(sid)
    counts = {"user": 0, "assistant": 0, "artifacts": 0, "total": len(messages)}
    clean_user = []
    clean_assistant = []
    artifact_examples = []

    for msg in messages:
        role = msg.get("role", "")
        if role in ("user", "assistant"):
            counts[role] += 1
        brief = _brief_message(msg, title)
        if brief["artifactReason"]:
            counts["artifacts"] += 1
            if len(artifact_examples) < 3:
                artifact_examples.append(brief)
            continue
        if role == "user":
            clean_user.append(brief)
        elif role == "assistant":
            clean_assistant.append(brief)

    return {
        "sessionId": sid,
        "title": title,
        "project": meta.get("project_name") or "",
        "source": meta.get("source") or "",
        "date": meta.get("date") or "",
        "counts": counts,
        "userMessages": clean_user[:limit],
        "assistantMessages": clean_assistant[:limit],
        "lastUserMessage": clean_user[-1] if clean_user else None,
        "artifactExamples": artifact_examples,
    }


def evidence_audit_data(args, kind: str = "all") -> dict:
    """Audit obvious orchestration noise in correction/decision candidates."""
    from chatview.commands.corrections import _data_corrections, _data_decisions

    datasets = {}
    if kind in ("all", "corrections"):
        datasets["corrections"] = _data_corrections(args)
    if kind in ("all", "decisions"):
        datasets["decisions"] = _data_decisions(args)

    summary = {}
    for name, records in datasets.items():
        reasons = {}
        examples = []
        for record in records:
            reason = _noise_reason(record.get("text", ""))
            if not reason:
                continue
            reasons[reason] = reasons.get(reason, 0) + 1
            if len(examples) < getattr(args, "limit", 20):
                examples.append({
                    "sessionId": record.get("sessionId", ""),
                    "title": record.get("title", ""),
                    "project": record.get("project", ""),
                    "date": record.get("date", ""),
                    "reason": reason,
                    "snippet": (record.get("text", "") or "")[:180].replace("\n", " "),
                })
        total = len(records)
        noisy = sum(reasons.values())
        summary[name] = {
            "total": total,
            "noisy": noisy,
            "clean": total - noisy,
            "noiseRate": round(noisy / max(total, 1), 4),
            "reasons": reasons,
            "examples": examples,
        }
    summary["generatedAt"] = datetime.now().isoformat()[:19]
    return summary


def cmd_search_plus(args):
    results = search_plus_data(args.query, args)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    print(f"Found {len(results)} hybrid matches for '{args.query}':\n")
    for row in results:
        reasons = ",".join(row.get("reasons", []))
        print(f"  [{row.get('score')}] {row.get('date', '')[:10]} {row.get('title', '')[:70]}")
        print(f"  {row.get('project', '')} · idx:{row.get('messageIndex')} · {reasons}")
        print(f"  > {row.get('snippet', '')[:220]}")
        print(f"  session: {row.get('sessionId', '')}")
        print()


def cmd_read_window(args):
    if getattr(args, "batch", ""):
        try:
            requests = json.loads(args.batch)
            if not isinstance(requests, list):
                raise ValueError("--batch must be a JSON list")
            data = read_windows_data(requests)
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            print(str(exc))
            return
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return
        for window in data["windows"]:
            print(f"# {window['title']}")
            print(f"# {window['project']} | target idx:{window['targetIndex']} radius:{window['radius']}\n")
            for msg in window["messages"]:
                text = (msg.get("text") or "").strip()
                print(f"--- {msg.get('role', '').upper()} idx:{msg.get('idx')} {msg.get('ts', '')[:16]} ---")
                print(text[:1200])
                print()
        return

    if not args.session or args.idx is None:
        print("read-window requires SESSION and --idx, or --batch JSON")
        return
    try:
        data = read_window_data(args.session, args.idx, args.radius)
    except KeyError as exc:
        print(str(exc))
        return
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(f"# {data['title']}")
    print(f"# {data['project']} | target idx:{data['targetIndex']} radius:{data['radius']}\n")
    for msg in data["messages"]:
        text = (msg.get("text") or "").strip()
        print(f"--- {msg.get('role', '').upper()} idx:{msg.get('idx')} {msg.get('ts', '')[:16]} ---")
        print(text[:1200])
        print()


def cmd_find_repeats(args):
    data = find_repeats_data(args.query, args)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    print(f"Repeat evidence for '{args.query}'")
    stats = data.get("stats", {})
    print(
        f"scanned={stats.get('scannedUserMessages', 0)} "
        f"candidates={stats.get('candidates', 0)} "
        f"clusters={stats.get('clusters', 0)} "
        f"elapsed={stats.get('elapsedMs', 0)}ms\n"
    )
    labels = [
        ("strong_evidence", "Strong Evidence"),
        ("related_context", "Related Context"),
        ("weak_matches", "Weak Matches"),
        ("artifacts", "Artifacts"),
    ]
    for key, label in labels:
        clusters = data.get("buckets", {}).get(key, [])
        print(f"## {label} ({len(clusters)})")
        for cluster in clusters:
            why = cluster.get("whyRanked", {})
            print(
                f"- {cluster.get('id')} tier={cluster.get('tier')} "
                f"support={cluster.get('support')} score={cluster.get('score')} "
                f"slots={','.join(why.get('matchedSlots', []))}"
            )
            if why.get("penalties"):
                print(f"  penalties={','.join(why.get('penalties', []))}")
            for example in cluster.get("examples", [])[:2]:
                print(
                    f"  {example.get('date', '')[:10]} {example.get('project', '')} "
                    f"idx:{example.get('messageIndex')} {example.get('classification')}"
                )
                print(f"  > {example.get('snippet', '')[:220]}")
                print(f"  session: {example.get('sessionId', '')}")
        print()


def cmd_session_brief(args):
    try:
        data = session_brief_data(args.session, args)
    except KeyError as exc:
        print(str(exc))
        return
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    counts = data.get("counts", {})
    print(f"# {data.get('title', '')}")
    print(f"{data.get('project', '')} | {data.get('source', '')} | {data.get('date', '')}")
    print(
        f"messages={counts.get('total', 0)} user={counts.get('user', 0)} "
        f"assistant={counts.get('assistant', 0)} artifacts={counts.get('artifacts', 0)}\n"
    )
    print("## User Messages")
    for msg in data.get("userMessages", []):
        print(f"- idx:{msg.get('idx')} {msg.get('ts', '')[:16]} {msg.get('snippet', '')}")
    if data.get("lastUserMessage"):
        last = data["lastUserMessage"]
        print(f"\nlast-user idx:{last.get('idx')} {last.get('snippet', '')}")
    if data.get("artifactExamples"):
        print("\n## Artifact Examples")
        for msg in data["artifactExamples"]:
            print(f"- idx:{msg.get('idx')} {msg.get('artifactReason')} {msg.get('snippet', '')[:160]}")


def cmd_evidence_audit(args):
    data = evidence_audit_data(args, getattr(args, "kind", "all"))
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    for name, item in data.items():
        if name == "generatedAt":
            continue
        print(f"{name}: total={item['total']} clean={item['clean']} noisy={item['noisy']} noiseRate={item['noiseRate']:.1%}")
        if item["reasons"]:
            print("  reasons: " + ", ".join(f"{k}={v}" for k, v in sorted(item["reasons"].items())))
