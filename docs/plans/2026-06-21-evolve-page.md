# Evolve Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Evolve" page with 5 D3.js-visualized tabs (Profile/Memory/Rules/Signals/Patterns) that extract structured insights from conversation history via AI analysis.

**Architecture:** New navigation item "Evolve" opens a tabbed page. Each tab triggers a Codex CLI analysis via `/api/chat` (existing endpoint), expects structured JSON back, renders with D3.js. Results cached in localStorage. AI Analysis presets link to Evolve tabs with auto-redirect. Right panel AI messages get fold/expand + modal popup.

**Tech Stack:** D3.js v7 (CDN), vanilla JS, existing Python server + Codex CLI integration

**Spec:** `docs/specs/2026-06-21-evolve-page-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `static/evolve.js` | Evolve page logic: tab switching, D3 visualizations, caching, API calls |
| Modify | `static/index.html` | Add D3.js CDN, Evolve nav item, evolve-view HTML, modal overlay |
| Modify | `static/app.js` | Wire Evolve nav, add right-panel fold/modal, AI Analysis redirect |
| Modify | `static/style.css` | Evolve page styles, modal styles, fold/expand styles |
| Modify | `server.py` | No changes needed — reuses existing `/api/chat` endpoint |

---

### Task 1: D3.js CDN + Evolve nav item + page skeleton

**Files:**
- Modify: `static/index.html:14` (add D3 script), `:52-56` (add nav item), `:231` (add evolve-view div), `:316` (add evolve.js script)

- [ ] **Step 1: Add D3.js CDN to index.html head**

In `static/index.html`, after line 6 (`<link rel="stylesheet" href="style.css">`), add:

```html
<script src="https://d3js.org/d3.v7.min.js"></script>
```

- [ ] **Step 2: Add Evolve nav item in sidebar**

In `static/index.html`, before the nav-divider (line 52), insert:

```html
<button class="nav-item" data-view="evolve">
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2a10 10 0 1 0 10 10"/><path d="M12 2v4"/><path d="M12 12l7-7"/><circle cx="12" cy="12" r="3"/></svg>
  Evolve
</button>
```

- [ ] **Step 3: Add evolve-view div in content area**

In `static/index.html`, after the `chat-view` div (after line 291, before the closing `</main>`), add:

```html
<div id="evolve-view" class="hidden">
  <div id="evolve-header">
    <div class="evolve-title-row">
      <h3>Evolve</h3>
      <p class="evolve-subtitle">从对话中学习，让 AI 越用越懂你</p>
    </div>
    <button id="evolve-refresh-all" class="btn-text">🔄 Refresh All</button>
  </div>
  <div id="evolve-overview-bar"></div>
  <div id="evolve-scope">
    <div class="scope-row">
      <span class="scope-label">Source</span>
      <div id="evolve-source-tabs" class="scope-tabs"></div>
    </div>
    <div class="scope-row">
      <span class="scope-label">Time</span>
      <div id="evolve-date-tabs" class="scope-tabs"></div>
    </div>
    <div class="scope-row">
      <span class="scope-label">Project</span>
      <select id="evolve-scope-project"><option value="">All Projects</option></select>
    </div>
  </div>
  <div id="evolve-tabs">
    <button class="evolve-tab active" data-tab="profile">🧬 Profile</button>
    <button class="evolve-tab" data-tab="memory">🧠 Memory</button>
    <button class="evolve-tab" data-tab="rules">📐 Rules</button>
    <button class="evolve-tab" data-tab="signals">⚡ Signals</button>
    <button class="evolve-tab" data-tab="patterns">🔄 Patterns</button>
  </div>
  <div id="evolve-tab-content">
    <div id="evolve-tab-header">
      <span id="evolve-tab-updated">尚未分析</span>
      <button id="evolve-tab-refresh" class="btn-text">🔄 Refresh</button>
    </div>
    <div id="evolve-tab-body">
      <div class="evolve-empty-state">
        <p>点击刷新，开始分析最近的对话</p>
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Add modal overlay for message popup**

In `static/index.html`, before the closing `</div>` of `#app` (before kbd-help div), add:

```html
<div id="msg-modal" class="hidden">
  <div class="msg-modal-backdrop"></div>
  <div class="msg-modal-content">
    <button class="msg-modal-close">✕</button>
    <div class="msg-modal-body"></div>
  </div>
</div>
```

- [ ] **Step 5: Add evolve.js script tag**

In `static/index.html`, after the `app.js` script tag (line 316), add:

```html
<script src="evolve.js"></script>
```

- [ ] **Step 6: Verify**

Run `python3 server.py`, open `http://localhost:8080`. Confirm Evolve nav item appears in sidebar. Clicking it should show the empty Evolve page skeleton (tabs visible, empty state message shown).

- [ ] **Step 7: Commit**

```bash
git add static/index.html
git commit -m "feat: add Evolve page skeleton with D3.js CDN and nav item"
```

---

### Task 2: Evolve core logic — tab switching, caching, API calls

**Files:**
- Create: `static/evolve.js`
- Modify: `static/app.js:143-153` (add evolve to nav handler and showView)

- [ ] **Step 1: Create evolve.js with core infrastructure**

Create `static/evolve.js`:

