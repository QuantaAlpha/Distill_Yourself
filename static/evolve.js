/**
 * Evolve Page — D3.js visualizations for AI self-evolution
 * Depends on: app.js (for showView, api, allSessions, esc, renderMarkdownSimple)
 */
(function () {
  "use strict";

  // ── State ──
  let evolveActiveTab = "profile";
  let evolveCache = {}; // {scopeKey: {updatedAt, scope, data}}
  let evolveLoadingTabs = {}; // {tab: true} — per-tab loading state
  let activeSimulation = null;
  let evolveStreamAborts = {}; // {tab: AbortController} — per-tab stream abort
  let evolveScopeSource = "all";
  let evolveScopeDate = "7d";
  let evolveScopeProject = "";
  let evolveScopeEngine = "auto";

  // ── DOM refs ──
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // ── Init (called from app.js when AI page opens) ──
  window.initEvolveView = function () {
    loadEvolveCache();
    // Scope filters are now rendered by initAiPage() in app.js
    // Read scope from shared global state
    const scope = window.getEvolveScope ? window.getEvolveScope() : {};
    if (scope.source) evolveScopeSource = scope.source;
    if (scope.date) evolveScopeDate = scope.date;
    if (scope.project !== undefined) evolveScopeProject = scope.project;
    if (scope.engine) evolveScopeEngine = scope.engine;
    // Clear initial HTML — per-tab panels will be created on demand
    const body = $("#evolve-tab-body");
    if (body) body.innerHTML = "";
    bindEvolveEvents();
    switchEvolveTab(evolveActiveTab);
    // Auto-load server-side cache for tabs missing from localStorage
    _loadServerCacheForMissingTabs();
  };

  function bindEvolveEvents() {
    // Tab switching
    $$(".evolve-tab").forEach(tab => {
      tab.onclick = () => switchEvolveTab(tab.dataset.tab);
    });

    // Per-tab refresh / stop
    const tabRefresh = $("#evolve-tab-refresh");
    if (tabRefresh) tabRefresh.onclick = () => {
      if (evolveStreamAborts[evolveActiveTab]) { _stopEvolveTab(evolveActiveTab); }
      else { refreshEvolveTab(evolveActiveTab); }
    };

    // Refresh all
    const refreshAll = $("#evolve-refresh-all");
    if (refreshAll) refreshAll.onclick = () => refreshAllEvolveTabs();

    // Sync button
    const syncBtn = $("#evolve-tab-sync");
    if (syncBtn) syncBtn.onclick = () => toggleSyncPanel();
  }

  function switchEvolveTab(tab) {
    evolveActiveTab = tab;
    $$(".evolve-tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tab));
    // Show/hide per-tab panels instead of re-rendering
    _ensureTabPanel(tab);
    $$(".evolve-tab-panel").forEach(p => {
      p.style.display = p.dataset.tab === tab ? "" : "none";
    });
    // Update header to show this tab's status
    const updatedEl = $("#evolve-tab-updated");
    if (evolveLoadingTabs[tab]) {
      if (updatedEl) { updatedEl.textContent = "AI 执行中…"; updatedEl.classList.add("loading"); }
    } else {
      const cached = getCachedTab(tab);
      if (updatedEl) { updatedEl.textContent = cached ? `Updated: ${timeAgo(cached.updatedAt)}` : "尚未分析"; updatedEl.classList.remove("loading"); }
    }
    updateEvolveOverviewBar();
    updateSyncButtonState();
    _setEvolveRefreshButton(); // reflect active tab's stream state
  }

  /** Ensure a per-tab panel exists inside #evolve-tab-body */
  function _ensureTabPanel(tab) {
    const body = $("#evolve-tab-body");
    if (!body) return null;
    let panel = body.querySelector(`.evolve-tab-panel[data-tab="${tab}"]`);
    if (!panel) {
      panel = document.createElement("div");
      panel.className = "evolve-tab-panel";
      panel.dataset.tab = tab;
      body.appendChild(panel);
      // Render cached content or empty state
      _renderTabPanel(tab, panel);
    }
    return panel;
  }

  /** Render tab content into its dedicated panel */
  function _renderTabPanel(tab, panel) {
    if (!panel) return;
    const cached = getCachedTab(tab);
    if (cached && cached.data) {
      if (activeSimulation) { activeSimulation.stop(); activeSimulation = null; }
      panel.innerHTML = "";
      if (cached.data._error) {
        panel.innerHTML = `<div class="evolve-empty-state"><p>分析失败：${(window.esc || String)(cached.data._error)}</p><p>点击 🔄 Refresh 重试</p></div>`;
        return;
      }
      renderTabVisualization(tab, cached.data, panel);
    } else if (!evolveLoadingTabs[tab]) {
      panel.innerHTML = '<div class="evolve-empty-state"><p>点击 🔄 Refresh 开始分析最近的对话</p></div>';
    }
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

  function getScopeCacheKey(tab, scope) {
    scope = scope || getEvolveScope();
    return [
      tab,
      scope.source || "all",
      scope.date || "7d",
      scope.project || "",
      scope.engine || "auto",
    ].join("::");
  }

  function getCachedTab(tab) {
    return evolveCache[getScopeCacheKey(tab)] || null;
  }

  function setCachedTab(tab, data, scope) {
    scope = scope || getEvolveScope();
    evolveCache[getScopeCacheKey(tab, scope)] = {
      updatedAt: new Date().toISOString(),
      scope,
      data,
    };
    saveEvolveCache();
    updateSyncButtonState();
  }

  function isCurrentScopeKey(tab, cacheKey) {
    return getScopeCacheKey(tab) === cacheKey;
  }

  // ── Scope (reads from shared global state set by initAiPage in app.js) ──
  function getEvolveScope() {
    if (typeof window.getEvolveScope === "function" && window.getEvolveScope !== getEvolveScope) {
      const scope = window.getEvolveScope() || {};
      return {
        source: scope.source || "all",
        date: scope.date || "7d",
        project: scope.project || "",
        engine: scope.engine || "auto",
      };
    }
    return {
      source: evolveScopeSource,
      date: evolveScopeDate,
      project: evolveScopeProject,
      engine: evolveScopeEngine,
    };
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
      case "profile": return (data.categories?.length || 0) + (data.radar?.dimensions?.length || 0);
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

  // ── Tab content rendering (legacy compat — routes to per-tab panel) ──
  function renderEvolveTabContent(tab) {
    const panel = _ensureTabPanel(tab);
    _renderTabPanel(tab, panel);
    // Update header
    const updatedEl = $("#evolve-tab-updated");
    const cached = getCachedTab(tab);
    if (updatedEl) updatedEl.textContent = cached ? `Updated: ${timeAgo(cached.updatedAt)}` : "尚未分析";
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

  // ── Auto-load server cache on init ──
  function _loadServerCacheForMissingTabs() {
    const tabs = ["profile", "memory", "rules", "signals", "patterns"];
    const scope = getEvolveScope();
    const params = new URLSearchParams({
      source: scope.source || "all",
      date: scope.date || "7d",
      project: scope.project || "",
      engine: scope.engine || "auto",
    });
    tabs.forEach(tab => {
      if (getCachedTab(tab)) return; // already in localStorage
      fetch(`/api/evolve/${tab}?${params}`)
        .then(r => r.json())
        .then(data => {
          if (data && !data._error && (data.categories?.length || data.nodes?.length || data.rules?.length || data.timeline?.length || data.bubbles?.length)) {
            const normalized = normalizeEvolveData(tab, data);
            setCachedTab(tab, normalized);
            const panel = _ensureTabPanel(tab);
            _renderTabPanel(tab, panel);
            updateEvolveOverviewBar();
          }
        })
        .catch(() => {}); // silent — server cache is optional
    });
  }

  // ── API call for analysis (unified: all tabs go through /api/evolve/{tab}) ──
  // AI tabs (profile, memory) may take longer since they run Codex on the backend
  const AI_TABS = new Set(["profile", "memory", "rules", "signals", "patterns"]);

  function _fetchEvolveTab(tab) {
    const scope = getEvolveScope();
    const requestCacheKey = getScopeCacheKey(tab, scope);
    const params = new URLSearchParams({
      refresh: "1",
      source: scope.source || "all",
      date: scope.date || "7d",
      project: scope.project || "",
      engine: scope.engine || "auto",
    });

    // AI tabs use SSE streaming for real-time progress
    if (AI_TABS.has(tab)) {
      params.set("stream", "1");
      return _fetchEvolveTabStream(tab, params, scope, requestCacheKey);
    }

    return fetch(`/api/evolve/${tab}?${params}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        const normalized = normalizeEvolveData(tab, data);
        setCachedTab(tab, normalized, scope);
        if (isCurrentScopeKey(tab, requestCacheKey)) {
          const panel = _ensureTabPanel(tab);
          _renderTabPanel(tab, panel);
          updateEvolveOverviewBar();
        }
      });
  }

  /** Stream SSE events for AI evolve tabs with live progress */
  function _fetchEvolveTabStream(tab, params, requestScope, requestCacheKey) {
    const updatedEl = $("#evolve-tab-updated");
    const esc = window.esc || String;

    // Ensure tab panel exists and set up streaming container inside it
    const panel = _ensureTabPanel(tab);
    if (panel) {
      panel.innerHTML = `<div class="evolve-stream-actions"><button class="btn-text" data-evolve-cancel="${tab}">取消分析</button></div><div class="evolve-stream-progress" id="evolve-stream-${tab}"><div class="evolve-thinking"><span class="evolve-thinking-dot"></span><span class="evolve-thinking-dot"></span><span class="evolve-thinking-dot"></span><span class="evolve-thinking-label">AI 启动中…</span></div></div>`;
      const cancelBtn = panel.querySelector(`[data-evolve-cancel="${tab}"]`);
      if (cancelBtn) cancelBtn.onclick = () => abortEvolveStream(tab, "用户已取消分析");
    }
    if (tab === evolveActiveTab && updatedEl) { updatedEl.textContent = "AI 启动中…"; updatedEl.classList.add("loading"); }

    const streamState = { blockText: "", textBlock: null, runningCards: [], stepCount: 0, currentToolGroup: null, toolGroupCounts: {}, toolGroupRunning: 0, toolGroupTotal: 0, toolGroupCollapseTimer: null, requestScope, requestCacheKey };

    // Create abort controller for this tab's stream
    if (evolveStreamAborts[tab]) evolveStreamAborts[tab].abort();
    const abortCtrl = new AbortController();
    evolveStreamAborts[tab] = abortCtrl;
    _setEvolveRefreshButton();

    return fetch(`/api/evolve/${tab}?${params}`, { signal: abortCtrl.signal })
      .then(response => window.readSseStream(response, evt => _handleEvolveStreamEvent(evt, tab, streamState)))
      .finally(() => { delete evolveStreamAborts[tab]; _setEvolveRefreshButton(); });
  }

  function _setEvolveRefreshButton() {
    const btn = $("#evolve-tab-refresh");
    if (!btn) return;
    const streaming = !!evolveStreamAborts[evolveActiveTab];
    if (streaming) { btn.textContent = "■ Stop"; btn.classList.add("btn-stop"); }
    else { btn.textContent = "🔄 Refresh"; btn.classList.remove("btn-stop"); }
  }

  function _stopEvolveTab(tab) {
    if (evolveStreamAborts[tab]) { evolveStreamAborts[tab].abort(); delete evolveStreamAborts[tab]; }
    delete evolveLoadingTabs[tab];
    _setEvolveRefreshButton();
    const updatedEl = $("#evolve-tab-updated");
    if (updatedEl) { updatedEl.textContent = "已停止"; updatedEl.classList.remove("loading"); }
  }

  /** Show a "thinking" indicator below the last text block */
  function _evolveShowThinking(container, state) {
    _evolveHideThinking(container);
    const el = document.createElement("div");
    el.className = "evolve-thinking";
    el.innerHTML = '<span class="evolve-thinking-dot"></span><span class="evolve-thinking-dot"></span><span class="evolve-thinking-dot"></span><span class="evolve-thinking-label">AI 分析生成中…</span>';
    container.appendChild(el);
  }
  function _evolveHideThinking(container) {
    const el = container && container.querySelector(".evolve-thinking");
    if (el) el.remove();
  }

  /** Auto-scroll #evolve-tab-body if user is near the bottom */
  function _evolveAutoScroll() {
    const scrollEl = $("#evolve-tab-body");
    if (!scrollEl) return;
    if (scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight < 80) {
      scrollEl.scrollTop = scrollEl.scrollHeight;
    }
  }

  function _renderEvolveMarkdownInto(el, text) {
    const esc = window.esc || String;
    el.innerHTML = window.renderMarkdownSimple
      ? window.renderMarkdownSimple(text)
      : `<pre>${esc(text)}</pre>`;
  }

  function _scheduleEvolveMarkdownRender(state, el, text) {
    el._pendingMarkdownText = text;
    if (el._markdownRenderTimer) return;
    const schedule = window.requestAnimationFrame || ((fn) => setTimeout(fn, 50));
    el._markdownRenderTimer = schedule(() => {
      el._markdownRenderTimer = null;
      _renderEvolveMarkdownInto(el, el._pendingMarkdownText || "");
      _evolveShowThinking(el.parentElement, state);
      _evolveAutoScroll();
    });
  }

  function _cancelEvolveMarkdownRender(el) {
    if (!el || !el._markdownRenderTimer) return;
    const cancel = window.cancelAnimationFrame || clearTimeout;
    cancel(el._markdownRenderTimer);
    el._markdownRenderTimer = null;
  }

  /** Create a new tool-group container */
  function _createToolGroup(parentContainer) {
    const group = document.createElement("div");
    group.className = "evolve-tool-group expanded running";
    group.innerHTML = `<div class="evolve-tg-header"><span class="evolve-tg-dot"></span><span class="evolve-tg-summary"></span><span class="evolve-tg-chevron">›</span></div><div class="evolve-tg-body"></div>`;
    group.querySelector(".evolve-tg-header").onclick = () => group.classList.toggle("expanded");
    parentContainer.appendChild(group);
    return group;
  }

  /** Update tool-group header summary text */
  function _updateToolGroupHeader(state) {
    const group = state.currentToolGroup;
    if (!group) return;
    const el = group.querySelector(".evolve-tg-summary");
    if (!el) return;
    const parts = Object.entries(state.toolGroupCounts).map(([name, count]) => `${count} ${name}`);
    el.innerHTML = `<span class="evolve-tg-count">⚡ ${state.toolGroupTotal} tools</span> · ${parts.join(" · ")}`;
  }

  /** Close (collapse) the current tool group */
  function _finalizeToolGroup(state) {
    if (state.toolGroupCollapseTimer) { clearTimeout(state.toolGroupCollapseTimer); state.toolGroupCollapseTimer = null; }
    if (state.currentToolGroup) {
      _updateToolGroupHeader(state);
      state.currentToolGroup.classList.remove("expanded", "running");
      state.currentToolGroup.classList.add("done");
      state.currentToolGroup = null;
    }
  }

  function _handleEvolveStreamEvent(evt, tab, state) {
    const container = document.getElementById(`evolve-stream-${tab}`);
    const updatedEl = $("#evolve-tab-updated");
    const esc = window.esc || String;
    if (!container) return;
    // Only update the header text and auto-scroll if this tab is currently visible
    const isActiveTab = (tab === evolveActiveTab);

    switch (evt.type) {
      case "tool": {
        if (evt.status === "running") {
          state.textBlock = null;
          state.blockText = "";
          _evolveHideThinking(container);
          if (state.toolGroupCollapseTimer) { clearTimeout(state.toolGroupCollapseTimer); state.toolGroupCollapseTimer = null; }
          if (!state.currentToolGroup) {
            state.currentToolGroup = _createToolGroup(container);
            state.toolGroupCounts = {};
            state.toolGroupRunning = 0;
            state.toolGroupTotal = 0;
          }
          const card = document.createElement("div");
          card.className = "tool-card running";
          const detail = evt.detail ? esc(evt.detail) : "";
          card.innerHTML = `<div class="tool-card-header"><span class="tool-status-dot"></span><span class="tool-card-name">${esc(evt.name)}</span><span class="tool-card-detail">${detail}</span><span class="tool-card-chevron">›</span></div><div class="tool-card-body"><div class="tool-card-cmd"></div><pre class="tool-card-output"></pre></div>`;
          // For Agent cards, show the full prompt in the body
          if (evt.name === "Agent" && evt.prompt) {
            const cmdEl = card.querySelector(".tool-card-cmd");
            if (cmdEl) {
              cmdEl.textContent = evt.prompt;
              cmdEl.classList.add("agent-prompt");
            }
          }
          state.currentToolGroup.querySelector(".evolve-tg-body").appendChild(card);
          state.runningCards.push(card);
          state.stepCount++;
          state.toolGroupTotal++;
          state.toolGroupRunning++;
          const toolName = evt.name || "Tool";
          state.toolGroupCounts[toolName] = (state.toolGroupCounts[toolName] || 0) + 1;
          _updateToolGroupHeader(state);
          state.currentToolGroup.classList.add("expanded", "running");
          state.currentToolGroup.classList.remove("done");
        } else if (evt.status === "done" && state.runningCards.length) {
          const card = state.runningCards.shift();
          card.classList.remove("running");
          card.classList.add("done");
          // Show full command/prompt in body
          const cmdEl = card.querySelector(".tool-card-cmd");
          const detailEl = card.querySelector(".tool-card-detail");
          const cardName = card.querySelector(".tool-card-name")?.textContent || "";
          const isAgent = cardName === "Agent";
          if (!isAgent && cmdEl && detailEl && detailEl.textContent) {
            cmdEl.textContent = detailEl.textContent;
          }
          if (!isAgent && evt.detail) {
            const outputEl = card.querySelector(".tool-card-output");
            if (outputEl) outputEl.textContent = evt.detail;
          }
          const header = card.querySelector(".tool-card-header");
          if (header) header.onclick = () => card.classList.toggle("expanded");
          state.toolGroupRunning = Math.max(0, state.toolGroupRunning - 1);
          _updateToolGroupHeader(state);
          if (state.toolGroupRunning === 0 && state.currentToolGroup) {
            state.currentToolGroup.classList.remove("running");
            state.currentToolGroup.classList.add("done");
            const grp = state.currentToolGroup;
            state.toolGroupCollapseTimer = setTimeout(() => {
              grp.classList.remove("expanded");
              if (state.currentToolGroup === grp) state.currentToolGroup = null;
              state.toolGroupCollapseTimer = null;
            }, 800);
          }
        }
        if (isActiveTab && updatedEl) { updatedEl.textContent = `AI 执行中… (${state.stepCount} steps)`; updatedEl.classList.add("loading"); }
        if (isActiveTab) _evolveAutoScroll();
        break;
      }
      case "text":
        _finalizeToolGroup(state);
        state.blockText += evt.content;
        if (!state.textBlock) {
          state.textBlock = document.createElement("div");
          state.textBlock.className = "text-block";
          container.appendChild(state.textBlock);
        }
        _scheduleEvolveMarkdownRender(state, state.textBlock, state.blockText);
        break;
      case "result":
        _finalizeToolGroup(state);
        _evolveHideThinking(container);
        _cancelEvolveMarkdownRender(state.textBlock);
        state.blockText = evt.content;
        if (!state.textBlock) {
          state.textBlock = document.createElement("div");
          state.textBlock.className = "text-block";
          container.appendChild(state.textBlock);
        }
        _renderEvolveMarkdownInto(state.textBlock, evt.content);
        if (isActiveTab) _evolveAutoScroll();
        break;
      case "evolve_result": {
        _finalizeToolGroup(state);
        _cancelEvolveMarkdownRender(state.textBlock);
        const normalized = normalizeEvolveData(tab, evt.data);
        setCachedTab(tab, normalized, state.requestScope);
        if (isCurrentScopeKey(tab, state.requestCacheKey)) {
          const panel = _ensureTabPanel(tab);
          _renderTabPanel(tab, panel);
          updateEvolveOverviewBar();
          if (isActiveTab && updatedEl) { updatedEl.textContent = `Updated ${new Date().toLocaleTimeString()}`; updatedEl.classList.remove("loading"); }
        }
        break;
      }
      case "done":
        _finalizeToolGroup(state);
        _evolveHideThinking(container);
        _cancelEvolveMarkdownRender(state.textBlock);
        if (isCurrentScopeKey(tab, state.requestCacheKey) && isActiveTab && updatedEl) { updatedEl.textContent = `Updated ${new Date().toLocaleTimeString()}`; updatedEl.classList.remove("loading"); }
        break;
      case "error":
        _finalizeToolGroup(state);
        _evolveHideThinking(container);
        _cancelEvolveMarkdownRender(state.textBlock);
        if (isCurrentScopeKey(tab, state.requestCacheKey)) {
          if (isActiveTab && updatedEl) { updatedEl.textContent = `Error: ${evt.message}`; updatedEl.classList.remove("loading"); }
          const panel2 = _ensureTabPanel(tab);
          if (panel2) panel2.innerHTML = `<div class="evolve-empty-state"><p>分析失败：${esc(evt.message)}</p></div>`;
        }
        break;
      case "timeout":
        _finalizeToolGroup(state);
        _evolveHideThinking(container);
        _cancelEvolveMarkdownRender(state.textBlock);
        if (isCurrentScopeKey(tab, state.requestCacheKey)) {
          const message = evt.message || "分析超时";
          if (isActiveTab && updatedEl) { updatedEl.textContent = `Timeout: ${message}`; updatedEl.classList.remove("loading"); }
          const panel3 = _ensureTabPanel(tab);
          if (panel3) panel3.innerHTML = `<div class="evolve-empty-state"><p>分析超时：${esc(message)}</p></div>`;
        }
        break;
    }
  }

  function refreshEvolveTab(tab) {
    if (evolveLoadingTabs[tab]) return; // only block same tab, not others
    evolveLoadingTabs[tab] = true;
    const updatedEl = $("#evolve-tab-updated");
    const isAI = AI_TABS.has(tab);
    const panel = _ensureTabPanel(tab);

    if (!isAI && panel) {
      panel.innerHTML = `<div class="evolve-skeleton"><div class="skeleton-bar"></div><div class="skeleton-bar short"></div><div class="skeleton-bar"></div><div class="skeleton-circle"></div></div>`;
      if (tab === evolveActiveTab && updatedEl) updatedEl.textContent = "分析中…";
    }

    _fetchEvolveTab(tab)
      .catch(err => {
        if (err.name === "AbortError") return; // user stopped — preserve partial UI
        if (panel) panel.innerHTML = `<div class="evolve-empty-state"><p>分析失败：${(window.esc || String)(err.message)}</p></div>`;
      })
      .finally(() => { delete evolveLoadingTabs[tab]; });
  }

  function refreshAllEvolveTabs() {
    const tabs = ["profile", "memory", "rules", "signals", "patterns"];
    // Non-AI tabs run in parallel; AI tabs run sequentially (server resource)
    const nonAI = tabs.filter(t => !AI_TABS.has(t));
    const ai = tabs.filter(t => AI_TABS.has(t));

    // Fire all non-AI tabs in parallel
    nonAI.forEach(tab => refreshEvolveTab(tab));

    // AI tabs sequentially (they're expensive)
    let idx = 0;
    function doNextAI() {
      if (idx >= ai.length) return;
      const tab = ai[idx++];
      evolveLoadingTabs[tab] = true;
      _fetchEvolveTab(tab)
        .catch(() => {})
        .finally(() => { delete evolveLoadingTabs[tab]; setTimeout(doNextAI, 300); });
    }
    doNextAI();
  }

  // ── Parse AI response to structured data (still used by AI Analysis chat in app.js) ──
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

  // ── Validate and normalize AI JSON data ──
  function normalizeEvolveData(tab, data) {
    if (!data || data._parseError) return data;
    switch (tab) {
      case "profile":
        if (!Array.isArray(data.categories)) data.categories = [];
        data.categories.forEach(c => {
          if (!Array.isArray(c.items)) c.items = [];
          if (!Array.isArray(c.tags)) c.tags = [];
          c.items = c.items.map(item => typeof item === "string" ? { text: item } : item);
        });
        if (!data.radar) data.radar = { dimensions: [] };
        if (!Array.isArray(data.radar.dimensions)) data.radar.dimensions = [];
        break;
      case "memory":
        if (!Array.isArray(data.nodes)) data.nodes = [];
        if (!Array.isArray(data.links)) data.links = [];
        if (!Array.isArray(data.cards)) data.cards = [];
        break;
      case "rules":
        if (!Array.isArray(data.rules)) data.rules = [];
        data.rules.forEach(r => { if (!Array.isArray(r.evidence)) r.evidence = []; });
        break;
      case "signals":
        if (!Array.isArray(data.timeline)) data.timeline = [];
        if (!Array.isArray(data.events)) data.events = [];
        break;
      case "patterns":
        if (!Array.isArray(data.bubbles)) data.bubbles = [];
        if (!Array.isArray(data.cards)) data.cards = [];
        break;
    }
    return data;
  }

  // ── Tab renderers ──
  function renderProfileTab(data, container) {
    if (data._parseError) {
      container.innerHTML = `<div class="evolve-raw-result">${(window.renderMarkdownSimple || window.esc || String)(data._raw)}</div>`;
      return;
    }
    container.innerHTML = "";

    // Categories section — main profile content
    const categories = data.categories || [];
    if (categories.length) {
      const grid = document.createElement("div");
      grid.className = "profile-categories";
      container.appendChild(grid);

      categories.forEach(cat => {
        const card = document.createElement("div");
        card.className = "profile-category-card";
        let html = `<div class="profile-cat-header"><span class="profile-cat-icon">${cat.icon || "📋"}</span><span class="profile-cat-name">${esc(cat.name || "")}</span></div>`;

        // Tags (short labels like tech names)
        if (cat.tags && cat.tags.length) {
          html += `<div class="profile-cat-tags">${cat.tags.map(t => `<span class="evolve-tag">${esc(String(t))}</span>`).join("")}</div>`;
        }

        // Items (detailed facts)
        if (cat.items && cat.items.length) {
          html += `<ul class="profile-cat-items">`;
          cat.items.forEach(item => {
            const text = typeof item === "string" ? item : (item.text || "");
            const conf = typeof item === "object" ? item.confidence : null;
            const confClass = conf === "low" ? " low-conf" : "";
            html += `<li class="profile-item${confClass}">${esc(text)}</li>`;
          });
          html += `</ul>`;
        }
        card.innerHTML = html;
        grid.appendChild(card);
      });
    }

    // Radar chart — ability dimensions (auto-discovered from conversations)
    if (data.radar?.dimensions?.length) {
      const radarSection = document.createElement("div");
      radarSection.className = "profile-radar-section";
      radarSection.innerHTML = `<div class="profile-section-title">能力雷达</div>`;
      container.appendChild(radarSection);

      const radarWrapper = document.createElement("div");
      radarWrapper.className = "profile-radar-wrapper";
      radarSection.appendChild(radarWrapper);

      const chartDiv = document.createElement("div");
      chartDiv.className = "profile-radar-chart";
      radarWrapper.appendChild(chartDiv);
      drawRadarChart(chartDiv, data.radar.dimensions);

      // Radar legend with evidence
      const legendDiv = document.createElement("div");
      legendDiv.className = "profile-radar-legend";
      radarWrapper.appendChild(legendDiv);
      data.radar.dimensions.forEach(dim => {
        const pct = Math.round((dim.score || 0) * 100);
        legendDiv.innerHTML += `<div class="radar-legend-item">
          <span class="radar-legend-bar"><span class="radar-legend-fill" style="width:${pct}%"></span></span>
          <span class="radar-legend-name">${esc(dim.name || "")}</span>
          <span class="radar-legend-pct">${pct}%</span>
          ${dim.evidence ? `<span class="radar-legend-evidence">${esc(dim.evidence)}</span>` : ""}
        </div>`;
      });
    }

    if (!categories.length && !data.radar?.dimensions?.length) {
      container.innerHTML = '<div class="evolve-empty-state"><p>暂无用户画像数据</p></div>';
    }
  }

  function drawRadarChart(container, dimensions) {
    const width = 280, height = 280, margin = 50;
    const radius = Math.min(width, height) / 2 - margin;
    const levels = 5;
    const n = dimensions.length;
    if (n < 3) return; // Need at least 3 dimensions for radar
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

    // Draw axes + labels
    dimensions.forEach((d, i) => {
      const angle = angleSlice * i - Math.PI / 2;
      const x = radius * Math.cos(angle);
      const y = radius * Math.sin(angle);
      svg.append("line")
        .attr("x1", 0).attr("y1", 0).attr("x2", x).attr("y2", y)
        .style("stroke", "var(--border-light)").style("stroke-width", "1");
      const lx = (radius + 18) * Math.cos(angle);
      const ly = (radius + 18) * Math.sin(angle);
      svg.append("text")
        .attr("x", lx).attr("y", ly)
        .attr("text-anchor", "middle").attr("dominant-baseline", "middle")
        .style("font-size", "10px").style("fill", "var(--text-secondary)")
        .text(d.name || "");
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
      svg.append("circle")
        .attr("cx", p[0]).attr("cy", p[1]).attr("r", 4)
        .style("fill", "var(--accent)")
        .style("stroke", "white").style("stroke-width", "1.5");
    });
  }

  function renderMemoryTab(data, container) {
    if (data._parseError) {
      container.innerHTML = `<div class="evolve-raw-result">${(window.renderMarkdownSimple || window.esc || String)(data._raw)}</div>`;
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
        const typeColors = {
            preference: "var(--accent)", workflow: "var(--bash-accent)",
            tooling: "var(--read-accent)", design: "var(--edit-accent)",
            communication: "var(--grep-accent)",
            "偏好": "var(--accent)", "工作流": "var(--bash-accent)",
            "工具": "var(--read-accent)", "设计": "var(--edit-accent)",
            "沟通": "var(--grep-accent)"
        };
        const node = (data.nodes || []).find(n => n.id === card.id);
        const type = node?.type || "preference";
        const conf = node?.confidence || "medium";
        const trigger = card.trigger || "";
        const instruction = card.instruction || "";
        const avoid = card.avoid || "";
        const hasV2 = trigger && instruction;

        let bodyHtml = "";
        if (hasV2) {
          bodyHtml = `<div class="memory-card-body">
            <div class="memory-field"><span class="memory-field-label">When:</span> ${esc(trigger)}</div>
            <div class="memory-field"><span class="memory-field-label">Do:</span> ${esc(instruction)}</div>
            ${avoid ? `<div class="memory-field"><span class="memory-field-label">Avoid:</span> ${esc(avoid)}</div>` : ""}
          </div>`;
        } else {
          bodyHtml = `<div class="memory-card-body">${esc(card.content || "")}</div>`;
        }

        let evidenceHtml = "";
        if (Array.isArray(card.evidence) && card.evidence.length) {
          const items = card.evidence.slice(0, 3).map(ev =>
            typeof ev === "object" ? `"${esc(ev.quote || "")}" <span class="evidence-meta">(${esc(ev.date || "")})</span>` : esc(String(ev))
          ).join("<br>");
          evidenceHtml = `<div class="memory-card-evidence">${items}</div>`;
        } else if (typeof card.evidence === "string" && card.evidence) {
          evidenceHtml = `<div class="memory-card-evidence">"${esc(card.evidence)}"</div>`;
        }

        const priorityBadge = node?.priority ? `<span class="memory-priority ${node.priority}">${node.priority}</span>` : "";
        const statusBadge = node?.status === "stale" ? `<span class="memory-status stale">stale</span>` : "";
        const conflictsHtml = (card.conflictsWith?.length)
          ? `<span class="memory-conflicts" title="Conflicts with: ${card.conflictsWith.join(', ')}">⚡</span>` : "";

        div.innerHTML = `<div class="memory-card-header">
            <span class="memory-type-dot" style="background:${typeColors[type] || "var(--accent)"}"></span>
            <span class="memory-card-label">${esc(node?.label || card.id)}</span>
            ${priorityBadge}${statusBadge}${conflictsHtml}
            <span class="memory-confidence ${conf}">${conf}</span>
          </div>
          ${bodyHtml}
          <div class="memory-card-meta">
            ${card.firstSeen ? `<span>First: ${card.firstSeen}</span>` : ""}
            ${card.lastSeen ? `<span>Last: ${card.lastSeen}</span>` : ""}
          </div>
          ${evidenceHtml}`;
        listDiv.appendChild(div);
      });
    }

    if (data.nodes?.length) {
      const graphNodes = JSON.parse(JSON.stringify(data.nodes || []));
      const graphLinks = JSON.parse(JSON.stringify(data.links || []));
      drawForceGraph(graphDiv, graphNodes, graphLinks, (nodeId) => {
        // Highlight corresponding card
        listDiv.querySelectorAll(".evolve-memory-card").forEach(c => {
          c.classList.toggle("highlighted", c.dataset.id === nodeId);
        });
        const target = [...listDiv.querySelectorAll(".evolve-memory-card")].find(c => c.dataset.id === nodeId);
        if (target) target.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    }
  }

  function drawForceGraph(container, nodes, links, onNodeClick) {
    const rect = container.getBoundingClientRect();
    const width = Math.max(rect.width || 450, 300);
    const height = Math.max(rect.height || 350, 280);
    const typeColors = {
        preference: "#5856d6", workflow: "#16a34a",
        tooling: "#d97706", design: "#ea580c",
        communication: "#2563eb",
        "偏好": "#5856d6", "工作流": "#16a34a",
        "工具": "#d97706", "设计": "#ea580c",
        "沟通": "#2563eb"
    };
    const typeLabels = { preference: "偏好", workflow: "工作流", tooling: "工具", design: "设计", communication: "沟通" };
    const n = nodes.length;

    // ── SVG + zoom layer ──
    const svg = d3.select(container).append("svg")
      .attr("viewBox", `0 0 ${width} ${height}`)
      .style("width", "100%").style("height", "100%");

    // Defs: glow filter for hover
    const defs = svg.append("defs");
    const filter = defs.append("filter").attr("id", "glow").attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
    filter.append("feGaussianBlur").attr("stdDeviation", "3").attr("result", "blur");
    const merge = filter.append("feMerge");
    merge.append("feMergeNode").attr("in", "blur");
    merge.append("feMergeNode").attr("in", "SourceGraphic");

    const g = svg.append("g"); // zoom target

    const zoom = d3.zoom()
      .scaleExtent([0.3, 4])
      .on("zoom", (e) => g.attr("transform", e.transform));
    svg.call(zoom);

    // ── Tooltip ──
    const tooltip = d3.select(container).append("div")
      .style("position", "absolute").style("pointer-events", "none")
      .style("background", "var(--bg-card, #fff)").style("border", "1px solid var(--border-light, #e0e0e0)")
      .style("border-radius", "6px").style("padding", "6px 10px").style("font-size", "11px")
      .style("box-shadow", "0 4px 12px rgba(0,0,0,.12)").style("opacity", 0)
      .style("transition", "opacity .15s").style("z-index", "10").style("max-width", "200px");

    // ── Type clustering: assign cluster center per type ──
    const types = [...new Set(nodes.map(d => d.type || "preference"))];
    const angleStep = (2 * Math.PI) / Math.max(types.length, 1);
    const clusterR = Math.min(width, height) * 0.25;
    const typeCenters = {};
    types.forEach((t, i) => {
      typeCenters[t] = {
        x: width / 2 + clusterR * Math.cos(angleStep * i - Math.PI / 2),
        y: height / 2 + clusterR * Math.sin(angleStep * i - Math.PI / 2)
      };
    });

    // ── Forces: adaptive to node count ──
    const nodeIds = new Set(nodes.map(n => n.id));
    const validLinks = links.filter(l => nodeIds.has(l.source) && nodeIds.has(l.target));
    const chargeStrength = n > 30 ? -60 : n > 15 ? -80 : -100;
    const linkDist = n > 30 ? 40 : n > 15 ? 55 : 70;

    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(validLinks).id(d => d.id).distance(linkDist).strength(d => d.strength || 0.4))
      .force("charge", d3.forceManyBody().strength(chargeStrength))
      .force("x", d3.forceX(d => typeCenters[d.type || "preference"].x).strength(0.08))
      .force("y", d3.forceY(d => typeCenters[d.type || "preference"].y).strength(0.08))
      .force("center", d3.forceCenter(width / 2, height / 2).strength(0.02))
      .force("collision", d3.forceCollide().radius(d => _nodeR(d) + 3));

    activeSimulation = simulation;

    function _nodeR(d) { return Math.sqrt(d.frequency || 1) * 4 + 4; }

    // ── Links ──
    const link = g.append("g").attr("class", "links").selectAll("line")
      .data(validLinks).enter().append("line")
      .style("stroke", "var(--border-light, #ddd)").style("stroke-opacity", 0.5)
      .style("stroke-width", d => Math.max((d.strength || 0.3) * 2, 0.5));

    // ── Nodes ──
    const node = g.append("g").attr("class", "nodes").selectAll("g")
      .data(nodes).enter().append("g")
      .style("cursor", "pointer")
      .on("click", (e, d) => { if (onNodeClick) onNodeClick(d.id); })
      .on("mouseenter", (e, d) => {
        d3.select(e.currentTarget).select("circle").style("filter", "url(#glow)");
        // Highlight connected links
        link.style("stroke-opacity", l =>
          (l.source.id || l.source) === d.id || (l.target.id || l.target) === d.id ? 1 : 0.1
        ).style("stroke-width", l =>
          (l.source.id || l.source) === d.id || (l.target.id || l.target) === d.id ? 2.5 : 0.5
        );
        node.style("opacity", nd =>
          nd.id === d.id || validLinks.some(l =>
            ((l.source.id || l.source) === d.id && (l.target.id || l.target) === nd.id) ||
            ((l.target.id || l.target) === d.id && (l.source.id || l.source) === nd.id)
          ) ? 1 : 0.25
        );
        // Tooltip
        const cRect = container.getBoundingClientRect();
        const type = d.type || "preference";
        tooltip.html(`<b>${esc(d.label || d.id)}</b><br><span style="color:${typeColors[type]}">${typeLabels[type] || type}</span> · ${d.confidence || "medium"}<br>频次: ${d.frequency || 1}`)
          .style("left", (e.clientX - cRect.left + 12) + "px")
          .style("top", (e.clientY - cRect.top - 10) + "px")
          .style("opacity", 1);
      })
      .on("mouseleave", (e) => {
        d3.select(e.currentTarget).select("circle").style("filter", null);
        link.style("stroke-opacity", 0.5).style("stroke-width", d => Math.max((d.strength || 0.3) * 2, 0.5));
        node.style("opacity", 1);
        tooltip.style("opacity", 0);
      })
      .call(d3.drag()
        .on("start", (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on("end", (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
      );

    node.append("circle")
      .attr("r", d => _nodeR(d))
      .style("fill", d => typeColors[d.type] || "#5856d6")
      .style("fill-opacity", d => d.confidence === "high" ? 0.85 : d.confidence === "medium" ? 0.55 : 0.3)
      .style("stroke", d => typeColors[d.type] || "#5856d6")
      .style("stroke-width", d => d.confidence === "low" ? 1 : 1.5)
      .style("stroke-dasharray", d => d.confidence === "low" ? "3,2" : "none")
      .style("transition", "filter .15s");

    node.append("text")
      .text(d => d.label?.length > 12 ? d.label.substring(0, 12) + "…" : d.label)
      .attr("dy", d => -(_nodeR(d) + 5))
      .attr("text-anchor", "middle")
      .style("font-size", "9px").style("fill", "var(--text-muted)")
      .style("pointer-events", "none");

    // ── Type legend ──
    const legend = svg.append("g").attr("transform", `translate(8, ${height - types.length * 16 - 4})`);
    types.forEach((t, i) => {
      const lg = legend.append("g").attr("transform", `translate(0, ${i * 16})`);
      lg.append("circle").attr("r", 4).attr("cx", 4).attr("cy", 0)
        .style("fill", typeColors[t] || "#5856d6");
      lg.append("text").attr("x", 12).attr("dy", "0.35em")
        .text(typeLabels[t] || t)
        .style("font-size", "9px").style("fill", "var(--text-muted)");
    });

    // ── Zoom controls ──
    const controls = d3.select(container).append("div")
      .style("position", "absolute").style("top", "8px").style("right", "8px")
      .style("display", "flex").style("flex-direction", "column").style("gap", "4px");

    [{ label: "+", scale: 1.4 }, { label: "−", scale: 1 / 1.4 }, { label: "⊙", scale: 0 }].forEach(btn => {
      const b = controls.append("button")
        .text(btn.label)
        .style("width", "26px").style("height", "26px")
        .style("border", "1px solid var(--border-light, #ddd)").style("border-radius", "4px")
        .style("background", "var(--bg-card, #fff)").style("cursor", "pointer")
        .style("font-size", "14px").style("line-height", "1").style("color", "var(--text-secondary, #666)")
        .style("display", "flex").style("align-items", "center").style("justify-content", "center");
      b.on("click", () => {
        if (btn.scale === 0) {
          // Fit to view
          svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity);
        } else {
          svg.transition().duration(200).call(zoom.scaleBy, btn.scale);
        }
      });
    });

    // ── Tick ──
    simulation.on("tick", () => {
      link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
      node.attr("transform", d => `translate(${d.x},${d.y})`);
    });

    // After stabilization, fit to content
    simulation.on("end", () => {
      const xs = nodes.map(d => d.x), ys = nodes.map(d => d.y);
      const x0 = Math.min(...xs) - 30, x1 = Math.max(...xs) + 30;
      const y0 = Math.min(...ys) - 30, y1 = Math.max(...ys) + 30;
      const bw = x1 - x0, bh = y1 - y0;
      const scale = Math.min(width / bw, height / bh, 1.5);
      const tx = (width - bw * scale) / 2 - x0 * scale;
      const ty = (height - bh * scale) / 2 - y0 * scale;
      svg.transition().duration(600).call(zoom.transform,
        d3.zoomIdentity.translate(tx, ty).scale(scale));
    });
  }

  function renderRulesTab(data, container) {
    if (data._parseError) {
      container.innerHTML = `<div class="evolve-raw-result">${(window.renderMarkdownSimple || window.esc || String)(data._raw)}</div>`;
      return;
    }
    container.innerHTML = "";
    const rules = data.rules || [];
    if (!rules.length) { container.innerHTML = '<div class="evolve-empty-state"><p>暂无规则建议</p></div>'; return; }

    // Top bar: category filter + copy all
    const topBar = document.createElement("div");
    topBar.className = "rules-top-bar";
    container.appendChild(topBar);

    // Category filter
    const categories = [...new Set(rules.map(r => r.category))];
    const filterBar = document.createElement("div");
    filterBar.className = "rules-filter-bar";
    let activeFilter = "all";
    topBar.appendChild(filterBar);

    // Copy all button
    const copyAllBtn = document.createElement("button");
    copyAllBtn.className = "rules-copy-all-btn";
    copyAllBtn.innerHTML = '<span class="rules-copy-icon">📋</span> Copy All';
    copyAllBtn.onclick = () => {
      const filtered = activeFilter === "all" ? rules : rules.filter(r => r.category === activeFilter);
      filtered.sort((a, b) => ({"P0":0,"P1":1,"P2":2}[a.priority]??9) - ({"P0":0,"P1":1,"P2":2}[b.priority]??9));
      const allText = filtered.map(r => r.rule || "").join("\n\n");
      _copyToClipboard(allText, copyAllBtn);
    };
    topBar.appendChild(copyAllBtn);

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

        // Header: priority + category + frequency + copy button
        const evidenceHtml = (rule.evidence || []).map(e =>
          `<div class="rule-evidence-item"><span class="rule-quote">"${esc(e.quote)}"</span>${e.session ? ` <a class="rule-session-link" href="#${e.session}">→ session</a>` : ""}</div>`
        ).join("");

        const whyText = rule.why || "";

        card.innerHTML = `<div class="rule-card-header">
            <span class="rule-priority-badge">${esc(rule.priority || "P2")}</span>
            <span class="rule-category">${esc(rule.category || "")}</span>
            ${rule.frequency ? `<span class="rule-freq">${rule.frequency}x</span>` : ""}
            <button class="rule-copy-btn" title="复制规则">📋</button>
          </div>
          <div class="rule-text">${esc(rule.rule)}</div>
          ${whyText ? `<details class="rule-why-details"><summary>Why</summary><div class="rule-why-text">${esc(whyText)}</div></details>` : ""}
          ${evidenceHtml ? `<details class="rule-evidence"><summary>Evidence (${rule.evidence.length})</summary>${evidenceHtml}</details>` : ""}`;

        // Bind copy button — only copy rule text
        const copyBtn = card.querySelector(".rule-copy-btn");
        if (copyBtn) copyBtn.onclick = (e) => { e.stopPropagation(); _copyToClipboard(rule.rule || "", copyBtn); };

        cardsContainer.appendChild(card);
      });
    }
    renderFilter();
    renderCards();
  }

  /** Copy text to clipboard and show feedback on the button */
  function _copyToClipboard(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
      const orig = btn.innerHTML;
      btn.innerHTML = btn.classList.contains("rules-copy-all-btn") ? '<span class="rules-copy-icon">✓</span> Copied!' : "✓";
      btn.classList.add("copied");
      setTimeout(() => { btn.innerHTML = orig; btn.classList.remove("copied"); }, 1500);
    }).catch(() => {
      // Fallback for non-HTTPS
      const ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      const orig = btn.innerHTML;
      btn.innerHTML = btn.classList.contains("rules-copy-all-btn") ? '<span class="rules-copy-icon">✓</span> Copied!' : "✓";
      btn.classList.add("copied");
      setTimeout(() => { btn.innerHTML = orig; btn.classList.remove("copied"); }, 1500);
    });
  }

  function renderSignalsTab(data, container) {
    if (data._parseError) {
      container.innerHTML = `<div class="evolve-raw-result">${(window.renderMarkdownSimple || window.esc || String)(data._raw)}</div>`;
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

  function renderPatternsTab(data, container) {
    if (data._parseError) {
      container.innerHTML = `<div class="evolve-raw-result">${(window.renderMarkdownSimple || window.esc || String)(data._raw)}</div>`;
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

  // ── Sync to Claude Code ──
  const SYNC_TABS = new Set(["profile", "memory"]);

  function updateSyncButtonState() {
    const btn = $("#evolve-tab-sync");
    if (!btn) return;
    const hasSyncableData = SYNC_TABS.has(evolveActiveTab) && getCachedTab(evolveActiveTab);
    btn.disabled = !hasSyncableData;
  }

  function toggleSyncPanel() {
    const panel = $("#evolve-sync-panel");
    if (!panel) return;
    if (!panel.classList.contains("hidden")) {
      panel.classList.add("hidden");
      panel.innerHTML = "";
      return;
    }
    // Show panel and fetch preview
    panel.classList.remove("hidden");
    panel.innerHTML = '<div style="padding:8px 0;color:var(--text-muted);font-size:12px">Loading preview...</div>';

    const targets = [];
    if (getCachedTab("memory")) targets.push("memory");
    if (getCachedTab("profile")) targets.push("claude_md");

    if (targets.length === 0) {
      panel.innerHTML = '<div style="padding:8px 0;color:var(--text-muted)">No Profile or Memory data to sync. Run Refresh first.</div>';
      return;
    }

    fetch("/api/evolve/sync", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({action: "preview", targets, scope: getEvolveScope()})
    })
      .then(r => r.json())
      .then(data => renderSyncPanel(panel, data, targets))
      .catch(err => {
        panel.innerHTML = `<div style="color:var(--danger,#e53e3e)">Preview failed: ${(window.esc || String)(err.message)}</div>`;
      });
  }

  function renderSyncPanel(panel, preview, initialTargets) {
    const esc = window.esc || String;
    let html = '<div class="sync-panel-title">同步到 Claude Code</div>';

    // Memory target
    const memData = preview.memory;
    const hasMemory = memData && !memData.error;
    html += `<div class="sync-target${hasMemory ? '' : ' disabled'}" id="sync-target-memory">
      <input type="checkbox" id="sync-check-memory" ${hasMemory ? 'checked' : 'disabled'}>
      <div class="sync-target-info">
        <div class="sync-target-label">Memory</div>
        <div class="sync-target-path">~/.claude/memory/</div>
        <div class="sync-target-summary">`;
    if (hasMemory) {
      const s = memData.summary;
      html += `+${s.create} new · ~${s.update} update · ${s.skip} skip`;
    } else {
      html += esc(memData ? memData.error : "No memory data");
    }
    html += `</div></div></div>`;

    // CLAUDE.md target
    const mdData = preview.claude_md;
    const hasMd = mdData && !mdData.error;
    html += `<div class="sync-target${hasMd ? '' : ' disabled'}" id="sync-target-claude-md">
      <input type="checkbox" id="sync-check-claude-md" ${hasMd ? 'checked' : 'disabled'}>
      <div class="sync-target-info">
        <div class="sync-target-label">CLAUDE.md</div>
        <div class="sync-target-path">~/.claude/CLAUDE.md</div>
        <div class="sync-target-summary">`;
    if (hasMd) {
      const action = mdData.status === "replace" ? "替换" : "追加";
      html += `${action} User Profile 段落 (${mdData.categories} 分类, ${mdData.radar_dims} 雷达维度, ~${mdData.lines} 行)`;
    } else {
      html += esc(mdData ? mdData.error : "No profile data");
    }
    html += `</div></div></div>`;

    // Actions
    const canSync = hasMemory || hasMd;
    html += `<div class="sync-actions">
      <button class="btn-text" id="sync-cancel">取消</button>
      <button class="btn-text btn-confirm" id="sync-confirm" ${canSync ? '' : 'disabled'}>确认同步</button>
    </div>`;

    panel.innerHTML = html;

    // Bind events
    const cancelBtn = panel.querySelector("#sync-cancel");
    if (cancelBtn) cancelBtn.onclick = () => { panel.classList.add("hidden"); panel.innerHTML = ""; };

    const confirmBtn = panel.querySelector("#sync-confirm");
    if (confirmBtn) confirmBtn.onclick = () => executeSyncFromPanel(panel);
  }

  function executeSyncFromPanel(panel) {
    const targets = [];
    const memCheck = panel.querySelector("#sync-check-memory");
    const mdCheck = panel.querySelector("#sync-check-claude-md");
    if (memCheck && memCheck.checked) targets.push("memory");
    if (mdCheck && mdCheck.checked) targets.push("claude_md");

    if (targets.length === 0) return;

    const confirmBtn = panel.querySelector("#sync-confirm");
    if (confirmBtn) { confirmBtn.disabled = true; confirmBtn.textContent = "同步中..."; }

    fetch("/api/evolve/sync", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({action: "execute", targets, scope: getEvolveScope()})
    })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          let msg = "✓ 同步完成 — ";
          const parts = [];
          if (data.memory) parts.push(`Memory: +${data.memory.created} new, ~${data.memory.updated} updated`);
          if (data.claude_md) parts.push(`CLAUDE.md: ${data.claude_md.status} (${data.claude_md.lines} lines)`);
          msg += parts.join("; ");
          panel.innerHTML = `<div class="sync-result">${(window.esc || String)(msg)}</div>`;
        } else {
          const errors = [];
          if (data.memory && data.memory.error) errors.push(`Memory: ${data.memory.error}`);
          if (data.claude_md && data.claude_md.error) errors.push(`CLAUDE.md: ${data.claude_md.error}`);
          panel.innerHTML = `<div class="sync-result error">${(window.esc || String)(errors.join("; ") || "Sync failed")}</div>`;
        }
        setTimeout(() => { panel.classList.add("hidden"); panel.innerHTML = ""; }, 3000);
      })
      .catch(err => {
        panel.innerHTML = `<div class="sync-result error">Sync failed: ${(window.esc || String)(err.message)}</div>`;
      });
  }

  // ── Public API for app.js linkage ──
  window.getEvolveScope = getEvolveScope;

  function abortEvolveStream(tab, message) {
    if (evolveStreamAborts[tab]) {
      try { evolveStreamAborts[tab].abort(); } catch (e) { /* ignore */ }
      delete evolveStreamAborts[tab];
    }
    delete evolveLoadingTabs[tab];
    const panel = _ensureTabPanel(tab);
    if (panel) panel.innerHTML = `<div class="evolve-empty-state"><p>${(window.esc || String)(message || "分析已取消")}</p></div>`;
    const updatedEl = $("#evolve-tab-updated");
    if (tab === evolveActiveTab && updatedEl) {
      updatedEl.textContent = "已取消";
      updatedEl.classList.remove("loading");
    }
  }

  window.abortEvolveStreams = function () {
    Object.keys(evolveStreamAborts).forEach(tab => abortEvolveStream(tab, "Scope 已变化，已取消旧分析"));
  };

  window.navigateToEvolveTab = function (tab, data) {
    if (data) setCachedTab(tab, data);
    switchEvolveTab(tab);
    updateEvolveOverviewBar();
  };

  window.parseEvolveResponseExternal = function (tab, raw) {
    return parseEvolveResponse(tab, raw);
  };

})();
