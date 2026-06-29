/**
 * Session list rendering — sidebar sessions, projects, filters.
 *
 * Usage:
 *   import { renderSessions, renderProjects, ... } from './sessions.js';
 */

import { state } from './state.js';
import { $, dom } from './dom.js';
import { esc, formatDate } from './utils.js';

// i18n helper: fall back to the live global if module import order differs.
const _t = (k, v) => (window.t ? window.t(k, v) : k);

// ── Late-bound references to functions in other modules ──────────
// These are set by the main module via registerSessionDeps() to avoid
// circular imports.  Inside this file, call e.g. _deps.showView("sessions").
let _deps = {
  showView: () => {},
  switchSidebarPanel: () => {},
  loadSession: () => {},
};

export function registerSessionDeps(deps) {
  Object.assign(_deps, deps);
}

// ── Welcome Stats ────────────────────────────────────────────────
export function updateWelcomeStats(sessions, projects) {
  const container = $("#welcome-stats");
  if (!container) return;
  const projCount = projects ? projects.length : 0;
  const now = new Date();
  const weekAgo = new Date(now - 7 * 86400000);
  const recentCount = sessions.filter(s => s.date && new Date(s.date) >= weekAgo).length;
  container.innerHTML = `
    <div class="welcome-stat"><span class="welcome-stat-num">${sessions.length}</span><span class="welcome-stat-label">${_t("welcome.stat.sessions")}</span></div>
    <div class="welcome-stat"><span class="welcome-stat-num">${projCount}</span><span class="welcome-stat-label">${_t("welcome.stat.projects")}</span></div>
    <div class="welcome-stat"><span class="welcome-stat-num">${recentCount}</span><span class="welcome-stat-label">${_t("welcome.stat.recent")}</span></div>
  `;
}

// ── Projects (dropdown) ──────────────────────────────────────────
export function renderProjects(projects) {
  // Group projects by source
  const claudeProjects = [];
  const codexProjects = [];
  projects.forEach(p => {
    // Check if any session in this project is codex
    const isCodex = state.allSessions.some(s => s.project === p.name && s.source === "codex");
    (isCodex ? codexProjects : claudeProjects).push(p);
  });

  dom.projectDropdown.innerHTML = "";

  // "All Projects" option
  const allItem = document.createElement("div");
  allItem.className = "proj-item proj-all";
  allItem.textContent = "All Projects";
  allItem.addEventListener("click", () => selectProject(null));
  dom.projectDropdown.appendChild(allItem);

  // Claude section
  if (claudeProjects.length) {
    const hdr = document.createElement("div");
    hdr.className = "proj-group-header";
    hdr.innerHTML = '<span class="source-badge claude">Claude</span>';
    dom.projectDropdown.appendChild(hdr);
    claudeProjects.forEach(p => dom.projectDropdown.appendChild(makeProjectItem(p)));
  }

  // Codex section
  if (codexProjects.length) {
    const hdr = document.createElement("div");
    hdr.className = "proj-group-header";
    hdr.innerHTML = '<span class="source-badge codex">Codex</span>';
    dom.projectDropdown.appendChild(hdr);
    codexProjects.forEach(p => dom.projectDropdown.appendChild(makeProjectItem(p)));
  }

  updateProjectTrigger();
}

export function makeProjectItem(p) {
  const item = document.createElement("div");
  item.className = "proj-item";
  item.innerHTML = `<span>${esc(p.name)}</span><span class="count">${p.sessionCount}</span>`;
  item.addEventListener("click", () => selectProject(p.name));
  return item;
}

export function selectProject(name) {
  state.currentProject = name;
  dom.projectDropdown.classList.add("hidden");
  updateProjectTrigger();
  const base = name ? state.allSessions.filter(s => s.project === name) : state.allSessions;
  renderSessions(base);
}

export function updateProjectTrigger() {
  const textEl = document.getElementById("project-trigger-text");
  if (textEl) textEl.textContent = state.currentProject || "All Projects";
}

// ── Session Filtering ────────────────────────────────────────────
export function filterSessionList(sessions) {
  let filtered = applySourceFilter(sessions);
  filtered = applyDateFilter(filtered);
  return filtered;
}

export function updateFilterChips() {
  const container = $("#filter-chips");
  const clearBtn = $("#filter-clear");
  if (!container) return;
  const chips = [];
  if (state.currentSourceFilter !== "all") chips.push(state.currentSourceFilter.charAt(0).toUpperCase() + state.currentSourceFilter.slice(1));
  if (state.currentDateFilter !== "all") {
    const labels = { "week": "This Week", "month": "This Month", "3months": "3 Months" };
    chips.push(labels[state.currentDateFilter] || state.currentDateFilter);
  }
  if (state.currentProject) chips.push(state.currentProject.split("/").pop());
  container.innerHTML = chips.map(c => `<span class="filter-chip">${c}</span>`).join("");
  if (clearBtn) clearBtn.classList.toggle("hidden", chips.length === 0);
}

