/**
 * i18n core (UI shell only; AI prompts / personas / model output are never translated).
 *
 * Tri-state locale: "system" | "zh" | "en". System mode follows navigator.language.
 * Exposes window.t / window.setLocale / window.registerI18n / window.applyI18nDom so
 * non-module scripts (twin.js, evolve.js) can share the same dictionary and re-render
 * on the "localechange" event.
 */

import { $ } from './dom.js';

const LOCALE_MODE_KEY = "chatview-locale-mode";   // "system" | "zh" | "en"

const I18N = {
  "zh": {
    "nav.sessions": "Sessions",
    "nav.ai": "AI Evolve",
    "nav.insights": "Insights",
    "nav.twin": "Distill Yourself",
    "search.placeholder": "搜索对话内容…",
    "filter.label": "Filter",
    "lang.title": "语言：系统 → 中文 → English",
    "welcome.subtitle": "浏览和分析你的 AI 对话历史",
    "welcome.card.sessions.title": "Sessions",
    "welcome.card.sessions.desc": "按项目、来源和时间快速定位历史上下文。",
    "welcome.card.ai.title": "AI Evolve",
    "welcome.card.ai.desc": "生成画像、记忆、规则和协作模式。",
    "welcome.card.twin.title": "Distill Yourself",
    "welcome.card.twin.desc": "把判断卡和认知特质压缩成上下文包。",
    "welcome.tools.title": "Insights",
    "welcome.tools.subtitle": "低成本查看使用模式、文件热点和代码资产",
    "welcome.card.heatmap.title": "工具热力图",
    "welcome.card.heatmap.desc": "各工具使用频率趋势",
    "welcome.card.hotspots.title": "文件热点",
    "welcome.card.hotspots.desc": "最常操作的文件排行",
    "welcome.card.errors.title": "错误模式",
    "welcome.card.errors.desc": "高频报错归类分析",
    "welcome.card.profile.title": "用户画像",
    "welcome.card.profile.desc": "AI 分析你的技术偏好",
    "welcome.card.health.title": "项目健康",
    "welcome.card.health.desc": "跨项目活跃度对比",
    "welcome.card.snippets.title": "代码片段",
    "welcome.card.snippets.desc": "对话中产生的代码集锦",
    "welcome.stat.sessions": "总会话",
    "welcome.stat.projects": "项目",
    "welcome.stat.recent": "近 7 天",
    "welcome.hint.press": "按",
    "welcome.hint.search": "搜索 ·",
    "welcome.hint.switch": "切换会话 ·",
    "welcome.hint.shortcuts": "查看全部快捷键",
    "chat.fold.expand": "展开全文 ↓",
    "chat.fold.collapse": "收起 ↑",
    "chat.continue": "继续分析",
    "chat.stopped": "（已停止）",
    "session.ai.placeholder": "问关于这个会话的问题…",
    "session.preset.req.title": "需求梳理",
    "session.preset.req.desc": "提取需求列表，标注完成状态和优先级",
    "session.preset.decision.title": "决策提取",
    "session.preset.decision.desc": "技术决策、方案选择及理由",
    "session.preset.pitfall.title": "踩坑总结",
    "session.preset.pitfall.desc": "Bug、错误及解法，提炼可复用教训",
    "session.preset.review.title": "Code Review",
    "session.preset.review.desc": "代码质量、安全性和改进点",
    "session.preset.todo.title": "待办提取",
    "session.preset.todo.desc": "未完成任务、遗留问题和下一步",
    "session.preset.rules.title": "规则提炼",
    "session.preset.rules.desc": "从纠正中提取 CLAUDE.md 规则建议",
    "gpreset.weekly.title": "本周复盘",
    "gpreset.weekly.desc": "按项目总结完成的功能、Bug修复、重构",
    "gpreset.repeat.title": "重复模式",
    "gpreset.repeat.desc": "跨项目的反复 Bug 模式和效率瓶颈",
    "gpreset.rulegen.title": "规则生成",
    "gpreset.rulegen.desc": "从纠正场景自动生成 CLAUDE.md 规则",
    "gpreset.promptopt.title": "Prompt 优化",
    "gpreset.promptopt.desc": "Prompt 质量评分和协作效率分析",
    "gpreset.decision.title": "决策考古",
    "gpreset.decision.desc": "提取架构决策及理由，生成决策日志",
    "gpreset.knowledge.title": "知识沉淀",
    "gpreset.knowledge.desc": "提炼可复用模式和 Memory 候选",
    "gpreset.efficiency.title": "效率分析",
    "gpreset.efficiency.desc": "高花费低产出会话诊断和工作流优化",
    "gpreset.tools.title": "工具对比",
    "gpreset.tools.desc": "Claude Code vs Codex CLI 使用效率对比",
    "ai.analysisDone": "✅ 分析完成：发现 {n} 条结果。3 秒后跳转到 Evolve → {tab}",
    "common.send": "发送",
    "common.stop": "■ 停止",
    "common.newChat": "+ 新建",
    "panel.recent": "最近",
    "panel.analysisHistory": "分析历史",
    "filter.source": "来源",
    "filter.date": "日期",
    "filter.project": "项目",
    "filter.clearAll": "清除全部",
    "filter.allProjects": "全部项目",
    "insights.tab.heatmap": "工具热力图",
    "insights.tab.hotspots": "文件热点",
    "insights.tab.errors": "错误模式",
    "insights.tab.health": "项目健康",
    "insights.tab.snippets": "代码片段",
    "evolve.tab.profile": "🧬 画像",
    "evolve.tab.memory": "🧠 记忆",
    "evolve.tab.rules": "📐 规则",
    "evolve.tab.signals": "⚡ 信号",
    "evolve.tab.patterns": "🔄 模式",
    "evolve.refresh": "🔄 刷新",
    "evolve.refreshAll": "🔄 全部",
    "evolve.sync": "📤 同步",
    "ai.chat.title": "💬 AI 分析",
    "twin.btn.analyze": "🔄 分析",
    "twin.btn.sync": "📤 同步",
    "conv.copy": "📋 复制",
    "conv.copy.title": "复制对话（仅用户 + 助手）",
    "conv.refresh": "↻ 刷新",
    "conv.refresh.title": "刷新",
    "conv.userOnly": "👤 仅用户",
    "conv.userOnly.title": "只显示用户消息",
    "conv.expandAll": "全部展开",
    "conv.collapseAll": "全部收起",
    "conv.expandAll.title": "展开 / 折叠工具块",
    "conv.export": "⬇ 导出",
    "conv.export.title": "导出为 Markdown",
    "conv.back.title": "返回",
    "rp.tab.outline": "大纲",
    "rp.tab.ai": "AI",
    "rp.tab.summary": "摘要",
    "search.results.title": "搜索结果",
    "search.sort.dateDesc": "按日期 ↓",
    "search.sort.dateAsc": "按日期 ↑",
    "search.sort.relevance": "按相关度",
    "search.count": "{n} 条结果",
    "search.noResults": "未找到结果。",
    "conv.showMore": "展开 ↓",
    "conv.showLess": "收起 ↑",
    "conv.collapse": "收起 ↑",
    "conv.you": "你",
    "conv.assistant": "助手",
    "conv.replyCopy.title": "复制",
    "conv.copyPath": "复制路径",
    "conv.image": "图片",
    "conv.agent": "🤖 智能体",
    "conv.toolCalls": "{n} 次工具调用",
    "conv.thinkingCount": "{n} 段思考",
    "conv.result": "结果",
    "conv.thinking": "思考中…",
    "conv.loadFailed": "加载会话失败：{msg}",
    "chat.continue.btn": "继续分析",
    "kbd.title": "键盘快捷键",
    "kbd.focusSearch": "聚焦搜索",
    "kbd.close": "关闭 / 退出搜索",
    "kbd.home": "首页",
    "kbd.aiEvolve": "AI Evolve",
    "kbd.insights": "Insights",
    "kbd.twin": "Distill Yourself",
    "kbd.nextPrevSession": "下一个 / 上一个会话",
    "kbd.openSession": "打开选中会话",
    "kbd.goHome": "返回首页",
    "kbd.nextPrevMsg": "下一条 / 上一条用户消息",
    "kbd.toggleOutline": "切换大纲面板",
    "kbd.collapseAll": "展开 / 折叠全部",
    "kbd.showHelp": "显示此帮助",
    "kbd.pressClose": "按 ? 或 Esc 关闭",
  },
  "en": {
    "nav.sessions": "Sessions",
    "nav.ai": "AI Evolve",
    "nav.insights": "Insights",
    "nav.twin": "Distill Yourself",
    "search.placeholder": "Search conversations…",
    "filter.label": "Filter",
    "lang.title": "Language: system → 中文 → English",
    "welcome.subtitle": "Browse and analyze your AI conversation history",
    "welcome.card.sessions.title": "Sessions",
    "welcome.card.sessions.desc": "Quickly locate historical context by project, source, and time.",
    "welcome.card.ai.title": "AI Evolve",
    "welcome.card.ai.desc": "Generate profiles, memory, rules, and collaboration patterns.",
    "welcome.card.twin.title": "Distill Yourself",
    "welcome.card.twin.desc": "Compress judgment cards and cognitive traits into a context pack.",
    "welcome.tools.title": "Insights",
    "welcome.tools.subtitle": "Low-cost view of usage patterns, file hotspots, and code assets",
    "welcome.card.heatmap.title": "Tool Heatmap",
    "welcome.card.heatmap.desc": "Per-tool usage frequency trends",
    "welcome.card.hotspots.title": "File Hotspots",
    "welcome.card.hotspots.desc": "Most frequently touched files",
    "welcome.card.errors.title": "Error Patterns",
    "welcome.card.errors.desc": "Grouped analysis of frequent errors",
    "welcome.card.profile.title": "User Profile",
    "welcome.card.profile.desc": "AI analysis of your tech preferences",
    "welcome.card.health.title": "Project Health",
    "welcome.card.health.desc": "Cross-project activity comparison",
    "welcome.card.snippets.title": "Code Snippets",
    "welcome.card.snippets.desc": "Code produced during conversations",
    "welcome.stat.sessions": "Total sessions",
    "welcome.stat.projects": "Projects",
    "welcome.stat.recent": "Last 7 days",
    "welcome.hint.press": "Press",
    "welcome.hint.search": "to search ·",
    "welcome.hint.switch": "to switch sessions ·",
    "welcome.hint.shortcuts": "for all shortcuts",
    "chat.fold.expand": "Expand ↓",
    "chat.fold.collapse": "Collapse ↑",
    "chat.continue": "Continue analysis",
    "chat.stopped": "(stopped)",
    "session.ai.placeholder": "Ask about this session…",
    "session.preset.req.title": "Requirements",
    "session.preset.req.desc": "Extract requirements with status and priority",
    "session.preset.decision.title": "Decisions",
    "session.preset.decision.desc": "Technical decisions, choices, and rationale",
    "session.preset.pitfall.title": "Pitfalls",
    "session.preset.pitfall.desc": "Bugs, errors, fixes, and reusable lessons",
    "session.preset.review.title": "Code Review",
    "session.preset.review.desc": "Code quality, security, and improvements",
    "session.preset.todo.title": "TODOs",
    "session.preset.todo.desc": "Unfinished tasks, open issues, and next steps",
    "session.preset.rules.title": "Rules",
    "session.preset.rules.desc": "Distill CLAUDE.md rules from corrections",
    "gpreset.weekly.title": "Weekly Recap",
    "gpreset.weekly.desc": "Per-project summary of features, fixes, refactors",
    "gpreset.repeat.title": "Recurring Patterns",
    "gpreset.repeat.desc": "Cross-project recurring bugs and bottlenecks",
    "gpreset.rulegen.title": "Rule Generation",
    "gpreset.rulegen.desc": "Auto-generate CLAUDE.md rules from corrections",
    "gpreset.promptopt.title": "Prompt Optimization",
    "gpreset.promptopt.desc": "Prompt quality scoring and collaboration efficiency",
    "gpreset.decision.title": "Decision Archaeology",
    "gpreset.decision.desc": "Extract architecture decisions and rationale",
    "gpreset.knowledge.title": "Knowledge Distillation",
    "gpreset.knowledge.desc": "Distill reusable patterns and memory candidates",
    "gpreset.efficiency.title": "Efficiency Analysis",
    "gpreset.efficiency.desc": "Diagnose costly low-output sessions and workflow",
    "gpreset.tools.title": "Tool Comparison",
    "gpreset.tools.desc": "Claude Code vs Codex CLI efficiency comparison",
    "ai.analysisDone": "✅ Analysis complete: found {n} results. Jumping to Evolve → {tab} in 3s",
    "common.send": "Send",
    "common.stop": "■ Stop",
    "common.newChat": "+ New",
    "panel.recent": "Recent",
    "panel.analysisHistory": "Analysis History",
    "filter.source": "Source",
    "filter.date": "Date",
    "filter.project": "Project",
    "filter.clearAll": "Clear all",
    "filter.allProjects": "All Projects",
    "insights.tab.heatmap": "Tool Heatmap",
    "insights.tab.hotspots": "File Hotspots",
    "insights.tab.errors": "Error Patterns",
    "insights.tab.health": "Project Health",
    "insights.tab.snippets": "Snippets",
    "evolve.tab.profile": "🧬 Profile",
    "evolve.tab.memory": "🧠 Memory",
    "evolve.tab.rules": "📐 Rules",
    "evolve.tab.signals": "⚡ Signals",
    "evolve.tab.patterns": "🔄 Patterns",
    "evolve.refresh": "🔄 Refresh",
    "evolve.refreshAll": "🔄 All",
    "evolve.sync": "📤 Sync",
    "ai.chat.title": "💬 AI Analysis",
    "twin.btn.analyze": "🔄 Analyze",
    "twin.btn.sync": "📤 Sync",
    "conv.copy": "📋 Copy",
    "conv.copy.title": "Copy conversation (User + Assistant only)",
    "conv.refresh": "↻ Refresh",
    "conv.refresh.title": "Refresh",
    "conv.userOnly": "👤 User Only",
    "conv.userOnly.title": "Show user messages only",
    "conv.expandAll": "Expand All",
    "conv.collapseAll": "Collapse All",
    "conv.expandAll.title": "Expand/collapse tool blocks",
    "conv.export": "⬇ Export",
    "conv.export.title": "Export as Markdown",
    "conv.back.title": "Back",
    "rp.tab.outline": "Outline",
    "rp.tab.ai": "AI",
    "rp.tab.summary": "Summary",
    "search.results.title": "Search Results",
    "search.sort.dateDesc": "By Date ↓",
    "search.sort.dateAsc": "By Date ↑",
    "search.sort.relevance": "By Relevance",
    "search.count": "{n} results",
    "search.noResults": "No results found.",
    "conv.showMore": "Show more ↓",
    "conv.showLess": "Show less ↑",
    "conv.collapse": "Collapse ↑",
    "conv.you": "You",
    "conv.assistant": "Assistant",
    "conv.replyCopy.title": "Copy",
    "conv.copyPath": "Copy path",
    "conv.image": "Image",
    "conv.agent": "🤖 Agent",
    "conv.toolCalls": "{n} tool calls",
    "conv.thinkingCount": "{n} thinking",
    "conv.result": "Result",
    "conv.thinking": "Thinking…",
    "conv.loadFailed": "Failed to load session: {msg}",
    "chat.continue.btn": "Continue analysis",
    "kbd.title": "Keyboard Shortcuts",
    "kbd.focusSearch": "Focus search",
    "kbd.close": "Close / blur search",
    "kbd.home": "Home",
    "kbd.aiEvolve": "AI Evolve",
    "kbd.insights": "Insights",
    "kbd.twin": "Distill Yourself",
    "kbd.nextPrevSession": "Next / previous session",
    "kbd.openSession": "Open selected session",
    "kbd.goHome": "Go back to Home",
    "kbd.nextPrevMsg": "Next / previous user message",
    "kbd.toggleOutline": "Toggle outline panel",
    "kbd.collapseAll": "Expand / collapse all",
    "kbd.showHelp": "Show this help",
    "kbd.pressClose": "Press ? or Esc to close",
  },
};

