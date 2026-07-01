/**
 * Session list rendering — sidebar sessions, projects, filters.
 *
 * Usage:
 *   import { renderSessions, renderProjects, ... } from './sessions.js';
 */

import { state } from './state.js';
import { $, dom } from './dom.js';
import { esc, formatDate } from './utils.js';
import { t, registerI18n } from './lang.js';

// ── i18n dictionary ──────────────────────────────────────────────
registerI18n({
  zh: {
    'sessions.allProjects': '全部项目',
    'sessions.source.all': '全部',
    'sessions.source.claude': 'Claude',
    'sessions.source.codex': 'Codex',
    'sessions.date.all': '全部',
    'sessions.date.week': '本周',
    'sessions.date.month': '本月',
    'sessions.date.3months': '3 个月',
    'sessions.loadMore': '+ {n} 更多会话',
    'sessions.msgs': '条消息',
    'sessions.rename': '重命名',
    'sessions.delete': '删除',
    'sessions.deleteIcon': '✕',
    'sessions.deleteConfirm': '确认删除"{title}"？',
  },
  en: {
    'sessions.allProjects': 'All Projects',
    'sessions.source.all': 'All',
    'sessions.source.claude': 'Claude',
    'sessions.source.codex': 'Codex',
    'sessions.date.all': 'All',
    'sessions.date.week': 'This Week',
    'sessions.date.month': 'This Month',
    'sessions.date.3months': '3 Months',
    'sessions.loadMore': '+ {n} more sessions',
    'sessions.msgs': 'msgs',
    'sessions.rename': 'Rename',
    'sessions.delete': 'Delete session',
    'sessions.deleteIcon': '✕',
    'sessions.deleteConfirm': 'Delete "{title}"?',
  },
});

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
    <div class="welcome-stat"><span class="welcome-stat-num">${sessions.length}</span><span class="welcome-stat-label">${t('stats.sessions')}</span></div>
    <div class="welcome-stat"><span class="welcome-stat-num">${projCount}</span><span class="welcome-stat-label">${t('stats.projects')}</span></div>
    <div class="welcome-stat"><span class="welcome-stat-num">${recentCount}</span><span class="welcome-stat-label">${t('stats.recent')}</span></div>
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
  allItem.textContent = t("sessions.allProjects");
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
  if (textEl) textEl.textContent = state.currentProject || t("sessions.allProjects");
}

// ── Session Favorites (Star) ───────────────────────────────────────
let starFilterActive = false;

export function toggleStarFilter() {
  starFilterActive = !starFilterActive;
  renderSessions(state.allSessions);
}

// ── Session Filtering ────────────────────────────────────────────
export function filterSessionList(sessions) {
  let filtered = applySourceFilter(sessions);
  filtered = applyDateFilter(filtered);
  if (starFilterActive) filtered = filtered.filter(s => s.starred);
  return filtered;
}

export function updateFilterChips() {
  const container = $("#filter-chips");
  const clearBtn = $("#filter-clear");
  if (!container) return;
  const chips = [];
  if (state.currentSourceFilter !== "all") chips.push(t("sessions.source." + state.currentSourceFilter.charAt(0).toUpperCase() + state.currentSourceFilter.slice(1)) || state.currentSourceFilter.charAt(0).toUpperCase() + state.currentSourceFilter.slice(1));
  if (state.currentDateFilter !== "all") {
    const labels = { "week": t("sessions.date.week"), "month": t("sessions.date.month"), "3months": t("sessions.date.3months") };
    chips.push(labels[state.currentDateFilter] || state.currentDateFilter);
  }
  if (state.currentProject) chips.push(state.currentProject.split("/").pop());
  container.innerHTML = chips.map(c => `<span class="filter-chip">${c}</span>`).join("");
  if (clearBtn) clearBtn.classList.toggle("hidden", chips.length === 0);
}