// ── Render Sessions ──────────────────────────────────────────────
export function renderSessions(sessions) {
  // Apply source filter, then date filter
  const filtered = filterSessionList(sessions);
  dom.sessionList.innerHTML = "";
  dom.sessionCount.textContent = filtered.length;

  // Add filter buttons
  renderSourceFilters();
  renderDateFilters();
  updateFilterChips();

  // Render visible sessions (cap at 200 for DOM performance, lazy-load rest on scroll)
  const RENDER_BATCH = 200;
  const toRender = filtered.slice(0, RENDER_BATCH);
  let renderedCount = toRender.length;

  const renderItem = (s) => {
    const li = document.createElement("li");
    li.dataset.id = s.id;
    if (s.id === state.currentSessionId) li.classList.add("active");
    const dateStr = s.date ? formatDate(s.date) : "";
    const srcBadge = s.source === "codex" ? '<span class="src-badge codex">Codex</span>' : '';
    const msgCount = s.userMessageCount ? `<span class="msg-count">${s.userMessageCount} msgs</span>` : '';
    li.innerHTML = `
      <div class="session-title">${esc(s.title)}</div>
      <div class="session-meta">
        ${srcBadge}
        <span class="session-project">${esc(s.project || '')}</span>
        <span>${dateStr}</span>
        ${msgCount}
      </div>
    `;
    li.addEventListener("click", () => { _deps.switchSidebarPanel("sessions"); _deps.loadSession(s.id); });
    return li;
  };

  toRender.forEach(s => dom.sessionList.appendChild(renderItem(s)));

  // Lazy-load remaining sessions on scroll
  if (filtered.length > RENDER_BATCH) {
    const sentinel = document.createElement("li");
    sentinel.className = "load-more-sentinel";
    sentinel.textContent = `+ ${filtered.length - RENDER_BATCH} more sessions`;
    sentinel.style.cssText = "text-align:center;color:var(--text-muted);font-size:12px;padding:12px;cursor:pointer";
    dom.sessionList.appendChild(sentinel);

    const loadMore = () => {
      sentinel.remove();
      const nextBatch = filtered.slice(renderedCount, renderedCount + RENDER_BATCH);
      nextBatch.forEach(s => dom.sessionList.appendChild(renderItem(s)));
      renderedCount += nextBatch.length;
      if (renderedCount < filtered.length) {
        sentinel.textContent = `+ ${filtered.length - renderedCount} more sessions`;
        dom.sessionList.appendChild(sentinel);
      }
    };
    sentinel.addEventListener("click", loadMore);
    // Also auto-load when scrolling near bottom (remove previous listener to prevent leaks)
    const sidebarContent = document.getElementById("sidebar-content");
    if (sidebarContent) {
      if (state._sidebarScrollHandler) sidebarContent.removeEventListener("scroll", state._sidebarScrollHandler);
      state._sidebarScrollHandler = () => {
        if (sidebarContent.scrollTop + sidebarContent.clientHeight >= sidebarContent.scrollHeight - 100) {
          if (renderedCount < filtered.length) loadMore();
        }
      };
      sidebarContent.addEventListener("scroll", state._sidebarScrollHandler, { passive: true });
    }
  }
}

// ── Source Filters ────────────────────────────────────────────────
export function applySourceFilter(sessions) {
  if (state.currentSourceFilter === "all") return sessions;
  return sessions.filter(s => (s.source || "claude") === state.currentSourceFilter);
}

export function renderSourceFilters() {
  const container = document.getElementById('source-tabs');
  if (!container) return;
  container.innerHTML = '';
  const filters = [
    { key: 'all', label: 'All' },
    { key: 'claude', label: 'Claude' },
    { key: 'codex', label: 'Codex' },
  ];
  filters.forEach(f => {
    const btn = document.createElement('button');
    btn.className = `source-tab${f.key === state.currentSourceFilter ? ' active' : ''}`;
    if (f.key !== 'all') btn.classList.add(f.key);
    btn.textContent = f.label;
    btn.addEventListener('click', () => {
      state.currentSourceFilter = f.key;
      const base = state.currentProject
        ? state.allSessions.filter(s => s.project === state.currentProject)
        : state.allSessions;
      renderSessions(base);
    });
    container.appendChild(btn);
  });
}

// ── Date Filters ─────────────────────────────────────────────────
export function renderDateFilters() {
  const df = document.querySelector('#filter-popover .date-filters');
  if (!df) return;
  df.innerHTML = '';
  const filters = [
    { key: 'all', label: 'All' },
    { key: 'week', label: 'This Week' },
    { key: 'month', label: 'This Month' },
    { key: '3months', label: '3 Months' },
  ];
  filters.forEach(f => {
    const btn = document.createElement('button');
    btn.className = `date-filter-btn${f.key === state.currentDateFilter ? ' active' : ''}`;
    btn.textContent = f.label;
    btn.addEventListener('click', () => {
      state.currentDateFilter = f.key;
      const base = state.currentProject
        ? state.allSessions.filter(s => s.project === state.currentProject)
        : state.allSessions;
      renderSessions(base);
    });
    df.appendChild(btn);
  });
}

export function applyDateFilter(sessions) {
  if (state.currentDateFilter === 'all') return sessions;
  const now = new Date();
  let cutoff;
  switch (state.currentDateFilter) {
    case 'week': cutoff = new Date(now - 7 * 86400000); break;
    case 'month': cutoff = new Date(now - 30 * 86400000); break;
    case '3months': cutoff = new Date(now - 90 * 86400000); break;
    default: return sessions;
  }
  return sessions.filter(s => s.date && new Date(s.date) >= cutoff);
}
