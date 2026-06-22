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
  let activeSimulation = null;
  let evolveScopeSource = "all";
  let evolveScopeDate = "7d";
  let evolveScopeProject = "";

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

    // Sync button
    const syncBtn = $("#evolve-tab-sync");
    if (syncBtn) syncBtn.onclick = () => toggleSyncPanel();
  }

  function switchEvolveTab(tab) {
    evolveActiveTab = tab;
    $$(".evolve-tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tab));
    renderEvolveTabContent(tab);
    updateEvolveOverviewBar();
    updateSyncButtonState();
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
    updateSyncButtonState();
  }

  // ── Scope (reads from shared global state set by initAiPage in app.js) ──
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

  // ── Tab content rendering ──
  function renderEvolveTabContent(tab) {
    const body = $("#evolve-tab-body");
    const updatedEl = $("#evolve-tab-updated");
    if (!body) return;

    const cached = getCachedTab(tab);
    if (cached && cached.data) {
      if (updatedEl) updatedEl.textContent = `Updated: ${timeAgo(cached.updatedAt)}`;
      if (activeSimulation) { activeSimulation.stop(); activeSimulation = null; }
      body.innerHTML = "";
      // Show backend error if present
      if (cached.data._error) {
        body.innerHTML = `<div class="evolve-empty-state"><p>分析失败：${(window.esc || String)(cached.data._error)}</p><p>点击 🔄 Refresh 重试</p></div>`;
        return;
      }
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

  // ── API call for analysis (unified: all tabs go through /api/evolve/{tab}) ──
  // AI tabs (profile, memory) may take longer since they run Codex on the backend
  const AI_TABS = new Set(["profile", "memory"]);

  function _fetchEvolveTab(tab) {
    const scope = getEvolveScope();
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
      return _fetchEvolveTabStream(tab, params);
    }

    return fetch(`/api/evolve/${tab}?${params}`)
      .then(r => r.json())
      .then(data => {
        const normalized = normalizeEvolveData(tab, data);
        setCachedTab(tab, normalized);
        if (tab === evolveActiveTab) renderEvolveTabContent(tab);
        updateEvolveOverviewBar();
      });
  }

  /** Stream SSE events for AI evolve tabs with live progress */
  function _fetchEvolveTabStream(tab, params) {
    const body = $("#evolve-tab-body");
    const updatedEl = $("#evolve-tab-updated");
    const esc = window.esc || String;

    // Show streaming progress UI using tool-card / text-block components
    if (body) {
      body.innerHTML = '<div class="evolve-stream-progress" id="evolve-stream-container"></div>';
    }
    if (updatedEl) updatedEl.textContent = "AI 启动中…";

    const streamState = { blockText: "", textBlock: null, runningCard: null, stepCount: 0 };

    return fetch(`/api/evolve/${tab}?${params}`)
      .then(response => {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        function pump() {
          return reader.read().then(({done, value}) => {
            if (done) return;
            buffer += decoder.decode(value, {stream: true});
            const parts = buffer.split("\n\n");
            buffer = parts.pop();
            for (const part of parts) {
              const lines = part.split("\n");
              for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                try {
                  const evt = JSON.parse(line.slice(6));
                  _handleEvolveStreamEvent(evt, tab, streamState);
                } catch (e) { /* skip */ }
              }
            }
            return pump();
          });
        }
        return pump();
      });
  }

  function _handleEvolveStreamEvent(evt, tab, state) {
    const container = document.getElementById("evolve-stream-container");
    const updatedEl = $("#evolve-tab-updated");
    const esc = window.esc || String;
    if (!container) return;

    switch (evt.type) {
      case "tool": {
        if (evt.status === "running") {
          state.textBlock = null;
          state.blockText = "";
          const card = document.createElement("div");
          card.className = "tool-card running";
          const detail = evt.detail ? esc(evt.detail) : "";
          card.innerHTML = `<div class="tool-card-header"><span class="tool-status-dot"></span><span class="tool-card-name">${esc(evt.name)}</span><span class="tool-card-detail">${detail}</span><span class="tool-card-chevron">›</span></div><div class="tool-card-body"><pre class="tool-card-output"></pre></div>`;
          container.appendChild(card);
          state.runningCard = card;
          state.stepCount++;
        } else if (evt.status === "done" && state.runningCard) {
          state.runningCard.classList.remove("running");
          state.runningCard.classList.add("done");
          if (evt.detail) {
            const outputEl = state.runningCard.querySelector(".tool-card-output");
            if (outputEl) outputEl.textContent = evt.detail;
          }
          const rc = state.runningCard;
          const header = rc.querySelector(".tool-card-header");
          if (header) header.onclick = () => rc.classList.toggle("expanded");
          state.runningCard = null;
        }
        if (updatedEl) updatedEl.textContent = `AI 执行中… (${state.stepCount} steps)`;
        break;
      }
      case "text":
        state.blockText += evt.content;
        if (!state.textBlock) {
          state.textBlock = document.createElement("div");
          state.textBlock.className = "text-block";
          container.appendChild(state.textBlock);
        }
        state.textBlock.innerHTML = window.renderMarkdownSimple
          ? window.renderMarkdownSimple(state.blockText)
          : `<pre>${esc(state.blockText)}</pre>`;
        break;
      case "result":
        state.blockText = evt.content;
        if (!state.textBlock) {
          state.textBlock = document.createElement("div");
          state.textBlock.className = "text-block";
          container.appendChild(state.textBlock);
        }
        state.textBlock.innerHTML = window.renderMarkdownSimple
          ? window.renderMarkdownSimple(evt.content)
          : `<pre>${esc(evt.content)}</pre>`;
        break;
      case "evolve_result": {
        const normalized = normalizeEvolveData(tab, evt.data);
        setCachedTab(tab, normalized);
        if (tab === evolveActiveTab) renderEvolveTabContent(tab);
        updateEvolveOverviewBar();
        if (updatedEl) updatedEl.textContent = `Updated ${new Date().toLocaleTimeString()}`;
        break;
      }
      case "done":
        if (updatedEl) updatedEl.textContent = `Updated ${new Date().toLocaleTimeString()}`;
        break;
      case "error":
        if (updatedEl) updatedEl.textContent = `Error: ${evt.message}`;
        const body = $("#evolve-tab-body");
        if (body) body.innerHTML = `<div class="evolve-empty-state"><p>分析失败：${esc(evt.message)}</p></div>`;
        break;
    }
  }

  function refreshEvolveTab(tab) {
    if (evolveLoading) return;
    evolveLoading = true;
    const body = $("#evolve-tab-body");
    const updatedEl = $("#evolve-tab-updated");
    const isAI = AI_TABS.has(tab);
    if (!isAI) {
      if (body) body.innerHTML = `<div class="evolve-skeleton"><div class="skeleton-bar"></div><div class="skeleton-bar short"></div><div class="skeleton-bar"></div><div class="skeleton-circle"></div></div>`;
      if (updatedEl) updatedEl.textContent = "分析中…";
    }

    _fetchEvolveTab(tab)
      .catch(err => {
        if (body) body.innerHTML = `<div class="evolve-empty-state"><p>分析失败：${(window.esc || String)(err.message)}</p></div>`;
      })
      .finally(() => { evolveLoading = false; });
  }

  function refreshAllEvolveTabs() {
    const tabs = ["profile", "memory", "rules", "signals", "patterns"];
    let idx = 0;
    function doNext() {
      if (idx >= tabs.length) return;
      const tab = tabs[idx++];
      switchEvolveTab(tab);

      _fetchEvolveTab(tab)
        .catch(() => {})
        .finally(() => { setTimeout(doNext, 300); });
    }
    doNext();
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
          c.items.forEach(item => { if (typeof item === "string") item = { text: item }; });
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
        const target = [...listDiv.querySelectorAll(".evolve-memory-card")].find(c => c.dataset.id === nodeId);
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

    const nodeIds = new Set(nodes.map(n => n.id));
    const validLinks = links.filter(l => nodeIds.has(l.source) && nodeIds.has(l.target));

    const pad = 20;
    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(validLinks).id(d => d.id).distance(50).strength(d => d.strength || 0.5))
      .force("charge", d3.forceManyBody().strength(-40))
      .force("x", d3.forceX(width / 2).strength(0.15))
      .force("y", d3.forceY(height / 2).strength(0.15))
      .force("collision", d3.forceCollide().radius(d => Math.sqrt(d.frequency || 1) * 4 + 6));

    activeSimulation = simulation;

    const link = svg.append("g").selectAll("line")
      .data(validLinks).enter().append("line")
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
      nodes.forEach(d => {
        d.x = Math.max(pad, Math.min(width - pad, d.x));
        d.y = Math.max(pad, Math.min(height - pad, d.y));
      });
      link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
      node.attr("transform", d => `translate(${d.x},${d.y})`);
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
      body: JSON.stringify({action: "preview", targets})
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
      body: JSON.stringify({action: "execute", targets})
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

  window.navigateToEvolveTab = function (tab, data) {
    if (data) setCachedTab(tab, data);
    switchEvolveTab(tab);
    updateEvolveOverviewBar();
  };

  window.parseEvolveResponseExternal = function (tab, raw) {
    return parseEvolveResponse(tab, raw);
  };

})();
