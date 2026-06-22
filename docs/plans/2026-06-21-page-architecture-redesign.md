# Page Architecture Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure Chat Viewer from 7 flat pages to 4 organized pages (Home/Sessions/Insights/AI) with top navigation and inline filtering.

**Architecture:** Replace sidebar vertical nav with a top horizontal nav bar. Move filter controls from sidebar into main content area. Merge related pages: Timeline→Home, Analytics+Health+Snippets→Insights, Evolve+AI Analysis→AI. No server changes needed — all frontend.

**Tech Stack:** Vanilla JS, CSS, HTML (zero dependencies, existing D3.js CDN for Evolve)

**Spec:** `docs/specs/2026-06-21-page-architecture-redesign.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `static/index.html` | Major rewrite | Replace `#sidebar-nav` with `#top-nav`, restructure view containers |
| `static/style.css` | Major rewrite | Top nav styles, remove sidebar nav styles, Home/Insights/AI page layouts |
| `static/app.js` | Major rewrite | New view routing, Home dashboard logic, Insights tab switching, unified scope |
| `static/evolve.js` | Minor modify | Adapt to new AI page container (Evolve becomes left panel of AI page) |
| `server.py` | No changes | All APIs remain the same |

---

### Task 1: Top Navigation Bar + View Routing Shell

Replace sidebar vertical nav with horizontal top nav. Set up the 4 new view containers (empty shells). Wire routing so clicking each nav item shows the correct view. At this step, page content is just placeholders — real content moves in Tasks 2-5.

**Files:**
- Modify: `static/index.html` (lines 30-101: sidebar nav + sidebar content)
- Modify: `static/style.css` (lines 143-170: sidebar nav styles)
- Modify: `static/app.js` (lines 21-23: currentView enum, lines 133-165: nav click handlers, lines 289-300: showView + switchSidebarPanel)

- [ ] **Step 1: Replace `#sidebar-nav` with `#top-nav` in index.html**

In `static/index.html`, replace the entire `<nav id="sidebar-nav">...</nav>` block (lines 32-63) with a horizontal nav inside `#top-bar`:

```html
<!-- Inside #top-bar, after the search wrapper, before </header> -->
<nav id="top-nav">
  <button class="top-nav-item active" data-view="home">Home</button>
  <button class="top-nav-item" data-view="sessions">Sessions</button>
  <button class="top-nav-item" data-view="insights">Insights</button>
  <button class="top-nav-item" data-view="ai">AI</button>
</nav>
```

Remove the old `<nav id="sidebar-nav">...</nav>` entirely from inside `<aside id="sidebar">`.

- [ ] **Step 2: Add new view containers in index.html**

Inside `<main id="content">`, add these new view shells (keep existing `#conversation-view` and `#search-results` intact):

```html
<!-- Home page -->
<div id="home-view">
  <div id="home-stats"></div>
  <div id="home-body">
    <div id="home-heatmap"></div>
    <div id="home-recent"></div>
  </div>
  <div id="home-chat">
    <div id="home-chat-messages"></div>
    <div id="home-chat-input-area">
      <textarea id="home-chat-input" placeholder="问关于所有对话的问题…" rows="1"></textarea>
      <button id="home-chat-send">Send</button>
    </div>
  </div>
</div>

<!-- Insights page (tabbed) -->
<div id="insights-view" class="hidden">
  <div id="insights-tabs">
    <button class="insights-tab active" data-tab="hotspots">File Hotspots</button>
    <button class="insights-tab" data-tab="heatmap">Tool Heatmap</button>
    <button class="insights-tab" data-tab="errors">Error Patterns</button>
    <button class="insights-tab" data-tab="health">Project Health</button>
    <button class="insights-tab" data-tab="snippets">Snippets</button>
  </div>
  <div id="insights-body"></div>
</div>

<!-- AI page (Evolve left + Chat right) -->
<div id="ai-view" class="hidden">
  <div id="ai-scope-bar"></div>
  <div id="ai-split">
    <div id="ai-evolve-panel"><!-- Evolve tabs + content move here --></div>
    <div id="ai-chat-panel"><!-- AI Analysis chat moves here --></div>
  </div>
</div>
```

