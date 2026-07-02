"""Correction, decision, error, and highlight analysis commands."""

import json
import os
import re
from collections import defaultdict

from chatview.commands.analysis import _get_filtered, _get_filtered_db, _get_messages_db
from chatview.utils.text import normalize_error as _normalize_error

_CORRECTION_EXTRACTOR_VERSION = "corrections-v3"


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------


def _correction_regexes():
    """Compile correction regexes shared by uncached and cached extraction."""
    patterns = [
        r"不是这样",
        r"不对[，。！\s]",
        r"不要这样",
        r"你忘了",
        r"应该是",
        r"错了[，。！\s]",
        r"你搞错",
        r"这样不行",
        r"别这样做",
        r"重新来",
        r"不是我说的",
        r"你理解错",
        r"不需要这个",
        r"我说的是",
        r"你漏了",
        r"搞反了",
        r"改回去",
        r"撤销",
        r"不行[，。！\s]",
        r"太[简精粗]",
        r"回退",
        r"换一种",
        r"重做",
        r"这不是",
        r"那不对",
        r"不应该",
        r"你没[看听懂理解]",
        r"别搞",
        r"我要的是",
        r"请不要",
        r"停[下一]",
        r"算了",
        r"之前说[的过]",
        r"刚才说",
        r"你搞反",
        r"弄反",
        r"多余的?[，。！\s]",
        r"没必要",
        r"不是这个意思",
        r"理解偏了",
        r"过度[设计复杂抽象]",
        r"太复杂",
        r"太臃肿",
        r"没有达到",
        r"怎么又",
        r"又错了",
        r"又来了",
        r"还是不行",
        r"还是有问题",
        r"没修好",
        r"没解决",
        r"问题还在",
        r"bug还在",
        r"你再看看",
        r"再想想",
        r"再试试",
        r"重新想",
        r"我没说",
        r"我没让你",
        r"谁让你",
        r"哪里说了",
        r"不合适",
        r"不合理",
        r"不是我想要",
        r"差太远",
        r"按我说的",
        r"照我说的",
        r"\b(?:that\'?s?|you\'?re?|this is|you.{0,5})wrong\b",
        r"\byou forgot\b",
        r"\bthat's not right\b",
        r"\bdon't do that\b",
        r"\bshouldn't have\b",
        r"\bnot what I (?:asked|meant|wanted)\b",
        r"\bI meant\b",
        r"\byou missed\b",
        r"\bplease (?:don\'t|stop)\b",
        r"\bactually,?\s+(?:I|it|the|we|that)\b",
        r"\bno,?\s+(?:I|it|the|we|that|not)\b",
        r"\brevert\b",
        r"\bundo\b",
        r"\broll\s*back\b",
        r"\btoo (?:complex|verbose|long|simple|short)\b",
        r"\bnot (?:quite|exactly|correct)\b",
        r"\bclose but\b",
        r"\bthat\'s (?:not|wrong|overkill|redundant)\b",
        r"\bovercomplicat",
        r"\bunnecessar",
        r"\bI (?:already|never|didn\'t) (?:said|told|asked|want)\b",
        r"\bstill (?:broken|not working|wrong|failing)\b",
        r"\bdoesn't work\b",
        r"\bnot working\b",
        r"\byou broke\b",
        r"\bthat broke\b",
        r"\btry again\b",
        r"\bstart over\b",
        r"\b(?:as |like )I said\b",
        r"\bI said\b",
        r"\bnope\b",
        r"\bnah\b",
    ]
    ai_correction_patterns = [
        r"抱歉",
        r"对不起",
        r"我理解错",
        r"我搞错",
        r"我的错",
        r"我的失误",
        r"是我的疏漏",
        r"说错了",
        r"我写错了",
        r"你是对的",
        r"感谢.{0,4}纠正",
        r"你说得对.{0,15}(?:我|确实|漏|错|没)",
        r"我搞混",
        r"我混了",
        r"我跑偏",
        r"我漏写",
        r"我没看到",
        r"我误读",
        r"我误判",
        r"判断错了",
        r"看错了",
        r"我遗漏",
        r"我忽略了",
        r"漏掉了",
        r"确实漏了",
        r"没考虑到",
        r"需要修正",
        r"本该",
        r"纠正一下",
        r"让我重新",
        r"推倒重来",
        r"换个思路",
        r"精简过头",
        r"想当然",
        r"错误假设",
        r"之前以为",
        r"已修正",
        r"已修复",
        r"撤回",
        r"改回",
        r"收到.{0,6}(?:偏|错|漏|之前|刚才)",
        r"刚才.{0,8}(?:偏差|偏了|错|漏|搞)",
        r"\bI apologize\b",
        r"\bmy mistake\b",
        r"\bI was wrong\b",
        r"\bI misunderstood\b",
        r"\bmy bad\b",
        r"\bI overlooked\b",
        r"\bI missed\b",
        r"\bsorry.{0,10}(?:mistake|wrong|missed|overlooked|confusion)\b",
        r"\blet me (?:fix|correct|redo) (?:that|this|my)\b",
        r"\bthank.{0,6}(?:correcting|catching)\b",
        r"\bI should have\b",
        r"\bI forgot\b",
        r"\bI didn't consider\b",
        r"\bupon (?:reflection|further review)\b",
        r"\bI realized\b",
        r"\bI incorrectly\b",
        r"\bI mistakenly\b",
        r"\bI stand corrected\b",
    ]
    ai_insight_patterns = [
        r"好(?:想法|主意|思路|建议|眼力)",
        r"好问题.{0,10}(?:让我|确实|我之前|我没|漏|错)",
        r"问得好",
        r"想法很好",
        r"完全正确",
        r"完全同意",
        r"确实如此",
        r"没想到",
        r"感谢.{0,4}指出",
        r"你提醒得对",
        r"你抓到",
        r"你指出",
        r"你发现",
        r"你点(?:到|出)",
        r"判断对了",
        r"有道理",
        r"切中要害",
        r"说到点子上",
        r"啊.{0,3}我理解",
        r"懂了.{0,6}(?:我|之前|不该|原来)",
        r"\bgood (?:catch|point|call|question|observation)\b",
        r"\bfair point\b",
        r"\bexcellent point\b",
        r"\bI see the (?:issue|problem)\b",
        r"\byou'?re right\b",
        r"\bI didn't think\b",
        r"\b(?:exactly|absolutely) right\b",
        r"\bthank.{0,6}pointing\b",
    ]
    return {
        "combined": re.compile("|".join(patterns), re.IGNORECASE),
        "ai_correction": re.compile("|".join(ai_correction_patterns), re.IGNORECASE),
        "ai_insight": re.compile("|".join(ai_insight_patterns), re.IGNORECASE),
        "ai_ack": re.compile(
            "|".join(ai_correction_patterns + ai_insight_patterns), re.IGNORECASE
        ),
    }


