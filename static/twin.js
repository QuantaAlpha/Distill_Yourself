/**
 * Digital Twin — Cognitive Handbook UI
 * Rich streaming analysis + wiki-style navigation
 * Reuses evolve.js streaming patterns (tool groups, text blocks, thinking dots)
 */
(function () {
  "use strict";

  // Trait categories for display
  const TRAIT_CATEGORIES = [
    { key: "价值取向",   icon: "⚖️", color: "#0f766e" },
    { key: "决策风格",   icon: "🧠", color: "#854d0e" },
    { key: "协作模式",   icon: "🤝", color: "#7c3aed" },
    { key: "能力边界",   icon: "📊", color: "#0369a1" },
    { key: "思维模式",   icon: "💡", color: "#c2410c" },
  ];

  const esc = (s) => {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
  };

  // ── State ──
  let overviewData = null;
  let analysisAbort = null;
  let analysisRunning = false;
  let eventsInited = false;
  let currentView = "overview"; // "overview" | "cards" | "card-detail" | "traits" | "trait-detail" | "analyzing"

  // ── Init ──
  window.initTwinView = function () {
    if (!eventsInited) { bindEvents(); eventsInited = true; }
    // Restore whichever sub-view was active (analysis runs independently)
    if (currentView === "analyzing") {
      _showOnlyView("analysis");
    } else {
      // Just reload overview if not already in a detail view
      loadOverview();
    }
    _updateAnalyzeButton();
  };

  function bindEvents() {
    const btnAnalyze = document.getElementById("twin-btn-analyze");
    const btnSync = document.getElementById("twin-btn-sync");
    const btnProgress = document.getElementById("twin-btn-progress");
    if (btnAnalyze) btnAnalyze.onclick = startAnalysis;
    if (btnSync) btnSync.onclick = startSync;
    if (btnProgress) btnProgress.onclick = toggleProgressView;
  }

  /** Toggle between analysis progress view and overview */
  function toggleProgressView() {
    if (currentView === "analyzing") {
      loadOverview();
    } else {
      currentView = "analyzing";
      _showOnlyView("analysis");
      setBreadcrumb([{ label: "分析中…" }]);
    }
    _updateProgressButton();
  }

  /** Show only the specified sub-view, hide all others */
  function _showOnlyView(name) {
    const views = {
      overview: "twin-overview",
      dimension: "twin-detail",
      item: "twin-item-view",
      analysis: "twin-analysis-progress",
    };
    for (const [k, id] of Object.entries(views)) {
      if (k === name) show(id);
      else hide(id);
    }
    _updateProgressButton();
  }

  /** Update analyze button and progress toggle to reflect current state */
  function _updateAnalyzeButton() {
    const btn = document.getElementById("twin-btn-analyze");
    const updatedEl = document.getElementById("twin-last-analyzed");
    if (analysisRunning) {
      if (btn) { btn.disabled = true; btn.textContent = "⏳ Analyzing..."; }
      if (updatedEl) updatedEl.classList.add("loading");
    } else {
      if (btn) { btn.disabled = false; btn.textContent = "🔄 Analyze"; }
      if (updatedEl) updatedEl.classList.remove("loading");
    }
    _updateProgressButton();
  }

  function _updateProgressButton() {
    const btnProgress = document.getElementById("twin-btn-progress");
    if (!btnProgress) return;
    if (analysisRunning) {
      btnProgress.classList.remove("hidden");
      btnProgress.textContent = currentView === "analyzing" ? "📋 查看概览" : "📊 查看进度";
    } else {
      btnProgress.classList.add("hidden");
    }
  }

  // ── Overview: Vertical Pipeline Layout ──
  function loadOverview() {
    fetch("/api/twin/overview")
      .then(r => r.json())
      .then((data) => {
        overviewData = data;
        renderOverview(data);
      })
      .catch(() => renderOverviewEmpty());
  }

  function _confColor(conf) {
    if (conf == null) return "var(--text-muted)";
    const h = Math.round(conf * 120); // 0=red, 60=yellow, 120=green
    return `hsl(${h}, 70%, 45%)`;
  }

  function renderOverview(data) {
    const container = document.getElementById("twin-overview");
    if (!container) return;

    currentView = "overview";
    _showOnlyView("overview");
    setBreadcrumb([]);
    // Hide stats bar in pipeline mode
    const bar = document.getElementById("twin-stats-bar");
    if (bar) bar.innerHTML = "";

    const eventsInfo = data.events || { count: 0, items: [] };
    const cardsInfo = data.cards || { count: 0, items: [] };
    const traitsInfo = data.traits || { count: 0, items: [] };
    const evtCount = eventsInfo.count || 0;
    const cardCount = cardsInfo.count || 0;
    const traitCount = traitsInfo.count || 0;
    const traitItems = traitsInfo.items || [];

    if (evtCount === 0 && cardCount === 0 && traitCount === 0) {
      renderOverviewEmpty(); return;
    }

    const updatedEl = document.getElementById("twin-last-analyzed");
    if (updatedEl) updatedEl.textContent = `${evtCount + cardCount + traitCount} 条认知记录`;

    // ─── Pipeline Header ───
    let html = `<div class="twin-pipeline-header">
      <span class="twin-ph-node" data-layer="events">📝 ${evtCount} 事件</span>
      <span class="twin-ph-arrow">→</span>
      <span class="twin-ph-node" data-layer="cards">🃏 ${cardCount} 判断卡</span>
      <span class="twin-ph-arrow">→</span>
      <span class="twin-ph-node" data-layer="traits">🧬 ${traitCount} 认知特质</span>
      <span class="twin-ph-arrow">→</span>
      <span class="twin-ph-node" data-layer="runtime">📦 Runtime</span>
    </div>`;

    html += '<div class="twin-pipeline">';

    // ─── L1: Evidence Events ───
    html += `<div class="twin-stage" style="--stage-color:#3b82f6">
      <div class="twin-stage-marker">L1</div>
      <div class="twin-stage-card">
        <div class="twin-stage-header" data-nav="events">
          <span class="twin-stage-icon">📝</span>
          <span class="twin-stage-title">Evidence Events</span>
          <span class="twin-stage-count">${evtCount}</span>
          <span class="twin-stage-cta">Browse all →</span>
        </div>
        <div class="twin-stage-body">`;

    const evtItems = eventsInfo.items || [];
    if (evtItems.length === 0) {
      html += '<div class="twin-dim-empty">暂无事件。点击 Analyze 开始提取。</div>';
    } else {
      for (const e of evtItems.slice(0, 3)) {
        const sig = e.signal_type || "";
        const quote = e.lesson || e.user_reaction || "";
        const domain = e.domain || "";
        html += `<div class="twin-event-row">
          <span class="twin-event-dot ${sig}"></span>
          <span class="twin-event-quote">${esc(truncate(quote, 80))}</span>
          <span class="twin-event-domain">${esc(domain)}</span>
        </div>`;
      }
      if (evtCount > 3) {
        html += `<div style="font-size:11px;color:var(--text-muted);margin-top:4px">+${evtCount - 3} more events</div>`;
      }
    }
    html += `</div></div></div>`;
    html += '<div class="twin-stage-connector">↓ distilled into</div>';

    // ─── L2: Judgment Cards ───
    html += `<div class="twin-stage" style="--stage-color:#8b5cf6">
      <div class="twin-stage-marker">L2</div>
      <div class="twin-stage-card">
        <div class="twin-stage-header" data-nav="cards">
          <span class="twin-stage-icon">🃏</span>
          <span class="twin-stage-title">Judgment Cards</span>
          <span class="twin-stage-count">${cardCount}</span>
          <span class="twin-stage-cta">View all →</span>
        </div>
        <div class="twin-stage-body">`;

    const cardItems = cardsInfo.items || [];
    if (cardItems.length === 0) {
      html += '<div class="twin-dim-empty">暂无判断卡。</div>';
    } else {
      html += '<div class="twin-card-grid">';
      for (const c of cardItems.slice(0, 4)) {
        const conf = c.confidence != null ? Math.round(c.confidence * 100) : 0;
        const status = c.status || "hypothesis";
        const statusClass = status === "confirmed" ? "confirmed" : status === "emerging" ? "emerging" : "hypothesis";
        const confColor = _confColor(c.confidence);
        html += `<div class="twin-card-preview" style="--card-color:${confColor}" data-card-id="${esc(c.id)}">
          <div class="twin-card-title">${esc(truncate(c.applies_when, 40))}</div>
          <div class="twin-conf-bar"><span style="width:${conf}%"></span></div>
          <div class="twin-item-meta" style="margin-top:2px">
            <span class="twin-status-badge ${statusClass}">${status}</span>
            <span class="twin-conf">${conf}%</span>
            ${c.evidence_count ? `<span class="twin-ep-count">${c.evidence_count} events</span>` : ""}
          </div>
          ${c.agent_action ? `<div class="twin-card-action">→ ${esc(truncate(c.agent_action, 50))}</div>` : ""}
        </div>`;
      }
      html += '</div>';
      if (cardCount > 4) {
        html += `<div style="font-size:11px;color:var(--text-muted);margin-top:8px;text-align:right">+${cardCount - 4} more cards</div>`;
      }
    }
    html += `</div></div></div>`;
    html += '<div class="twin-stage-connector">↓ generalized to</div>';

    // ─── L3: Cognitive Traits ───
    html += `<div class="twin-stage" style="--stage-color:#14b8a6">
      <div class="twin-stage-marker">L3</div>
      <div class="twin-stage-card">
        <div class="twin-stage-header" data-nav="traits">
          <span class="twin-stage-icon">🧬</span>
          <span class="twin-stage-title">Cognitive Traits</span>
          <span class="twin-stage-count">${traitCount}</span>
          <span class="twin-stage-cta">View all →</span>
        </div>
        <div class="twin-stage-body">`;

    if (traitItems.length === 0) {
      html += '<div class="twin-dim-empty">暂无认知特质。</div>';
    } else {
      html += '<div class="twin-trait-columns">';
      for (const cat of TRAIT_CATEGORIES) {
        const catTraits = traitItems.filter(t => t.category === cat.key);
        html += `<div class="twin-trait-col" style="--cat-color:${cat.color}" data-category="${cat.key}">
          <div class="twin-trait-col-header">
            <span class="twin-trait-col-icon">${cat.icon}</span>
            <span class="twin-trait-col-name">${cat.key}</span>
            <span class="twin-trait-col-count">${catTraits.length}</span>
          </div>`;
        if (catTraits.length === 0) {
          html += '<div class="twin-trait-empty">暂无数据</div>';
        } else {
          for (const t of catTraits.slice(0, 5)) {
            const str = t.strength != null ? Math.round(t.strength * 100) : 0;
            html += `<div class="twin-trait-row">
              <span class="twin-trait-name">${esc(t.name)}</span>
              <span class="twin-trait-bar"><span style="width:${str}%"></span></span>
              <span class="twin-trait-pct">${str}%</span>
            </div>`;
          }
        }
        html += '</div>';
      }
      html += '</div>';
    }
    html += `</div></div></div>`;
    html += '<div class="twin-stage-connector">↓ compiled to</div>';

    // ─── L4: Runtime Pack ───
    const hasData = cardCount > 0 || traitCount > 0;
    const statusClass = hasData ? "ready" : "no-data";
    const statusText = hasData ? "✅ Ready" : "⏳ No data";
    html += `<div class="twin-stage" style="--stage-color:#f59e0b">
      <div class="twin-stage-marker">L4</div>
      <div class="twin-stage-card">
        <div class="twin-stage-header" data-nav="sync">
          <span class="twin-stage-icon">📦</span>
          <span class="twin-stage-title">Runtime Pack</span>
          <span class="twin-stage-cta">Sync to AI →</span>
        </div>
        <div class="twin-stage-body">
          <div class="twin-runtime-panel">
            <span class="twin-runtime-status ${statusClass}">${statusText}</span>
            <span class="twin-runtime-info">${cardCount} cards + ${traitCount} traits → AI 指令文件</span>
          </div>
        </div>
      </div>
    </div>`;

    html += '</div>'; // close .twin-pipeline

    container.innerHTML = html;

    // ─── Click handlers ───
    // Pipeline header pills
    container.querySelectorAll(".twin-ph-node").forEach(el => {
      el.onclick = () => {
        const layer = el.dataset.layer;
        if (layer === "events") loadEventsList();
        else if (layer === "cards") loadCards();
        else if (layer === "traits") loadTraits();
        else if (layer === "runtime") loadRuntimePreview();
      };
    });
    // Stage headers
    container.querySelectorAll(".twin-stage-header").forEach(el => {
      el.onclick = () => {
        const nav = el.dataset.nav;
        if (nav === "events") loadEventsList();
        else if (nav === "cards") loadCards();
        else if (nav === "traits") loadTraits();
        else if (nav === "sync") loadRuntimePreview();
      };
    });
    // Card previews → card detail
    container.querySelectorAll(".twin-card-preview").forEach(el => {
      el.onclick = (e) => { e.stopPropagation(); loadCardDetail(el.dataset.cardId); };
    });
    // Trait columns → trait list by category
    container.querySelectorAll(".twin-trait-col").forEach(el => {
      el.onclick = (e) => { e.stopPropagation(); loadTraits(el.dataset.category); };
    });
  }

  function renderOverviewEmpty() {
    const container = document.getElementById("twin-overview");
    if (!container) return;
    const bar = document.getElementById("twin-stats-bar");
    if (bar) bar.innerHTML = "";
    container.innerHTML = `<div class="twin-empty-state">
      <p>🧠 Distill Yourself (Cognitive Handbook)</p>
      <p>点击 <b>Analyze</b> 开始从对话历史中提取认知模型</p>
      <p style="color:var(--text-muted);font-size:0.85em;margin-top:12px">
        4 阶段流水线：事件提取 → 判断卡蒸馏 → 认知特质归纳 → Runtime 编译
      </p>
    </div>`;
  }

  // ── Events List View ──
  function loadEventsList(signalFilter) {
    let url = "/api/twin/events?limit=200";
    if (signalFilter) url += `&signal_type=${encodeURIComponent(signalFilter)}`;
    fetch(url)
      .then(r => r.json())
      .then(data => renderEventsList(data.events || [], signalFilter))
      .catch(e => console.error("Failed to load events:", e));
  }

  function renderEventsList(items, activeFilter) {
    currentView = "events";
    _showOnlyView("dimension");
    const container = document.getElementById("twin-detail");
    setBreadcrumb([{ label: "Evidence Events", onclick: () => loadEventsList() }]);

    const filters = ["all", "correction", "acceptance", "escalation", "question"];
    let html = `<div class="twin-detail-header" style="--dim-color:#3b82f6">
      <span class="twin-dim-icon">📝</span>
      <span class="twin-detail-title">Evidence Events</span>
      <span class="twin-dim-count">${items.length} 条</span>
    </div>
    <div class="twin-filter-chips">
      ${filters.map(f => `<span class="twin-filter-chip ${(!activeFilter && f === "all") || activeFilter === f ? "active" : ""}" data-filter="${f}">${f}</span>`).join("")}
    </div>
    <div class="twin-detail-list" style="margin-top:12px">`;

    if (items.length === 0) {
      html += '<div class="twin-dim-empty" style="padding:24px">暂无事件。</div>';
    }

    for (const e of items) {
      const sig = e.signal_type || "";
      html += `<div class="twin-episode-card">
        <div class="twin-ep-header">
          <span class="twin-event-dot ${sig}" style="display:inline-block"></span>
          <span class="twin-ep-signal ${sig}">${esc(sig)}</span>
          <span class="twin-ep-domain">${esc(e.domain || "")}</span>
          <span class="twin-ep-date">${esc((e.created_at || "").slice(0, 10))}</span>
        </div>
        <div class="twin-ep-body">
          <div><b>AI:</b> ${esc(truncate(e.ai_action, 120))}</div>
          <div><b>反应:</b> ${esc(truncate(e.user_reaction, 120))}</div>
          ${e.lesson ? `<div><b>教训:</b> ${esc(e.lesson)}</div>` : ""}
        </div>
        ${e.card_id ? `<div style="margin-top:4px"><span class="twin-tag" style="cursor:pointer" data-card-link="${esc(e.card_id)}">🃏 ${esc(e.card_id)}</span></div>` : ""}
      </div>`;
    }

    html += "</div>";
    container.innerHTML = html;

    // Filter chip clicks
    container.querySelectorAll(".twin-filter-chip").forEach(el => {
      el.onclick = () => {
        const f = el.dataset.filter;
        loadEventsList(f === "all" ? undefined : f);
      };
    });
    // Card link clicks
    container.querySelectorAll("[data-card-link]").forEach(el => {
      el.onclick = (e) => { e.stopPropagation(); loadCardDetail(el.dataset.cardLink); };
    });
  }

  // ── Judgment Cards List ──
  function loadCards() {
    fetch("/api/twin/cards?limit=200")
      .then(r => r.json())
      .then(data => renderCards(data.cards || []))
      .catch(e => console.error("Failed to load cards:", e));
  }

  function renderCards(items) {
    currentView = "cards";
    _showOnlyView("dimension");
    const container = document.getElementById("twin-detail");
    setBreadcrumb([{ label: "判断卡", onclick: () => loadCards() }]);

    let html = `<div class="twin-detail-header" style="--dim-color:#1d4ed8">
      <span class="twin-dim-icon">🃏</span>
      <span class="twin-detail-title">判断卡</span>
      <span class="twin-dim-count">${items.length} 条</span>
    </div>
    <div class="twin-detail-list">`;

    if (items.length === 0) {
      html += '<div class="twin-dim-empty" style="padding:24px">暂无数据。点击 Analyze 开始提取。</div>';
    }

    for (const card of items) {
      const conf = card.confidence != null ? Math.round(card.confidence * 100) : null;
      const status = card.status || "";
      const statusClass = status === "confirmed" ? "confirmed" : status === "emerging" ? "emerging" : "hypothesis";
      const tags = tryParseJson(card.tags);

      html += `<div class="twin-detail-item" data-item-id="${esc(card.id)}">
        <div class="twin-item-body">
          <div><b>${esc(card.applies_when)}</b></div>
          <div class="twin-item-sub">${esc(truncate(card.judgment, 150))}</div>
          <div class="twin-item-sub" style="color:var(--accent)">→ ${esc(card.agent_action)}</div>
          ${tags ? `<div class="twin-item-tags">${tags.split(", ").map(t => `<span class="twin-tag">${esc(t)}</span>`).join("")}</div>` : ""}
        </div>
        <div class="twin-item-meta">
          ${status ? `<span class="twin-status-badge ${statusClass}">${status}</span>` : ""}
          ${conf !== null ? `<span class="twin-conf">${conf}%</span>` : ""}
          ${card.evidence_count ? `<span class="twin-ep-count">${card.evidence_count} events</span>` : ""}
        </div>
      </div>`;
    }

    html += "</div>";
    container.innerHTML = html;

    container.querySelectorAll("[data-item-id]").forEach(el => {
      el.onclick = () => loadCardDetail(el.dataset.itemId);
    });
  }

  // ── Card Detail ──
  function loadCardDetail(cardId) {
    fetch(`/api/twin/card/${cardId}`)
      .then(r => r.json())
      .then(data => renderCardDetail(data))
      .catch(e => console.error("Failed to load card detail:", e));
  }

  function renderCardDetail(data) {
    currentView = "card-detail";
    _showOnlyView("item");
    const container = document.getElementById("twin-item-view");
    const card = data.card || {};
    const evidence = data.evidence || [];
    const relations = data.relations || [];
    setBreadcrumb([
      { label: "判断卡", onclick: () => loadCards() },
      { label: card.id || "detail" },
    ]);

    const conf = card.confidence != null ? Math.round(card.confidence * 100) : null;
    const status = card.status || "";
    const tags = tryParseJson(card.tags);

    let html = `<div class="twin-item-detail">
      <div class="twin-item-detail-header" style="border-left:4px solid #1d4ed8">
        <span>🃏 判断卡</span>
        <span class="twin-item-id">${esc(card.id)}</span>
      </div>
      <div class="twin-item-detail-body" style="padding:16px">
        <div style="margin-bottom:12px"><b>触发场景：</b>${esc(card.applies_when)}</div>
        <div style="margin-bottom:12px"><b>用户判断逻辑：</b>${esc(card.judgment)}</div>
        <div style="margin-bottom:12px;color:var(--accent)"><b>AI 行动：</b>${esc(card.agent_action)}</div>
        ${card.exceptions ? `<div style="margin-bottom:12px"><b>例外：</b>${esc(card.exceptions)}</div>` : ""}
        <div class="twin-item-meta">
          ${status ? `<span class="twin-status-badge ${status === "confirmed" ? "confirmed" : status === "emerging" ? "emerging" : "hypothesis"}">${status}</span>` : ""}
          ${conf !== null ? `<span class="twin-conf">${conf}%</span>` : ""}
          ${card.evidence_count ? `<span class="twin-ep-count">${card.evidence_count} events</span>` : ""}
          ${tags ? tags.split(", ").map(t => `<span class="twin-tag">${esc(t)}</span>`).join("") : ""}
        </div>
      </div>`;

    if (evidence.length) {
      html += `<div class="twin-trace-section">
        <h4>📎 支撑事件 (${evidence.length})</h4>`;
      for (const ep of evidence) {
        html += `<div class="twin-episode-card">
          <div class="twin-ep-header">
            <span class="twin-ep-signal ${ep.signal_type || ""}">${esc(ep.signal_type)}</span>
            <span class="twin-ep-domain">${esc(ep.domain)}</span>
            <span class="twin-ep-date">${esc((ep.created_at || "").slice(0, 10))}</span>
          </div>
          <div class="twin-ep-body">
            <div><b>AI:</b> ${esc(truncate(ep.ai_action, 120))}</div>
            <div><b>反应:</b> ${esc(truncate(ep.user_reaction, 120))}</div>
            ${ep.lesson ? `<div><b>教训:</b> ${esc(ep.lesson)}</div>` : ""}
          </div>
          ${ep.session_id ? `<a class="twin-ep-link" onclick="window.openSession && window.openSession('${esc(ep.session_id)}')">查看原始会话 →</a>` : ""}
        </div>`;
      }
      html += "</div>";
    }

    if (relations.length) {
      html += `<div class="twin-trace-section">
        <h4>🔗 关联卡片 (${relations.length})</h4>`;
      for (const rel of relations) {
        const other = rel.from_id === card.id ? rel.to_id : rel.from_id;
        html += `<div class="twin-dim-item" style="cursor:pointer" onclick="window._loadCardDetail && window._loadCardDetail('${esc(other)}')">
          <span class="twin-tag">${esc(rel.relation)}</span> ${esc(other)}
        </div>`;
      }
      html += "</div>";
    }

    html += "</div>";
    container.innerHTML = html;
  }
  window._loadCardDetail = loadCardDetail;

  // ── Cognitive Traits List ──
  function loadTraits(category) {
    let url = "/api/twin/traits?limit=200";
    if (category) url += `&category=${encodeURIComponent(category)}`;
    fetch(url)
      .then(r => r.json())
      .then(data => renderTraits(data.traits || [], category))
      .catch(e => console.error("Failed to load traits:", e));
  }

  function renderTraits(items, category) {
    currentView = "traits";
    _showOnlyView("dimension");
    const container = document.getElementById("twin-detail");
    const title = category || "全部认知特质";
    setBreadcrumb([{ label: title, onclick: () => loadTraits(category) }]);

    const cat = TRAIT_CATEGORIES.find(c => c.key === category) || { icon: "🧬", color: "#7c3aed" };

    let html = `<div class="twin-detail-header" style="--dim-color:${cat.color}">
      <span class="twin-dim-icon">${cat.icon}</span>
      <span class="twin-detail-title">${title}</span>
      <span class="twin-dim-count">${items.length} 条</span>
    </div>
    <div class="twin-detail-list">`;

    if (items.length === 0) {
      html += '<div class="twin-dim-empty" style="padding:24px">暂无数据。点击 Analyze 开始提取。</div>';
    }

    for (const t of items) {
      const str = t.strength != null ? Math.round(t.strength * 100) : null;
      const status = t.status || "";
      const statusClass = status === "confirmed" ? "confirmed" : status === "emerging" ? "emerging" : "hypothesis";

      html += `<div class="twin-detail-item" data-item-id="${esc(t.id)}">
        <div class="twin-item-body">
          <div><b>${esc(t.name)}</b> <span class="twin-tag">${esc(t.category)}</span></div>
          <div class="twin-item-sub">${esc(t.description)}</div>
        </div>
        <div class="twin-item-meta">
          ${status ? `<span class="twin-status-badge ${statusClass}">${status}</span>` : ""}
          ${str !== null ? `<span class="twin-conf">${str}%</span>` : ""}
          ${t.evidence_count ? `<span class="twin-ep-count">${t.evidence_count} events</span>` : ""}
        </div>
      </div>`;
    }

    html += "</div>";
    container.innerHTML = html;

    container.querySelectorAll("[data-item-id]").forEach(el => {
      el.onclick = () => loadTraitDetail(el.dataset.itemId);
    });
  }

  // ── Trait Detail ──
  function loadTraitDetail(traitId) {
    fetch(`/api/twin/trait/${traitId}`)
      .then(r => r.json())
      .then(data => renderTraitDetail(data))
      .catch(e => console.error("Failed to load trait detail:", e));
  }

  function renderTraitDetail(data) {
    currentView = "trait-detail";
    _showOnlyView("item");
    const container = document.getElementById("twin-item-view");
    const trait = data.trait || {};
    const cards = data.supporting_cards || [];
    const cat = TRAIT_CATEGORIES.find(c => c.key === trait.category) || { icon: "🧬", color: "#7c3aed" };
    setBreadcrumb([
      { label: trait.category || "特质", onclick: () => loadTraits(trait.category) },
      { label: trait.name || "detail" },
    ]);

    const str = trait.strength != null ? Math.round(trait.strength * 100) : null;
    const status = trait.status || "";

    let html = `<div class="twin-item-detail">
      <div class="twin-item-detail-header" style="border-left:4px solid ${cat.color}">
        <span>${cat.icon} ${esc(trait.category)}</span>
        <span class="twin-item-id">${esc(trait.id)}</span>
      </div>
      <div class="twin-item-detail-body" style="padding:16px">
        <div style="margin-bottom:12px;font-size:1.1em"><b>${esc(trait.name)}</b></div>
        <div style="margin-bottom:12px">${esc(trait.description)}</div>
        <div class="twin-item-meta">
          ${status ? `<span class="twin-status-badge ${status === "confirmed" ? "confirmed" : status === "emerging" ? "emerging" : "hypothesis"}">${status}</span>` : ""}
          ${str !== null ? `<span class="twin-conf">${str}%</span>` : ""}
          ${trait.evidence_count ? `<span class="twin-ep-count">${trait.evidence_count} events</span>` : ""}
        </div>
      </div>`;

    if (cards.length) {
      html += `<div class="twin-trace-section">
        <h4>🃏 支撑判断卡 (${cards.length})</h4>`;
      for (const c of cards) {
        html += `<div class="twin-episode-card" style="cursor:pointer" onclick="window._loadCardDetail && window._loadCardDetail('${esc(c.id)}')">
          <div class="twin-ep-header">
            <span class="twin-ep-domain">${esc(c.applies_when)}</span>
            ${c.confidence != null ? `<span class="twin-conf">${Math.round(c.confidence * 100)}%</span>` : ""}
          </div>
          <div class="twin-ep-body">
            <div>${esc(truncate(c.judgment, 120))}</div>
          </div>
        </div>`;
      }
      html += "</div>";
    }

    html += "</div>";
    container.innerHTML = html;
  }

  // ══════════════════════════════════════════════════════════════════
  // ── Analysis (SSE streaming with rich UI — mirrors evolve.js) ──
  // ══════════════════════════════════════════════════════════════════

  function startAnalysis() {
    if (analysisRunning) return; // prevent double-start
    analysisRunning = true;
    _updateAnalyzeButton();

    const updatedEl = document.getElementById("twin-last-analyzed");
    if (updatedEl) { updatedEl.textContent = "AI 启动中…"; }

    // Switch to analysis view
    currentView = "analyzing";
    _showOnlyView("analysis");
    setBreadcrumb([{ label: "分析中…" }]);

    const progress = show("twin-analysis-progress");
    if (progress) {
      progress.innerHTML = `<div class="twin-stream-container" id="twin-stream-output">
        <div class="evolve-thinking">
          <span class="evolve-thinking-dot"></span>
          <span class="evolve-thinking-dot"></span>
          <span class="evolve-thinking-dot"></span>
          <span class="evolve-thinking-label">AI 启动中…</span>
        </div>
      </div>`;
    }

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
    };

    // Abort previous if any
    if (analysisAbort) analysisAbort.abort();
    const abortCtrl = new AbortController();
    analysisAbort = abortCtrl;

    fetch("/api/twin/analyze", { method: "POST", signal: abortCtrl.signal })
      .then((response) => {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        function pump() {
          return reader.read().then(({ done, value }) => {
            if (done) {
              _finishAnalysis(streamState);
              return;
            }
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split("\n\n");
            buffer = parts.pop();
            for (const part of parts) {
              const lines = part.split("\n");
              for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                try {
                  const evt = JSON.parse(line.slice(6));
                  _handleStreamEvent(evt, streamState);
                } catch (e) { /* skip */ }
              }
            }
            // Also handle single \n separated events (server may not double-newline)
            const singleLines = buffer.split("\n");
            buffer = singleLines.pop() || "";
            for (const line of singleLines) {
              if (!line.startsWith("data: ")) continue;
              try {
                const evt = JSON.parse(line.slice(6));
                _handleStreamEvent(evt, streamState);
              } catch (e) { /* skip */ }
            }
            return pump();
          });
        }
        return pump();
      })
      .catch((e) => {
        if (e.name === "AbortError") { analysisRunning = false; _updateAnalyzeButton(); return; }
        const container = document.getElementById("twin-stream-output");
        if (container) {
          _hideThinking(container);
          const errDiv = document.createElement("div");
          errDiv.className = "twin-stream-error";
          errDiv.textContent = `❌ ${String(e)}`;
          container.appendChild(errDiv);
        }
        _finishAnalysis(streamState);
      })
      .finally(() => { analysisAbort = null; });
  }

  function _finishAnalysis(state) {
    analysisRunning = false;
    _finalizeToolGroup(state);
    _updateAnalyzeButton();
    const updatedEl = document.getElementById("twin-last-analyzed");
    if (updatedEl) { updatedEl.textContent = `Updated ${new Date().toLocaleTimeString()}`; }
    // If user is still watching the analysis, switch to overview
    if (currentView === "analyzing") {
      setBreadcrumb([{ label: "分析完成 ✅" }]);
      setTimeout(() => loadOverview(), 1500);
    }
  }

  /** Handle a single SSE event — renders tool cards, text blocks, thinking dots */
  function _handleStreamEvent(evt, state) {
    const container = document.getElementById("twin-stream-output");
    const updatedEl = document.getElementById("twin-last-analyzed");
    if (!container) return;

    switch (evt.type) {
      case "tool": {
        if (evt.status === "running") {
          state.textBlock = null;
          state.blockText = "";
          _hideThinking(container);

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
          card.innerHTML = `<div class="tool-card-header">
            <span class="tool-status-dot"></span>
            <span class="tool-card-name">${esc(evt.name)}</span>
            <span class="tool-card-detail">${detail}</span>
            <span class="tool-card-chevron">›</span>
          </div>
          <div class="tool-card-body">
            <div class="tool-card-cmd"></div>
            <pre class="tool-card-output"></pre>
          </div>`;

          // Agent cards: show prompt
          if (evt.name === "Agent" && evt.prompt) {
            const cmdEl = card.querySelector(".tool-card-cmd");
            if (cmdEl) { cmdEl.textContent = evt.prompt; cmdEl.classList.add("agent-prompt"); }
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
        if (updatedEl) {
          updatedEl.textContent = `AI 执行中… (${state.stepCount} steps)`;
          updatedEl.classList.add("loading");
        }
        _autoScroll();
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
        state.textBlock.innerHTML = window.renderMarkdownSimple
          ? window.renderMarkdownSimple(state.blockText)
          : `<pre>${esc(state.blockText)}</pre>`;
        _showThinking(container);
        _autoScroll();
        break;

      case "result":
        _finalizeToolGroup(state);
        _hideThinking(container);
        state.blockText = evt.content;
        if (!state.textBlock) {
          state.textBlock = document.createElement("div");
          state.textBlock.className = "text-block";
          container.appendChild(state.textBlock);
        }
        state.textBlock.innerHTML = window.renderMarkdownSimple
          ? window.renderMarkdownSimple(evt.content)
          : `<pre>${esc(evt.content)}</pre>`;
        _autoScroll();
        break;

      case "done":
        _finalizeToolGroup(state);
        _hideThinking(container);
        if (updatedEl) {
          updatedEl.textContent = `Updated ${new Date().toLocaleTimeString()}`;
          updatedEl.classList.remove("loading");
        }
        break;

      case "error":
        _finalizeToolGroup(state);
        _hideThinking(container);
        const errDiv = document.createElement("div");
        errDiv.className = "twin-stream-error";
        errDiv.innerHTML = `❌ ${esc(evt.message || "Unknown error")}`;
        container.appendChild(errDiv);
        if (updatedEl) {
          updatedEl.textContent = `Error: ${evt.message || ""}`;
          updatedEl.classList.remove("loading");
        }
        _autoScroll();
        break;
    }
  }

  // ── Streaming UI helpers (mirroring evolve.js) ──

  function _createToolGroup(parentContainer) {
    const group = document.createElement("div");
    group.className = "evolve-tool-group expanded running";
    group.innerHTML = `<div class="evolve-tg-header">
      <span class="evolve-tg-dot"></span>
      <span class="evolve-tg-summary"></span>
      <span class="evolve-tg-chevron">›</span>
    </div>
    <div class="evolve-tg-body"></div>`;
    group.querySelector(".evolve-tg-header").onclick = () => group.classList.toggle("expanded");
    parentContainer.appendChild(group);
    return group;
  }

  function _updateToolGroupHeader(state) {
    const group = state.currentToolGroup;
    if (!group) return;
    const el = group.querySelector(".evolve-tg-summary");
    if (!el) return;
    const parts = Object.entries(state.toolGroupCounts).map(([name, count]) => `${count} ${name}`);
    el.innerHTML = `<span class="evolve-tg-count">⚡ ${state.toolGroupTotal} tools</span> · ${parts.join(" · ")}`;
  }

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

  function _showThinking(container) {
    _hideThinking(container);
    const el = document.createElement("div");
    el.className = "evolve-thinking";
    el.innerHTML = '<span class="evolve-thinking-dot"></span><span class="evolve-thinking-dot"></span><span class="evolve-thinking-dot"></span><span class="evolve-thinking-label">AI 分析生成中…</span>';
    container.appendChild(el);
  }

  function _hideThinking(container) {
    const el = container && container.querySelector(".evolve-thinking");
    if (el) el.remove();
  }

  function _autoScroll() {
    const scrollEl = document.getElementById("twin-body");
    if (!scrollEl) return;
    if (scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight < 80) {
      scrollEl.scrollTop = scrollEl.scrollHeight;
    }
  }

  // ── Runtime Preview ──
  function loadRuntimePreview() {
    fetch("/api/twin/runtime-preview")
      .then(r => r.json())
      .then(data => renderRuntimePreview(data))
      .catch(e => console.error("Failed to load runtime preview:", e));
  }

  function renderRuntimePreview(data) {
    currentView = "runtime";
    _showOnlyView("dimension");
    const container = document.getElementById("twin-detail");
    setBreadcrumb([{ label: "Runtime Pack", onclick: () => loadRuntimePreview() }]);

    const text = data.text || "(empty)";
    const cardCount = data.card_count || 0;
    const traitCount = data.trait_count || 0;
    const hasData = cardCount > 0 || traitCount > 0;

    let html = `<div class="twin-detail-header" style="--dim-color:#f59e0b">
      <span class="twin-dim-icon">📦</span>
      <span class="twin-detail-title">Runtime Pack</span>
      <span class="twin-dim-count">${cardCount} cards + ${traitCount} traits</span>
    </div>
    <div style="margin-bottom:16px;display:flex;align-items:center;gap:12px">
      <span class="twin-runtime-status ${hasData ? "ready" : "no-data"}">${hasData ? "✅ Ready to sync" : "⏳ No data"}</span>
      <span style="font-size:12px;color:var(--text-muted)">以下内容将写入 AI 指令文件，AI 在下次会话时自动读取</span>
    </div>
    <div style="padding:16px;background:var(--bg-primary);border:1px solid var(--border-light);border-radius:var(--radius);font-size:13px;line-height:1.8;white-space:pre-wrap;color:var(--text);max-height:60vh;overflow-y:auto">${window.renderMarkdownSimple ? window.renderMarkdownSimple(text) : esc(text)}</div>`;

    if (hasData) {
      html += `<div style="margin-top:16px;text-align:right">
        <button class="btn-text" id="twin-runtime-sync-btn" style="font-size:13px;padding:6px 16px;background:var(--accent);color:white;border-radius:var(--radius-sm);border:none;cursor:pointer">📤 Sync to CLAUDE.md</button>
      </div>`;
    }

    container.innerHTML = html;

    const syncBtn = document.getElementById("twin-runtime-sync-btn");
    if (syncBtn) syncBtn.onclick = startSync;
  }

  // ── Sync ──
  function startSync() {
    if (!confirm("将Distill Yourself同步到 CLAUDE.md？")) return;
    fetch("/api/twin/sync", { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          alert(`同步完成：${data.cards_synced || 0} 判断卡 + ${data.traits_synced || 0} 认知特质已写入`);
        } else {
          alert("同步失败：" + (data.error || "unknown"));
        }
      })
      .catch((e) => alert("Sync failed: " + e));
  }

  // ── Navigation helpers ──
  function setBreadcrumb(parts) {
    const bc = document.getElementById("twin-breadcrumb");
    if (!bc) return;
    let html = `<span class="twin-bc-root" onclick="window.initTwinView && window.initTwinView()">Distill Yourself</span>`;
    for (const p of parts) {
      html += ` <span class="twin-bc-sep">›</span> `;
      if (p.onclick) {
        html += `<span class="twin-bc-link">${esc(p.label)}</span>`;
      } else {
        html += `<span class="twin-bc-current">${esc(p.label)}</span>`;
      }
    }
    bc.innerHTML = html;
    const links = bc.querySelectorAll(".twin-bc-link");
    links.forEach((link, i) => {
      if (parts[i] && parts[i].onclick) {
        link.onclick = parts[i].onclick;
      }
    });
  }

  function show(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove("hidden");
    return el;
  }

  function hide(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add("hidden");
    return el;
  }

  function truncate(s, n) {
    if (!s) return "";
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  function tryParseJson(s) {
    if (!s) return "";
    try {
      const arr = JSON.parse(s);
      return Array.isArray(arr) ? arr.join(", ") : String(s);
    } catch {
      return String(s);
    }
  }
})();