Remove old standalone views: `#welcome-screen`, `#timeline-view`, `#analytics-view`, `#snippets-view`, `#health-view`, `#chat-view`, `#evolve-view`. Keep `#conversation-view` and `#search-results`.

- [ ] **Step 3: Update sidebar to be contextual**

The sidebar (`<aside id="sidebar">`) keeps its `#sidebar-content` but removes the nav and filter bar. Sidebar panels remain: `panel-sessions` (for Sessions page), `panel-chat` (for AI page). Remove `panel-timeline` and `panel-analytics`.

```html
<aside id="sidebar">
  <!-- Filter bar moves to inline in Sessions page, removed from here -->
  <div id="sidebar-content">
    <div id="panel-sessions" class="sidebar-panel">
      <div class="panel-label">Recent <span id="session-count" class="badge"></span></div>
      <ul id="session-list"></ul>
    </div>
    <div id="panel-chat" class="sidebar-panel hidden">
      <div class="panel-label" style="display:flex;justify-content:space-between;align-items:center">
        Analysis History
        <button id="btn-new-chat" class="btn-sidebar-action">+ New</button>
      </div>
      <ul id="chat-history-list"></ul>
    </div>
  </div>
</aside>
```

- [ ] **Step 4: Add top nav + layout CSS**

In `static/style.css`, remove `.nav-item`, `.nav-section-label` styles. Add:

```css
/* Top navigation */
#top-nav {
  display: flex; gap: 2px; margin-left: 24px;
}
.top-nav-item {
  background: none; border: none; color: var(--text-secondary);
  font-size: 13px; font-weight: 500; padding: 6px 14px;
  border-radius: var(--radius-sm); cursor: pointer; transition: all 0.12s;
}
.top-nav-item:hover { background: var(--bg-hover); color: var(--text); }
.top-nav-item.active { background: var(--accent-dim); color: var(--accent); }
```

Update sidebar CSS: remove `#sidebar-nav` padding, sidebar now starts directly with content.

- [ ] **Step 5: Update showView + nav routing in app.js**

Update `currentView` enum comment and `showView` function:

```js
let currentView = "home"; // home|sessions|conversation|search|insights|ai

function showView(name, pushHistory = true) {
  if (pushHistory && currentView !== name) viewHistory.push(currentView);
  currentView = name;
  const views = {
    home: $("#home-view"), sessions: $("#home-view"), // sessions shares home initially, conversation takes over
    conversation: convView, search: searchResults,
    insights: $("#insights-view"), ai: $("#ai-view")
  };
  for (const [k, el] of Object.entries(views)) {
    if (el) el.classList.toggle("hidden", k !== name);
  }
  // Sidebar visibility
  const sidebar = $("#sidebar");
  if (sidebar) sidebar.classList.toggle("hidden", name === "home" || name === "insights");
}
```

Replace nav click handler to target `.top-nav-item`:

```js
document.querySelectorAll(".top-nav-item").forEach(btn => {
  btn.addEventListener("click", () => {
    const view = btn.dataset.view;
    document.querySelectorAll(".top-nav-item").forEach(b => b.classList.toggle("active", b === btn));
    if (view === "home") { showView("home"); renderHome(); }
    else if (view === "sessions") { showSidebar("sessions"); showView("sessions"); }
    else if (view === "insights") { showView("insights"); openInsights(); }
    else if (view === "ai") { showSidebar("chat"); showView("ai"); initAiPage(); }
  });
});
```

- [ ] **Step 6: Verify navigation works**

Start server: `python server.py`  
Open http://localhost:8080  
Verify: 4 top nav buttons visible, clicking each shows correct (placeholder) view, sidebar hides on Home/Insights, sidebar shows on Sessions/AI.

- [ ] **Step 7: Commit**

```bash
git add static/index.html static/style.css static/app.js
git commit -m "refactor: replace sidebar nav with top horizontal nav (4 pages)"
```

---

### Task 2: Home Page (Dashboard)

Build the Home page with stats cards, activity heatmap (from Timeline), recent sessions list, and AI chat input.

