/**
 * Global AI / Evolve page — standalone AI chat view for cross-session analysis.
 *
 * Usage:
 *   import { initAiPage, notifyEvolveScopeChanged, renderAiScopeBar,
 *            submitGlobalAi, newGlobalChat, saveChatToStorage, loadChatFromStorage,
 *            ... } from './evolve-page.js';
 */

import { state } from './state.js';
import { $ } from './dom.js';
import { esc, autoResizeTextarea } from './utils.js';
import {
  appendChatMsg, createAssistantTurn, sendChatStream,
  _appendContinueButton,
} from './chat.js';
import { t, getLang } from './lang.js';

// ── Presets ──────────────────────────────────────────────────────

const GLOBAL_AI_PRESETS = [
  { icon: "📊", titleKey: "preset.global.review.title", descKey: "preset.global.review.desc", prompt: "分析所有对话，生成工作复盘。\n\n**工作流（按顺序执行）**：\n1. 先运行 `highlights` 获取全部会话的一行概览（含纠正/决策信号数）\n2. 运行 `stats` 查看项目分布和统计\n3. 对高信号会话运行 `read -s <id>` 看摘要\n4. 运行 `errors` 看高频错误模式\n\n**输出要求**：\n1. **项目分布**：各项目会话数和主要活动\n2. **关键产出**：每个项目完成的功能/修复\n3. **主要问题**：遇到的阻塞和解决情况\n4. **技术亮点**：有价值的技术方案或突破\n5. **效率观察**：哪些会话高效（低纠正、少消息）、哪些低效（高纠正）\n\n每个发现附 session ID 作为证据锚点。" },
  { icon: "🔄", titleKey: "preset.global.patterns.title", descKey: "preset.global.patterns.desc", prompt: "深度分析对话历史，找出跨项目反复出现的问题模式。\n\n**工作流（按顺序执行）**：\n1. 运行 `errors` 获取所有错误模式（按频率排序、跨 session 聚合）\n2. 运行 `corrections` 获取用户纠正模式（反映效率瓶颈）\n3. 运行 `highlights` 找高纠正/高消息数的低效会话\n4. 对高频错误和纠正的会话运行 `read -s <id>` 看上下文\n5. 运行 `search \"搜索\"` 和 `search \"怎么\"` 定位知识盲区\n\n**输出要求**：\n1. **高频错误**：同类错误出现2+次的模式\n2. **效率瓶颈**：反复消耗时间的环节\n3. **知识盲区**：多次搜索或询问的领域\n4. **根因分析**：每个模式的根本原因\n5. **改进方案**：具体可执行的改进，按ROI排序" },
  { icon: "📐", titleKey: "preset.global.rules.title", descKey: "preset.global.rules.desc", prompt: "分析所有对话中用户纠正AI的场景，自动生成CLAUDE.md规则。\n\n**工作流（按顺序执行）**：\n1. 先运行 `corrections` 获取所有纠正样本（已含50+种中英文信号词检测）\n2. 运行 `highlights` 找高纠正数的会话（corr≥3的重点关注）\n3. 对高纠正会话运行 `read -s <id>` 看上下文（理解纠正原因）\n4. 补充搜索 `search \"不行\"` `search \"太精简\"` `search \"应该是\"` 等关键词\n\n**输出要求**：\n1. 聚类相似纠正，提取模式\n2. 为每个模式生成规则：规则内容 | 触发场景 | 来源频次\n3. 按出现频率排序，标注优先级 P0/P1/P2\n4. 格式参考 CLAUDE.md 规则写法（可直接粘贴使用）\n\n每条规则附至少一条原始纠正引用（用户原话）和 session ID 作为证据。" },
  { icon: "💡", titleKey: "preset.global.prompt.title", descKey: "preset.global.prompt.desc", prompt: "分析我的 prompt 质量和 AI 协作效率。\n\n**工作流（按顺序执行）**：\n1. 运行 `highlights` 查看每个会话的消息数和纠正信号数\n2. 运行 `corrections` 获取所有纠正场景（纠正=prompt 不够好）\n3. 对比低纠正会话（corr:0, 消息少）和高纠正会话（corr≥3），用 `read -s <id>` 各看 2-3 个\n4. 运行 `queries --limit 30` 浏览用户 prompt 样本\n\n**输出要求**：\n1. **一次成功率**：哪些类型的 prompt 能一次成功\n2. **多轮纠正**：哪些场景需反复修改，为什么\n3. **高效模式**：好 prompt 的共同特征\n4. **低效模式**：差 prompt 的问题所在\n5. **改进建议**：针对我的习惯的 prompt 模板建议" },
  { icon: "🎯", titleKey: "preset.global.decisions.title", descKey: "preset.global.decisions.desc", prompt: "提取所有会话中的架构和技术决策，生成决策日志。\n\n**工作流（按顺序执行）**：\n1. 先运行 `decisions` 获取所有决策点样本\n2. 运行 `highlights` 找高决策数的会话（dec≥2的重点关注）\n3. 对关键会话运行 `read -s <id>` 查看决策上下文\n4. 运行 `stats` 了解项目分布，按项目组织决策\n\n**输出要求**：\n1. 按时间线列出所有重要决策\n2. 每个决策：背景、选项、最终选择、理由\n3. 标注跨项目影响的决策\n4. 识别前后矛盾或需重新审视的决策\n5. 输出格式参考 ADR (Architecture Decision Record)\n\n每个 ADR 附 session ID。Top 5 关键决策需展开完整背景/选项/理由。" },
  { icon: "🧠", titleKey: "preset.global.knowledge.title", descKey: "preset.global.knowledge.desc", prompt: "从对话轨迹中提炼可沉淀的知识。\n\n**工作流（按顺序执行）**：\n1. 运行 `stats` 获取项目分布全景\n2. 运行 `errors` 获取高频错误模式（→踩坑大全候选）\n3. 运行 `corrections` 获取纠正模式（→有效实践候选）\n4. 运行 `highlights` 找信号丰富的会话\n5. 对关键会话运行 `read -s <id>` 提取可复用方案\n6. 运行 `files` 看文件热点（→技能图谱依据）\n\n**输出要求**：\n1. **可复用方案**：跨项目可复用的代码模式\n2. **验证有效的实践**：确认好用的开发实践（附证据：session ID + 关键引用）\n3. **踩坑大全**：高频踩坑及标准解法\n4. **Memory候选**：建议写入记忆的知识（知识内容 | 适用场景 | 来源证据）\n5. **技能图谱**：哪些技术领域积累最深，哪些需加强" },
  { icon: "📈", titleKey: "preset.global.efficiency.title", descKey: "preset.global.efficiency.desc", prompt: "分析 AI 编码效率和成本热点。\n\n**工作流（按顺序执行）**：\n1. 运行 `highlights` 获取全部会话概览，按消息数排序找高耗时会话\n2. 运行 `stats` 看总体数据量（sessions/messages/MB）\n3. 对消息数 Top 5 的会话运行 `read -s <id>` 诊断低效原因\n4. 运行 `corrections` 统计哪些项目纠正最多（纠正=返工成本）\n5. 运行 `files` 看文件编辑热点（高编辑=可能过度修改）\n\n**输出要求**：\n1. **高耗时会话**：消息数最多的 Top 5 会话及主题\n2. **低效原因**：反复修改、方向错误、上下文丢失\n3. **工具使用**：哪些工具被过度使用或使用不足\n4. **对比分析**：高效会话 vs 低效会话的模式差异\n5. **优化建议**：具体的工作流改进建议" },
  { icon: "🔀", titleKey: "preset.global.compare.title", descKey: "preset.global.compare.desc", prompt: "对比分析 Claude Code 和 Codex CLI 的使用效率。\n\n**工作流（按顺序执行）**：\n1. 运行 `stats --source claude` 和 `stats --source codex` 分别统计\n2. 运行 `highlights --source claude --limit 20` 和 `highlights --source codex --limit 20` 对比\n3. 运行 `corrections --source claude` 和 `corrections --source codex` 对比纠正率\n4. 运行 `files --source claude` 和 `files --source codex` 对比文件操作模式\n5. 对代表性会话运行 `read -s <id>` 了解任务类型差异\n\n**输出要求**：\n1. **使用分布**：各工具的会话数、消息数、数据量\n2. **任务类型**：各工具擅长的任务类型\n3. **成功率**：哪个工具在什么场景下纠正更少\n4. **互补模式**：两者最佳搭配使用方式\n5. **工作流建议**：什么任务用哪个工具" },
];