export function registerI18n(extra) {
  for (const loc of Object.keys(extra || {})) {
    I18N[loc] = Object.assign(I18N[loc] || {}, extra[loc]);
  }
}

function getStoredLocaleMode() {
  const m = localStorage.getItem(LOCALE_MODE_KEY);
  return (m === "system" || m === "zh" || m === "en") ? m : "system";
}

function resolveLocale(mode) {
  if (mode !== "system") return mode;
  const nav = (navigator.language || "en").toLowerCase();
  return nav.startsWith("zh") ? "zh" : "en";
}

let _locale = resolveLocale(getStoredLocaleMode());

export function t(key, vars) {
  const table = I18N[_locale] || I18N["en"];
  let s = (key in table) ? table[key] : (I18N["en"][key] != null ? I18N["en"][key] : key);
  if (vars) for (const k of Object.keys(vars)) s = s.replace(new RegExp("\\{" + k + "\\}", "g"), vars[k]);
  return s;
}

export function applyI18nDom(root) {
  const scope = root || document;
  scope.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  scope.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.setAttribute("placeholder", t(el.getAttribute("data-i18n-placeholder")));
  });
  scope.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.setAttribute("title", t(el.getAttribute("data-i18n-title")));
  });
}

export function setLocale(mode) {
  localStorage.setItem(LOCALE_MODE_KEY, mode);
  _locale = resolveLocale(mode);
  document.documentElement.setAttribute("lang", _locale === "zh" ? "zh-CN" : "en");
  applyI18nDom(document);
  window.dispatchEvent(new CustomEvent("localechange", { detail: { locale: _locale, mode } }));
}

function localeGlyphTitle(mode) {
  return mode === "system" ? "🌐" : (mode === "zh" ? "中" : "EN");
}

export function initLocaleToggle() {
  document.documentElement.setAttribute("lang", _locale === "zh" ? "zh-CN" : "en");
  const btn = $("#locale-toggle");
  applyI18nDom(document);
  if (btn) btn.textContent = localeGlyphTitle(getStoredLocaleMode());
  if (!btn) return;
  btn.addEventListener("click", () => {
    const order = ["system", "zh", "en"];
    const next = order[(order.indexOf(getStoredLocaleMode()) + 1) % order.length];
    setLocale(next);
    btn.textContent = localeGlyphTitle(next);
  });
}

// Expose for non-module scripts (twin.js / evolve.js) which use window.t etc.
window.t = t;
window.registerI18n = registerI18n;
window.setLocale = setLocale;
window.applyI18nDom = applyI18nDom;
