<div align="center">

# ⬡ ConvoLab

**AI Session Intelligence Platform**

*Transform your Claude Code & Codex conversation histories into actionable insights.*
*Browse. Search. Analyze. Evolve.*

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Dependencies](https://img.shields.io/badge/Dependencies-Zero-00C853?style=flat-square)](.)
[![Privacy](https://img.shields.io/badge/Privacy-Local_First-7C3AED?style=flat-square&logo=shield&logoColor=white)](.)
[![D3.js](https://img.shields.io/badge/Viz-D3.js-F9A03C?style=flat-square&logo=d3dotjs&logoColor=white)](https://d3js.org)

---

**ConvoLab** parses your local AI coding session files and serves a beautiful analytics dashboard — no cloud, no signup, no dependencies to install. Just `python3 server.py` and go.

</div>

<br>

## ✦ Why ConvoLab

Most AI coding tools generate thousands of conversation turns — then forget them. ConvoLab resurfaces that hidden knowledge:

- **What tools do you actually use?** See heatmaps of Bash, Edit, Read, Grep across all sessions
- **Where are the hotspots?** Discover which files get touched most and where errors cluster
- **How is your AI evolving?** Track behavioral patterns, memory growth, and style shifts over time
- **What happened last Tuesday?** Full-text search across every conversation you've ever had

All of this runs locally. Your data never leaves your machine.

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

### Sessions

Browse all Claude Code and Codex sessions in a ChatGPT-style interface with sidebar navigation.

- **Message rendering** — user prompts, assistant replies, tool calls (Bash, Read, Edit…), and thinking blocks each get distinct visual treatment
- **Smart filter popover** — filter by source, date range, and project; active filters display as inline chips (`Codex · 7d · my-project`)
- **Full-text search** — search across all session content with highlighted keyword matches
- **Session outline** — jump between user messages within a long conversation
- **Keyboard-driven** — `j/k` to navigate, `/` to search, `Enter` to open, `Esc` to go back

### Insights

Five analytical tabs that aggregate patterns across your entire session history.

| Tab | What it shows |
|-----|---------------|
| **Tool Heatmap** | Usage frequency of each tool type with visual intensity scaling |
| **File Hotspots** | Most frequently touched files ranked by edit count |
| **Error Patterns** | Recurring failures and error messages with source context |
| **Project Health** | Per-project activity scores, session counts, and trend arrows |
| **Snippets** | Extracted code blocks with language tags and applied/suggested status |

### AI Evolve

Five D3.js-powered interactive visualizations that reveal how your AI usage evolves over time.

| Visualization | Description |
|--------------|-------------|
| **Profile Radar** | Multi-axis chart — autonomy, complexity, tool diversity, error handling style |
| **Memory Mind Map** | Force-directed graph of user memory entries and their semantic relationships |
| **Rules Force Graph** | Interactive network of CLAUDE.md rules showing connections and clusters |
| **Signals Timeline** | Temporal scatter plot of behavioral shifts and preference changes |
| **Behavior Patterns** | Clustered pattern detection with evolution tracking |

### AI Chat

Ask natural-language questions about your sessions — powered by Claude via the Anthropic API.

- **Session-scoped** — "What was the root cause of this bug?" (analyzes one session)
- **Global-scoped** — "Which project had the most errors this week?" (analyzes all sessions)
- **Persistent history** — conversations are saved to localStorage

<br>

## ✦ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5757` | Server port |
| `ANTHROPIC_API_KEY` | — | Required for AI Chat and AI Evolve analysis |

```bash
# Custom port
PORT=3000 python3 server.py

# With AI features
ANTHROPIC_API_KEY=sk-ant-... python3 server.py
```

<br>

## ✦ Architecture

```
ConvoLab/
├── server.py            # HTTP server, REST API, JSONL parser, AI chat proxy
├── analyze.py           # Standalone CLI analytics tool
├── start.sh             # Quick launcher
└── static/
    ├── index.html       # SPA shell — sidebar nav + 3 content views
    ├── app.js           # Core application logic (vanilla JS)
    ├── evolve.js        # D3.js interactive visualizations
    └── style.css        # Light premium theme
```

### Design Philosophy

| Principle | Implementation |
|-----------|---------------|
| **Zero dependencies** | Python stdlib server, vanilla JS frontend. Only D3.js loaded via CDN. |
| **Privacy first** | All data read from local `~/.claude/` and `~/.codex/`. No telemetry, no external calls. |
| **Single-file server** | One `server.py` handles routing, parsing, caching, and AI proxy. |
| **Incremental indexing** | Session index built at startup, cached to disk. Only modified files re-parsed on refresh. |

### REST API

<details>
<summary><b>14 endpoints</b> — click to expand</summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/sessions` | List all sessions (id, title, date, source, project) |
| `GET` | `/api/session/:id` | Full message history for a session |
| `GET` | `/api/projects` | List all detected projects |
| `GET` | `/api/search?q=…` | Full-text search across sessions |
| `GET` | `/api/timeline` | Daily session counts for heatmap rendering |
| `GET` | `/api/analytics` | Aggregated tool usage statistics |
| `GET` | `/api/insights` | File hotspots + error pattern analysis |
| `GET` | `/api/project-health` | Per-project health scores and trends |
| `GET` | `/api/snippets` | Extracted code snippets with metadata |
| `GET` | `/api/evolve/:tab` | AI Evolve data (profile/memory/rules/signals/patterns) |
| `GET` | `/api/stats` | Global statistics summary |
| `POST` | `/api/chat` | AI chat (requires `ANTHROPIC_API_KEY`) |
| `POST` | `/api/refresh` | Rebuild session index from disk |

</details>

<br>

## ✦ CLI Analytics

```bash
# Quick terminal report
python3 analyze.py

# AI-enhanced analysis
ANTHROPIC_API_KEY=sk-ant-... python3 analyze.py --ai
```

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
| Server | Python 3.8+ stdlib (`http.server`, `json`, `threading`) |
| Frontend | Vanilla JavaScript, HTML5, CSS3 |
| Visualizations | [D3.js v7](https://d3js.org) (CDN) |
| AI Integration | [Anthropic API](https://docs.anthropic.com) (optional) |
| Storage | Filesystem + localStorage (no database) |

<br>

<div align="center">

---

Built with 🧠 by [QuantaAlpha](https://github.com/QuantaAlpha)

</div>
