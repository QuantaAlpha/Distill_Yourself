"""CLI entry point for analyze commands.

Usage:
  python3 -m chatview.cli <command> [options]
  python3 analyze.py <command> [options]  (via thin wrapper)
"""

import argparse
import io
import sys

from chatview.commands.analysis import (
    cmd_sessions, cmd_read, cmd_search, cmd_queries, cmd_stats, cmd_files,
    cmd_refresh, cmd_install_skill,
)
from chatview.commands.corrections import (
    cmd_corrections, cmd_decisions, cmd_errors, cmd_highlights,
)
from chatview.commands.evolve import (
    cmd_evolve_rules, cmd_evolve_signals, cmd_evolve_patterns,
    cmd_evolve_write, cmd_evolve_sync, cmd_aggregates, cmd_profile_digest,
)
from chatview.commands.twin import (
    cmd_twin_stats, cmd_twin_events, cmd_twin_cards, cmd_twin_traits,
    cmd_twin_write, cmd_twin_compile, cmd_twin_candidates,
    cmd_twin_get, cmd_twin_search, cmd_twin_add, cmd_twin_edit,
    cmd_twin_link, cmd_twin_batch,
)


def main():
    parser = argparse.ArgumentParser(
        description="CLI tools for analyzing Claude Code / Codex conversation history.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 analyze.py sessions --date 7d --source claude
  python3 analyze.py read <session-id>
  python3 analyze.py search "redis cache" --date 30d
  python3 analyze.py corrections --date 7d --project myproject
  python3 analyze.py errors --date 30d
  python3 analyze.py decisions --date 7d
  python3 analyze.py stats
  python3 analyze.py files --date 7d
  python3 analyze.py highlights --date 7d
""")
    # Shared filter args (added to every subcommand)
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--date", default="7d",
                        help="Time filter: 1d, 7d, 30d, 90d, all (default: 7d)")
    shared.add_argument("--source", default="all",
                        help="Source filter: claude, codex, all (default: all)")
    shared.add_argument("--project", default="",
                        help="Filter by project name (substring match)")
    shared.add_argument("--limit", type=int, default=50,
                        help="Max results (default: 50)")
    shared.add_argument("--json", action="store_true",
                        help="Output as JSON")
    shared.add_argument("--save", default="",
                        help="Save full output to file (prints summary + path instead)")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    sub.add_parser("sessions", parents=[shared], help="List sessions matching filters")

    p_read = sub.add_parser("read", parents=[shared], help="Read a session (human-readable)")
    p_read.add_argument("session", help="Session ID or partial match")
    p_read.add_argument("-v", "--verbose", action="store_true",
                        help="Include tool inputs and results")
    p_read.add_argument("-s", "--summary", action="store_true",
                        help="Summary mode: user messages + assistant conclusions only (no tools)")

    p_search = sub.add_parser("search", parents=[shared], help="Search user messages")
    p_search.add_argument("query", help="Search query")

    p_queries = sub.add_parser("queries", parents=[shared], help="Extract user queries only (no AI responses)")
    p_queries.add_argument("--session", default="", help="Session ID to extract from (omit for cross-session)")
    p_queries.add_argument("--keyword", "-k", default="", help="Filter queries containing keyword")

    sub.add_parser("corrections", parents=[shared], help="Find user correction patterns")
    sub.add_parser("decisions", parents=[shared], help="Find decision points in conversations")
    sub.add_parser("errors", parents=[shared], help="Extract error patterns from tool results")
    sub.add_parser("stats", parents=[shared], help="Show aggregate statistics")
    sub.add_parser("files", parents=[shared], help="Show most-edited files")
    sub.add_parser("highlights", parents=[shared], help="Per-session one-line highlights with signal counts")
    sub.add_parser("evolve-rules", parents=[shared], help="Generate rules JSON for Evolve page")
    sub.add_parser("evolve-signals", parents=[shared], help="Generate signals JSON for Evolve page")
    sub.add_parser("evolve-patterns", parents=[shared], help="Generate patterns JSON for Evolve page")

    p_ew = sub.add_parser("evolve-write", help="Write/merge/delete Evolve tab data (validated, writes to SQLite)")
    p_ew.add_argument("--tab", required=True, choices=["profile", "memory", "rules", "signals", "patterns"],
                       help="Target tab")
    p_ew.add_argument("--mode", default="replace", choices=["replace", "merge", "delete"],
                       help="Write mode: replace (full), merge (add/update), delete (remove by id)")
    p_ew.add_argument("--ids", default="", help="Comma-separated ids/names for delete mode")
    p_ew.add_argument("--source", default="all", help="Scope: data source (all/claude/codex)")
    p_ew.add_argument("--date", default="7d", help="Scope: date range (7d/30d/90d/all)")
    p_ew.add_argument("--project", default="", help="Scope: project filter")
    p_ew.add_argument("--engine", default="auto", help="Scope: AI engine used (auto/codex/claude)")

    p_es = sub.add_parser("evolve-sync",
                          help="Sync staged Evolve data (SQLite) to ~/.claude config files")
    p_es.add_argument("--tab", required=True, choices=["memory", "profile"],
                       help="What to sync: memory -> memory/*.md, profile -> CLAUDE.md")
    p_es.add_argument("--execute", action="store_true",
                       help="Actually write files (default: preview only, no writes)")
    p_es.add_argument("--source", default="all", help="Scope: data source (all/claude/codex)")
    p_es.add_argument("--date", default="7d", help="Scope: date range (7d/30d/90d/all)")
    p_es.add_argument("--project", default="", help="Scope: project filter")
    p_es.add_argument("--engine", default="auto", help="Scope: AI engine used (auto/codex/claude)")

    p_refresh = sub.add_parser("refresh",
                               help="Force re-index: scan JSONL, rebuild SQLite + aggregates")
    p_refresh.add_argument("--force", action="store_true",
                            help="Re-parse all files even if unchanged")
    p_refresh.add_argument("--json", action="store_true", help="Output build summary as JSON")

    p_is = sub.add_parser("install-skill",
                          help="Copy the bundled distill-yourself skill into ~/.claude/skills (and Codex)")
    p_is.add_argument("--force", action="store_true", help="Overwrite if already installed")

    p_agg = sub.add_parser("aggregates", help="Print pre-computed aggregates from SQLite DB as JSON")
    p_agg.add_argument("--json", action="store_true", help="Output as JSON (always JSON regardless)")
    sub.add_parser("profile-digest", parents=[shared], help="Pre-computed profile digest for sub-agents (JSON)")

    sub.add_parser("twin-stats", parents=[shared], help="Show Cognitive Handbook statistics")

    p_te = sub.add_parser("twin-events", parents=[shared], help="List evidence events")
    p_te.add_argument("--domain", default="", help="Filter by domain")
    p_te.add_argument("--signal", default="", help="Filter by signal_type")
    p_te.add_argument("--session", default="", help="Filter by session id (substring)")
    p_te.add_argument("--run-id", default="", help="Filter by Twin analysis run id")

    p_tc = sub.add_parser("twin-cards", parents=[shared], help="List judgment cards")
    p_tc.add_argument("--status", default="", help="Filter by status (hypothesis/emerging/confirmed)")
    p_tc.add_argument("--tag", default="", help="Filter by tag (substring match)")
    p_tc.add_argument("--min-confidence", type=float, default=None, dest="min_confidence",
                      help="Minimum confidence threshold")
    p_tc.add_argument("--run-id", default="", help="Filter by Twin analysis run id")

    p_tt = sub.add_parser("twin-traits", parents=[shared], help="List cognitive traits")
    p_tt.add_argument("--status", default="", help="Filter by status")
    p_tt.add_argument("--category", default="", help="Filter by category")
    p_tt.add_argument("--run-id", default="", help="Filter by Twin analysis run id")

    sub.add_parser("twin-write", help="Write/update/delete cognitive handbook entries from JSON stdin")
    p_tcomp = sub.add_parser("twin-compile", help="Compile Runtime Pack from cards + traits")
    p_tcomp.add_argument("--run-id", default="", help="Compile only artifacts from this Twin analysis run")
    p_tcomp.add_argument("--lang", default="zh", help="Output language: zh or en (default: zh)")
    sub.add_parser("twin-candidates", help="Validate candidate Twin operations without writing")

    # CRUD tools
    p_tg = sub.add_parser("twin-get", help="Get a single event/card/trait by ID")
    p_tg.add_argument("resource", choices=["events", "cards", "traits"])
    p_tg.add_argument("id", help="Item ID (e.g. ev_xxx, jc_xxx, ct_xxx)")

    p_ts = sub.add_parser("twin-search", parents=[shared],
                          help="Search events/cards/traits by keyword")
    p_ts.add_argument("resource", choices=["events", "cards", "traits"])
    p_ts.add_argument("--q", required=True, help="Search keyword")

    p_ta = sub.add_parser("twin-add", help="Add a new event/card/trait (JSON from stdin)")
    p_ta.add_argument("resource", choices=["events", "cards", "traits"])

    p_ted = sub.add_parser("twin-edit", help="Edit an existing event/card/trait (JSON from stdin)")
    p_ted.add_argument("resource", choices=["events", "cards", "traits"])
    p_ted.add_argument("id", help="Item ID to edit")

    p_tl = sub.add_parser("twin-link", help="Link event->card or card->trait")
    p_tl.add_argument("from_id", help="Source ID (ev_/p_ for event, jc_ for card)")
    p_tl.add_argument("to_id", help="Target ID (jc_ for card, ct_ for trait)")
    p_tl.add_argument("--run-id", default="", help="Require both endpoints to match this run id")

    sub.add_parser("twin-batch", help="Execute multiple operations (JSON from stdin)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmds = {
        "sessions": cmd_sessions, "read": cmd_read, "search": cmd_search,
        "queries": cmd_queries, "corrections": cmd_corrections,
        "decisions": cmd_decisions, "errors": cmd_errors,
        "stats": cmd_stats, "files": cmd_files, "highlights": cmd_highlights,
        "evolve-rules": cmd_evolve_rules, "evolve-signals": cmd_evolve_signals,
        "evolve-patterns": cmd_evolve_patterns, "evolve-write": cmd_evolve_write,
        "evolve-sync": cmd_evolve_sync,
        "refresh": cmd_refresh, "install-skill": cmd_install_skill,
        "aggregates": cmd_aggregates,
        "profile-digest": cmd_profile_digest,
        "twin-stats": cmd_twin_stats,
        "twin-events": cmd_twin_events,
        "twin-cards": cmd_twin_cards,
        "twin-traits": cmd_twin_traits,
        "twin-write": cmd_twin_write,
        "twin-compile": cmd_twin_compile,
        "twin-candidates": cmd_twin_candidates,
        "twin-get": cmd_twin_get,
        "twin-search": cmd_twin_search,
        "twin-add": cmd_twin_add,
        "twin-edit": cmd_twin_edit,
        "twin-link": cmd_twin_link,
        "twin-batch": cmd_twin_batch,
    }

    save_path = getattr(args, "save", "")
    if save_path:
        # Capture stdout, save full output to file, print summary
        old_stdout = sys.stdout
        sys.stdout = buf = io.StringIO()
        # Remove limit when saving -- get all data
        if hasattr(args, "limit"):
            args.limit = 99999
        cmds[args.command](args)
        full_output = buf.getvalue()
        sys.stdout = old_stdout
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(full_output)
        line_count = full_output.count("\n")
        char_count = len(full_output)
        print(f"Saved {line_count} lines ({char_count} chars) to {save_path}")
        print(f"Use: cat {save_path}  or  sed -n '1,100p' {save_path}  to read in segments")
    else:
        cmds[args.command](args)


if __name__ == "__main__":
    main()