```javascript
/**
 * Evolve Page — D3.js visualizations for AI self-evolution
 * Depends on: app.js (for showView, api, allSessions, esc, renderMarkdownSimple)
 */
(function () {
  "use strict";

  // ── State ──
  let evolveActiveTab = "profile";
  let evolveCache = {}; // {tab: {updatedAt, data}}
  let evolveLoading = false;
  let evolveScopeSource = "all";
  let evolveScopeDate = "7d";
  let evolveScopeProject = "";

  // ── DOM refs ──
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // ── Init (called from app.js when Evolve nav clicked) ──
  window.initEvolveView = function () {
    loadEvolveCache();
    renderEvolveScopeTabs();
    renderEvolveScopeProject();
    bindEvolveEvents();
    switchEvolveTab(evolveActiveTab);
  };

  function bindEvolveEvents() {
    // Tab switching
    $$(".evolve-tab").forEach(tab => {
      tab.onclick = () => switchEvolveTab(tab.dataset.tab);
    });

    // Per-tab refresh
    const tabRefresh = $("#evolve-tab-refresh");
    if (tabRefresh) tabRefresh.onclick = () => refreshEvolveTab(evolveActiveTab);

    // Refresh all
    const refreshAll = $("#evolve-refresh-all");
    if (refreshAll) refreshAll.onclick = () => refreshAllEvolveTabs();
  }

  function switchEvolveTab(tab) {
    evolveActiveTab = tab;
    $$(".evolve-tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tab));
    renderEvolveTabContent(tab);
    updateEvolveOverviewBar();
  }

  // ── Cache ──
  function loadEvolveCache() {
    try {
      const raw = localStorage.getItem("chatview-evolve");
      if (raw) evolveCache = JSON.parse(raw);
    } catch (e) { evolveCache = {}; }
  }

  function saveEvolveCache() {
    try {
      localStorage.setItem("chatview-evolve", JSON.stringify(evolveCache));
    } catch (e) { /* quota */ }
  }

  function getCachedTab(tab) {
    return evolveCache[tab] || null;
  }

  function setCachedTab(tab, data) {
    evolveCache[tab] = { updatedAt: new Date().toISOString(), data };
    saveEvolveCache();
  }

  // ── Scope filters ──
  function renderEvolveScopeTabs() {
    const sessions = window.allSessions || [];
    // Source tabs
    const srcContainer = $("#evolve-source-tabs");
    if (srcContainer) {
      srcContainer.innerHTML = "";
      const counts = { all: sessions.length, claude: 0, codex: 0 };
      sessions.forEach(s => { counts[s.source || "claude"]++; });
      [{ key: "all", label: "All" }, { key: "claude", label: "Claude" }, { key: "codex", label: "Codex" }].forEach(s => {
        const btn = document.createElement("button");
        btn.className = `scope-tab${s.key === evolveScopeSource ? " active" : ""}`;
        btn.innerHTML = `${s.label} <span class="tab-count">${counts[s.key] || 0}</span>`;
        btn.onclick = () => { evolveScopeSource = s.key; renderEvolveScopeTabs(); renderEvolveScopeProject(); };
        srcContainer.appendChild(btn);
      });
    }
    // Date tabs
    const dateContainer = $("#evolve-date-tabs");
    if (dateContainer) {
      dateContainer.innerHTML = "";
      [{ key: "1d", label: "Today" }, { key: "7d", label: "This Week" }, { key: "30d", label: "30 Days" }, { key: "90d", label: "3 Months" }, { key: "all", label: "All" }].forEach(d => {
        const btn = document.createElement("button");
        btn.className = `scope-tab${d.key === evolveScopeDate ? " active" : ""}`;
        btn.textContent = d.label;
        btn.onclick = () => { evolveScopeDate = d.key; renderEvolveScopeTabs(); };
        dateContainer.appendChild(btn);
      });
    }
  }

  function renderEvolveScopeProject() {
    const sel = $("#evolve-scope-project");
    if (!sel) return;
    sel.innerHTML = '<option value="">All Projects</option>';
    const sessions = window.allSessions || [];
    const projCounts = {};
    sessions.forEach(s => {
      if (evolveScopeSource !== "all" && (s.source || "claude") !== evolveScopeSource) return;
      projCounts[s.project || "unknown"] = (projCounts[s.project || "unknown"] || 0) + 1;
    });
    Object.entries(projCounts).sort((a, b) => b[1] - a[1]).forEach(([name, count]) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = `${name} (${count})`;
      sel.appendChild(opt);
    });
    sel.value = evolveScopeProject;
    sel.onchange = () => { evolveScopeProject = sel.value; };
  }

  function getEvolveScope() {
    return { source: evolveScopeSource, date: evolveScopeDate, project: evolveScopeProject };
  }

  // ── Overview bar ──
  function updateEvolveOverviewBar() {
    const bar = $("#evolve-overview-bar");
    if (!bar) return;
    const tabs = ["profile", "memory", "rules", "signals", "patterns"];
    const icons = { profile: "🧬", memory: "🧠", rules: "📐", signals: "⚡", patterns: "🔄" };
    const labels = { profile: "Profile", memory: "Memory", rules: "Rules", signals: "Signals", patterns: "Patterns" };
    bar.innerHTML = "";
    tabs.forEach(tab => {
      const cached = getCachedTab(tab);
      const count = cached ? getTabItemCount(tab, cached.data) : 0;
      const div = document.createElement("div");
      div.className = `evolve-stat-card${tab === evolveActiveTab ? " active" : ""}`;
      div.innerHTML = `<span class="evolve-stat-icon">${icons[tab]}</span><span class="evolve-stat-count">${count}</span><span class="evolve-stat-label">${labels[tab]}</span>`;
      div.onclick = () => switchEvolveTab(tab);
      bar.appendChild(div);
    });
    // Last scan info
    const anyUpdated = tabs.map(t => getCachedTab(t)?.updatedAt).filter(Boolean).sort().pop();
    if (anyUpdated) {
      const span = document.createElement("span");
      span.className = "evolve-last-scan";
      span.textContent = `Last scan: ${timeAgo(anyUpdated)}`;
      bar.appendChild(span);
    }
  }

  function getTabItemCount(tab, data) {
    if (!data) return 0;
    switch (tab) {
      case "profile": return data.radar?.dimensions?.length || 0;
      case "memory": return data.nodes?.length || 0;
      case "rules": return data.rules?.length || 0;
      case "signals": return data.events?.length || 0;
      case "patterns": return data.bubbles?.length || 0;
      default: return 0;
    }
  }

  function timeAgo(iso) {
    const diff = Date.now() - new Date(iso).getTime();
    if (diff < 60000) return "just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return `${Math.floor(diff / 86400000)}d ago`;
  }

  // ── Tab content rendering ──
  function renderEvolveTabContent(tab) {
    const body = $("#evolve-tab-body");
    const updatedEl = $("#evolve-tab-updated");
    if (!body) return;

    const cached = getCachedTab(tab);
    if (cached && cached.data) {
      if (updatedEl) updatedEl.textContent = `Updated: ${timeAgo(cached.updatedAt)}`;
      body.innerHTML = "";
      renderTabVisualization(tab, cached.data, body);
    } else {
      if (updatedEl) updatedEl.textContent = "尚未分析";
      body.innerHTML = '<div class="evolve-empty-state"><p>点击 🔄 Refresh 开始分析最近的对话</p></div>';
    }
  }

  function renderTabVisualization(tab, data, container) {
    switch (tab) {
      case "profile": renderProfileTab(data, container); break;
      case "memory": renderMemoryTab(data, container); break;
      case "rules": renderRulesTab(data, container); break;
      case "signals": renderSignalsTab(data, container); break;
      case "patterns": renderPatternsTab(data, container); break;
    }
  }

  // ── API call for analysis ──
  function refreshEvolveTab(tab) {
    if (evolveLoading) return;
    evolveLoading = true;
    const body = $("#evolve-tab-body");
    const updatedEl = $("#evolve-tab-updated");
    if (body) body.innerHTML = '<div class="evolve-skeleton"><div class="skeleton-bar"></div><div class="skeleton-bar short"></div><div class="skeleton-bar"></div><div class="skeleton-circle"></div></div>';
    if (updatedEl) updatedEl.textContent = "分析中…";

    const prompt = getEvolvePrompt(tab);
    const scope = getEvolveScope();

    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, contextType: "global", scope })
    })
      .then(r => r.json())
      .then(result => {
        evolveLoading = false;
        const raw = result.response || "";
        const data = parseEvolveResponse(tab, raw);
        setCachedTab(tab, data);
        renderEvolveTabContent(tab);
        updateEvolveOverviewBar();
      })
      .catch(err => {
        evolveLoading = false;
        if (body) body.innerHTML = `<div class="evolve-empty-state"><p>分析失败：${err.message}</p></div>`;
      });
  }

  function refreshAllEvolveTabs() {
    const tabs = ["profile", "memory", "rules", "signals", "patterns"];
    let idx = 0;
    function next() {
      if (idx >= tabs.length) return;
      const tab = tabs[idx++];
      evolveLoading = false; // allow sequential
      switchEvolveTab(tab);
      refreshEvolveTab(tab);
      // Wait for completion by polling evolveLoading
      const check = setInterval(() => {
        if (!evolveLoading) { clearInterval(check); setTimeout(next, 500); }
      }, 1000);
    }
    next();
  }

  // ── Prompts for each tab ──
  function getEvolvePrompt(tab) {
    const base = "Analyze conversations and respond ONLY with valid JSON (no markdown, no explanation, just the JSON object).";
    switch (tab) {
      case "profile":
        return `${base}

Extract user profile from conversation history. Output JSON:
{
  "radar": {"dimensions": [{"name": "Caution", "score": 0.0-1.0, "confidence": "high|medium|low"}, ...]},
  "mindmap": {"center": "User", "branches": [{"label": "category", "children": ["item1", "item2"]}, ...]},
  "cards": [{"category": "Working Style|Communication|Technical|Review", "items": ["trait1", "trait2"]}, ...]
}

Radar dimensions should include 6-8 from: Caution, Detail, Autonomy, Verification, Design Taste, Communication, Speed, Directness.
Mind map branches: Tech Stack, Projects, Common Tasks, Preferences.
Cards: group behavioral observations into categories.`;

      case "memory":
        return `${base}

Extract user preferences and memories from conversations. Output JSON:
{
  "nodes": [{"id": "m1", "label": "preference text", "type": "preference|workflow|tooling|design|communication", "frequency": N, "confidence": "high|medium|low", "sessions": ["session_id"]}, ...],
  "links": [{"source": "m1", "target": "m2", "strength": 0.0-1.0}, ...],
  "cards": [{"id": "m1", "content": "full description", "firstSeen": "YYYY-MM-DD", "lastSeen": "YYYY-MM-DD", "evidence": "user quote"}, ...]
}

Look for: explicit preferences ("I prefer...", "don't do..."), recurring patterns, tool/style choices, workflow habits.`;

      case "rules":
        return `${base}

