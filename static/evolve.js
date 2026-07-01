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
  let evolveLoadingScopes = {}; // {tab: scopeKey} — loading state belongs to which scope
  let evolveProgressState = {}; // {tab: {runId, stepCount, usageInput, usageOutput, starting, recovered}}
  let activeSimulation = null;
  let evolveStreamAborts = {}; // {tab: AbortController} — per-tab stream abort
  let evolveDetachedTabs = {}; // {tab: true} — detachOnly markers
  let evolveRecoveredRunPollers = {}; // {tab: {timer, scopeKey}} — resume backend progress after rehydrate
  let evolveScopeSource = "all";
  let evolveScopeDate = "7d";
  let evolveScopeProject = "";
  let evolveScopeEngine = "auto";
  let evolveScopeLang = "zh";
  const EVOLVE_ACTIVE_TAB_KEY = "chatview-evolve-active-tab";
  const EVOLVE_ACTIVE_RUN_KEY = "chatview-evolve-active-run-id";
  const EVOLVE_TABS = ["profile", "memory", "rules", "signals", "patterns"];
  const AI_TABS = new Set(EVOLVE_TABS);

  // ── Page-refresh guard (Fix 3: survive page refresh) ──
  let _beforeUnloadBound = false;
  if (!_beforeUnloadBound) {
    _beforeUnloadBound = true;
    window.addEventListener("beforeunload", (e) => {
      if (Object.keys(evolveStreamAborts).length > 0) {
        e.preventDefault();
        e.returnValue = "";
      }
    });
    try {
      const wasInterrupted = localStorage.getItem("evolve-mid-analysis");
      if (wasInterrupted) window._evolveWasInterrupted = true;
    } catch (e) {
      /* ignore */
    }
  }

  // ── DOM refs ──
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  function _getEvolveUpdatedEl() {
    const el = $("#evolve-tab-updated");
    if (el && el.hasAttribute("data-i18n")) {
      el.removeAttribute("data-i18n");
    }
    return el;
  }

  // ── i18n (shared via app.js) ──
  let _i18nRegistered = false;
  function _registerEvolveI18n() {
    if (_i18nRegistered || !window.registerI18n) return;
    _i18nRegistered = true;
    window.registerI18n({
      zh: {
        "evolve.status.never": "尚未分析",
        "evolve.status.aiRunning": "AI 执行中…",
        "evolve.status.aiRunningSteps": "AI 执行中… ({n} steps)",
        "evolve.status.aiRunningTokens": "AI 执行中… ({in}↑ / {out}↓ tokens)",
        "evolve.status.aiStarting": "AI 启动中…",
        "evolve.status.checking": "正在恢复后端进度…",
        "evolve.status.aiGenerating": "AI 分析生成中…",
        "evolve.status.stopped": "已停止",
        "evolve.status.analyzing": "分析中…",
        "evolve.error.analyzeFailed": "分析失败：{error}",
        "evolve.error.timedOut": "AI 分析超时",
        "evolve.error.retryHint": "点击 🔄 Refresh 重试",
        "evolve.btn.retry": "重试",
        "evolve.btn.startAnalysis": "开始分析",
        "evolve.btn.stop": "■ 停止",
        "evolve.btn.refresh": "🔄 刷新",
        "evolve.banner.interrupted": "分析因页面刷新而中断。点击刷新继续。",
        "evolve.empty.refreshHint": "点击 🔄 Refresh 开始分析最近的对话",
        "evolve.empty.initial": "点击刷新，开始分析最近的对话",
        "evolve.empty.profile": "暂无用户画像数据",
        "evolve.empty.memory": "暂无记忆卡片数据",
        "evolve.empty.rules": "暂无规则建议",
        "evolve.empty.signals": "暂无纠正记录",
        "evolve.empty.patterns": "暂无重复模式",
        "evolve.profile.radarTitle": "能力雷达",
        "evolve.field.frequency": "频次:",
        "evolve.rules.copyTitle": "复制规则",
        "evolve.sync.title": "同步到 Claude Code",
        "evolve.sync.replace": "替换",
        "evolve.sync.append": "追加",
        "evolve.sync.mdSummary":
          "{action} User Profile 段落 ({categories} 分类, {radar_dims} 雷达维度, ~{lines} 行)",
        "evolve.sync.cancel": "取消",
        "evolve.sync.confirm": "确认同步",
        "evolve.sync.syncing": "同步中...",
        "evolve.sync.done": "✓ 同步完成 — ",
        "evolve.chat.inputPlaceholder": "输入跨会话分析需求…",
        // Tab labels
        "evolve.tab.profile": "画像",
        "evolve.tab.memory": "记忆",
        "evolve.tab.rules": "规则",
        "evolve.tab.signals": "信号",
        "evolve.tab.patterns": "模式",
        // Overview bar
        "evolve.overview.lastScan": "上次扫描：{time}",
        // Time ago
        "evolve.time.justNow": "刚刚",
        "evolve.time.mAgo": "{n} 分钟前",
        "evolve.time.hAgo": "{n} 小时前",
        "evolve.time.dAgo": "{n} 天前",
        // Rules
        "evolve.rules.copyAll": "全部复制",
        "evolve.rules.filterAll": "全部",
        "evolve.rules.why": "为什么",
        "evolve.rules.evidence": "证据",
        "evolve.rules.sessionLink": "→ 会话",
        // Tool group
        "evolve.tools.groupHeader": "⚡ {n} 个工具",
        // Force graph type labels (Chinese already present — these map when lang=zh)
        "evolve.graph.type.preference": "偏好",
        "evolve.graph.type.workflow": "工作流",
        "evolve.graph.type.tooling": "工具",
        "evolve.graph.type.design": "设计",
        "evolve.graph.type.communication": "沟通",
        // Storage quota
        "evolve.quotaWarning": "存储空间不足 — Evolve 缓存可能无法持久化。",
        // Updated label
        "evolve.updated": "更新于 {time}",
        "evolve.progress.runLabel": "Run {id}",
        "evolve.progress.live": "实时执行中",
        "evolve.progress.recovered": "已从后端恢复执行进度",
        "evolve.progress.steps": "{n} steps",
        "evolve.progress.tokens": "{in}↑ / {out}↓ tokens",
        // Bubble chart types
        "evolve.bubble.error": "错误",
        "evolve.bubble.efficiency": "效率",
        "evolve.bubble.knowledge_gap": "知识缺口",
        "evolve.bubble.workflow": "工作流",
        // Session link
        "evolve.sessionLink": "→ 会话",
      },
      en: {
        "evolve.status.never": "Not analyzed yet",
        "evolve.status.aiRunning": "AI running…",
        "evolve.status.aiRunningSteps": "AI running… ({n} steps)",
        "evolve.status.aiRunningTokens": "AI running… ({in}↑ / {out}↓ tokens)",
        "evolve.status.aiStarting": "AI starting…",
        "evolve.status.checking": "Restoring backend progress…",
        "evolve.status.aiGenerating": "AI generating analysis…",
        "evolve.status.stopped": "Stopped",
        "evolve.status.analyzing": "Analyzing…",
        "evolve.error.analyzeFailed": "Analysis failed: {error}",
        "evolve.error.timedOut": "AI analysis timed out",
        "evolve.error.retryHint": "Click 🔄 Refresh to retry",
        "evolve.btn.retry": "Retry",
        "evolve.btn.startAnalysis": "Start Analysis",
        "evolve.btn.stop": "■ Stop",
        "evolve.btn.refresh": "🔄 Refresh",
        "evolve.banner.interrupted":
          "Analysis was interrupted by page refresh. Click Refresh to continue.",
        "evolve.empty.refreshHint":
          "Click 🔄 Refresh to start analyzing recent conversations",
        "evolve.empty.initial":
          "Click Refresh to start analyzing recent conversations",
        "evolve.empty.profile": "No user profile data yet",
        "evolve.empty.memory": "No memory cards yet",
        "evolve.empty.rules": "No rule suggestions yet",
        "evolve.empty.signals": "No correction records yet",
        "evolve.empty.patterns": "No recurring patterns yet",
        "evolve.profile.radarTitle": "Ability Radar",
        "evolve.field.frequency": "Frequency:",
        "evolve.rules.copyTitle": "Copy rule",
        "evolve.sync.title": "Sync to Claude Code",
        "evolve.sync.replace": "Replace",
        "evolve.sync.append": "Append",
        "evolve.sync.mdSummary":
          "{action} User Profile section ({categories} categories, {radar_dims} radar dims, ~{lines} lines)",
        "evolve.sync.cancel": "Cancel",
        "evolve.sync.confirm": "Confirm sync",
        "evolve.sync.syncing": "Syncing...",
        "evolve.sync.done": "✓ Sync complete — ",
        "evolve.chat.inputPlaceholder":
          "Enter a cross-session analysis request…",
        // Tab labels
        "evolve.tab.profile": "Profile",
        "evolve.tab.memory": "Memory",
        "evolve.tab.rules": "Rules",
        "evolve.tab.signals": "Signals",
        "evolve.tab.patterns": "Patterns",
        // Overview bar
        "evolve.overview.lastScan": "Last scan: {time}",
        // Time ago
        "evolve.time.justNow": "just now",
        "evolve.time.mAgo": "{n}m ago",
        "evolve.time.hAgo": "{n}h ago",
        "evolve.time.dAgo": "{n}d ago",
        // Rules
        "evolve.rules.copyAll": "Copy All",
        "evolve.rules.filterAll": "All",
        "evolve.rules.why": "Why",
        "evolve.rules.evidence": "Evidence",
        "evolve.rules.sessionLink": "→ session",
        // Tool group
        "evolve.tools.groupHeader": "⚡ {n} tools",
        // Force graph type labels
        "evolve.graph.type.preference": "Preference",
        "evolve.graph.type.workflow": "Workflow",
        "evolve.graph.type.tooling": "Tooling",
        "evolve.graph.type.design": "Design",
        "evolve.graph.type.communication": "Communication",
        // Storage quota
        "evolve.quotaWarning":
          "Storage quota exceeded — Evolve cache may not persist.",
        // Updated label
        "evolve.updated": "Updated {time}",
        "evolve.progress.runLabel": "Run {id}",
        "evolve.progress.live": "Live progress",
        "evolve.progress.recovered": "Recovered from backend progress",
        "evolve.progress.steps": "{n} steps",
        "evolve.progress.tokens": "{in}↑ / {out}↓ tokens",
        // Bubble chart types
        "evolve.bubble.error": "Error",
        "evolve.bubble.efficiency": "Efficiency",
        "evolve.bubble.knowledge_gap": "Knowledge Gap",
        "evolve.bubble.workflow": "Workflow",
        // Session link
        "evolve.sessionLink": "→ session",
      },
    });
  }

  function _tt(key, vars) {
    return window.t ? window.t(key, vars) : key;
  }

  function _getLang() {
    return (window.getLang && window.getLang()) || "zh";
  }

  // ── Init (called from app.js when AI page opens) ──
  window.initEvolveView = function () {
    _registerEvolveI18n();
    loadEvolveCache();
    try {
      const storedTab =
        localStorage.getItem(EVOLVE_ACTIVE_TAB_KEY) ||
        (typeof window.getPersistedEvolveTab === "function"
          ? window.getPersistedEvolveTab()
          : "");
      if (storedTab) evolveActiveTab = storedTab;
    } catch (e) {
      /* ignore */
    }
    // Clear stale cached errors (but not "no_cache" which is an empty state)
    // so switching pages doesn't show stale "network error" messages
    _clearStaleErrorCache();
    // Scope filters are now rendered by initAiPage() in app.js
    // Read scope from shared global state
    const scope = window.getEvolveScope ? window.getEvolveScope() : {};
    if (scope.source) evolveScopeSource = scope.source;
    if (scope.date) evolveScopeDate = scope.date;
    if (scope.project !== undefined) evolveScopeProject = scope.project;
    if (scope.engine) evolveScopeEngine = scope.engine;
    if (scope.lang) evolveScopeLang = scope.lang;
    bindEvolveEvents();
    _showProgressCheckState();
    _restoreEvolveRunState().finally(() => {
      _clearProgressCheckState();
      switchEvolveTab(evolveActiveTab);
      // Auto-load server-side cache for tabs missing from localStorage
      _loadServerCacheForMissingTabs();
      // Show interrupted banner if page was refreshed mid-analysis (Fix 3)
      _showInterruptedBanner();
    });
  };

  function _showProgressCheckState() {
    const body = $("#evolve-tab-body");
    if (!body || body.querySelector(".evolve-tab-panel")) return;
    body.innerHTML = `<div class="evolve-empty-state evolve-progress-check"><div class="evolve-empty-icon">⏳</div><p class="evolve-empty-title">${_tt("evolve.status.checking")}</p></div>`;
    const updatedEl = _getEvolveUpdatedEl();
    if (updatedEl) {
      updatedEl.textContent = _tt("evolve.status.checking");
      updatedEl.classList.add("loading");
    }
  }

  function _clearProgressCheckState() {
    const el = document.querySelector(".evolve-progress-check");
    if (el) el.remove();
  }

  function _currentScopeKey(tab, scope) {
    return getScopeCacheKey(tab, scope || getEvolveScope());
  }

  function _markTabLoading(tab, scope) {
    const scopeKey = _currentScopeKey(tab, scope);
    evolveLoadingTabs[tab] = true;
    evolveLoadingScopes[tab] = scopeKey;
    return scopeKey;
  }

  function _clearTabLoading(tab, scope) {
    const scopeKey = scope ? _currentScopeKey(tab, scope) : "";
    if (
      scope &&
      evolveLoadingScopes[tab] &&
      evolveLoadingScopes[tab] !== scopeKey
    ) {
      return;
    }
    delete evolveLoadingTabs[tab];
    delete evolveLoadingScopes[tab];
  }

  function _isTabLoadingForScope(tab, scope) {
    if (!evolveLoadingTabs[tab]) return false;
    const current = evolveLoadingScopes[tab];
    return !current || current === _currentScopeKey(tab, scope);
  }

  function _isTabBusy(tab, scope) {
    return (
      !!evolveStreamAborts[tab] ||
      !!evolveRecoveredRunPollers[tab] ||
      _isTabLoadingForScope(tab, scope)
    );
  }

  function _getProgressState(tab) {
    if (!evolveProgressState[tab]) {
      evolveProgressState[tab] = {
        runId: "",
        stepCount: 0,
        usageInput: 0,
        usageOutput: 0,
        starting: false,
        recovered: false,
      };
    }
    return evolveProgressState[tab];
  }

  function _resetProgressState(tab) {
    evolveProgressState[tab] = {
      runId: "",
      stepCount: 0,
      usageInput: 0,
      usageOutput: 0,
      starting: false,
      recovered: false,
    };
    return evolveProgressState[tab];
  }

  function _syncEvolveChrome(tab, scope) {
    const activeScope = getEvolveScope();
    const headerScope =
      tab &&
      scope &&
      tab === evolveActiveTab &&
      _currentScopeKey(tab, scope) ===
        _currentScopeKey(evolveActiveTab, activeScope)
        ? scope
        : activeScope;
    _updateEvolveHeader(evolveActiveTab, headerScope);
    _setEvolveRefreshButton();
    _updateTabStatusIndicators();
    updateEvolveOverviewBar();
    updateSyncButtonState();
  }

  function _updateEvolveHeader(tab, scope) {
    const targetTab = tab || evolveActiveTab;
    const updatedEl = _getEvolveUpdatedEl();
    if (!updatedEl) return;

    const requestScope = scope || getEvolveScope();
    const cached = getCachedTab(targetTab, requestScope);
    const state = _getProgressState(targetTab);
    const isLoading = _isTabBusy(targetTab, requestScope);

    if (isLoading) {
      if (state.usageInput || state.usageOutput) {
        updatedEl.textContent = _tt("evolve.status.aiRunningTokens", {
          in: state.usageInput || 0,
          out: state.usageOutput || 0,
        });
      } else if (state.stepCount) {
        updatedEl.textContent = _tt("evolve.status.aiRunningSteps", {
          n: state.stepCount,
        });
      } else if (state.starting) {
        updatedEl.textContent = _tt("evolve.status.aiStarting");
      } else {
        updatedEl.textContent = _tt("evolve.status.aiRunning");
      }
      updatedEl.classList.add("loading");
      return;
    }

    if (cached && cached.data && !cached.data._error) {
      updatedEl.textContent = _tt("evolve.updated", {
        time: timeAgo(cached.updatedAt),
      });
      updatedEl.classList.remove("loading");
      return;
    }
    if (cached && cached.data && cached.data._error === "no_cache") {
      updatedEl.textContent = _tt("evolve.status.never");
      updatedEl.classList.remove("loading");
      return;
    }
    if (cached && cached.data && cached.data._error) {
      updatedEl.textContent = _tt("evolve.error.analyzeFailed", {
        error: cached.data._error,
      });
      updatedEl.classList.remove("loading");
      return;
    }
    updatedEl.textContent = _tt("evolve.status.never");
    updatedEl.classList.remove("loading");
  }

  function _refreshRecoveredRun(tab, requestScope) {
    const scope = requestScope || getEvolveScope();
    const params = _progressParams(scope, tab);
    return fetch(`/api/evolve/progress?${params}`)
      .then((r) => r.json())
      .then((payload) => {
        if (!payload || !payload.ok) return null;
        _applyRecoveredRun(
          tab,
          payload.run,
          !!payload.running,
          scope,
          payload.cache,
          !!payload.stale,
        );
        return payload;
      })
      .catch(() => null);
  }

  function _progressSummaryHtml(tab, state, live) {
    const statusParts = [];
    if (state.stepCount) {
      statusParts.push(_tt("evolve.progress.steps", { n: state.stepCount }));
    }
    if (state.usageInput || state.usageOutput) {
      statusParts.push(
        _tt("evolve.progress.tokens", {
          in: state.usageInput || 0,
          out: state.usageOutput || 0,
        }),
      );
    }
    const note = state.recovered
      ? _tt("evolve.progress.recovered")
      : _tt("evolve.progress.live");
    let html = '<div class="evolve-progress-head">';
    if (state.runId) {
      html +=
        '<span class="evolve-progress-runid">' +
        esc(_tt("evolve.progress.runLabel", { id: state.runId })) +
        "</span>";
    }
    html +=
      '<span class="evolve-progress-note' +
      (state.recovered ? " recovered" : "") +
      '">' +
      esc(note) +
      "</span>" +
      "</div>";
    if (statusParts.length) {
      html +=
        '<div class="evolve-progress-stats">' +
        esc(statusParts.join(" · ")) +
        "</div>";
    }
    if (live) {
      html +=
        '<div class="evolve-progress-live">' +
        '<span class="evolve-thinking-dot"></span>' +
        '<span class="evolve-thinking-dot"></span>' +
        '<span class="evolve-thinking-dot"></span>' +
        '<span class="evolve-progress-live-label">' +
        esc(_tt("evolve.status.aiGenerating")) +
        "</span>" +
        "</div>";
    }
    return html;
  }

  function _updateProgressSummary(tab, state, live) {
    const container = document.getElementById(`evolve-stream-${tab}`);
    if (!container) return;
    const progressState = state || _getProgressState(tab);
    let summary = container.querySelector(".evolve-progress-summary");
    if (!summary) {
      summary = document.createElement("div");
      summary.className = "evolve-progress-summary";
      container.insertBefore(summary, container.firstChild);
    }
    summary.classList.toggle("is-live", !!live);
    summary.innerHTML = _progressSummaryHtml(tab, progressState, live);
  }

  function _isTransientEvolveError(error) {
    const text = String(error || "");
    return (
      text === "Network error" ||
      text === "Failed to fetch" ||
      text === "Analysis interrupted: no active backend process" ||
      text === "AI analysis timed out" ||
      text === _tt("evolve.error.timedOut") ||
      text.toLowerCase() === "timeout" ||
      text.startsWith("Timeout")
    );
  }

  function _clearCachedTabTransientError(tab, scope) {
    const targetScope = scope || getEvolveScope();
    const prefix = [
      tab,
      targetScope.source || "all",
      targetScope.date || "7d",
      targetScope.project || "",
    ].join("::");
    let changed = false;
    Object.keys(evolveCache).forEach((key) => {
      const entry = evolveCache[key];
      if (
        key.startsWith(prefix + "::") &&
        entry &&
        entry.data &&
        _isTransientEvolveError(entry.data._error)
      ) {
        delete evolveCache[key];
        changed = true;
      }
    });
    if (changed) saveEvolveCache();
    return changed;
  }

  /** Clear cached entries that have transient error states (not "no_cache") */
  function _clearStaleErrorCache() {
    const scope = getEvolveScope();
    // 逐 tab 匹配当前 source/date/project 下的所有 engine cache，
    // 清掉会遮挡后端保存内容的瞬时 error，
    // 这样切页/重进 #ai 不会再渲染上一轮 abort 留下的 "network error"。
    EVOLVE_TABS.forEach((tab) => {
      _clearCachedTabTransientError(tab, scope);
    });
  }

  /** Show a banner if analysis was interrupted by page refresh (Fix 3) */
  function _showInterruptedBanner() {
    const body = $("#evolve-tab-body");
    if (!body) return;
    if (window._evolveWasInterrupted) {
      const banner = document.createElement("div");
      banner.className = "evolve-refresh-all-banner";
      banner.innerHTML = `<span>⚠️ ${_tt("evolve.banner.interrupted")}</span>`;
      body.insertBefore(banner, body.firstChild);
      window._evolveWasInterrupted = false;
      // Auto-dismiss after 30 seconds
      setTimeout(() => {
        if (banner.parentNode) banner.remove();
      }, 30000);
    }
    // Also check server-side cache for partial data
    const scope = getEvolveScope();
    const params = new URLSearchParams({
      source: scope.source || "all",
      date: scope.date || "7d",
      project: scope.project || "",
      engine: scope.engine || "auto",
      lang: scope.lang || "zh",
    });
    EVOLVE_TABS.forEach((tab) => {
      if (_isTabBusy(tab, scope)) return;
      const cached = getCachedTab(tab, scope);
      if (cached && cached.data && !cached.data._error) return;
      fetch(`/api/evolve/${tab}?${params}`)
        .then((r) => r.json())
        .then((data) => {
          if (_isTabBusy(tab, scope)) return;
          if (hasRenderableData(tab, data)) {
            const normalized = normalizeEvolveData(tab, data);
            setCachedTab(tab, normalized, scope);
            if (isCurrentScopeKey(tab, scope)) {
              const panel = _ensureTabPanel(tab);
              _renderTabPanel(tab, panel);
            }
            _syncEvolveChrome(tab, scope);
          }
        })
        .catch(() => {});
    });
  }

  function bindEvolveEvents() {
    // Tab switching
    $$(".evolve-tab").forEach((tab) => {
      tab.onclick = () => switchEvolveTab(tab.dataset.tab);
    });

    // Per-tab refresh / stop
    const tabRefresh = $("#evolve-tab-refresh");
    if (tabRefresh)
      tabRefresh.onclick = () => {
        const activeScope = getEvolveScope();
        if (_isTabBusy(evolveActiveTab, activeScope)) {
          _stopEvolveTab(evolveActiveTab);
        } else {
          refreshEvolveTab(evolveActiveTab);
        }
      };

    // Refresh all
    const refreshAll = $("#evolve-refresh-all");
    if (refreshAll) refreshAll.onclick = () => refreshAllEvolveTabs();

    // Sync button
    const syncBtn = $("#evolve-tab-sync");
    if (syncBtn) syncBtn.onclick = () => toggleSyncPanel();
  }

  function switchEvolveTab(tab) {
    // Stop force simulation when switching away from a tab that uses one
    if (evolveActiveTab !== tab) {
      const oldPanel = document.querySelector(
        `.evolve-tab-panel[data-tab="${evolveActiveTab}"]`,
      );
      if (oldPanel && activeSimulation) {
        activeSimulation.on("tick", null);
        activeSimulation.on("end", null);
        activeSimulation.stop();
        activeSimulation = null;
      }
    }
    evolveActiveTab = tab;
    try {
      localStorage.setItem(EVOLVE_ACTIVE_TAB_KEY, tab);
    } catch (e) {}
    if (typeof window.setPersistedEvolveTab === "function") {
      try {
        window.setPersistedEvolveTab(tab);
      } catch (e) {}
    }
    $$(".evolve-tab").forEach((t) =>
      t.classList.toggle("active", t.dataset.tab === tab),
    );
    // Show/hide per-tab panels instead of re-rendering
    const activePanel = _ensureTabPanel(tab);
    const scope = getEvolveScope();
    if (
      activePanel &&
      activePanel.dataset.langRendered &&
      activePanel.dataset.langRendered !== _getLang() &&
      !_isTabBusy(tab, scope)
    ) {
      _renderTabPanel(tab, activePanel);
    }
    $$(".evolve-tab-panel").forEach((p) => {
      p.style.display = p.dataset.tab === tab ? "" : "none";
    });
    _syncEvolveChrome(tab);
  }

  /** Update per-tab status indicators (spinner/checkmark/error in tab buttons) */
  function _updateTabStatusIndicators() {
    const scope = getEvolveScope();
    EVOLVE_TABS.forEach((tab) => {
      const btn = document.querySelector(`.evolve-tab[data-tab="${tab}"]`);
      if (!btn) return;
      // Remove existing status indicator
      const existing = btn.querySelector(".evolve-tab-status");
      if (existing) existing.remove();
      // Add status indicator
      const status = document.createElement("span");
      status.className = "evolve-tab-status";
      if (_isTabBusy(tab, scope)) {
        status.textContent = "⏳";
        status.title = _getLang() === "en" ? "Loading..." : "加载中…";
        status.classList.add("loading");
      } else {
        const cached = getCachedTab(tab, scope);
        if (cached && cached.data && cached.data._error) {
          if (cached.data._error === "no_cache") {
            // "no_cache" is an empty state, not an error — no indicator
            // Fall through — status.textContent is empty, won't be appended
          } else {
            status.textContent = "⚠️";
            status.title = cached.data._error;
            status.classList.add("error");
          }
        } else if (cached) {
          status.textContent = "✓";
          status.title = _getLang() === "en" ? "Cached" : "已缓存";
          status.classList.add("cached");
        }
      }
      if (status.textContent) btn.appendChild(status);
    });
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
      panel.style.display = tab === evolveActiveTab ? "" : "none";
      body.appendChild(panel);
      // Render cached content or empty state
      _renderTabPanel(tab, panel);
    }
    return panel;
  }

  /** Render tab content into its dedicated panel */
  function _renderTabPanel(tab, panel) {
    if (!panel) return;
    panel.dataset.langRendered = _getLang();
    const scope = getEvolveScope();
    const cached = getCachedTab(tab, scope);
    if (cached && cached.data) {
      // Stop any existing simulation before re-rendering
      if (activeSimulation) {
        activeSimulation.on("tick", null);
        activeSimulation.on("end", null);
        activeSimulation.stop();
        activeSimulation = null;
      }
      panel.innerHTML = "";
      if (cached.data._error) {
        if (cached.data._error === "no_cache") {
          // "no_cache" is an empty state, not a failure — show a friendly hint
          panel.innerHTML = `<div class="evolve-empty-state"><div class="evolve-empty-icon">📊</div><p class="evolve-empty-title">${_tt("evolve.empty.initial")}</p><p class="evolve-empty-hint">${_tt("evolve.empty.refreshHint")}</p><button class="btn btn-primary btn-sm evolve-retry-btn" data-tab="${esc(tab)}">${esc(_tt("evolve.btn.startAnalysis"))}</button></div>`;
          _bindRetryButtons(panel);
          return;
        }
        // Real error — show error message with retry
        panel.innerHTML = `<div class="evolve-empty-state evolve-error-state"><div class="evolve-empty-icon evolve-error-icon">⚠️</div><p class="evolve-empty-title">${_tt("evolve.error.analyzeFailed", { error: (window.esc || String)(cached.data._error) })}</p><p class="evolve-empty-hint">${_tt("evolve.error.retryHint")}</p><button class="btn btn-primary btn-sm evolve-retry-btn" data-tab="${esc(tab)}">${esc(_tt("evolve.btn.retry"))}</button></div>`;
        _bindRetryButtons(panel);
        return;
      }
      renderTabVisualization(tab, cached.data, panel);
    } else if (!_isTabBusy(tab, scope)) {
      panel.innerHTML = `<div class="evolve-empty-state"><div class="evolve-empty-icon">📊</div><p class="evolve-empty-title">${_tt("evolve.empty.initial")}</p><p class="evolve-empty-hint">${_tt("evolve.empty.refreshHint")}</p><button class="btn btn-primary btn-sm evolve-retry-btn" data-tab="${esc(tab)}">${esc(_tt("evolve.btn.startAnalysis"))}</button></div>`;
      _bindRetryButtons(panel);
    }
  }

  /** Bind click handlers for retry buttons inside a panel */
  function _bindRetryButtons(panel) {
    if (!panel) return;
    panel.querySelectorAll(".evolve-retry-btn").forEach((btn) => {
      btn.onclick = () => refreshEvolveTab(btn.dataset.tab);
    });
  }

  // ── Cache ──
  function loadEvolveCache() {
    try {
      const raw = localStorage.getItem("chatview-evolve");
      if (raw) evolveCache = JSON.parse(raw);
    } catch (e) {
      evolveCache = {};
    }
    _migrateLegacyLangScopedCache();
  }

  function saveEvolveCache() {
    try {
      localStorage.setItem("chatview-evolve", JSON.stringify(evolveCache));
    } catch (e) {
      if (e.name === "QuotaExceededError" || (e.code && e.code === 22)) {
        if (!window._evolveQuotaWarned) {
          window._evolveQuotaWarned = true;
          const t = document.createElement("div");
          t.style.cssText =
            "position:fixed;bottom:20px;right:20px;background:#e65100;color:#fff;padding:12px 20px;border-radius:8px;z-index:9999;font-size:13px;box-shadow:0 4px 12px rgba(0,0,0,.3);max-width:320px";
          t.textContent = _tt("evolve.quotaWarning");
          document.body.appendChild(t);
          setTimeout(() => t.remove(), 8000);
        }
      }
    }
  }

  function getLegacyScopeCacheKey(tab, scope) {
    const s = scope || getEvolveScope();
    return [
      tab,
      s.source || "all",
      s.date || "7d",
      s.project || "",
      s.engine || "auto",
      s.lang || evolveScopeLang || "zh",
    ].join("::");
  }

  function getScopeCacheKey(tab, scope) {
    const s = scope || getEvolveScope();
    return [
      tab,
      s.source || "all",
      s.date || "7d",
      s.project || "",
      s.engine || "auto",
    ].join("::");
  }

  function _migrateLegacyLangScopedCache() {
    let changed = false;
    Object.entries(evolveCache).forEach(([key, entry]) => {
      if (!key || key.split("::").length < 6) return;
      const tab = key.split("::")[0];
      const scope = entry && entry.scope ? entry.scope : {};
      const normalizedKey = getScopeCacheKey(tab, {
        source: scope.source,
        date: scope.date,
        project: scope.project,
        engine: scope.engine,
      });
      const current = evolveCache[normalizedKey];
      const currentTs = new Date(current?.updatedAt || 0).getTime();
      const entryTs = new Date(entry?.updatedAt || 0).getTime();
      if (!current || entryTs >= currentTs) {
        evolveCache[normalizedKey] = entry;
      }
      delete evolveCache[key];
      changed = true;
    });
    if (changed) saveEvolveCache();
  }

  function getExactCachedTab(tab, scope) {
    const targetScope = scope || getEvolveScope();
    const exactKey = getScopeCacheKey(tab, targetScope);
    if (evolveCache[exactKey]) return evolveCache[exactKey];
    const legacyKey = getLegacyScopeCacheKey(tab, targetScope);
    if (evolveCache[legacyKey]) {
      evolveCache[exactKey] = evolveCache[legacyKey];
      delete evolveCache[legacyKey];
      saveEvolveCache();
      return evolveCache[exactKey];
    }
    return null;
  }

  function getBestCachedTab(tab, scope) {
    const targetScope = scope || getEvolveScope();
    const exact = getExactCachedTab(tab, targetScope);
    if (exact) return exact;
    const prefix = [
      tab,
      targetScope.source || "all",
      targetScope.date || "7d",
      targetScope.project || "",
    ].join("::");
    const matches = Object.entries(evolveCache)
      .filter(([key]) => key.startsWith(prefix + "::"))
      .sort((a, b) => {
        const aTime = new Date(a[1]?.updatedAt || 0).getTime();
        const bTime = new Date(b[1]?.updatedAt || 0).getTime();
        return bTime - aTime;
      });
    if (!matches.length) return null;
    return Object.assign({ stale: true }, matches[0][1]);
  }

  function getCachedTab(tab, scope) {
    return getExactCachedTab(tab, scope);
  }

  function setCachedTab(tab, data, scope) {
    const writeScope = scope || getEvolveScope();
    evolveCache[getScopeCacheKey(tab, writeScope)] = {
      updatedAt: new Date().toISOString(),
      scope: writeScope,
      data,
    };
    saveEvolveCache();
    updateSyncButtonState();
  }

  function isCurrentScopeKey(tab, scopeOrKey) {
    const key =
      typeof scopeOrKey === "string"
        ? scopeOrKey
        : getScopeCacheKey(tab, scopeOrKey);
    return key === getScopeCacheKey(tab, getEvolveScope());
  }

  // ── Scope (reads from shared global state set by initAiPage in app.js) ──
  function getEvolveScope() {
    if (
      typeof window.getEvolveScope === "function" &&
      window.getEvolveScope !== getEvolveScope
    ) {
      const scope = window.getEvolveScope() || {};
      return {
        source: scope.source || "all",
        date: scope.date || "7d",
        project: scope.project || "",
        engine: scope.engine || "auto",
        lang: scope.lang || "zh",
        timeout: scope.timeout || 900,
      };
    }
    return {
      source: evolveScopeSource,
      date: evolveScopeDate,
      project: evolveScopeProject,
      engine: evolveScopeEngine,
      lang: evolveScopeLang,
      timeout: 900,
    };
  }

  // ── Overview bar ──
  function updateEvolveOverviewBar() {
    const bar = $("#evolve-overview-bar");
    if (!bar) return;
    const scope = getEvolveScope();
    const icons = {
      profile: "🧬",
      memory: "🧠",
      rules: "📐",
      signals: "⚡",
      patterns: "🔄",
    };
    bar.innerHTML = "";
    EVOLVE_TABS.forEach((tab) => {
      const cached = getCachedTab(tab, scope);
      const count = cached ? getTabItemCount(tab, cached.data) : 0;
      const div = document.createElement("div");
      div.className = `evolve-stat-card${tab === evolveActiveTab ? " active" : ""}`;
      div.innerHTML = `<span class="evolve-stat-icon">${icons[tab]}</span><span class="evolve-stat-count">${count}</span><span class="evolve-stat-label">${_tt("evolve.tab." + tab)}</span>`;
      div.onclick = () => switchEvolveTab(tab);
      bar.appendChild(div);
    });
    // Last scan info
    const anyUpdated = EVOLVE_TABS.map((t) => getCachedTab(t, scope)?.updatedAt)
      .filter(Boolean)
      .sort()
      .pop();
    if (anyUpdated) {
      const span = document.createElement("span");
      span.className = "evolve-last-scan";
      span.textContent = _tt("evolve.overview.lastScan", {
        time: timeAgo(anyUpdated),
      });
      bar.appendChild(span);
    }
  }

  function getTabItemCount(tab, data) {
    if (!data) return 0;
    switch (tab) {
      case "profile":
        return (
          (data.categories?.length || 0) + (data.radar?.dimensions?.length || 0)
        );
      case "memory":
        return (data.cards?.length || 0) + (data.nodes?.length || 0);
      case "rules":
        return data.rules?.length || 0;
      case "signals":
        return data.events?.length || 0;
      case "patterns":
        return (data.bubbles?.length || 0) + (data.cards?.length || 0);
      default:
        return 0;
    }
  }

  function hasRenderableData(tab, data) {
    if (!data || data._error) return false;
    switch (tab) {
      case "profile":
        return !!(data.categories?.length || data.radar?.dimensions?.length);
      case "memory":
        return !!(
          data.cards?.length ||
          data.nodes?.length ||
          data.links?.length
        );
      case "rules":
        return !!data.rules?.length;
      case "signals":
        return !!(data.timeline?.length || data.events?.length);
      case "patterns":
        return !!(data.cards?.length || data.bubbles?.length);
      default:
        return false;
    }
  }

  function timeAgo(iso) {
    const diff = Date.now() - new Date(iso).getTime();
    if (diff < 60000) return _tt("evolve.time.justNow");
    if (diff < 3600000)
      return _tt("evolve.time.mAgo", { n: Math.floor(diff / 60000) });
    if (diff < 86400000)
      return _tt("evolve.time.hAgo", { n: Math.floor(diff / 3600000) });
    return _tt("evolve.time.dAgo", { n: Math.floor(diff / 86400000) });
  }

  // ── Tab content rendering (legacy compat — routes to per-tab panel) ──
  function renderEvolveTabContent(tab) {
    const panel = _ensureTabPanel(tab);
    _renderTabPanel(tab, panel);
    _updateEvolveHeader(tab);
  }

  function renderTabVisualization(tab, data, container) {
    switch (tab) {
      case "profile":
        renderProfileTab(data, container);
        break;
      case "memory":
        renderMemoryTab(data, container);
        break;
      case "rules":
        renderRulesTab(data, container);
        break;
      case "signals":
        renderSignalsTab(data, container);
        break;
      case "patterns":
        renderPatternsTab(data, container);
        break;
    }
  }

  // ── Auto-load server cache on init ──
  function _loadServerCacheForMissingTabs() {
    const scope = getEvolveScope();
    const params = new URLSearchParams({
      source: scope.source || "all",
      date: scope.date || "7d",
      project: scope.project || "",
      engine: scope.engine || "auto",
      lang: scope.lang || "zh",
    });
    EVOLVE_TABS.forEach((tab) => {
      if (_isTabBusy(tab, scope)) return;
      const cached = getCachedTab(tab, scope);
      if (cached && cached.data && !cached.data._error) return; // already in localStorage
      fetch(`/api/evolve/${tab}?${params}`)
        .then((r) => r.json())
        .then((data) => {
          if (_isTabBusy(tab, scope)) return;
          // "no_cache" just means never analyzed yet — not a failure.
          // Leave the tab in its empty/"Analyze" state instead of showing an error.
          if (data && data._error && data._error !== "no_cache") {
            // Cache error data so it shows on next render
            setCachedTab(tab, data, scope);
            if (isCurrentScopeKey(tab, scope)) {
              const panel = _ensureTabPanel(tab);
              _renderTabPanel(tab, panel);
            }
            _syncEvolveChrome(tab, scope);
            return;
          }
          if (data && data._error === "no_cache") return;
          if (hasRenderableData(tab, data)) {
            const normalized = normalizeEvolveData(tab, data);
            setCachedTab(tab, normalized, scope);
            if (isCurrentScopeKey(tab, scope)) {
              const panel = _ensureTabPanel(tab);
              _renderTabPanel(tab, panel);
            }
            _syncEvolveChrome(tab, scope);
          }
        })
        .catch(() => {}); // silent — server cache is optional
    });
  }

  function _progressParams(scope, tab) {
    const params = new URLSearchParams({
      source: scope.source || "all",
      date: scope.date || "7d",
      project: scope.project || "",
      engine: scope.engine || "auto",
    });
    if (tab) params.set("tab", tab);
    return params;
  }

  function _stopRecoveredRunPoll(tab) {
    const poller = evolveRecoveredRunPollers[tab];
    if (poller && poller.timer) clearTimeout(poller.timer);
    delete evolveRecoveredRunPollers[tab];
    _syncRecoveredRunFlag();
  }

  function _syncRecoveredRunFlag() {
    try {
      if (
        Object.keys(evolveStreamAborts).length > 0 ||
        Object.keys(evolveRecoveredRunPollers).length > 0
      ) {
        localStorage.setItem("evolve-mid-analysis", "1");
      } else {
        localStorage.removeItem("evolve-mid-analysis");
      }
    } catch (e) {}
  }

  function _scheduleRecoveredRunPoll(tab, requestScope) {
    const scope = requestScope || getEvolveScope();
    const scopeKey = getScopeCacheKey(tab, scope);
    const existing = evolveRecoveredRunPollers[tab];
    if (existing && existing.scopeKey === scopeKey) return;

    _stopRecoveredRunPoll(tab);
    const poller = { timer: null, scopeKey };
    evolveRecoveredRunPollers[tab] = poller;
    _syncRecoveredRunFlag();

    const poll = () => {
      if (evolveRecoveredRunPollers[tab] !== poller) return;
      const params = _progressParams(scope, tab);
      fetch(`/api/evolve/progress?${params}`)
        .then((r) => r.json())
        .then((payload) => {
          if (evolveRecoveredRunPollers[tab] !== poller) return;
          if (!payload || !payload.ok || (!payload.run && !payload.cache)) {
            _stopRecoveredRunPoll(tab);
            _clearTabLoading(tab, scope);
            _syncEvolveChrome(tab, scope);
            return;
          }
          _applyRecoveredRun(
            tab,
            payload.run,
            !!payload.running,
            scope,
            payload.cache,
            !!payload.stale,
          );
          if (payload.running) {
            poller.timer = setTimeout(poll, 2000);
          } else {
            _stopRecoveredRunPoll(tab);
          }
        })
        .catch(() => {
          if (evolveRecoveredRunPollers[tab] !== poller) return;
          poller.timer = setTimeout(poll, 2000);
        });
    };

    poll();
  }

  function _restoreEvolveRunState() {
    const scope = getEvolveScope();
    const params = _progressParams(scope);
    return fetch(`/api/evolve/progress?${params}`)
      .then((r) => r.json())
      .then((payload) => {
        if (!payload || !payload.ok || !payload.tabs) return;
        Object.entries(payload.tabs).forEach(([tab, info]) => {
          if (!info || (!info.run && !info.cache)) return;
          _applyRecoveredRun(
            tab,
            info.run,
            !!info.running,
            scope,
            info.cache,
            !!info.stale,
          );
        });
      })
      .catch(() => {});
  }

  function _applyRecoveredRun(tab, run, running, scope, cache, stale) {
    const snapshot = (run && run.snapshot) || {};
    const result = snapshot.result;
    const requestScope = scope || getEvolveScope();
    const progressState = _getProgressState(tab);
    progressState.runId = (run && run.run_id) || progressState.runId || "";
    progressState.stepCount = snapshot.step_count || 0;
    progressState.usageInput = snapshot.usage?.input || 0;
    progressState.usageOutput = snapshot.usage?.output || 0;
    progressState.starting = !progressState.stepCount;
    progressState.recovered = !!running;
    if (run && run.run_id) {
      try {
        localStorage.setItem(`${EVOLVE_ACTIVE_RUN_KEY}::${tab}`, run.run_id);
      } catch (e) {}
    }
    if (result && !result._error) {
      const normalized = normalizeEvolveData(tab, result);
      setCachedTab(tab, normalized, requestScope);
      _clearTabLoading(tab, requestScope);
    } else if (!running && cache && cache.data && !cache.data._error) {
      const normalized = normalizeEvolveData(tab, cache.data);
      setCachedTab(tab, normalized, requestScope);
      _clearTabLoading(tab, requestScope);
    } else if (!running && run && run.status === "failed") {
      setCachedTab(
        tab,
        {
          _error:
            run.error_message ||
            _tt("evolve.error.analyzeFailed", { error: "unknown" }),
        },
        requestScope,
      );
      _clearTabLoading(tab, requestScope);
    } else if (!running && run && run.status === "cancelled") {
      setCachedTab(tab, { _error: "Cancelled by user" }, requestScope);
      _clearTabLoading(tab, requestScope);
    } else if (!running && (stale || (run && run.status === "running"))) {
      _clearTabLoading(tab, requestScope);
    }

    if (running) {
      _clearCachedTabTransientError(tab, requestScope);
      _markTabLoading(tab, requestScope);
      _scheduleRecoveredRunPoll(tab, requestScope);
      const panel = _ensureTabPanel(tab);
      _renderRecoveredProgress(tab, panel, snapshot);
      _syncEvolveChrome(tab, requestScope);
    } else if (tab === evolveActiveTab) {
      _stopRecoveredRunPoll(tab);
      try {
        localStorage.removeItem(`${EVOLVE_ACTIVE_RUN_KEY}::${tab}`);
      } catch (e) {}
      progressState.recovered = false;
      progressState.starting = false;
      const panel = _ensureTabPanel(tab);
      _renderTabPanel(tab, panel);
      _syncEvolveChrome(tab, requestScope);
    } else if (!running) {
      _stopRecoveredRunPoll(tab);
      try {
        localStorage.removeItem(`${EVOLVE_ACTIVE_RUN_KEY}::${tab}`);
      } catch (e) {}
      progressState.recovered = false;
      progressState.starting = false;
      _syncEvolveChrome(tab, requestScope);
    }
  }

  function _renderRecoveredProgress(tab, panel, snapshot) {
    if (!panel) return;
    const esc = window.esc || String;
    const state = _getProgressState(tab);
    state.stepCount = snapshot.step_count || 0;
    state.usageInput = snapshot.usage?.input || 0;
    state.usageOutput = snapshot.usage?.output || 0;
    state.starting = !state.stepCount;
    state.recovered = true;
    const text = snapshot.text || "";
    panel.innerHTML = `<div class="evolve-stream-progress evolve-recovered-progress" id="evolve-stream-${tab}">
    </div>`;
    const container = panel.querySelector(`#evolve-stream-${tab}`);
    if (!container) return;
    _updateProgressSummary(tab, state, true);
    if (Array.isArray(snapshot.events)) {
      const runningCards = [];
      snapshot.events.forEach((evt) => {
        if (evt.type === "tool" && evt.status === "running") {
          const group = _createToolGroup(container);
          const body = group.querySelector(".evolve-tg-body");
          const card = document.createElement("div");
          card.className = "tool-card running expanded";
          card.innerHTML = `<div class="tool-card-header"><span class="tool-status-dot"></span><span class="tool-card-name">${esc(evt.name || "Tool")}</span><span class="tool-card-detail">${esc(evt.detail || "")}</span><span class="tool-card-chevron">›</span></div><div class="tool-card-body"><div class="tool-card-cmd">${esc(evt.prompt || evt.detail || "")}</div><pre class="tool-card-output"></pre></div>`;
          body.appendChild(card);
          runningCards.push({ card, group });
        } else if (
          evt.type === "tool" &&
          evt.status === "done" &&
          runningCards.length
        ) {
          const item = runningCards.shift();
          item.card.classList.remove("running");
          item.card.classList.add("done");
          const outputEl = item.card.querySelector(".tool-card-output");
          if (outputEl) outputEl.textContent = evt.detail || "";
          const header = item.card.querySelector(".tool-card-header");
          if (header)
            header.onclick = () => item.card.classList.toggle("expanded");
          item.group.classList.remove("running");
          item.group.classList.add("done");
        }
      });
    }
    if (text) {
      const block = document.createElement("div");
      block.className = "text-block";
      block.innerHTML = window.renderMarkdownSimple
        ? window.renderMarkdownSimple(text)
        : `<pre>${esc(text)}</pre>`;
      container.appendChild(block);
    }
  }

  // ── API call for analysis (unified: all tabs go through /api/evolve/{tab}) ──
  // AI tabs (profile, memory) may take longer since they run Codex on the backend
  function _fetchEvolveTab(tab) {
    const scope = getEvolveScope();
    const params = new URLSearchParams({
      refresh: "1",
      source: scope.source || "all",
      date: scope.date || "7d",
      project: scope.project || "",
      engine: scope.engine || "auto",
      lang: scope.lang || "zh",
      timeout: String(scope.timeout || 900),
    });

    // AI tabs use SSE streaming for real-time progress
    if (AI_TABS.has(tab)) {
      params.set("stream", "1");
      return _fetchEvolveTabStream(tab, params, scope);
    }

    return fetch(`/api/evolve/${tab}?${params}`)
      .then((r) => {
        if (!r.ok) throw new Error("Server error: " + r.status);
        return r.json();
      })
      .then((data) => {
        // "no_cache" is not a failure — leave the empty/"Analyze" state.
        if (data._error && data._error !== "no_cache") {
          // Cache the error data so it shows on next render
          setCachedTab(tab, data, scope);
          if (isCurrentScopeKey(tab, scope)) {
            const panel = _ensureTabPanel(tab);
            _renderTabPanel(tab, panel);
            updateEvolveOverviewBar();
          }
          return;
        }
        if (data._error === "no_cache") return;
        const normalized = normalizeEvolveData(tab, data);
        setCachedTab(tab, normalized, scope);
        // Re-render this tab's panel
        if (isCurrentScopeKey(tab, scope)) {
          const panel = _ensureTabPanel(tab);
          _renderTabPanel(tab, panel);
          updateEvolveOverviewBar();
        }
      });
  }

  /** Stream SSE events for AI evolve tabs with live progress */
  function _fetchEvolveTabStream(tab, params, scope) {
    const esc = window.esc || String;
    const requestScope = scope || getEvolveScope();
    const requestCacheKey = getScopeCacheKey(tab, requestScope);
    _stopRecoveredRunPoll(tab);
    const progressState = _resetProgressState(tab);
    progressState.starting = true;
    progressState.recovered = false;

    // Ensure tab panel exists and set up streaming container inside it
    const panel = _ensureTabPanel(tab);
    if (panel) {
      panel.innerHTML = `<div class="evolve-stream-progress" id="evolve-stream-${tab}"><div class="evolve-thinking"><span class="evolve-thinking-dot"></span><span class="evolve-thinking-dot"></span><span class="evolve-thinking-dot"></span><span class="evolve-thinking-label">${esc(_tt("evolve.status.aiStarting"))}</span></div></div>`;
      _updateProgressSummary(tab, progressState, true);
    }
    _syncEvolveChrome(tab, requestScope);

    const streamState = {
      blockText: "",
      textBlock: null,
      runningCards: [],
      stepCount: 0,
      currentToolGroup: null,
      toolGroupCounts: {},
      toolGroupRunning: 0,
      toolGroupTotal: 0,
      toolGroupCollapseTimer: null,
      requestScope,
      requestCacheKey,
      runId: "",
      progressState,
    };

    // Create abort controller for this tab's stream
    if (evolveStreamAborts[tab]) evolveStreamAborts[tab].abort();
    const abortCtrl = new AbortController();
    abortCtrl.detachOnly = false;
    abortCtrl.keepRecoveredPollers = false;
    abortCtrl.requestScope = requestScope;
    evolveStreamAborts[tab] = abortCtrl;
    _markTabLoading(tab, requestScope);
    // Track that a stream is in progress (for page-refresh recovery)
    try {
      localStorage.setItem("evolve-mid-analysis", "1");
    } catch (e) {}
    _syncEvolveChrome(tab, requestScope);

    return fetch(`/api/evolve/${tab}?${params}`, { signal: abortCtrl.signal })
      .then((response) =>
        window.readSseStream(response, (evt) =>
          _handleEvolveStreamEvent(evt, tab, streamState),
        ),
      )
      .catch((err) => {
        // 切页 / 切 scope / 停止分析都会 abort 这个 fetch。abort 触发的 reject
        // 不是真实网络错误，必须在这里吞掉，否则会冒泡到 refreshEvolveTab.catch
        // 被持久化成 { _error: "Network error" }，导致切页后误报。
        if (abortCtrl.signal.aborted || (err && err.name === "AbortError"))
          return;
        throw err; // 真实错误（如 !response.ok）继续上抛由调用方处理
      })
      .finally(() => {
        if (evolveStreamAborts[tab] === abortCtrl)
          delete evolveStreamAborts[tab];
        if (abortCtrl.detachOnly && abortCtrl.keepRecoveredPollers) {
          _scheduleRecoveredRunPoll(tab, requestScope);
        }
        _syncEvolveChrome(tab, requestScope);
        // Clear the mid-analysis flag if no other streams are active
        if (Object.keys(evolveStreamAborts).length === 0) {
          _syncRecoveredRunFlag();
        }
      });
  }

  function _setEvolveRefreshButton() {
    const btn = $("#evolve-tab-refresh");
    if (!btn) return;
    const scope = getEvolveScope();
    const streaming = _isTabBusy(evolveActiveTab, scope);
    if (streaming) {
      btn.textContent = _tt("evolve.btn.stop");
      btn.classList.add("btn-stop");
    } else {
      btn.textContent = _tt("evolve.btn.refresh");
      btn.classList.remove("btn-stop");
    }
  }

  async function _stopEvolveTab(tab) {
    _stopRecoveredRunPoll(tab);
    const scope = getEvolveScope();
    let cancelled = false;
    try {
      const resp = await fetch("/api/evolve/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tab,
          scope: {
            source: scope.source || "all",
            date: scope.date || "7d",
            project: scope.project || "",
            engine: scope.engine || "auto",
          },
        }),
      });
      const data = await resp.json();
      cancelled = !!(data && data.ok);
    } catch (e) {}
    if (!cancelled && !evolveStreamAborts[tab]) {
      await _refreshRecoveredRun(tab, scope);
      _syncEvolveChrome(tab, scope);
      return;
    }
    if (evolveStreamAborts[tab]) {
      evolveStreamAborts[tab].abort();
      delete evolveStreamAborts[tab];
    }
    _clearTabLoading(tab, scope);
    _resetProgressState(tab);
    try {
      localStorage.removeItem(`${EVOLVE_ACTIVE_RUN_KEY}::${tab}`);
    } catch (e) {}
    const updatedEl = _getEvolveUpdatedEl();
    if (updatedEl) {
      updatedEl.textContent = _tt("evolve.status.stopped");
      updatedEl.classList.remove("loading");
    }
    setCachedTab(tab, { _error: "Cancelled by user" }, scope);
    const panel = _ensureTabPanel(tab);
    _renderTabPanel(tab, panel);
    _syncEvolveChrome(tab, scope);
  }

  /** Show a "thinking" indicator below the last text block */
  function _evolveShowThinking(container, state) {
    _evolveHideThinking(container);
    const el = document.createElement("div");
    el.className = "evolve-thinking";
    el.innerHTML = `<span class="evolve-thinking-dot"></span><span class="evolve-thinking-dot"></span><span class="evolve-thinking-dot"></span><span class="evolve-thinking-label">${(window.esc || String)(_tt("evolve.status.aiGenerating"))}</span>`;
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
    if (
      scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight <
      80
    ) {
      scrollEl.scrollTop = scrollEl.scrollHeight;
    }
  }

  /** Create a new tool-group container */
  function _createToolGroup(parentContainer) {
    const group = document.createElement("div");
    group.className = "evolve-tool-group expanded running";
    group.innerHTML = `<div class="evolve-tg-header"><span class="evolve-tg-dot"></span><span class="evolve-tg-summary"></span><span class="evolve-tg-chevron">›</span></div><div class="evolve-tg-body"></div>`;
    group.querySelector(".evolve-tg-header").onclick = () =>
      group.classList.toggle("expanded");
    parentContainer.appendChild(group);
    return group;
  }

  /** Update tool-group header summary text */
  function _updateToolGroupHeader(state) {
    const group = state.currentToolGroup;
    if (!group) return;
    const el = group.querySelector(".evolve-tg-summary");
    if (!el) return;
    const parts = Object.entries(state.toolGroupCounts).map(
      ([name, count]) => `${count} ${name}`,
    );
    el.innerHTML = `<span class="evolve-tg-count">${_tt("evolve.tools.groupHeader", { n: state.toolGroupTotal })}</span> · ${parts.join(" · ")}`;
  }

  /** Close (collapse) the current tool group */
  function _finalizeToolGroup(state) {
    if (state.toolGroupCollapseTimer) {
      clearTimeout(state.toolGroupCollapseTimer);
      state.toolGroupCollapseTimer = null;
    }
    if (state.currentToolGroup) {
      _updateToolGroupHeader(state);
      state.currentToolGroup.classList.remove("expanded", "running");
      state.currentToolGroup.classList.add("done");
      state.currentToolGroup = null;
    }
  }

  function _handleEvolveStreamEvent(evt, tab, state) {
    const streamState = state;
    const container = document.getElementById(`evolve-stream-${tab}`);
    const esc = window.esc || String;
    const needsContainer =
      evt.type === "tool" || evt.type === "text" || evt.type === "result";
    if (!container && needsContainer) return;
    // Only update the header text and auto-scroll if this tab is currently visible
    const isActiveTab = tab === evolveActiveTab;
    const progressState = streamState.progressState || _getProgressState(tab);

    switch (evt.type) {
      case "run":
        streamState.runId = evt.run_id || "";
        progressState.runId = streamState.runId;
        if (streamState.runId) {
          try {
            localStorage.setItem(
              `${EVOLVE_ACTIVE_RUN_KEY}::${tab}`,
              streamState.runId,
            );
          } catch (e) {}
        }
        break;
      case "tool": {
        if (evt.status === "running") {
          state.textBlock = null;
          state.blockText = "";
          progressState.starting = false;
          progressState.recovered = false;
          _evolveHideThinking(container);
          if (state.toolGroupCollapseTimer) {
            clearTimeout(state.toolGroupCollapseTimer);
            state.toolGroupCollapseTimer = null;
          }
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
          state.currentToolGroup
            .querySelector(".evolve-tg-body")
            .appendChild(card);
          state.runningCards.push(card);
          state.stepCount++;
          progressState.stepCount = state.stepCount;
          state.toolGroupTotal++;
          state.toolGroupRunning++;
          const toolName = evt.name || "Tool";
          state.toolGroupCounts[toolName] =
            (state.toolGroupCounts[toolName] || 0) + 1;
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
          const cardName =
            card.querySelector(".tool-card-name")?.textContent || "";
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
        _updateProgressSummary(tab, progressState, true);
        _syncEvolveChrome(tab, streamState.requestScope);
        if (isActiveTab) _evolveAutoScroll();
        break;
      }
      case "text":
        _finalizeToolGroup(state);
        progressState.starting = false;
        state.blockText += evt.content;
        if (!state.textBlock) {
          state.textBlock = document.createElement("div");
          state.textBlock.className = "text-block";
          container.appendChild(state.textBlock);
        }
        state.textBlock.innerHTML = window.renderMarkdownSimple
          ? window.renderMarkdownSimple(state.blockText)
          : `<pre>${esc(state.blockText)}</pre>`;
        _updateProgressSummary(tab, progressState, true);
        // Show a thinking indicator after text — tool generation can take 60s+
        _evolveShowThinking(container, state);
        if (isActiveTab) _evolveAutoScroll();
        break;
      case "result":
        _finalizeToolGroup(state);
        progressState.starting = false;
        _evolveHideThinking(container);
        state.blockText = evt.content;
        if (!state.textBlock) {
          state.textBlock = document.createElement("div");
          state.textBlock.className = "text-block";
          container.appendChild(state.textBlock);
        }
        state.textBlock.innerHTML = window.renderMarkdownSimple
          ? window.renderMarkdownSimple(evt.content)
          : `<pre>${esc(evt.content)}</pre>`;
        _updateProgressSummary(tab, progressState, true);
        if (isActiveTab) _evolveAutoScroll();
        break;
      case "evolve_result": {
        _finalizeToolGroup(state);
        _stopRecoveredRunPoll(tab);
        _clearTabLoading(tab, streamState.requestScope);
        progressState.recovered = false;
        progressState.starting = false;
        const normalized = normalizeEvolveData(tab, evt.data);
        setCachedTab(tab, normalized, streamState.requestScope);
        if (streamState.runId) {
          try {
            localStorage.removeItem(`${EVOLVE_ACTIVE_RUN_KEY}::${tab}`);
          } catch (e) {}
        }
        // Re-render this tab's panel with the final visualization
        if (isCurrentScopeKey(tab, streamState.requestCacheKey)) {
          const panel = _ensureTabPanel(tab);
          _renderTabPanel(tab, panel);
        }
        _syncEvolveChrome(tab, streamState.requestScope);
        // Browser notification
        if (typeof window.sendBrowserNotification === "function") {
          window.sendBrowserNotification(
            _tt("notify.evolveDone"),
            _tt("notify.analysisDone", { label: tab }),
          );
        }
        break;
      }
      case "done":
        _finalizeToolGroup(state);
        _evolveHideThinking(container);
        _stopRecoveredRunPoll(tab);
        _clearTabLoading(tab, streamState.requestScope);
        progressState.recovered = false;
        progressState.starting = false;
        if (streamState.runId) {
          try {
            localStorage.removeItem(`${EVOLVE_ACTIVE_RUN_KEY}::${tab}`);
          } catch (e) {}
        }
        _syncEvolveChrome(tab, streamState.requestScope);
        // Browser notification
        if (typeof window.sendBrowserNotification === "function") {
          window.sendBrowserNotification(
            _tt("notify.evolveDone"),
            _tt("notify.analysisDone", { label: tab }),
          );
        }
        break;
      case "usage":
        // Token usage stats from the engine (codex turn.completed). Surface
        // progress so the user knows the AI is actually consuming tokens.
        if (
          typeof evt.input_tokens === "number" ||
          typeof evt.output_tokens === "number"
        ) {
          progressState.usageInput =
            (progressState.usageInput || 0) + (evt.input_tokens || 0);
          progressState.usageOutput =
            (progressState.usageOutput || 0) + (evt.output_tokens || 0);
          _updateProgressSummary(tab, progressState, true);
          _syncEvolveChrome(tab, streamState.requestScope);
        }
        break;
      case "timeout": {
        _finalizeToolGroup(state);
        _evolveHideThinking(container);
        _stopRecoveredRunPoll(tab);
        _clearTabLoading(tab, streamState.requestScope);
        progressState.recovered = false;
        progressState.starting = false;
        const tmsg = evt.message || _tt("evolve.error.timedOut");
        // Persist failure so it survives re-render (don't silently reset to "never").
        setCachedTab(tab, { _error: tmsg }, streamState.requestScope);
        if (isCurrentScopeKey(tab, streamState.requestCacheKey)) {
          const panelT = _ensureTabPanel(tab);
          _renderTabPanel(tab, panelT);
        }
        _syncEvolveChrome(tab, streamState.requestScope);
        if (streamState.runId) {
          try {
            localStorage.removeItem(`${EVOLVE_ACTIVE_RUN_KEY}::${tab}`);
          } catch (e) {}
        }
        if (window.showToast)
          window.showToast.error(
            _tt("evolve.error.analyzeFailed", { error: tmsg }),
            0,
            {
              label: _tt("evolve.btn.retry"),
              callback: () => refreshEvolveTab(tab),
            },
          );
        break;
      }
      case "error": {
        _finalizeToolGroup(state);
        _evolveHideThinking(container);
        _stopRecoveredRunPoll(tab);
        _clearTabLoading(tab, streamState.requestScope);
        progressState.recovered = false;
        progressState.starting = false;
        const emsg = evt.message || "Unknown error";
        // Persist failure so it survives re-render (don't silently reset to "never").
        setCachedTab(tab, { _error: emsg }, streamState.requestScope);
        if (streamState.runId) {
          try {
            localStorage.removeItem(`${EVOLVE_ACTIVE_RUN_KEY}::${tab}`);
          } catch (e) {}
        }
        // Re-render the panel so the error + retry button are shown (instead of raw text dump).
        if (isCurrentScopeKey(tab, streamState.requestCacheKey)) {
          const panel2 = _ensureTabPanel(tab);
          _renderTabPanel(tab, panel2);
        }
        _syncEvolveChrome(tab, streamState.requestScope);
        if (window.showToast)
          window.showToast.error(
            _tt("evolve.error.analyzeFailed", { error: emsg }),
            0,
            {
              label: _tt("evolve.btn.retry"),
              callback: () => refreshEvolveTab(tab),
            },
          );
        break;
      }
    }
  }

  function refreshEvolveTab(tab) {
    const requestScope = getEvolveScope();
    if (_isTabBusy(tab, requestScope)) return; // only block same tab, not others
    delete evolveDetachedTabs[tab];
    _clearCachedTabTransientError(tab, requestScope);
    _markTabLoading(tab, requestScope);
    const progressState = _resetProgressState(tab);
    progressState.starting = AI_TABS.has(tab);
    const isAI = AI_TABS.has(tab);
    const panel = _ensureTabPanel(tab);

    if (!isAI && panel) {
      panel.innerHTML = `<div class="evolve-skeleton"><div class="skeleton-bar"></div><div class="skeleton-bar short"></div><div class="skeleton-bar"></div><div class="skeleton-circle"></div></div>`;
      _syncEvolveChrome(tab, requestScope);
    }

    _fetchEvolveTab(tab)
      .catch((err) => {
        // user stopped / 切页 / 切 scope 触发的 abort 不是真实失败，保留现有 UI
        if (err && (err.name === "AbortError" || err.name === "DOMException"))
          return;
        setCachedTab(
          tab,
          { _error: err.message || "Network error" },
          requestScope,
        );
        if (panel) {
          panel.innerHTML = `<div class="evolve-empty-state evolve-error-state"><div class="evolve-empty-icon evolve-error-icon">⚠️</div><p class="evolve-empty-title">${_tt("evolve.error.analyzeFailed", { error: (window.esc || String)(err.message) })}</p><p class="evolve-empty-hint">${_tt("evolve.error.retryHint")}</p><button class="btn btn-primary btn-sm evolve-retry-btn" data-tab="${esc(tab)}">${esc(_tt("evolve.btn.retry"))}</button></div>`;
          _bindRetryButtons(panel);
        }
        if (window.showToast)
          window.showToast.error(
            _tt("evolve.error.analyzeFailed", { error: err.message }),
            0,
            {
              label: _tt("evolve.btn.retry"),
              callback: () => refreshEvolveTab(tab),
            },
          );
      })
      .finally(() => {
        if (evolveDetachedTabs[tab]) {
          delete evolveDetachedTabs[tab];
          return;
        }
        _clearTabLoading(tab, requestScope);
        progressState.starting = false;
        _syncEvolveChrome(tab, requestScope);
      });
  }

  function refreshAllEvolveTabs() {
    const nonAI = EVOLVE_TABS.filter((t) => !AI_TABS.has(t));
    const ai = EVOLVE_TABS.filter((t) => AI_TABS.has(t));

    // Show a progress banner
    const body = $("#evolve-tab-body");
    if (body) {
      const banner = document.createElement("div");
      banner.className = "evolve-refresh-all-banner";
      banner.id = "evolve-refresh-all-banner";
      banner.innerHTML = `<span>${_tt("evolve.status.analyzing")}</span>`;
      body.insertBefore(banner, body.firstChild);
    }

    // Fire all non-AI tabs in parallel
    nonAI.forEach((tab) => refreshEvolveTab(tab));

    // AI tabs sequentially (they're expensive)
    let idx = 0;
    function doNextAI() {
      if (idx >= ai.length) {
        // Remove banner when done
        const b = document.getElementById("evolve-refresh-all-banner");
        if (b) b.remove();
        return;
      }
      const tab = ai[idx++];
      // Update banner with current tab
      const b = document.getElementById("evolve-refresh-all-banner");
      if (b)
        b.innerHTML = `<span class="evolve-think-dot"></span> ${_tt("evolve.tab." + tab)} — ${_tt("evolve.status.analyzing")}`;
      _markTabLoading(tab, getEvolveScope());
      _syncEvolveChrome(tab);
      _fetchEvolveTab(tab)
        .catch(() => {})
        .finally(() => {
          _clearTabLoading(tab, getEvolveScope());
          _syncEvolveChrome(tab);
          setTimeout(doNextAI, 300);
        });
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
        try {
          return JSON.parse(jsonMatch[1]);
        } catch (e2) {
          /* fall through */
        }
      }
      // Try to find first { ... } block
      const braceMatch = raw.match(/\{[\s\S]*\}/);
      if (braceMatch) {
        try {
          return JSON.parse(braceMatch[0]);
        } catch (e3) {
          /* fall through */
        }
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
        data.categories.forEach((c) => {
          if (!Array.isArray(c.items)) c.items = [];
          if (!Array.isArray(c.tags)) c.tags = [];
          c.items.forEach((item) => {
            if (typeof item === "string") item = { text: item };
          });
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
        data.rules.forEach((r) => {
          if (!Array.isArray(r.evidence)) r.evidence = [];
        });
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

      categories.forEach((cat) => {
        const card = document.createElement("div");
        card.className = "profile-category-card";
        let html = `<div class="profile-cat-header"><span class="profile-cat-icon">${cat.icon || "📋"}</span><span class="profile-cat-name">${esc(cat.name || "")}</span></div>`;

        // Tags (short labels like tech names)
        if (cat.tags && cat.tags.length) {
          html += `<div class="profile-cat-tags">${cat.tags.map((t) => `<span class="evolve-tag">${esc(String(t))}</span>`).join("")}</div>`;
        }

        // Items (detailed facts)
        if (cat.items && cat.items.length) {
          html += `<ul class="profile-cat-items">`;
          cat.items.forEach((item) => {
            const text = typeof item === "string" ? item : item.text || "";
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
      radarSection.innerHTML = `<div class="profile-section-title">${esc(_tt("evolve.profile.radarTitle"))}</div>`;
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
      data.radar.dimensions.forEach((dim) => {
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
      container.innerHTML = `<div class="evolve-empty-state"><p>${_tt("evolve.empty.profile")}</p></div>`;
    }
  }

  function drawRadarChart(container, dimensions) {
    const width = 280,
      height = 280,
      margin = 50;
    const radius = Math.min(width, height) / 2 - margin;
    const levels = 5;
    const n = dimensions.length;
    if (n < 3) return; // Need at least 3 dimensions for radar
    const angleSlice = (Math.PI * 2) / n;

    const svg = d3
      .select(container)
      .append("svg")
      .attr("viewBox", `0 0 ${width} ${height}`)
      .append("g")
      .attr("transform", `translate(${width / 2},${height / 2})`);

    // Draw grid
    for (let level = 1; level <= levels; level++) {
      const r = (radius / levels) * level;
      const points = d3.range(n).map((i) => {
        const angle = angleSlice * i - Math.PI / 2;
        return [r * Math.cos(angle), r * Math.sin(angle)];
      });
      svg
        .append("polygon")
        .attr("points", points.map((p) => p.join(",")).join(" "))
        .style("fill", "none")
        .style("stroke", "var(--border-light)")
        .style("stroke-width", "1");
    }

    // Draw axes + labels
    dimensions.forEach((d, i) => {
      const angle = angleSlice * i - Math.PI / 2;
      const x = radius * Math.cos(angle);
      const y = radius * Math.sin(angle);
      svg
        .append("line")
        .attr("x1", 0)
        .attr("y1", 0)
        .attr("x2", x)
        .attr("y2", y)
        .style("stroke", "var(--border-light)")
        .style("stroke-width", "1");
      const lx = (radius + 18) * Math.cos(angle);
      const ly = (radius + 18) * Math.sin(angle);
      svg
        .append("text")
        .attr("x", lx)
        .attr("y", ly)
        .attr("text-anchor", "middle")
        .attr("dominant-baseline", "middle")
        .style("font-size", "10px")
        .style("fill", "var(--text-secondary)")
        .text(d.name || "");
    });

    // Draw data polygon
    const dataPoints = dimensions.map((d, i) => {
      const angle = angleSlice * i - Math.PI / 2;
      const r = radius * (d.score || 0);
      return [r * Math.cos(angle), r * Math.sin(angle)];
    });

    svg
      .append("polygon")
      .attr("points", dataPoints.map((p) => p.join(",")).join(" "))
      .style("fill", "var(--accent)")
      .style("fill-opacity", "0.15")
      .style("stroke", "var(--accent)")
      .style("stroke-width", "2");

    // Draw data points
    dataPoints.forEach((p, i) => {
      svg
        .append("circle")
        .attr("cx", p[0])
        .attr("cy", p[1])
        .attr("r", 4)
        .style("fill", "var(--accent)")
        .style("stroke", "white")
        .style("stroke-width", "1.5");
    });
  }

  function renderMemoryTab(data, container) {
    if (data._parseError) {
      container.innerHTML = `<div class="evolve-raw-result">${(window.renderMarkdownSimple || window.esc || String)(data._raw)}</div>`;
      return;
    }
    if (!data.cards?.length && !data.nodes?.length && !data.links?.length) {
      container.innerHTML = `<div class="evolve-empty-state"><div class="evolve-empty-icon">🧠</div><p class="evolve-empty-title">${_tt("evolve.empty.memory")}</p><p class="evolve-empty-hint">${_tt("evolve.empty.refreshHint")}</p></div>`;
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
      data.cards.forEach((card) => {
        const div = document.createElement("div");
        div.className = "evolve-memory-card";
        div.dataset.id = card.id;
        const typeColors = {
          preference: "var(--accent)",
          workflow: "var(--bash-accent)",
          tooling: "var(--read-accent)",
          design: "var(--edit-accent)",
          communication: "var(--grep-accent)",
        };
        const node = (data.nodes || []).find((n) => n.id === card.id);
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
          const items = card.evidence
            .slice(0, 3)
            .map((ev) =>
              typeof ev === "object"
                ? `"${esc(ev.quote || "")}" <span class="evidence-meta">(${esc(ev.date || "")})</span>`
                : esc(String(ev)),
            )
            .join("<br>");
          evidenceHtml = `<div class="memory-card-evidence">${items}</div>`;
        } else if (typeof card.evidence === "string" && card.evidence) {
          evidenceHtml = `<div class="memory-card-evidence">"${esc(card.evidence)}"</div>`;
        }

        const priorityBadge = node?.priority
          ? `<span class="memory-priority ${node.priority}">${node.priority}</span>`
          : "";
        const statusBadge =
          node?.status === "stale"
            ? `<span class="memory-status stale">stale</span>`
            : "";
        const conflictsHtml = card.conflictsWith?.length
          ? `<span class="memory-conflicts" title="Conflicts with: ${card.conflictsWith.join(", ")}">⚡</span>`
          : "";

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
      drawForceGraph(graphDiv, data.nodes, data.links || [], (nodeId) => {
        // Highlight corresponding card
        listDiv.querySelectorAll(".evolve-memory-card").forEach((c) => {
          c.classList.toggle("highlighted", c.dataset.id === nodeId);
        });
        const target = [
          ...listDiv.querySelectorAll(".evolve-memory-card"),
        ].find((c) => c.dataset.id === nodeId);
        if (target)
          target.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    }
  }

  function drawForceGraph(container, nodes, links, onNodeClick) {
    const rect = container.getBoundingClientRect();
    const width = Math.max(rect.width || 450, 300);
    const height = Math.max(rect.height || 350, 280);
    const typeColors = {
      preference: "#5856d6",
      workflow: "#16a34a",
      tooling: "#d97706",
      design: "#ea580c",
      communication: "#2563eb",
    };
    const typeLabels = {
      preference: _tt("evolve.graph.type.preference"),
      workflow: _tt("evolve.graph.type.workflow"),
      tooling: _tt("evolve.graph.type.tooling"),
      design: _tt("evolve.graph.type.design"),
      communication: _tt("evolve.graph.type.communication"),
    };
    const n = nodes.length;

    // ── SVG + zoom layer ──
    const svg = d3
      .select(container)
      .append("svg")
      .attr("viewBox", `0 0 ${width} ${height}`)
      .style("width", "100%")
      .style("height", "100%");

    // Defs: glow filter for hover
    const defs = svg.append("defs");
    const filter = defs
      .append("filter")
      .attr("id", "glow")
      .attr("x", "-50%")
      .attr("y", "-50%")
      .attr("width", "200%")
      .attr("height", "200%");
    filter
      .append("feGaussianBlur")
      .attr("stdDeviation", "3")
      .attr("result", "blur");
    const merge = filter.append("feMerge");
    merge.append("feMergeNode").attr("in", "blur");
    merge.append("feMergeNode").attr("in", "SourceGraphic");

    const g = svg.append("g"); // zoom target

    const zoom = d3
      .zoom()
      .scaleExtent([0.3, 4])
      .on("zoom", (e) => g.attr("transform", e.transform));
    svg.call(zoom);

    // ── Tooltip ──
    const tooltip = d3
      .select(container)
      .append("div")
      .style("position", "absolute")
      .style("pointer-events", "none")
      .style("background", "var(--bg-card, #fff)")
      .style("border", "1px solid var(--border-light, #e0e0e0)")
      .style("border-radius", "6px")
      .style("padding", "6px 10px")
      .style("font-size", "11px")
      .style("box-shadow", "0 4px 12px rgba(0,0,0,.12)")
      .style("opacity", 0)
      .style("transition", "opacity .15s")
      .style("z-index", "10")
      .style("max-width", "200px");

    // ── Type clustering: assign cluster center per type ──
    const types = [...new Set(nodes.map((d) => d.type || "preference"))];
    const angleStep = (2 * Math.PI) / Math.max(types.length, 1);
    const clusterR = Math.min(width, height) * 0.25;
    const typeCenters = {};
    types.forEach((t, i) => {
      typeCenters[t] = {
        x: width / 2 + clusterR * Math.cos(angleStep * i - Math.PI / 2),
        y: height / 2 + clusterR * Math.sin(angleStep * i - Math.PI / 2),
      };
    });

    // ── Forces: adaptive to node count ──
    const nodeIds = new Set(nodes.map((n) => n.id));
    const validLinks = links.filter(
      (l) => nodeIds.has(l.source) && nodeIds.has(l.target),
    );
    const chargeStrength = n > 30 ? -60 : n > 15 ? -80 : -100;
    const linkDist = n > 30 ? 40 : n > 15 ? 55 : 70;

    // Stop any previous simulation before creating a new one
    if (activeSimulation) {
      activeSimulation.on("tick", null);
      activeSimulation.on("end", null);
      activeSimulation.stop();
      activeSimulation = null;
    }

    const simulation = d3
      .forceSimulation(nodes)
      .force(
        "link",
        d3
          .forceLink(validLinks)
          .id((d) => d.id)
          .distance(linkDist)
          .strength((d) => d.strength || 0.4),
      )
      .force("charge", d3.forceManyBody().strength(chargeStrength))
      .force(
        "x",
        d3.forceX((d) => typeCenters[d.type || "preference"].x).strength(0.08),
      )
      .force(
        "y",
        d3.forceY((d) => typeCenters[d.type || "preference"].y).strength(0.08),
      )
      .force("center", d3.forceCenter(width / 2, height / 2).strength(0.02))
      .force(
        "collision",
        d3.forceCollide().radius((d) => _nodeR(d) + 3),
      );

    activeSimulation = simulation;

    function _nodeR(d) {
      return Math.sqrt(d.frequency || 1) * 4 + 4;
    }

    // ── Links ──
    const link = g
      .append("g")
      .attr("class", "links")
      .selectAll("line")
      .data(validLinks)
      .enter()
      .append("line")
      .style("stroke", "var(--border-light, #ddd)")
      .style("stroke-opacity", 0.5)
      .style("stroke-width", (d) => Math.max((d.strength || 0.3) * 2, 0.5));

    // ── Nodes ──
    const node = g
      .append("g")
      .attr("class", "nodes")
      .selectAll("g")
      .data(nodes)
      .enter()
      .append("g")
      .style("cursor", "pointer")
      .on("click", (e, d) => {
        if (onNodeClick) onNodeClick(d.id);
      })
      .on("mouseenter", (e, d) => {
        d3.select(e.currentTarget)
          .select("circle")
          .style("filter", "url(#glow)");
        // Highlight connected links
        link
          .style("stroke-opacity", (l) =>
            (l.source.id || l.source) === d.id ||
            (l.target.id || l.target) === d.id
              ? 1
              : 0.1,
          )
          .style("stroke-width", (l) =>
            (l.source.id || l.source) === d.id ||
            (l.target.id || l.target) === d.id
              ? 2.5
              : 0.5,
          );
        node.style("opacity", (nd) =>
          nd.id === d.id ||
          validLinks.some(
            (l) =>
              ((l.source.id || l.source) === d.id &&
                (l.target.id || l.target) === nd.id) ||
              ((l.target.id || l.target) === d.id &&
                (l.source.id || l.source) === nd.id),
          )
            ? 1
            : 0.25,
        );
        // Tooltip
        const cRect = container.getBoundingClientRect();
        const type = d.type || "preference";
        tooltip
          .html(
            `<b>${esc(d.label || d.id)}</b><br><span style="color:${typeColors[type]}">${typeLabels[type] || type}</span> · ${d.confidence || "medium"}<br>${esc(_tt("evolve.field.frequency"))} ${d.frequency || 1}`,
          )
          .style("left", e.clientX - cRect.left + 12 + "px")
          .style("top", e.clientY - cRect.top - 10 + "px")
          .style("opacity", 1);
      })
      .on("mouseleave", (e) => {
        d3.select(e.currentTarget).select("circle").style("filter", null);
        link
          .style("stroke-opacity", 0.5)
          .style("stroke-width", (d) => Math.max((d.strength || 0.3) * 2, 0.5));
        node.style("opacity", 1);
        tooltip.style("opacity", 0);
      })
      .call(
        d3
          .drag()
          .on("start", (e, d) => {
            if (!e.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (e, d) => {
            d.fx = e.x;
            d.fy = e.y;
          })
          .on("end", (e, d) => {
            if (!e.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          }),
      );

    node
      .append("circle")
      .attr("r", (d) => _nodeR(d))
      .style("fill", (d) => typeColors[d.type] || "#5856d6")
      .style("fill-opacity", (d) =>
        d.confidence === "high" ? 0.85 : d.confidence === "medium" ? 0.55 : 0.3,
      )
      .style("stroke", (d) => typeColors[d.type] || "#5856d6")
      .style("stroke-width", (d) => (d.confidence === "low" ? 1 : 1.5))
      .style("stroke-dasharray", (d) =>
        d.confidence === "low" ? "3,2" : "none",
      )
      .style("transition", "filter .15s");

    node
      .append("text")
      .text((d) =>
        d.label?.length > 12 ? d.label.substring(0, 12) + "…" : d.label,
      )
      .attr("dy", (d) => -(_nodeR(d) + 5))
      .attr("text-anchor", "middle")
      .style("font-size", "9px")
      .style("fill", "var(--text-muted)")
      .style("pointer-events", "none");

    // ── Type legend ──
    const legend = svg
      .append("g")
      .attr("transform", `translate(8, ${height - types.length * 16 - 4})`);
    types.forEach((t, i) => {
      const lg = legend
        .append("g")
        .attr("transform", `translate(0, ${i * 16})`);
      lg.append("circle")
        .attr("r", 4)
        .attr("cx", 4)
        .attr("cy", 0)
        .style("fill", typeColors[t] || "#5856d6");
      lg.append("text")
        .attr("x", 12)
        .attr("dy", "0.35em")
        .text(typeLabels[t] || t)
        .style("font-size", "9px")
        .style("fill", "var(--text-muted)");
    });

    // ── Zoom controls ──
    const controls = d3
      .select(container)
      .append("div")
      .style("position", "absolute")
      .style("top", "8px")
      .style("right", "8px")
      .style("display", "flex")
      .style("flex-direction", "column")
      .style("gap", "4px");

    [
      { label: "+", scale: 1.4 },
      { label: "−", scale: 1 / 1.4 },
      { label: "⊙", scale: 0 },
    ].forEach((btn) => {
      const b = controls
        .append("button")
        .text(btn.label)
        .style("width", "26px")
        .style("height", "26px")
        .style("border", "1px solid var(--border-light, #ddd)")
        .style("border-radius", "4px")
        .style("background", "var(--bg-card, #fff)")
        .style("cursor", "pointer")
        .style("font-size", "14px")
        .style("line-height", "1")
        .style("color", "var(--text-secondary, #666)")
        .style("display", "flex")
        .style("align-items", "center")
        .style("justify-content", "center");
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
      link
        .attr("x1", (d) => d.source.x)
        .attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x)
        .attr("y2", (d) => d.target.y);
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    // After stabilization, fit to content
    simulation.on("end", () => {
      const xs = nodes.map((d) => d.x),
        ys = nodes.map((d) => d.y);
      const x0 = Math.min(...xs) - 30,
        x1 = Math.max(...xs) + 30;
      const y0 = Math.min(...ys) - 30,
        y1 = Math.max(...ys) + 30;
      const bw = x1 - x0,
        bh = y1 - y0;
      const scale = Math.min(width / bw, height / bh, 1.5);
      const tx = (width - bw * scale) / 2 - x0 * scale;
      const ty = (height - bh * scale) / 2 - y0 * scale;
      svg
        .transition()
        .duration(600)
        .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
    });
  }

  function renderRulesTab(data, container) {
    if (data._parseError) {
      container.innerHTML = `<div class="evolve-raw-result">${(window.renderMarkdownSimple || window.esc || String)(data._raw)}</div>`;
      return;
    }
    container.innerHTML = "";
    const rules = data.rules || [];
    if (!rules.length) {
      container.innerHTML = `<div class="evolve-empty-state"><p>${_tt("evolve.empty.rules")}</p></div>`;
      return;
    }

    // Top bar: category filter + copy all
    const topBar = document.createElement("div");
    topBar.className = "rules-top-bar";
    container.appendChild(topBar);

    // Category filter
    const categories = [...new Set(rules.map((r) => r.category))];
    const filterBar = document.createElement("div");
    filterBar.className = "rules-filter-bar";
    let activeFilter = "all";
    topBar.appendChild(filterBar);

    // Copy all button
    const copyAllBtn = document.createElement("button");
    copyAllBtn.className = "rules-copy-all-btn";
    copyAllBtn.innerHTML = `<span class="rules-copy-icon">📋</span> ${_tt("evolve.rules.copyAll")}`;
    copyAllBtn.onclick = () => {
      const filtered =
        activeFilter === "all"
          ? rules
          : rules.filter((r) => r.category === activeFilter);
      filtered.sort(
        (a, b) =>
          (({ P0: 0, P1: 1, P2: 2 })[a.priority] ?? 9) -
          ({ P0: 0, P1: 1, P2: 2 }[b.priority] ?? 9),
      );
      const allText = filtered.map((r) => r.rule || "").join("\n\n");
      _copyToClipboard(allText, copyAllBtn);
    };
    topBar.appendChild(copyAllBtn);

    function renderFilter() {
      filterBar.innerHTML = "";
      [
        { key: "all", label: _tt("evolve.rules.filterAll") },
        ...categories.map((c) => ({ key: c, label: c })),
      ].forEach((f) => {
        const btn = document.createElement("button");
        btn.className = `scope-tab${f.key === activeFilter ? " active" : ""}`;
        btn.textContent = f.label;
        btn.onclick = () => {
          activeFilter = f.key;
          renderFilter();
          renderCards();
        };
        filterBar.appendChild(btn);
      });
    }

    const cardsContainer = document.createElement("div");
    cardsContainer.className = "rules-card-list";
    container.appendChild(cardsContainer);

    function renderCards() {
      cardsContainer.innerHTML = "";
      const filtered =
        activeFilter === "all"
          ? rules
          : rules.filter((r) => r.category === activeFilter);
      filtered.sort((a, b) => {
        const prio = { P0: 0, P1: 1, P2: 2 };
        return (prio[a.priority] ?? 9) - (prio[b.priority] ?? 9);
      });
      filtered.forEach((rule) => {
        const card = document.createElement("div");
        card.className = `rule-card priority-${(rule.priority || "P2").toLowerCase()}`;

        // Header: priority + category + frequency + copy button
        const evidenceHtml = (rule.evidence || [])
          .map(
            (e) =>
              `<div class="rule-evidence-item"><span class="rule-quote">"${esc(e.quote)}"</span>${e.session ? ` <a class="rule-session-link" href="#${e.session}">${_tt("evolve.rules.sessionLink")}</a>` : ""}</div>`,
          )
          .join("");

        const whyText = rule.why || "";

        card.innerHTML = `<div class="rule-card-header">
            <span class="rule-priority-badge">${esc(rule.priority || "P2")}</span>
            <span class="rule-category">${esc(rule.category || "")}</span>
            ${rule.frequency ? `<span class="rule-freq">${rule.frequency}x</span>` : ""}
            <button class="rule-copy-btn" title="${esc(_tt("evolve.rules.copyTitle"))}">📋</button>
          </div>
          <div class="rule-text">${esc(rule.rule)}</div>
          ${whyText ? `<details class="rule-why-details"><summary>${_tt("evolve.rules.why")}</summary><div class="rule-why-text">${esc(whyText)}</div></details>` : ""}
          ${evidenceHtml ? `<details class="rule-evidence"><summary>${_tt("evolve.rules.evidence")} (${rule.evidence.length})</summary>${evidenceHtml}</details>` : ""}`;

        // Bind copy button — only copy rule text
        const copyBtn = card.querySelector(".rule-copy-btn");
        if (copyBtn)
          copyBtn.onclick = (e) => {
            e.stopPropagation();
            _copyToClipboard(rule.rule || "", copyBtn);
          };

        cardsContainer.appendChild(card);
      });
    }
    renderFilter();
    renderCards();
  }

  /** Copy text to clipboard and show feedback on the button */
  function _copyToClipboard(text, btn) {
    navigator.clipboard
      .writeText(text)
      .then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = btn.classList.contains("rules-copy-all-btn")
          ? '<span class="rules-copy-icon">✓</span> Copied!'
          : "✓";
        btn.classList.add("copied");
        setTimeout(() => {
          btn.innerHTML = orig;
          btn.classList.remove("copied");
        }, 1500);
      })
      .catch(() => {
        // Fallback for non-HTTPS
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        const orig = btn.innerHTML;
        btn.innerHTML = btn.classList.contains("rules-copy-all-btn")
          ? '<span class="rules-copy-icon">✓</span> Copied!'
          : "✓";
        btn.classList.add("copied");
        setTimeout(() => {
          btn.innerHTML = orig;
          btn.classList.remove("copied");
        }, 1500);
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

      const typeColors = {
        style: "#5856d6",
        scope: "#f59e0b",
        accuracy: "#dc2626",
        workflow: "#16a34a",
        overengineering: "#ea580c",
      };
      events.forEach((ev) => {
        const div = document.createElement("div");
        div.className = "signal-event";
        div.innerHTML = `<div class="signal-event-dot" style="background:${typeColors[ev.type] || "#888"}"></div>
          <div class="signal-event-body">
            <div class="signal-event-header">
              <span class="signal-type-badge" style="background:${typeColors[ev.type] || "#888"}">${esc(ev.type)}</span>
              <span class="signal-date">${esc(ev.date || "")}</span>
              ${ev.session ? `<a class="rule-session-link" href="#${ev.session}">${_tt("evolve.sessionLink")}</a>` : ""}
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
      container.innerHTML = `<div class="evolve-empty-state"><p>${_tt("evolve.empty.signals")}</p></div>`;
    }
  }

  function drawSignalsTimeline(container, timeline) {
    const margin = { top: 20, right: 20, bottom: 30, left: 40 };
    const width = 700 - margin.left - margin.right;
    const height = 180 - margin.top - margin.bottom;
    const types = ["style", "scope", "accuracy", "workflow"];
    const typeColors = {
      style: "#5856d6",
      scope: "#f59e0b",
      accuracy: "#dc2626",
      workflow: "#16a34a",
    };

    // Stack data
    const stackData = timeline.map((d) => {
      const obj = { date: d.date };
      types.forEach((t) => {
        obj[t] = d.counts?.[t] || 0;
      });
      return obj;
    });

    const svg = d3
      .select(container)
      .append("svg")
      .attr(
        "viewBox",
        `0 0 ${width + margin.left + margin.right} ${height + margin.top + margin.bottom}`,
      )
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    const x = d3
      .scaleBand()
      .domain(stackData.map((d) => d.date))
      .range([0, width])
      .padding(0.2);
    const stack = d3.stack().keys(types);
    const series = stack(stackData);
    const yMax = d3.max(series, (s) => d3.max(s, (d) => d[1])) || 5;
    const y = d3.scaleLinear().domain([0, yMax]).range([height, 0]);

    // Bars
    svg
      .selectAll("g.series")
      .data(series)
      .enter()
      .append("g")
      .attr("fill", (d, i) => typeColors[types[i]])
      .attr("fill-opacity", 0.7)
      .selectAll("rect")
      .data((d) => d)
      .enter()
      .append("rect")
      .attr("x", (d) => x(d.data.date))
      .attr("width", x.bandwidth())
      .attr("y", height)
      .attr("height", 0)
      .transition()
      .duration(400)
      .attr("y", (d) => y(d[1]))
      .attr("height", (d) => y(d[0]) - y(d[1]));

    // Axes
    svg
      .append("g")
      .attr("transform", `translate(0,${height})`)
      .call(d3.axisBottom(x).tickFormat((d) => d.slice(5)))
      .selectAll("text")
      .style("font-size", "9px");
    svg
      .append("g")
      .call(d3.axisLeft(y).ticks(4))
      .selectAll("text")
      .style("font-size", "9px");

    // Legend
    const legend = svg
      .append("g")
      .attr("transform", `translate(${width - 200},-10)`);
    types.forEach((t, i) => {
      legend
        .append("rect")
        .attr("x", i * 55)
        .attr("width", 10)
        .attr("height", 10)
        .attr("rx", 2)
        .attr("fill", typeColors[t]);
      legend
        .append("text")
        .attr("x", i * 55 + 14)
        .attr("y", 9)
        .text(t)
        .style("font-size", "9px")
        .style("fill", "var(--text-muted)");
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
      cards.forEach((card) => {
        const trendIcon =
          card.trend === "decreasing"
            ? "📉"
            : card.trend === "increasing"
              ? "📈"
              : "➡️";
        const typeColors = {
          error: "#dc2626",
          efficiency: "#f59e0b",
          knowledge_gap: "#3b82f6",
          workflow: "#16a34a",
        };
        const bubble = bubbles.find((b) => b.id === card.id);
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
      container.innerHTML = `<div class="evolve-empty-state"><p>${_tt("evolve.empty.patterns")}</p></div>`;
    }
  }

  function drawBubbleCluster(container, bubbles) {
    const width = 400,
      height = 350;
    const typeColors = {
      error: "#dc2626",
      efficiency: "#f59e0b",
      knowledge_gap: "#3b82f6",
      workflow: "#16a34a",
    };

    const packData = {
      children: bubbles.map((b) => ({ ...b, value: b.frequency || 1 })),
    };
    const root = d3.hierarchy(packData).sum((d) => d.value);
    d3
      .pack()
      .size([width - 20, height - 20])
      .padding(6)(root);

    const svg = d3
      .select(container)
      .append("svg")
      .attr("viewBox", `0 0 ${width} ${height}`);

    const leaf = svg
      .selectAll("g")
      .data(root.leaves())
      .enter()
      .append("g")
      .attr("transform", (d) => `translate(${d.x + 10},${d.y + 10})`);

    leaf
      .append("circle")
      .attr("r", 0)
      .style("fill", (d) => typeColors[d.data.type] || "#888")
      .style("fill-opacity", 0.2)
      .style("stroke", (d) => typeColors[d.data.type] || "#888")
      .style("stroke-width", 1.5)
      .transition()
      .duration(500)
      .attr("r", (d) => d.r);

    leaf
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.3em")
      .style("font-size", (d) => Math.max(8, Math.min(d.r / 3, 12)) + "px")
      .style("fill", "var(--text-secondary)")
      .text((d) => {
        const label = d.data.label || "";
        return label.length > d.r / 3
          ? label.substring(0, Math.floor(d.r / 3)) + "…"
          : label;
      });
  }

  // ── Sync to Claude Code ──
  const SYNC_TABS = new Set(["profile", "memory"]);

  function isSyncableCached(tab, scope) {
    if (!SYNC_TABS.has(tab)) return false;
    const cached = getExactCachedTab(tab, scope || getEvolveScope());
    return !!(cached && hasRenderableData(tab, cached.data));
  }

  function updateSyncButtonState() {
    const btn = $("#evolve-tab-sync");
    if (!btn) return;
    btn.disabled = !isSyncableCached(evolveActiveTab);
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
    panel.innerHTML =
      '<div style="padding:8px 0;color:var(--text-muted);font-size:12px">Loading preview...</div>';

    const targets = [];
    if (isSyncableCached("memory")) targets.push("memory");
    if (isSyncableCached("profile")) targets.push("claude_md");

    if (targets.length === 0) {
      panel.innerHTML =
        '<div style="padding:8px 0;color:var(--text-muted)">No Profile or Memory data to sync. Run Refresh first.</div>';
      return;
    }

    fetch("/api/evolve/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "preview",
        targets,
        scope: getEvolveScope(),
      }),
    })
      .then((r) => r.json())
      .then((data) => renderSyncPanel(panel, data, targets))
      .catch((err) => {
        panel.innerHTML = `<div style="color:var(--danger,#e53e3e)">Preview failed: ${(window.esc || String)(err.message)}</div>`;
        if (window.showToast)
          window.showToast.error("Preview failed: " + err.message, 0, {
            label: "Retry",
            callback: () => toggleSyncPanel(),
          });
      });
  }

  function renderSyncPanel(panel, preview, initialTargets) {
    const esc = window.esc || String;
    let html = `<div class="sync-panel-title">${esc(_tt("evolve.sync.title"))}</div>`;

    // Memory target
    const memData = preview.memory;
    const hasMemory = memData && !memData.error;
    html += `<div class="sync-target${hasMemory ? "" : " disabled"}" id="sync-target-memory">
      <input type="checkbox" id="sync-check-memory" ${hasMemory ? "checked" : "disabled"}>
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
    html += `<div class="sync-target${hasMd ? "" : " disabled"}" id="sync-target-claude-md">
      <input type="checkbox" id="sync-check-claude-md" ${hasMd ? "checked" : "disabled"}>
      <div class="sync-target-info">
        <div class="sync-target-label">CLAUDE.md</div>
        <div class="sync-target-path">~/.claude/CLAUDE.md</div>
        <div class="sync-target-summary">`;
    if (hasMd) {
      const action =
        mdData.status === "replace"
          ? _tt("evolve.sync.replace")
          : _tt("evolve.sync.append");
      html += _tt("evolve.sync.mdSummary", {
        action,
        categories: mdData.categories,
        radar_dims: mdData.radar_dims,
        lines: mdData.lines,
      });
    } else {
      html += esc(mdData ? mdData.error : "No profile data");
    }
    html += `</div></div></div>`;

    // Actions
    const canSync = hasMemory || hasMd;
    html += `<div class="sync-actions">
      <button class="btn-text" id="sync-cancel">${esc(_tt("evolve.sync.cancel"))}</button>
      <button class="btn-text btn-confirm" id="sync-confirm" ${canSync ? "" : "disabled"}>${esc(_tt("evolve.sync.confirm"))}</button>
    </div>`;

    panel.innerHTML = html;

    // Bind events
    const cancelBtn = panel.querySelector("#sync-cancel");
    if (cancelBtn)
      cancelBtn.onclick = () => {
        panel.classList.add("hidden");
        panel.innerHTML = "";
      };

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
    if (confirmBtn) {
      confirmBtn.disabled = true;
      confirmBtn.textContent = _tt("evolve.sync.syncing");
    }

    fetch("/api/evolve/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "execute",
        targets,
        scope: getEvolveScope(),
      }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          let msg = _tt("evolve.sync.done");
          const parts = [];
          if (data.memory)
            parts.push(
              `Memory: +${data.memory.created} new, ~${data.memory.updated} updated`,
            );
          if (data.claude_md)
            parts.push(
              `CLAUDE.md: ${data.claude_md.status} (${data.claude_md.lines} lines)`,
            );
          msg += parts.join("; ");
          panel.innerHTML = `<div class="sync-result">${(window.esc || String)(msg)}</div>`;
        } else {
          const errors = [];
          if (data.memory && data.memory.error)
            errors.push(`Memory: ${data.memory.error}`);
          if (data.claude_md && data.claude_md.error)
            errors.push(`CLAUDE.md: ${data.claude_md.error}`);
          panel.innerHTML = `<div class="sync-result error">${(window.esc || String)(errors.join("; ") || "Sync failed")}</div>`;
        }
        setTimeout(() => {
          panel.classList.add("hidden");
          panel.innerHTML = "";
        }, 3000);
      })
      .catch((err) => {
        panel.innerHTML = `<div class="sync-result error">Sync failed: ${(window.esc || String)(err.message)}</div>`;
      });
  }

  // ── Public API for app.js linkage ──
  window.getEvolveScope = getEvolveScope;

  window.abortEvolveStreams = function (detachOnly, keepRecoveredPollers) {
    if (!detachOnly) {
      Object.keys(evolveRecoveredRunPollers).forEach((tab) =>
        _stopRecoveredRunPoll(tab),
      );
    } else if (!keepRecoveredPollers) {
      Object.keys(evolveRecoveredRunPollers).forEach((tab) => {
        const poller = evolveRecoveredRunPollers[tab];
        if (poller && poller.timer) clearTimeout(poller.timer);
        delete evolveRecoveredRunPollers[tab];
      });
      _syncRecoveredRunFlag();
    }
    Object.entries(evolveStreamAborts).forEach(([tab, ctrl]) => {
      if (detachOnly) {
        ctrl.detachOnly = true;
        ctrl.keepRecoveredPollers = !!keepRecoveredPollers;
        evolveDetachedTabs[tab] = true;
      }
      ctrl.abort();
    });
    evolveStreamAborts = {};
    if (!detachOnly) {
      evolveLoadingTabs = {};
      evolveLoadingScopes = {};
      Object.keys(evolveProgressState).forEach((tab) =>
        _resetProgressState(tab),
      );
    }
    _syncEvolveChrome(evolveActiveTab);
  };

  window.navigateToEvolveTab = function (tab, data) {
    if (data) setCachedTab(tab, data);
    switchEvolveTab(tab);
    updateEvolveOverviewBar();
  };

  window.parseEvolveResponseExternal = function (tab, raw) {
    return parseEvolveResponse(tab, raw);
  };

  // Re-render UI-shell strings on language change without interrupting a running stream.
  let _localeListenerBound = false;
  if (!_localeListenerBound) {
    _localeListenerBound = true;
    window.addEventListener("localechange", () => {
      _registerEvolveI18n();
      if (window.applyI18nDom) window.applyI18nDom(document);
      _syncEvolveChrome(evolveActiveTab);
      if (_isTabBusy(evolveActiveTab, getEvolveScope())) {
        _updateProgressSummary(
          evolveActiveTab,
          _getProgressState(evolveActiveTab),
          true,
        );
      }
      // If a tab is mid-stream, don't restart it — only the static DOM labels above refresh.
      if (
        !evolveStreamAborts[evolveActiveTab] &&
        !_isTabBusy(evolveActiveTab, getEvolveScope())
      ) {
        const panel = document.querySelector(
          `.evolve-tab-panel[data-tab="${evolveActiveTab}"]`,
        );
        if (panel) _renderTabPanel(evolveActiveTab, panel);
      }
    });
  }

  // app.js runs its first applyI18nDom before this module loads, so refresh once after registering.
  _registerEvolveI18n();
  if (window.applyI18nDom) window.applyI18nDom(document);
  _getEvolveUpdatedEl();
})();