**Files:**
- Modify: `static/app.js` — add `renderHome()` function
- Modify: `static/style.css` — Home page layout styles
- Modify: `static/index.html` — finalize Home view markup

- [ ] **Step 1: Add Home page CSS**

```css
/* Home page */
#home-view {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  max-width: 900px; margin: 0 auto; width: 100%; padding: 0 24px;
}
#home-stats {
  display: flex; gap: 12px; padding: 20px 0 16px;
}
.home-stat-card {
  flex: 1; background: var(--bg-surface); border: 1px solid var(--border-light);
  border-radius: var(--radius); padding: 16px;
}
.home-stat-card .stat-value { font-size: 28px; font-weight: 700; color: var(--text); }
.home-stat-card .stat-label { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
#home-body {
  display: flex; gap: 20px; flex: 1; overflow: hidden;
}
#home-heatmap { flex: 2; overflow-y: auto; }
#home-recent { flex: 1; overflow-y: auto; }
.home-section-title {
  font-size: 11px; font-weight: 600; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;
}
.home-recent-item {
  padding: 8px 10px; border-radius: var(--radius-sm);
  cursor: pointer; transition: background 0.12s;
  border-bottom: 1px solid var(--border-light);
}
.home-recent-item:hover { background: var(--bg-hover); }
.home-recent-item .title { font-size: 13px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.home-recent-item .meta { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
/* Home chat — reuse from welcome-chat, just rename selectors */
#home-chat { /* same as #welcome-chat styles */ }
```

- [ ] **Step 2: Implement `renderHome()` in app.js**

```js
async function renderHome() {
  // Stats cards
  const statsEl = $("#home-stats");
  const thisWeek = allSessions.filter(s => {
    if (!s.date) return false;
    const d = new Date(s.date);
    return (Date.now() - d) < 7 * 86400000;
  });
  const projects = new Set(allSessions.map(s => s.project).filter(Boolean));
  statsEl.innerHTML = `
    <div class="home-stat-card"><div class="stat-value">${allSessions.length}</div><div class="stat-label">Total Sessions</div></div>
    <div class="home-stat-card"><div class="stat-value">${thisWeek.length}</div><div class="stat-label">This Week</div></div>
    <div class="home-stat-card"><div class="stat-value">${projects.size}</div><div class="stat-label">Projects</div></div>
  `;

  // Heatmap (reuse Timeline rendering into #home-heatmap)
  const heatmapEl = $("#home-heatmap");
  heatmapEl.innerHTML = '<div class="home-section-title">Activity</div><div id="home-heatmap-body">Loading…</div>';
  try {
    const data = await api("/api/timeline");
    const body = $("#home-heatmap-body");
    body.innerHTML = "";
    // Render simplified calendar heatmap (last 90 days)
    renderHomeHeatmap(body, data.days || []);
  } catch (e) {
    $("#home-heatmap-body").textContent = "Failed to load activity data";
  }

  // Recent sessions
  const recentEl = $("#home-recent");
  recentEl.innerHTML = '<div class="home-section-title">Recent Sessions</div>';
  const recent = allSessions.slice(0, 15);
  recent.forEach(s => {
    const item = document.createElement("div");
    item.className = "home-recent-item";
    item.innerHTML = `<div class="title">${esc(s.title || "Untitled")}</div><div class="meta">${s.project || ""} · ${formatDate(s.date)}</div>`;
    item.addEventListener("click", () => {
      // Navigate to Sessions > open this session
      document.querySelectorAll(".top-nav-item").forEach(b => b.classList.toggle("active", b.dataset.view === "sessions"));
      showSidebar("sessions");
      loadSession(s.id);
    });
    recentEl.appendChild(item);
  });
}

function renderHomeHeatmap(container, days) {
  // Simple grid: last 90 days, color by session count
  const last90 = days.slice(0, 90);
  if (!last90.length) { container.textContent = "No activity data"; return; }
  const maxCount = Math.max(...last90.map(d => d.sessionCount), 1);
  const grid = document.createElement("div");
  grid.style.cssText = "display:flex;flex-wrap:wrap;gap:3px";
  last90.reverse().forEach(d => {
    const cell = document.createElement("div");
    const intensity = d.sessionCount / maxCount;
    const alpha = 0.1 + intensity * 0.8;
    cell.style.cssText = `width:14px;height:14px;border-radius:3px;background:rgba(124,107,240,${alpha});cursor:pointer`;
    cell.title = `${d.date}: ${d.sessionCount} sessions`;
    grid.appendChild(cell);
  });
  container.appendChild(grid);
}
```

