/**
 * Lightweight i18n — Chinese / English language switch.
 *
 * Usage:
 *   import { t, getLang, setLang, applyLang } from './lang.js';
 *   t('search.placeholder')          // → current-language string
 *   t('found.results', 42)           // → "发现 42 条结果" or "Found 42 results"
 *   setLang('en')                    // switch + update DOM
 */

const I18N = {
  zh: {
    // ── Top bar ──
    'search.placeholder': '搜索对话内容…',

    // ── Welcome page ──
    'welcome.subtitle': '浏览和分析你的 AI 对话历史',
    'welcome.sessions.desc': '按项目、来源和时间快速定位历史上下文。',
    'welcome.evolve.desc': '生成画像、记忆、规则和协作模式。',
    'welcome.twin.desc': '把判断卡和认知特质压缩成上下文包。',
    'welcome.insights.subtitle': '低成本查看使用模式、文件热点和代码资产',
    'welcome.heatmap.title': '工具热力图',
    'welcome.heatmap.desc': '各工具使用频率趋势',
    'welcome.hotspots.title': '文件热点',
    'welcome.hotspots.desc': '最常操作的文件排行',
    'welcome.errors.title': '错误模式',
    'welcome.errors.desc': '高频报错归类分析',
    'welcome.profile.title': '用户画像',
    'welcome.profile.desc': 'AI 分析你的技术偏好',
    'welcome.health.title': '项目健康',
    'welcome.health.desc': '跨项目活跃度对比',
    'welcome.snippets.title': '代码片段',
    'welcome.snippets.desc': '对话中产生的代码集锦',
    'welcome.hint': '按 {0} 搜索 · {1}{2} 切换会话 · {3} 查看全部快捷键',

    // ── Welcome stats ──
    'stats.sessions': '总会话',
    'stats.projects': '项目',
    'stats.recent': '近 7 天',

    // ── Twin view ──
    'twin.notAnalyzed': '尚未分析',
    'twin.viewProgress': '📊 查看进度',
    'twin.openPack': '点击打开 Runtime Pack',
    'twin.selectType': '选择认知类型',
    'twin.awaitModel': '等待认知模型',
    'twin.awaitModelHint': '点击 Analyze 后匹配认知模型',

    // ── Evolve view ──
    'evolve.notAnalyzed': '尚未分析',
    'evolve.emptyHint': '点击刷新，开始分析最近的对话',

    // ── AI chat ──
    'ai.inputPlaceholder': '输入跨会话分析需求…',
    'session.ai.placeholder': '问关于这个会话的问题…',

    // ── Session AI presets (titles + descs) ──
    'preset.session.requirements.title': '需求梳理',
    'preset.session.requirements.desc': '提取需求列表，标注完成状态和优先级',
    'preset.session.decisions.title': '决策提取',
    'preset.session.decisions.desc': '技术决策、方案选择及理由',
    'preset.session.bugs.title': '踩坑总结',
    'preset.session.bugs.desc': 'Bug、错误及解法，提炼可复用教训',
    'preset.session.review.desc': '代码质量、安全性和改进点',
    'preset.session.todos.title': '待办提取',
    'preset.session.todos.desc': '未完成任务、遗留问题和下一步',
    'preset.session.rules.title': '规则提炼',
    'preset.session.rules.desc': '从纠正中提取 CLAUDE.md 规则建议',

    // ── Global AI presets (titles + descs) ──
    'preset.global.review.title': '本周复盘',
    'preset.global.review.desc': '按项目总结完成的功能、Bug修复、重构',
    'preset.global.patterns.title': '重复模式',
    'preset.global.patterns.desc': '跨项目的反复 Bug 模式和效率瓶颈',
    'preset.global.rules.title': '规则生成',
    'preset.global.rules.desc': '从纠正场景自动生成 CLAUDE.md 规则',
    'preset.global.prompt.title': 'Prompt 优化',
    'preset.global.prompt.desc': 'Prompt 质量评分和协作效率分析',
    'preset.global.decisions.title': '决策考古',
    'preset.global.decisions.desc': '提取架构决策及理由，生成决策日志',
    'preset.global.knowledge.title': '知识沉淀',
    'preset.global.knowledge.desc': '提炼可复用模式和 Memory 候选',
    'preset.global.efficiency.title': '效率分析',
    'preset.global.efficiency.desc': '高花费低产出会话诊断和工作流优化',
    'preset.global.compare.title': '工具对比',
    'preset.global.compare.desc': 'Claude Code vs Codex CLI 使用效率对比',

    // ── Dynamic strings (JS) ──
    'chat.continue': '继续',
    'chat.stopped': '*(已停止)*',
    'chat.continueAnalysis': '继续分析',
    'chat.expandFull': '展开全文 ↓',
    'chat.collapse': '收起 ↑',
    'chat.analysisComplete': '✅ 分析完成：发现 {0} 条结果。3 秒后跳转到 Evolve → {1}',
  },

  en: {
    // ── Top bar ──
    'search.placeholder': 'Search conversations…',

    // ── Welcome page ──
    'welcome.subtitle': 'Browse and analyze your AI conversation history',
    'welcome.sessions.desc': 'Quickly locate history by project, source, and time.',
    'welcome.evolve.desc': 'Generate profiles, memories, rules, and patterns.',
    'welcome.twin.desc': 'Compress judgment cards and cognitive traits into context packs.',
    'welcome.insights.subtitle': 'Lightweight views for usage patterns, file hotspots, and code assets',
    'welcome.heatmap.title': 'Tool Heatmap',
    'welcome.heatmap.desc': 'Tool usage frequency trends',
    'welcome.hotspots.title': 'File Hotspots',
    'welcome.hotspots.desc': 'Most frequently edited files',
    'welcome.errors.title': 'Error Patterns',
    'welcome.errors.desc': 'Common error classification',
    'welcome.profile.title': 'User Profile',
    'welcome.profile.desc': 'AI-analyzed technical preferences',
    'welcome.health.title': 'Project Health',
    'welcome.health.desc': 'Cross-project activity comparison',
    'welcome.snippets.title': 'Code Snippets',
    'welcome.snippets.desc': 'Code produced in conversations',
    'welcome.hint': 'Press {0} to search · {1}{2} to switch sessions · {3} for all shortcuts',

    // ── Welcome stats ──
    'stats.sessions': 'Sessions',
    'stats.projects': 'Projects',
    'stats.recent': 'Last 7 days',

    // ── Twin view ──
    'twin.notAnalyzed': 'Not analyzed',
    'twin.viewProgress': '📊 View progress',
    'twin.openPack': 'Click to open Runtime Pack',
    'twin.selectType': 'Select cognitive type',
    'twin.awaitModel': 'Awaiting cognitive model',
    'twin.awaitModelHint': 'Click Analyze to match a cognitive model',

    // ── Evolve view ──
    'evolve.notAnalyzed': 'Not analyzed',
    'evolve.emptyHint': 'Click refresh to start analyzing recent conversations',

    // ── AI chat ──
    'ai.inputPlaceholder': 'Enter cross-session analysis request…',
    'session.ai.placeholder': 'Ask about this session…',

    // ── Session AI presets (titles + descs) ──
    'preset.session.requirements.title': 'Requirements',
    'preset.session.requirements.desc': 'Extract requirement list with status and priority',
    'preset.session.decisions.title': 'Decisions',
    'preset.session.decisions.desc': 'Technical decisions, choices, and rationale',
    'preset.session.bugs.title': 'Pitfalls',
    'preset.session.bugs.desc': 'Bugs, errors, solutions, and reusable lessons',
    'preset.session.review.desc': 'Code quality, security, and improvements',
    'preset.session.todos.title': 'TODOs',
    'preset.session.todos.desc': 'Unfinished tasks, remaining issues, and next steps',
    'preset.session.rules.title': 'Rules',
    'preset.session.rules.desc': 'Extract CLAUDE.md rules from correction patterns',

    // ── Global AI presets (titles + descs) ──
    'preset.global.review.title': 'Weekly Review',
    'preset.global.review.desc': 'Summarize features, bug fixes, refactors by project',
    'preset.global.patterns.title': 'Repeat Patterns',
    'preset.global.patterns.desc': 'Cross-project recurring bugs and efficiency bottlenecks',
    'preset.global.rules.title': 'Rule Generation',
    'preset.global.rules.desc': 'Auto-generate CLAUDE.md rules from corrections',
    'preset.global.prompt.title': 'Prompt Optimization',
    'preset.global.prompt.desc': 'Prompt quality scoring and collaboration efficiency',
    'preset.global.decisions.title': 'Decision Archaeology',
    'preset.global.decisions.desc': 'Extract architecture decisions and rationale',
    'preset.global.knowledge.title': 'Knowledge Distill',
    'preset.global.knowledge.desc': 'Distill reusable patterns and memory candidates',
    'preset.global.efficiency.title': 'Efficiency Analysis',
    'preset.global.efficiency.desc': 'Diagnose high-cost low-output sessions',
    'preset.global.compare.title': 'Tool Comparison',
    'preset.global.compare.desc': 'Claude Code vs Codex CLI efficiency comparison',

    // ── Dynamic strings (JS) ──
    'chat.continue': 'Continue',
    'chat.stopped': '*(stopped)*',
    'chat.continueAnalysis': 'Continue analysis',
    'chat.expandFull': 'Expand all ↓',
    'chat.collapse': 'Collapse ↑',
    'chat.analysisComplete': '✅ Analysis complete: found {0} results. Redirecting to Evolve → {1} in 3s',
  },
};

let _lang = localStorage.getItem('chatview-lang') || 'zh';

/**
 * Translate a key, with optional positional args: t('key', arg0, arg1)
 * Placeholders: {0}, {1}, etc.
 */
export function t(key, ...args) {
  const str = (I18N[_lang] && I18N[_lang][key]) || I18N.zh[key] || key;
  if (!args.length) return str;
  return str.replace(/\{(\d+)\}/g, (_, i) => (args[+i] != null ? args[+i] : ''));
}

/** Current language code ('zh' or 'en'). */
export function getLang() { return _lang; }

/**
 * Switch language and update all data-i18n elements in the DOM.
 */
export function setLang(lang) {
  if (lang !== 'zh' && lang !== 'en') return;
  _lang = lang;
  localStorage.setItem('chatview-lang', lang);
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  applyLang();
}

/**
 * Re-apply current language to all tagged DOM elements.
 * Call after dynamic content is rendered.
 */
export function applyLang() {
  document.documentElement.lang = _lang === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    el.title = t(el.dataset.i18nTitle);
  });
}