Extract rules from user corrections in conversations. Output JSON:
{
  "rules": [{"id": "r1", "priority": "P0|P1|P2", "category": "style|scope|accuracy|workflow|safety",
    "rule": "rule text", "why": "reason", "positive": "good example", "negative": "bad example",
    "evidence": [{"session": "session_id", "quote": "user's exact words"}], "frequency": N}, ...]
}

P0=must follow, P1=strongly recommended, P2=nice to have. Look for correction signals: "不要/不是/应该/别/wrong/stop/actually".`;

      case "signals":
        return `${base}

Extract correction events from conversations. Output JSON:
{
  "timeline": [{"date": "YYYY-MM-DD", "counts": {"style": N, "scope": N, "accuracy": N, "workflow": N}}, ...],
  "events": [{"id": "c1", "date": "YYYY-MM-DD", "session": "session_id",
    "type": "style|scope|accuracy|workflow|overengineering",
    "userQuote": "user's correction text", "aiIssue": "what AI did wrong",
    "correction": "what should be done", "linkedRule": "rule_id or null"}, ...]
}

Group by date. Identify correction types: style mismatch, scope creep, factual error, workflow issue, overengineering.`;

      case "patterns":
        return `${base}

Find repeating problem patterns across conversations. Output JSON:
{
  "bubbles": [{"id": "p1", "label": "short pattern name", "frequency": N, "type": "error|efficiency|knowledge_gap|workflow", "trend": "increasing|stable|decreasing"}, ...],
  "cards": [{"id": "p1", "description": "detailed description", "frequency": N,
    "cost": "estimated time/effort cost", "suggestion": "improvement suggestion",
    "sessions": ["session_id1", "session_id2"], "trend": "increasing|stable|decreasing"}, ...]
}

Look for: repeated errors, frequent searches for same topic, recurring tool issues, efficiency bottlenecks.`;
    }
  }

  // ── Parse AI response to structured data ──
  function parseEvolveResponse(tab, raw) {
    // Try to extract JSON from response
    try {
      // Try direct parse
      return JSON.parse(raw);
    } catch (e) {
      // Try to find JSON block in markdown
      const jsonMatch = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
      if (jsonMatch) {
        try { return JSON.parse(jsonMatch[1]); } catch (e2) { /* fall through */ }
      }
      // Try to find first { ... } block
      const braceMatch = raw.match(/\{[\s\S]*\}/);
      if (braceMatch) {
        try { return JSON.parse(braceMatch[0]); } catch (e3) { /* fall through */ }
      }
    }
    // Fallback: return raw text wrapped
    return { _raw: raw, _parseError: true };
  }

  // ── Placeholder renderers (will be filled in Tasks 4-8) ──
  function renderProfileTab(data, container) {
    container.innerHTML = '<div class="evolve-empty-state"><p>Profile visualization — coming soon</p></div>';
  }
  function renderMemoryTab(data, container) {
    container.innerHTML = '<div class="evolve-empty-state"><p>Memory visualization — coming soon</p></div>';
  }
  function renderRulesTab(data, container) {
    container.innerHTML = '<div class="evolve-empty-state"><p>Rules visualization — coming soon</p></div>';
  }
  function renderSignalsTab(data, container) {
    container.innerHTML = '<div class="evolve-empty-state"><p>Signals visualization — coming soon</p></div>';
  }
  function renderPatternsTab(data, container) {
    container.innerHTML = '<div class="evolve-empty-state"><p>Patterns visualization — coming soon</p></div>';
  }

  // ── Public API for app.js linkage ──
  window.navigateToEvolveTab = function (tab, data) {
    if (data) setCachedTab(tab, data);
    switchEvolveTab(tab);
    updateEvolveOverviewBar();
  };

})();
```

- [ ] **Step 2: Wire Evolve into app.js navigation**

In `static/app.js`, in the nav-item click handler (around line 143), add `evolve` to the panelMap and view handler. Find the block:

```javascript
if (view === "timeline") { showView("timeline"); openTimeline(); }
else if (view === "analytics") { showView("analytics"); openAnalytics(); }
```

Add before the `else showView("welcome")` line:

```javascript
else if (view === "evolve") { showView("evolve"); if (window.initEvolveView) window.initEvolveView(); }
```

In the `showView` function (around line 278), add `evolve` to the views map:

```javascript
evolve: $("#evolve-view"),
```

- [ ] **Step 3: Verify**

