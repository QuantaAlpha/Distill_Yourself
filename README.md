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

---

每天，全球 51% 的开发者都在和 AI 编程助手对话——产出数千轮包含架构决策、调试洞察、偏好信号的丰富交互——但终端一关，这些信息就沉入无人翻阅的 JSONL 日志文件。市面上 6 个以上的开源工具能浏览这些历史，但全部止步于「只读」——没有分析、没有模式提取、没有反馈闭环。ConvoLab 更进一步：它将你的 Claude Code 和 Codex 会话索引为可搜索、可分析的知识库，再通过 **Evolve AI** 引擎从五个维度挖掘智能——开发者画像、记忆图谱、纠正规则、行为信号、反复出现的问题模式——全部以交互式 D3.js 图表可视化。真正的突破在于闭环：Evolve 将发现同步回你的 `CLAUDE.md` 和记忆文件，AI 在下次启动时自动读取——更少的纠正、更少的上下文重建、一个越用越懂你的搭档。在开发者对 AI 输出的信任度从 40% 跌至 29%、团队每个冲刺仅重建上下文就浪费 2-3 个工程日的当下，ConvoLab 把一次性的对话变成持续积累的智能资产。零依赖、完全本地、数据不出机器。

**[📖 Read the full vision →](docs/vision.html)**

</div>

<br>

## ✦ The Problem

Every day, millions of developers have rich conversations with AI coding assistants — architecture decisions, debugging sessions, preference corrections, technical tradeoffs. Then the terminal closes and all of it vanishes into raw JSONL log files.

**The numbers tell the story:**
- 51% of developers use AI tools daily, yet only 29% trust the output ([source](https://uvik.net/blog/ai-coding-assistant-statistics/))
- Context rebuild costs ~1 hour/week per developer — 2-3 engineering days per 10-person sprint ([source](https://smarterarticles.co.uk/when-coding-agents-forget-the-hidden-cost-of-ai-context-degradation))
- 6+ open-source session viewers exist, but they're all **read-only** — no analytics, no self-evolution
- Enterprise observability tools (LangSmith, Braintrust) raised $80M+ but don't serve individual CLI users

ConvoLab closes this gap with three layers: **See** your history → **Understand** patterns → **Feed it back** to make AI smarter. All running locally — your data never leaves your machine.

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

### 🗂 Sessions — Browse & Search

ChatGPT-style interface for your entire Claude Code and Codex history.

- **Message rendering** — user prompts, assistant replies, tool calls (Bash, Read, Edit…), and thinking blocks each get distinct visual treatment
- **Fuzzy search** — search across session titles and user messages with keyword highlighting
- **Smart filters** — filter by source (Claude/Codex), date range, and project; active filters display as inline chips
- **Session outline** — jump between user messages within a long conversation
- **Keyboard-driven** — `j/k` to navigate, `/` to search, `Enter` to open, `Esc` to go back

### 📊 Insights — Understand Patterns

Five analytical tabs aggregating patterns across your entire session history.

| Tab | What it shows |
|-----|---------------|
| **Tool Heatmap** | Usage frequency of each tool type with visual intensity scaling |
| **File Hotspots** | Most frequently referenced files ranked by touch count |
| **Error Patterns** | Recurring failures and error messages with source context |
| **Project Health** | Per-project activity scores, session counts, and trend arrows |
| **Snippets** | Extracted code blocks with language tags and applied/suggested status |

### 🧬 Evolve AI — Self-Evolution Engine

The core differentiator. Five D3.js-powered interactive visualizations that mine your conversation history for actionable intelligence — then **sync it back** to make your AI smarter.

| Tab | What it answers | Visualization |
|-----|----------------|---------------|
| **Profile** | *Who are you as a developer?* | Radar chart — autonomy, complexity, tool diversity, debugging style |
| **Memory** | *What do you care about?* | Force-directed graph of preferences, habits, and their relationships |
| **Rules** | *What have you corrected?* | Priority-ranked rule cards (P0/P1/P2) with user-quote evidence |
| **Signals** | *Are corrections trending up or down?* | Stacked timeline of style/scope/accuracy/workflow corrections |
| **Patterns** | *What keeps going wrong?* | Bubble chart of recurring issues with improvement suggestions |

**The closed loop:** Evolve builds your Profile and Memory → syncs Profile to `~/.claude/CLAUDE.md` and Memory nodes to `~/.claude/memory/` → Claude Code reads these on next startup → generates better output → fewer corrections needed. Rules and Signals are generated for review and reference.

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
├── server.py            # HTTP server (2.8K lines) — REST API, JSONL parser, AI proxy, SSE streaming
├── db.py                # SQLite storage — sessions, messages, FTS5 search, pre-aggregates
├── analyze.py           # CLI analytics tool (2.2K lines) — standalone analysis + Evolve generators
├── start.sh             # Quick launcher
├── docs/
│   └── vision.html      # Product vision & narrative
└── static/
    ├── index.html       # SPA shell — sidebar nav + multi-view layout
    ├── app.js           # Core application logic (2.6K lines, vanilla JS)
    ├── evolve.js        # D3.js interactive visualizations (1.4K lines)
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
<summary><b>16 endpoints</b> — click to expand</summary>

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
| Frontend | Vanilla JavaScript (~4K lines), HTML5, CSS3 |
| Visualizations | [D3.js v7](https://d3js.org) — radar charts, force graphs, timelines, bubble packs |
| AI Integration | [Codex CLI](https://github.com/openai/codex) or [Claude Code](https://claude.ai/code) (optional, locally installed) |
| Storage | `.cache/sessions.db` (SQLite) + localStorage (UI state) |

<br>

## ✦ Roadmap

ConvoLab is actively developed. See the [full vision document](docs/vision.html) for the product narrative and future directions.

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