- [ ] **Step 3: Wire Home chat input**

Reuse the `submitWelcomeChat` logic but target `#home-chat-input`, `#home-chat-messages`, `#home-chat-send`. Rename the function to `submitHomeChat` and update DOM selectors.

- [ ] **Step 4: Set Home as default landing page**

In `init()`, change from `showView("welcome")` to `showView("home"); renderHome()`. Update logo click handler similarly.

- [ ] **Step 5: Verify Home page**

Refresh http://localhost:8080. Verify:
- Stats cards show correct numbers
- Heatmap renders last 90 days
- Recent sessions list is clickable → navigates to session
- AI chat input works at bottom

- [ ] **Step 6: Commit**

```bash
git add static/index.html static/app.js static/style.css
git commit -m "feat: add Home dashboard page with stats, heatmap, recent sessions"
```

---

### Task 3: Sessions Page — Inline Filters

Move the filter bar from sidebar into the main content area of the Sessions page. Sidebar becomes purely a session list.

**Files:**
- Modify: `static/index.html` — move `#filter-bar` into Sessions view area
- Modify: `static/style.css` — inline filter bar styles
- Modify: `static/app.js` — filter logic update

- [ ] **Step 1: Move filter bar HTML**

Remove `#filter-bar` from inside `<aside id="sidebar">`. Add it as the first child of the Sessions content area (above the conversation/welcome content). Wrap Sessions in a container:

```html
<!-- Sessions page wrapper (inside #content, shown when sessions nav active) -->
<div id="sessions-view">
  <div id="sessions-filter-bar">
    <div id="source-tabs"></div>
    <div id="project-bar">
      <button id="project-trigger"><span id="project-trigger-text">All Projects</span>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2.5 4 5 6.5 7.5 4"/></svg>
      </button>
      <div id="project-dropdown" class="hidden"></div>
    </div>
    <div class="date-filters"></div>
    <div id="sessions-scope-stats" class="scope-stats"></div>
  </div>
  <!-- #conversation-view and welcome content go here -->
</div>
```

- [ ] **Step 2: Style inline filter bar**

```css
#sessions-filter-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 20px; border-bottom: 1px solid var(--border-light);
}
#sessions-scope-stats {
  margin-left: auto; font-size: 11px; color: var(--text-muted);
}
```

- [ ] **Step 3: Update filter JS to show scope stats**

After filters change, update a stats line: `"1,234 sessions · 8 projects"`.

```js
function updateSessionsScopeStats() {
  const el = $("#sessions-scope-stats");
  if (!el) return;
  const filtered = getFilteredSessionList();
  const projects = new Set(filtered.map(s => s.project).filter(Boolean));
  el.textContent = `${filtered.length} sessions · ${projects.size} projects`;
}
```

Call `updateSessionsScopeStats()` after every filter change in `renderSessions`.

- [ ] **Step 4: Show/hide filter bar with Sessions view**

In `showView`, ensure `#sessions-filter-bar` is only visible when `currentView === "sessions"` or `currentView === "conversation"`.

- [ ] **Step 5: Verify inline filters**

Open Sessions page. Verify:
- Filter bar at top of main area (not in sidebar)
- Source tabs, project dropdown, date filters all work
- Scope stats update on filter change
- Sidebar only shows session list (no filters)

- [ ] **Step 6: Commit**

```bash
git add static/index.html static/app.js static/style.css
git commit -m "feat: move session filters inline into main content area"
```

---

### Task 4: Insights Page (Merged Analytics + Health + Snippets)

Combine Analytics, Project Health, and Snippets into one tabbed Insights page.

**Files:**
- Modify: `static/index.html` — finalize Insights view tabs
- Modify: `static/style.css` — Insights tab styles
- Modify: `static/app.js` — `openInsights()`, tab switching, reuse existing render functions