Run server, click Evolve in nav. Confirm: tabs render, clicking tabs switches, scope filters populate, Refresh button triggers API call (may fail if Codex not available — that's OK).

- [ ] **Step 4: Commit**

```bash
git add static/evolve.js static/app.js
git commit -m "feat: add Evolve core logic — tabs, caching, API integration"
```

---

### Task 3: Evolve page styles + skeleton loading + empty states

**Files:**
- Modify: `static/style.css` (append Evolve-specific styles)

- [ ] **Step 1: Add Evolve page styles to style.css**

Append to `static/style.css` (before the `@media` responsive block at line 1122):

```css
/* ---- Evolve Page ---- */
#evolve-view { padding: 24px 32px; overflow-y: auto; height: 100%; }
#evolve-header {
  display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px;
}
#evolve-header h3 { font-size: 22px; font-weight: 700; color: var(--text); margin: 0; }
.evolve-subtitle { font-size: 13px; color: var(--text-muted); margin-top: 2px; }
#evolve-overview-bar {
  display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
  padding: 12px 0; border-bottom: 1px solid var(--border-light); margin-bottom: 12px;
}
.evolve-stat-card {
  display: flex; align-items: center; gap: 6px; padding: 8px 14px;
  background: var(--bg-surface); border: 1px solid var(--border-light);
  border-radius: var(--radius-sm); cursor: pointer; transition: all 0.15s;
  font-size: 13px;
}
.evolve-stat-card:hover { border-color: var(--accent); }
.evolve-stat-card.active { border-color: var(--accent); background: var(--accent-dim); }
.evolve-stat-icon { font-size: 16px; }
.evolve-stat-count { font-weight: 700; color: var(--text); }
.evolve-stat-label { color: var(--text-muted); font-size: 11px; }
.evolve-last-scan { font-size: 11px; color: var(--text-muted); margin-left: auto; }

#evolve-scope { padding: 8px 0 12px; display: flex; flex-direction: column; gap: 6px; }

#evolve-tabs {
  display: flex; gap: 0; border-bottom: 2px solid var(--border-light); margin-bottom: 0;
}
.evolve-tab {
  padding: 10px 20px; font-size: 13px; font-weight: 500; color: var(--text-muted);
  background: none; border: none; cursor: pointer; border-bottom: 2px solid transparent;
  margin-bottom: -2px; transition: all 0.15s; font-family: inherit;
}
.evolve-tab:hover { color: var(--text); }
.evolve-tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }

#evolve-tab-content {
  background: var(--bg-surface); border: 1px solid var(--border-light);
  border-top: none; border-radius: 0 0 var(--radius) var(--radius);
  min-height: 400px;
}
#evolve-tab-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 16px; border-bottom: 1px solid var(--border-light);
  font-size: 11px; color: var(--text-muted);
}
#evolve-tab-body { padding: 20px; position: relative; }

.evolve-empty-state {
  text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 14px;
}

/* Skeleton loading */
.evolve-skeleton { padding: 20px; }
.skeleton-bar {
  height: 16px; background: linear-gradient(90deg, var(--bg-surface2) 25%, var(--bg-hover) 50%, var(--bg-surface2) 75%);
  background-size: 200% 100%; border-radius: 8px; margin-bottom: 12px;
  animation: skeleton-pulse 1.5s infinite;
}
.skeleton-bar.short { width: 60%; }
.skeleton-circle {
  width: 200px; height: 200px; border-radius: 50%; margin: 20px auto;
  background: linear-gradient(90deg, var(--bg-surface2) 25%, var(--bg-hover) 50%, var(--bg-surface2) 75%);
  background-size: 200% 100%; animation: skeleton-pulse 1.5s infinite;
}
@keyframes skeleton-pulse { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* Modal for message popup */
#msg-modal { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; }
.msg-modal-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,0.4); backdrop-filter: blur(4px); }
.msg-modal-content {
  position: relative; background: var(--bg-surface); border-radius: var(--radius);
  box-shadow: var(--shadow-md); width: 90%; max-width: 800px; max-height: 85vh;
  overflow-y: auto; padding: 24px;
}
.msg-modal-close {
  position: absolute; top: 12px; right: 12px; background: var(--bg-surface2);
  border: none; width: 28px; height: 28px; border-radius: 50%; cursor: pointer;
  font-size: 14px; display: flex; align-items: center; justify-content: center;
  transition: background 0.15s;
}
.msg-modal-close:hover { background: var(--bg-hover); }
.msg-modal-body { font-size: 14px; line-height: 1.7; }

/* Right panel message fold */
.chat-bubble.foldable { max-height: 300px; overflow: hidden; position: relative; }
.chat-bubble.foldable.folded::after {
  content: ""; position: absolute; bottom: 0; left: 0; right: 0; height: 60px;
  background: linear-gradient(transparent, var(--bg-surface));
}
.chat-fold-toggle {
  display: block; width: 100%; text-align: center; padding: 6px;
  font-size: 11px; color: var(--accent); cursor: pointer; background: none; border: none;
  border-top: 1px solid var(--border-light); font-family: inherit;
}
.chat-fold-toggle:hover { background: var(--accent-dim); }
.chat-msg-actions {
  position: absolute; top: 4px; right: 4px; display: flex; gap: 4px; opacity: 0; transition: opacity 0.15s;
}
.chat-msg:hover .chat-msg-actions { opacity: 1; }
.chat-msg-expand {
  background: var(--bg-surface2); border: 1px solid var(--border-light); border-radius: 4px;
  width: 22px; height: 22px; cursor: pointer; font-size: 11px;
  display: flex; align-items: center; justify-content: center;
}
.chat-msg-expand:hover { background: var(--bg-hover); }
```

- [ ] **Step 2: Verify**

Refresh browser. Evolve page should have proper styling: overview bar, tab underlines, skeleton animation visible when refreshing.

- [ ] **Step 3: Commit**

```bash
git add static/style.css
git commit -m "feat: add Evolve page styles, skeleton loading, modal overlay"
```

---

### Task 4: Profile tab — D3 radar chart + mind map

**Files:**
- Modify: `static/evolve.js` (replace `renderProfileTab` placeholder)

- [ ] **Step 1: Implement renderProfileTab with D3 radar chart and mind map**

In `static/evolve.js`, replace the `renderProfileTab` placeholder function with:

```javascript
function renderProfileTab(data, container) {
  if (data._parseError) {
    container.innerHTML = `<div class="evolve-raw-result">${window.renderMarkdownSimple ? renderMarkdownSimple(data._raw) : data._raw}</div>`;
    return;
  }
  container.innerHTML = "";
  const wrapper = document.createElement("div");
  wrapper.className = "evolve-profile-layout";
  container.appendChild(wrapper);

  // Left: Radar chart
  const radarSection = document.createElement("div");
  radarSection.className = "evolve-profile-radar";
  wrapper.appendChild(radarSection);
  if (data.radar?.dimensions?.length) {
    drawRadarChart(radarSection, data.radar.dimensions);
  }

  // Right: Mind map
  const mindSection = document.createElement("div");
  mindSection.className = "evolve-profile-mind";
  wrapper.appendChild(mindSection);
  if (data.mindmap) {
    drawMindMap(mindSection, data.mindmap);
  }

  // Bottom: Profile cards
  if (data.cards?.length) {
    const cardsRow = document.createElement("div");
    cardsRow.className = "evolve-profile-cards";
    container.appendChild(cardsRow);
    data.cards.forEach(card => {
      const div = document.createElement("div");
      div.className = "evolve-card";
      div.innerHTML = `<div class="evolve-card-title">${esc(card.category)}</div>
        <div class="evolve-card-tags">${card.items.map(i => `<span class="evolve-tag">${esc(i)}</span>`).join("")}</div>`;
      cardsRow.appendChild(div);
    });
  }
}

function drawRadarChart(container, dimensions) {
  const width = 300, height = 300, margin = 50;
  const radius = Math.min(width, height) / 2 - margin;
  const levels = 5;
  const n = dimensions.length;
  const angleSlice = (Math.PI * 2) / n;

  const svg = d3.select(container).append("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .append("g")
    .attr("transform", `translate(${width / 2},${height / 2})`);

  // Draw grid
  for (let level = 1; level <= levels; level++) {
    const r = (radius / levels) * level;
    const points = d3.range(n).map(i => {
      const angle = angleSlice * i - Math.PI / 2;
      return [r * Math.cos(angle), r * Math.sin(angle)];
    });
    svg.append("polygon")
      .attr("points", points.map(p => p.join(",")).join(" "))
      .style("fill", "none")
      .style("stroke", "var(--border-light)")
      .style("stroke-width", "1");
  }

  // Draw axes
  dimensions.forEach((d, i) => {
    const angle = angleSlice * i - Math.PI / 2;
    const x = radius * Math.cos(angle);
    const y = radius * Math.sin(angle);
    svg.append("line")
      .attr("x1", 0).attr("y1", 0).attr("x2", x).attr("y2", y)
      .style("stroke", "var(--border-light)").style("stroke-width", "1");
    // Label
    const lx = (radius + 20) * Math.cos(angle);
    const ly = (radius + 20) * Math.sin(angle);
    svg.append("text")
      .attr("x", lx).attr("y", ly)
      .attr("text-anchor", "middle").attr("dominant-baseline", "middle")
      .style("font-size", "10px").style("fill", "var(--text-secondary)")
      .text(d.name);
  });

  // Draw data polygon
  const dataPoints = dimensions.map((d, i) => {
    const angle = angleSlice * i - Math.PI / 2;
    const r = radius * (d.score || 0);
    return [r * Math.cos(angle), r * Math.sin(angle)];
  });

  svg.append("polygon")
    .attr("points", dataPoints.map(p => p.join(",")).join(" "))
    .style("fill", "var(--accent)")
    .style("fill-opacity", "0.15")
    .style("stroke", "var(--accent)")
    .style("stroke-width", "2");

  // Draw data points
  dataPoints.forEach((p, i) => {
    const conf = dimensions[i].confidence;
    svg.append("circle")
      .attr("cx", p[0]).attr("cy", p[1]).attr("r", 4)
      .style("fill", conf === "high" ? "var(--accent)" : conf === "medium" ? "var(--accent-light)" : "var(--border)")
      .style("stroke", "white").style("stroke-width", "1.5");
  });
}

function drawMindMap(container, mindmapData) {
  const width = 400, height = 300;
  // Convert to D3 hierarchy
  const root = {
    name: mindmapData.center || "User",
    children: (mindmapData.branches || []).map(b => ({
      name: b.label,
      children: (b.children || []).map(c => ({ name: c }))
    }))
  };

  const svg = d3.select(container).append("svg")
    .attr("viewBox", `0 0 ${width} ${height}`);

  const g = svg.append("g").attr("transform", `translate(${width / 2},${height / 2})`);

  const hierarchy = d3.hierarchy(root);
  const treeLayout = d3.tree().size([2 * Math.PI, Math.min(width, height) / 2 - 40]);
  treeLayout(hierarchy);

  // Links
  g.selectAll(".mind-link")
    .data(hierarchy.links())
    .enter().append("path")
    .attr("class", "mind-link")
    .attr("d", d3.linkRadial().angle(d => d.x).radius(d => d.y))
    .style("fill", "none")
    .style("stroke", "var(--border)")
    .style("stroke-width", "1.5")
    .style("opacity", 0)
    .transition().duration(400).style("opacity", 1);

  // Nodes
  const nodes = g.selectAll(".mind-node")
    .data(hierarchy.descendants())
    .enter().append("g")
    .attr("transform", d => `rotate(${d.x * 180 / Math.PI - 90}) translate(${d.y},0)`);

  nodes.append("circle")
    .attr("r", d => d.depth === 0 ? 8 : d.children ? 5 : 3)
    .style("fill", d => d.depth === 0 ? "var(--accent)" : d.children ? "var(--accent-light)" : "var(--bg-active)")
    .style("stroke", d => d.depth === 0 ? "var(--accent)" : "var(--border)")
    .style("stroke-width", "1.5");

  nodes.append("text")
    .attr("dy", "0.31em")
    .attr("x", d => d.x < Math.PI === !d.children ? 8 : -8)
    .attr("text-anchor", d => d.x < Math.PI === !d.children ? "start" : "end")
    .attr("transform", d => d.x >= Math.PI ? "rotate(180)" : null)
    .style("font-size", d => d.depth === 0 ? "12px" : "10px")
    .style("fill", "var(--text-secondary)")
    .text(d => d.data.name);
}
```

- [ ] **Step 2: Add Profile layout CSS**

Append to `static/style.css` (within the Evolve section):

```css
/* Evolve — Profile tab */
.evolve-profile-layout { display: flex; gap: 24px; flex-wrap: wrap; }
.evolve-profile-radar, .evolve-profile-mind { flex: 1; min-width: 280px; }
.evolve-profile-cards { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
.evolve-card {
  background: var(--bg-surface2); border-radius: var(--radius-sm);
  padding: 14px; flex: 1; min-width: 200px; border: 1px solid var(--border-light);
}
.evolve-card-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; }
.evolve-card-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.evolve-tag {
  font-size: 11px; padding: 3px 8px; border-radius: 10px;
  background: var(--accent-dim); color: var(--accent); font-weight: 500;
}
.evolve-raw-result { padding: 16px; font-size: 13px; line-height: 1.6; }
```

- [ ] **Step 3: Verify**

In browser, go to Evolve → Profile tab → click Refresh. If Codex returns valid JSON, radar chart and mind map should render. If parse fails, raw text fallback shows.

- [ ] **Step 4: Commit**

```bash
git add static/evolve.js static/style.css
git commit -m "feat: add Profile tab — D3 radar chart + radial mind map"
```

---

### Task 5: Memory tab — D3 force-directed knowledge graph

**Files:**
- Modify: `static/evolve.js` (replace `renderMemoryTab` placeholder)
- Modify: `static/style.css` (add Memory tab styles)

- [ ] **Step 1: Implement renderMemoryTab**

In `static/evolve.js`, replace the `renderMemoryTab` placeholder:

```javascript
function renderMemoryTab(data, container) {
  if (data._parseError) {
    container.innerHTML = `<div class="evolve-raw-result">${window.renderMarkdownSimple ? renderMarkdownSimple(data._raw) : data._raw}</div>`;
    return;
  }
  container.innerHTML = "";
  const wrapper = document.createElement("div");
  wrapper.className = "evolve-memory-layout";
  container.appendChild(wrapper);

  // Left: Force graph
  const graphDiv = document.createElement("div");
  graphDiv.className = "evolve-memory-graph";
  wrapper.appendChild(graphDiv);

  // Right: Card list
  const listDiv = document.createElement("div");
  listDiv.className = "evolve-memory-list";
  wrapper.appendChild(listDiv);

  if (data.cards?.length) {
    data.cards.forEach(card => {
      const div = document.createElement("div");
      div.className = "evolve-memory-card";
      div.dataset.id = card.id;
      const typeColors = { preference: "var(--accent)", workflow: "var(--bash-accent)", tooling: "var(--read-accent)", design: "var(--edit-accent)", communication: "var(--grep-accent)" };
      const node = (data.nodes || []).find(n => n.id === card.id);
      const type = node?.type || "preference";
      const conf = node?.confidence || "medium";
      div.innerHTML = `<div class="memory-card-header">
          <span class="memory-type-dot" style="background:${typeColors[type] || "var(--accent)"}"></span>
          <span class="memory-card-label">${esc(card.content || card.id)}</span>
          <span class="memory-confidence ${conf}">${conf}</span>
        </div>
        <div class="memory-card-meta">
          ${card.firstSeen ? `<span>First: ${card.firstSeen}</span>` : ""}
          ${card.lastSeen ? `<span>Last: ${card.lastSeen}</span>` : ""}
        </div>
        ${card.evidence ? `<div class="memory-card-evidence">"${esc(card.evidence)}"</div>` : ""}`;
      listDiv.appendChild(div);
    });
  }

  if (data.nodes?.length) {
    drawForceGraph(graphDiv, data.nodes, data.links || [], (nodeId) => {
      // Highlight corresponding card
      listDiv.querySelectorAll(".evolve-memory-card").forEach(c => {
        c.classList.toggle("highlighted", c.dataset.id === nodeId);
      });
      const target = listDiv.querySelector(`.evolve-memory-card[data-id="${nodeId}"]`);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }
}

function drawForceGraph(container, nodes, links, onNodeClick) {
  const width = 450, height = 350;
  const typeColors = { preference: "#5856d6", workflow: "#16a34a", tooling: "#d97706", design: "#ea580c", communication: "#2563eb" };

  const svg = d3.select(container).append("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .style("width", "100%");

  const simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(60).strength(d => d.strength || 0.3))
    .force("charge", d3.forceManyBody().strength(-80))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide().radius(d => Math.sqrt(d.frequency || 1) * 5 + 8));

  const link = svg.append("g").selectAll("line")
    .data(links).enter().append("line")
    .style("stroke", "var(--border-light)").style("stroke-width", d => (d.strength || 0.5) * 2);

  const node = svg.append("g").selectAll("g")
    .data(nodes).enter().append("g")
    .style("cursor", "pointer")
    .on("click", (e, d) => { if (onNodeClick) onNodeClick(d.id); })
    .call(d3.drag()
      .on("start", (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on("end", (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  node.append("circle")
    .attr("r", d => Math.sqrt(d.frequency || 1) * 4 + 4)
    .style("fill", d => typeColors[d.type] || "#5856d6")
    .style("fill-opacity", d => d.confidence === "high" ? 0.9 : d.confidence === "medium" ? 0.6 : 0.3)
    .style("stroke", d => typeColors[d.type] || "#5856d6")
    .style("stroke-width", d => d.confidence === "low" ? "1" : "2")
    .style("stroke-dasharray", d => d.confidence === "low" ? "3,2" : "none");

  node.append("text")
    .text(d => d.label?.length > 15 ? d.label.substring(0, 15) + "…" : d.label)
    .attr("dy", d => -(Math.sqrt(d.frequency || 1) * 4 + 8))
    .attr("text-anchor", "middle")
    .style("font-size", "9px").style("fill", "var(--text-muted)");

  simulation.on("tick", () => {
    link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    node.attr("transform", d => `translate(${d.x},${d.y})`);
  });
}
```

- [ ] **Step 2: Add Memory tab CSS**

Append to style.css:

```css
/* Evolve — Memory tab */
.evolve-memory-layout { display: flex; gap: 20px; min-height: 350px; }
.evolve-memory-graph { flex: 1.2; min-width: 300px; }
.evolve-memory-list { flex: 1; max-height: 500px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
.evolve-memory-card {
  padding: 10px 12px; border: 1px solid var(--border-light); border-radius: var(--radius-sm);
  background: var(--bg-surface); transition: all 0.15s; font-size: 12px;
}
.evolve-memory-card.highlighted { border-color: var(--accent); background: var(--accent-dim); }
.memory-card-header { display: flex; align-items: center; gap: 6px; }
.memory-type-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.memory-card-label { flex: 1; font-weight: 500; color: var(--text); }
.memory-confidence { font-size: 10px; padding: 1px 6px; border-radius: 8px; }
.memory-confidence.high { background: #dcfce7; color: #16a34a; }
.memory-confidence.medium { background: #fef9c3; color: #ca8a04; }
.memory-confidence.low { background: var(--bg-surface2); color: var(--text-muted); }
.memory-card-meta { font-size: 10px; color: var(--text-muted); margin-top: 4px; display: flex; gap: 8px; }
.memory-card-evidence { font-size: 11px; color: var(--text-secondary); margin-top: 4px; font-style: italic; border-left: 2px solid var(--border); padding-left: 8px; }
```

- [ ] **Step 3: Verify and commit**

```bash
git add static/evolve.js static/style.css
git commit -m "feat: add Memory tab — D3 force-directed knowledge graph"
```

---

### Task 6: Rules tab — priority card wall

**Files:**
- Modify: `static/evolve.js` (replace `renderRulesTab`)
- Modify: `static/style.css`

- [ ] **Step 1: Implement renderRulesTab**

Replace the placeholder in `static/evolve.js`:

```javascript
function renderRulesTab(data, container) {
  if (data._parseError) {
    container.innerHTML = `<div class="evolve-raw-result">${window.renderMarkdownSimple ? renderMarkdownSimple(data._raw) : data._raw}</div>`;
    return;
  }
  container.innerHTML = "";
  const rules = data.rules || [];
  if (!rules.length) { container.innerHTML = '<div class="evolve-empty-state"><p>暂无规则建议</p></div>'; return; }

  // Category filter
  const categories = [...new Set(rules.map(r => r.category))];
  const filterBar = document.createElement("div");
  filterBar.className = "rules-filter-bar";
  let activeFilter = "all";
  function renderFilter() {
    filterBar.innerHTML = "";
    [{ key: "all", label: "All" }, ...categories.map(c => ({ key: c, label: c }))].forEach(f => {
      const btn = document.createElement("button");
      btn.className = `scope-tab${f.key === activeFilter ? " active" : ""}`;
      btn.textContent = f.label;
      btn.onclick = () => { activeFilter = f.key; renderFilter(); renderCards(); };
      filterBar.appendChild(btn);
    });
  }
  container.appendChild(filterBar);

  const cardsContainer = document.createElement("div");
  cardsContainer.className = "rules-card-list";
  container.appendChild(cardsContainer);

  function renderCards() {
    cardsContainer.innerHTML = "";
    const filtered = activeFilter === "all" ? rules : rules.filter(r => r.category === activeFilter);
    filtered.sort((a, b) => {
      const prio = { P0: 0, P1: 1, P2: 2 };
      return (prio[a.priority] ?? 9) - (prio[b.priority] ?? 9);
    });
    filtered.forEach(rule => {
      const card = document.createElement("div");
      card.className = `rule-card priority-${(rule.priority || "P2").toLowerCase()}`;
      const evidenceHtml = (rule.evidence || []).map(e =>
        `<div class="rule-evidence-item"><span class="rule-quote">"${esc(e.quote)}"</span>${e.session ? ` <a class="rule-session-link" href="#${e.session}">→ session</a>` : ""}</div>`
      ).join("");
      card.innerHTML = `<div class="rule-card-header">
          <span class="rule-priority-badge">${esc(rule.priority || "P2")}</span>
          <span class="rule-category">${esc(rule.category || "")}</span>
          ${rule.frequency ? `<span class="rule-freq">${rule.frequency}x</span>` : ""}
        </div>
        <div class="rule-text">${esc(rule.rule)}</div>
        ${rule.why ? `<div class="rule-why"><strong>Why:</strong> ${esc(rule.why)}</div>` : ""}
        <div class="rule-examples">
          ${rule.positive ? `<div class="rule-example good">✓ ${esc(rule.positive)}</div>` : ""}
          ${rule.negative ? `<div class="rule-example bad">✗ ${esc(rule.negative)}</div>` : ""}
        </div>
        ${evidenceHtml ? `<details class="rule-evidence"><summary>Evidence (${rule.evidence.length})</summary>${evidenceHtml}</details>` : ""}`;
      cardsContainer.appendChild(card);
    });
  }
  renderFilter();
  renderCards();
}
```

- [ ] **Step 2: Add Rules CSS**

```css
/* Evolve — Rules tab */
.rules-filter-bar { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
.rules-card-list { display: flex; flex-direction: column; gap: 12px; }
.rule-card {
  border-radius: var(--radius-sm); padding: 14px; background: var(--bg-surface);
  border: 1px solid var(--border-light); border-left: 4px solid;
}
.rule-card.priority-p0 { border-left-color: #dc2626; }
.rule-card.priority-p1 { border-left-color: #f59e0b; }
.rule-card.priority-p2 { border-left-color: #3b82f6; }
.rule-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.rule-priority-badge {
  font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; color: white;
}
.priority-p0 .rule-priority-badge { background: #dc2626; }
.priority-p1 .rule-priority-badge { background: #f59e0b; }
.priority-p2 .rule-priority-badge { background: #3b82f6; }
.rule-category { font-size: 11px; color: var(--text-muted); }
.rule-freq { font-size: 10px; color: var(--text-muted); margin-left: auto; }
.rule-text { font-size: 14px; font-weight: 500; color: var(--text); margin-bottom: 6px; }
.rule-why { font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; }
.rule-examples { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
.rule-example { font-size: 12px; padding: 4px 8px; border-radius: 4px; }
.rule-example.good { background: #f0fdf4; color: #16a34a; }
.rule-example.bad { background: #fef2f2; color: #dc2626; }
.rule-evidence { font-size: 11px; color: var(--text-muted); }
.rule-evidence summary { cursor: pointer; padding: 4px 0; }
.rule-evidence-item { padding: 4px 0; border-top: 1px solid var(--border-light); }
.rule-quote { font-style: italic; }
.rule-session-link { color: var(--accent); text-decoration: none; font-size: 10px; }
```

- [ ] **Step 3: Verify and commit**

```bash
git add static/evolve.js static/style.css
git commit -m "feat: add Rules tab — priority card wall with evidence"
```

---

### Task 7: Signals tab — D3 timeline + correction events

**Files:**
- Modify: `static/evolve.js` (replace `renderSignalsTab`)
- Modify: `static/style.css`

- [ ] **Step 1: Implement renderSignalsTab**

Replace placeholder in `static/evolve.js`:

```javascript
function renderSignalsTab(data, container) {
  if (data._parseError) {
    container.innerHTML = `<div class="evolve-raw-result">${window.renderMarkdownSimple ? renderMarkdownSimple(data._raw) : data._raw}</div>`;
    return;
  }
  container.innerHTML = "";

  // Timeline chart
  if (data.timeline?.length) {
    const chartDiv = document.createElement("div");
    chartDiv.className = "signals-chart";
    container.appendChild(chartDiv);
    drawSignalsTimeline(chartDiv, data.timeline);
  }

  // Event list
  const events = data.events || [];
  if (events.length) {
    const listDiv = document.createElement("div");
    listDiv.className = "signals-event-list";
    container.appendChild(listDiv);

    const typeColors = { style: "#5856d6", scope: "#f59e0b", accuracy: "#dc2626", workflow: "#16a34a", overengineering: "#ea580c" };
    events.forEach(ev => {
      const div = document.createElement("div");
      div.className = "signal-event";
      div.innerHTML = `<div class="signal-event-dot" style="background:${typeColors[ev.type] || "#888"}"></div>
        <div class="signal-event-body">
          <div class="signal-event-header">
            <span class="signal-type-badge" style="background:${typeColors[ev.type] || "#888"}">${esc(ev.type)}</span>
            <span class="signal-date">${esc(ev.date || "")}</span>
            ${ev.session ? `<a class="rule-session-link" href="#${ev.session}">→ session</a>` : ""}
          </div>
          <div class="signal-quote">"${esc(ev.userQuote || "")}"</div>
          ${ev.aiIssue ? `<div class="signal-issue">AI issue: ${esc(ev.aiIssue)}</div>` : ""}
          ${ev.correction ? `<div class="signal-fix">Fix: ${esc(ev.correction)}</div>` : ""}
          ${ev.linkedRule ? `<span class="signal-linked-rule">→ Rule ${esc(ev.linkedRule)}</span>` : ""}
        </div>`;
      listDiv.appendChild(div);
    });
  }

  if (!data.timeline?.length && !events.length) {
    container.innerHTML = '<div class="evolve-empty-state"><p>暂无纠正记录</p></div>';
  }
}

function drawSignalsTimeline(container, timeline) {
  const margin = { top: 20, right: 20, bottom: 30, left: 40 };
  const width = 700 - margin.left - margin.right;
  const height = 180 - margin.top - margin.bottom;
  const types = ["style", "scope", "accuracy", "workflow"];
  const typeColors = { style: "#5856d6", scope: "#f59e0b", accuracy: "#dc2626", workflow: "#16a34a" };

  // Stack data
  const stackData = timeline.map(d => {
    const obj = { date: d.date };
    types.forEach(t => { obj[t] = d.counts?.[t] || 0; });
    return obj;
  });

  const svg = d3.select(container).append("svg")
    .attr("viewBox", `0 0 ${width + margin.left + margin.right} ${height + margin.top + margin.bottom}`)
    .append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand().domain(stackData.map(d => d.date)).range([0, width]).padding(0.2);
  const stack = d3.stack().keys(types);
  const series = stack(stackData);
  const yMax = d3.max(series, s => d3.max(s, d => d[1])) || 5;
  const y = d3.scaleLinear().domain([0, yMax]).range([height, 0]);

  // Bars
  svg.selectAll("g.series")
    .data(series).enter().append("g")
    .attr("fill", (d, i) => typeColors[types[i]])
    .attr("fill-opacity", 0.7)
    .selectAll("rect")
    .data(d => d).enter().append("rect")
    .attr("x", d => x(d.data.date))
    .attr("width", x.bandwidth())
    .attr("y", height)
    .attr("height", 0)
    .transition().duration(400)
    .attr("y", d => y(d[1]))
    .attr("height", d => y(d[0]) - y(d[1]));

  // Axes
  svg.append("g").attr("transform", `translate(0,${height})`).call(d3.axisBottom(x).tickFormat(d => d.slice(5)))
    .selectAll("text").style("font-size", "9px");
  svg.append("g").call(d3.axisLeft(y).ticks(4)).selectAll("text").style("font-size", "9px");

  // Legend
  const legend = svg.append("g").attr("transform", `translate(${width - 200},-10)`);
  types.forEach((t, i) => {
    legend.append("rect").attr("x", i * 55).attr("width", 10).attr("height", 10).attr("rx", 2).attr("fill", typeColors[t]);
    legend.append("text").attr("x", i * 55 + 14).attr("y", 9).text(t).style("font-size", "9px").style("fill", "var(--text-muted)");
  });
}
```

- [ ] **Step 2: Add Signals CSS**

```css
/* Evolve — Signals tab */
.signals-chart { margin-bottom: 20px; }
.signals-event-list { display: flex; flex-direction: column; gap: 0; }
.signal-event {
  display: flex; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border-light);
  position: relative;
}
.signal-event-dot {
  width: 10px; height: 10px; border-radius: 50%; margin-top: 4px; flex-shrink: 0;
}
.signal-event::before {
  content: ""; position: absolute; left: 4px; top: 16px; bottom: -1px;
  width: 2px; background: var(--border-light);
}
.signal-event:last-child::before { display: none; }
.signal-event-body { flex: 1; }
.signal-event-header { display: flex; gap: 8px; align-items: center; margin-bottom: 4px; }
.signal-type-badge {
  font-size: 10px; color: white; padding: 1px 6px; border-radius: 4px; font-weight: 500;
}
.signal-date { font-size: 10px; color: var(--text-muted); }
.signal-quote { font-size: 13px; font-style: italic; color: var(--text); margin-bottom: 4px; }
.signal-issue, .signal-fix { font-size: 11px; color: var(--text-secondary); }
.signal-fix { color: var(--bash-accent); }
.signal-linked-rule { font-size: 10px; color: var(--accent); }
```

- [ ] **Step 3: Verify and commit**

```bash
git add static/evolve.js static/style.css
git commit -m "feat: add Signals tab — stacked bar timeline + event list"
```

---

### Task 8: Patterns tab — D3 bubble cluster

**Files:**
- Modify: `static/evolve.js` (replace `renderPatternsTab`)
- Modify: `static/style.css`

- [ ] **Step 1: Implement renderPatternsTab**

Replace placeholder in `static/evolve.js`:

```javascript
function renderPatternsTab(data, container) {
  if (data._parseError) {
    container.innerHTML = `<div class="evolve-raw-result">${window.renderMarkdownSimple ? renderMarkdownSimple(data._raw) : data._raw}</div>`;
    return;
  }
  container.innerHTML = "";
  const wrapper = document.createElement("div");
  wrapper.className = "evolve-patterns-layout";
  container.appendChild(wrapper);

  // Left: Bubble chart
  const bubbleDiv = document.createElement("div");
  bubbleDiv.className = "patterns-bubble-chart";
  wrapper.appendChild(bubbleDiv);

  // Right: Cards
  const cardsDiv = document.createElement("div");
  cardsDiv.className = "patterns-card-list";
  wrapper.appendChild(cardsDiv);

  const bubbles = data.bubbles || [];
  const cards = data.cards || [];

  if (bubbles.length) {
    drawBubbleCluster(bubbleDiv, bubbles);
  }

  if (cards.length) {
    cards.sort((a, b) => (b.frequency || 0) - (a.frequency || 0));
    cards.forEach(card => {
      const trendIcon = card.trend === "decreasing" ? "📉" : card.trend === "increasing" ? "📈" : "➡️";
      const typeColors = { error: "#dc2626", efficiency: "#f59e0b", knowledge_gap: "#3b82f6", workflow: "#16a34a" };
      const bubble = bubbles.find(b => b.id === card.id);
      const type = bubble?.type || "workflow";
      const div = document.createElement("div");
      div.className = "pattern-card";
      div.innerHTML = `<div class="pattern-card-header">
          <span class="pattern-type-dot" style="background:${typeColors[type] || "#888"}"></span>
          <span class="pattern-freq">${card.frequency || 0}x</span>
          <span class="pattern-trend">${trendIcon} ${esc(card.trend || "stable")}</span>
        </div>
        <div class="pattern-desc">${esc(card.description || card.id)}</div>
        ${card.cost ? `<div class="pattern-cost">Cost: ${esc(card.cost)}</div>` : ""}
        ${card.suggestion ? `<div class="pattern-suggestion">💡 ${esc(card.suggestion)}</div>` : ""}`;
      cardsDiv.appendChild(div);
    });
  }

  if (!bubbles.length && !cards.length) {
    container.innerHTML = '<div class="evolve-empty-state"><p>暂无重复模式</p></div>';
  }
}

function drawBubbleCluster(container, bubbles) {
  const width = 400, height = 350;
  const typeColors = { error: "#dc2626", efficiency: "#f59e0b", knowledge_gap: "#3b82f6", workflow: "#16a34a" };

  const packData = { children: bubbles.map(b => ({ ...b, value: b.frequency || 1 })) };
  const root = d3.hierarchy(packData).sum(d => d.value);
  d3.pack().size([width - 20, height - 20]).padding(6)(root);

  const svg = d3.select(container).append("svg")
    .attr("viewBox", `0 0 ${width} ${height}`);

  const leaf = svg.selectAll("g")
    .data(root.leaves()).enter().append("g")
    .attr("transform", d => `translate(${d.x + 10},${d.y + 10})`);

  leaf.append("circle")
    .attr("r", 0)
    .style("fill", d => typeColors[d.data.type] || "#888")
    .style("fill-opacity", 0.2)
    .style("stroke", d => typeColors[d.data.type] || "#888")
    .style("stroke-width", 1.5)
    .transition().duration(500)
    .attr("r", d => d.r);

  leaf.append("text")
    .attr("text-anchor", "middle")
    .attr("dy", "0.3em")
    .style("font-size", d => Math.max(8, Math.min(d.r / 3, 12)) + "px")
    .style("fill", "var(--text-secondary)")
    .text(d => {
      const label = d.data.label || "";
      return label.length > d.r / 3 ? label.substring(0, Math.floor(d.r / 3)) + "…" : label;
    });
}
```

- [ ] **Step 2: Add Patterns CSS**

```css
/* Evolve — Patterns tab */
.evolve-patterns-layout { display: flex; gap: 20px; min-height: 350px; }
.patterns-bubble-chart { flex: 1.2; min-width: 300px; }
.patterns-card-list { flex: 1; max-height: 500px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
.pattern-card {
  padding: 10px 12px; border: 1px solid var(--border-light); border-radius: var(--radius-sm);
  background: var(--bg-surface); font-size: 12px;
}
.pattern-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.pattern-type-dot { width: 8px; height: 8px; border-radius: 50%; }
.pattern-freq { font-weight: 700; color: var(--text); }
.pattern-trend { font-size: 10px; color: var(--text-muted); margin-left: auto; }
.pattern-desc { font-size: 13px; color: var(--text); margin-bottom: 4px; }
.pattern-cost { font-size: 11px; color: var(--text-muted); }
.pattern-suggestion { font-size: 11px; color: var(--accent); margin-top: 4px; }
```

- [ ] **Step 3: Verify and commit**

```bash
git add static/evolve.js static/style.css
git commit -m "feat: add Patterns tab — D3 bubble cluster + pattern cards"
```

---

### Task 9: AI Analysis linkage — auto-redirect to Evolve

**Files:**
- Modify: `static/app.js` (modify `submitGlobalAi` and `appendChatMsg`)

- [ ] **Step 1: Add redirect logic in submitGlobalAi**

In `static/app.js`, find the `submitGlobalAi` function (line ~2053). In the `.then(data => { ... })` callback (around line 2087), after `saveChatToStorage()`, add Evolve redirect detection:

```javascript
// Check if this was an Evolve-related analysis
const evolveTabMap = {
  "规则生成": "rules", "规则提炼": "rules", "Rule": "rules",
  "知识沉淀": "memory", "Memory": "memory", "偏好": "memory",
  "用户画像": "profile", "Profile": "profile",
  "纠正": "signals", "Correction": "signals",
  "重复模式": "patterns", "Pattern": "patterns", "效率分析": "patterns"
};
let targetTab = null;
for (const [keyword, tab] of Object.entries(evolveTabMap)) {
  if (text.includes(keyword)) { targetTab = tab; break; }
}
if (targetTab && !data.error) {
  // Try to parse as Evolve data
  const parsed = window.parseEvolveResponseExternal ? window.parseEvolveResponseExternal(targetTab, reply) : null;
  if (parsed && !parsed._parseError) {
    // Show summary instead of full reply
    const itemCount = Object.values(parsed).reduce((sum, v) => sum + (Array.isArray(v) ? v.length : 0), 0);
    const summaryText = `✅ 分析完成：发现 ${itemCount} 条结果。3 秒后跳转到 Evolve → ${targetTab}`;
    // Replace the last message with summary
    const lastBubble = container.querySelector(".chat-msg:last-child .chat-bubble");
    if (lastBubble) lastBubble.innerHTML = esc(summaryText);
    // Auto redirect after 3s
    setTimeout(() => {
      if (window.navigateToEvolveTab) window.navigateToEvolveTab(targetTab, parsed);
      // Switch to Evolve view
      document.querySelectorAll(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.view === "evolve"));
      showView("evolve");
      if (window.initEvolveView) window.initEvolveView();
    }, 3000);
  }
}
```

- [ ] **Step 2: Expose parseEvolveResponse in evolve.js**

In `static/evolve.js`, add to the public API section at the bottom:

```javascript
window.parseEvolveResponseExternal = function (tab, raw) {
  return parseEvolveResponse(tab, raw);
};
```

- [ ] **Step 3: Verify**

In AI Analysis, click "规则生成" preset. After analysis completes, chat should show a summary and auto-redirect to Evolve → Rules tab after 3 seconds.

- [ ] **Step 4: Commit**

```bash
git add static/app.js static/evolve.js
git commit -m "feat: link AI Analysis presets to Evolve with auto-redirect"
```

---

### Task 10: Right panel fold/expand + modal popup

**Files:**
- Modify: `static/app.js` (modify `appendChatMsg`, add modal logic)

- [ ] **Step 1: Add fold and modal to appendChatMsg**

In `static/app.js`, replace the `appendChatMsg` function (line ~1782):

```javascript
function appendChatMsg(container, role, content) {
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.style.position = "relative";
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.innerHTML = role === "assistant" ? renderMarkdownSimple(content) : esc(content).replace(/\n/g, "<br>");
  div.appendChild(bubble);

  if (role === "assistant") {
    // Actions bar (expand button)
    const actions = document.createElement("div");
    actions.className = "chat-msg-actions";
    const expandBtn = document.createElement("button");
    expandBtn.className = "chat-msg-expand";
    expandBtn.textContent = "⤢";
    expandBtn.title = "Full screen";
    expandBtn.onclick = (e) => {
      e.stopPropagation();
      openMsgModal(content);
    };
    actions.appendChild(expandBtn);
    div.appendChild(actions);

    // Check after render if content is long enough to fold
    requestAnimationFrame(() => {
      if (bubble.scrollHeight > 300) {
        bubble.classList.add("foldable", "folded");
        bubble.style.maxHeight = "300px";
        const toggle = document.createElement("button");
        toggle.className = "chat-fold-toggle";
        toggle.textContent = "展开全文 ↓";
        toggle.onclick = () => {
          const isFolded = bubble.classList.contains("folded");
          bubble.classList.toggle("folded", !isFolded);
          bubble.style.maxHeight = isFolded ? "none" : "300px";
          toggle.textContent = isFolded ? "收起 ↑" : "展开全文 ↓";
        };
        div.appendChild(toggle);
      }
    });
  }

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function openMsgModal(content) {
  const modal = document.getElementById("msg-modal");
  if (!modal) return;
  const body = modal.querySelector(".msg-modal-body");
  if (body) body.innerHTML = renderMarkdownSimple(content);
  modal.classList.remove("hidden");
  // Close handlers
  const close = modal.querySelector(".msg-modal-close");
  const backdrop = modal.querySelector(".msg-modal-backdrop");
  function closeModal() { modal.classList.add("hidden"); }
  if (close) close.onclick = closeModal;
  if (backdrop) backdrop.onclick = closeModal;
  document.addEventListener("keydown", function escHandler(e) {
    if (e.key === "Escape") { closeModal(); document.removeEventListener("keydown", escHandler); }
  });
}
```

- [ ] **Step 2: Verify**

Open a session → AI tab → ask a question that generates a long reply. Confirm:
1. Long replies auto-fold with "展开全文 ↓" button
2. Hover shows ⤢ expand button
3. Clicking ⤢ opens a centered modal with full content
4. Modal closes on ✕, backdrop click, or Escape

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat: add right panel message fold/expand + fullscreen modal"
```

---

### Task 11: Final integration + polish

**Files:**
- Modify: `static/app.js` (welcome card for Evolve)
- Modify: `static/index.html` (add Evolve welcome card)

- [ ] **Step 1: Add Evolve to welcome screen**

In `static/index.html`, add a welcome card inside `.welcome-cards` (after the Project Health card around line 128):

```html
<button class="welcome-card" data-action="evolve">
  <span class="wc-icon">🧬</span>
  <span class="wc-title">Evolve</span>
  <span class="wc-desc">AI self-evolution from conversations</span>
</button>
```

- [ ] **Step 2: Wire welcome card click in app.js**

In `static/app.js`, in the welcome card click handler (around line 157), add:

```javascript
else if (action === "evolve") { switchSidebarPanel("sessions"); showView("evolve"); if (window.initEvolveView) window.initEvolveView(); }
```

And highlight the correct nav item when switching to Evolve:

```javascript
// In the evolve nav click handler, ensure nav highlight
document.querySelectorAll(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.view === "evolve"));
```

- [ ] **Step 3: Full smoke test**

1. Open `http://localhost:8080` — Evolve welcome card visible
2. Click Evolve card → Evolve page renders with 5 tabs
3. Click each tab → empty state or cached data shows
4. Click Refresh on Profile tab → skeleton loading → AI result renders (or raw fallback)
5. Go to AI Analysis → click "规则生成" → chat shows summary → 3s auto-redirect to Evolve Rules
6. Open a session → AI tab → send a long question → reply folds with toggle + expand modal works
7. Close modal with Esc/backdrop/✕

- [ ] **Step 4: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat: add Evolve welcome card + final integration"
```