// ── Presets rendering ────────────────────────────────────────────

export function populateGlobalAiPresets() {
  const container = $("#ai-chat-presets");
  if (!container || container.dataset.populated) return;
  container.dataset.populated = "1";
  container.innerHTML = "";
  GLOBAL_AI_PRESETS.forEach(p => {
    const btn = document.createElement("button");
    btn.className = "preset-card";
    btn.dataset.prompt = p.prompt;
    btn.innerHTML = `<span class="preset-icon">${p.icon}</span><div class="preset-info"><span class="preset-title">${t(p.titleKey)}</span><span class="preset-desc">${t(p.descKey)}</span></div>`;
    btn.addEventListener("click", () => submitGlobalAi(btn.dataset.prompt));
    container.appendChild(btn);
  });
}

// ── AI Page init ─────────────────────────────────────────────────

/** Initialize AI page — scope bar + Evolve + chat */
export function initAiPage() {
  // Override getEvolveScope to read from shared global scope
  window.getEvolveScope = function() {
    return { source: state.globalScopeSource, date: state.globalScopeDate, project: state.globalScopeProject, engine: state.globalScopeEngine, lang: getLang() };
  };
  renderAiScopeBar();
  populateGlobalAiPresets();
  restoreAiChatMessages();
  // Initialize Evolve visualizations after the shared scope getter exists.
  if (window.initEvolveView) window.initEvolveView();
}