- [ ] **Step 1: Add Insights page CSS**

```css
#insights-view {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}
#insights-tabs {
  display: flex; gap: 2px; padding: 12px 20px;
  border-bottom: 1px solid var(--border-light);
}
.insights-tab {
  background: none; border: none; color: var(--text-secondary);
  font-size: 13px; padding: 8px 14px; border-radius: var(--radius-sm);
  cursor: pointer; transition: all 0.12s; font-family: inherit;
}
.insights-tab:hover { background: var(--bg-hover); color: var(--text); }
.insights-tab.active { background: var(--accent-dim); color: var(--accent); font-weight: 500; }
#insights-body {
  flex: 1; overflow-y: auto; padding: 20px 24px;
}
```

- [ ] **Step 2: Implement tab switching + data loading**

```js
let insightsActiveTab = "hotspots";
let insightsDataCache = { analytics: null, health: null, snippets: null };

function openInsights() {
  showView("insights");
  bindInsightsTabs();
  loadInsightsTab(insightsActiveTab);
}

function bindInsightsTabs() {
  document.querySelectorAll(".insights-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      insightsActiveTab = tab.dataset.tab;
      document.querySelectorAll(".insights-tab").forEach(t => t.classList.toggle("active", t === tab));
      loadInsightsTab(insightsActiveTab);
    });
  });
}

async function loadInsightsTab(tab) {
  const body = $("#insights-body");
  body.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-muted)">Loading…</div>';

  try {
    if (tab === "hotspots" || tab === "heatmap" || tab === "errors") {
      if (!insightsDataCache.analytics) {
        insightsDataCache.analytics = await api("/api/analytics");
      }
      renderInsightsAnalytics(body, insightsDataCache.analytics, tab);
    } else if (tab === "health") {
      if (!insightsDataCache.health) {
        insightsDataCache.health = await api("/api/project-health");
      }
      renderProjectHealth(insightsDataCache.health, body); // reuse existing
    } else if (tab === "snippets") {
      if (!insightsDataCache.snippets) {
        insightsDataCache.snippets = await api("/api/snippets");
      }
      renderSnippets(insightsDataCache.snippets, body); // reuse existing
    }
  } catch (err) {
    body.innerHTML = `<div style="padding:40px;text-align:center;color:#e57373">${esc(err.message)}</div>`;
  }
}
```

- [ ] **Step 3: Extract analytics section renderers**

The existing `renderAnalytics(data)` renders all 3 sections into `analyticsBody`. Split it so each section can render independently into a target container:

```js
function renderInsightsAnalytics(container, data, tab) {
  container.innerHTML = "";
  if (tab === "hotspots" && data.hotspots?.length) {
    // Reuse existing hotspot table rendering code from renderAnalytics
    renderHotspotsSection(container, data);
  } else if (tab === "heatmap" && data.heatmap?.tools?.length) {
    renderHeatmapSection(container, data);
  } else if (tab === "errors" && data.errors?.length) {
    renderErrorsSection(container, data);
  } else {
    container.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-muted)">No data</div>';
  }
}
```

Extract the 3 sections from the existing `renderAnalytics` function into `renderHotspotsSection`, `renderHeatmapSection`, `renderErrorsSection` — each takes `(container, data)`. The rendering code is already self-contained per section; just move each section's code into its own function.

- [ ] **Step 4: Adapt `renderProjectHealth` and `renderSnippets`**

These functions currently render into fixed containers (`#health-body`, `#snippets-body`). Change them to accept a container parameter: `renderProjectHealth(data, container)`, `renderSnippets(data, container)`. Update any internal `getElementById` calls to use the passed container.

- [ ] **Step 5: Verify Insights page**

Click Insights in top nav. Verify:
- 5 tabs visible, clicking each loads correct content
- File Hotspots table renders (with frequency bars)
- Tool Heatmap renders (matrix grid)
- Error Patterns renders (clustered cards)
- Project Health renders (project cards)
- Snippets renders (code blocks with copy)

- [ ] **Step 6: Commit**

