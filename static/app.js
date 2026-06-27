/**
 * Claude Chat Viewer — Frontend
 */
(function () {
  "use strict";

  // ── State ──────────────────────────────────────────────────────
  let allSessions = [];
  let currentProject = null;
  let currentSessionId = null;
  let userOnlyMode = false;
  let allCollapsed = false;
  let currentDateFilter = "all";
  let currentSourceFilter = "all";
  let searchDebounceTimer = null;
  let lastSearchResults = [];
  let lastSearchQuery = "";
  let _searchAbort = null; // AbortController for search
  let _sessionAbort = null; // AbortController for session loading
  let outlineVisible = true;
  let _scrollHandler = null;
  let _sidebarScrollHandler = null;
  let currentMessages = []; // store for export
  let currentView = "sessions"; // sessions|conversation|search|insights|ai
  let viewHistory = []; // for back navigation
  let currentSidebarPanel = "sessions";

  // Chat state — dual surface: session AI (right panel) + global AI (standalone view)
  let globalChatHistory = []; // [{id, title, messages:[{role,content}]}]
  let currentGlobalChatId = null;
  let sessionChatCache = {}; // {[sessionId]: {messages:[{role,content}]}}
  let sessionAiLoading = false;
  let globalAiLoading = false;
  let sessionAiHandle = null; // sendChatStream handle for abort
  let globalAiHandle = null;

  // Global AI scope state
  let globalScopeSource = "all";
  let globalScopeDate = "7d";
  let globalScopeProject = "";
  let globalScopeEngine = "auto";
  let chatTimeout = parseInt(localStorage.getItem("chatview-timeout") || "900", 10); // seconds

  // Insights page state
  let insightsActiveTab = "heatmap";
  let insightsDataCache = { analytics: null, health: null, snippets: null };

  // ── DOM refs ───────────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const searchInput = $("#global-search");
  const searchStats = $("#search-stats");
  const projectTrigger = $("#project-trigger");
  const projectDropdown = $("#project-dropdown");
  const sessionList = $("#session-list");
  const sessionCount = $("#session-count");
  const convView = $("#conversation-view");
  const searchResults = $("#search-results");
  const messagesContainer = $("#messages-container");
  const convTitle = $("#conv-title");
  const convMeta = $("#conv-meta");
  const searchResultCount = $("#search-result-count");
  const searchResultsList = $("#search-results-list");
  const searchSortSelect = $("#search-sort");
  const rightPanel = $("#right-panel");
  const outlineList = $("#outline-list");
  const insightsView = $("#insights-view");
  const aiView = $("#ai-view");
  const sidebar = $("#sidebar");
  const kbdHelp = $("#kbd-help");

  // ── API helpers ────────────────────────────────────────────────
  async function api(path) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    return resp.json();
  }

  // ── Init ───────────────────────────────────────────────────────
  async function init() {
    bindEvents();
    // Show loading state immediately
    sessionList.innerHTML = '<li class="loading-placeholder"><div class="skeleton-line" style="width:70%"></div><div class="skeleton-line short"></div></li>'.repeat(8);
    searchStats.textContent = "Loading…";

    // Load from cached index immediately (server builds index at startup)
    const [projects, sessions] = await Promise.all([
      api("/api/projects"),
      api("/api/sessions"),
    ]);
    allSessions = sessions;
    renderProjects(projects);
    renderSessions(sessions);
    searchStats.textContent = `${sessions.length} sessions`;
    updateWelcomeStats(sessions, projects);
    // Background refresh: rebuild index and re-render if data changed
    api("/api/refresh").then(() => Promise.all([
      api("/api/projects"),
      api("/api/sessions"),
    ])).then(([p, s]) => {
      if (s.length !== allSessions.length) {
        allSessions = s;
        renderProjects(p);
        renderSessions(s);
        searchStats.textContent = `${s.length} sessions`;
        updateWelcomeStats(s, p);
        // Invalidate insights cache so new sessions are reflected
        insightsDataCache = { analytics: null, health: null, snippets: null };
      }
    }).catch(() => {});

    // Restore session from URL hash (replaceState, not push, to avoid duplicate entry)
    const hash = window.location.hash.slice(1);
    if (hash) {
      const match = allSessions.find(s => s.id === hash);
      if (match && match.source) {
        currentSourceFilter = match.source;
        renderSessions(allSessions);
      }
      history.replaceState({ view: "conversation", sessionId: hash }, "", `#${hash}`);
      loadSession(hash, undefined, false);
    }
  }

  // ── Event Bindings ─────────────────────────────────────────────
  function bindEvents() {
    // Filter button + popover
    const filterBtn = $("#filter-btn");
    const filterPopover = $("#filter-popover");
    if (filterBtn && filterPopover) {
      filterBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const open = !filterPopover.classList.contains("hidden");
        filterPopover.classList.toggle("hidden", open);
        filterBtn.classList.toggle("active", !open);
      });
      // Close popover on outside click
      document.addEventListener("click", (e) => {
        if (!filterPopover.contains(e.target) && e.target !== filterBtn) {
          filterPopover.classList.add("hidden");
          filterBtn.classList.remove("active");
        }
      });
    }

    // Filter clear button
    const filterClear = $("#filter-clear");
    if (filterClear) {
      filterClear.addEventListener("click", (e) => {
        e.stopPropagation();
        currentSourceFilter = "all";
        currentDateFilter = "all";
        currentProject = null;
        const textEl = $("#project-trigger-text");
        if (textEl) textEl.textContent = "All Projects";
        renderSessions(allSessions);
      });
    }

    // Global search
    searchInput.addEventListener("input", () => {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => doSearch(searchInput.value.trim()), 300);
    });
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        searchInput.value = "";
        showView("sessions");
      }
    });
    searchSortSelect.addEventListener("change", () => {
      if (lastSearchResults.length) renderSearchResults();
    });

    // Keyboard shortcuts (F5)
    document.addEventListener("keydown", handleKeyboard);

    // Logo → sessions
    const logo = $("#logo");
    if (logo) logo.addEventListener("click", (e) => { e.preventDefault(); showView("sessions"); history.replaceState(null, "", window.location.pathname); });

    // Top nav items
    document.querySelectorAll(".sidebar-nav-item").forEach(btn => {
      btn.addEventListener("click", () => {
        const view = btn.dataset.view;
        // Highlight active nav
        document.querySelectorAll(".sidebar-nav-item").forEach(b => b.classList.toggle("active", b === btn));
        // Show the right main view
        if (view === "sessions") { showView("sessions"); }
        else if (view === "insights") { openInsights(); }
        else if (view === "ai") { showView("ai"); initAiPage(); }
        else if (view === "twin") { showView("twin"); }
      });
    });

    // Project dropdown toggle
    projectTrigger.addEventListener("click", () => {
      projectDropdown.classList.toggle("hidden");
    });
    // Close dropdown on outside click
    document.addEventListener("click", (e) => {
      if (!e.target.closest("#project-bar")) {
        projectDropdown.classList.add("hidden");
      }
    });

    // Back button → previous view
    $("#btn-back").addEventListener("click", goBack);

    // Refresh current session
    $("#btn-refresh").addEventListener("click", async () => {
      if (currentSessionId) {
        await api("/api/refresh");
        loadSession(currentSessionId);
      }
    });

    // User-only toggle
    $("#btn-user-only").addEventListener("click", function () {
      userOnlyMode = !userOnlyMode;
      this.classList.toggle("active", userOnlyMode);
      applyUserOnlyFilter();
    });

    // Collapse/Expand all toggle — tool bodies start collapsed (display:none)
    // So first click should EXPAND all, not collapse
    $("#btn-collapse-all").addEventListener("click", function () {
      allCollapsed = !allCollapsed;
      // allCollapsed=true means "show expanded" (since initial is collapsed)
      this.textContent = allCollapsed ? "Collapse All" : "Expand All";
      this.classList.toggle("active", allCollapsed);
      $$(".tool-body, .thinking-body").forEach((el) => {
        el.style.display = allCollapsed ? "" : "none";
      });
      $$(".tool-toggle").forEach((el) => {
        el.classList.toggle("open", allCollapsed);
      });
      // Also handle tool call groups
      $$(".tool-group-body").forEach((el) => {
        el.style.display = allCollapsed ? "" : "none";
      });
      $$(".tool-group-toggle").forEach((el) => {
        el.classList.toggle("open", allCollapsed);
      });
      $$(".tool-call-group").forEach((el) => {
        el.classList.toggle("collapsed", !allCollapsed);
      });
    });

    // Right panel tab switching
    document.querySelectorAll(".rp-tab").forEach(tab => {
      tab.addEventListener("click", () => {
        const panel = tab.dataset.panel;
        document.querySelectorAll(".rp-tab").forEach(t => t.classList.toggle("active", t === tab));
        document.querySelectorAll(".rp-content").forEach(c => c.classList.toggle("hidden", !c.id.endsWith(panel)));
        // Lazy-load summary when switching to that tab
        if (panel === "summary" && currentSessionId) {
          loadSessionSummary(currentSessionId);
        }
      });
    });

    // Export (F4)
    $("#btn-export").addEventListener("click", exportMarkdown);

    // Copy conversation (User + Assistant text only)
    $("#btn-copy-conv").addEventListener("click", copyConversation);

    // ── Session AI bindings (right panel) ──
    const sessionAiSend = $("#session-ai-send");
    const sessionAiInput = $("#session-ai-input");
    if (sessionAiSend) sessionAiSend.addEventListener("click", () => {
      if (sessionAiLoading && sessionAiHandle) { _stopSessionAi(); } else { submitSessionAi(); }
    });
    if (sessionAiInput) {
      sessionAiInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          if (sessionAiLoading && sessionAiHandle) { _stopSessionAi(); } else { submitSessionAi(); }
        }
      });
      sessionAiInput.addEventListener("input", () => autoResizeTextarea(sessionAiInput));
    }
    // Session AI presets (inside #session-ai-presets)
    document.querySelectorAll("#session-ai-presets .preset-card").forEach(btn => {
      btn.addEventListener("click", () => submitSessionAi(btn.dataset.prompt));
    });

    // ── Global AI bindings (AI page chat panel) ──
    const chatSendBtn = $("#ai-chat-send");
    const chatInput = $("#ai-chat-input");
    if (chatSendBtn) chatSendBtn.addEventListener("click", () => {
      if (globalAiLoading && globalAiHandle) { _stopGlobalAi(); } else { submitGlobalAi(); }
    });
    if (chatInput) {
      chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          if (globalAiLoading && globalAiHandle) { _stopGlobalAi(); } else { submitGlobalAi(); }
        }
      });
      chatInput.addEventListener("input", () => autoResizeTextarea(chatInput));
    }

    // (Welcome chat and standalone AI chat bindings removed — containers removed in new architecture)

    // Global AI presets (populated dynamically)
    const btnNewChatAi = $("#btn-new-chat-ai");
    if (btnNewChatAi) btnNewChatAi.addEventListener("click", newGlobalChat);
    const btnNewChatSidebar = $("#btn-new-chat");
    if (btnNewChatSidebar) btnNewChatSidebar.addEventListener("click", newGlobalChat);

    // Load persisted chat history
    loadChatFromStorage();

    // Browser back/forward button support
    window.addEventListener("popstate", (e) => {
      const state = e.state;
      if (state && state.view === "conversation" && state.sessionId) {
        loadSession(state.sessionId, undefined, false);
      } else {
        showView("sessions", false);
        currentSessionId = null;
      }
    });

    // Mobile sidebar toggle
    const sidebarToggle = $("#sidebar-toggle");
    const sidebar = $("#sidebar");
    const sidebarOverlay = $("#sidebar-overlay");
    if (sidebarToggle && sidebar) {
      const closeSidebar = () => sidebar.classList.remove("open");
      sidebarToggle.addEventListener("click", () => sidebar.classList.toggle("open"));
      if (sidebarOverlay) sidebarOverlay.addEventListener("click", closeSidebar);
      // Close sidebar when a session is selected on mobile
      sessionList.addEventListener("click", (e) => {
        if (e.target.closest("li") && window.innerWidth <= 768) closeSidebar();
      });
    }

  }

  // ── View Switching ─────────────────────────────────────────────
  function showView(name, pushHistory = true) {
    if (pushHistory && currentView !== name) {
      viewHistory.push(currentView);
      if (viewHistory.length > 50) viewHistory = viewHistory.slice(-20);
    }
    currentView = name;
    const twinView = $("#twin-view");
    const views = {conversation: convView, search: searchResults,
      insights: insightsView, ai: aiView, twin: twinView};
    for (const [k, el] of Object.entries(views)) {
      if (el) el.classList.toggle("hidden", k !== name);
    }
    const emptyState = $("#empty-state");
    if (emptyState) emptyState.classList.toggle("hidden", name !== "sessions");
    // Sidebar panel: sessions list by default, chat history for AI page
    if (name === "ai") {
      switchSidebarPanel("chat");
    } else {
      switchSidebarPanel("sessions");
    }
    // Initialize Twin view when switching to it
    if (name === "twin" && window.initTwinView) window.initTwinView();
    // Update sidebar nav active state
    const navView = (name === "conversation" || name === "search") ? "sessions" : name;
    document.querySelectorAll(".sidebar-nav-item").forEach(b => b.classList.toggle("active", b.dataset.view === navView));
  }

  function goBack() {
    const prev = viewHistory.pop() || "sessions";
    showView(prev, false);
    if (prev === "sessions") history.replaceState(null, "", window.location.pathname);
  }

  function switchSidebarPanel(panel) {
    currentSidebarPanel = panel;
    document.querySelectorAll(".sidebar-panel").forEach(p => {
      p.classList.toggle("hidden", !p.id.endsWith(panel));
    });
    // (filter bar is now always visible in sidebar)
  }

  // ── Welcome Stats ───────────────────────────────────────────────
  function updateWelcomeStats(sessions, projects) {
    const container = $("#welcome-stats");
    if (!container) return;
    const projCount = projects ? projects.length : 0;
    const now = new Date();
    const weekAgo = new Date(now - 7 * 86400000);
    const recentCount = sessions.filter(s => s.date && new Date(s.date) >= weekAgo).length;
    container.innerHTML = `
      <div class="welcome-stat"><span class="welcome-stat-num">${sessions.length}</span><span class="welcome-stat-label">总会话</span></div>
      <div class="welcome-stat"><span class="welcome-stat-num">${projCount}</span><span class="welcome-stat-label">项目</span></div>
      <div class="welcome-stat"><span class="welcome-stat-num">${recentCount}</span><span class="welcome-stat-label">近 7 天</span></div>
    `;
  }

  // ── Welcome Card Actions ──────────────────────────────────────
  function openInsightsTab(tabName) {
    showView("insights");
    bindInsightsTabs();
    insightsActiveTab = tabName;
    document.querySelectorAll(".insights-tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tabName));
    loadInsightsTab(tabName);
  }

  (function bindWelcomeCards() {
    document.querySelectorAll(".welcome-card").forEach(card => {
      card.addEventListener("click", () => {
        const action = card.dataset.action;
        if (action === "heatmap" || action === "hotspots" || action === "errors" || action === "health" || action === "snippets") {
          openInsightsTab(action);
        } else if (action === "profile") {
          document.querySelector('.sidebar-nav-item[data-view="ai"]')?.click();
        }
      });
    });
  })();

  // ── Projects (dropdown) ─────────────────────────────────────────
  function renderProjects(projects) {
    // Group projects by source
    const claudeProjects = [];
    const codexProjects = [];
    projects.forEach(p => {
      // Check if any session in this project is codex
      const isCodex = allSessions.some(s => s.project === p.name && s.source === "codex");
      (isCodex ? codexProjects : claudeProjects).push(p);
    });

    projectDropdown.innerHTML = "";

    // "All Projects" option
    const allItem = document.createElement("div");
    allItem.className = "proj-item proj-all";
    allItem.textContent = "All Projects";
    allItem.addEventListener("click", () => selectProject(null));
    projectDropdown.appendChild(allItem);

    // Claude section
    if (claudeProjects.length) {
      const hdr = document.createElement("div");
      hdr.className = "proj-group-header";
      hdr.innerHTML = '<span class="source-badge claude">Claude</span>';
      projectDropdown.appendChild(hdr);
      claudeProjects.forEach(p => projectDropdown.appendChild(makeProjectItem(p)));
    }

    // Codex section
    if (codexProjects.length) {
      const hdr = document.createElement("div");
      hdr.className = "proj-group-header";
      hdr.innerHTML = '<span class="source-badge codex">Codex</span>';
      projectDropdown.appendChild(hdr);
      codexProjects.forEach(p => projectDropdown.appendChild(makeProjectItem(p)));
    }

    updateProjectTrigger();
  }

  function makeProjectItem(p) {
    const item = document.createElement("div");
    item.className = "proj-item";
    item.innerHTML = `<span>${esc(p.name)}</span><span class="count">${p.sessionCount}</span>`;
    item.addEventListener("click", () => selectProject(p.name));
    return item;
  }

  function selectProject(name) {
    currentProject = name;
    projectDropdown.classList.add("hidden");
    updateProjectTrigger();
    const base = name ? allSessions.filter(s => s.project === name) : allSessions;
    renderSessions(base);
  }

  function updateProjectTrigger() {
    const textEl = document.getElementById("project-trigger-text");
    if (textEl) textEl.textContent = currentProject || "All Projects";
  }

  // ── Sessions ───────────────────────────────────────────────────
  function filterSessionList(sessions) {
    let filtered = applySourceFilter(sessions);
    filtered = applyDateFilter(filtered);
    return filtered;
  }

  function updateFilterChips() {
    const container = $("#filter-chips");
    const clearBtn = $("#filter-clear");
    if (!container) return;
    const chips = [];
    if (currentSourceFilter !== "all") chips.push(currentSourceFilter.charAt(0).toUpperCase() + currentSourceFilter.slice(1));
    if (currentDateFilter !== "all") {
      const labels = { "week": "This Week", "month": "This Month", "3months": "3 Months" };
      chips.push(labels[currentDateFilter] || currentDateFilter);
    }
    if (currentProject) chips.push(currentProject.split("/").pop());
    container.innerHTML = chips.map(c => `<span class="filter-chip">${c}</span>`).join("");
    if (clearBtn) clearBtn.classList.toggle("hidden", chips.length === 0);
  }

  function renderSessions(sessions) {
    // Apply source filter, then date filter
    const filtered = filterSessionList(sessions);
    sessionList.innerHTML = "";
    sessionCount.textContent = filtered.length;

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
      if (s.id === currentSessionId) li.classList.add("active");
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
      li.addEventListener("click", () => { switchSidebarPanel("sessions"); loadSession(s.id); });
      return li;
    };

    toRender.forEach(s => sessionList.appendChild(renderItem(s)));

    // Lazy-load remaining sessions on scroll
    if (filtered.length > RENDER_BATCH) {
      const sentinel = document.createElement("li");
      sentinel.className = "load-more-sentinel";
      sentinel.textContent = `+ ${filtered.length - RENDER_BATCH} more sessions`;
      sentinel.style.cssText = "text-align:center;color:var(--text-muted);font-size:12px;padding:12px;cursor:pointer";
      sessionList.appendChild(sentinel);

      const loadMore = () => {
        sentinel.remove();
        const nextBatch = filtered.slice(renderedCount, renderedCount + RENDER_BATCH);
        nextBatch.forEach(s => sessionList.appendChild(renderItem(s)));
        renderedCount += nextBatch.length;
        if (renderedCount < filtered.length) {
          sentinel.textContent = `+ ${filtered.length - renderedCount} more sessions`;
          sessionList.appendChild(sentinel);
        }
      };
      sentinel.addEventListener("click", loadMore);
      // Also auto-load when scrolling near bottom (remove previous listener to prevent leaks)
      const sidebarContent = document.getElementById("sidebar-content");
      if (sidebarContent) {
        if (_sidebarScrollHandler) sidebarContent.removeEventListener("scroll", _sidebarScrollHandler);
        _sidebarScrollHandler = () => {
          if (sidebarContent.scrollTop + sidebarContent.clientHeight >= sidebarContent.scrollHeight - 100) {
            if (renderedCount < filtered.length) loadMore();
          }
        };
        sidebarContent.addEventListener("scroll", _sidebarScrollHandler, { passive: true });
      }
    }
  }

  function applySourceFilter(sessions) {
    if (currentSourceFilter === "all") return sessions;
    return sessions.filter(s => (s.source || "claude") === currentSourceFilter);
  }

  function renderSourceFilters() {
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
      btn.className = `source-tab${f.key === currentSourceFilter ? ' active' : ''}`;
      if (f.key !== 'all') btn.classList.add(f.key);
      btn.textContent = f.label;
      btn.addEventListener('click', () => {
        currentSourceFilter = f.key;
        const base = currentProject
          ? allSessions.filter(s => s.project === currentProject)
          : allSessions;
        renderSessions(base);
      });
      container.appendChild(btn);
    });
  }

  function renderDateFilters() {
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
      btn.className = `date-filter-btn${f.key === currentDateFilter ? ' active' : ''}`;
      btn.textContent = f.label;
      btn.addEventListener('click', () => {
        currentDateFilter = f.key;
        const base = currentProject
          ? allSessions.filter(s => s.project === currentProject)
          : allSessions;
        renderSessions(base);
      });
      df.appendChild(btn);
    });
  }

  function applyDateFilter(sessions) {
    if (currentDateFilter === 'all') return sessions;
    const now = new Date();
    let cutoff;
    switch (currentDateFilter) {
      case 'week': cutoff = new Date(now - 7 * 86400000); break;
      case 'month': cutoff = new Date(now - 30 * 86400000); break;
      case '3months': cutoff = new Date(now - 90 * 86400000); break;
      default: return sessions;
    }
    return sessions.filter(s => s.date && new Date(s.date) >= cutoff);
  }

  // ── Load Session ───────────────────────────────────────────────
  async function loadSession(sessionId, jumpToIndex, pushHistory = true) {
    // Cancel any in-flight session load
    if (_sessionAbort) _sessionAbort.abort();
    _sessionAbort = new AbortController();

    currentSessionId = sessionId;
    if (pushHistory) {
      history.pushState({ view: "conversation", sessionId }, "", `#${sessionId}`);
    }
    $$('#session-list li').forEach(li => {
      li.classList.toggle('active', li.dataset.id === sessionId);
    });

    showView("conversation");
    messagesContainer.innerHTML = '<div class="insights-loading"><div class="skeleton-block"></div><div class="skeleton-block" style="width:85%"></div><div class="skeleton-block" style="width:60%"></div></div>';

    try {
      const resp = await fetch(`/api/session/${sessionId}`, { signal: _sessionAbort.signal });
      if (!resp.ok) throw new Error(`API error: ${resp.status}`);
      const data = await resp.json();
      convTitle.textContent = data.title;
      const metaParts = [`${data.project} · ${formatDate(data.date)} · ${data.messages.length} messages`];
      convMeta.innerHTML = "";
      convMeta.appendChild(document.createTextNode(metaParts[0]));
      if (data.filePath) {
        const pathRow = document.createElement("div");
        pathRow.className = "conv-filepath-row";
        const pathText = document.createElement("span");
        pathText.textContent = data.filePath;
        pathRow.appendChild(pathText);
        const copyBtn = document.createElement("button");
        copyBtn.className = "conv-filepath-copy";
        copyBtn.title = "Copy path";
        copyBtn.textContent = "📋";
        copyBtn.addEventListener("click", () => {
          navigator.clipboard.writeText(data.filePath).then(() => {
            copyBtn.textContent = "✅";
            setTimeout(() => { copyBtn.textContent = "📋"; }, 1500);
          });
        });
        pathRow.appendChild(copyBtn);
        convMeta.appendChild(pathRow);
      }

      currentMessages = data.messages;
      renderMessages(data.messages);
      buildOutline(data.messages);
      // Switch to AI tab
      document.querySelectorAll(".rp-tab").forEach(t => t.classList.toggle("active", t.dataset.panel === "ai"));
      document.querySelectorAll(".rp-content").forEach(c => c.classList.toggle("hidden", !c.id.endsWith("ai")));
      updateSessionAiHeader();
      restoreSessionAiMessages();

      // Outline scroll tracking (remove previous listener to prevent leaks)
      const mc = document.getElementById("messages-container");
      if (_scrollHandler) mc.removeEventListener("scroll", _scrollHandler);
      let _scrollTick = false;
      _scrollHandler = () => {
        if (_scrollTick || !outlineVisible) return;
        _scrollTick = true;
        requestAnimationFrame(() => {
          _scrollTick = false;
          const userMsgs = mc.querySelectorAll(".msg.user-msg");
          const containerTop = mc.getBoundingClientRect().top;
          let closest = null;
          for (const el of userMsgs) {
            const r = el.getBoundingClientRect();
            if (r.top <= containerTop + 100) closest = el;
          }
          if (closest) highlightOutlineItem(parseInt(closest.dataset.idx));
        });
      };
      mc.addEventListener("scroll", _scrollHandler, { passive: true });

      if (typeof jumpToIndex === "number") {
        setTimeout(() => jumpToMessage(jumpToIndex), 100);
      }
    } catch (err) {
      if (err.name === "AbortError") return; // superseded by newer load
      messagesContainer.innerHTML = `<div style="padding:40px;text-align:center;color:#e57373">Failed to load session: ${esc(err.message)}</div>`;
    }
  }

  // ── Render Messages ────────────────────────────────────────────
  function renderMessages(messages) {
    messagesContainer.innerHTML = "";

    // Group messages into turns: user turn vs assistant turn (consecutive assistant + tool_result)
    const turns = [];
    let currentTurn = null;

    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      const isUser = msg.type === "user";
      const isAssistant = msg.type === "assistant";
      const isToolResult = msg.type === "tool_result";

      if (isUser && !isToolResult) {
        // User message starts a new user turn
        currentTurn = { type: "user", messages: [msg], startIdx: i };
        turns.push(currentTurn);
        currentTurn = null; // user turns are always single
      } else {
        // Assistant or tool_result → group into assistant turn
        if (!currentTurn || currentTurn.type !== "assistant") {
          currentTurn = { type: "assistant", messages: [], startIdx: i };
          turns.push(currentTurn);
        }
        currentTurn.messages.push(msg);
      }
    }

    // Render each turn
    let msgIdx = 0;
    turns.forEach((turn) => {
      if (turn.type === "user") {
        const el = createUserMsgEl(turn.messages[0], msgIdx);
        messagesContainer.appendChild(el);
        msgIdx++;
      } else {
        const el = createAssistantTurnEl(turn.messages, msgIdx);
        messagesContainer.appendChild(el);
        msgIdx += turn.messages.length;
      }
    });

    // Reset filters
    userOnlyMode = false;
    allCollapsed = false;
    $("#btn-user-only").classList.remove("active");
    $("#btn-collapse-all").classList.remove("active");
  }

  const COLLAPSE_THRESHOLD = 300; // chars — collapse texts longer than this

  function createUserMsgEl(msg, idx) {
    const div = document.createElement("div");
    div.className = "msg user-msg";
    div.dataset.idx = idx;
    div.dataset.type = "user";
    div.id = `msg-${idx}`;
    if (msg.isSidechain) div.classList.add("sidechain");

    const timeStr = msg.timestamp ? formatTime(msg.timestamp) : "";
    const hasLong = msg.content.some(b => b.type === "text" && b.text.length > COLLAPSE_THRESHOLD);
    let html = `<div class="msg-label">${hasLong ? '<span class="msg-collapse-toggle open">▶</span>' : ""}<span style="font-size:14px">👤</span> You <span style="font-weight:400;font-size:10px;color:var(--text-muted)">${timeStr}</span>${hasLong ? '<span class="msg-fold">Show more ↓</span>' : ""}</div>`;

    for (const block of msg.content) {
      if (block.type === "text") {
        const isLong = block.text.length > COLLAPSE_THRESHOLD;
        html += `<div class="text-collapsible${isLong ? " collapsed" : ""}">`;
        html += `<div class="msg-text">${renderMarkdown(block.text)}</div>`;
        if (isLong) html += `<button class="text-toggle">Show more ↓</button>`;
        html += `</div>`;
      } else if (block.type === "image") {
        html += `<div class="image-placeholder">🖼️ ${block.alt || "Image"}</div>`;
      }
    }

    div.innerHTML = html;
    bindUserFoldToggle(div);
    return div;
  }

  function createAssistantTurnEl(messages, startIdx) {
    const div = document.createElement("div");
    div.className = "msg assistant-turn";
    div.dataset.idx = startIdx;
    div.dataset.type = "assistant";
    div.id = `msg-${startIdx}`;

    // Collect all blocks in order
    const allBlocks = [];
    for (const msg of messages) {
      for (const block of msg.content) {
        allBlocks.push(block);
      }
    }

    // Stats for turn header
    let toolUseCount = 0;
    let thinkingCount = 0;
    const toolNameSet = new Set();
    for (const block of allBlocks) {
      if (block.type === "tool_use") { toolUseCount++; toolNameSet.add(block.name); }
      else if (block.type === "thinking") { thinkingCount++; }
    }
    const hasProcessBlocks = toolUseCount > 0 || thinkingCount > 0;

    // Group consecutive process blocks (tool_use/tool_result/thinking)
    const groups = [];
    let curProcessGroup = null;
    for (const block of allBlocks) {
      const isProcess = block.type === "tool_use" || block.type === "tool_result" || block.type === "thinking";
      if (isProcess) {
        if (!curProcessGroup) {
          curProcessGroup = { type: "process", blocks: [] };
          groups.push(curProcessGroup);
        }
        curProcessGroup.blocks.push(block);
      } else {
        curProcessGroup = null;
        groups.push({ type: "content", block });
      }
    }

    let html = "";
    const firstTs = messages[0]?.timestamp;
    const timeStr = firstTs ? formatTime(firstTs) : "";

    // Turn-level collapse bar (only when there are tool/thinking blocks)
    if (hasProcessBlocks) {
      let parts = [];
      if (toolUseCount > 0) parts.push(`${toolUseCount} tool calls`);
      if (thinkingCount > 0) parts.push(`${thinkingCount} thinking`);
      html += `<div class="turn-collapse-bar collapsed">
        <span class="turn-collapse-toggle">▶</span>
        <span class="turn-collapse-label">🤖 Agent</span>
        <span class="turn-collapse-summary">${parts.join(" · ")}</span>
        ${timeStr ? `<span class="turn-collapse-time">${timeStr}</span>` : ""}
      </div>`;
    }

    html += `<div class="turn-body"${hasProcessBlocks ? ' style="display:none"' : ""}>`;

    for (const group of groups) {
      if (group.type === "process") {
        const gToolCount = group.blocks.filter(b => b.type === "tool_use").length;
        const gToolNames = [...new Set(group.blocks.filter(b => b.type === "tool_use").map(b => b.name))];
        const autoCollapse = gToolCount >= 2;

        if (autoCollapse) {
          html += `<div class="tool-call-group collapsed">`;
          html += `<div class="tool-group-header">
            <span class="tool-group-toggle">▶</span>
            <span class="tool-group-label">${gToolCount} tool calls</span>
            <span class="tool-group-names">${esc(gToolNames.join(", "))}</span>
          </div>`;
          html += `<div class="tool-group-body" style="display:none">`;
        }

        for (const block of group.blocks) {
          switch (block.type) {
            case "tool_use": html += renderToolUse(block); break;
            case "tool_result": html += renderToolResult(block); break;
            case "thinking": html += renderThinking(block); break;
          }
        }

        if (autoCollapse) {
          html += `</div></div>`;
        }
      } else if (group.block) {
        const block = group.block;
        if (block.type === "text" && block.text?.trim()) {
          const isLong = block.text.length > COLLAPSE_THRESHOLD;
          html += `<div class="reply-card${isLong ? " collapsed" : ""}">`;
          html += `<div class="reply-label"><span style="font-size:13px">🤖</span> Assistant<button class="reply-copy" title="Copy">📋</button>${isLong ? ' <span class="reply-fold">Show more ↓</span>' : ""}</div>`;
          html += `<div class="msg-text">${renderMarkdown(block.text)}</div>`;
          if (isLong) html += `<button class="text-toggle reply-text-toggle">Show more ↓</button>`;
          html += `</div>`;
        } else if (block.type === "image") {
          html += `<div class="image-placeholder">🖼️ ${block.alt || "Image"}</div>`;
        }
      }
    }

    html += `</div>`; // close turn-body

    if (timeStr && !hasProcessBlocks) {
      html += `<div class="turn-time">${timeStr}</div>`;
    }

    div.innerHTML = html;
    bindReplyFoldToggles(div);
    bindToolToggles(div);
    bindTurnCollapseToggle(div);
    bindToolGroupToggles(div);
    return div;
  }

  function bindTextToggles(container) {
    container.querySelectorAll(".text-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        const wrapper = btn.parentElement;
        const isCollapsed = wrapper.classList.contains("collapsed");
        wrapper.classList.toggle("collapsed", !isCollapsed);
        btn.textContent = isCollapsed ? "Show less ↑" : "Show more ↓";
      });
    });
  }

  function bindUserFoldToggle(container) {
    const triangle = container.querySelector(".msg-collapse-toggle");
    const foldBtn = container.querySelector(".msg-fold");
    const textToggle = container.querySelector(".text-toggle");
    const collapsible = container.querySelector(".text-collapsible");
    if (!collapsible) return;

    function toggle() {
      const isCollapsed = collapsible.classList.contains("collapsed");
      collapsible.classList.toggle("collapsed", !isCollapsed);
      const label = isCollapsed ? "Collapse ↑" : "Show more ↓";
      if (foldBtn) foldBtn.textContent = label;
      if (textToggle) textToggle.textContent = label;
      if (triangle) triangle.classList.toggle("open", isCollapsed);
    }

    if (triangle) triangle.addEventListener("click", toggle);
    if (foldBtn) foldBtn.addEventListener("click", toggle);
    if (textToggle) textToggle.addEventListener("click", toggle);
  }

  function bindReplyFoldToggles(container) {
    container.querySelectorAll(".reply-card").forEach((card) => {
      const topBtn = card.querySelector(".reply-fold");
      const bottomBtn = card.querySelector(".reply-text-toggle");

      if (topBtn || bottomBtn) {
        function toggle(e) {
          if (e) e.stopPropagation();
          const isCollapsed = card.classList.contains("collapsed");
          card.classList.toggle("collapsed", !isCollapsed);
          const label = isCollapsed ? "Collapse ↑" : "Show more ↓";
          if (topBtn) topBtn.textContent = label;
          if (bottomBtn) bottomBtn.textContent = label;
        }
        if (topBtn) topBtn.addEventListener("click", toggle);
        if (bottomBtn) bottomBtn.addEventListener("click", toggle);
      }

      // Copy button on reply card
      const copyBtn = card.querySelector(".reply-copy");
      if (copyBtn) {
        copyBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          const textEl = card.querySelector(".msg-text");
          if (!textEl) return;
          navigator.clipboard.writeText(textEl.innerText).then(() => {
            copyBtn.textContent = "✅";
            setTimeout(() => { copyBtn.textContent = "📋"; }, 1500);
          });
        });
      }
    });
  }

  function bindToolToggles(container) {
    container.querySelectorAll(".tool-header, .thinking-header").forEach((header) => {
      header.addEventListener("click", () => {
        const body = header.nextElementSibling;
        const toggle = header.querySelector(".tool-toggle");
        if (body) body.style.display = body.style.display === "none" ? "" : "none";
        if (toggle) toggle.classList.toggle("open");
      });
    });
  }

  function bindTurnCollapseToggle(container) {
    const bar = container.querySelector(".turn-collapse-bar");
    if (!bar) return;
    bar.addEventListener("click", () => {
      const body = container.querySelector(".turn-body");
      const toggle = bar.querySelector(".turn-collapse-toggle");
      if (!body) return;
      const isOpen = toggle.classList.contains("open");
      body.style.display = isOpen ? "none" : "";
      toggle.classList.toggle("open", !isOpen);
      bar.classList.toggle("collapsed", isOpen);
    });
  }

  function bindToolGroupToggles(container) {
    container.querySelectorAll(".tool-group-header").forEach((header) => {
      header.addEventListener("click", () => {
        const group = header.parentElement;
        const body = group.querySelector(".tool-group-body");
        const toggle = header.querySelector(".tool-group-toggle");
        if (!body) return;
        const isCollapsed = body.style.display === "none";
        body.style.display = isCollapsed ? "" : "none";
        if (toggle) toggle.classList.toggle("open", isCollapsed);
        group.classList.toggle("collapsed", !isCollapsed);
      });
    });
  }

  function renderToolUse(block) {
    const inputStr = typeof block.input === "string"
      ? block.input
      : JSON.stringify(block.input, null, 2);
    // Tool-type CSS class for color coding
    const toolClass = getToolClass(block.name);
    // Tool-specific icon
    const icon = getToolIcon(block.name);
    // Determine a concise summary for the tool header
    let summary = "";
    if (block.input) {
      if (block.input.command) summary = block.input.command.substring(0, 80);
      else if (block.input.file_path) summary = block.input.file_path;
      else if (block.input.pattern) summary = block.input.pattern;
      else if (block.input.query) summary = block.input.query.substring(0, 60);
      else if (block.input.description) summary = block.input.description.substring(0, 60);
      else if (block.input.prompt) summary = block.input.prompt.substring(0, 60);
    }
    // For Agent, show only the prompt in body
    const isAgent = (block.name || "").toLowerCase() === "agent";
    const bodyContent = isAgent && block.input && block.input.prompt
      ? block.input.prompt
      : inputStr;
    return `
      <div class="tool-block ${toolClass}">
        <div class="tool-header">
          <span class="tool-icon">${icon}</span>
          <span class="tool-name">${esc(block.name)}</span>
          ${summary ? `<span style="color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:400px">${esc(summary)}</span>` : ""}
          <span class="tool-toggle">▶</span>
        </div>
        <div class="tool-body${isAgent ? ' agent-prompt' : ''}" style="display:none">${esc(bodyContent)}</div>
      </div>`;
  }

  function getToolClass(name) {
    const n = (name || "").toLowerCase();
    if (n === "bash") return "tool-bash";
    if (n === "read") return "tool-read";
    if (n === "edit") return "tool-edit";
    if (n.includes("grep")) return "tool-grep";
    if (n === "write") return "tool-write";
    if (n === "agent") return "tool-agent";
    if (n === "glob") return "tool-glob";
    return "";
  }

  function getToolIcon(name) {
    const n = (name || "").toLowerCase();
    if (n === "bash") return "⚡";
    if (n === "read") return "📖";
    if (n === "edit") return "✏️";
    if (n.includes("grep")) return "🔍";
    if (n === "write") return "📝";
    if (n === "agent") return "🤖";
    if (n === "glob") return "📁";
    if (n.includes("todo")) return "📋";
    if (n.includes("web") || n.includes("fetch")) return "🌐";
    if (n.includes("skill")) return "⚙️";
    return "🔧";
  }

  function renderToolResult(block) {
    const content = typeof block.content === "string" ? block.content : JSON.stringify(block.content);
    return `
      <div class="tool-block tool-result">
        <div class="tool-header">
          <span class="tool-icon">📋</span>
          <span class="tool-name">Result</span>
          <span class="tool-toggle">▶</span>
        </div>
        <div class="tool-body" style="display:none">${esc(content)}</div>
      </div>`;
  }

  function renderThinking(block) {
    return `
      <div class="thinking-block">
        <div class="thinking-header">
          <span>💭</span>
          <span>Thinking…</span>
          <span class="tool-toggle">▶</span>
        </div>
        <div class="thinking-body" style="display:none">${esc(block.text)}</div>
      </div>`;
  }

  // ── User-only filter ───────────────────────────────────────────
  function applyUserOnlyFilter() {
    $$(".msg").forEach((el) => {
      if (userOnlyMode) {
        // Show only user messages, hide assistant turns
        const isUser = el.classList.contains("user-msg");
        el.style.display = isUser ? "" : "none";
      } else {
        el.style.display = "";
      }
    });
  }

  // ── Search ─────────────────────────────────────────────────────
  async function doSearch(query) {
    if (!query || query.length < 2) {
      if (!currentSessionId) showView("sessions");
      return;
    }

    // Cancel any in-flight search
    if (_searchAbort) _searchAbort.abort();
    _searchAbort = new AbortController();

    showView("search");
    searchResultsList.innerHTML = '<li style="padding:20px;color:var(--text-muted)">Searching…</li>';

    let results;
    try {
      const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}`, { signal: _searchAbort.signal });
      if (!resp.ok) throw new Error(`API error: ${resp.status}`);
      results = await resp.json();
    } catch (err) {
      if (err.name === "AbortError") return; // superseded by newer search
      searchResultsList.innerHTML = `<li style="padding:20px;color:#e57373">Search failed: ${esc(err.message)}</li>`;
      return;
    }

    lastSearchResults = results;
    lastSearchQuery = query;
    renderSearchResults();
  }

  function renderSearchResults() {
    const results = lastSearchResults;
    const query = lastSearchQuery;
    searchResultCount.textContent = `${results.length} results`;

    if (results.length === 0) {
      searchResultsList.innerHTML = '<li style="padding:20px;color:var(--text-muted)">No results found.</li>';
      return;
    }

    const sorted = [...results];
    const sortMode = searchSortSelect.value;
    const ts = r => r.timestamp || r.date || "";
    if (sortMode === "date-desc") {
      sorted.sort((a, b) => ts(b).localeCompare(ts(a)));
    } else if (sortMode === "date-asc") {
      sorted.sort((a, b) => ts(a).localeCompare(ts(b)));
    }
    // "relevance" keeps original backend order

    searchResultsList.innerHTML = "";
    sorted.forEach((r) => {
      const li = document.createElement("li");
      const dateStr = r.date ? formatDate(r.date) : "";
      const snippet = highlightQuery(r.snippet, query);
      li.innerHTML = `
        <div class="sr-title">${esc(r.title)}</div>
        <div class="sr-project">${esc(r.project)} · ${dateStr}</div>
        <div class="sr-snippet">${snippet}</div>
      `;
      li.addEventListener("click", () => {
        searchInput.value = "";
        loadSession(r.sessionId, r.messageIndex);
      });
      searchResultsList.appendChild(li);
    });
  }

  function highlightQuery(text, query) {
    if (!query) return esc(text);
    const escaped = esc(text);
    const qEsc = escRegex(query);
    return escaped.replace(new RegExp(qEsc, "gi"), (m) => `<mark>${m}</mark>`);
  }

  // ── Jump to message ────────────────────────────────────────────
  function jumpToMessage(idx) {
    const el = document.getElementById(`msg-${idx}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.style.outline = "2px solid var(--search-highlight)";
    el.style.outlineOffset = "2px";
    setTimeout(() => {
      el.style.outline = "";
      el.style.outlineOffset = "";
    }, 3000);
  }

  // ── Utilities ──────────────────────────────────────────────────
  function esc(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function escRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function formatDate(isoStr) {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric", year: "numeric" });
    } catch { return isoStr; }
  }

  function formatTime(isoStr) {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    } catch { return ""; }
  }

  function formatSize(bytes) {
    if (!bytes) return "";
    if (bytes < 1024) return bytes + "B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(0) + "KB";
    return (bytes / 1048576).toFixed(1) + "MB";
  }

  function renderMarkdown(text, opts) {
    if (!text) return "";
    const wrapParagraphs = opts && opts.wrapParagraphs;
    // Extract code blocks BEFORE escaping to preserve raw content
    const codeBlocks = [];
    let s = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const idx = codeBlocks.length;
      codeBlocks.push(`<pre${wrapParagraphs ? '' : ' class="md-pre"'}><code>${esc(code)}</code></pre>`);
      return `\x00CB${idx}\x00`;
    });
    // Extract inline code before escaping
    const inlineCode = [];
    s = s.replace(/`([^`]+)`/g, (_, code) => {
      const idx = inlineCode.length;
      inlineCode.push(`<code${wrapParagraphs ? '' : ' class="md-code"'}>${esc(code)}</code>`);
      return `\x00IC${idx}\x00`;
    });
    // Now escape the rest
    s = esc(s);
    // Bold
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Headings
    s = s.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    s = s.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    s = s.replace(/^# (.+)$/gm, '<h2>$1</h2>');
    // Horizontal rule (always apply)
    s = s.replace(/^---$/gm, '<hr>');
    // List items
    s = s.replace(/^[*-] (.+)$/gm, '<li>$1</li>');
    s = s.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    s = s.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
    // Paragraph wrapping or simple line breaks
    if (wrapParagraphs) {
      s = s.replace(/\n{2,}/g, '</p><p>');
      s = s.replace(/\n/g, '<br>');
      s = '<p>' + s + '</p>';
      s = s.replace(/<p>\s*<(h[234]|pre|ul|hr)/g, '<$1');
      s = s.replace(/<\/(h[234]|pre|ul|hr)>\s*<\/p>/g, '</$1>');
      s = s.replace(/<p>\s*<\/p>/g, '');
    } else {
      s = s.replace(/\n/g, '<br>');
    }
    // Restore code blocks and inline code
    s = s.replace(/\x00CB(\d+)\x00/g, (_, i) => codeBlocks[+i]);
    s = s.replace(/\x00IC(\d+)\x00/g, (_, i) => inlineCode[+i]);
    return s;
  }

  // ── Keyboard Navigation (F5) ────────────────────────────────────
  function handleKeyboard(e) {
    const tag = document.activeElement?.tagName;
    const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

    // ? — help overlay (always works)
    if (e.key === "?" && !isInput) {
      e.preventDefault();
      kbdHelp.classList.toggle("hidden");
      return;
    }
    // Esc — close help, blur search, or go home
    if (e.key === "Escape") {
      if (!kbdHelp.classList.contains("hidden")) { kbdHelp.classList.add("hidden"); return; }
      if (isInput) { searchInput.blur(); searchInput.value = ""; return; }
      showView("sessions"); history.pushState({ view: "sessions" }, "", window.location.pathname);
      return;
    }
    // Don't handle when typing in input
    if (isInput) {
      if (e.key === "/" && document.activeElement === searchInput) return;
      return;
    }

    switch (e.key) {
      case "/":
        e.preventDefault();
        searchInput.focus();
        break;
      case "j": // next session
        navigateSession(1);
        break;
      case "k": // prev session
        navigateSession(-1);
        break;
      case "Enter": { // open selected session
        const active = sessionList.querySelector("li.active");
        if (active) loadSession(active.dataset.id);
        break;
      }
      case "h": // go back
        showView("sessions");
        history.replaceState(null, "", window.location.pathname);
        break;
      case "n": // next user message
        navigateUserMessage(1);
        break;
      case "N": // prev user message
        navigateUserMessage(-1);
        break;
      case "1": // Sessions
        showView("sessions");
        break;
      case "2": // AI Evolve
        showView("ai"); initAiPage();
        break;
      case "3": // Insights
        openInsights();
        break;
      case "4": // Digital Twin
        showView("twin");
        break;
      case "o": // outline
        if (!convView.classList.contains("hidden")) toggleOutline();
        break;
      case "c": // ask AI about session
        if (!convView.classList.contains("hidden")) openSessionAiPanel();
        break;
    }
  }

  function navigateSession(direction) {
    const items = Array.from(sessionList.querySelectorAll("li"));
    if (!items.length) return;
    const activeIdx = items.findIndex(li => li.classList.contains("active"));
    let nextIdx = activeIdx + direction;
    if (nextIdx < 0) nextIdx = 0;
    if (nextIdx >= items.length) nextIdx = items.length - 1;
    items.forEach(li => li.classList.remove("active"));
    items[nextIdx].classList.add("active");
    items[nextIdx].scrollIntoView({ block: "nearest" });
  }

  function navigateUserMessage(direction) {
    const container = document.getElementById("messages-container");
    if (!container) return;
    const userMsgs = Array.from(container.querySelectorAll(".msg.user-msg"));
    if (!userMsgs.length) return;

    // Find which user message is currently in view
    const containerRect = container.getBoundingClientRect();
    const viewCenter = containerRect.top + containerRect.height / 3;
    let currentIdx = -1;
    for (let i = 0; i < userMsgs.length; i++) {
      const r = userMsgs[i].getBoundingClientRect();
      if (r.top >= viewCenter - 20) { currentIdx = i; break; }
    }
    if (currentIdx === -1) currentIdx = userMsgs.length - 1;

    let targetIdx = direction > 0 ? currentIdx + 1 : currentIdx - 1;
    // Ensure forward actually moves past current
    if (direction > 0 && currentIdx >= 0) {
      const r = userMsgs[currentIdx].getBoundingClientRect();
      if (r.top < viewCenter + 20) targetIdx = currentIdx + 1;
      else targetIdx = currentIdx;
    }
    if (targetIdx < 0) targetIdx = 0;
    if (targetIdx >= userMsgs.length) targetIdx = userMsgs.length - 1;

    userMsgs[targetIdx].scrollIntoView({ behavior: "smooth", block: "start" });
    // Highlight in outline
    highlightOutlineItem(parseInt(userMsgs[targetIdx].dataset.idx));
  }

  // ── Outline Panel (F2) ────────────────────────────────────────
  function toggleOutline() {
    // Panel is always visible; toggle switches to Outline tab
    const current = document.querySelector(".rp-tab.active")?.dataset.panel;
    const target = current === "outline" ? "ai" : "outline";
    document.querySelectorAll(".rp-tab").forEach(t => t.classList.toggle("active", t.dataset.panel === target));
    document.querySelectorAll(".rp-content").forEach(c => c.classList.toggle("hidden", !c.id.endsWith(target)));
  }

  function buildOutline(messages) {
    outlineList.innerHTML = "";
    let userIdx = 0;
    messages.forEach((msg, i) => {
      if (msg.type !== "user") return;
      const text = msg.content.map(b => b.type === "text" ? b.text : "").join(" ").trim();
      if (!text) return;
      userIdx++;
      const li = document.createElement("li");
      li.dataset.msgIdx = i;
      li.innerHTML = `<span class="outline-idx">${userIdx}</span>${esc(text.substring(0, 80))}`;
      li.addEventListener("click", () => {
        jumpToMessage(i);
        highlightOutlineItem(i);
      });
      outlineList.appendChild(li);
    });
  }

  function highlightOutlineItem(msgIdx) {
    outlineList.querySelectorAll("li").forEach(li => {
      li.classList.toggle("active", parseInt(li.dataset.msgIdx) === msgIdx);
    });
  }

  // ── Analytics sub-renderers (used by Insights tabs) ──────────
  function renderHotspotsSection(container, data) {
    if (!data.hotspots?.length) {
      const empty = document.createElement("div");
      empty.style.cssText = "padding:40px;text-align:center;color:var(--text-muted)";
      empty.textContent = "No file hotspot data available.";
      container.appendChild(empty);
      return;
    }
    const section = document.createElement("div");
    section.className = "analytics-section";
    const maxCount = data.hotspots[0].count;
    let html = '<h3><span class="a-icon">🔥</span> File Hotspots</h3>';
    html += '<table class="hotspot-table"><thead><tr><th>File</th><th>Edits</th><th>Sessions</th><th>Frequency</th></tr></thead><tbody>';
    data.hotspots.slice(0, 25).forEach(h => {
      const pct = maxCount > 0 ? (h.count / maxCount * 100) : 0;
      html += `<tr>
        <td><span class="hotspot-path" title="${esc(h.fullPath || h.path)}">${esc(h.path)}</span></td>
        <td>${h.count}</td>
        <td>${h.sessionCount}</td>
        <td><div class="hotspot-bar"><div class="hotspot-bar-fill" style="width:${pct}%"></div></div></td>
      </tr>`;
    });
    html += '</tbody></table>';
    section.innerHTML = html;
    container.appendChild(section);
  }

  function renderHeatmapSection(container, data) {
    if (!data.heatmap?.days?.length || !data.heatmap?.tools?.length) {
      const empty = document.createElement("div");
      empty.style.cssText = "padding:40px;text-align:center;color:var(--text-muted)";
      empty.textContent = "No heatmap data available.";
      container.appendChild(empty);
      return;
    }
    const section = document.createElement("div");
    section.className = "analytics-section";
    const hm = data.heatmap;
    let html = '<h3><span class="a-icon">🗓️</span> Tool Usage Heatmap <span style="font-size:11px;font-weight:400;color:var(--text-muted)">(last 30 days)</span></h3>';
    let maxVal = 0;
    hm.days.forEach(day => { hm.tools.forEach(t => { maxVal = Math.max(maxVal, hm.data[day]?.[t] || 0); }); });

    html += `<div class="heatmap-grid" style="grid-template-columns: 80px repeat(${hm.days.length}, 1fr);">`;
    html += '<div></div>';
    hm.days.forEach(day => {
      html += `<div class="heatmap-day-label">${day.slice(5)}</div>`;
    });
    hm.tools.forEach(tool => {
      html += `<div class="heatmap-label">${esc(tool)}</div>`;
      hm.days.forEach(day => {
        const val = hm.data[day]?.[tool] || 0;
        const intensity = maxVal > 0 ? val / maxVal : 0;
        const bg = val > 0 ? `rgba(88,86,214,${0.1 + intensity * 0.8})` : 'var(--bg-surface2)';
        const color = intensity > 0.5 ? '#fff' : 'var(--text-muted)';
        html += `<div class="heatmap-cell" style="background:${bg};color:${color}" title="${tool}: ${val} calls on ${day}">${val || ''}</div>`;
      });
    });
    html += '</div>';

    html += '<div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">';
    hm.tools.forEach(tool => {
      const total = hm.totals[tool] || 0;
      html += `<span style="font-size:12px;padding:3px 8px;background:var(--bg-surface2);border-radius:12px;color:var(--text-secondary)"><strong>${esc(tool)}</strong> ${total}</span>`;
    });
    html += '</div>';

    section.innerHTML = html;
    container.appendChild(section);
  }

  function renderErrorsSection(container, data) {
    if (!data.errors?.length) {
      const empty = document.createElement("div");
      empty.style.cssText = "padding:40px;text-align:center;color:var(--text-muted)";
      empty.textContent = "No error patterns found.";
      container.appendChild(empty);
      return;
    }
    const section = document.createElement("div");
    section.className = "analytics-section";
    let html = '<h3><span class="a-icon">⚠️</span> Error Patterns</h3>';
    html += '<ul class="error-list">';
    data.errors.forEach(e => {
      html += `<li class="error-item">
        <div class="error-pattern">${esc(e.pattern)}</div>
        <div class="error-meta">
          <span><strong>${e.count}</strong> occurrences</span>
          <span><strong>${e.sessionCount}</strong> sessions</span>
          <span>${e.firstSeen} → ${e.lastSeen}</span>
          <span>${e.projects.join(', ')}</span>
        </div>
      </li>`;
    });
    html += '</ul>';
    section.innerHTML = html;
    container.appendChild(section);
  }

  function renderProjectHealthInto(container, data) {
    container.innerHTML = "";
    if (!data.projects?.length) {
      container.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-muted)">No project data.</div>';
      return;
    }
    const sec = document.createElement("div");
    sec.className = "analytics-section";
    let html = '<h3><span class="a-icon">🏥</span> Project Health Dashboard</h3>';
    html += `<table class="health-table"><thead><tr>
      <th>Project</th><th>Source</th><th>Sessions</th><th>Messages</th><th>Recent (7d)</th><th>Last Active</th><th>Trend</th><th>Status</th>
    </tr></thead><tbody>`;
    data.projects.forEach(p => {
      const trendIcon = p.trend === "up" ? "📈" : p.trend === "down" ? "📉" : "➡️";
      let staleClass = "fresh";
      let staleLabel = `${p.staleDays}d ago`;
      if (p.staleDays > 30) { staleClass = "stale"; staleLabel = `${p.staleDays}d`; }
      else if (p.staleDays > 7) { staleClass = "recent"; }
      else if (p.staleDays <= 1) { staleLabel = "today"; }
      html += `<tr>
        <td><span class="health-name">${esc(p.name)}</span></td>
        <td><span class="source-badge ${p.source}">${esc(p.source)}</span></td>
        <td>${p.sessionCount}</td>
        <td>${p.totalMessages}</td>
        <td>${p.recentSessions}</td>
        <td>${esc(p.lastSeen)}</td>
        <td class="health-trend">${trendIcon}</td>
        <td><span class="health-stale ${staleClass}">${staleLabel}</span></td>
      </tr>`;
    });
    html += '</tbody></table>';
    sec.innerHTML = html;
    container.appendChild(sec);
  }

  function renderSnippetsInto(container, data) {
    container.innerHTML = "";
    if (!data.snippets?.length) {
      container.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-muted)">No code snippets found.</div>';
      return;
    }
    const appliedCount = data.snippets.filter(s => s.applied).length;
    const toolbar = document.createElement("div");
    toolbar.style.cssText = "margin-bottom:16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap";
    toolbar.innerHTML = `
      <input type="text" id="snippet-search" placeholder="Search snippets…" style="flex:1;min-width:200px;padding:6px 12px;border:1px solid var(--border-light);border-radius:var(--radius-sm);font-size:13px;background:var(--bg-surface);outline:none">
      <button class="snippet-filter-btn active" data-filter="all">All (${data.snippets.length})</button>
      <button class="snippet-filter-btn" data-filter="applied">✅ Applied (${appliedCount})</button>
      <button class="snippet-filter-btn" data-filter="suggested">Suggested (${data.snippets.length - appliedCount})</button>`;
    container.appendChild(toolbar);

    const listDiv = document.createElement("div");
    listDiv.id = "snippet-list";
    container.appendChild(listDiv);

    let currentFilter = "all";
    function renderList(items) {
      listDiv.innerHTML = "";
      items.forEach(s => {
        const card = document.createElement("div");
        card.className = "snippet-card";
        const badge = s.applied
          ? '<span class="snippet-badge applied">✅ Applied</span>'
          : '<span class="snippet-badge suggested">Suggested</span>';
        card.innerHTML = `
          <div class="snippet-header">
            <span class="snippet-lang">${esc(s.language || "code")}</span>
            ${badge}
            <span class="snippet-context">${esc(s.context)}</span>
            <span class="snippet-meta">${esc(s.project)} · ${formatDate(s.date)}</span>
          </div>
          <div class="snippet-code-wrap">
            <div class="snippet-code">${esc(s.code)}</div>
            <button class="snippet-copy" title="Copy code">📋</button>
          </div>`;
        card.querySelector(".snippet-header").addEventListener("click", () => loadSession(s.sessionId));
        card.querySelector(".snippet-copy").addEventListener("click", (e) => {
          e.stopPropagation();
          navigator.clipboard.writeText(s.code).then(() => {
            const btn = card.querySelector(".snippet-copy");
            btn.textContent = "✓";
            setTimeout(() => { btn.textContent = "📋"; }, 1500);
          });
        });
        listDiv.appendChild(card);
      });
    }

    function applyFilters() {
      const q = (container.querySelector("#snippet-search")?.value || "").toLowerCase();
      let items = data.snippets;
      if (currentFilter === "applied") items = items.filter(s => s.applied);
      else if (currentFilter === "suggested") items = items.filter(s => !s.applied);
      if (q) items = items.filter(s =>
        (s.code || '').toLowerCase().includes(q) || (s.context || '').toLowerCase().includes(q) ||
        (s.language || '').toLowerCase().includes(q) || (s.project || '').toLowerCase().includes(q)
      );
      renderList(items);
    }

    renderList(data.snippets);
    toolbar.querySelectorAll(".snippet-filter-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        currentFilter = btn.dataset.filter;
        toolbar.querySelectorAll(".snippet-filter-btn").forEach(b => b.classList.toggle("active", b === btn));
        applyFilters();
      });
    });
    container.querySelector("#snippet-search")?.addEventListener("input", applyFilters);
  }

  // ── Insights Page (tabbed) ─────────────────────────────────────
  function openInsights() {
    showView("insights");
    bindInsightsTabs();
    loadInsightsTab(insightsActiveTab);
  }

  let _insightsTabsBound = false;
  function bindInsightsTabs() {
    if (_insightsTabsBound) return;
    _insightsTabsBound = true;
    document.querySelectorAll(".insights-tab").forEach(tab => {
      tab.addEventListener("click", () => {
        insightsActiveTab = tab.dataset.tab;
        document.querySelectorAll(".insights-tab").forEach(t => t.classList.toggle("active", t.dataset.tab === insightsActiveTab));
        loadInsightsTab(insightsActiveTab);
      });
    });
  }

  async function loadInsightsTab(tab) {
    const body = document.getElementById("insights-body");
    if (!body) return;
    body.innerHTML = '<div class="insights-loading"><div class="skeleton-block"></div><div class="skeleton-block" style="width:80%"></div><div class="skeleton-block" style="width:60%"></div></div>';

    try {
      if (tab === "hotspots" || tab === "heatmap" || tab === "errors") {
        if (!insightsDataCache.analytics) {
          insightsDataCache.analytics = await api("/api/analytics");
        }
        const data = insightsDataCache.analytics;
        body.innerHTML = "";
        if (tab === "hotspots") renderHotspotsSection(body, data);
        else if (tab === "heatmap") renderHeatmapSection(body, data);
        else renderErrorsSection(body, data);
      } else if (tab === "health") {
        if (!insightsDataCache.health) {
          insightsDataCache.health = await api("/api/project-health");
        }
        renderProjectHealthInto(body, insightsDataCache.health);
      } else if (tab === "snippets") {
        if (!insightsDataCache.snippets) {
          insightsDataCache.snippets = await api("/api/snippets");
        }
        renderSnippetsInto(body, insightsDataCache.snippets);
      }
    } catch (err) {
      body.innerHTML = `<div style="padding:40px;text-align:center;color:#e57373">Failed: ${esc(err.message)}</div>`;
    }
  }

  // ── F11: Session Summary (Request vs Reality) ──────────────────
  async function loadSessionSummary(sessionId) {
    const body = document.getElementById("summary-body");
    if (!body) return;
    body.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--text-muted)">Loading…</div>';

    try {
      const data = await api(`/api/session-summary?session=${sessionId}`);
      renderSessionSummary(data, body);
    } catch (err) {
      body.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--text-muted)">—</div>';
    }
  }

  function renderSessionSummary(data, body) {
    body.innerHTML = "";
    // Request
    if (data.request) {
      const sec = document.createElement("div");
      sec.className = "insight-section";
      sec.innerHTML = `<h4>📝 Initial Request</h4><div class="summary-request">${esc(data.request)}</div>`;
      body.appendChild(sec);
    }
    // Files touched
    if (data.files?.length) {
      const sec = document.createElement("div");
      sec.className = "insight-section";
      let html = `<h4>📁 Files Touched (${data.files.length})</h4><ul class="summary-files">`;
      data.files.forEach(f => {
        const badges = [];
        if (f.edits) badges.push(`<span class="sf-badge edit">${f.edits} edit</span>`);
        if (f.writes) badges.push(`<span class="sf-badge write">${f.writes} write</span>`);
        if (f.reads) badges.push(`<span class="sf-badge read">${f.reads} read</span>`);
        html += `<li class="summary-file"><span class="sf-path" title="${esc(f.path)}">${esc(f.path)}</span>${badges.join("")}</li>`;
      });
      html += '</ul>';
      sec.innerHTML = html;
      body.appendChild(sec);
    }
    // Tool summary
    if (data.tools && Object.keys(data.tools).length) {
      const sec = document.createElement("div");
      sec.className = "insight-section";
      const sorted = Object.entries(data.tools).sort((a, b) => b[1] - a[1]);
      let html = '<h4>🔧 Tool Usage</h4><div style="display:flex;gap:6px;flex-wrap:wrap">';
      sorted.forEach(([name, count]) => {
        html += `<span style="font-size:11px;padding:3px 7px;background:var(--bg-surface2);border-radius:10px">${esc(name)} <strong>${count}</strong></span>`;
      });
      html += '</div>';
      sec.innerHTML = html;
      body.appendChild(sec);
    }
  }

  // ── AI Chat (Dual Surface) ──────────────────────────────────────
  // Surface A: Session AI — lives in right panel AI tab
  // Surface B: Global AI — standalone view for cross-session analysis

  /** Auto-resize textarea to content */
  function autoResizeTextarea(el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, parseInt(getComputedStyle(el).maxHeight) || 120) + "px";
  }

  /** Markdown renderer with paragraph wrapping (for chat bubbles, modals) */
  function renderMarkdownSimple(text) {
    return renderMarkdown(text, { wrapParagraphs: true });
  }

  /** Append a chat message bubble to a container */
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
    const close = modal.querySelector(".msg-modal-close");
    const backdrop = modal.querySelector(".msg-modal-backdrop");
    const controller = new AbortController();
    function closeModal() {
      modal.classList.add("hidden");
      controller.abort();
    }
    if (close) close.addEventListener("click", closeModal, { signal: controller.signal });
    if (backdrop) backdrop.addEventListener("click", closeModal, { signal: controller.signal });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeModal();
    }, { signal: controller.signal });
  }

  /** Show loading indicator in a container, return the element for later removal */
  function showChatLoading(container, description) {
    const el = document.createElement("div");
    el.className = "chat-msg assistant";
    el.innerHTML = `<div class="chat-bubble"><div class="chat-loading"><span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="chat-loading-text">${esc(description)}</span></div></div>`;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
    return el;
  }

  // ── Smart auto-scroll ──────────────────────────────────────
  function _shouldAutoScroll(container) {
    return container.scrollHeight - container.scrollTop - container.clientHeight < 80;
  }
  function _autoScroll(container) {
    if (_shouldAutoScroll(container)) {
      container.scrollTop = container.scrollHeight;
    }
  }

  /**
   * Create a ChatGPT-style assistant turn: a vertical stream of
   * tool-cards and text-blocks, appended as SSE events arrive.
   * Returns {addTool(evt), updateText(accumulated), finalize(fullText)}
   */
  function createAssistantTurn(container) {
    const turn = document.createElement("div");
    turn.className = "assistant-turn";

    // Init indicator
    const initEl = document.createElement("div");
    initEl.className = "turn-init";
    initEl.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="turn-init-text">Thinking…</span>';
    turn.appendChild(initEl);

    container.appendChild(turn);
    _autoScroll(container);

    let _currentTextBlock = null; // the active .text-block element
    let _blockText = ""; // text accumulated for the CURRENT block only
    let _renderTimer = null;
    let _started = false;
    let _runningCards = []; // queue of running tool cards (FIFO for done matching)

    function _ensureStarted() {
      if (!_started) {
        _started = true;
        if (initEl.parentNode) initEl.remove();
      }
    }

    function _ensureTextBlock() {
      if (!_currentTextBlock) {
        _currentTextBlock = document.createElement("div");
        _currentTextBlock.className = "text-block";
        _currentTextBlock.innerHTML = '<span class="stream-cursor">▍</span>';
        turn.appendChild(_currentTextBlock);
      }
      return _currentTextBlock;
    }

    return {
      el: turn,

      addTool(evt) {
        _ensureStarted();

        if (evt.status === "running") {
          // Remove cursor from the previous text block
          if (_currentTextBlock) {
            const cursor = _currentTextBlock.querySelector(".stream-cursor");
            if (cursor) cursor.remove();
          }
          // Reset per-block accumulator; close current text block
          _blockText = "";
          _currentTextBlock = null;
          // Create a new tool card
          const card = document.createElement("div");
          card.className = "tool-card running";
          const detail = evt.detail ? esc(evt.detail) : "";
          card.innerHTML = `<div class="tool-card-header"><span class="tool-status-dot"></span><span class="tool-card-name">${esc(evt.name)}</span><span class="tool-card-detail">${detail}</span><span class="tool-card-chevron">›</span></div><div class="tool-card-body"><pre class="tool-card-output"></pre></div>`;
          turn.appendChild(card);
          _runningCards.push(card);
        } else if (evt.status === "done" && _runningCards.length) {
          // Complete the oldest running card (FIFO)
          const card = _runningCards.shift();
          card.classList.remove("running");
          card.classList.add("done");
          // Update output if provided
          if (evt.detail) {
            const outputEl = card.querySelector(".tool-card-output");
            if (outputEl) outputEl.textContent = evt.detail;
          }
          // Make it collapsible
          const header = card.querySelector(".tool-card-header");
          if (header) {
            header.onclick = () => card.classList.toggle("expanded");
          }
        }
        _autoScroll(container);
      },

      updateText(chunk) {
        _ensureStarted();
        _blockText += chunk;
        const block = _ensureTextBlock();
        if (!_renderTimer) {
          _renderTimer = requestAnimationFrame(() => {
            _renderTimer = null;
            block.innerHTML = renderMarkdownSimple(_blockText) + '<span class="stream-cursor">▍</span>';
            _autoScroll(container);
          });
        }
      },

      finalize(fullText) {
        _ensureStarted();
        turn.classList.add("done");
        // Remove all streaming cursors from earlier blocks
        turn.querySelectorAll(".stream-cursor").forEach(c => c.remove());
        // Render final block text (without cursor)
        if (_blockText || fullText) {
          const block = _ensureTextBlock();
          block.innerHTML = renderMarkdownSimple(_blockText || fullText);
          // Add action buttons
          const actions = document.createElement("div");
          actions.className = "text-block-actions";
          const expandBtn = document.createElement("button");
          expandBtn.className = "text-action-btn";
          expandBtn.textContent = "⤢";
          expandBtn.title = "Full screen";
          expandBtn.onclick = (e) => { e.stopPropagation(); openMsgModal(fullText); };
          actions.appendChild(expandBtn);
          const copyBtn = document.createElement("button");
          copyBtn.className = "text-action-btn";
          copyBtn.textContent = "📋";
          copyBtn.title = "Copy";
          copyBtn.onclick = () => {
            navigator.clipboard.writeText(fullText).then(() => {
              copyBtn.textContent = "✓";
              setTimeout(() => { copyBtn.textContent = "📋"; }, 1500);
            });
          };
          actions.appendChild(copyBtn);
          block.appendChild(actions);
        } else if (initEl.parentNode) {
          initEl.remove(); // clean up if no content at all
        }
        _autoScroll(container);
      },
    };
  }

  /** Send chat request to backend (legacy non-streaming) */
  function sendChatRequest(prompt, contextType, sessionId, scope) {
    const body = {prompt, contextType, sessionId: sessionId || null};
    if (scope) body.scope = scope;
    return fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    }).then(r => r.json());
  }

  /**
   * Stream a chat request via SSE. Returns an object with:
   *   .onText(fn)  — called with accumulated text on each text chunk
   *   .onTool(fn)  — called with {name, status, detail} for tool events
   *   .onDone(fn)  — called with final full text
   *   .onError(fn) — called with error message
   *   .abort()     — cancel the stream
   */
  function sendChatStream(prompt, contextType, sessionId, scope, messages) {
    const body = {prompt, contextType, sessionId: sessionId || null, timeout: chatTimeout};
    if (scope) body.scope = scope;
    if (messages && messages.length) body.messages = messages;
    const callbacks = { text: null, tool: null, done: null, error: null, abort: null };
    const controller = new AbortController();

    const handle = {
      onText(fn) { callbacks.text = fn; return handle; },
      onTool(fn) { callbacks.tool = fn; return handle; },
      onDone(fn) { callbacks.done = fn; return handle; },
      onError(fn) { callbacks.error = fn; return handle; },
      onAbort(fn) { callbacks.abort = fn; return handle; },
      abort() { controller.abort(); },
    };

    const state = { text: "" }; // accumulator shared across events

    fetch("/api/chat/stream", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
      signal: controller.signal,
    }).then(response => {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      function pump() {
        return reader.read().then(({done, value}) => {
          if (done) return;
          buffer += decoder.decode(value, {stream: true});
          // Parse SSE events (data: ...\n\n)
          const parts = buffer.split("\n\n");
          buffer = parts.pop(); // keep incomplete part
          for (const part of parts) {
            const lines = part.split("\n");
            for (const line of lines) {
              if (line.startsWith("data: ")) {
                try {
                  const evt = JSON.parse(line.slice(6));
                  _handleStreamEvent(evt, callbacks, state);
                } catch (e) { /* skip malformed */ }
              }
            }
          }
          return pump();
        });
      }
      return pump();
    }).catch(err => {
      if (err.name === "AbortError") {
        if (callbacks.abort) callbacks.abort(state.text);
      } else if (callbacks.error) {
        callbacks.error(err.message);
      }
    });

    return handle;
  }

  function _appendContinueButton(container, onClick) {
    const wrap = document.createElement("div");
    wrap.className = "chat-continue-wrap";
    const btn = document.createElement("button");
    btn.className = "btn-continue";
    btn.textContent = "继续分析";
    btn.addEventListener("click", () => {
      wrap.remove();
      onClick();
    });
    wrap.appendChild(btn);
    container.appendChild(wrap);
    _autoScroll(container);
  }

  function _handleStreamEvent(evt, callbacks, state) {
    switch (evt.type) {
      case "text":
        state.text += evt.content;
        if (callbacks.text) callbacks.text(evt.content);
        break;
      case "tool":
        if (callbacks.tool) callbacks.tool(evt);
        break;
      case "result":
        state.text = evt.content;
        break;
      case "done":
        if (callbacks.done) callbacks.done(evt.content || state.text);
        break;
      case "timeout":
        // Timeout with partial text — treat as done-with-partial so history is preserved
        state.text = evt.content || state.text;
        if (callbacks.done) callbacks.done(state.text, true); // second arg = isTimeout
        break;
      case "error":
        if (callbacks.error) callbacks.error(evt.message);
        break;
    }
  }

  // ── Session AI (right panel) ──────────────────────────────────

  /** Open right panel → AI tab */
  function openSessionAiPanel() {
    if (!currentSessionId) return;
    // Switch to AI tab + widen panel
    document.querySelectorAll(".rp-tab").forEach(t => t.classList.toggle("active", t.dataset.panel === "ai"));
    document.querySelectorAll(".rp-content").forEach(c => c.classList.toggle("hidden", !c.id.endsWith("ai")));
    // Update header
    updateSessionAiHeader();
    // Restore session chat history
    restoreSessionAiMessages();
    // Focus input
    const input = $("#session-ai-input");
    if (input) setTimeout(() => input.focus(), 100);
  }

  function updateSessionAiHeader() {}

  function restoreSessionAiMessages() {
    const container = $("#session-ai-messages");
    if (!container) return;
    container.innerHTML = "";
    const cache = sessionChatCache[currentSessionId];
    if (cache && cache.messages.length) {
      cache.messages.forEach(m => appendChatMsg(container, m.role, m.content));
      // Hide presets if there are messages
      const presets = $("#session-ai-presets");
      if (presets) presets.style.display = "none";
    } else {
      const presets = $("#session-ai-presets");
      if (presets) presets.style.display = "";
    }
  }

  function submitSessionAi(prompt) {
    const input = $("#session-ai-input");
    const text = prompt || (input ? input.value.trim() : "");
    if (!text || sessionAiLoading || !currentSessionId) return;
    if (input) { input.value = ""; autoResizeTextarea(input); }

    const container = $("#session-ai-messages");
    if (!container) return;

    // Capture session ID at call time (防止 loading 期间切换 session 导致写入错误 cache)
    const targetSessionId = currentSessionId;

    // Init cache for this session
    if (!sessionChatCache[targetSessionId]) {
      sessionChatCache[targetSessionId] = {messages: []};
    }
    const cache = sessionChatCache[targetSessionId];

    // Add user message
    appendChatMsg(container, "user", text);
    cache.messages.push({role: "user", content: text});

    // Hide presets
    const presets = $("#session-ai-presets");
    if (presets) presets.style.display = "none";

    // Show streaming bubble
    sessionAiLoading = true;
    _setSessionAiButton(true);
    const assistantTurn = currentSessionId === targetSessionId
      ? createAssistantTurn(container) : null;
    const handle = sendChatStream(text, "session", targetSessionId, undefined, cache.messages.slice(0, -1));
    sessionAiHandle = handle;
    handle
      .onText(chunk => {
        if (assistantTurn && currentSessionId === targetSessionId) {
          assistantTurn.updateText(chunk);
        }
      })
      .onTool(evt => {
        if (assistantTurn && currentSessionId === targetSessionId) {
          assistantTurn.addTool(evt);
        }
      })
      .onDone((fullText, isTimeout) => {
        if (sessionAiHandle !== handle) return;
        sessionAiLoading = false;
        sessionAiHandle = null;
        _setSessionAiButton(false);
        const reply = fullText || "(empty response)";
        cache.messages.push({role: "assistant", content: reply});
        saveChatToStorage();
        if (assistantTurn && currentSessionId === targetSessionId) {
          assistantTurn.finalize(reply);
          if (isTimeout) _appendContinueButton(container, () => submitSessionAi("继续"));
        }
      })
      .onError(msg => {
        if (sessionAiHandle !== handle) return;
        sessionAiLoading = false;
        sessionAiHandle = null;
        _setSessionAiButton(false);
        const reply = `**Error:** ${msg}`;
        cache.messages.push({role: "assistant", content: reply});
        saveChatToStorage();
        if (assistantTurn && currentSessionId === targetSessionId) {
          assistantTurn.finalize(reply);
        }
      })
      .onAbort(partialText => {
        if (sessionAiHandle !== handle) return;
        sessionAiLoading = false;
        sessionAiHandle = null;
        _setSessionAiButton(false);
        const reply = (partialText || "") + "\n\n*(已停止)*";
        cache.messages.push({role: "assistant", content: reply});
        saveChatToStorage();
        if (assistantTurn && currentSessionId === targetSessionId) {
          assistantTurn.finalize(reply);
          _appendContinueButton(container, () => submitSessionAi("继续"));
        }
      });
  }

  function _setSessionAiButton(loading) {
    const btn = $("#session-ai-send");
    if (!btn) return;
    if (loading) { btn.textContent = "■ Stop"; btn.classList.add("btn-stop"); }
    else { btn.textContent = "Send"; btn.classList.remove("btn-stop"); }
  }

  function _stopSessionAi() {
    if (sessionAiHandle) sessionAiHandle.abort();
    // Don't null sessionAiHandle here — let onAbort callback do cleanup
    // (otherwise the stale-callback guard blocks finalize)
    sessionAiLoading = false;
    _setSessionAiButton(false);
  }

  // ── Global AI (evolve chat panel) ───────────────────────────────

  const GLOBAL_AI_PRESETS = [
    { icon: "📊", title: "本周复盘", desc: "按项目总结完成的功能、Bug修复、重构", prompt: "分析所有对话，生成工作复盘。\n\n**工作流（按顺序执行）**：\n1. 先运行 `highlights` 获取全部会话的一行概览（含纠正/决策信号数）\n2. 运行 `stats` 查看项目分布和统计\n3. 对高信号会话运行 `read -s <id>` 看摘要\n4. 运行 `errors` 看高频错误模式\n\n**输出要求**：\n1. **项目分布**：各项目会话数和主要活动\n2. **关键产出**：每个项目完成的功能/修复\n3. **主要问题**：遇到的阻塞和解决情况\n4. **技术亮点**：有价值的技术方案或突破\n5. **效率观察**：哪些会话高效（低纠正、少消息）、哪些低效（高纠正）\n\n每个发现附 session ID 作为证据锚点。" },
    { icon: "🔄", title: "重复模式", desc: "跨项目的反复 Bug 模式和效率瓶颈", prompt: "深度分析对话历史，找出跨项目反复出现的问题模式。\n\n**工作流（按顺序执行）**：\n1. 运行 `errors` 获取所有错误模式（按频率排序、跨 session 聚合）\n2. 运行 `corrections` 获取用户纠正模式（反映效率瓶颈）\n3. 运行 `highlights` 找高纠正/高消息数的低效会话\n4. 对高频错误和纠正的会话运行 `read -s <id>` 看上下文\n5. 运行 `search \"搜索\"` 和 `search \"怎么\"` 定位知识盲区\n\n**输出要求**：\n1. **高频错误**：同类错误出现2+次的模式\n2. **效率瓶颈**：反复消耗时间的环节\n3. **知识盲区**：多次搜索或询问的领域\n4. **根因分析**：每个模式的根本原因\n5. **改进方案**：具体可执行的改进，按ROI排序" },
    { icon: "📐", title: "规则生成", desc: "从纠正场景自动生成 CLAUDE.md 规则", prompt: "分析所有对话中用户纠正AI的场景，自动生成CLAUDE.md规则。\n\n**工作流（按顺序执行）**：\n1. 先运行 `corrections` 获取所有纠正样本（已含50+种中英文信号词检测）\n2. 运行 `highlights` 找高纠正数的会话（corr≥3的重点关注）\n3. 对高纠正会话运行 `read -s <id>` 看上下文（理解纠正原因）\n4. 补充搜索 `search \"不行\"` `search \"太精简\"` `search \"应该是\"` 等关键词\n\n**输出要求**：\n1. 聚类相似纠正，提取模式\n2. 为每个模式生成规则：规则内容 | 触发场景 | 来源频次\n3. 按出现频率排序，标注优先级 P0/P1/P2\n4. 格式参考 CLAUDE.md 规则写法（可直接粘贴使用）\n\n每条规则附至少一条原始纠正引用（用户原话）和 session ID 作为证据。" },
    { icon: "💡", title: "Prompt 优化", desc: "Prompt 质量评分和协作效率分析", prompt: "分析我的 prompt 质量和 AI 协作效率。\n\n**工作流（按顺序执行）**：\n1. 运行 `highlights` 查看每个会话的消息数和纠正信号数\n2. 运行 `corrections` 获取所有纠正场景（纠正=prompt 不够好）\n3. 对比低纠正会话（corr:0, 消息少）和高纠正会话（corr≥3），用 `read -s <id>` 各看 2-3 个\n4. 运行 `queries --limit 30` 浏览用户 prompt 样本\n\n**输出要求**：\n1. **一次成功率**：哪些类型的 prompt 能一次成功\n2. **多轮纠正**：哪些场景需反复修改，为什么\n3. **高效模式**：好 prompt 的共同特征\n4. **低效模式**：差 prompt 的问题所在\n5. **改进建议**：针对我的习惯的 prompt 模板建议" },
    { icon: "🎯", title: "决策考古", desc: "提取架构决策及理由，生成决策日志", prompt: "提取所有会话中的架构和技术决策，生成决策日志。\n\n**工作流（按顺序执行）**：\n1. 先运行 `decisions` 获取所有决策点样本\n2. 运行 `highlights` 找高决策数的会话（dec≥2的重点关注）\n3. 对关键会话运行 `read -s <id>` 查看决策上下文\n4. 运行 `stats` 了解项目分布，按项目组织决策\n\n**输出要求**：\n1. 按时间线列出所有重要决策\n2. 每个决策：背景、选项、最终选择、理由\n3. 标注跨项目影响的决策\n4. 识别前后矛盾或需重新审视的决策\n5. 输出格式参考 ADR (Architecture Decision Record)\n\n每个 ADR 附 session ID。Top 5 关键决策需展开完整背景/选项/理由。" },
    { icon: "🧠", title: "知识沉淀", desc: "提炼可复用模式和 Memory 候选", prompt: "从对话轨迹中提炼可沉淀的知识。\n\n**工作流（按顺序执行）**：\n1. 运行 `stats` 获取项目分布全景\n2. 运行 `errors` 获取高频错误模式（→踩坑大全候选）\n3. 运行 `corrections` 获取纠正模式（→有效实践候选）\n4. 运行 `highlights` 找信号丰富的会话\n5. 对关键会话运行 `read -s <id>` 提取可复用方案\n6. 运行 `files` 看文件热点（→技能图谱依据）\n\n**输出要求**：\n1. **可复用方案**：跨项目可复用的代码模式\n2. **验证有效的实践**：确认好用的开发实践（附证据：session ID + 关键引用）\n3. **踩坑大全**：高频踩坑及标准解法\n4. **Memory候选**：建议写入记忆的知识（知识内容 | 适用场景 | 来源证据）\n5. **技能图谱**：哪些技术领域积累最深，哪些需加强" },
    { icon: "📈", title: "效率分析", desc: "高花费低产出会话诊断和工作流优化", prompt: "分析 AI 编码效率和成本热点。\n\n**工作流（按顺序执行）**：\n1. 运行 `highlights` 获取全部会话概览，按消息数排序找高耗时会话\n2. 运行 `stats` 看总体数据量（sessions/messages/MB）\n3. 对消息数 Top 5 的会话运行 `read -s <id>` 诊断低效原因\n4. 运行 `corrections` 统计哪些项目纠正最多（纠正=返工成本）\n5. 运行 `files` 看文件编辑热点（高编辑=可能过度修改）\n\n**输出要求**：\n1. **高耗时会话**：消息数最多的 Top 5 会话及主题\n2. **低效原因**：反复修改、方向错误、上下文丢失\n3. **工具使用**：哪些工具被过度使用或使用不足\n4. **对比分析**：高效会话 vs 低效会话的模式差异\n5. **优化建议**：具体的工作流改进建议" },
    { icon: "🔀", title: "工具对比", desc: "Claude Code vs Codex CLI 使用效率对比", prompt: "对比分析 Claude Code 和 Codex CLI 的使用效率。\n\n**工作流（按顺序执行）**：\n1. 运行 `stats --source claude` 和 `stats --source codex` 分别统计\n2. 运行 `highlights --source claude --limit 20` 和 `highlights --source codex --limit 20` 对比\n3. 运行 `corrections --source claude` 和 `corrections --source codex` 对比纠正率\n4. 运行 `files --source claude` 和 `files --source codex` 对比文件操作模式\n5. 对代表性会话运行 `read -s <id>` 了解任务类型差异\n\n**输出要求**：\n1. **使用分布**：各工具的会话数、消息数、数据量\n2. **任务类型**：各工具擅长的任务类型\n3. **成功率**：哪个工具在什么场景下纠正更少\n4. **互补模式**：两者最佳搭配使用方式\n5. **工作流建议**：什么任务用哪个工具" },
  ];

  function populateGlobalAiPresets() {
    const container = $("#ai-chat-presets");
    if (!container || container.dataset.populated) return;
    container.dataset.populated = "1";
    container.innerHTML = "";
    GLOBAL_AI_PRESETS.forEach(p => {
      const btn = document.createElement("button");
      btn.className = "preset-card";
      btn.dataset.prompt = p.prompt;
      btn.innerHTML = `<span class="preset-icon">${p.icon}</span><div class="preset-info"><span class="preset-title">${p.title}</span><span class="preset-desc">${p.desc}</span></div>`;
      btn.addEventListener("click", () => submitGlobalAi(btn.dataset.prompt));
      container.appendChild(btn);
    });
  }

  /** Initialize AI page — scope bar + Evolve + chat */
  function initAiPage() {
    // Override getEvolveScope to read from shared global scope
    window.getEvolveScope = function() {
      return { source: globalScopeSource, date: globalScopeDate, project: globalScopeProject, engine: globalScopeEngine };
    };
    renderAiScopeBar();
    populateGlobalAiPresets();
    restoreAiChatMessages();
    // Initialize Evolve visualizations after the shared scope getter exists.
    if (window.initEvolveView) window.initEvolveView();
  }

  function notifyEvolveScopeChanged() {
    if (window.initEvolveView) window.initEvolveView();
  }

  function renderAiScopeBar() {
    const bar = $("#ai-scope-bar");
    if (!bar) return;
    bar.innerHTML = "";

    // Source label + tabs
    const srcLabel = document.createElement("span");
    srcLabel.className = "scope-label";
    srcLabel.textContent = "Source";
    bar.appendChild(srcLabel);

    const srcTabs = document.createElement("div");
    srcTabs.className = "scope-tabs";
    const claudeCount = allSessions.filter(s => (s.source || "claude") === "claude").length;
    const codexCount = allSessions.filter(s => s.source === "codex").length;
    [
      { key: "all", label: "All", count: allSessions.length },
      { key: "claude", label: "Claude", count: claudeCount },
      { key: "codex", label: "Codex", count: codexCount },
    ].forEach(s => {
      const btn = document.createElement("button");
      btn.className = `scope-tab${s.key === globalScopeSource ? " active" : ""}`;
      btn.innerHTML = `${s.label} <span class="tab-count">${s.count}</span>`;
      btn.addEventListener("click", () => {
        globalScopeSource = s.key;
        renderAiScopeBar();
        notifyEvolveScopeChanged();
      });
      srcTabs.appendChild(btn);
    });
    bar.appendChild(srcTabs);

    // Date label + tabs
    const dateLabel = document.createElement("span");
    dateLabel.className = "scope-label";
    dateLabel.textContent = "Date";
    bar.appendChild(dateLabel);

    const dateTabs = document.createElement("div");
    dateTabs.className = "scope-tabs";
    [
      { key: "1d", label: "Today" },
      { key: "7d", label: "Week" },
      { key: "30d", label: "30d" },
      { key: "90d", label: "3mo" },
      { key: "all", label: "All" },
    ].forEach(d => {
      const btn = document.createElement("button");
      btn.className = `scope-tab${d.key === globalScopeDate ? " active" : ""}`;
      btn.textContent = d.label;
      btn.addEventListener("click", () => {
        globalScopeDate = d.key;
        renderAiScopeBar();
        notifyEvolveScopeChanged();
      });
      dateTabs.appendChild(btn);
    });
    bar.appendChild(dateTabs);

    // Project dropdown
    const projSelect = document.createElement("select");
    projSelect.id = "ai-scope-project";
    const filtered = getFilteredScopeSessions();
    const projCounts = {};
    filtered.forEach(s => { const p = s.project || "unknown"; projCounts[p] = (projCounts[p] || 0) + 1; });
    const allOpt = document.createElement("option");
    allOpt.value = "";
    allOpt.textContent = `All Projects (${filtered.length})`;
    projSelect.appendChild(allOpt);
    Object.entries(projCounts).sort((a, b) => b[1] - a[1]).forEach(([name, count]) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = `${name} (${count})`;
      projSelect.appendChild(opt);
    });
    if (globalScopeProject && !Object.prototype.hasOwnProperty.call(projCounts, globalScopeProject)) {
      globalScopeProject = "";
    }
    projSelect.value = globalScopeProject;
    projSelect.onchange = () => {
      globalScopeProject = projSelect.value;
      renderAiScopeBar();
      notifyEvolveScopeChanged();
    };
    bar.appendChild(projSelect);

    // Engine dropdown
    const engineLabel = document.createElement("span");
    engineLabel.className = "scope-label";
    engineLabel.textContent = "Engine";
    bar.appendChild(engineLabel);

    const engineSelect = document.createElement("select");
    engineSelect.id = "ai-scope-engine";
    [
      { key: "auto", label: "Auto" },
      { key: "codex", label: "Codex" },
      { key: "claude", label: "Claude" },
    ].forEach(e => {
      const opt = document.createElement("option");
      opt.value = e.key;
      opt.textContent = e.label;
      engineSelect.appendChild(opt);
    });
    engineSelect.value = globalScopeEngine;
    engineSelect.onchange = () => {
      globalScopeEngine = engineSelect.value;
      notifyEvolveScopeChanged();
    };
    bar.appendChild(engineSelect);

    // Timeout selector
    const timeoutLabel = document.createElement("span");
    timeoutLabel.className = "scope-label";
    timeoutLabel.textContent = "Timeout";
    bar.appendChild(timeoutLabel);

    const timeoutSelect = document.createElement("select");
    timeoutSelect.id = "ai-scope-timeout";
    [
      { key: 300, label: "5 min" },
      { key: 600, label: "10 min" },
      { key: 900, label: "15 min" },
      { key: 1200, label: "20 min" },
      { key: 1800, label: "30 min" },
    ].forEach(t => {
      const opt = document.createElement("option");
      opt.value = t.key;
      opt.textContent = t.label;
      timeoutSelect.appendChild(opt);
    });
    timeoutSelect.value = chatTimeout;
    timeoutSelect.onchange = () => {
      chatTimeout = parseInt(timeoutSelect.value, 10);
      localStorage.setItem("chatview-timeout", String(chatTimeout));
    };
    bar.appendChild(timeoutSelect);

    // Scope stats
    let scopeFiltered = filtered;
    if (globalScopeProject) scopeFiltered = scopeFiltered.filter(s => s.project === globalScopeProject);
    const projects = new Set(scopeFiltered.map(s => s.project).filter(Boolean));
    const msgs = scopeFiltered.reduce((sum, s) => sum + (s.userMessageCount || 0), 0);
    const statsSpan = document.createElement("span");
    statsSpan.className = "scope-stats";
    statsSpan.innerHTML = `<strong>${scopeFiltered.length}</strong> sessions · <strong>${projects.size}</strong> projects · <strong>${msgs}</strong> msgs`;
    bar.appendChild(statsSpan);
  }

  function restoreAiChatMessages() {
    const container = $("#ai-chat-messages");
    if (!container) return;
    container.innerHTML = "";
    if (currentGlobalChatId) {
      const chat = globalChatHistory.find(c => c.id === currentGlobalChatId);
      if (chat && chat.messages.length) {
        chat.messages.forEach(m => appendChatMsg(container, m.role, m.content));
        const presets = $("#ai-chat-presets");
        if (presets) presets.style.display = "none";
      }
    }
  }

  /** Get sessions matching current evolve scope (source + date) */
  function getFilteredScopeSessions() {
    const scope = window.getEvolveScope ? window.getEvolveScope() : { source: globalScopeSource, date: globalScopeDate };
    let list = allSessions;
    if (scope.source !== "all") {
      list = list.filter(s => (s.source || "claude") === scope.source);
    }
    if (scope.date !== "all") {
      const now = new Date();
      const daysMap = { "1d": 1, "7d": 7, "30d": 30, "90d": 90 };
      const maxDays = daysMap[scope.date] || 9999;
      const cutoff = new Date(now - maxDays * 86400000);
      list = list.filter(s => s.date && new Date(s.date) >= cutoff);
    }
    return list;
  }

  function submitGlobalAi(prompt) {
    const input = $("#ai-chat-input");
    const text = prompt || (input ? input.value.trim() : "");
    if (!text || globalAiLoading) return;
    if (input) { input.value = ""; autoResizeTextarea(input); }

    const container = $("#ai-chat-messages");
    if (!container) return;

    // Ensure we have a global chat
    if (!currentGlobalChatId) initNewGlobalChat();

    // Use shared scope state
    const scope = {
      project: globalScopeProject,
      date: globalScopeDate,
      source: globalScopeSource,
      engine: globalScopeEngine,
    };

    // Add user message
    appendChatMsg(container, "user", text);
    saveGlobalChatMessage("user", text);

    // Hide presets
    const presets = $("#ai-chat-presets");
    if (presets) presets.style.display = "none";

    // Show streaming bubble
    globalAiLoading = true;
    _setGlobalAiButton(true);
    const assistantTurn = createAssistantTurn(container);

    const chat = globalChatHistory.find(c => c.id === currentGlobalChatId);
    const priorMsgs = chat ? chat.messages.slice(0, -1) : [];
    const handle = sendChatStream(text, "global", null, scope, priorMsgs);
    globalAiHandle = handle;
    handle
      .onText(chunk => {
        assistantTurn.updateText(chunk);
      })
      .onTool(evt => {
        assistantTurn.addTool(evt);
      })
      .onDone((fullText, isTimeout) => {
        if (globalAiHandle !== handle) return;
        globalAiLoading = false;
        globalAiHandle = null;
        _setGlobalAiButton(false);
        const reply = fullText || "(empty response)";
        assistantTurn.finalize(reply);
        saveGlobalChatMessage("assistant", reply);
        // Update title
        const chat2 = globalChatHistory.find(c => c.id === currentGlobalChatId);
        if (chat2 && chat2.title === "New Analysis") {
          chat2.title = text.substring(0, 40) + (text.length > 40 ? "…" : "");
          renderGlobalChatSidebar();
        }
        saveChatToStorage();

        if (isTimeout) {
          _appendContinueButton(container, () => submitGlobalAi("继续"));
        } else {
          // Check if this was an Evolve-related analysis
          const evolveTabMap = {
            "自动生成CLAUDE.md规则": "rules", "规则生成": "rules",
            "可沉淀的知识": "memory", "知识沉淀": "memory",
            "用户画像": "profile",
            "纠正AI的场景": "signals", "纠正模式": "signals",
            "反复出现的问题模式": "patterns", "重复模式": "patterns",
          };
          let targetTab = null;
          for (const [keyword, tab] of Object.entries(evolveTabMap)) {
            if (text.includes(keyword)) { targetTab = tab; break; }
          }
          if (targetTab) {
            const parsed = window.parseEvolveResponseExternal ? window.parseEvolveResponseExternal(targetTab, reply) : null;
            if (parsed && !parsed._parseError) {
              const itemCount = Object.values(parsed).reduce((sum, v) => sum + (Array.isArray(v) ? v.length : 0), 0);
              const summaryText = `✅ 分析完成：发现 ${itemCount} 条结果。3 秒后跳转到 Evolve → ${targetTab}`;
              appendChatMsg(container, "assistant", summaryText);
              setTimeout(() => {
                if (window.navigateToEvolveTab) window.navigateToEvolveTab(targetTab, parsed);
              }, 3000);
            }
          }
        }
      })
      .onError(msg => {
        if (globalAiHandle !== handle) return;
        globalAiLoading = false;
        globalAiHandle = null;
        _setGlobalAiButton(false);
        const reply = `**Error:** ${msg}`;
        assistantTurn.finalize(reply);
        saveGlobalChatMessage("assistant", reply);
        saveChatToStorage();
      })
      .onAbort(partialText => {
        if (globalAiHandle !== handle) return;
        globalAiLoading = false;
        globalAiHandle = null;
        _setGlobalAiButton(false);
        const reply = (partialText || "") + "\n\n*(已停止)*";
        assistantTurn.finalize(reply);
        saveGlobalChatMessage("assistant", reply);
        saveChatToStorage();
        _appendContinueButton(container, () => submitGlobalAi("继续"));
      });
  }

  function _setGlobalAiButton(loading) {
    const btn = $("#ai-chat-send");
    if (!btn) return;
    if (loading) { btn.textContent = "■ Stop"; btn.classList.add("btn-stop"); }
    else { btn.textContent = "Send"; btn.classList.remove("btn-stop"); }
  }

  function _stopGlobalAi() {
    if (globalAiHandle) globalAiHandle.abort();
    // Don't null globalAiHandle here — let onAbort callback do cleanup
    globalAiLoading = false;
    _setGlobalAiButton(false);
  }

  function initNewGlobalChat() {
    currentGlobalChatId = "gchat-" + Date.now();
    globalChatHistory.unshift({id: currentGlobalChatId, title: "New Analysis", messages: []});
    renderGlobalChatSidebar();
  }

  function newGlobalChat() {
    currentGlobalChatId = null;
    const container = $("#ai-chat-messages");
    if (container) container.innerHTML = "";
    const presets = $("#ai-chat-presets");
    if (presets) presets.style.display = "";
    initNewGlobalChat();
  }

  function saveGlobalChatMessage(role, content) {
    const chat = globalChatHistory.find(c => c.id === currentGlobalChatId);
    if (chat) chat.messages.push({role, content});
  }

  function renderGlobalChatSidebar() {
    const list = $("#chat-history-list");
    if (!list) return;
    list.innerHTML = "";
    globalChatHistory.forEach(chat => {
      const li = document.createElement("li");
      li.className = "session-item" + (chat.id === currentGlobalChatId ? " active" : "");
      li.innerHTML = `<div class="session-title">${esc(chat.title)}</div>
        <div class="session-date">${chat.messages.length} messages</div>`;
      li.addEventListener("click", () => loadGlobalChatHistory(chat.id));
      list.appendChild(li);
    });
  }

  function loadGlobalChatHistory(chatId) {
    const chat = globalChatHistory.find(c => c.id === chatId);
    if (!chat) return;
    currentGlobalChatId = chatId;
    const container = $("#ai-chat-messages");
    if (container) {
      container.innerHTML = "";
      chat.messages.forEach(m => appendChatMsg(container, m.role, m.content));
    }
    const presets = $("#ai-chat-presets");
    if (presets) presets.style.display = chat.messages.length ? "none" : "";
    renderGlobalChatSidebar();
  }

  // ── Chat persistence (localStorage) ───────────────────────────

  let _quotaWarningShown = false;
  function _showQuotaWarning() {
    if (_quotaWarningShown) return;
    _quotaWarningShown = true;
    const toast = document.createElement("div");
    toast.style.cssText = "position:fixed;bottom:20px;right:20px;background:#e65100;color:#fff;padding:12px 20px;border-radius:8px;z-index:9999;font-size:13px;box-shadow:0 4px 12px rgba(0,0,0,.3);max-width:320px";
    toast.textContent = "Storage quota exceeded — chat history and cache may not persist. Consider clearing old chat sessions.";
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 8000);
  }

  function saveChatToStorage() {
    try {
      // Session chats — prune to last 50 sessions
      const keys = Object.keys(sessionChatCache);
      if (keys.length > 50) {
        keys.slice(50).forEach(k => delete sessionChatCache[k]);
      }
      localStorage.setItem("chatview-session-chats", JSON.stringify(sessionChatCache));
      // Global chats — keep last 30
      const trimmed = globalChatHistory.slice(0, 30);
      localStorage.setItem("chatview-global-chats", JSON.stringify(trimmed));
    } catch (e) {
      if (e.name === "QuotaExceededError" || (e.code && e.code === 22)) {
        _showQuotaWarning();
      }
    }
  }

  function loadChatFromStorage() {
    try {
      const sc = localStorage.getItem("chatview-session-chats");
      if (sc) sessionChatCache = JSON.parse(sc);
      const gc = localStorage.getItem("chatview-global-chats");
      if (gc) {
        globalChatHistory = JSON.parse(gc);
        renderGlobalChatSidebar();
      }
    } catch (e) { /* corrupt data — ignore */ }
  }

  // ── Markdown Export (F4) ──────────────────────────────────────
  function exportMarkdown() {
    if (!currentMessages.length || !currentSessionId) return;

    const title = convTitle.textContent || "Untitled";
    const meta = convMeta.textContent || "";
    let md = `# ${title}\n\n_${meta}_\n\n---\n\n`;

    for (const msg of currentMessages) {
      if (msg.type === "user") {
        const text = msg.content.map(b => b.type === "text" ? b.text : "").join("\n").trim();
        if (text) md += `## 👤 You\n\n${text}\n\n`;
      } else if (msg.type === "assistant") {
        for (const block of msg.content) {
          if (block.type === "text" && block.text?.trim()) {
            md += `### 🤖 Assistant\n\n${block.text}\n\n`;
          } else if (block.type === "tool_use") {
            const inp = typeof block.input === "string" ? block.input : JSON.stringify(block.input, null, 2);
            md += `<details><summary>🔧 ${block.name}</summary>\n\n\`\`\`json\n${inp}\n\`\`\`\n</details>\n\n`;
          } else if (block.type === "thinking") {
            md += `<details><summary>💭 Thinking</summary>\n\n${block.text}\n</details>\n\n`;
          }
        }
      } else if (msg.type === "tool_result") {
        const content = msg.content.map(b => typeof b.content === "string" ? b.content : JSON.stringify(b.content)).join("\n");
        if (content.trim()) {
          md += `<details><summary>📋 Tool Result</summary>\n\n\`\`\`\n${content.substring(0, 2000)}\n\`\`\`\n</details>\n\n`;
        }
      }
    }

    // Trigger download
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.substring(0, 60).replace(/[\/\\?%*:|"<>]/g, "_")}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ── Copy Conversation (User + Assistant text only) ─────────────
  function copyConversation() {
    if (!currentMessages.length) return;
    let text = "";
    for (const msg of currentMessages) {
      if (msg.type === "user") {
        const t = msg.content.map(b => b.type === "text" ? b.text : "").join("\n").trim();
        if (t) text += `👤 You:\n${t}\n\n`;
      } else if (msg.type === "assistant") {
        const t = msg.content.filter(b => b.type === "text" && b.text?.trim()).map(b => b.text).join("\n\n");
        if (t) text += `🤖 Assistant:\n${t}\n\n`;
      }
    }
    navigator.clipboard.writeText(text.trim()).then(() => {
      const btn = $("#btn-copy-conv");
      const orig = btn.innerHTML;
      btn.innerHTML = "✅ Copied";
      setTimeout(() => { btn.innerHTML = orig; }, 1500);
    });
  }

  // ── Expose globals for evolve.js ──────────────────────────────
  window.esc = esc;
  window.renderMarkdownSimple = renderMarkdownSimple;
  // allSessions is kept in sync via loadSessions; expose getter
  Object.defineProperty(window, "allSessions", { get: () => allSessions });

  // ── Boot ───────────────────────────────────────────────────────
  init().catch((err) => {
    console.error("Init failed:", err);
    const el = document.getElementById("content");
    if (el) el.innerHTML =
      `<div style="padding:60px 40px;text-align:center"><h2 style="color:var(--text)">Error</h2><p style="color:var(--text-muted)">${err.message}</p><p style="color:var(--text-muted)">Make sure server.py is running.</p></div>`;
  });
})();
