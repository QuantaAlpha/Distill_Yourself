/**
 * Digital Twin — Cognitive Model UI
 * Wiki-style navigation: Overview → Dimension detail → Item trace
 */
(function () {
  "use strict";

  const DIMENSIONS = [
    { key: "tensions",      table: "cm_tensions",      icon: "⚖️", label: "价值层级",   color: "#0f766e" },
    { key: "principles",    table: "cm_principles",    icon: "🔗", label: "因果原则",   color: "#1d4ed8" },
    { key: "tradeoffs",     table: "cm_tradeoffs",     icon: "🎯", label: "权衡矩阵",   color: "#9d174d" },
    { key: "reasoning",     table: "cm_reasoning",     icon: "🧠", label: "推理风格",   color: "#854d0e" },
    { key: "communication", table: "cm_communication", icon: "📋", label: "沟通契约",   color: "#7c3aed" },
    { key: "roles",         table: "cm_roles",         icon: "🎭", label: "角色模式",   color: "#c2410c" },
    { key: "expertise",     table: "cm_expertise",     icon: "📊", label: "领域图谱",   color: "#0369a1" },
  ];

  const esc = (s) => {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
  };

  // ── State ──
  let overviewData = null;

  // ── Init ──
  window.initTwinView = function () {
    bindEvents();
    loadOverview();
  };

  function bindEvents() {
    const btnAnalyze = document.getElementById("twin-btn-analyze");
    const btnSync = document.getElementById("twin-btn-sync");
    if (btnAnalyze) btnAnalyze.onclick = startAnalysis;
    if (btnSync) btnSync.onclick = startSync;
  }

  // ── Overview ──
  function loadOverview() {
    fetch("/api/twin/overview")
      .then((r) => r.json())
      .then((data) => {
        overviewData = data;
        renderOverview(data);
      })
      .catch(() => renderOverviewEmpty());
  }

  function renderOverview(data) {
    const container = document.getElementById("twin-overview");
    if (!container) return;

    // Show overview, hide others
    container.classList.remove("hidden");
    hide("twin-detail");
    hide("twin-policies-view");
    hide("twin-item-view");
    setBreadcrumb([]);

    let html = '<div class="twin-cards-grid">';

    for (const dim of DIMENSIONS) {
      const info = data[dim.key] || { count: 0, items: [] };
      const count = info.count || 0;
      const items = info.items || [];

      html += `<div class="twin-dim-card" data-dim="${dim.key}" style="--dim-color:${dim.color}">
        <div class="twin-dim-header">
          <span class="twin-dim-icon">${dim.icon}</span>
          <span class="twin-dim-label">${dim.label}</span>
          <span class="twin-dim-count">${count}</span>
        </div>
        <div class="twin-dim-preview">`;

      if (items.length === 0) {
        html += '<div class="twin-dim-empty">暂无数据</div>';
      } else {
        for (const item of items.slice(0, 3)) {
          const text = itemPreviewText(dim.key, item);
          const conf = item.confidence != null ? Math.round(item.confidence * 100) : null;
          html += `<div class="twin-dim-item">
            <span class="twin-dim-item-text">${esc(text)}</span>
            ${conf !== null ? `<span class="twin-dim-item-conf">${conf}%</span>` : ""}
          </div>`;
        }
      }

      html += `</div></div>`;
    }

    // Policies card
    const polInfo = data.policies || { count: 0, items: [] };
    html += `<div class="twin-dim-card twin-policies-card" data-dim="policies" style="--dim-color:#1e293b">
      <div class="twin-dim-header">
        <span class="twin-dim-icon">⚡</span>
        <span class="twin-dim-label">执行策略</span>
        <span class="twin-dim-count">${polInfo.count || 0}</span>
      </div>
      <div class="twin-dim-preview">`;
    for (const p of (polInfo.items || []).slice(0, 3)) {
      html += `<div class="twin-dim-item">
        <span class="twin-dim-item-text">${esc(p.condition || p.action || "")}</span>
        ${p.confidence != null ? `<span class="twin-dim-item-conf">${Math.round(p.confidence * 100)}%</span>` : ""}
      </div>`;
    }
    if (!polInfo.items?.length) html += '<div class="twin-dim-empty">暂无数据</div>';
    html += `</div></div>`;

    html += "</div>";
    container.innerHTML = html;

    // Card click → drill into dimension
    container.querySelectorAll(".twin-dim-card").forEach((card) => {
      card.onclick = () => {
        const dim = card.dataset.dim;
        if (dim === "policies") {
          loadPolicies();
        } else {
          loadDimension(dim);
        }
      };
    });
  }

  function renderOverviewEmpty() {
    const container = document.getElementById("twin-overview");
    if (!container) return;
    container.innerHTML = `<div class="twin-empty-state">
      <p>🧠 Digital Twin 认知模型</p>
      <p>点击 <b>Analyze</b> 开始从对话历史中提取认知模型</p>
      <p style="color:var(--text-muted);font-size:0.85em;margin-top:12px">
        或使用 CLI：<code>python3 analyze.py twin-stats</code>
      </p>
    </div>`;
  }

  function itemPreviewText(dimKey, item) {
    switch (dimKey) {
      case "tensions": return `${item.value_a || ""} vs ${item.value_b || ""}`;
      case "principles": return item.statement || "";
      case "tradeoffs": return item.context || "";
      case "reasoning": return `${item.dimension || ""}: ${item.description || ""}`;
      case "communication": return `[${item.category || ""}] ${item.description || ""}`;
      case "roles": return `${item.role || ""}: ${item.behavior_profile || ""}`;
      case "expertise": return `${item.domain || ""} (${item.depth || ""})`;
      default: return JSON.stringify(item).slice(0, 60);
    }
  }

  // ── Dimension Detail ──
  function loadDimension(dimKey) {
    const dim = DIMENSIONS.find((d) => d.key === dimKey);
    if (!dim) return;

    fetch(`/api/twin/dimension/${dimKey}?limit=200`)
      .then((r) => r.json())
      .then((data) => renderDimension(dim, data.items || data))
      .catch((e) => console.error("Failed to load dimension:", e));
  }

  function renderDimension(dim, items) {
    hide("twin-overview");
    hide("twin-policies-view");
    hide("twin-item-view");
    const container = show("twin-detail");
    setBreadcrumb([{ label: dim.label, onclick: () => loadDimension(dim.key) }]);

    let html = `<div class="twin-detail-header" style="--dim-color:${dim.color}">
      <span class="twin-dim-icon">${dim.icon}</span>
      <span class="twin-detail-title">${dim.label}</span>
      <span class="twin-dim-count">${items.length} 条</span>
    </div>
    <div class="twin-detail-list">`;

    if (items.length === 0) {
      html += '<div class="twin-dim-empty" style="padding:24px">暂无数据。点击 Analyze 开始提取。</div>';
    }

    for (const item of items) {
      html += renderDimensionItem(dim.key, item);
    }

    html += "</div>";
    container.innerHTML = html;

    // Item click → load detail with trace
    container.querySelectorAll("[data-item-id]").forEach((el) => {
      el.onclick = () => loadItemDetail(dim.key, el.dataset.itemId);
    });
  }

  function renderDimensionItem(dimKey, item) {
    const conf = item.confidence != null ? Math.round(item.confidence * 100) : null;
    const status = item.status || "";
    const statusClass = status === "confirmed" ? "confirmed" : status === "emerging" ? "emerging" : "hypothesis";

    let body = "";
    switch (dimKey) {
      case "tensions":
        body = `<b>${esc(item.value_a)}</b> vs <b>${esc(item.value_b)}</b>
          <div class="twin-item-sub">默认：${esc(item.default_resolution)}</div>`;
        break;
      case "principles":
        body = `<div>${esc(item.statement)}</div>
          <div class="twin-item-sub">因：${esc(item.cause)} → 果：${esc(item.effect)}</div>`;
        break;
      case "tradeoffs":
        body = `<div>场景：${esc(item.context)}</div>
          <div class="twin-item-sub">保护：${esc(tryParseJson(item.protect))} | 牺牲：${esc(tryParseJson(item.sacrifice))}</div>`;
        break;
      case "reasoning":
        body = `<b>${esc(item.dimension)}</b>: ${esc(item.description)}`;
        break;
      case "communication":
        body = `<span class="twin-cat-badge ${item.category}">${esc(item.category)}</span> ${esc(item.description)}`;
        break;
      case "roles":
        body = `<b>${esc(item.role)}</b>: ${esc(item.behavior_profile)}
          <div class="twin-item-sub">自主性: ${esc(item.autonomy_level)}</div>`;
        break;
      case "expertise":
        body = `<b>${esc(item.domain)}</b> — ${esc(item.depth)}
          <div class="twin-item-sub">${esc(item.autonomy_boundary || "")}</div>`;
        break;
    }

    return `<div class="twin-detail-item" data-item-id="${esc(item.id)}">
      <div class="twin-item-body">${body}</div>
      <div class="twin-item-meta">
        ${status ? `<span class="twin-status-badge ${statusClass}">${status}</span>` : ""}
        ${conf !== null ? `<span class="twin-conf">${conf}%</span>` : ""}
        ${item.episode_count ? `<span class="twin-ep-count">${item.episode_count} episodes</span>` : ""}
      </div>
    </div>`;
  }

  // ── Item Detail + Trace ──
  function loadItemDetail(dimKey, itemId) {
    const typeMap = {
      tensions: "tension", principles: "principle", tradeoffs: "tradeoff",
      reasoning: "reasoning", communication: "communication",
      roles: "role", expertise: "expertise",
    };
    const type = typeMap[dimKey] || dimKey;
    fetch(`/api/twin/item/${type}/${itemId}`)
      .then((r) => r.json())
      .then((data) => renderItemDetail(dimKey, data))
      .catch((e) => console.error("Failed to load item detail:", e));
  }

  function renderItemDetail(dimKey, data) {
    const dim = DIMENSIONS.find((d) => d.key === dimKey);
    hide("twin-overview");
    hide("twin-policies-view");
    const detailContainer = show("twin-detail");
    const container = show("twin-item-view");
    setBreadcrumb([
      { label: dim.label, onclick: () => loadDimension(dim.key) },
      { label: data.item?.id || "detail" },
    ]);

    // Hide the list, show item view
    detailContainer.classList.add("hidden");

    const item = data.item || {};
    const episodes = data.episodes || [];

    let html = `<div class="twin-item-detail">
      <div class="twin-item-detail-header" style="border-left:4px solid ${dim.color}">
        <span>${dim.icon} ${dim.label}</span>
        <span class="twin-item-id">${esc(item.id)}</span>
      </div>
      <div class="twin-item-detail-body">
        ${renderDimensionItem(dimKey, item)}
      </div>`;

    // Episodes
    if (episodes.length) {
      html += `<div class="twin-trace-section">
        <h4>📎 支撑事件 (${episodes.length})</h4>`;
      for (const ep of episodes) {
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

    html += "</div>";
    container.innerHTML = html;
  }

  // ── Policies ──
  function loadPolicies() {
    fetch("/api/twin/policies?status=active&limit=200")
      .then((r) => r.json())
      .then((data) => renderPolicies(data.policies || data))
      .catch((e) => console.error("Failed to load policies:", e));
  }

  function renderPolicies(items) {
    hide("twin-overview");
    hide("twin-detail");
    hide("twin-item-view");
    const container = show("twin-policies-view");
    setBreadcrumb([{ label: "执行策略" }]);

    let html = `<div class="twin-detail-header" style="--dim-color:#1e293b">
      <span class="twin-dim-icon">⚡</span>
      <span class="twin-detail-title">执行策略</span>
      <span class="twin-dim-count">${items.length} 条</span>
    </div>
    <div class="twin-policies-list">`;

    for (const p of items) {
      const conf = p.confidence != null ? Math.round(p.confidence * 100) : null;
      html += `<div class="twin-policy-card" data-policy-id="${esc(p.id)}">
        <div class="twin-policy-rule">
          <div><span class="twin-kw">IF</span> ${esc(p.condition)}</div>
          <div><span class="twin-kw">THEN</span> ${esc(p.action)}</div>
          ${p.exception ? `<div><span class="twin-kw">UNLESS</span> ${esc(p.exception)}</div>` : ""}
        </div>
        ${p.rationale ? `<div class="twin-policy-rationale"><b>Why:</b> ${esc(p.rationale)}</div>` : ""}
        <div class="twin-item-meta">
          <span class="twin-source">${esc(p.source_type)}:${esc(p.source_id)}</span>
          ${p.domain ? `<span class="twin-ep-domain">${esc(p.domain)}</span>` : ""}
          ${conf !== null ? `<span class="twin-conf">${conf}%</span>` : ""}
        </div>
      </div>`;
    }

    if (!items.length) {
      html += '<div class="twin-dim-empty" style="padding:24px">暂无策略。先运行 Analyze，然后通过 CLI 执行 <code>python3 analyze.py twin-compile</code> 编译策略。</div>';
    }

    html += "</div>";
    container.innerHTML = html;

    // Policy click → trace
    container.querySelectorAll("[data-policy-id]").forEach((el) => {
      el.onclick = () => loadPolicyTrace(el.dataset.policyId);
    });
  }

  function loadPolicyTrace(policyId) {
    fetch(`/api/twin/trace/${policyId}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.source) {
          // Determine dimKey from source_type
          const typeMap = {
            principle: "principles", tension: "tensions", tradeoff: "tradeoffs",
            communication: "communication", role: "roles", expertise: "expertise",
          };
          const dimKey = typeMap[data.policy?.source_type] || "principles";
          renderItemDetail(dimKey, { item: data.source, episodes: data.episodes || [] });
        }
      })
      .catch((e) => console.error("Failed to load trace:", e));
  }

  // ── Analysis (SSE streaming) ──
  function startAnalysis() {
    const btn = document.getElementById("twin-btn-analyze");
    if (btn) { btn.disabled = true; btn.textContent = "⏳ Analyzing..."; }

    const progress = show("twin-analysis-progress");
    if (progress) progress.innerHTML = '<div class="twin-stream-log"></div>';
    const log = progress?.querySelector(".twin-stream-log");

    fetch("/api/twin/analyze", { method: "POST" })
      .then((r) => {
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        function pump() {
          return reader.read().then(({ done, value }) => {
            if (done) {
              if (btn) { btn.disabled = false; btn.textContent = "🔄 Analyze"; }
              loadOverview();
              return;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (const line of lines) {
              if (line.startsWith("data: ")) {
                try {
                  const evt = JSON.parse(line.slice(6));
                  if (log) {
                    if (evt.type === "text") {
                      log.innerHTML += esc(evt.content || "");
                    } else if (evt.type === "tool") {
                      log.innerHTML += `<div class="twin-stream-tool">[${esc(evt.name || "")}] ${esc(evt.status || "")}</div>`;
                    } else if (evt.type === "error") {
                      log.innerHTML += `<div class="twin-stream-error">❌ ${esc(evt.message || "")}</div>`;
                    } else if (evt.type === "done") {
                      log.innerHTML += `<div class="twin-stream-done">✅ ${esc(evt.content || "完成")}</div>`;
                    }
                    log.scrollTop = log.scrollHeight;
                  }
                } catch {}
              }
            }
            return pump();
          });
        }
        return pump();
      })
      .catch((e) => {
        if (log) log.innerHTML += `<div class="twin-stream-error">❌ ${esc(String(e))}</div>`;
        if (btn) { btn.disabled = false; btn.textContent = "🔄 Analyze"; }
      });
  }

  // ── Sync ──
  function startSync() {
    if (!confirm("将认知模型策略同步到 CLAUDE.md 和 memory 文件？")) return;
    fetch("/api/twin/sync", { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          alert(`同步完成：${data.policies_synced || 0} 条策略已写入`);
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
    let html = `<span class="twin-bc-root" onclick="window.initTwinView && window.initTwinView()">Digital Twin</span>`;
    for (const p of parts) {
      html += ` <span class="twin-bc-sep">›</span> `;
      if (p.onclick) {
        html += `<span class="twin-bc-link">${esc(p.label)}</span>`;
      } else {
        html += `<span class="twin-bc-current">${esc(p.label)}</span>`;
      }
    }
    bc.innerHTML = html;
    // Re-bind click handlers
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