```bash
git add static/index.html static/app.js static/style.css
git commit -m "feat: merge Analytics + Health + Snippets into Insights tabbed page"
```

---

### Task 5: AI Page (Evolve + AI Analysis)

Combine Evolve visualizations and AI Analysis chat into one split-pane AI page with shared scope.

**Files:**
- Modify: `static/index.html` — AI page structure
- Modify: `static/style.css` — AI page split layout
- Modify: `static/app.js` — `initAiPage()`, unified scope
- Modify: `static/evolve.js` — adapt `initEvolveView` to target new container

- [ ] **Step 1: Add AI page CSS**

```css
#ai-view {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}
#ai-scope-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 20px; border-bottom: 1px solid var(--border-light);
}
#ai-split {
  flex: 1; display: flex; overflow: hidden;
}
#ai-evolve-panel {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  border-right: 1px solid var(--border-light);
}
#ai-chat-panel {
  width: 380px; display: flex; flex-direction: column; overflow: hidden;
}
```

- [ ] **Step 2: Move Evolve content into AI left panel**

Move the Evolve header, tabs, tab-content, overview-bar from the old `#evolve-view > #evolve-main` into `#ai-evolve-panel`. Keep the same IDs so `evolve.js` functions still work.

```html
<div id="ai-evolve-panel">
  <div id="evolve-tabs">
    <button class="evolve-tab active" data-tab="profile">🧬 Profile</button>
    <button class="evolve-tab" data-tab="memory">🧠 Memory</button>
    <button class="evolve-tab" data-tab="rules">📐 Rules</button>
    <button class="evolve-tab" data-tab="signals">⚡ Signals</button>
    <button class="evolve-tab" data-tab="patterns">🔄 Patterns</button>
  </div>
  <div id="evolve-overview-bar"></div>
  <div id="evolve-tab-content">
    <div id="evolve-tab-header">
      <span id="evolve-tab-updated">尚未分析</span>
      <button id="evolve-tab-refresh" class="btn-text">🔄 Refresh</button>
    </div>
    <div id="evolve-tab-body">
      <div class="evolve-empty-state"><p>点击刷新，开始分析</p></div>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Move AI Analysis chat into AI right panel**

Move preset cards, messages, and input from old `#chat-view` / `#evolve-chat-panel` into `#ai-chat-panel`:

```html
<div id="ai-chat-panel">
  <div id="ai-chat-header">
    <span>💬 AI Analysis</span>
    <button id="btn-new-chat-ai" class="btn-sidebar-action">+ New</button>
  </div>
  <div id="ai-chat-presets" class="preset-grid preset-grid-1col"></div>
  <div id="ai-chat-messages"></div>
  <div id="ai-chat-input-area">
    <textarea id="ai-chat-input" placeholder="输入跨会话分析需求…" rows="1"></textarea>
    <button id="ai-chat-send">Send</button>
  </div>
</div>
```

- [ ] **Step 4: Render shared scope bar**

In `initAiPage()`, render Source/Date/Project scope filters into `#ai-scope-bar`. Reuse the existing `renderScopeTabs` + `renderScopeProjectDropdown` functions, but target the new containers. Use the unified `globalScope` state.

```js
function initAiPage() {
  renderAiScopeBar();
  if (window.initEvolveView) window.initEvolveView();
  populateAiChatPresets();
  restoreAiChatMessages();
}

function renderAiScopeBar() {
  const bar = $("#ai-scope-bar");
  if (!bar || bar.dataset.rendered) return;
  bar.dataset.rendered = "1";
  bar.innerHTML = `
    <span style="font-size:11px;color:var(--text-muted);font-weight:500">Scope:</span>
    <div id="ai-source-tabs" class="scope-tabs"></div>
    <span style="color:var(--border)">·</span>
    <div id="ai-date-tabs" class="scope-tabs"></div>
    <span style="color:var(--border)">·</span>
    <select id="ai-scope-project"><option value="">All Projects</option></select>
    <span id="ai-scope-stats" class="scope-stats" style="margin-left:auto"></span>
  `;
  // Render tabs using globalScope state, targeting #ai-source-tabs / #ai-date-tabs
  renderScopeTabsInto($("#ai-source-tabs"), $("#ai-date-tabs"));
  renderScopeProjectInto($("#ai-scope-project"));
  updateAiScopeStats();
}
```