// ── Render Sessions ──────────────────────────────────────────────
export function renderSessions(sessions) {
  const sidebarContent = document.getElementById("sidebar-content");
  if (sidebarContent && state._sidebarScrollHandler) {
    sidebarContent.removeEventListener("scroll", state._sidebarScrollHandler);
    state._sidebarScrollHandler = null;
  }
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
    if (s.starred) li.classList.add("starred");
    const dateStr = s.date ? formatDate(s.date) : "";
    const srcBadge = s.source === "codex" ? '<span class="src-badge codex">Codex</span>' : '';
    const msgCount = s.userMessageCount ? `<span class="msg-count">${s.userMessageCount} ${t("sessions.msgs")}</span>` : '';
    const starIcon = s.starred ? '★' : '☆';
    li.innerHTML = `
      <div class="session-header-row">
        <div class="session-title">${esc(s.title)}</div>
        <div class="session-header-actions">
          <button class="session-rename-btn" title="${esc(t('sessions.rename') || 'Rename')}">&#9998;</button>
          <button class="session-star-btn" title="${s.starred ? 'Unstar' : 'Star'}">${starIcon}</button>
          <button class="session-delete-btn" title="${esc(t('sessions.delete') || 'Delete')}">${t('sessions.deleteIcon') || '✕'}</button>
        </div>
      </div>
      <div class="session-meta">
        ${srcBadge}
        <span class="session-project">${esc(s.project || '')}</span>
        <span>${dateStr}</span>
        ${msgCount}
      </div>
    `;
    li.addEventListener("click", (e) => {
      if (e.target.closest('.session-delete-btn') || e.target.closest('.session-star-btn') || e.target.closest('.session-rename-btn')) return;
      _deps.switchSidebarPanel("sessions"); _deps.loadSession(s.id);
    });
    // Delete button handler
    const delBtn = li.querySelector('.session-delete-btn');
    if (delBtn) {
      delBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        e.preventDefault();
        const confirmed = confirm(t('sessions.deleteConfirm', { title: s.title }) + '');
        if (!confirmed) return;
        try {
          const resp = await fetch(`/api/session/${s.id}`, { method: 'DELETE' });
          const data = await resp.json();
          if (!data.ok) throw new Error(data.error || 'Delete failed');
          state.allSessions = state.allSessions.filter(ses => ses.id !== s.id);
          renderSessions(state.allSessions);
          if (window.showToast) window.showToast.success('Session deleted');
        } catch (err) {
          if (window.showToast) window.showToast.error('Delete failed: ' + err.message);
          else alert('Delete failed: ' + err.message);
        }
      });
    }
    // Rename button handler
    const renameBtn = li.querySelector('.session-rename-btn');
    if (renameBtn) {
      renameBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const titleEl = li.querySelector('.session-title');
        const oldTitle = s.title;
        titleEl.contentEditable = 'true';
        titleEl.focus();
        const range = document.createRange();
        range.selectNodeContents(titleEl);
        window.getSelection().removeAllRanges();
        window.getSelection().addRange(range);

        let cancelled = false;
        const onKeydown = (ke) => {
          if (ke.key === 'Enter') { ke.preventDefault(); titleEl.blur(); }
          if (ke.key === 'Escape') { cancelled = true; titleEl.blur(); }
        };
        const finishEdit = () => {
          titleEl.contentEditable = 'false';
          titleEl.removeEventListener('keydown', onKeydown);
          if (cancelled) { titleEl.textContent = oldTitle; return; }
          const newTitle = (titleEl.textContent || '').trim();
          titleEl.textContent = newTitle || oldTitle;
          if (newTitle && newTitle !== oldTitle) {
            fetch('/api/session/rename', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({id: s.id, title: newTitle})
            }).then(r => {
              if (!r.ok) { titleEl.textContent = oldTitle; s.title = oldTitle; }
            }).catch(() => { titleEl.textContent = oldTitle; s.title = oldTitle; });
            s.title = newTitle;
          } else {
            titleEl.textContent = oldTitle;
          }
        };
        titleEl.addEventListener('blur', finishEdit, {once: true});
        titleEl.addEventListener('keydown', onKeydown);
      });
    }
    // Star button handler
    const starBtn = li.querySelector('.session-star-btn');
    if (starBtn) {
      starBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        e.preventDefault();
        try {
          const resp = await fetch(`/api/session/${s.id}/star`, { method: 'POST' });
          const data = await resp.json();
          if (data.ok) {
            // Update in-place
            const found = state.allSessions.find(ses => ses.id === s.id);
            if (found) found.starred = data.starred ? 1 : 0;
            renderSessions(state.allSessions);
          }
        } catch (err) {
          if (window.showToast) window.showToast.error('Failed to toggle star');
        }
      });
    }
    return li;
  };

  toRender.forEach(s => dom.sessionList.appendChild(renderItem(s)));

  // Lazy-load remaining sessions on scroll
  if (filtered.length > RENDER_BATCH) {
    const sentinel = document.createElement("li");
    sentinel.className = "load-more-sentinel";
    sentinel.textContent = t("sessions.loadMore", { n: filtered.length - RENDER_BATCH });
    sentinel.style.cssText = "text-align:center;color:var(--text-muted);font-size:12px;padding:12px;cursor:pointer";
    dom.sessionList.appendChild(sentinel);

    const loadMore = () => {
      sentinel.remove();
      const nextBatch = filtered.slice(renderedCount, renderedCount + RENDER_BATCH);
      nextBatch.forEach(s => dom.sessionList.appendChild(renderItem(s)));
      renderedCount += nextBatch.length;
      if (renderedCount < filtered.length) {
        sentinel.textContent = t("sessions.loadMore", { n: filtered.length - renderedCount });
        dom.sessionList.appendChild(sentinel);
      }
    };
    sentinel.addEventListener("click", loadMore);
    // Also auto-load when scrolling near bottom (remove previous listener to prevent leaks)
    if (sidebarContent) {
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
    { key: 'all', label: t("sessions.source.all") },
    { key: 'claude', label: t("sessions.source.claude") },
    { key: 'codex', label: t("sessions.source.codex") },
    { key: 'starred', label: t("sessions.starred.filter"), className: 'star-filter-btn' },
  ];
  filters.forEach(f => {
    const btn = document.createElement('button');
    btn.className = `source-tab${f.key === state.currentSourceFilter ? ' active' : ''}`;
    if (f.className) btn.classList.add(f.className);
    if (f.key !== 'all' && f.key !== 'starred') btn.classList.add(f.key);
    btn.textContent = f.label;
    btn.addEventListener('click', () => {
      if (f.key === 'starred') {
        state.currentSourceFilter = 'all';
        starFilterActive = !starFilterActive;
      } else {
        state.currentSourceFilter = f.key;
        starFilterActive = false;
      }
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
    { key: 'all', label: t('sessions.date.all') },
    { key: 'week', label: t('sessions.date.week') },
    { key: 'month', label: t('sessions.date.month') },
    { key: '3months', label: t('sessions.date.3months') },
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
