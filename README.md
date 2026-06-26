<div align="center">

# ⬡ ConvoLab

**AI Session Intelligence Platform**

*Your AI conversations are a goldmine of patterns, decisions, and insights — sitting in JSONL files that nobody reads.*
*ConvoLab mines that data. Browse. Search. Analyze. **Evolve.***

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Dependencies](https://img.shields.io/badge/Dependencies-Zero-00C853?style=flat-square)](.)
[![Privacy](https://img.shields.io/badge/Privacy-Local_First-7C3AED?style=flat-square&logo=shield&logoColor=white)](.)
[![SQLite](https://img.shields.io/badge/Storage-SQLite_FTS5-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org)
[![D3.js](https://img.shields.io/badge/Viz-D3.js-F9A03C?style=flat-square&logo=d3dotjs&logoColor=white)](https://d3js.org)

</div>

---

Every day, **51% of developers worldwide** talk to AI coding assistants — generating thousands of rich exchanges full of architecture decisions, debugging insights, and preference signals. Then the terminal closes and all of it sinks into JSONL log files nobody ever reopens. A half-dozen open-source tools let you *browse* that history, but they stop there: no analysis, no pattern extraction, no feedback loop.

ConvoLab goes further. It indexes your Claude Code and Codex sessions into a searchable, analyzable knowledge base, then mines five dimensions of intelligence with its **Evolve AI** engine — developer profile, memory graph, correction rules, behavioral signals, and recurring problem patterns — all rendered as interactive D3.js charts. The real breakthrough is the closed loop: Evolve writes its findings back into your `CLAUDE.md` and memory files, which your AI picks up on its next launch — fewer corrections, less context to rebuild, a partner that fits you a little better every week. At a time when developer trust in AI output has slipped from 40% to 29% and teams burn 2–3 engineer-days per sprint just rebuilding context, ConvoLab turns throwaway conversations into a compounding asset. Zero dependencies, fully local, your data never leaves your machine.

**[📖 Read the user guide →](docs/USER_GUIDE.md)**

<br>

## ✦ Quick Start

```bash
git clone https://github.com/QuantaAlpha/ConvoLab.git
cd ConvoLab
python3 server.py
```

Open **http://localhost:5757** — that's it. No `pip install`, no `npm`, no Docker.

> **Prerequisites:** Python 3.8+ and session data from [Claude Code](https://claude.ai/code) (`~/.claude/projects/`) or [Codex](https://openai.com/codex) (`~/.codex/sessions/`).

<br>

## ✦ Features

ConvoLab works in three layers — it **collects** every conversation so you can always find it again, **surfaces** the patterns hiding across hundreds of them, and helps your AI **evolve**: it distills what it learns about you and writes those lessons straight back into your AI's config, so the next session starts smarter.

### 🗂 Sessions — Browse & Search

ChatGPT-style interface for your entire Claude Code and Codex history.

- **Message rendering** — user prompts, assistant replies, tool calls (Bash, Read, Edit…), and thinking blocks each get distinct visual treatment
- **Fuzzy search** — search across session titles and user messages with keyword highlighting
- **Smart filters** — filter by source (Claude/Codex), date range, and project; active filters display as inline chips
- **Session outline** — jump between user messages within a long conversation
- **Keyboard-driven** — `j/k` to navigate, `/` to search, `Enter` to open, `Esc` to go back

<p align="center"><img src="docs/images/user-guide/02-session.jpg" alt="Session detail view" width="820"></p>
<p align="center"><sub><i>Verbose tool calls stay collapsed by default, so you follow the conversation's main thread instead of scrolling through noise. The right rail holds an outline, an auto-summary, and a chat box for asking about <b>this</b> session.</i></sub></p>

### 📊 Insights — Understand Patterns

Five analytical tabs aggregating patterns across your entire session history.

| Tab | What it shows |
|-----|---------------|
| **Tool Heatmap** | Usage frequency of each tool type with visual intensity scaling |
| **File Hotspots** | Most frequently referenced files ranked by touch count |
| **Error Patterns** | Recurring failures and error messages with source context |
| **Project Health** | Per-project activity scores, session counts, and trend arrows |
| **Snippets** | Extracted code blocks with language tags and applied/suggested status |

<p align="center"><img src="docs/images/user-guide/05-heatmap.jpg" alt="Tool usage heatmap" width="820"></p>
<p align="center"><sub><i>The tool heatmap compresses hundreds of sessions into a day-by-day fingerprint of how you work — at a glance you can tell whether you've lately been reading code or rewriting it. Everything here is computed locally; no AI engine required.</i></sub></p>

### 🧬 Evolve AI — Self-Evolution Engine

The core differentiator. Five D3.js-powered interactive visualizations that mine your conversation history for actionable intelligence — then **sync it back** to make your AI smarter.

| Tab | What it answers | Visualization |
|-----|----------------|---------------|
| **Profile** | *Who are you as a developer?* | Profile card + radar chart over capability dimensions the engine derives itself (so they vary per developer) |
| **Memory** | *What do you care about?* | Force-directed graph of preferences, habits, and their relationships |
| **Rules** | *What have you corrected?* | Priority-ranked rule cards (P0/P1/P2) with user-quote evidence |
| **Signals** | *Are corrections trending up or down?* | Stacked timeline of style/scope/accuracy/workflow corrections |
| **Patterns** | *What keeps going wrong?* | Bubble chart of recurring issues with improvement suggestions |

**The closed loop:** Evolve builds your Profile and Memory → syncs Profile to `~/.claude/CLAUDE.md` and Memory nodes to `~/.claude/memory/` → Claude Code reads these on next startup → generates better output → fewer corrections needed. Because sync edits your global config, it always shows a preview first — what it will create, update, or skip — and writes nothing until you confirm. Rules, Signals, and Patterns are generated for review and reference (never synced).

<p align="center"><img src="docs/images/user-guide/06-profile-radar.png" alt="Profile capability radar" width="820"></p>
<p align="center"><sub><i><b>Profile</b> never asks you to fill in a form — it reads your actual behavior from the transcripts and scores you on dimensions it derives on its own, so everyone's radar comes out a little different. It's often the first time you see yourself the way your AI does.</i></sub></p>

<p align="center"><img src="docs/images/user-guide/04-evolve-memory.jpg" alt="Memory preference graph and cards" width="820"></p>
<p align="center"><sub><i><b>Memory</b> distills your preferences into actionable "when X, do Y / avoid Z" cards and links them into a graph. Every card traces back to the exact conversation that justifies it — nothing is invented.</i></sub></p>

### 💬 AI Chat

Ask natural-language questions about your sessions — powered by locally installed Codex CLI or Claude Code.

- **Session-scoped** — "What was the root cause of this bug?" (analyzes one session)
- **Global-scoped** — "Which project had the most errors this week?" (analyzes all sessions)
- **Preset prompts** — requirement extraction, decisions, bugs, code review, TODOs, rules
- **Persistent history** — conversations saved to localStorage

<br>

## ✦ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5757` | Server port |

```bash
# Custom port
PORT=3000 python3 server.py
```

> **AI features** (AI Chat, Evolve AI) require a locally installed AI CLI tool — either [Codex CLI](https://github.com/openai/codex) (`npm i -g @openai/codex`) or [Claude Code](https://claude.ai/code) (`npm i -g @anthropic-ai/claude-code`). No API keys needed — ConvoLab invokes the CLI directly.

<br>

## ✦ Architecture

```
ConvoLab/
├── server.py            # HTTP server (~3.5K lines) — REST API, JSONL parser, AI proxy, SSE streaming
├── db.py                # SQLite storage — sessions, messages, FTS5 search, pre-aggregates
├── analyze.py           # CLI analytics tool (~2.8K lines) — standalone analysis + Evolve generators
├── start.sh             # Quick launcher
├── docs/
│   ├── USER_GUIDE.md    # Full walkthrough with screenshots
│   └── images/          # Screenshots used in the docs
└── static/
    ├── index.html       # SPA shell — sidebar nav + multi-view layout
    ├── app.js           # Core application logic (vanilla JS)
    ├── evolve.js        # D3.js interactive visualizations
    ├── twin.js          # Digital Twin tab — cognitive model UI
    └── style.css        # Light premium theme
```

### Design Philosophy

| Principle | Implementation |
|-----------|---------------|
| **Zero dependencies** | Python stdlib server, vanilla JS frontend. Only D3.js loaded via CDN. No `pip install`, no `npm`. |
| **Privacy first** | All data read from local `~/.claude/` and `~/.codex/`. No telemetry, no cloud, no external calls. |
| **Incremental everything** | File MTimes tracked; only changed JSONL files re-parsed. ThreadPoolExecutor for parallel parsing. |
| **SQLite + FTS5** | Sessions & messages stored in `.cache/sessions.db` with WAL mode. FTS5 index powers CLI search; web uses fuzzy matching. |
| **SSE streaming** | Evolve AI analysis streams real-time progress (tool execution, thinking, results) via Server-Sent Events. |

### Data Sources

| Source | Location | Format |
|--------|----------|--------|
| Claude Code | `~/.claude/projects/` | JSONL (sessions, messages, tool calls) |
| Codex CLI | `~/.codex/sessions/` + `~/.codex/archived_sessions/` | JSONL (Codex-native format) |

### REST API

<details>
<summary><b>Core REST endpoints</b> — click to expand</summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/sessions` | List all sessions (id, title, date, source, project) |
| `GET` | `/api/session/:id` | Full message history for a session |
| `GET` | `/api/session-summary` | Session summary (condensed view) |
| `GET` | `/api/projects` | List all detected projects |
| `GET` | `/api/search?q=…` | Fuzzy search across session titles and messages |
| `GET` | `/api/timeline` | Daily session counts |
| `GET` | `/api/analytics` | Aggregated tool usage statistics + file hotspots |
| `GET` | `/api/project-health` | Per-project health scores and trends |
| `GET` | `/api/snippets` | Extracted code snippets with metadata |
| `GET` | `/api/file-evolution` | Cross-session edit timeline for a file |
| `GET` | `/api/evolve/:tab` | Evolve AI data (profile/memory/rules/signals/patterns) — supports SSE streaming |
| `GET` | `/api/stats` | Global statistics summary |
| `GET` | `/api/refresh` | Rebuild session index from disk |
| `POST` | `/api/chat` | AI chat (requires locally installed Codex CLI or Claude Code) |
| `POST` | `/api/chat/stream` | SSE streaming AI chat |
| `POST` | `/api/evolve/sync` | Sync Evolve results to Claude Code (`CLAUDE.md` + memory files) |

</details>

<br>

## ✦ CLI Analytics

`analyze.py` is a standalone CLI tool — usable independently of the web server, and designed to be called by AI agents (Claude Code, Codex) for automated analysis.

```bash
# List sessions with filters
python3 analyze.py sessions --source claude --date 7d --limit 20

# Full-text search across all sessions
python3 analyze.py search "authentication bug" --project my-app

# Extract user queries from a specific session
python3 analyze.py queries --session abc123

# Detect user correction patterns (→ CLAUDE.md rules)
python3 analyze.py corrections --date 30d

# Generate Evolve rules/signals/patterns
python3 analyze.py evolve-rules
python3 analyze.py evolve-signals
python3 analyze.py evolve-patterns

# Pre-computed aggregates (used by Evolve AI)
python3 analyze.py aggregates
```

Most analysis commands support `--json` for machine-readable output and filters: `--source`, `--date`, `--project`, `--limit`. Additional commands available: `read`, `decisions`, `errors`, `stats`, `files`, `highlights`.

<br>

## ✦ Keyboard Shortcuts

| Key | Action |
|:---:|--------|
| `/` | Focus search |
| `Esc` | Clear search / go back |
| `j` `k` | Next / previous session |
| `Enter` | Open selected session |
| `n` `N` | Next / previous user message |
| `h` | Return to sessions list |
| `o` | Toggle session outline |
| `c` | Open AI chat for current session |
| `1` `2` `3` | Sessions / AI Evolve / Insights |
| `?` | Show keyboard help overlay |

<br>

## ✦ Tech Stack

| Layer | Technology |
|-------|-----------|
| Server | Python 3.8+ stdlib (`http.server`, `json`, `threading`, `sqlite3`) |
| Database | SQLite with WAL mode + FTS5 full-text search |
| Frontend | Vanilla JavaScript (~5K lines), HTML5, CSS3 |
| Visualizations | [D3.js v7](https://d3js.org) — radar charts, force graphs, timelines, bubble packs |
| AI Integration | [Codex CLI](https://github.com/openai/codex) or [Claude Code](https://claude.ai/code) (optional, locally installed) |
| Storage | `.cache/sessions.db` (SQLite) + localStorage (UI state) |

<br>

## ✦ Roadmap

ConvoLab is actively developed. See the [user guide](docs/USER_GUIDE.md) for a full walkthrough.

- [ ] **Cross-tool support** — Cursor, Aider, Windsurf session import
- [ ] **Team dashboard** — Anonymized team-level Evolve analytics
- [ ] **Proactive insights** — Push notifications when new correction patterns emerge
- [ ] **Auto-evolve** — Incremental Evolve updates after every session (no manual refresh)
- [ ] **Decision archaeology** — Cross-session knowledge graph of technical decisions

<br>

<div align="center">

---

Built with 🧠 by [QuantaAlpha](https://github.com/QuantaAlpha)

</div>
