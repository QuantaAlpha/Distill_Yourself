# Claude Code Chat History Viewer — Design Doc

## Problem
~1988 JSONL conversation files (~1.9GB) across 15+ projects in `~/.claude/projects/`.
User needs to browse, search, and review past conversations — especially their own inputs.

## Architecture

**Python stdlib backend + vanilla HTML/CSS/JS frontend. Zero external dependencies.**

```
chat-viewer/
├── server.py          # Python HTTP server + REST API
├── static/
│   ├── index.html     # Single-page app
│   ├── style.css      # Styles
│   └── app.js         # Frontend logic
└── start.sh           # Launcher (python3 server.py)
```

### Backend (server.py)

Built on `http.server` — no Flask/Django needed.

**Startup flow:**
1. Scan all `~/.claude/projects/*/*.jsonl` → build metadata index
2. Extract per-session: id, title (from `ai-title`), project, mtime, file size, user message count
3. Cache metadata to `~/.claude/chat-viewer/.cache/index.json` (rebuild if stale)

**API endpoints:**
| Endpoint | Description |
|----------|-------------|
| `GET /` | Serve index.html |
| `GET /api/projects` | List projects with session counts |
| `GET /api/sessions?project=X&sort=date&page=N` | Paginated session list |
| `GET /api/session/<id>` | Full parsed conversation (lazy load) |
| `GET /api/search?q=keyword&page=N` | Search user messages across all sessions |

**Search strategy:** Streaming grep through JSONL files (no pre-built inverted index).
For ~2000 files this completes in seconds. Results return session matches with
context snippets and message positions for jump-to.

**Message parsing rules:**
- `type: "user"` + `message.role: "user"` → user message. Extract text from content (string or `{type:"text", text:"..."}`)
- `type: "assistant"` + `message.role: "assistant"` → assistant message. Content types: `text`, `thinking`, `tool_use`
- `type: "user"` + content has `tool_result` → tool result (pair with preceding tool_use)
- Skip: `queue-operation`, `file-history-snapshot`, `attachment` (system metadata)
- `ai-title` → session title
- Subagent conversations in `<session-id>/subagents/*.jsonl` → optional drill-down

### Frontend (static/index.html + style.css + app.js)

**Layout:** Three-panel responsive design
```
┌─────────────────────────────────────────────────┐
│  🔍 Search bar                                  │
├──────────┬──────────────────────────────────────┤
│ Projects │                                      │
│ ──────── │   Conversation View                  │
│ Sessions │   (chat bubbles)                     │
│          │                                      │
│          │   👤 User message (highlighted)      │
│          │   🤖 Assistant text                  │
│          │   🔧 Tool call (collapsible)         │
│          │   📋 Tool result (collapsible)       │
│          │                                      │
└──────────┴──────────────────────────────────────┘
```

**Key features:**
1. **User messages prominently highlighted** — larger font, distinct color, avatar
2. **Collapsible sections** — thinking blocks, tool calls, tool results collapsed by default
3. **Search with keyword highlighting** — results show matching sessions + snippets, click to jump to exact message
4. **Lazy loading** — session list paginated, conversation loaded on click
5. **Message-level anchors** — URL hash `#msg-N` for deep linking
6. **Keyboard shortcuts** — ↑↓ navigate sessions, / to focus search, Esc to clear
7. **Responsive** — works on narrow screens too

**Visual design:**
- Clean, modern look. Light theme (dark theme toggle optional)
- User messages: blue/indigo background, right-aligned or left with prominent styling
- Assistant text: light gray background
- Tool calls: monospace, collapsed with tool name visible
- Thinking: italic, very light, collapsed by default
- Timestamps on hover

## Data Flow

1. User opens `http://localhost:8080`
2. Frontend calls `/api/projects` → renders sidebar
3. User clicks project → `/api/sessions?project=X` → session list
4. User clicks session → `/api/session/<id>` → render conversation
5. User searches → `/api/search?q=keyword` → results with snippets → click to jump

## Performance Considerations

- Metadata index cached to disk, rebuilt only when new files detected
- Large sessions (>1MB) streamed and parsed incrementally
- Search is streaming (not full-index), parallelized with ThreadPoolExecutor
- Frontend virtualizes long conversations (render visible messages + buffer)
