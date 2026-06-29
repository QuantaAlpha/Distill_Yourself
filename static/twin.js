/**
 * Digital Twin — Cognitive Handbook UI
 * Rich streaming analysis + wiki-style navigation
 * Reuses evolve.js streaming patterns (tool groups, text blocks, thinking dots)
 */
(function () {
  "use strict";

  // ── Cognitive Avatar ──
  // Persona ID → PNG slug mapping (16 personas, variant "a" default)
  const PERSONA_SLUGS = {
    P01: "deep-researcher", P02: "feedback-iterator", P03: "systems-architect",
    P04: "skeptical-debugger", P05: "minimal-decision-maker", P06: "chaotic-creative-maker",
    P07: "taste-curator", P08: "evidence-analyst", P09: "human-centered-facilitator",
    P10: "consensus-translator", P11: "ai-orchestrator", P12: "explorer-strategist",
    P13: "reliable-operator", P14: "quiet-engineer", P15: "contrarian-reframer",
    P16: "tone-calibrator",
  };
  const USER_PERSONA_SELECTION_KEY = "twin:user-persona-selection:v1";
  const COGNITIVE_MODEL_OPTIONS = [
    { id: "cm_001", name: "问题定界者", personaId: "P03", personaName: "系统架构者" },
    { id: "cm_002", name: "本质追问者", personaId: "P15", personaName: "反常识重构者" },
    { id: "cm_003", name: "隐含前提拆解者", personaId: "P15", personaName: "反常识重构者" },
    { id: "cm_004", name: "语境敏感者", personaId: "P09", personaName: "人本协调者" },
    { id: "cm_005", name: "边界敏感者", personaId: "P03", personaName: "系统架构者" },
    { id: "cm_006", name: "问题重构者", personaId: "P15", personaName: "反常识重构者" },
    { id: "cm_007", name: "因果追踪者", personaId: "P01", personaName: "深度研究者" },
    { id: "cm_008", name: "第一性原理者", personaId: "P15", personaName: "反常识重构者" },
    { id: "cm_009", name: "结构推演者", personaId: "P03", personaName: "系统架构者" },
    { id: "cm_010", name: "模式归纳者", personaId: "P08", personaName: "证据分析者" },
    { id: "cm_011", name: "类比迁移者", personaId: "P06", personaName: "混沌创意建造者" },
    { id: "cm_012", name: "约束反推者", personaId: "P05", personaName: "极简决策者" },
    { id: "cm_013", name: "稳妥决策者", personaId: "P13", personaName: "可靠运营者" },
    { id: "cm_014", name: "风险收敛者", personaId: "P04", personaName: "怀疑型调试者" },
    { id: "cm_015", name: "证据锚定者", personaId: "P08", personaName: "证据分析者" },
    { id: "cm_016", name: "最小代价选择者", personaId: "P05", personaName: "极简决策者" },
    { id: "cm_017", name: "长期权衡者", personaId: "P03", personaName: "系统架构者" },
    { id: "cm_018", name: "可逆试错者", personaId: "P02", personaName: "反馈迭代者" },
    { id: "cm_019", name: "复杂度克制者", personaId: "P05", personaName: "极简决策者" },
    { id: "cm_020", name: "本质极简者", personaId: "P05", personaName: "极简决策者" },
    { id: "cm_021", name: "冗余厌恶者", personaId: "P05", personaName: "极简决策者" },
    { id: "cm_022", name: "秩序建立者", personaId: "P13", personaName: "可靠运营者" },
    { id: "cm_023", name: "结构收束者", personaId: "P03", personaName: "系统架构者" },
    { id: "cm_024", name: "依赖敏感者", personaId: "P03", personaName: "系统架构者" },
    { id: "cm_025", name: "可控性优先者", personaId: "P13", personaName: "可靠运营者" },
    { id: "cm_026", name: "验证闭环者", personaId: "P14", personaName: "安静工程师" },
    { id: "cm_027", name: "异常预判者", personaId: "P04", personaName: "怀疑型调试者" },
    { id: "cm_028", name: "失控厌恶者", personaId: "P13", personaName: "可靠运营者" },
    { id: "cm_029", name: "后果敏感者", personaId: "P09", personaName: "人本协调者" },
    { id: "cm_030", name: "失败预演者", personaId: "P04", personaName: "怀疑型调试者" },
    { id: "cm_031", name: "小步推进者", personaId: "P02", personaName: "反馈迭代者" },
    { id: "cm_032", name: "稳态执行者", personaId: "P13", personaName: "可靠运营者" },
    { id: "cm_033", name: "闭环完成者", personaId: "P13", personaName: "可靠运营者" },
    { id: "cm_034", name: "路径校准者", personaId: "P02", personaName: "反馈迭代者" },
    { id: "cm_035", name: "目标反推者", personaId: "P12", personaName: "探索战略者" },
    { id: "cm_036", name: "实用落地者", personaId: "P13", personaName: "可靠运营者" },
    { id: "cm_037", name: "噪声过滤者", personaId: "P05", personaName: "极简决策者" },
    { id: "cm_038", name: "信息压缩者", personaId: "P08", personaName: "证据分析者" },
    { id: "cm_039", name: "信号捕捉者", personaId: "P08", personaName: "证据分析者" },
    { id: "cm_040", name: "细节校准者", personaId: "P14", personaName: "安静工程师" },
    { id: "cm_041", name: "重点提炼者", personaId: "P05", personaName: "极简决策者" },
    { id: "cm_042", name: "脉络梳理者", personaId: "P01", personaName: "深度研究者" },
    { id: "cm_043", name: "实质锚定者", personaId: "P05", personaName: "极简决策者" },
    { id: "cm_044", name: "克制表达者", personaId: "P16", personaName: "语气校准者" },
    { id: "cm_045", name: "清晰度维护者", personaId: "P09", personaName: "人本协调者" },
    { id: "cm_046", name: "语言密度追求者", personaId: "P05", personaName: "极简决策者" },
    { id: "cm_047", name: "结构表达者", personaId: "P03", personaName: "系统架构者" },
    { id: "cm_048", name: "质感表达者", personaId: "P07", personaName: "审美策展者" },
  ];
  const AVATAR_STYLE_OPTIONS = [
    { avatarId: "P01-A", personaId: "P01", personaName: "深度研究者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p01-a-deep-researcher.png" },
    { avatarId: "P01-B", personaId: "P01", personaName: "深度研究者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p01-b-deep-researcher.png" },
    { avatarId: "P02-A", personaId: "P02", personaName: "反馈迭代者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p02-a-feedback-iterator.png" },
    { avatarId: "P02-B", personaId: "P02", personaName: "反馈迭代者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p02-b-feedback-iterator.png" },
    { avatarId: "P03-A", personaId: "P03", personaName: "系统架构者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p03-a-systems-architect.png" },
    { avatarId: "P03-B", personaId: "P03", personaName: "系统架构者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p03-b-systems-architect.png" },
    { avatarId: "P04-A", personaId: "P04", personaName: "怀疑型调试者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p04-a-skeptical-debugger.png" },
    { avatarId: "P04-B", personaId: "P04", personaName: "怀疑型调试者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p04-b-skeptical-debugger.png" },
    { avatarId: "P05-A", personaId: "P05", personaName: "极简决策者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p05-a-minimal-decision-maker.png" },
    { avatarId: "P05-B", personaId: "P05", personaName: "极简决策者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p05-b-minimal-decision-maker.png" },
    { avatarId: "P06-A", personaId: "P06", personaName: "混沌创意建造者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p06-a-chaotic-creative-maker.png" },
    { avatarId: "P06-B", personaId: "P06", personaName: "混沌创意建造者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p06-b-chaotic-creative-maker.png" },
    { avatarId: "P07-A", personaId: "P07", personaName: "审美策展者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p07-a-taste-curator.png" },
    { avatarId: "P07-B", personaId: "P07", personaName: "审美策展者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p07-b-taste-curator.png" },
    { avatarId: "P08-A", personaId: "P08", personaName: "证据分析者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p08-a-evidence-analyst.png" },
    { avatarId: "P08-B", personaId: "P08", personaName: "证据分析者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p08-b-evidence-analyst.png" },
    { avatarId: "P09-A", personaId: "P09", personaName: "人本协调者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p09-a-human-centered-facilitator.png" },
    { avatarId: "P09-B", personaId: "P09", personaName: "人本协调者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p09-b-human-centered-facilitator.png" },
    { avatarId: "P10-A", personaId: "P10", personaName: "共识翻译者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p10-a-consensus-translator.png" },
    { avatarId: "P10-B", personaId: "P10", personaName: "共识翻译者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p10-b-consensus-translator.png" },
    { avatarId: "P11-A", personaId: "P11", personaName: "AI 编排者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p11-a-ai-orchestrator.png" },
    { avatarId: "P11-B", personaId: "P11", personaName: "AI 编排者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p11-b-ai-orchestrator.png" },
    { avatarId: "P12-A", personaId: "P12", personaName: "探索战略者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p12-a-explorer-strategist.png" },
    { avatarId: "P12-B", personaId: "P12", personaName: "探索战略者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p12-b-explorer-strategist.png" },
    { avatarId: "P13-A", personaId: "P13", personaName: "可靠运营者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p13-a-reliable-operator.png" },
    { avatarId: "P13-B", personaId: "P13", personaName: "可靠运营者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p13-b-reliable-operator.png" },
    { avatarId: "P14-A", personaId: "P14", personaName: "安静工程师", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p14-a-quiet-engineer.png" },
    { avatarId: "P14-B", personaId: "P14", personaName: "安静工程师", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p14-b-quiet-engineer.png" },
    { avatarId: "P15-A", personaId: "P15", personaName: "反常识重构者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p15-a-contrarian-reframer.png" },
    { avatarId: "P15-B", personaId: "P15", personaName: "反常识重构者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p15-b-contrarian-reframer.png" },
    { avatarId: "P16-A", personaId: "P16", personaName: "语气校准者", styleName: "风格 A", image: "assets/cognitive-avatars/v2/images/p16-a-tone-calibrator.png" },
    { avatarId: "P16-B", personaId: "P16", personaName: "语气校准者", styleName: "风格 B", image: "assets/cognitive-avatars/v2/images/p16-b-tone-calibrator.png" },
  ];
  let cachedAvatarSelection = null;
  let userPersonaSelection = loadUserPersonaSelection();
  let currentPersonaTraits = [];

  function personaAvatarPath(personaId) {
    const slug = PERSONA_SLUGS[personaId] || "systems-architect";
    const num = (personaId || "P03").replace("P", "").padStart(2, "0");
    return `assets/cognitive-avatars/v2/images/p${num}-a-${slug}.png`;
  }

  function loadUserPersonaSelection() {
    try {
      const raw = localStorage.getItem(USER_PERSONA_SELECTION_KEY);
      const parsed = raw ? JSON.parse(raw) : null;
      if (parsed && parsed.avatarId) return parsed;
      if (parsed && parsed.modelId) {
        const model = findModelOption(parsed.modelId);
        return model ? { avatarId: `${model.personaId}-A` } : null;
      }
      return null;
    } catch {
      return null;
    }
  }

  function saveUserPersonaSelection(option) {
    userPersonaSelection = option ? { avatarId: option.avatarId } : null;
    try {
      if (userPersonaSelection) {
        localStorage.setItem(USER_PERSONA_SELECTION_KEY, JSON.stringify(userPersonaSelection));
      } else {
        localStorage.removeItem(USER_PERSONA_SELECTION_KEY);
      }
    } catch {
      // Ignore storage failures; the in-memory choice still updates this view.
    }
  }

  function findModelOption(modelId) {
    return COGNITIVE_MODEL_OPTIONS.find(o => o.id === modelId) || null;
  }

  function findAvatarOption(avatarId) {
    return AVATAR_STYLE_OPTIONS.find(o => o.avatarId === avatarId) || null;
  }

  function avatarOptionForPersona(personaId) {
    return AVATAR_STYLE_OPTIONS.find(o => o.personaId === personaId && o.avatarId.endsWith("-A"))
      || AVATAR_STYLE_OPTIONS.find(o => o.personaId === personaId)
      || null;
  }

  function groupAvatarOptions() {
    const groups = [];
    for (const option of AVATAR_STYLE_OPTIONS) {
      let group = groups.find(g => g.personaId === option.personaId);
      if (!group) {
        group = { personaId: option.personaId, personaName: option.personaName, options: [] };
        groups.push(group);
      }
      group.options.push(option);
    }
    return groups;
  }

  function renderPersonaAvatar(traits, avatarSelection) {
    const titleEl = document.getElementById("twin-persona-title");
    const subtitleEl = document.getElementById("twin-persona-subtitle");
    const traitsEl = document.getElementById("twin-persona-traits");
    const imgEl = document.getElementById("twin-persona-img");
    const avatarEl = document.getElementById("twin-persona-avatar");
    const avatarHintEl = document.getElementById("twin-persona-card-hint");
    const personaCardEl = document.getElementById("twin-persona-card");
    if (!titleEl || !subtitleEl || !traitsEl) return;
    if (personaCardEl) {
      personaCardEl.onclick = () => loadRuntimePreview();
      personaCardEl.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          loadRuntimePreview();
        }
      };
    }
    if (avatarEl) {
      avatarEl.onclick = (e) => {
        e.stopPropagation();
        openPersonaOptions();
      };
      avatarEl.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          e.stopPropagation();
          openPersonaOptions();
        }
      };
    }
    if (avatarHintEl) {
      avatarHintEl.onclick = (e) => {
        e.stopPropagation();
        openPersonaOptions();
      };
    }

    currentPersonaTraits = traits || [];
    const topTraits = (traits || []).slice(0, 3);
    traitsEl.innerHTML = topTraits.length
      ? topTraits.map(t => `<span>${esc(t.name || t.category || _tt("twin.trait.fallback"))}</span>`).join("")
      : `<span>${esc(_tt("twin.trait.waiting"))}</span>`;

    // Default avatar shown during loading
    const defaultAvatar = personaAvatarPath("P03");

    const sel = avatarSelection || cachedAvatarSelection;
    const manualOption = userPersonaSelection ? findAvatarOption(userPersonaSelection.avatarId) : null;
    const selectedAvatarPath = manualOption ? manualOption.image : null;

    if (sel && sel.persona_id) {
      titleEl.textContent = sel.persona_title || sel.model_name || _tt("twin.persona.model");
      subtitleEl.textContent = sel.rationale || "";
      if (imgEl) {
        imgEl.src = selectedAvatarPath || personaAvatarPath(sel.persona_id);
        imgEl.alt = manualOption ? `${manualOption.personaName} ${manualOption.styleName}` : (sel.persona_title || sel.model_name || "");
      }
      cachedAvatarSelection = sel;
      renderPersonaOptions(sel, manualOption ? manualOption.avatarId : "");
      return;
    }

    titleEl.textContent = _tt("twin.persona.model");
    subtitleEl.textContent = traits && traits.length ? _tt("twin.persona.matching") : _tt("twin.trait.waiting");
    if (imgEl) { imgEl.src = selectedAvatarPath || defaultAvatar; imgEl.alt = manualOption ? `${manualOption.personaName} ${manualOption.styleName}` : ""; }
    renderPersonaOptions(sel, manualOption ? manualOption.avatarId : "");

    if (traits && traits.length) {
      fetch("/api/twin/avatar-selection")
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (data && data.persona_id) {
            cachedAvatarSelection = data;
            renderPersonaAvatar(traits, data);
          } else {
            subtitleEl.textContent = _tt("twin.persona.matchHint");
          }
        })
        .catch(() => { subtitleEl.textContent = _tt("twin.persona.matchHint"); });
    }
  }

  function renderPersonaOptions(avatarSelection, selectedAvatarId) {
    const container = document.getElementById("twin-persona-options");
    if (!container) return;
    const aiAvatar = avatarSelection && avatarSelection.persona_id
      ? avatarOptionForPersona(avatarSelection.persona_id)
      : null;
    const aiAvatarId = aiAvatar ? aiAvatar.avatarId : "";
    const manualAvatarId = userPersonaSelection ? userPersonaSelection.avatarId : "";
    const activeAvatarId = selectedAvatarId || manualAvatarId || aiAvatarId;

    container.innerHTML = `<div class="twin-persona-options-backdrop" data-close-persona-options></div>
      <div class="twin-persona-options-panel">
        <div class="twin-persona-options-head">
          <div>
            <div id="twin-persona-options-title">${esc(_tt("twin.persona.optionsTitle"))}</div>
            <div class="twin-persona-options-subtitle">${esc(_tt("twin.persona.optionsSubtitle"))}</div>
          </div>
          <div class="twin-persona-options-actions">
            ${manualAvatarId ? `<button type="button" id="twin-persona-reset">${esc(_tt("twin.persona.useAi"))}</button>` : ""}
            <button type="button" id="twin-persona-close" aria-label="${esc(_tt("twin.persona.close"))}">×</button>
          </div>
        </div>
        <div class="twin-persona-option-grid">
          ${groupAvatarOptions().map(group => `<section class="twin-persona-group" data-persona-id="${esc(group.personaId)}">
            <div class="twin-persona-group-title">${esc(group.personaName)}</div>
            <div class="twin-persona-style-options">
              ${group.options.map(option => {
                const active = option.avatarId === activeAvatarId ? " active" : "";
                const styleLabel = _styleName(option.avatarId);
                const aiMatched = option.avatarId === aiAvatarId ? `<span class="twin-persona-badge">${esc(_tt("twin.persona.badgeAi"))}</span>` : "";
                const selected = option.avatarId === manualAvatarId ? `<span class="twin-persona-badge selected">${esc(_tt("twin.persona.badgeSelected"))}</span>` : "";
                return `<button type="button" class="twin-persona-option${active}" data-avatar-id="${esc(option.avatarId)}">
                  <img src="${esc(option.image)}" alt="${esc(option.personaName)} ${esc(styleLabel)}">
                  <span class="twin-persona-option-persona">${esc(styleLabel)}</span>
                  ${selected || aiMatched}
                </button>`;
              }).join("")}
            </div>
          </section>`).join("")}
        </div>
      </div>`;

    const resetBtn = document.getElementById("twin-persona-reset");
    if (resetBtn) {
      resetBtn.onclick = () => {
        saveUserPersonaSelection(null);
        renderPersonaAvatar(currentPersonaTraits, cachedAvatarSelection);
        closePersonaOptions();
      };
    }
    const closeBtn = document.getElementById("twin-persona-close");
    if (closeBtn) closeBtn.onclick = closePersonaOptions;
    container.querySelectorAll("[data-close-persona-options]").forEach(el => {
      el.onclick = closePersonaOptions;
    });
    container.querySelectorAll(".twin-persona-option").forEach(btn => {
      btn.onclick = () => {
        const option = findAvatarOption(btn.getAttribute("data-avatar-id"));
        if (!option) return;
        saveUserPersonaSelection(option);
        renderPersonaAvatar(currentPersonaTraits, cachedAvatarSelection);
        closePersonaOptions();
      };
    });
  }

  function openPersonaOptions() {
    const container = document.getElementById("twin-persona-options");
    if (!container) return;
    if (!container.innerHTML.trim()) {
      renderPersonaOptions(cachedAvatarSelection, userPersonaSelection ? userPersonaSelection.avatarId : "");
    }
    container.classList.remove("hidden");
    container.setAttribute("aria-hidden", "false");
  }

  function closePersonaOptions() {
    const container = document.getElementById("twin-persona-options");
    if (!container) return;
    container.classList.add("hidden");
    container.setAttribute("aria-hidden", "true");
  }

  function isPersonaOptionsOpen() {
    const container = document.getElementById("twin-persona-options");
    return Boolean(container && !container.classList.contains("hidden"));
  }

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

  // ── i18n (UI shell only; persona/avatar/AI data never translated) ──
  let _i18nRegistered = false;
  function _registerTwinI18n() {
    if (_i18nRegistered || !window.registerI18n) return;
    _i18nRegistered = true;
    window.registerI18n({
      zh: {
        "twin.trait.waiting": "等待分析",
        "twin.trait.fallback": "认知特质",
        "twin.persona.model": "认知模型",
        "twin.persona.matching": "匹配中...",
        "twin.persona.matchHint": "点击 Analyze 后匹配认知模型",
        "twin.persona.optionsTitle": "选择头像风格",
        "twin.persona.optionsSubtitle": "相同头像已合并；同一视觉画像的不同风格会分别展示。",
        "twin.persona.useAi": "使用 AI 匹配",
        "twin.persona.close": "关闭",
        "twin.persona.badgeAi": "AI 匹配",
        "twin.persona.badgeSelected": "已选择",
        "twin.persona.styleA": "风格 A",
        "twin.persona.styleB": "风格 B",
        "twin.bc.analyzing": "分析中…",
        "twin.btn.viewOverview": "📋 查看概览",
        "twin.btn.viewProgress": "📊 查看进度",
        "twin.status.stopped": "已停止",
        "twin.btn.stop": "■ Stop",
        "twin.btn.analyze": "🔄 Analyze",
        "twin.btn.progress": "📊 查看进度",
        "twin.btn.sync": "📤 Sync",
        "twin.records": "{n} 条认知记录",
        "twin.node.events": "📝 {n} 事件",
        "twin.node.cards": "🃏 {n} 判断卡",
        "twin.node.traits": "🧬 {n} 认知特质",
        "twin.empty.events": "暂无事件。点击 Analyze 开始提取。",
        "twin.empty.cards": "暂无判断卡。",
        "twin.empty.traits": "暂无认知特质。",
        "twin.empty.traitData": "暂无数据",
        "twin.overview.startHint": "点击 <b>Analyze</b> 开始从对话历史中提取认知模型",
        "twin.overview.pipeline": "4 阶段流水线：事件提取 → 判断卡蒸馏 → 认知特质归纳 → Runtime 编译",
        "twin.count": "{n} 条",
        "twin.empty.eventsShort": "暂无事件。",
        "twin.field.reaction": "反应:",
        "twin.field.lesson": "教训:",
        "twin.cards.title": "判断卡",
        "twin.empty.cardsData": "暂无数据。点击 Analyze 开始提取。",
        "twin.card.heading": "🃏 判断卡",
        "twin.field.appliesWhen": "触发场景：",
        "twin.field.judgment": "用户判断逻辑：",
        "twin.field.agentAction": "AI 行动：",
        "twin.field.exceptions": "例外：",
        "twin.card.supportEvents": "📎 支撑事件 ({n})",
        "twin.card.viewSession": "查看原始会话 →",
        "twin.card.relatedCards": "🔗 关联卡片 ({n})",
        "twin.traits.allTitle": "全部认知特质",
        "twin.traits.fallbackCat": "特质",
        "twin.empty.traitsData": "暂无数据。点击 Analyze 开始提取。",
        "twin.trait.supportCards": "🃏 支撑判断卡 ({n})",
        "twin.status.aiStarting": "AI 启动中…",
        "twin.bc.done": "分析完成 ✅",
        "twin.bc.failed": "分析失败，请检查错误并重试",
        "twin.status.aiRunning": "AI 执行中… ({n} steps)",
        "twin.status.aiGenerating": "AI 分析生成中…",
        "twin.runtime.desc": "将判断卡与认知特质压缩成下一次会话可读取的上下文包。",
        "twin.sync.confirm": "将Distill Yourself同步到 CLAUDE.md？",
        "twin.sync.success": "同步完成：{cards} 判断卡 + {traits} 认知特质已写入",
        "twin.sync.failed": "同步失败：{error}",
        "twin.lastAnalyzed.never": "尚未分析",
        "twin.persona.cardTitle": "点击打开 Runtime Pack",
        "twin.persona.avatarTitle": "选择认知类型",
        "twin.persona.kicker": "Cognitive Model",
        "twin.persona.waitTitle": "等待认知模型",
        "twin.persona.waitSubtitle": "点击 Analyze 后匹配认知模型",
        "twin.persona.changeAvatar": "Change avatar →",
        "twin.node.runtime": "📦 Runtime",
        "twin.stage.events.title": "证据事件",
        "twin.stage.events.cta": "浏览全部 →",
        "twin.stage.cards.title": "判断卡",
        "twin.stage.cards.cta": "查看全部 →",
        "twin.stage.traits.title": "认知特质",
        "twin.stage.traits.cta": "查看全部 →",
        "twin.stage.runtime.title": "Runtime Pack",
        "twin.stage.runtime.cta": "打开预览 →",
        "twin.connector.distilled": "↓ 蒸馏为",
        "twin.connector.generalized": "↓ 归纳为",
        "twin.connector.compiled": "↓ 编译为",
        "twin.more.events": "+{n} 个更多事件",
        "twin.more.cards": "+{n} 张更多判断卡",
        "twin.card.eventCount": "{n} 个事件",
        "twin.runtime.ready": "就绪",
        "twin.runtime.noData": "暂无数据",
        "twin.runtime.info": "已编译的上下文包",
        "twin.runtime.metricCards": "判断卡",
        "twin.runtime.metricTraits": "认知特质",
        "twin.runtime.target": "目标",
        "twin.runtime.openHint": "点击卡片预览 →",
      },
      en: {
        "twin.trait.waiting": "Awaiting analysis",
        "twin.trait.fallback": "Cognitive trait",
        "twin.persona.model": "Cognitive Model",
        "twin.persona.matching": "Matching...",
        "twin.persona.matchHint": "Click Analyze to match a cognitive model",
        "twin.persona.optionsTitle": "Choose avatar style",
        "twin.persona.optionsSubtitle": "Identical avatars are merged; different styles of the same visual persona are shown separately.",
        "twin.persona.useAi": "Use AI match",
        "twin.persona.close": "Close",
        "twin.persona.badgeAi": "AI match",
        "twin.persona.badgeSelected": "Selected",
        "twin.persona.styleA": "Style A",
        "twin.persona.styleB": "Style B",
        "twin.bc.analyzing": "Analyzing…",
        "twin.btn.viewOverview": "📋 View overview",
        "twin.btn.viewProgress": "📊 View progress",
        "twin.status.stopped": "Stopped",
        "twin.btn.stop": "■ Stop",
        "twin.btn.analyze": "🔄 Analyze",
        "twin.btn.progress": "📊 View progress",
        "twin.btn.sync": "📤 Sync",
        "twin.records": "{n} cognitive records",
        "twin.node.events": "📝 {n} events",
        "twin.node.cards": "🃏 {n} cards",
        "twin.node.traits": "🧬 {n} traits",
        "twin.empty.events": "No events yet. Click Analyze to start extracting.",
        "twin.empty.cards": "No judgment cards yet.",
        "twin.empty.traits": "No cognitive traits yet.",
        "twin.empty.traitData": "No data",
        "twin.overview.startHint": "Click <b>Analyze</b> to extract your cognitive model from conversation history",
        "twin.overview.pipeline": "4-stage pipeline: event extraction → card distillation → trait generalization → Runtime compile",
        "twin.count": "{n}",
        "twin.empty.eventsShort": "No events yet.",
        "twin.field.reaction": "Reaction:",
        "twin.field.lesson": "Lesson:",
        "twin.cards.title": "Judgment Cards",
        "twin.empty.cardsData": "No data. Click Analyze to start extracting.",
        "twin.card.heading": "🃏 Judgment Card",
        "twin.field.appliesWhen": "Applies when: ",
        "twin.field.judgment": "User judgment: ",
        "twin.field.agentAction": "AI action: ",
        "twin.field.exceptions": "Exceptions: ",
        "twin.card.supportEvents": "📎 Supporting events ({n})",
        "twin.card.viewSession": "View original session →",
        "twin.card.relatedCards": "🔗 Related cards ({n})",
        "twin.traits.allTitle": "All cognitive traits",
        "twin.traits.fallbackCat": "Trait",
        "twin.empty.traitsData": "No data. Click Analyze to start extracting.",
        "twin.trait.supportCards": "🃏 Supporting cards ({n})",
        "twin.status.aiStarting": "AI starting…",
        "twin.bc.done": "Analysis complete ✅",
        "twin.bc.failed": "Analysis failed, please check the error and retry",
        "twin.status.aiRunning": "AI running… ({n} steps)",
        "twin.status.aiGenerating": "AI generating analysis…",
        "twin.runtime.desc": "Compresses judgment cards and cognitive traits into a context package readable by the next session.",
        "twin.sync.confirm": "Sync Distill Yourself to CLAUDE.md?",
        "twin.sync.success": "Sync complete: {cards} cards + {traits} traits written",
        "twin.sync.failed": "Sync failed: {error}",
        "twin.lastAnalyzed.never": "Not analyzed yet",
        "twin.persona.cardTitle": "Click to open Runtime Pack",
        "twin.persona.avatarTitle": "Choose cognitive type",
        "twin.persona.kicker": "Cognitive Model",
        "twin.persona.waitTitle": "Awaiting cognitive model",
        "twin.persona.waitSubtitle": "Click Analyze to match a cognitive model",
        "twin.persona.changeAvatar": "Change avatar →",
        "twin.node.runtime": "📦 Runtime",
        "twin.stage.events.title": "Evidence Events",
        "twin.stage.events.cta": "Browse all →",
        "twin.stage.cards.title": "Judgment Cards",
        "twin.stage.cards.cta": "View all →",
        "twin.stage.traits.title": "Cognitive Traits",
        "twin.stage.traits.cta": "View all →",
        "twin.stage.runtime.title": "Runtime Pack",
        "twin.stage.runtime.cta": "Open preview →",
        "twin.connector.distilled": "↓ distilled into",
        "twin.connector.generalized": "↓ generalized to",
        "twin.connector.compiled": "↓ compiled to",
        "twin.more.events": "+{n} more events",
        "twin.more.cards": "+{n} more cards",
        "twin.card.eventCount": "{n} events",
        "twin.runtime.ready": "Ready",
        "twin.runtime.noData": "No data",
        "twin.runtime.info": "Compiled context package",
        "twin.runtime.metricCards": "Cards",
        "twin.runtime.metricTraits": "Traits",
        "twin.runtime.target": "Target",
        "twin.runtime.openHint": "Click card to preview →",
      },
    });
  }

  function _tt(key, vars) {
    return window.t ? window.t(key, vars) : key;
  }

  function _styleName(avatarId) {
    return _tt((avatarId || "").endsWith("-B") ? "twin.persona.styleB" : "twin.persona.styleA");
  }

  // ── State ──
  let overviewData = null;
  let analysisAbort = null;
  let analysisRunning = false;
  let eventsInited = false;
  let currentView = "overview"; // "overview" | "cards" | "card-detail" | "traits" | "trait-detail" | "analyzing"
  let _activeRunId = "";
  try {
    const _storedRunId = localStorage.getItem("twin-active-run-id");
    if (_storedRunId) _activeRunId = _storedRunId;
  } catch (e) {}

  function _withRunId(url) {
    if (!_activeRunId) return url;
    const sep = url.includes("?") ? "&" : "?";
    return url + sep + "run_id=" + encodeURIComponent(_activeRunId);
  }

  // ── Init ──
  window.initTwinView = function () {
    _registerTwinI18n();
    if (!eventsInited) { bindEvents(); eventsInited = true; }
    if (currentView === "analyzing") {
      _showOnlyView("analysis");
      _updateAnalyzeButton();
      return;
    }
    if (!_activeRunId) {
      // Resolve default run scope first, then load overview exactly once.
      fetch("/api/twin/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      })
        .then(r => r.json())
        .then((d) => {
          if (d && d.ok && d.run && d.run.run_id) {
            _activeRunId = d.run.run_id;
            try { localStorage.setItem("twin-active-run-id", _activeRunId); } catch (e) {}
          }
        })
        .catch(() => {})
        .finally(() => { loadOverview(); });
    } else {
      loadOverview();
    }
    _updateAnalyzeButton();
  };

  // Re-render UI-shell strings on language change without interrupting a running analysis.
  let _localeListenerBound = false;
  if (!_localeListenerBound) {
    _localeListenerBound = true;
    window.addEventListener("localechange", () => {
      _registerTwinI18n();
      if (window.applyI18nDom) window.applyI18nDom(document);
      if (analysisRunning) {
        // Analysis in progress: only refresh shell labels, don't restart the stream.
        _updateAnalyzeButton();
      } else if (window.initTwinView) {
        window.initTwinView();
      }
    });
  }

  function bindEvents() {
    const btnAnalyze = document.getElementById("twin-btn-analyze");
    const btnSync = document.getElementById("twin-btn-sync");
    const btnProgress = document.getElementById("twin-btn-progress");
    if (btnAnalyze) btnAnalyze.onclick = () => {
      if (analysisRunning && analysisAbort) { _stopAnalysis(); } else { startAnalysis(); }
    };
    if (btnSync) btnSync.onclick = startSync;
    if (btnProgress) btnProgress.onclick = toggleProgressView;
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !isPersonaOptionsOpen()) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      closePersonaOptions();
    }, true);
  }

  /** Toggle between analysis progress view and overview */
  function toggleProgressView() {
    if (currentView === "analyzing") {
      loadOverview();
    } else {
      currentView = "analyzing";
      _showOnlyView("analysis");
      setBreadcrumb([{ label: _tt("twin.bc.analyzing") }]);
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
    toggle("twin-persona-card", name === "overview");
    _updateProgressButton();
  }

  /** Update analyze button and progress toggle to reflect current state */
  function _updateAnalyzeButton() {
    const btn = document.getElementById("twin-btn-analyze");
    const updatedEl = document.getElementById("twin-last-analyzed");
    if (analysisRunning) {
      if (btn) { btn.disabled = false; btn.textContent = _tt("twin.btn.stop"); btn.classList.add("btn-stop"); }
      if (updatedEl) updatedEl.classList.add("loading");
    } else {
      if (btn) { btn.disabled = false; btn.textContent = _tt("twin.btn.analyze"); btn.classList.remove("btn-stop"); }
      if (updatedEl) updatedEl.classList.remove("loading");
    }
    _updateProgressButton();
  }

  function _updateProgressButton() {
    const btnProgress = document.getElementById("twin-btn-progress");
    if (!btnProgress) return;
    if (analysisRunning) {
      btnProgress.classList.remove("hidden");
      btnProgress.textContent = currentView === "analyzing" ? _tt("twin.btn.viewOverview") : _tt("twin.btn.viewProgress");
    } else {
      btnProgress.classList.add("hidden");
    }
  }

  function _stopAnalysis() {
    if (analysisAbort) analysisAbort.abort();
    if (_activeRunId) {
      fetch("/api/twin/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: _activeRunId }),
      }).catch(() => {});
    }
    // Don't null analysisAbort here — let .catch/.finally do cleanup
    // (otherwise the stale-callback guard blocks state reset)
    analysisRunning = false;
    _updateAnalyzeButton();
    _restoreOverviewAfterStoppedAnalysis();
    const updatedEl = document.getElementById("twin-last-analyzed");
    if (updatedEl) { updatedEl.textContent = _tt("twin.status.stopped"); updatedEl.classList.remove("loading"); }
  }

  function _restoreOverviewAfterStoppedAnalysis() {
    const progress = document.getElementById("twin-analysis-progress");
    if (progress) progress.innerHTML = "";
    if (overviewData) {
      renderOverview(overviewData);
    } else {
      loadOverview();
    }
  }

  // ── Overview: Vertical Pipeline Layout ──
  function loadOverview() {
    fetch(_withRunId("/api/twin/overview"))
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

    // Render persona avatar (uses cached selection or lazy-fetches)
    renderPersonaAvatar(traitItems, data.avatar_selection || null);

    if (evtCount === 0 && cardCount === 0 && traitCount === 0) {
      renderOverviewEmpty(); return;
    }

    const updatedEl = document.getElementById("twin-last-analyzed");
    if (updatedEl) updatedEl.textContent = _tt("twin.records", { n: evtCount + cardCount + traitCount });

    // ─── Pipeline Header ───
    let html = `<div class="twin-pipeline-header">
      <span class="twin-ph-node" data-layer="events">${esc(_tt("twin.node.events", { n: evtCount }))}</span>
      <span class="twin-ph-arrow">→</span>
      <span class="twin-ph-node" data-layer="cards">${esc(_tt("twin.node.cards", { n: cardCount }))}</span>
      <span class="twin-ph-arrow">→</span>
      <span class="twin-ph-node" data-layer="traits">${esc(_tt("twin.node.traits", { n: traitCount }))}</span>
      <span class="twin-ph-arrow">→</span>
      <span class="twin-ph-node" data-layer="runtime">${esc(_tt("twin.node.runtime"))}</span>
    </div>`;

    html += '<div class="twin-pipeline">';

    // ─── L1: Evidence Events ───
    html += `<div class="twin-stage" style="--stage-color:#3b82f6">
      <div class="twin-stage-marker">L1</div>
      <div class="twin-stage-card">
        <div class="twin-stage-header" data-nav="events">
          <span class="twin-stage-icon">📝</span>
          <span class="twin-stage-title">${esc(_tt("twin.stage.events.title"))}</span>
          <span class="twin-stage-count">${evtCount}</span>
          <span class="twin-stage-cta">${esc(_tt("twin.stage.events.cta"))}</span>
        </div>
        <div class="twin-stage-body">`;

    const evtItems = eventsInfo.items || [];
    if (evtItems.length === 0) {
      html += `<div class="twin-dim-empty">${esc(_tt("twin.empty.events"))}</div>`;
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
        html += `<div style="font-size:11px;color:var(--text-muted);margin-top:4px">${esc(_tt("twin.more.events", { n: evtCount - 3 }))}</div>`;
      }
    }
    html += `</div></div></div>`;
    html += `<div class="twin-stage-connector">${esc(_tt("twin.connector.distilled"))}</div>`;

    // ─── L2: Judgment Cards ───
    html += `<div class="twin-stage" style="--stage-color:#8b5cf6">
      <div class="twin-stage-marker">L2</div>
      <div class="twin-stage-card">
        <div class="twin-stage-header" data-nav="cards">
          <span class="twin-stage-icon">🃏</span>
          <span class="twin-stage-title">${esc(_tt("twin.stage.cards.title"))}</span>
          <span class="twin-stage-count">${cardCount}</span>
          <span class="twin-stage-cta">${esc(_tt("twin.stage.cards.cta"))}</span>
        </div>
        <div class="twin-stage-body">`;

    const cardItems = cardsInfo.items || [];
    if (cardItems.length === 0) {
      html += `<div class="twin-dim-empty">${esc(_tt("twin.empty.cards"))}</div>`;
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
            ${c.evidence_count ? `<span class="twin-ep-count">${esc(_tt("twin.card.eventCount", { n: c.evidence_count }))}</span>` : ""}
          </div>
          ${c.agent_action ? `<div class="twin-card-action">→ ${esc(truncate(c.agent_action, 50))}</div>` : ""}
        </div>`;
      }
      html += '</div>';
      if (cardCount > 4) {
        html += `<div style="font-size:11px;color:var(--text-muted);margin-top:8px;text-align:right">${esc(_tt("twin.more.cards", { n: cardCount - 4 }))}</div>`;
      }
    }
    html += `</div></div></div>`;
    html += `<div class="twin-stage-connector">${esc(_tt("twin.connector.generalized"))}</div>`;

    // ─── L3: Cognitive Traits ───
    html += `<div class="twin-stage" style="--stage-color:#14b8a6">
      <div class="twin-stage-marker">L3</div>
      <div class="twin-stage-card">
        <div class="twin-stage-header" data-nav="traits">
          <span class="twin-stage-icon">🧬</span>
          <span class="twin-stage-title">${esc(_tt("twin.stage.traits.title"))}</span>
          <span class="twin-stage-count">${traitCount}</span>
          <span class="twin-stage-cta">${esc(_tt("twin.stage.traits.cta"))}</span>
        </div>
        <div class="twin-stage-body">`;

    if (traitItems.length === 0) {
      html += `<div class="twin-dim-empty">${esc(_tt("twin.empty.traits"))}</div>`;
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
          html += `<div class="twin-trait-empty">${esc(_tt("twin.empty.traitData"))}</div>`;
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
    html += `<div class="twin-stage-connector">${esc(_tt("twin.connector.compiled"))}</div>`;

    // ─── L4: Runtime Pack ───
    const hasData = cardCount > 0 || traitCount > 0;
    const statusClass = hasData ? "ready" : "no-data";
    const statusText = hasData ? _tt("twin.runtime.ready") : _tt("twin.runtime.noData");
    html += `<div class="twin-stage" style="--stage-color:#f59e0b">
      <div class="twin-stage-marker">L4</div>
      <div class="twin-stage-card twin-stage-card-clickable" data-nav="sync" role="button" tabindex="0">
        <div class="twin-stage-header" data-nav="sync">
          <span class="twin-stage-icon">📦</span>
          <span class="twin-stage-title">${esc(_tt("twin.stage.runtime.title"))}</span>
          <span class="twin-stage-cta">${esc(_tt("twin.stage.runtime.cta"))}</span>
        </div>
        <div class="twin-stage-body">
          <div class="twin-runtime-panel">
            <div class="twin-runtime-state">
              <span class="twin-runtime-status ${statusClass}">${statusText}</span>
              <span class="twin-runtime-info">${esc(_tt("twin.runtime.info"))}</span>
            </div>
            <div class="twin-runtime-metrics" aria-label="Runtime Pack source counts">
              <span><b>${cardCount}</b><em>${esc(_tt("twin.runtime.metricCards"))}</em></span>
              <span><b>${traitCount}</b><em>${esc(_tt("twin.runtime.metricTraits"))}</em></span>
            </div>
            <div class="twin-runtime-target">
              <span class="twin-runtime-target-label">${esc(_tt("twin.runtime.target"))}</span>
              <span class="twin-runtime-target-file">CLAUDE.md</span>
              <span class="twin-runtime-open-hint">${esc(_tt("twin.runtime.openHint"))}</span>
            </div>
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
      el.onclick = (e) => {
        e.stopPropagation();
        const nav = el.dataset.nav;
        if (nav === "events") loadEventsList();
        else if (nav === "cards") loadCards();
        else if (nav === "traits") loadTraits();
        else if (nav === "sync") loadRuntimePreview();
      };
    });
    container.querySelectorAll(".twin-stage-card[data-nav]").forEach(el => {
      const open = () => {
        const nav = el.dataset.nav;
        if (nav === "sync") loadRuntimePreview();
      };
      el.onclick = open;
      el.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
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
    renderPersonaAvatar([]);
    const bar = document.getElementById("twin-stats-bar");
    if (bar) bar.innerHTML = "";
    container.innerHTML = `<div class="twin-empty-state">
      <p>🧠 Distill Yourself (Cognitive Handbook)</p>
      <p>${_tt("twin.overview.startHint")}</p>
      <p style="color:var(--text-muted);font-size:0.85em;margin-top:12px">
        ${esc(_tt("twin.overview.pipeline"))}
      </p>
    </div>`;
  }

  // ── Events List View ──
  function loadEventsList(signalFilter) {
    let url = "/api/twin/events?limit=200";
    if (signalFilter) url += `&signal_type=${encodeURIComponent(signalFilter)}`;
    fetch(_withRunId(url))
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
      <span class="twin-dim-count">${esc(_tt("twin.count", { n: items.length }))}</span>
    </div>
    <div class="twin-filter-chips">
      ${filters.map(f => `<span class="twin-filter-chip ${(!activeFilter && f === "all") || activeFilter === f ? "active" : ""}" data-filter="${f}">${f}</span>`).join("")}
    </div>
    <div class="twin-detail-list" style="margin-top:12px">`;

    if (items.length === 0) {
      html += `<div class="twin-dim-empty" style="padding:24px">${esc(_tt("twin.empty.eventsShort"))}</div>`;
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
          <div><b>${esc(_tt("twin.field.reaction"))}</b> ${esc(truncate(e.user_reaction, 120))}</div>
          ${e.lesson ? `<div><b>${esc(_tt("twin.field.lesson"))}</b> ${esc(e.lesson)}</div>` : ""}
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
    fetch(_withRunId("/api/twin/cards?limit=200"))
      .then(r => r.json())
      .then(data => renderCards(data.cards || []))
      .catch(e => console.error("Failed to load cards:", e));
  }

  function renderCards(items) {
    currentView = "cards";
    _showOnlyView("dimension");
    const container = document.getElementById("twin-detail");
    setBreadcrumb([{ label: _tt("twin.cards.title"), onclick: () => loadCards() }]);

    let html = `<div class="twin-detail-header" style="--dim-color:#1d4ed8">
      <span class="twin-dim-icon">🃏</span>
      <span class="twin-detail-title">${esc(_tt("twin.cards.title"))}</span>
      <span class="twin-dim-count">${esc(_tt("twin.count", { n: items.length }))}</span>
    </div>
    <div class="twin-detail-list">`;

    if (items.length === 0) {
      html += `<div class="twin-dim-empty" style="padding:24px">${esc(_tt("twin.empty.cardsData"))}</div>`;
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
      { label: _tt("twin.cards.title"), onclick: () => loadCards() },
      { label: card.id || "detail" },
    ]);

    const conf = card.confidence != null ? Math.round(card.confidence * 100) : null;
    const status = card.status || "";
    const tags = tryParseJson(card.tags);

    let html = `<div class="twin-item-detail">
      <div class="twin-item-detail-header" style="border-left:4px solid #1d4ed8">
        <span>${esc(_tt("twin.card.heading"))}</span>
        <span class="twin-item-id">${esc(card.id)}</span>
      </div>
      <div class="twin-item-detail-body" style="padding:16px">
        <div style="margin-bottom:12px"><b>${esc(_tt("twin.field.appliesWhen"))}</b>${esc(card.applies_when)}</div>
        <div style="margin-bottom:12px"><b>${esc(_tt("twin.field.judgment"))}</b>${esc(card.judgment)}</div>
        <div style="margin-bottom:12px;color:var(--accent)"><b>${esc(_tt("twin.field.agentAction"))}</b>${esc(card.agent_action)}</div>
        ${card.exceptions ? `<div style="margin-bottom:12px"><b>${esc(_tt("twin.field.exceptions"))}</b>${esc(card.exceptions)}</div>` : ""}
        <div class="twin-item-meta">
          ${status ? `<span class="twin-status-badge ${status === "confirmed" ? "confirmed" : status === "emerging" ? "emerging" : "hypothesis"}">${status}</span>` : ""}
          ${conf !== null ? `<span class="twin-conf">${conf}%</span>` : ""}
          ${card.evidence_count ? `<span class="twin-ep-count">${card.evidence_count} events</span>` : ""}
          ${tags ? tags.split(", ").map(t => `<span class="twin-tag">${esc(t)}</span>`).join("") : ""}
        </div>
      </div>`;

    if (evidence.length) {
      html += `<div class="twin-trace-section">
        <h4>${esc(_tt("twin.card.supportEvents", { n: evidence.length }))}</h4>`;
      for (const ep of evidence) {
        html += `<div class="twin-episode-card">
          <div class="twin-ep-header">
            <span class="twin-ep-signal ${ep.signal_type || ""}">${esc(ep.signal_type)}</span>
            <span class="twin-ep-domain">${esc(ep.domain)}</span>
            <span class="twin-ep-date">${esc((ep.created_at || "").slice(0, 10))}</span>
          </div>
          <div class="twin-ep-body">
            <div><b>AI:</b> ${esc(truncate(ep.ai_action, 120))}</div>
            <div><b>${esc(_tt("twin.field.reaction"))}</b> ${esc(truncate(ep.user_reaction, 120))}</div>
            ${ep.lesson ? `<div><b>${esc(_tt("twin.field.lesson"))}</b> ${esc(ep.lesson)}</div>` : ""}
          </div>
          ${ep.session_id ? `<a class="twin-ep-link" onclick="window.openSession && window.openSession('${esc(ep.session_id)}')">${esc(_tt("twin.card.viewSession"))}</a>` : ""}
        </div>`;
      }
      html += "</div>";
    }

    if (relations.length) {
      html += `<div class="twin-trace-section">
        <h4>${esc(_tt("twin.card.relatedCards", { n: relations.length }))}</h4>`;
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
    fetch(_withRunId(url))
      .then(r => r.json())
      .then(data => renderTraits(data.traits || [], category))
      .catch(e => console.error("Failed to load traits:", e));
  }

  function renderTraits(items, category) {
    currentView = "traits";
    _showOnlyView("dimension");
    const container = document.getElementById("twin-detail");
    const title = category || _tt("twin.traits.allTitle");
    setBreadcrumb([{ label: title, onclick: () => loadTraits(category) }]);

    const cat = TRAIT_CATEGORIES.find(c => c.key === category) || { icon: "🧬", color: "#7c3aed" };

    let html = `<div class="twin-detail-header" style="--dim-color:${cat.color}">
      <span class="twin-dim-icon">${cat.icon}</span>
      <span class="twin-detail-title">${title}</span>
      <span class="twin-dim-count">${esc(_tt("twin.count", { n: items.length }))}</span>
    </div>
    <div class="twin-detail-list">`;

    if (items.length === 0) {
      html += `<div class="twin-dim-empty" style="padding:24px">${esc(_tt("twin.empty.traitsData"))}</div>`;
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
      { label: trait.category || _tt("twin.traits.fallbackCat"), onclick: () => loadTraits(trait.category) },
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
        <h4>${esc(_tt("twin.trait.supportCards", { n: cards.length }))}</h4>`;
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
    if (updatedEl) { updatedEl.textContent = _tt("twin.status.aiStarting"); }

    // Switch to analysis view
    currentView = "analyzing";
    _showOnlyView("analysis");
    setBreadcrumb([{ label: _tt("twin.bc.analyzing") }]);

    const progress = show("twin-analysis-progress");
    if (progress) {
      progress.innerHTML = `<div class="twin-stream-container" id="twin-stream-output">
        <div class="evolve-thinking">
          <span class="evolve-thinking-dot"></span>
          <span class="evolve-thinking-dot"></span>
          <span class="evolve-thinking-dot"></span>
          <span class="evolve-thinking-label">${esc(_tt("twin.status.aiStarting"))}</span>
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
      failed: false,
    };

    // Abort previous if any
    if (analysisAbort) analysisAbort.abort();
    const abortCtrl = new AbortController();
    analysisAbort = abortCtrl;

    fetch("/api/twin/analyze", { method: "POST", signal: abortCtrl.signal })
      .then((response) => window.readSseStream(response, evt => _handleStreamEvent(evt, streamState)))
      .then(() => _finishAnalysis(streamState, streamState.failed))
      .catch((e) => {
        if (e.name === "AbortError") {
          if (analysisAbort === abortCtrl) { analysisRunning = false; _updateAnalyzeButton(); }
          return;
        }
        const container = document.getElementById("twin-stream-output");
        if (container) {
          _hideThinking(container);
          const errDiv = document.createElement("div");
          errDiv.className = "twin-stream-error";
          errDiv.textContent = `❌ ${String(e)}`;
          container.appendChild(errDiv);
        }
        _finishAnalysis(streamState, true);
      })
      .finally(() => { if (analysisAbort === abortCtrl) analysisAbort = null; });
  }

  function _finishAnalysis(state, failed = false) {
    analysisRunning = false;
    _finalizeToolGroup(state);
    _updateAnalyzeButton();
    const updatedEl = document.getElementById("twin-last-analyzed");
    if (updatedEl && !failed) { updatedEl.textContent = `Updated ${new Date().toLocaleTimeString()}`; }
    // If user is still watching the analysis, switch to overview
    if (currentView === "analyzing" && !failed) {
      setBreadcrumb([{ label: _tt("twin.bc.done") }]);
      setTimeout(() => loadOverview(), 1500);
    } else if (currentView === "analyzing" && failed) {
      setBreadcrumb([{ label: _tt("twin.bc.failed") }]);
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
          updatedEl.textContent = _tt("twin.status.aiRunning", { n: state.stepCount });
          updatedEl.classList.add("loading");
        }
        _autoScroll();
        break;
      }

      case "text":
        _finalizeToolGroup(state);
        state.blockText += evt.content;
        {
          const runIdMatch = /Twin run_id:\s*(\S+)/.exec(evt.content);
          if (runIdMatch) {
            _activeRunId = runIdMatch[1];
            try {
              localStorage.setItem("twin-active-run-id", _activeRunId);
            } catch (e) {}
          }
        }
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
        state.failed = true;
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
    el.innerHTML = `<span class="evolve-thinking-dot"></span><span class="evolve-thinking-dot"></span><span class="evolve-thinking-dot"></span><span class="evolve-thinking-label">${esc(_tt("twin.status.aiGenerating"))}</span>`;
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
  function loadRuntimePreview(options = {}) {
    fetch(_withRunId("/api/twin/runtime-preview"))
      .then(r => r.json())
      .then(data => renderRuntimePreview(data, options))
      .catch(e => console.error("Failed to load runtime preview:", e));
  }

  function renderRuntimeMarkdown(text) {
    return window.renderMarkdownSimple
      ? window.renderMarkdownSimple(text)
      : esc(text).replace(/\n/g, "<br>");
  }

  function cleanRuntimeSectionTitle(text) {
    return String(text || "")
      .replace(/^#+\s*/, "")
      .replace(/^\*\*|\*\*$/g, "")
      .trim();
  }

  function parseRuntimeSection(block, index) {
    const headingMatch = block.match(/^#{1,4}\s+([^\n]+)\n*([\s\S]*)$/);
    if (headingMatch) {
      return {
        title: cleanRuntimeSectionTitle(headingMatch[1]),
        body: headingMatch[2].trim(),
      };
    }

    const boldMatch = block.match(/^\*\*(.+?)\*\*\s*[。.:：-]?\s*([\s\S]*)$/);
    if (boldMatch) {
      return {
        title: cleanRuntimeSectionTitle(boldMatch[1]),
        body: boldMatch[2].trim(),
      };
    }

    const labelMatch = block.match(/^([^。！？!?：:\n]{2,38})[。.:：]\s*([\s\S]+)$/);
    if (labelMatch) {
      return {
        title: cleanRuntimeSectionTitle(labelMatch[1]),
        body: labelMatch[2].trim(),
      };
    }

    return {
      title: index === 0 ? "Overview" : `Section ${index + 1}`,
      body: block.trim(),
    };
  }

  function renderRuntimePreviewSections(text) {
    const blocks = String(text || "")
      .trim()
      .split(/\n\s*\n/)
      .map(block => block.trim())
      .filter(Boolean);

    if (!blocks.length || (blocks.length === 1 && blocks[0] === "(empty)")) {
      return `<div class="twin-runtime-section-empty">No compiled Runtime Pack content yet.</div>`;
    }

    let intro = "";
    const sections = [];
    blocks.forEach((block, index) => {
      const parsed = parseRuntimeSection(block, index);
      if (index === 0 && !parsed.body && block.length <= 80) {
        intro = parsed.title || block;
        return;
      }
      sections.push(parsed);
    });

    const introHtml = intro
      ? `<div class="twin-runtime-section-intro">
          <span>Runtime summary</span>
          <h3>${esc(intro)}</h3>
        </div>`
      : "";

    const sectionHtml = sections.map((section, index) => {
      const body = section.body || section.title;
      return `<section class="twin-runtime-section-card">
        <div class="twin-runtime-section-index">${String(index + 1).padStart(2, "0")}</div>
        <div class="twin-runtime-section-content">
          <h4>${esc(section.title)}</h4>
          <div class="twin-runtime-section-text">${renderRuntimeMarkdown(body)}</div>
        </div>
      </section>`;
    }).join("");

    return `<div class="twin-runtime-section-list">${introHtml}${sectionHtml}</div>`;
  }

  function focusRuntimePreviewContent() {
    const body = document.getElementById("twin-body");
    const target = document.querySelector(".twin-runtime-document");
    if (!body || !target) return;

    const bodyRect = body.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const offset = targetRect.top - bodyRect.top + body.scrollTop - 16;
    body.scrollTo({ top: Math.max(0, offset), behavior: "auto" });
  }

  function resetTwinScrollTop() {
    const body = document.getElementById("twin-body");
    if (!body) return;
    const reset = () => {
      body.scrollTop = 0;
      body.scrollTo({ top: 0, left: 0, behavior: "auto" });
    };
    reset();
    requestAnimationFrame(() => {
      reset();
      requestAnimationFrame(reset);
    });
  }

  function renderRuntimePreview(data, options = {}) {
    currentView = "runtime";
    _showOnlyView("dimension");
    show("twin-persona-card");
    const container = document.getElementById("twin-detail");
    setBreadcrumb([{ label: "Runtime Pack", onclick: () => loadRuntimePreview() }]);

    const text = data.text || "(empty)";
    const cardCount = data.card_count || 0;
    const traitCount = data.trait_count || 0;
    const hasData = cardCount > 0 || traitCount > 0;
    const renderedText = renderRuntimePreviewSections(text);

    let html = `<div class="twin-runtime-detail">
      <div class="twin-runtime-hero">
        <div class="twin-runtime-hero-main">
          <span class="twin-runtime-hero-icon">📦</span>
          <div>
            <div class="twin-runtime-kicker">Compiled to AI instructions</div>
            <h2>Runtime Pack</h2>
            <p>${esc(_tt("twin.runtime.desc"))}</p>
            <div class="twin-runtime-compact-summary">
              <span><b>${cardCount}</b> cards</span>
              <span><b>${traitCount}</b> traits</span>
              <span>${hasData ? "Ready" : "Empty"}</span>
            </div>
          </div>
        </div>
        <div class="twin-runtime-hero-side">
          <span class="twin-runtime-status ${hasData ? "ready" : "no-data"}">${hasData ? "Ready to sync" : "No data"}</span>
          <span class="twin-runtime-target-file">CLAUDE.md</span>
          ${hasData ? '<button class="btn-text twin-runtime-sync-button twin-runtime-hero-action" id="twin-runtime-sync-btn">📤 Sync to CLAUDE.md</button>' : ""}
        </div>
      </div>
      <div class="twin-runtime-document">
        <div class="twin-runtime-document-head">
          <span>Compiled preview</span>
          <span>${cardCount} cards + ${traitCount} traits</span>
        </div>
        <div class="twin-runtime-document-body">${renderedText}</div>
      </div></div>`;

    container.innerHTML = html;
    if (options.focusContent) focusRuntimePreviewContent();
    else resetTwinScrollTop();

    const syncBtn = document.getElementById("twin-runtime-sync-btn");
    if (syncBtn) syncBtn.onclick = startSync;
  }

  // ── Sync ──
  function startSync() {
    if (!confirm(_tt("twin.sync.confirm"))) return;
    fetch("/api/twin/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(_activeRunId ? { run_id: _activeRunId } : {}),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          alert(_tt("twin.sync.success", { cards: data.cards_synced || 0, traits: data.traits_synced || 0 }));
        } else {
          alert(_tt("twin.sync.failed", { error: data.error || "unknown" }));
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

  function toggle(id, visible) {
    return visible ? show(id) : hide(id);
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

  // Register shell strings at module load so static [data-i18n] elements
  // resolve correctly even before initTwinView runs. app.js runs its first
  // applyI18nDom before this module loads, so refresh once after registering.
  _registerTwinI18n();
  if (window.applyI18nDom) window.applyI18nDom(document);
})();