def _skip_correction_noise(text):
    if len(text) < 5 or len(text) > 3000:
        return True
    if text.strip().startswith(("#", "```", "<", "{")):
        return True
    if "analyze.py" in text or "CLI tool" in text:
        return True
    if "Base directory for this skill:" in text or "skill:" in text[:30]:
        return True
    return False


def _extract_corrections_from_session(meta, user_texts, assistant_snippets, regexes=None):
    """Extract correction events from one session using the same rules as the legacy scan."""
    regexes = regexes or _correction_regexes()
    corrections = []
    seen_keys = set()
    asst_by_idx = {a["idx"]: a["text"] for a in assistant_snippets}

    for ut in user_texts:
        text = ut.get("text", "")
        if _skip_correction_noise(text):
            continue
        matches = regexes["combined"].findall(text)
        if not matches:
            continue
        key = (meta["id"], ut["idx"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        ai_confirmed = False
        for offset in range(1, 4):
            asst_text = asst_by_idx.get(ut["idx"] + offset, "")
            if asst_text and regexes["ai_ack"].search(asst_text):
                ai_confirmed = True
                break
        corrections.append(
            {
                "sessionId": meta["id"],
                "message_idx": ut["idx"],
                "title": meta.get("title", "")[:60],
                "project": meta.get("projectName", ""),
                "date": meta.get("date", "")[:10],
                "text": text[:400],
                "signals": sorted(set(matches))[:5],
                "source": "user",
                "aiConfirmed": ai_confirmed,
                "filePath": meta.get("filePath", ""),
            }
        )

    user_corr_idxs = {k[1] for k in seen_keys if k[0] == meta["id"]}
    for asst in assistant_snippets:
        asst_text = asst.get("text", "")
        corr_matches = regexes["ai_correction"].findall(asst_text)
        insight_matches = regexes["ai_insight"].findall(asst_text)
        if not corr_matches and not insight_matches:
            continue
        ai_idx = asst["idx"]
        if any(abs(ai_idx - ui) <= 5 for ui in user_corr_idxs):
            continue
        key = (meta["id"], ai_idx)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        kind = "correction" if corr_matches else "insight"
        all_matches = corr_matches or insight_matches
        preceding_user = ""
        for ut in reversed(user_texts):
            if ut["idx"] < asst["idx"]:
                preceding_user = ut["text"][:200]
                break
        corrections.append(
            {
                "sessionId": meta["id"],
                "message_idx": ai_idx,
                "title": meta.get("title", "")[:60],
                "project": meta.get("projectName", ""),
                "date": meta.get("date", "")[:10],
                "text": preceding_user or "(AI-side only)",
                "aiText": asst_text[:200],
                "signals": sorted(set(all_matches))[:3],
                "source": "ai",
                "kind": kind,
                "aiConfirmed": True,
                "filePath": meta.get("filePath", ""),
            }
        )
    return corrections


def _data_corrections_uncached(args):
    """Compute correction data without the correction_events cache."""
    regexes = _correction_regexes()
    corrections = []

    db_sessions = _get_filtered_db(args)
    if db_sessions:
        from chatview import db as _db

        _db.init_db()
        sess_user, sess_asst = _session_messages_for_correction_extract(db_sessions)
        for session in db_sessions:
            meta = {
                "id": session["id"],
                "title": session.get("title", ""),
                "projectName": session.get("project_name", ""),
                "date": session.get("date", ""),
                "filePath": session.get("file_path", ""),
            }
            corrections.extend(
                _extract_corrections_from_session(
                    meta,
                    sess_user.get(session["id"], []),
                    sess_asst.get(session["id"], []),
                    regexes,
                )
            )
    else:
        for sid, meta in _get_filtered(args).items():
            session_meta = dict(meta)
            session_meta["id"] = sid
            corrections.extend(
                _extract_corrections_from_session(
                    session_meta,
                    session_meta.get("userTexts", []),
                    session_meta.get("assistantSnippets", []),
                    regexes,
                )
            )

    for item in corrections:
        item.pop("message_idx", None)
    corrections.sort(key=lambda c: c.get("date", ""), reverse=True)
    return corrections


def _session_messages_for_correction_extract(sessions):
    if not sessions:
        return {}, {}
    from chatview import db as _db

    sids = [s["id"] for s in sessions]
    rows = _db.query_in_chunks(
        _db.get_conn(),
        """
        SELECT m.session_id, m.idx, m.role, m.text
        FROM messages m
        WHERE m.session_id IN ({placeholders})
        ORDER BY m.session_id, m.idx
        """,
        sids,
    )
    sess_user = defaultdict(list)
    sess_asst = defaultdict(list)
    for r in rows:
        entry = {"idx": r["idx"], "text": r["text"], "ts": ""}
        if r["role"] == "user":
            sess_user[r["session_id"]].append(entry)
        elif r["role"] == "assistant":
            sess_asst[r["session_id"]].append(entry)
    return sess_user, sess_asst


def _ensure_correction_events_current(db_sessions):
    from chatview import db as _db

    stale_sessions = _db.stale_correction_sessions(
        db_sessions, _CORRECTION_EXTRACTOR_VERSION
    )
    if not stale_sessions:
        return 0

    sess_user, sess_asst = _session_messages_for_correction_extract(stale_sessions)
    regexes = _correction_regexes()
    _db.begin_bulk()
    try:
        for session in stale_sessions:
            meta = {
                "id": session["id"],
                "title": session.get("title", ""),
                "projectName": session.get("project_name", ""),
                "date": session.get("date", ""),
                "filePath": session.get("file_path", ""),
            }
            events = _extract_corrections_from_session(
                meta,
                sess_user.get(session["id"], []),
                sess_asst.get(session["id"], []),
                regexes,
            )
            _db.replace_correction_events(
                session, events, _CORRECTION_EXTRACTOR_VERSION
            )
    finally:
        _db.end_bulk()
    return len(stale_sessions)


def _data_corrections(args):
    """Compute correction data, using per-session cached events when DB is available."""
    db_sessions = _get_filtered_db(args)
    if not db_sessions:
        return _data_corrections_uncached(args)

    from chatview import db as _db

    _db.init_db()
    _ensure_correction_events_current(db_sessions)
    return _db.query_correction_events(db_sessions, _CORRECTION_EXTRACTOR_VERSION)


def cmd_corrections(args):
    """Find user correction / dissatisfaction patterns across sessions."""
    corrections = _data_corrections(args)

    # Stats
    user_src = [c for c in corrections if c.get("source") == "user"]
    ai_corr = [
        c
        for c in corrections
        if c.get("source") == "ai" and c.get("kind") == "correction"
    ]
    ai_insight = [
        c for c in corrections if c.get("source") == "ai" and c.get("kind") == "insight"
    ]
    confirmed = [c for c in user_src if c.get("aiConfirmed")]

    shown = corrections[: args.limit]
    if args.json:
        print(json.dumps(shown, ensure_ascii=False, indent=2))
    else:
        print(
            f"Found {len(corrections)} (user:{len(user_src)} ai-correction:{len(ai_corr)} ai-insight:{len(ai_insight)} confirmed:{len(confirmed)}):\n"
        )
        for c in shown:
            signals = ", ".join(c["signals"])
            text = c["text"][:180].replace("\n", " ")
            if c.get("source") == "user":
                src_tag = "\U0001f464"
                ack_tag = " \u2713AI" if c.get("aiConfirmed") else ""
            elif c.get("kind") == "insight":
                src_tag = "\U0001f4a1"
                ack_tag = ""
            else:
                src_tag = "\U0001f916"
                ack_tag = ""
            print(f"  {src_tag}{ack_tag} [{c['date']}] {c['project']} [{signals}]")
            print(f"    {text}")
            if c.get("source") == "ai" and c.get("aiText"):
                print(f"    \U0001f916 {c['aiText'][:120].replace(chr(10), ' ')}")
            print(f"    sid:{c['sessionId']}")


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


def _data_decisions(args):
    """Compute decision data and return as a list of dicts (sorted by date desc)."""
    # Tighter decision patterns — require decision-making context words
    decision_re = re.compile(
        r"(?:决定[了用采]|最终选|采用了?|放弃了?|"
        r"方案[AB12一二]|用.{1,20}还是|A还是B|"
        r"\bdecided\b|\blet\'s go with\b|\bshould we\b|"
        r"\bchoose\b|\btrade-?off\b|\bvs\.?\s)",
        re.IGNORECASE,
    )

    decisions = []

    # Try DB first; fall back to old method if DB is empty
    db_rows = _get_messages_db(args, role="user", limit=99999)
    if db_rows:
        # Build a session-id → session meta lookup from DB
        db_sessions = {s["id"]: s for s in _get_filtered_db(args)}
        for row in db_rows:
            text = row.get("text", "")
            sid = row.get("session_id", "")
            meta = db_sessions.get(sid, {})
            # Skip noise
            if len(text) < 10 or len(text) > 2000:
                continue
            if text.strip().startswith(("<", "{", "```", "#")):
                continue
            if (
                "analyze.py" in text
                or "CLI tool" in text
                or "\u5de5\u4f5c\u6d41" in text[:50]
            ):
                continue
            if text.strip().startswith(
                ("You are review", "You have a CLI", "Search the web")
            ):
                continue
            if text.strip().startswith(("toolu_", "a9bd", "Agent ")):
                continue
            if decision_re.search(text):
                decisions.append(
                    {
                        "sessionId": sid,
                        "title": meta.get("title", "")[:60],
                        "project": meta.get("project_name", ""),
                        "date": (meta.get("date") or "")[:10],
                        "text": text[:400],
                        "filePath": meta.get("file_path", ""),
                    }
                )
    else:
        filtered = _get_filtered(args)
        for sid, meta in filtered.items():
            for ut in meta.get("userTexts", []):
                text = ut.get("text", "")
                if len(text) < 10 or len(text) > 2000:
                    continue
                if text.strip().startswith(("<", "{", "```", "#")):
                    continue
                if (
                    "analyze.py" in text
                    or "CLI tool" in text
                    or "\u5de5\u4f5c\u6d41" in text[:50]
                ):
                    continue
                if text.strip().startswith(
                    ("You are review", "You have a CLI", "Search the web")
                ):
                    continue
                if text.strip().startswith(("toolu_", "a9bd", "Agent ")):
                    continue
                if decision_re.search(text):
                    decisions.append(
                        {
                            "sessionId": sid,
                            "title": meta.get("title", "")[:60],
                            "project": meta.get("projectName", ""),
                            "date": meta.get("date", "")[:10],
                            "text": text[:400],
                            "filePath": meta.get("filePath", ""),
                        }
                    )

    decisions.sort(key=lambda d: d.get("date", ""), reverse=True)
    return decisions


def cmd_decisions(args):
    """Extract potential decision points from conversations."""
    decisions = _data_decisions(args)
    shown = decisions[: args.limit]
    if args.json:
        print(json.dumps(shown, ensure_ascii=False, indent=2))
    else:
        print(f"Found {len(decisions)} potential decision points:\n")
        for d in shown:
            print(f"  [{d['date']}] {d['project']} — {d['title']}")
            print(f"  > {d['text'][:250]}")
            print(f"  session: {d['sessionId']}")
            print()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def _data_errors(args):
    """Compute error data and return as a list of dicts (sorted by count desc)."""
    filtered = _get_filtered(args)

    err_re = re.compile(
        r"((?:Traceback.*?:\s*)?"
        r"(?:(?:Error|Exception|TypeError|ValueError|KeyError|AttributeError|"
        r"ImportError|ModuleNotFoundError|NameError|IndexError|RuntimeError|"
        r"SyntaxError|FileNotFoundError|PermissionError|OSError|IOError|"
        r"ConnectionError|TimeoutError)"
        r"[:\s].{0,150}))",
        re.IGNORECASE,
    )

    groups = {}  # normalized → {count, sessions, projects, sample}

    for sid, meta in filtered.items():
        fp = meta.get("filePath", "")
        source = meta.get("source", "claude")
        project = meta.get("projectName", "")
        if not fp or not os.path.exists(fp):
            continue

        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if (
                        source == "claude"
                        and obj.get("type") == "user"
                        and obj.get("toolUseResult")
                    ):
                        content = obj.get("message", {}).get("content", [])
                        if isinstance(content, list):
                            for block in content:
                                if (
                                    isinstance(block, dict)
                                    and block.get("type") == "tool_result"
                                ):
                                    rt = block.get("content", "")
                                    if isinstance(rt, list):
                                        rt = json.dumps(rt)
                                    if isinstance(rt, str):
                                        for m in err_re.finditer(rt[:5000]):
                                            raw = m.group(1)
                                            # Skip source code patterns (not real errors)
                                            if (
                                                "except Exception" in raw
                                                or "Exception as e" in raw
                                            ):
                                                continue
                                            if (
                                                "raise " in raw[:20]
                                                or "class " in raw[:20]
                                            ):
                                                continue
                                            key = _normalize_error(raw)
                                            if len(key) < 10:
                                                continue
                                            # Skip overly generic or source-code patterns
                                            if key.strip().rstrip(":") in (
                                                "Exception",
                                                "Error",
                                                "error",
                                            ):
                                                continue
                                            if (
                                                "${" in raw
                                                or "`);" in raw
                                                or "throw new" in raw
                                            ):
                                                continue
                                            if (
                                                "# noqa" in raw
                                                or '{e}")' in raw
                                                or 'f"' in raw[:10]
                                            ):
                                                continue
                                            if key not in groups:
                                                groups[key] = {
                                                    "count": 0,
                                                    "sessions": set(),
                                                    "projects": set(),
                                                    "sample": m.group(1)[:200],
                                                }
                                            groups[key]["count"] += 1
                                            groups[key]["sessions"].add(sid)
                                            groups[key]["projects"].add(project)
        except Exception:
            continue

    sorted_errors = sorted(groups.items(), key=lambda x: -x[1]["count"])
    return [
        {
            "pattern": k,
            "count": v["count"],
            "sessions": len(v["sessions"]),
            "projects": sorted(v["projects"]),
            "sample": v["sample"],
        }
        for k, v in sorted_errors
    ]


def cmd_errors(args):
    """Extract error patterns from tool results across sessions."""
    errors = _data_errors(args)
    shown = errors[: args.limit]
    if args.json:
        print(json.dumps(shown, ensure_ascii=False, indent=2))
    else:
        print(f"Found {len(errors)} error patterns:\n")
        for data in shown:
            projs = ", ".join(data["projects"])
            print(f"  [{data['count']}x · {data['sessions']} sessions] {projs}")
            print(f"  {data['sample']}")
            print()


# ---------------------------------------------------------------------------
# Highlights
# ---------------------------------------------------------------------------


def _data_highlights(args):
    """Compute highlights data and return as a list of dicts (sorted by date desc)."""
    # Reuse correction + decision regexes for signal counting
    correction_re = re.compile(
        r"不是这样|不对[，。！\s]|不要这样|你忘了|应该是|错了[，。！\s]|你搞错|这样不行|别这样做|重新来|"
        r"不是我说的|你理解错|不需要这个|我说的是|你漏了|搞反了|改回去|撤销|"
        r"不行[，。！\s]|太[简精粗]|回退|换一种|重做|这不是|那不对|不应该|你没[看听懂理解]|别搞|"
        r"我要的是|请不要|停[下一]|算了|"
        r"\bwrong\b|\byou forgot\b|\bthat\'s not right\b|\bdon\'t do that\b|\bshouldn\'t have\b|"
        r"\bnot what I (?:asked|meant|wanted)\b|\bI meant\b|\byou missed\b|\bplease (?:don\'t|stop)\b|"
        r"\bactually,?\s+(?:I|it|the|we|that)\b|\bno,?\s+(?:I|it|the|we|that|not)\b|"
        r"\brevert\b|\bundo\b|\broll\s*back\b",
        re.IGNORECASE,
    )
    decision_re = re.compile(
        r"决定|选择|方案|approach|decided|choose|option|trade-?off|vs\.?|versus|"
        r"用.+还是|should we|let\'s go with|我们用|最终选|采用|放弃",
        re.IGNORECASE,
    )

    results = []

    # Try DB first; fall back to old method if DB is empty
    db_sessions = _get_filtered_db(args)
    if db_sessions:
        from chatview import db as _db

        _db.init_db()
        # Load user messages in bulk for all sessions
        sids = [s["id"] for s in db_sessions]
        conn = _db.get_conn()
        # 分批查询规避 SQLite 宿主参数上限；同一 session 落在同一批，分组顺序不受影响。
        msg_rows = _db.query_in_chunks(
            conn,
            """
            SELECT session_id, text FROM messages
            WHERE session_id IN ({placeholders}) AND role='user'
            ORDER BY session_id, idx
        """,
            sids,
        )
        # Group messages by session
        sess_texts = defaultdict(list)
        for r in msg_rows:
            sess_texts[r["session_id"]].append(r["text"])

        items = sorted(db_sessions, key=lambda s: s.get("date", ""), reverse=True)

        for s in items:
            sid = s["id"]
            title = (s.get("title") or "Untitled")[:50]
            project = s.get("project_name", "")
            source = (s.get("source", "claude") or "claude")[:3]
            date = (s.get("date") or "")[:10]
            msg_count = s.get("user_message_count") or 0

            corrections = 0
            decisions = 0
            topics = []
            for text in sess_texts.get(sid, []):
                if len(text) < 3 or text.strip().startswith(("<", "{", "```")):
                    continue
                if correction_re.search(text):
                    corrections += 1
                if decision_re.search(text):
                    decisions += 1
                if not topics and len(text) > 10 and not text.startswith(("#", "```")):
                    topics.append(text[:80].replace("\n", " "))

            topic = topics[0] if topics else title
            results.append(
                {
                    "id": sid,
                    "date": date,
                    "source": source,
                    "project": project,
                    "title": title,
                    "topic": topic,
                    "messages": msg_count,
                    "corrections": corrections,
                    "decisions": decisions,
                }
            )
    else:
        filtered = _get_filtered(args)
        items = sorted(filtered.values(), key=lambda m: m.get("date", ""), reverse=True)

        for m in items:
            sid = m.get("id", "")
            title = m.get("title", "Untitled")[:50]
            project = m.get("projectName", "")
            source = m.get("source", "claude")[:3]
            date = m.get("date", "")[:10]
            msg_count = m.get("userMessageCount", 0)

            corrections = 0
            decisions = 0
            topics = []
            for ut in m.get("userTexts", []):
                text = ut.get("text", "")
                if len(text) < 3 or text.strip().startswith(("<", "{", "```")):
                    continue
                if correction_re.search(text):
                    corrections += 1
                if decision_re.search(text):
                    decisions += 1
                if not topics and len(text) > 10 and not text.startswith(("#", "```")):
                    topics.append(text[:80].replace("\n", " "))

            topic = topics[0] if topics else title
            results.append(
                {
                    "id": sid,
                    "date": date,
                    "source": source,
                    "project": project,
                    "title": title,
                    "topic": topic,
                    "messages": msg_count,
                    "corrections": corrections,
                    "decisions": decisions,
                }
            )

    return results


def cmd_highlights(args):
    """Per-session one-line highlights: topic, key signals, message count."""
    results = _data_highlights(args)
    shown = results[: args.limit]

    if args.json:
        print(json.dumps(shown, ensure_ascii=False, indent=2))
    else:
        print(f"Highlights for {len(shown)} sessions:\n")
        for r in shown:
            signals = []
            if r["corrections"]:
                signals.append(f"corr:{r['corrections']}")
            if r["decisions"]:
                signals.append(f"dec:{r['decisions']}")
            sig_str = " ".join(signals) if signals else "-"
            print(
                f"  [{r['source']}] {r['date']} {r['messages']:3d}msg {sig_str:12s} {r['project'][:20]:20s} | {r['topic']}"
            )