export function notifyEvolveScopeChanged() {
  if (typeof window.abortEvolveStreams === "function") window.abortEvolveStreams();
  if (window.initEvolveView) window.initEvolveView();
}

// ── Scope bar ────────────────────────────────────────────────────

export function renderAiScopeBar() {
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
  const claudeCount = state.allSessions.filter(s => (s.source || "claude") === "claude").length;
  const codexCount = state.allSessions.filter(s => s.source === "codex").length;
  [
    { key: "all", label: "All", count: state.allSessions.length },
    { key: "claude", label: "Claude", count: claudeCount },
    { key: "codex", label: "Codex", count: codexCount },
  ].forEach(s => {
    const btn = document.createElement("button");
    btn.className = `scope-tab${s.key === state.globalScopeSource ? " active" : ""}`;
    btn.innerHTML = `${s.label} <span class="tab-count">${s.count}</span>`;
    btn.addEventListener("click", () => {
      state.globalScopeSource = s.key;
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
    btn.className = `scope-tab${d.key === state.globalScopeDate ? " active" : ""}`;
    btn.textContent = d.label;
    btn.addEventListener("click", () => {
      state.globalScopeDate = d.key;
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
  if (state.globalScopeProject && !Object.prototype.hasOwnProperty.call(projCounts, state.globalScopeProject)) {
    state.globalScopeProject = "";
  }
  projSelect.value = state.globalScopeProject;
  projSelect.onchange = () => {
    state.globalScopeProject = projSelect.value;
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
  (state.availableEngines.length ? state.availableEngines : ["claude"]).forEach(eng => {
    const opt = document.createElement("option");
    opt.value = eng;
    opt.textContent = eng.charAt(0).toUpperCase() + eng.slice(1);
    engineSelect.appendChild(opt);
  });
  engineSelect.disabled = state.availableEngines.length <= 1;
  engineSelect.value = state.globalScopeEngine;
  engineSelect.onchange = () => {
    state.globalScopeEngine = engineSelect.value;
    // Sync back to header selector
    const headerEngine = $("#global-engine-select");
    if (headerEngine) headerEngine.value = state.globalScopeEngine;
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
  timeoutSelect.value = state.chatTimeout;
  timeoutSelect.onchange = () => {
    state.chatTimeout = parseInt(timeoutSelect.value, 10);
    localStorage.setItem("chatview-timeout", String(state.chatTimeout));
  };
  bar.appendChild(timeoutSelect);

  // Scope stats
  let scopeFiltered = filtered;
  if (state.globalScopeProject) scopeFiltered = scopeFiltered.filter(s => s.project === state.globalScopeProject);
  const projects = new Set(scopeFiltered.map(s => s.project).filter(Boolean));
  const msgs = scopeFiltered.reduce((sum, s) => sum + (s.userMessageCount || 0), 0);
  const statsSpan = document.createElement("span");
  statsSpan.className = "scope-stats";
  statsSpan.innerHTML = `<strong>${scopeFiltered.length}</strong> sessions · <strong>${projects.size}</strong> projects · <strong>${msgs}</strong> msgs`;
  bar.appendChild(statsSpan);
}

// ── Chat messages ────────────────────────────────────────────────

export function restoreAiChatMessages() {
  const container = $("#ai-chat-messages");
  if (!container) return;
  container.innerHTML = "";
  if (state.currentGlobalChatId) {
    const chat = state.globalChatHistory.find(c => c.id === state.currentGlobalChatId);
    if (chat && chat.messages.length) {
      chat.messages.forEach(m => appendChatMsg(container, m.role, m.content));
      const presets = $("#ai-chat-presets");
      if (presets) presets.style.display = "none";
    }
  }
}

/** Get sessions matching current evolve scope (source + date) */
export function getFilteredScopeSessions() {
  const scope = window.getEvolveScope ? window.getEvolveScope() : { source: state.globalScopeSource, date: state.globalScopeDate };
  let list = state.allSessions;
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

// ── Submit global AI ─────────────────────────────────────────────

export function submitGlobalAi(prompt) {
  const input = $("#ai-chat-input");
  const text = prompt || (input ? input.value.trim() : "");
  if (!text || state.globalAiLoading) return;
  if (input) { input.value = ""; autoResizeTextarea(input); }

  const container = $("#ai-chat-messages");
  if (!container) return;

  // Ensure we have a global chat
  if (!state.currentGlobalChatId) initNewGlobalChat();

  // Use shared scope state
  const scope = {
    project: state.globalScopeProject,
    date: state.globalScopeDate,
    source: state.globalScopeSource,
    engine: state.globalScopeEngine,
  };

  // Add user message
  appendChatMsg(container, "user", text);
  saveGlobalChatMessage("user", text);

  // Hide presets
  const presets = $("#ai-chat-presets");
  if (presets) presets.style.display = "none";

  // Show streaming bubble
  state.globalAiLoading = true;
  _setGlobalAiButton(true);
  const assistantTurn = createAssistantTurn(container);

  const chat = state.globalChatHistory.find(c => c.id === state.currentGlobalChatId);
  const priorMsgs = chat ? chat.messages.slice(0, -1) : [];
  const handle = sendChatStream(text, "global", null, scope, priorMsgs);
  state.globalAiHandle = handle;
  handle
    .onText(chunk => {
      assistantTurn.updateText(chunk);
    })
    .onTool(evt => {
      assistantTurn.addTool(evt);
    })
    .onDone((fullText, isTimeout) => {
      if (state.globalAiHandle !== handle) return;
      state.globalAiLoading = false;
      state.globalAiHandle = null;
      _setGlobalAiButton(false);
      const reply = fullText || "(empty response)";
      assistantTurn.finalize(reply);
      saveGlobalChatMessage("assistant", reply);
      // Update title
      const chat2 = state.globalChatHistory.find(c => c.id === state.currentGlobalChatId);
      if (chat2 && chat2.title === "New Analysis") {
        chat2.title = text.substring(0, 40) + (text.length > 40 ? "…" : "");
        renderGlobalChatSidebar();
      }
      saveChatToStorage();

      if (isTimeout) {
        _appendContinueButton(container, () => submitGlobalAi(t('chat.continue')));
      } else {
        // Check if this was an Evolve-related analysis (bilingual keywords)
        const evolveTabMap = {
          "自动生成CLAUDE.md规则": "rules", "规则生成": "rules",
          "auto-generate CLAUDE.md rules": "rules", "rule generation": "rules",
          "可沉淀的知识": "memory", "知识沉淀": "memory",
          "distillable knowledge": "memory", "knowledge distill": "memory",
          "用户画像": "profile", "user profile": "profile",
          "纠正AI的场景": "signals", "纠正模式": "signals",
          "correction signals": "signals", "correction patterns": "signals",
          "反复出现的问题模式": "patterns", "重复模式": "patterns",
          "recurring patterns": "patterns", "repeat patterns": "patterns",
        };
        let targetTab = null;
        const textLower = text.toLowerCase();
        for (const [keyword, tab] of Object.entries(evolveTabMap)) {
          if (textLower.includes(keyword.toLowerCase())) { targetTab = tab; break; }
        }
        if (targetTab) {
          const parsed = window.parseEvolveResponseExternal ? window.parseEvolveResponseExternal(targetTab, reply) : null;
          if (parsed && !parsed._parseError) {
            const itemCount = Object.values(parsed).reduce((sum, v) => sum + (Array.isArray(v) ? v.length : 0), 0);
            const summaryText = t('chat.analysisComplete', itemCount, targetTab);
            appendChatMsg(container, "assistant", summaryText);
            setTimeout(() => {
              if (window.navigateToEvolveTab) window.navigateToEvolveTab(targetTab, parsed);
            }, 3000);
          }
        }
      }
    })
    .onError(msg => {
      if (state.globalAiHandle !== handle) return;
      state.globalAiLoading = false;
      state.globalAiHandle = null;
      _setGlobalAiButton(false);
      const reply = `**Error:** ${msg}`;
      assistantTurn.finalize(reply);
      saveGlobalChatMessage("assistant", reply);
      saveChatToStorage();
    })
    .onAbort(partialText => {
      if (state.globalAiHandle !== handle) return;
      state.globalAiLoading = false;
      state.globalAiHandle = null;
      _setGlobalAiButton(false);
      const reply = (partialText || "") + "\n\n" + t('chat.stopped');
      assistantTurn.finalize(reply);
      saveGlobalChatMessage("assistant", reply);
      saveChatToStorage();
      _appendContinueButton(container, () => submitGlobalAi(t('chat.continue')));
    });
}

export function _setGlobalAiButton(loading) {
  const btn = $("#ai-chat-send");
  if (!btn) return;
  if (loading) { btn.textContent = "■ Stop"; btn.classList.add("btn-stop"); }
  else { btn.textContent = "Send"; btn.classList.remove("btn-stop"); }
}

export function _stopGlobalAi() {
  if (state.globalAiHandle) state.globalAiHandle.abort();
  // Don't null globalAiHandle here — let onAbort callback do cleanup
  state.globalAiLoading = false;
  _setGlobalAiButton(false);
}

// ── Chat session management ──────────────────────────────────────

export function initNewGlobalChat() {
  state.currentGlobalChatId = "gchat-" + Date.now();
  state.globalChatHistory.unshift({id: state.currentGlobalChatId, title: "New Analysis", messages: []});
  renderGlobalChatSidebar();
}

export function newGlobalChat() {
  state.currentGlobalChatId = null;
  const container = $("#ai-chat-messages");
  if (container) container.innerHTML = "";
  const presets = $("#ai-chat-presets");
  if (presets) presets.style.display = "";
  initNewGlobalChat();
}

export function saveGlobalChatMessage(role, content) {
  const chat = state.globalChatHistory.find(c => c.id === state.currentGlobalChatId);
  if (chat) chat.messages.push({role, content});
}

export function renderGlobalChatSidebar() {
  const list = $("#chat-history-list");
  if (!list) return;
  list.innerHTML = "";
  state.globalChatHistory.forEach(chat => {
    const li = document.createElement("li");
    li.className = "session-item" + (chat.id === state.currentGlobalChatId ? " active" : "");
    li.innerHTML = `<div class="session-title">${esc(chat.title)}</div>
      <div class="session-date">${chat.messages.length} messages</div>`;
    li.addEventListener("click", () => loadGlobalChatHistory(chat.id));
    list.appendChild(li);
  });
}

export function loadGlobalChatHistory(chatId) {
  const chat = state.globalChatHistory.find(c => c.id === chatId);
  if (!chat) return;
  state.currentGlobalChatId = chatId;
  const container = $("#ai-chat-messages");
  if (container) {
    container.innerHTML = "";
    chat.messages.forEach(m => appendChatMsg(container, m.role, m.content));
  }
  const presets = $("#ai-chat-presets");
  if (presets) presets.style.display = chat.messages.length ? "none" : "";
  renderGlobalChatSidebar();
}

// ── Chat persistence (localStorage) ─────────────────────────────

let _quotaWarningShown = false;
export function _showQuotaWarning() {
  if (_quotaWarningShown) return;
  _quotaWarningShown = true;
  const toast = document.createElement("div");
  toast.style.cssText = "position:fixed;bottom:20px;right:20px;background:#e65100;color:#fff;padding:12px 20px;border-radius:8px;z-index:9999;font-size:13px;box-shadow:0 4px 12px rgba(0,0,0,.3);max-width:320px";
  toast.textContent = "Storage quota exceeded — chat history and cache may not persist. Consider clearing old chat sessions.";
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 8000);
}

export function saveChatToStorage() {
  try {
    // Session chats — prune to last 50 sessions
    const keys = Object.keys(state.sessionChatCache);
    if (keys.length > 50) {
      keys.slice(50).forEach(k => delete state.sessionChatCache[k]);
    }
    localStorage.setItem("chatview-session-chats", JSON.stringify(state.sessionChatCache));
    // Global chats — keep last 30
    const trimmed = state.globalChatHistory.slice(0, 30);
    localStorage.setItem("chatview-global-chats", JSON.stringify(trimmed));
  } catch (e) {
    if (e.name === "QuotaExceededError" || (e.code && e.code === 22)) {
      _showQuotaWarning();
    }
  }
}

export function loadChatFromStorage() {
  try {
    const sc = localStorage.getItem("chatview-session-chats");
    if (sc) state.sessionChatCache = JSON.parse(sc);
    const gc = localStorage.getItem("chatview-global-chats");
    if (gc) {
      state.globalChatHistory = JSON.parse(gc);
      renderGlobalChatSidebar();
    }
  } catch (e) { /* corrupt data — ignore */ }
}