- [ ] **Step 5: Update evolve.js container references**

In `static/evolve.js`, the `initEvolveView` function looks for `#evolve-tabs`, `#evolve-tab-body`, etc. Since we keep the same IDs inside `#ai-evolve-panel`, the `evolve.js` code works without changes. Only verify that Evolve's scope filter calls (if any reference `#evolve-source-tabs` etc.) are updated to use the shared `#ai-source-tabs`.

Check `evolve.js` for any DOM queries that reference old container IDs from `#evolve-view` or `#evolve-header`. Update `getEvolveScope()` to read from the unified `globalScope` state:

```js
// In evolve.js, update getEvolveScope:
window.getEvolveScope = function() {
  return { source: globalScopeSource, date: globalScopeDate, project: globalScopeProject };
};
```

- [ ] **Step 6: Wire AI chat submit**

Create `submitAiChat()` targeting `#ai-chat-input` and `#ai-chat-messages`. Same logic as existing `submitGlobalAi` / `submitChatViewAi` but with new element IDs. Use `globalScope` for scope values.

- [ ] **Step 7: Verify AI page**

Click AI in top nav. Verify:
- Left panel: Evolve tabs (Profile/Memory/Rules/Signals/Patterns) work
- Right panel: AI Analysis presets show, chat input works
- Scope bar at top: Source/Date/Project filters affect both panels
- Chat history in sidebar (when AI page active)

- [ ] **Step 8: Commit**

```bash
git add static/index.html static/app.js static/style.css static/evolve.js
git commit -m "feat: combine Evolve + AI Analysis into unified AI page"
```

---

### Task 6: Cleanup + Polish

Remove dead code from old pages, verify all navigation paths, update keyboard shortcuts.

**Files:**
- Modify: `static/app.js` — remove old view functions, update keyboard shortcuts
- Modify: `static/style.css` — remove old page styles
- Modify: `static/index.html` — remove any leftover old containers

- [ ] **Step 1: Remove dead CSS**

Remove styles for deleted elements: `#welcome-screen`, `.welcome-inner`, `.welcome-cards`, `#timeline-view`, `#analytics-view`, `#snippets-view`, `#health-view`, `#chat-view`, `#global-ai-header`, `#global-ai-scope`, `#global-ai-presets`, `#chat-messages`, `#chat-input-area`, `#chat-input`, `#chat-send`, `#evolve-view` layout styles (keep internal Evolve styles), old sidebar nav styles (`.nav-item`, `.nav-section-label`).

- [ ] **Step 2: Remove dead JS**

Remove functions: `openTimeline()`, `renderTimeline()`, `renderTimelineSidebar()`, `openAnalytics()` (replaced by `openInsights`), `openSnippets()` (replaced by Insights tab), `openProjectHealth()` (replaced by Insights tab), `submitWelcomeChat()`, `submitChatViewAi()`, old `initChatView()`.

Remove old welcome card click handlers, old nav item click handlers.

- [ ] **Step 3: Update keyboard shortcuts**

In `handleKeyboard()`, update shortcut bindings:
- `1` → Home, `2` → Sessions, `3` → Insights, `4` → AI (replacing old 1-7 bindings)
- `/` → focus search (unchanged)
- `?` → keyboard help (unchanged)

- [ ] **Step 4: Update keyboard help modal**

Update the `#kbd-help` modal content to reflect new shortcuts.

- [ ] **Step 5: Full regression test**

Test all paths:
- Home: stats, heatmap, recent sessions click-through, AI chat
- Sessions: inline filters, session list, conversation view, right panel (outline + session AI)
- Insights: all 5 tabs load data correctly
- AI: Evolve tabs work, scope filters, AI chat presets + input
- Search: `/` shortcut, results click-through
- Back navigation: `Escape` / `←` work correctly

- [ ] **Step 6: Commit**

```bash
git add static/index.html static/app.js static/style.css static/evolve.js
git commit -m "refactor: remove old page code, update shortcuts, final polish"
```
