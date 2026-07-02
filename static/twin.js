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
      const displayTitle = sel.persona_title || sel.model_name || _tt("twin.persona.model");
      titleEl.textContent = displayTitle;
      subtitleEl.textContent = sel.rationale || "";
      if (imgEl) {
        imgEl.src = selectedAvatarPath || personaAvatarPath(sel.persona_id);
        const styleLabel = manualOption ? _styleName(manualOption.avatarId) : "";
        const personaLabel = manualOption ? _personaName(manualOption.personaId) : displayTitle;
        imgEl.alt = manualOption ? `${personaLabel} ${styleLabel}` : displayTitle;
      }
      cachedAvatarSelection = sel;
      renderPersonaOptions(sel, manualOption ? manualOption.avatarId : "");
      return;
    }

    titleEl.textContent = _tt("twin.persona.model");
    subtitleEl.textContent = traits && traits.length ? _tt("twin.persona.matching") : _tt("twin.trait.waiting");
    if (imgEl) {
      imgEl.src = selectedAvatarPath || defaultAvatar;
      if (manualOption) {
        imgEl.alt = `${_personaName(manualOption.personaId)} ${_styleName(manualOption.avatarId)}`;
      } else {
        imgEl.alt = "";
      }
    }
    renderPersonaOptions(sel, manualOption ? manualOption.avatarId : "");

    if (traits && traits.length) {
      fetch(_withRunId("/api/twin/avatar-selection"))
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
            <div class="twin-persona-group-title">${esc(_personaName(group.personaId))}</div>
            <div class="twin-persona-style-options">
              ${group.options.map(option => {
                const active = option.avatarId === activeAvatarId ? " active" : "";
                const styleLabel = _styleName(option.avatarId);
                const personaLabel = _personaName(option.personaId);
                const aiMatched = option.avatarId === aiAvatarId ? `<span class="twin-persona-badge">${esc(_tt("twin.persona.badgeAi"))}</span>` : "";
                const selected = option.avatarId === manualAvatarId ? `<span class="twin-persona-badge selected">${esc(_tt("twin.persona.badgeSelected"))}</span>` : "";
                return `<button type="button" class="twin-persona-option${active}" data-avatar-id="${esc(option.avatarId)}">
                  <img src="${esc(option.image)}" alt="${esc(personaLabel)} ${esc(styleLabel)}">
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

  // ── i18n (UI shell + persona/cognitive model names) ──
  let _i18nRegistered = false;
  function _registerTwinI18n() {
    if (_i18nRegistered || !window.registerI18n) return;
    _i18nRegistered = true;
    const zhModel = {
      "twin.model.cm_001": "问题定界者",
      "twin.model.cm_002": "本质追问者",
      "twin.model.cm_003": "隐含前提拆解者",
      "twin.model.cm_004": "语境敏感者",
      "twin.model.cm_005": "边界敏感者",
      "twin.model.cm_006": "问题重构者",
      "twin.model.cm_007": "因果追踪者",
      "twin.model.cm_008": "第一性原理者",
      "twin.model.cm_009": "结构推演者",
      "twin.model.cm_010": "模式归纳者",
      "twin.model.cm_011": "类比迁移者",
      "twin.model.cm_012": "约束反推者",
      "twin.model.cm_013": "稳妥决策者",
      "twin.model.cm_014": "风险收敛者",
      "twin.model.cm_015": "证据锚定者",
      "twin.model.cm_016": "最小代价选择者",
      "twin.model.cm_017": "长期权衡者",
      "twin.model.cm_018": "可逆试错者",
      "twin.model.cm_019": "复杂度克制者",
      "twin.model.cm_020": "本质极简者",
      "twin.model.cm_021": "冗余厌恶者",
      "twin.model.cm_022": "秩序建立者",
      "twin.model.cm_023": "结构收束者",
      "twin.model.cm_024": "依赖敏感者",
      "twin.model.cm_025": "可控性优先者",
      "twin.model.cm_026": "验证闭环者",
      "twin.model.cm_027": "异常预判者",
      "twin.model.cm_028": "失控厌恶者",
      "twin.model.cm_029": "后果敏感者",
      "twin.model.cm_030": "失败预演者",
      "twin.model.cm_031": "小步推进者",
      "twin.model.cm_032": "稳态执行者",
      "twin.model.cm_033": "闭环完成者",
      "twin.model.cm_034": "路径校准者",
      "twin.model.cm_035": "目标反推者",
      "twin.model.cm_036": "实用落地者",
      "twin.model.cm_037": "噪声过滤者",
      "twin.model.cm_038": "信息压缩者",
      "twin.model.cm_039": "信号捕捉者",
      "twin.model.cm_040": "细节校准者",
      "twin.model.cm_041": "重点提炼者",
      "twin.model.cm_042": "脉络梳理者",
      "twin.model.cm_043": "实质锚定者",
      "twin.model.cm_044": "克制表达者",
      "twin.model.cm_045": "清晰度维护者",
      "twin.model.cm_046": "语言密度追求者",
      "twin.model.cm_047": "结构表达者",
      "twin.model.cm_048": "质感表达者",
    };
    const enModel = {
      "twin.model.cm_001": "Problem Framer",
      "twin.model.cm_002": "First-Principle Inquirer",
      "twin.model.cm_003": "Hidden-Assumption Deconstructor",
      "twin.model.cm_004": "Context-Sensitive Thinker",
      "twin.model.cm_005": "Boundary Sentinel",
      "twin.model.cm_006": "Problem Reframer",
      "twin.model.cm_007": "Causality Tracker",
      "twin.model.cm_008": "First-Principles Reasoner",
      "twin.model.cm_009": "Structural Deductionist",
      "twin.model.cm_010": "Pattern Synthesizer",
      "twin.model.cm_011": "Analogical Transferrer",
      "twin.model.cm_012": "Constraint-Driven Reasoner",
      "twin.model.cm_013": "Prudent Decision-Maker",
      "twin.model.cm_014": "Risk Mitigator",
      "twin.model.cm_015": "Evidence Anchorer",
      "twin.model.cm_016": "Minimal-Cost Chooser",
      "twin.model.cm_017": "Long-Horizon Tradeoff Analyst",
      "twin.model.cm_018": "Reversible Experimenter",
      "twin.model.cm_019": "Complexity Restrainer",
      "twin.model.cm_020": "Essential Minimalist",
      "twin.model.cm_021": "Redundancy Eliminator",
      "twin.model.cm_022": "Order Architect",
      "twin.model.cm_023": "Structure Consolidator",
      "twin.model.cm_024": "Dependency Sensitizer",
      "twin.model.cm_025": "Contingency Prioritizer",
      "twin.model.cm_026": "Verification Closer",
      "twin.model.cm_027": "Anomaly Anticipator",
      "twin.model.cm_028": "Chaos Averse Operator",
      "twin.model.cm_029": "Consequence-Weighted Thinker",
      "twin.model.cm_030": "Failure Previsualizer",
      "twin.model.cm_031": "Incremental Pacer",
      "twin.model.cm_032": "Steady-State Executor",
      "twin.model.cm_033": "Loop-Close Finisher",
      "twin.model.cm_034": "Path Calibrator",
      "twin.model.cm_035": "Goal-Backed Planner",
      "twin.model.cm_036": "Pragmatic Implementer",
      "twin.model.cm_037": "Noise Filter",
      "twin.model.cm_038": "Information Compressor",
      "twin.model.cm_039": "Signal Detector",
      "twin.model.cm_040": "Detail Calibrator",
      "twin.model.cm_041": "Key Point Distiller",
      "twin.model.cm_042": "Thread Unweaver",
      "twin.model.cm_043": "Substance Anchorer",
      "twin.model.cm_044": "Restrained Expressor",
      "twin.model.cm_045": "Clarity Guardian",
      "twin.model.cm_046": "Density Seeker",
      "twin.model.cm_047": "Structural Communicator",
      "twin.model.cm_048": "Texture Crafted Expressor",
    };
    const zhPersona = {
      "twin.persona.P01": "深度研究者",
      "twin.persona.P02": "反馈迭代者",
      "twin.persona.P03": "系统架构者",
      "twin.persona.P04": "怀疑型调试者",
      "twin.persona.P05": "极简决策者",
      "twin.persona.P06": "混沌创意建造者",
      "twin.persona.P07": "审美策展者",
      "twin.persona.P08": "证据分析者",
      "twin.persona.P09": "人本协调者",
      "twin.persona.P10": "共识翻译者",
      "twin.persona.P11": "AI 编排者",
      "twin.persona.P12": "探索战略者",
      "twin.persona.P13": "可靠运营者",
      "twin.persona.P14": "安静工程师",
      "twin.persona.P15": "反常识重构者",
      "twin.persona.P16": "语气校准者",
    };
    const enPersona = {
      "twin.persona.P01": "Deep Researcher",
      "twin.persona.P02": "Feedback Iterator",
      "twin.persona.P03": "Systems Architect",
      "twin.persona.P04": "Skeptical Debugger",
      "twin.persona.P05": "Minimal Decision-Maker",
      "twin.persona.P06": "Chaotic Creative Maker",
      "twin.persona.P07": "Taste Curator",
      "twin.persona.P08": "Evidence Analyst",
      "twin.persona.P09": "Human-Centered Facilitator",
      "twin.persona.P10": "Consensus Translator",
      "twin.persona.P11": "AI Orchestrator",
      "twin.persona.P12": "Explorer Strategist",
      "twin.persona.P13": "Reliable Operator",
      "twin.persona.P14": "Quiet Engineer",
      "twin.persona.P15": "Contrarian Reframer",
      "twin.persona.P16": "Tone Calibrator",
    };
    const zhStyle = {
      "twin.style.A": "风格 A",
      "twin.style.B": "风格 B",
    };
    const enStyle = {
      "twin.style.A": "Style A",
      "twin.style.B": "Style B",
    };
    window.registerI18n({
      zh: Object.assign({
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
        "twin.overview.runSwitcher": "切换历史运行",
        "twin.overview.viewingRun": "当前 overview：{id}",
        "twin.overview.openProgress": "查看进度",
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
        "twin.status.bgRunning": "后台分析仍在进行中…（切换页面不会中断）",
        "twin.bc.done": "分析完成 ✅",
        "twin.bc.failed": "分析失败，请检查错误并重试",
        "twin.bc.interrupted": "分析已中断（可继续）",
        "twin.status.aiRunning": "AI 执行中… ({n} steps)",
        "twin.status.aiGenerating": "AI 分析生成中…",
        "twin.analysis.failedTitle": "分析中断",
        "twin.analysis.failedHint": "上游 AI 引擎返回错误。当前进度已保留，可以返回概览、重新分析，或从已完成阶段继续。",
        "twin.analysis.viewOverview": "返回概览",
        "twin.analysis.retry": "重新分析",
        "twin.analysis.resume": "继续未完成阶段",
        "twin.analysis.switchEngine": "改用 {engine} 重试",
        "twin.progress.title": "分析进度",
        "twin.progress.stage1": "证据事件提取",
        "twin.progress.stage2": "判断卡蒸馏",
        "twin.progress.stage3": "认知特质归纳",
        "twin.progress.stage4": "Runtime 编译",
        "twin.progress.stage5": "认知模型头像匹配",
        "twin.progress.st.completed": "已完成",
        "twin.progress.st.running": "进行中",
        "twin.progress.st.failed": "失败",
        "twin.progress.st.cancelled": "已取消",
        "twin.progress.st.pending": "待处理",
        "twin.progress.stats": "{events} 事件 · {cards} 判断卡 · {traits} 认知特质",
        "twin.progress.runLabel": "Twin run_id：{id}",
        "twin.progress.stageLine": "阶段 {n}/5：{name}",
        "twin.progress.failedWith": "上次运行失败：{msg}",
        "twin.progress.interrupted": "当前没有运行中的分析进程，以下为上一次运行的进度。",
        "twin.progress.empty": "暂无进度记录。点击 Analyze 开始分析。",
        "twin.progress.history.title": "历史记录（最近 10 次）",
        "twin.progress.history.empty": "暂无历史运行记录。",
        "twin.progress.history.current": "当前",
        "twin.progress.rs.completed": "已完成",
        "twin.progress.rs.partial": "部分完成",
        "twin.progress.rs.failed": "失败",
        "twin.progress.rs.cancelled": "已取消",
        "twin.progress.rs.interrupted": "已中断",
        "twin.progress.rs.running": "进行中",
        "twin.progress.rs.empty": "无数据",
        "twin.resume.prompt": "之前的分析在 {stages} 后中断。是否从中断处继续？",
        "twin.resume.btn": "继续分析",
        "twin.resume.fresh": "重新开始",
        "twin.stream.idle": "连接似乎已空闲。分析可能已停滞。你可以继续等待，或返回后重试。",
        "twin.runtime.desc": "将判断卡与认知特质压缩成下一次会话可读取的上下文包。",
        "twin.sync.confirm": "将Distill Yourself同步到 CLAUDE.md？",
        "twin.sync.success": "同步完成：{cards} 判断卡 + {traits} 认知特质已写入",
        "twin.sync.failed": "同步失败：{error}",
        "twin.lastAnalyzed.never": "尚未分析",
        "twin.persona.cardTitle": "点击打开 Runtime Pack",
        "twin.persona.avatarTitle": "选择认知类型",
        "twin.persona.kicker": "认知模型",
        "twin.persona.waitTitle": "等待认知模型",
        "twin.persona.waitSubtitle": "点击 Analyze 后匹配认知模型",
        "twin.persona.changeAvatar": "更换头像 →",
        "twin.persona.selectLabel": "选择",
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
        "twin.signal.all": "全部",
        "twin.signal.correction": "纠正",
        "twin.signal.acceptance": "认可",
        "twin.signal.escalation": "升级",
        "twin.signal.question": "提问",
        "twin.status.confirmed": "已确认",
        "twin.status.emerging": "形成中",
        "twin.status.hypothesis": "假设",
        "twin.cat.values": "价值取向",
        "twin.cat.decision": "决策风格",
        "twin.cat.collaboration": "协作模式",
        "twin.cat.capability": "能力边界",
        "twin.cat.thinking": "思维模式",
        "twin.field.ai": "AI:",
        "twin.events.title": "证据事件",
        "twin.tg.tools": "{n} 个工具",
        "twin.status.updated": "已更新 {time}",
        "twin.status.error": "错误：{msg}",
        "twin.runtime.compiledKicker": "已编译为 AI 指令",
        "twin.runtime.heroTitle": "Runtime Pack",
        "twin.runtime.empty": "空",
        "twin.runtime.readyToSync": "可同步",
        "twin.runtime.syncBtn": "📤 同步到 CLAUDE.md",
        "twin.runtime.compiledPreview": "编译预览",
        "twin.runtime.cardsTraits": "{cards} 判断卡 + {traits} 认知特质",
        "twin.runtime.sectionEmpty": "尚无已编译的 Runtime Pack 内容。",
        "twin.runtime.summary": "Runtime 摘要",
        "twin.runtime.sectionOverview": "概览",
        "twin.runtime.section": "第 {n} 节",
        "twin.runtime.sourceCounts": "Runtime Pack 来源数量",
      }, zhModel, zhPersona, zhStyle),
      en: Object.assign({
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
        "twin.overview.runSwitcher": "Switch historical run",
        "twin.overview.viewingRun": "Overview run: {id}",
        "twin.overview.openProgress": "View progress",
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
        "twin.status.bgRunning": "Analysis still running in the background… (switching tabs won't interrupt it)",
        "twin.bc.done": "Analysis complete ✅",
        "twin.bc.failed": "Analysis failed, please check the error and retry",
        "twin.bc.interrupted": "Analysis interrupted (resumable)",
        "twin.status.aiRunning": "AI running… ({n} steps)",
        "twin.status.aiGenerating": "AI generating analysis…",
        "twin.analysis.failedTitle": "Analysis interrupted",
        "twin.analysis.failedHint": "The upstream AI engine returned an error. The current progress is preserved; you can return to overview, retry, or resume completed stages.",
        "twin.analysis.viewOverview": "Back to overview",
        "twin.analysis.retry": "Retry",
        "twin.analysis.resume": "Resume incomplete stages",
        "twin.analysis.switchEngine": "Retry with {engine}",
        "twin.progress.title": "Analysis progress",
        "twin.progress.stage1": "Evidence event extraction",
        "twin.progress.stage2": "Judgment card distillation",
        "twin.progress.stage3": "Cognitive trait generalization",
        "twin.progress.stage4": "Runtime compile",
        "twin.progress.stage5": "Cognitive avatar matching",
        "twin.progress.st.completed": "Completed",
        "twin.progress.st.running": "Running",
        "twin.progress.st.failed": "Failed",
        "twin.progress.st.cancelled": "Cancelled",
        "twin.progress.st.pending": "Pending",
        "twin.progress.stats": "{events} events · {cards} cards · {traits} traits",
        "twin.progress.runLabel": "Twin run_id: {id}",
        "twin.progress.stageLine": "Stage {n}/5: {name}",
        "twin.progress.failedWith": "Last run failed: {msg}",
        "twin.progress.interrupted": "No analysis is running right now. Showing the progress of the last run.",
        "twin.progress.empty": "No progress recorded yet. Click Analyze to start.",
        "twin.progress.history.title": "Recent runs (last 10)",
        "twin.progress.history.empty": "No past runs yet.",
        "twin.progress.history.current": "Current",
        "twin.progress.rs.completed": "Completed",
        "twin.progress.rs.partial": "Partial",
        "twin.progress.rs.failed": "Failed",
        "twin.progress.rs.cancelled": "Cancelled",
        "twin.progress.rs.interrupted": "Interrupted",
        "twin.progress.rs.running": "Running",
        "twin.progress.rs.empty": "No data",
        "twin.resume.prompt": "A previous analysis was interrupted after {stages}. Resume from where it left off?",
        "twin.resume.btn": "Resume",
        "twin.resume.fresh": "Start Fresh",
        "twin.stream.idle": "Connection appears idle. The analysis may have stalled. You can wait longer or go back and retry.",
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
        "twin.persona.selectLabel": "Select",
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
        "twin.signal.all": "all",
        "twin.signal.correction": "correction",
        "twin.signal.acceptance": "acceptance",
        "twin.signal.escalation": "escalation",
        "twin.signal.question": "question",
        "twin.status.confirmed": "confirmed",
        "twin.status.emerging": "emerging",
        "twin.status.hypothesis": "hypothesis",
        "twin.cat.values": "Values",
        "twin.cat.decision": "Decision style",
        "twin.cat.collaboration": "Collaboration",
        "twin.cat.capability": "Capability",
        "twin.cat.thinking": "Thinking mode",
        "twin.field.ai": "AI:",
        "twin.events.title": "Evidence Events",
        "twin.tg.tools": "{n} tools",
        "twin.status.updated": "Updated {time}",
        "twin.status.error": "Error: {msg}",
        "twin.runtime.compiledKicker": "Compiled to AI instructions",
        "twin.runtime.heroTitle": "Runtime Pack",
        "twin.runtime.empty": "Empty",
        "twin.runtime.readyToSync": "Ready to sync",
        "twin.runtime.syncBtn": "📤 Sync to CLAUDE.md",
        "twin.runtime.compiledPreview": "Compiled preview",
        "twin.runtime.cardsTraits": "{cards} cards + {traits} traits",
        "twin.runtime.sectionEmpty": "No compiled Runtime Pack content yet.",
        "twin.runtime.summary": "Runtime summary",
        "twin.runtime.sectionOverview": "Overview",
        "twin.runtime.section": "Section {n}",
        "twin.runtime.sourceCounts": "Runtime Pack source counts",
      }, enModel, enPersona, enStyle),
    });
  }

  function _tt(key, vars) {
    return window.t ? window.t(key, vars) : key;
  }

  function _getLang() {
    return (window.getLang && window.getLang()) || "zh";
  }

  function _getEngine() {
    // 优先级：全局共享 scope（state.globalScopeEngine）> DOM select > localStorage > auto。
    // 仅读 DOM select 在 select 尚未填充或被折叠时会丢失用户选择，故先走共享状态。
    try {
      if (typeof window.getEvolveScope === "function") {
        const eng = (window.getEvolveScope() || {}).engine;
        if (eng) return eng;
      }
    } catch (e) { /* ignore */ }
    const sel = document.getElementById("global-engine-select");
    if (sel && sel.value) return sel.value;
    try {
      const stored = localStorage.getItem("chatview-engine");
      if (stored) return stored;
    } catch (e) { /* ignore */ }
    return "auto";
  }

  function _styleName(avatarId) {
    return _tt((avatarId || "").endsWith("-B") ? "twin.style.B" : "twin.style.A");
  }

  function _modelName(modelId) {
    return _tt("twin.model." + (modelId || ""));
  }

  function _personaName(personaId) {
    return _tt("twin.persona." + (personaId || ""));
  }

  /** Apply twin-specific CSS variables that depend on locale (e.g. ::after content labels). */
  function _applyTwinCssVars() {
    const root = document.documentElement;
    root.style.setProperty("--twin-select-label", `"${_tt("twin.persona.selectLabel")}"`);
  }

  // ── Enum localization (DB values are fixed tokens; display only) ──
  const _SIGNAL_KEYS = {
    correction: "twin.signal.correction", acceptance: "twin.signal.acceptance",
    escalation: "twin.signal.escalation", question: "twin.signal.question", all: "twin.signal.all",
  };
  const _STATUS_KEYS = {
    confirmed: "twin.status.confirmed", emerging: "twin.status.emerging", hypothesis: "twin.status.hypothesis",
  };
  const _CATEGORY_KEYS = {
    "价值取向": "twin.cat.values", "决策风格": "twin.cat.decision", "协作模式": "twin.cat.collaboration",
    "能力边界": "twin.cat.capability", "思维模式": "twin.cat.thinking",
  };
  function _signalLabel(sig) { return sig && _SIGNAL_KEYS[sig] ? _tt(_SIGNAL_KEYS[sig]) : (sig || ""); }
  function _statusLabel(st) { return st && _STATUS_KEYS[st] ? _tt(_STATUS_KEYS[st]) : (st || ""); }
  function _categoryLabel(cat) { return cat && _CATEGORY_KEYS[cat] ? _tt(_CATEGORY_KEYS[cat]) : (cat || ""); }

  // ── State ──
  let overviewData = null;
  let analysisAbort = null;
  let analysisRunning = false;
  let hasAnalysisProgress = false;
  let eventsInited = false;
  let _bgPollTimer = null; // polls /api/twin/progress to re-attach to a background run
  let _statsPollTimer = null; // polls /api/twin/progress during a live SSE stream to refresh stats/stages
  let _lastRunHistoryRenderAt = 0;
  let _lastProgressRun = null; // last run dict from /api/twin/progress or /resume
  let beforeUnloadBound = false;

  // ── Page-refresh guard (Fix 1: survive page refresh) ──
  if (!beforeUnloadBound) {
    beforeUnloadBound = true;
    window.addEventListener("beforeunload", (e) => {
      if (analysisRunning) {
        e.preventDefault();
        e.returnValue = "";
      }
    });
  }
  let currentView = "overview"; // "overview" | "cards" | "card-detail" | "traits" | "trait-detail" | "analyzing"
  let _reloadCurrentView = null; // closure to re-fetch+re-render the active detail/list view (for locale change)
  const TWIN_ACTIVE_RUN_KEY = "twin-active-run-id";
  const TWIN_VIEW_RUN_KEY = "twin-view-run-id";
  let _activeRunId = "";
  let _viewRunId = "";
  let _suggestedEngine = ""; // engine suggested by a failed run (e.g. "claude" when codex returns 521)
  try {
    const _storedRunId = localStorage.getItem(TWIN_ACTIVE_RUN_KEY);
    if (_storedRunId) _activeRunId = _storedRunId;
    const _storedViewRunId = localStorage.getItem(TWIN_VIEW_RUN_KEY);
    if (_storedViewRunId) _viewRunId = _storedViewRunId;
  } catch (e) {}

  // ── Progress snapshot cache (survive tab switch + full page refresh) ──
  // The live tool-call DOM lives in #twin-stream-output and is preserved across
  // in-app tab switches (the SPA only toggles .hidden). A full browser refresh
  // destroys it, so we persist a lightweight snapshot (run_id / status / last
  // error) to localStorage and rebuild an honest progress view on reload.
  const PROGRESS_SNAPSHOT_KEY = "twin-progress-snapshot";
  let _lastError = ""; // last analysis error message (persisted across reload)

  function _isTerminalIncomplete(status) {
    return status === "partial" || status === "interrupted" ||
      status === "failed" || status === "cancelled";
  }

  function _saveProgressSnapshot(extra) {
    try {
      const run = _lastProgressRun || {};
      const snap = Object.assign({
        run_id: _activeRunId || run.run_id || "",
        status: run.status || "",
        stats: run.stats || {},
        checkpoints: run.checkpoints || {},
        error: _lastError || "",
        ts: Date.now(),
      }, extra || {});
      localStorage.setItem(PROGRESS_SNAPSHOT_KEY, JSON.stringify(snap));
    } catch (e) {}
  }

  function _loadProgressSnapshot() {
    try {
      const raw = localStorage.getItem(PROGRESS_SNAPSHOT_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function _clearProgressSnapshot() {
    _lastError = "";
    try { localStorage.removeItem(PROGRESS_SNAPSHOT_KEY); } catch (e) {}
  }

  async function _refreshAuthoritativeProgressSnapshot(extra) {
    try {
      const resp = await fetch("/api/twin/progress");
      const data = await resp.json();
      if (data && data.ok && data.run) {
        _lastProgressRun = Object.assign({}, data.run, extra || {});
        _activeRunId = _lastProgressRun.run_id || _activeRunId;
        if (_activeRunId) {
          try { localStorage.setItem(TWIN_ACTIVE_RUN_KEY, _activeRunId); } catch (e) {}
        }
        _saveProgressSnapshot(_lastProgressRun);
        return _lastProgressRun;
      }
    } catch (e) {}
    return null;
  }

  /** Map a run status to an honest breadcrumb label key (never lie with "done"). */
  function _breadcrumbKeyForStatus(status) {
    if (status === "completed") return "twin.bc.done";
    if (status === "failed" || status === "cancelled") return "twin.bc.failed";
    if (status === "partial" || status === "interrupted") return "twin.bc.interrupted";
    return "twin.progress.title";
  }

  /** True when the live stream container already holds meaningful rendered
   * content (tool groups / text / banners / stage list / error actions), so a
   * re-entry into the progress view must NOT wipe it. */
  function _streamHasContent() {
    const c = document.getElementById("twin-stream-output");
    if (!c) return false;
    return c.querySelector(
      ".evolve-tool-group, .text-block, .twin-analysis-complete-banner, " +
      ".twin-stream-error, .twin-analysis-error-actions, .twin-progress-stages"
    ) != null;
  }

  function _hideResumePrompt() {
    const container = document.getElementById("twin-resume-prompt");
    if (container) { container.classList.add("hidden"); container.innerHTML = ""; }
  }

  function _setViewRunId(runId) {
    _viewRunId = runId || "";
    try {
      if (_viewRunId) localStorage.setItem(TWIN_VIEW_RUN_KEY, _viewRunId);
      else localStorage.removeItem(TWIN_VIEW_RUN_KEY);
    } catch (e) {}
  }

  function _runScopedUrl(url, runId) {
    let u = url;
    if (runId) {
      const sep = u.includes("?") ? "&" : "?";
      u += sep + "run_id=" + encodeURIComponent(runId);
    }
    const lang = _getLang();
    const sep = u.includes("?") ? "&" : "?";
    u += sep + "lang=" + encodeURIComponent(lang);
    return u;
  }

  function _withRunId(url, options) {
    const opts = options || {};
    const includeViewRun = opts.includeViewRun !== false;
    return _runScopedUrl(url, includeViewRun ? _viewRunId : "");
  }

  // ── Init ──
  window.initTwinView = function () {
    _registerTwinI18n();
    _applyTwinCssVars();
    if (!eventsInited) { bindEvents(); eventsInited = true; }
    // Fix: if the viewing was set to "analyzing" on a previous page load, this
    // tab was re-opened while showing analyzing. Since the in-memory
    // analysisRunning flag is false (not persisted), show a proper completed /
    // idle state instead of stale thinking dots. The background poll (below)
    // will re-attach if the server-side stream is still live.
    // Seed from the persisted snapshot so a full page refresh keeps the last
    // known state (error / partial / completed) instead of resetting to default.
    if (!_lastError) {
      const snap = _loadProgressSnapshot();
      if (snap) {
        if (snap.error) _lastError = snap.error;
        if (!_activeRunId && snap.run_id) _activeRunId = snap.run_id;
        if (snap.status && !_lastProgressRun) {
          _lastProgressRun = {
            run_id: snap.run_id || _activeRunId || "",
            status: snap.status,
            stats: snap.stats || {},
            checkpoints: snap.checkpoints || {},
          };
        }
        if (snap.status && _isTerminalIncomplete(snap.status)) hasAnalysisProgress = true;
      }
    }
    // If a live SSE stream is already running in THIS tab (in-app tab switch,
    // DOM preserved), do not touch the rendered tool-call stream — just keep
    // showing it. Only re-render when there is nothing live to preserve.
    const _liveInTab = analysisRunning && _streamHasContent();
    if (currentView === "analyzing" && !_liveInTab) {
      _showOnlyView("analysis");
      const _bcKey = analysisRunning ? "twin.bc.analyzing"
        : _breadcrumbKeyForStatus(_lastProgressRun && _lastProgressRun.status);
      setBreadcrumb([{ label: _tt(_bcKey) }]);
      // Render whatever progress we already know about (likely none yet). The
      // progress fetch below will refresh this with real checkpoints/stats and
      // either re-attach (live) or downgrade to an interrupted/empty note.
      _renderRunProgress(_lastProgressRun, analysisRunning);
    } else if (_liveInTab) {
      _showOnlyView("analysis");
      setBreadcrumb([{ label: _tt("twin.bc.analyzing") }]);
    }
    _updateAnalyzeButton();
    // ── Background re-attach (Group D): a prior analysis may still be running
    // server-side even though this tab's SSE stream was dropped. Detect it and
    // poll so the UI can rebuild progress without restarting from stage 1.
    if (_liveInTab) {
      // Already streaming live in this tab — nothing to re-attach or reset.
      _updateProgressButton();
      return;
    }
    fetch("/api/twin/progress")
      .then(r => r.json())
      .then((p) => {
        _lastProgressRun = (p && p.run) || _lastProgressRun || null;
        if (p && p.ok && p.running && !analysisRunning) {
          if (p.run && p.run.run_id) {
            _activeRunId = p.run.run_id;
            try { localStorage.setItem(TWIN_ACTIVE_RUN_KEY, _activeRunId); } catch (e) {}
          }
          hasAnalysisProgress = true;
          _saveProgressSnapshot();
          _attachBackgroundRun();
          return true;
        }
        // No live process. If this tab was reopened while showing the analysis
        // view, downgrade the stale "running" placeholder to a real (non-live)
        // progress render so the user does not stare at frozen thinking dots.
        if (currentView === "analyzing" && !analysisRunning) {
          _renderRunProgress(_lastProgressRun, false);
        }
        _updateProgressButton();
        return false;
      })
      .catch(() => false)
      .then((attached) => { if (!attached) _initResume(); });
    _updateAnalyzeButton();
  };

  function _initResume() {
    // Resolve the authoritative latest run on open, then load overview exactly
    // once. A stale stored id would otherwise scope every read to nothing.
    fetch("/api/twin/resume", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lang: _getLang() }),
    })
      .then(r => r.json())
      .then((d) => {
        if (d && d.ok && d.run && d.run.run_id) {
          _lastProgressRun = d.run;
          if (d.run.status === "partial" || d.run.status === "interrupted") {
            hasAnalysisProgress = true;
            _updateProgressButton();
            _resumePromptIfNotRunning(d.run);
          }
        } else {
          _activeRunId = "";
          hasAnalysisProgress = false;
          try { localStorage.removeItem(TWIN_ACTIVE_RUN_KEY); } catch (e) {}
        }
      })
      .catch(() => { /* network error: keep the stored id, do NOT clear */ })
      .finally(() => { loadOverview(); });
  }

  /** Show the resume prompt only after confirming the backend is NOT running.
   * If a run is still live we instead re-attach to it (no misleading prompt). */
  function _resumePromptIfNotRunning(runData) {
    fetch("/api/twin/progress")
      .then(r => r.json())
      .then((p) => {
        if (p && p.ok && p.running) {
          // Still running — attach to the live run instead of prompting resume.
          if (p.run) { _lastProgressRun = p.run; _activeRunId = p.run.run_id || _activeRunId; }
          hasAnalysisProgress = true;
          _updateProgressButton();
          _saveProgressSnapshot({ status: "running", error: "" });
          return;
        }
        _maybeShowResumePrompt(runData);
      })
      .catch(() => { _maybeShowResumePrompt(runData); });
  }

  /** Re-attach to a background analysis: show a progress banner + poll the
   * server until the run finishes, then refresh the overview. Used when the
   * SSE stream was dropped (tab switch / refresh) but the AI keeps running. */
  function _attachBackgroundRun() {
    currentView = "analyzing";
    _showOnlyView("analysis");
    setBreadcrumb([{ label: _tt("twin.bc.analyzing") }]);
    _renderRunProgress(_lastProgressRun, true);
    _updateProgressButton();
    _startBackgroundPoll();
  }

  function _reattachToRunningTwinAnalysis() {
    return fetch("/api/twin/progress")
      .then(r => r.json())
      .then((p) => {
        if (!p || !p.ok || !p.running || !p.run) return false;
        _lastProgressRun = p.run;
        _activeRunId = p.run.run_id || _activeRunId;
        if (_activeRunId) {
          try { localStorage.setItem(TWIN_ACTIVE_RUN_KEY, _activeRunId); } catch (e) {}
        }
        _lastError = "";
        analysisRunning = false;
        hasAnalysisProgress = true;
        _stopStatsPoll();
        _saveProgressSnapshot({ status: "running", error: "" });
        _attachBackgroundRun();
        _updateAnalyzeButton();
        const updatedEl = document.getElementById("twin-last-analyzed");
        if (updatedEl) updatedEl.textContent = _tt("twin.status.bgRunning");
        return true;
      })
      .catch(() => false);
  }

  function _startBackgroundPoll() {
    if (_bgPollTimer) return;
    _bgPollTimer = setInterval(() => {
      fetch("/api/twin/progress")
        .then(r => r.json())
        .then((p) => {
          if (!p || !p.ok) return;
          _lastProgressRun = p.run || _lastProgressRun;
          if (!p.running) {
            _stopBackgroundPoll();
            const runStatus = p.run ? p.run.status : "";
            const incomplete = _isTerminalIncomplete(runStatus);
            hasAnalysisProgress = incomplete;
            if (incomplete) {
              // The run did NOT complete cleanly (failed / partial / cancelled).
              // Honestly reflect that instead of pretending success.
              _saveProgressSnapshot({ status: runStatus, error: _lastError });
              if (currentView === "analyzing") {
                setBreadcrumb([{ label: _tt(_breadcrumbKeyForStatus(runStatus)) }]);
                _renderRunProgress(p.run || _lastProgressRun, false);
                _appendBackToOverviewBtn();
              }
              _updateProgressButton();
            } else {
              // Clean server-side completion.
              _clearProgressSnapshot();
              if (currentView === "analyzing") {
                const container = document.getElementById("twin-stream-output");
                if (container && !container.querySelector(".twin-analysis-complete-banner")) {
                  _hideThinking(container);
                  const banner = document.createElement("div");
                  banner.className = "twin-analysis-complete-banner";
                  banner.innerHTML =
                    '<span class="twin-analysis-complete-icon">&#10003;</span>' +
                    '<span class="twin-analysis-complete-label">' + esc(_tt("twin.bc.done")) + '</span>' +
                    '<button type="button" class="btn btn-ghost btn-sm" id="twin-poll-done-back-btn">' +
                    esc(_tt("twin.analysis.viewOverview")) +
                    '</button>';
                  container.appendChild(banner);
                  const backBtn = document.getElementById("twin-poll-done-back-btn");
                  if (backBtn) backBtn.onclick = _loadDefaultOverview;
                }
                setBreadcrumb([{ label: _tt("twin.bc.done") }]);
                setTimeout(() => {
                  if (currentView === "analyzing") { _loadDefaultOverview(); }
                }, 3000);
              } else {
                _loadDefaultOverview();
              }
            }
          } else if (currentView === "analyzing") {
            // Still running — refresh the live progress view so newly completed
            // stages + growing stats render in real time.
            _renderRunProgress(p.run || _lastProgressRun, true);
            _saveProgressSnapshot({ status: "running", error: "" });
          }
        })
        .catch(() => {});
    }, 1500);
  }

  function _stopBackgroundPoll() {
    if (_bgPollTimer) { clearInterval(_bgPollTimer); _bgPollTimer = null; }
  }

  /** During a LIVE SSE stream (owned by this tab) poll /api/twin/progress so the
   * run summary (events/cards/traits counters + per-stage status) ticks in real
   * time next to the tool-call stream — the backend writes rows to the DB as it
   * goes, so this reflects true progress, not the stale start-of-run values. */
  function _startStatsPoll() {
    if (_statsPollTimer) return;
    _statsPollTimer = setInterval(() => {
      if (!analysisRunning) { _stopStatsPoll(); return; }
      fetch("/api/twin/progress")
        .then(r => r.json())
        .then((p) => {
          if (!p || !p.ok || !p.run) return;
          _lastProgressRun = p.run;
          if (analysisRunning && currentView === "analyzing") {
            _updateProgressSummary(p.run);
            _renderRunHistoryThrottled();
          }
          _saveProgressSnapshot({ status: "running", error: "" });
        })
        .catch(() => {});
    }, 1500);
  }

  function _stopStatsPoll() {
    if (_statsPollTimer) { clearInterval(_statsPollTimer); _statsPollTimer = null; }
  }

  /** Render a real progress view from a /api/twin/progress or /api/twin/resume
   * run dict (checkpoints + stats), instead of bare thinking dots. Used by the
   * background re-attach / reopen / "view progress" paths so a reopened tab
   * actually shows what the backend has produced.
   *
   * @param {object|null} run  { run_id, status, stats, checkpoints }
   * @param {boolean} live      true when an analysis process is still running
   */
  function _currentStageNum(checkpoints) {
    // First stage (1-5) that is not yet completed — the stage "in flight".
    for (let i = 1; i <= 5; i++) {
      if ((checkpoints["" + i] || "pending") !== "completed") return i;
    }
    return 5;
  }

  /** Build the run-summary inner HTML (run header + stats line + stage list).
   * Shared by the full re-render (_renderRunProgress) and the in-place live
   * updater (_updateProgressSummary) so both views stay consistent. */
  function _progressSummaryHtml(run, live) {
    const checkpoints = (run && run.checkpoints) || {};
    const stats = (run && run.stats) || {};
    const stageNums = ["1", "2", "3", "4", "5"];
    const hasAny = Object.keys(checkpoints).length > 0 ||
      (stats.events || stats.cards || stats.traits);
    const runId = (run && run.run_id) || _activeRunId || "";
    let html = "";
    // Run header — mirrors the analyze view ("Twin run_id: ... / Stage n/5 ...")
    if (runId) {
      const stageNo = _currentStageNum(checkpoints);
      const stageName = _tt("twin.progress.stage" + stageNo);
      html += '<div class="twin-progress-head">' +
        '<span class="twin-progress-runid">' + esc(_tt("twin.progress.runLabel", { id: runId })) + '</span>' +
        '<span class="twin-progress-stageline">' +
        esc(_tt("twin.progress.stageLine", { n: stageNo, name: stageName })) + '</span>' +
        '</div>';
    }
    // Honest terminal notes only when NOT live (a live run must never show a
    // "failed/interrupted" banner above its still-growing stream).
    if (!live && run && run.status === "failed") {
      html += '<div class="twin-progress-note twin-progress-note-error">' +
        esc(_lastError ? _tt("twin.progress.failedWith", { msg: _lastError }) : _tt("twin.analysis.failedHint")) +
        '</div>';
    } else if (!live && run && (run.status === "partial" || run.status === "interrupted" || run.status === "cancelled")) {
      html += '<div class="twin-progress-note">' + esc(_tt("twin.progress.interrupted")) + '</div>';
    }
    if (hasAny) {
      html += '<div class="twin-progress-stats">' +
        esc(_tt("twin.progress.stats", {
          events: stats.events || 0,
          cards: stats.cards || 0,
          traits: stats.traits || 0,
        })) + '</div>';
      html += '<ul class="twin-progress-stages">';
      stageNums.forEach((n) => {
        const st = checkpoints[n] || "pending";
        const stKey = "twin.progress.st." + (
          ["completed", "running", "failed", "cancelled"].includes(st) ? st : "pending"
        );
        html += '<li class="twin-progress-stage st-' + esc(st) + '">' +
          '<span class="twin-progress-stage-name">' + esc(_tt("twin.progress.stage" + n)) + '</span>' +
          '<span class="twin-progress-stage-status">' + esc(_tt(stKey)) + '</span>' +
          '</li>';
      });
      html += '</ul>';
    }
    return { html, hasAny };
  }

  /** Update (or insert) the run-summary block at the TOP of the live stream
   * container WITHOUT touching the tool-call cards below it. This is what keeps
   * events/cards/traits + stage status ticking in real time during a live run
   * (缺陷①: previously the poll path short-circuited and froze the summary). */
  function _updateProgressSummary(run) {
    const container = document.getElementById("twin-stream-output");
    if (!container) return;
    const runId = (run && run.run_id) || _activeRunId || "";
    const built = _progressSummaryHtml(run, true);
    if (!built.hasAny && !runId) return;
    let summary = container.querySelector(".twin-progress-summary");
    if (!summary) {
      summary = document.createElement("div");
      summary.className = "twin-progress-summary";
      container.insertBefore(summary, container.firstChild);
    }
    summary.innerHTML = built.html;
  }

  function _renderRunProgress(run, live) {
    const progress = show("twin-analysis-progress");
    if (!progress) return;
    // Never wipe a live, content-rich stream (in-app tab switch keeps the DOM):
    // the rendered tool-call records must persist and keep growing. Instead of
    // returning early (which froze the stats), refresh the summary in place.
    if (live && _streamHasContent()) { _updateProgressSummary(run); _renderRunHistoryThrottled(); return; }
    const built = _progressSummaryHtml(run, live);
    let inner = '<div class="twin-stream-container" id="twin-stream-output">';
    inner += '<div class="twin-progress-summary">' + built.html + '</div>';
    if (live) {
      inner += '<div class="evolve-thinking">' +
        '<span class="evolve-thinking-dot"></span>' +
        '<span class="evolve-thinking-dot"></span>' +
        '<span class="evolve-thinking-dot"></span>' +
        '<span class="evolve-thinking-label">' + esc(_tt("twin.status.bgRunning")) + '</span>' +
        '</div>';
    } else if (!built.hasAny) {
      inner += '<div class="twin-progress-note">' + esc(_tt("twin.progress.empty")) + '</div>';
    }
    inner += '</div>';
    progress.innerHTML = inner;
    // History list lives below the stream summary; re-append after the rebuild.
    _renderRunHistory();
  }

  function _renderRunHistoryThrottled(force) {
    const now = Date.now();
    if (!force && now - _lastRunHistoryRenderAt < 10000) return;
    _lastRunHistoryRenderAt = now;
    _renderRunHistory();
  }

  /** Map a run-level status to its localized label key for the history list. */
  function _runStatusKey(status) {
    const known = [
      "completed", "partial", "failed", "cancelled",
      "interrupted", "running", "empty",
    ];
    return "twin.progress.rs." + (known.includes(status) ? status : "empty");
  }

  /** Format an ISO-ish timestamp for compact display; falls back to raw text. */
  function _fmtRunTs(ts) {
    if (!ts) return "";
    try {
      // DB timestamps are UTC isoformat without a trailing 'Z'; normalize so
      // the browser interprets them as UTC before converting to local time.
      let iso = String(ts);
      if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(iso) && !/[zZ+]/.test(iso.slice(10))) {
        iso += "Z";
      }
      const d = new Date(iso);
      if (isNaN(d.getTime())) return String(ts);
      const lang = _getLang();
      return d.toLocaleString(lang === "en" ? "en-US" : "zh-CN", {
        month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit",
      });
    } catch (e) { return String(ts); }
  }

  /** Build a single history row's inner HTML. */
  function _runHistoryItemHtml(run) {
    const stats = run.stats || {};
    const runId = run.run_id || "";
    const shortId = runId.length > 16 ? runId.slice(0, 16) + "…" : runId;
    const isCurrent = !!runId && runId === (_viewRunId || _activeRunId);
    const resumable = ["partial", "interrupted", "failed", "cancelled"].includes(run.status);
    let html = '<span class="twin-run-badge rs-' + esc(run.status || "empty") + '">' +
      esc(_tt(_runStatusKey(run.status))) + '</span>';
    html += '<span class="twin-run-id" title="' + esc(runId) + '">' + esc(shortId) + '</span>';
    html += '<span class="twin-run-stats">' + esc(_tt("twin.progress.stats", {
      events: stats.events || 0, cards: stats.cards || 0, traits: stats.traits || 0,
    })) + '</span>';
    html += '<span class="twin-run-time">' + esc(_fmtRunTs(run.ts)) + '</span>';
    if (isCurrent) {
      html += '<span class="twin-run-current">' + esc(_tt("twin.progress.history.current")) + '</span>';
    }
    if (resumable) {
      html += '<button type="button" class="btn btn-ghost btn-sm twin-run-resume" data-run-id="' +
        esc(runId) + '">' + esc(_tt("twin.resume.btn")) + '</button>';
    }
    return { html, resumable, isCurrent, runId };
  }

  /** Fetch + render the recent-runs history list BELOW the progress stream.
   * Newest first, max 10. The list lives in its own container so refreshing it
   * never disturbs a live SSE stream rendered in #twin-stream-output. */
  function _renderRunHistory() {
    const progress = document.getElementById("twin-analysis-progress");
    if (!progress) return;
    fetch("/api/twin/runs?limit=10")
      .then(r => r.json())
      .then((p) => {
        const runs = (p && p.ok && Array.isArray(p.runs)) ? p.runs : [];
        let box = document.getElementById("twin-run-history");
        if (!box) {
          box = document.createElement("div");
          box.id = "twin-run-history";
          box.className = "twin-run-history";
          progress.appendChild(box);
        } else if (box.parentNode !== progress) {
          progress.appendChild(box);
        }
        let html = '<div class="twin-run-history-title">' +
          esc(_tt("twin.progress.history.title")) + '</div>';
        if (!runs.length) {
          html += '<div class="twin-run-history-empty">' +
            esc(_tt("twin.progress.history.empty")) + '</div>';
          box.innerHTML = html;
          return;
        }
        html += '<ul class="twin-run-history-list">';
        const built = [];
        runs.forEach((run) => {
          const it = _runHistoryItemHtml(run);
          built.push(it);
          html += '<li class="twin-run-item' +
            (it.isCurrent ? " is-current" : "") +
            (it.resumable ? " is-resumable" : "") +
            '" data-run-id="' + esc(it.runId) + '"' +
            ' role="button" tabindex="0"' +
            '>' + it.html + '</li>';
        });
        html += '</ul>';
        box.innerHTML = html;
        // Rows switch the progress panel to that run. Resume is an explicit button.
        box.querySelectorAll(".twin-run-item").forEach((el) => {
          const rid = el.getAttribute("data-run-id");
          if (!rid) return;
          const go = () => { _selectTwinRunForViewing(rid); };
          el.onclick = go;
          el.onkeydown = (e) => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
          };
        });
        box.querySelectorAll(".twin-run-resume").forEach((btn) => {
          const rid = btn.getAttribute("data-run-id");
          if (!rid) return;
          btn.onclick = (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!analysisRunning) _startAnalysisWithResume(rid);
          };
        });
      })
      .catch(() => {});
  }

  function _loadDefaultOverview() {
    _setViewRunId("");
    loadOverview();
  }

  function _selectTwinRunForViewing(runId) {
    if (!runId) return;
    _setViewRunId(runId);
    currentView = "analyzing";
    hasAnalysisProgress = true;
    _showOnlyView("analysis");
    setBreadcrumb([{ label: _tt("twin.progress.title") }]);
    _renderRunProgress({ run_id: runId, status: "empty", stats: {}, checkpoints: {} }, false);
    _appendBackToOverviewBtn();
    fetch(_runScopedUrl("/api/twin/progress", runId))
      .then(r => r.json())
      .then((p) => {
        if (!p || !p.ok || !p.run) return;
        _lastProgressRun = p.run;
        const live = !!p.running;
        if (live && p.run.run_id) {
          _activeRunId = p.run.run_id;
          try { localStorage.setItem(TWIN_ACTIVE_RUN_KEY, _activeRunId); } catch (e) {}
        }
        setBreadcrumb([{ label: _tt(_breadcrumbKeyForStatus(p.run.status)) }]);
        _renderRunProgress(p.run, live);
        if (!live) _appendBackToOverviewBtn();
        _updateProgressButton();
      })
      .catch(() => {});
  }

  /** Show a resume prompt if a partial checkpoint exists (Issue 2.1) */
  function _maybeShowResumePrompt(runData) {
    // Never show the "interrupted, resume?" prompt while a run is genuinely
    // live — that message would be wrong and confusing.
    if (analysisRunning) return;
    const checkpoints = runData.checkpoints;
    if (!checkpoints) return;
    const completedStages = Object.values(checkpoints).filter(v => v === "completed").length;
    const totalStages = Object.keys(checkpoints).length;
    // Only prompt if at least one stage completed but not all are done,
    // and the run status is not already "completed"
    if (completedStages > 0 && completedStages < totalStages && runData.status !== "completed") {
      const completedStr = Object.entries(checkpoints)
        .filter(([, v]) => v === "completed")
        .map(([k]) => `Stage ${k}`)
        .join(", ");
      const msg = _tt("twin.resume.prompt", { stages: completedStr });
      const container = document.getElementById("twin-resume-prompt");
      if (!container) return;
      container.classList.remove("hidden");
      container.innerHTML = `<div class="twin-resume-banner">
        <span class="twin-resume-msg">${esc(msg)}</span>
        <button type="button" class="btn btn-primary btn-sm" id="twin-resume-btn">${esc(_tt("twin.resume.btn"))}</button>
        <button type="button" class="btn btn-ghost btn-sm" id="twin-fresh-btn">${esc(_tt("twin.resume.fresh"))}</button>
      </div>`;
      const resumeBtn = document.getElementById("twin-resume-btn");
      const freshBtn = document.getElementById("twin-fresh-btn");
      if (resumeBtn) resumeBtn.onclick = () => {
        container.classList.add("hidden");
        _startAnalysisWithResume(runData.run_id);
      };
      if (freshBtn) freshBtn.onclick = () => {
        container.classList.add("hidden");
        // Clear the active run ID so a new analysis starts fresh
        _activeRunId = "";
        try { localStorage.removeItem(TWIN_ACTIVE_RUN_KEY); } catch (e) {}
      };
    }
  }

  function _startAnalysisWithResume(runId) {
    _activeRunId = runId;
    _setViewRunId(runId);
    try { localStorage.setItem(TWIN_ACTIVE_RUN_KEY, _activeRunId); } catch (e) {}
    startAnalysis(true);
  }

  // Re-render UI-shell strings on language change without interrupting a running analysis.
  let _localeListenerBound = false;
  if (!_localeListenerBound) {
    _localeListenerBound = true;
    window.addEventListener("localechange", () => {
      _registerTwinI18n();
      _applyTwinCssVars();
      if (window.applyI18nDom) window.applyI18nDom(document);
      if (analysisRunning) {
        // Analysis in progress: only refresh shell labels, don't restart the stream.
        _updateAnalyzeButton();
        if (_lastProgressRun) _updateProgressSummary(_lastProgressRun);
      } else if (_lastProgressRun && currentView === "analyzing") {
        _renderRunProgress(_lastProgressRun, false);
      } else if (_reloadCurrentView) {
        // Re-render the active detail/list view in the new locale.
        _reloadCurrentView();
      } else if (window.initTwinView) {
        window.initTwinView();
      }
    });
  }

  function bindEvents() {
    const btnAnalyze = document.getElementById("twin-btn-analyze");
    const btnSync = document.getElementById("twin-btn-sync");
    const btnProgress = document.getElementById("twin-btn-progress");
    const btnExport = document.getElementById("twin-btn-export");
    if (btnAnalyze) btnAnalyze.onclick = () => {
      if (analysisRunning && analysisAbort) { _stopAnalysis(); } else { startAnalysis(); }
    };
    if (btnSync) btnSync.onclick = startSync;
    if (btnProgress) btnProgress.onclick = toggleProgressView;
    if (btnExport) btnExport.onclick = () => {
      // Dynamic import of export module
      import('./js/export.js').then(mod => mod.exportTwinData()).catch(e => console.error(e));
    };
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !isPersonaOptionsOpen()) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      closePersonaOptions();
    }, true);
  }

  function toggleProgressView() {
    if (currentView === "analyzing") {
      _loadDefaultOverview();
      _updateProgressButton();
      return;
    }
    currentView = "analyzing";
    _showOnlyView("analysis");
    if (analysisRunning) {
      // Live stream owned by this tab — keep the existing rendered tool-call
      // DOM intact and just show it.
      setBreadcrumb([{ label: _tt("twin.bc.analyzing") }]);
      if (!_streamHasContent()) _renderRunProgress(_lastProgressRun, true);
    } else {
      // Not running here. Re-check the selected run first so a browser
      // refresh preserves the user's history selection instead of jumping to
      // whichever run is latest in the backend.
      const selectedRunId = _viewRunId || "";
      const initialRun = selectedRunId
        ? { run_id: selectedRunId, status: "empty", stats: {}, checkpoints: {} }
        : _lastProgressRun;
      const status = initialRun && initialRun.status;
      setBreadcrumb([{ label: _tt(_breadcrumbKeyForStatus(status)) }]);
      _renderRunProgress(initialRun, false);
      _appendBackToOverviewBtn();
      fetch(_runScopedUrl("/api/twin/progress", selectedRunId))
        .then(r => r.json())
        .then((p) => {
          if (p && p.ok && p.running) {
            if (p.run && p.run.run_id) {
              _activeRunId = p.run.run_id;
              try { localStorage.setItem(TWIN_ACTIVE_RUN_KEY, _activeRunId); } catch (e) {}
            }
            _lastProgressRun = p.run || _lastProgressRun;
            hasAnalysisProgress = true;
            _attachBackgroundRun();
          } else if (p && p.run) {
            _lastProgressRun = p.run;
            setBreadcrumb([{ label: _tt(_breadcrumbKeyForStatus(p.run.status)) }]);
            _renderRunProgress(p.run, false);
            _appendBackToOverviewBtn();
            _saveProgressSnapshot();
          }
        })
        .catch(() => {});
    }
    _updateProgressButton();
  }

  /** Append a styled "Back to overview" button to the progress stream once. */
  function _appendBackToOverviewBtn() {
    const progress = document.getElementById("twin-stream-output");
    if (!progress || progress.querySelector(".twin-progress-back-btn")) return;
    const backBtn = document.createElement("button");
    backBtn.type = "button";
    backBtn.className = "btn btn-ghost btn-sm twin-progress-back-btn";
    backBtn.textContent = _tt("twin.analysis.viewOverview");
    backBtn.onclick = _loadDefaultOverview;
    progress.appendChild(backBtn);
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
    if (analysisRunning || hasAnalysisProgress) {
      btnProgress.classList.remove("hidden");
      btnProgress.textContent = currentView === "analyzing" ? _tt("twin.btn.viewOverview") : _tt("twin.btn.viewProgress");
    } else {
      btnProgress.classList.add("hidden");
    }
  }

  async function _stopAnalysis() {
    if (analysisAbort) analysisAbort.abort();
    _stopBackgroundPoll();
    _stopStatsPoll();
    const runId = _activeRunId;
    if (runId) {
      try {
        await fetch("/api/twin/cancel", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: runId, lang: _getLang() }),
        });
      } catch (e) {}
      const run = await _refreshAuthoritativeProgressSnapshot({ error: _lastError });
      if (run) {
        hasAnalysisProgress = true;
        currentView = "analyzing";
        _showOnlyView("analysis");
        _renderRunProgress(run, false);
        _appendBackToOverviewBtn();
      }
    }
    // Don't null analysisAbort here — let .catch/.finally do cleanup
    // (otherwise the stale-callback guard blocks state reset)
    analysisRunning = false;
    _updateAnalyzeButton();
    const updatedEl = document.getElementById("twin-last-analyzed");
    if (updatedEl) { updatedEl.textContent = _tt("twin.status.stopped"); updatedEl.classList.remove("loading"); }
  }

  // ── Overview: Vertical Pipeline Layout ──
  function loadOverview(runId) {
    _reloadCurrentView = null;
    const requestedRunId = runId || "";
    const url = "/api/twin/overview";
    fetch(requestedRunId ? _runScopedUrl(url, requestedRunId) : _withRunId(url, { includeViewRun: false }))
      .then(r => r.json())
      .then((data) => {
        overviewData = data;
        if (data && data.run_id) {
          if (requestedRunId || !_viewRunId) _setViewRunId(data.run_id);
        } else {
          _setViewRunId("");
        }
        renderOverview(data);
      })
      .catch(() => { renderOverviewEmpty(); if (window.showToast) window.showToast.error('Failed to load overview', 0, { label: 'Retry', callback: () => loadOverview() }); });
  }

  function _renderOverviewRunSwitcher(container, currentRunId) {
    if (!container || !currentRunId) return;
    let mount = container.querySelector(".twin-overview-run-switcher");
    if (!mount) {
      mount = document.createElement("div");
      mount.className = "twin-overview-run-switcher";
      container.insertBefore(mount, container.firstChild);
    }
    fetch("/api/twin/runs?limit=10")
      .then(r => r.json())
      .then((p) => {
        const runs = ((p && p.ok && Array.isArray(p.runs)) ? p.runs : [])
          .filter((run) => {
            const stats = (run && run.stats) || {};
            return (stats.events || 0) + (stats.cards || 0) + (stats.traits || 0) > 0;
          });
        if (!runs.length) {
          mount.remove();
          return;
        }
        let html = '<div class="twin-overview-run-switcher-head">' +
          '<span>' + esc(_tt("twin.overview.runSwitcher")) + '</span>' +
          '<strong>' + esc(_tt("twin.overview.viewingRun", { id: currentRunId })) + '</strong>' +
          '<button type="button" class="btn btn-ghost btn-sm twin-overview-progress-btn">' +
          esc(_tt("twin.overview.openProgress")) + '</button>' +
          '</div><div class="twin-overview-run-list">';
        runs.forEach((run) => {
          const rid = run.run_id || "";
          if (!rid) return;
          const shortId = rid.length > 14 ? rid.slice(0, 14) + "..." : rid;
          const stats = run.stats || {};
          html += '<button type="button" class="twin-overview-run-chip' +
            (rid === currentRunId ? " is-current" : "") +
            '" data-run-id="' + esc(rid) + '">' +
            '<span class="twin-run-badge rs-' + esc(run.status || "empty") + '">' +
            esc(_tt(_runStatusKey(run.status))) + '</span>' +
            '<span class="twin-overview-run-id">' + esc(shortId) + '</span>' +
            '<span class="twin-overview-run-counts">' +
            esc(_tt("twin.progress.stats", {
              events: stats.events || 0,
              cards: stats.cards || 0,
              traits: stats.traits || 0,
            })) + '</span>' +
            '</button>';
        });
        html += '</div>';
        mount.innerHTML = html;
        mount.querySelectorAll(".twin-overview-run-chip").forEach((btn) => {
          const rid = btn.getAttribute("data-run-id");
          if (!rid) return;
          btn.onclick = () => loadOverview(rid);
        });
        const progressBtn = mount.querySelector(".twin-overview-progress-btn");
        if (progressBtn) progressBtn.onclick = () => _selectTwinRunForViewing(currentRunId);
      })
      .catch(() => {});
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
            <span class="twin-status-badge ${statusClass}">${esc(_statusLabel(status))}</span>
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
            <span class="twin-trait-col-name">${esc(_categoryLabel(cat.key))}</span>
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
            <div class="twin-runtime-metrics" aria-label="${esc(_tt("twin.runtime.sourceCounts"))}">
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
    _renderOverviewRunSwitcher(container, data.run_id || _viewRunId || "");

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
    _reloadCurrentView = () => loadEventsList(signalFilter);
    let url = "/api/twin/events?limit=200";
    if (signalFilter) url += `&signal_type=${encodeURIComponent(signalFilter)}`;
    fetch(_withRunId(url))
      .then(r => r.json())
      .then(data => renderEventsList(data.events || [], signalFilter))
      .catch(e => { console.error("Failed to load events:", e); if (window.showToast) window.showToast.error('Failed to load events', 0, { label: 'Retry', callback: () => loadEventsList(signalFilter) }); });
  }

  function renderEventsList(items, activeFilter) {
    currentView = "events";
    _showOnlyView("dimension");
    const container = document.getElementById("twin-detail");
    setBreadcrumb([{ label: _tt("twin.events.title"), onclick: () => loadEventsList() }]);

    const filters = ["all", "correction", "acceptance", "escalation", "question"];
    let html = `<div class="twin-detail-header" style="--dim-color:#3b82f6">
      <span class="twin-dim-icon">📝</span>
      <span class="twin-detail-title">${esc(_tt("twin.events.title"))}</span>
      <span class="twin-dim-count">${esc(_tt("twin.count", { n: items.length }))}</span>
    </div>
    <div class="twin-filter-chips">
      ${filters.map(f => `<span class="twin-filter-chip ${(!activeFilter && f === "all") || activeFilter === f ? "active" : ""}" data-filter="${f}">${esc(_signalLabel(f))}</span>`).join("")}
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
          <span class="twin-ep-signal ${sig}">${esc(_signalLabel(sig))}</span>
          <span class="twin-ep-domain">${esc(e.domain || "")}</span>
          <span class="twin-ep-date">${esc((e.created_at || "").slice(0, 10))}</span>
        </div>
        <div class="twin-ep-body">
          <div><b>${esc(_tt("twin.field.ai"))}</b> ${esc(truncate(e.ai_action, 120))}</div>
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
    _reloadCurrentView = () => loadCards();
    fetch(_withRunId("/api/twin/cards?limit=200"))
      .then(r => r.json())
      .then(data => renderCards(data.cards || []))
      .catch(e => { console.error("Failed to load cards:", e); if (window.showToast) window.showToast.error('Failed to load cards', 0, { label: 'Retry', callback: () => loadCards() }); });
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
          ${status ? `<span class="twin-status-badge ${statusClass}">${esc(_statusLabel(status))}</span>` : ""}
          ${conf !== null ? `<span class="twin-conf">${conf}%</span>` : ""}
          ${card.evidence_count ? `<span class="twin-ep-count">${esc(_tt("twin.card.eventCount", { n: card.evidence_count }))}</span>` : ""}
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
    _reloadCurrentView = () => loadCardDetail(cardId);
    fetch(`/api/twin/card/${cardId}?lang=${encodeURIComponent(_getLang())}`)
      .then(r => r.json())
      .then(data => renderCardDetail(data))
      .catch(e => { console.error("Failed to load card detail:", e); if (window.showToast) window.showToast.error('Failed to load card detail', 0, { label: 'Retry', callback: () => loadCardDetail(cardId) }); });
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
          ${status ? `<span class="twin-status-badge ${status === "confirmed" ? "confirmed" : status === "emerging" ? "emerging" : "hypothesis"}">${esc(_statusLabel(status))}</span>` : ""}
          ${conf !== null ? `<span class="twin-conf">${conf}%</span>` : ""}
          ${card.evidence_count ? `<span class="twin-ep-count">${esc(_tt("twin.card.eventCount", { n: card.evidence_count }))}</span>` : ""}
          ${tags ? tags.split(", ").map(t => `<span class="twin-tag">${esc(t)}</span>`).join("") : ""}
        </div>
      </div>`;

    if (evidence.length) {
      html += `<div class="twin-trace-section">
        <h4>${esc(_tt("twin.card.supportEvents", { n: evidence.length }))}</h4>`;
      for (const ep of evidence) {
        html += `<div class="twin-episode-card">
          <div class="twin-ep-header">
            <span class="twin-ep-signal ${ep.signal_type || ""}">${esc(_signalLabel(ep.signal_type))}</span>
            <span class="twin-ep-domain">${esc(ep.domain)}</span>
            <span class="twin-ep-date">${esc((ep.created_at || "").slice(0, 10))}</span>
          </div>
          <div class="twin-ep-body">
            <div><b>${esc(_tt("twin.field.ai"))}</b> ${esc(truncate(ep.ai_action, 120))}</div>
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
    _reloadCurrentView = () => loadTraits(category);
    let url = "/api/twin/traits?limit=200";
    if (category) url += `&category=${encodeURIComponent(category)}`;
    fetch(_withRunId(url))
      .then(r => r.json())
      .then(data => renderTraits(data.traits || [], category))
      .catch(e => { console.error("Failed to load traits:", e); if (window.showToast) window.showToast.error('Failed to load traits', 0, { label: 'Retry', callback: () => loadTraits(category) }); });
  }

  function renderTraits(items, category) {
    currentView = "traits";
    _showOnlyView("dimension");
    const container = document.getElementById("twin-detail");
    const title = category ? _categoryLabel(category) : _tt("twin.traits.allTitle");
    setBreadcrumb([{ label: title, onclick: () => loadTraits(category) }]);

    const cat = TRAIT_CATEGORIES.find(c => c.key === category) || { icon: "🧬", color: "#7c3aed" };

    let html = `<div class="twin-detail-header" style="--dim-color:${cat.color}">
      <span class="twin-dim-icon">${cat.icon}</span>
      <span class="twin-detail-title">${esc(title)}</span>
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
          <div><b>${esc(t.name)}</b> <span class="twin-tag">${esc(_categoryLabel(t.category))}</span></div>
          <div class="twin-item-sub">${esc(t.description)}</div>
        </div>
        <div class="twin-item-meta">
          ${status ? `<span class="twin-status-badge ${statusClass}">${esc(_statusLabel(status))}</span>` : ""}
          ${str !== null ? `<span class="twin-conf">${str}%</span>` : ""}
          ${t.evidence_count ? `<span class="twin-ep-count">${esc(_tt("twin.card.eventCount", { n: t.evidence_count }))}</span>` : ""}
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
    _reloadCurrentView = () => loadTraitDetail(traitId);
    fetch(`/api/twin/trait/${traitId}?lang=${encodeURIComponent(_getLang())}`)
      .then(r => r.json())
      .then(data => renderTraitDetail(data))
      .catch(e => { console.error("Failed to load trait detail:", e); if (window.showToast) window.showToast.error('Failed to load trait detail', 0, { label: 'Retry', callback: () => loadTraitDetail(traitId) }); });
  }

  function renderTraitDetail(data) {
    currentView = "trait-detail";
    _showOnlyView("item");
    const container = document.getElementById("twin-item-view");
    const trait = data.trait || {};
    const cards = data.supporting_cards || [];
    const cat = TRAIT_CATEGORIES.find(c => c.key === trait.category) || { icon: "🧬", color: "#7c3aed" };
    setBreadcrumb([
      { label: trait.category ? _categoryLabel(trait.category) : _tt("twin.traits.fallbackCat"), onclick: () => loadTraits(trait.category) },
      { label: trait.name || "detail" },
    ]);

    const str = trait.strength != null ? Math.round(trait.strength * 100) : null;
    const status = trait.status || "";

    let html = `<div class="twin-item-detail">
      <div class="twin-item-detail-header" style="border-left:4px solid ${cat.color}">
        <span>${cat.icon} ${esc(_categoryLabel(trait.category))}</span>
        <span class="twin-item-id">${esc(trait.id)}</span>
      </div>
      <div class="twin-item-detail-body" style="padding:16px">
        <div style="margin-bottom:12px;font-size:1.1em"><b>${esc(trait.name)}</b></div>
        <div style="margin-bottom:12px">${esc(trait.description)}</div>
        <div class="twin-item-meta">
          ${status ? `<span class="twin-status-badge ${status === "confirmed" ? "confirmed" : status === "emerging" ? "emerging" : "hypothesis"}">${esc(_statusLabel(status))}</span>` : ""}
          ${str !== null ? `<span class="twin-conf">${str}%</span>` : ""}
          ${trait.evidence_count ? `<span class="twin-ep-count">${esc(_tt("twin.card.eventCount", { n: trait.evidence_count }))}</span>` : ""}
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

  function startAnalysis(resumeMode, engineOverride) {
    if (analysisRunning) return; // prevent double-start
    _stopBackgroundPoll(); // a direct SSE stream supersedes background polling
    if (!resumeMode) _setViewRunId("");
    _suggestedEngine = "";
    analysisRunning = true;
    hasAnalysisProgress = true;
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
      // Fix: SSE idle watchdog — if no event received for 30s, warn the user
      // so they know the backend may have hung or the connection was dropped.
      // Grace: the first event gets a longer timeout (90s) because AI engine
      // cold-start (Claude auth probe, Codex health check) can take 30-60s.
      _watchdogTimer: null,
      _lastEventTime: Date.now(),
      _firstEventReceived: false,
    };

    const IDLE_TIMEOUT_INITIAL = 90000;  // 90s grace for engine cold-start
    const IDLE_TIMEOUT_NORMAL  = 30000;  // 30s after first event

    // Kick off the watchdog that fires if no SSE event is seen within the timeout.
    function _resetIdleWatchdog() {
      streamState._lastEventTime = Date.now();
      if (streamState._watchdogTimer) {
        clearTimeout(streamState._watchdogTimer);
        streamState._watchdogTimer = null;
      }
      const timeout = streamState._firstEventReceived ? IDLE_TIMEOUT_NORMAL : IDLE_TIMEOUT_INITIAL;
      streamState._watchdogTimer = setTimeout(() => {
        const elapsed = Date.now() - streamState._lastEventTime;
        if (elapsed >= timeout) {
          // Only warn once and only if the stream hasn't ended yet
          if (analysisRunning && !streamState.failed) {
            const container = document.getElementById("twin-stream-output");
            if (container && !container.querySelector(".twin-stream-idle-warning")) {
              const warn = document.createElement("div");
              warn.className = "twin-stream-idle-warning";
              warn.textContent = _tt("twin.stream.idle");
              container.appendChild(warn);
              _autoScroll();
            }
          }
        }
      }, timeout + 2000);
    }

    // Start the watchdog immediately (before any SSE event arrives)
    _resetIdleWatchdog();
    // Poll the backend for real-time stats/stage status alongside the SSE
    // tool stream so events/cards/traits counters stay live (缺陷①/③).
    _startStatsPoll();

    // Reset watchdog on every SSE event
    const _origHandleFn = evt => _handleStreamEvent(evt, streamState);
    const _wrappedHandleFn = function(evt) {
      streamState._firstEventReceived = true;
      _resetIdleWatchdog();
      _origHandleFn(evt);
    };

    // Abort previous if any
    if (analysisAbort) analysisAbort.abort();
    const abortCtrl = new AbortController();
    analysisAbort = abortCtrl;

    const body = { lang: _getLang(), engine: engineOverride || _getEngine() };
    if (resumeMode) {
      body.resume = true;
      if (_activeRunId) body.run_id = _activeRunId;
    }
    let analysisAttached = false;

    fetch("/api/twin/analyze", {
      method: "POST",
      signal: abortCtrl.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(async (response) => {
        if (response.status === 409) {
          analysisAttached = await _reattachToRunningTwinAnalysis();
          if (analysisAttached) return;
        }
        return window.readSseStream(response, _wrappedHandleFn);
      })
      .then(() => {
        // Clear watchdog since the stream ended normally
        if (streamState._watchdogTimer) { clearTimeout(streamState._watchdogTimer); streamState._watchdogTimer = null; }
        if (analysisAttached) return;
        _finishAnalysis(streamState, streamState.failed);
      })
      .catch((e) => {
        // Clear watchdog
        if (streamState._watchdogTimer) { clearTimeout(streamState._watchdogTimer); streamState._watchdogTimer = null; }
        if (analysisAttached) return;
        if (e.name === "AbortError") {
          if (analysisAbort === abortCtrl) { analysisRunning = false; _updateAnalyzeButton(); }
          return;
        }
        _appendAnalysisError(String(e));
        _finishAnalysis(streamState, true);
      })
      .finally(() => {
        if (streamState._watchdogTimer) { clearTimeout(streamState._watchdogTimer); streamState._watchdogTimer = null; }
        if (analysisAbort === abortCtrl) analysisAbort = null;
      });
  }

  async function _finishAnalysis(state, failed = false) {
    analysisRunning = false;
    _stopStatsPoll();
    const authoritativeRun = await _refreshAuthoritativeProgressSnapshot(
      failed ? { status: "failed", error: _lastError } : null,
    );
    const finalStatus = authoritativeRun && authoritativeRun.status;
    const incomplete = failed || _isTerminalIncomplete(finalStatus);
    // Fix: hasAnalysisProgress should only be true for partial/incomplete runs.
    // A fully completed run should NOT show "view progress" (no SSE data to view).
    if (incomplete) {
      hasAnalysisProgress = true;
      // Persist the failure so it survives tab switches / reloads.
      _saveProgressSnapshot({ status: finalStatus || "failed", error: _lastError });
    } else {
      hasAnalysisProgress = false;
      // A clean completion has no recoverable progress; drop the snapshot.
      _clearProgressSnapshot();
    }
    _finalizeToolGroup(state);
    _updateAnalyzeButton();
    const updatedEl = document.getElementById("twin-last-analyzed");
    if (updatedEl && !failed) { updatedEl.textContent = _tt("twin.status.updated", { time: new Date().toLocaleTimeString() }); }
    // Send browser notification on completion
    if (!failed && typeof window.sendBrowserNotification === 'function') {
      window.sendBrowserNotification(
        _tt("notify.twinDone"),
        _tt("notify.analysisDone", { label: 'Twin' })
      );
    }
    // If user is still watching the analysis, switch to overview
    if (currentView === "analyzing" && !failed) {
      setBreadcrumb([{ label: _tt("twin.bc.done") }]);
      // Replace the thinking dots with a complete banner
      const container = document.getElementById("twin-stream-output");
      if (container) {
        const existingComplete = container.querySelector(".twin-analysis-complete-banner");
        if (!existingComplete) {
          const banner = document.createElement("div");
          banner.className = "twin-analysis-complete-banner";
          banner.innerHTML =
            '<span class="twin-analysis-complete-icon">&#10003;</span>' +
            '<span class="twin-analysis-complete-label">' + esc(_tt("twin.bc.done")) + '</span>' +
            '<button type="button" class="btn btn-ghost btn-sm" id="twin-finish-back-btn">' +
            esc(_tt("twin.analysis.viewOverview")) +
            '</button>';
          container.appendChild(banner);
          const backBtn = document.getElementById("twin-finish-back-btn");
          if (backBtn) backBtn.onclick = _loadDefaultOverview;
        }
      }
      // Auto-transition after a short delay (only if user hasn't clicked anything)
      setTimeout(() => {
        if (currentView === "analyzing") {
          _loadDefaultOverview();
        }
      }, 3000);
    } else if (currentView === "analyzing" && failed) {
      _markAnalysisFailed(state);
    }
  }

  function _markAnalysisFailed(state) {
    if (state) state.failed = true;
    setBreadcrumb([{ label: _tt("twin.bc.failed") }]);
    _appendAnalysisErrorActions();
    _updateProgressButton();
  }

  function _appendAnalysisError(message) {
    const container = document.getElementById("twin-stream-output");
    if (!container) return;
    _hideThinking(container);
    const errDiv = document.createElement("div");
    errDiv.className = "twin-stream-error";
    errDiv.innerHTML = `❌ ${esc(message || "Unknown error")}`;
    container.appendChild(errDiv);
  }

  function _appendAnalysisErrorActions() {
    const container = document.getElementById("twin-stream-output");
    if (!container || container.querySelector(".twin-analysis-error-actions")) return;
    const actions = document.createElement("div");
    actions.className = "twin-analysis-error-actions";
    const switchBtn = _suggestedEngine
      ? `<button type="button" class="btn-text" data-action="switch">${esc(_tt("twin.analysis.switchEngine", { engine: _suggestedEngine }))}</button>`
      : "";
    actions.innerHTML = `
      <div class="twin-analysis-error-title">${esc(_tt("twin.analysis.failedTitle"))}</div>
      <div class="twin-analysis-error-hint">${esc(_tt("twin.analysis.failedHint"))}</div>
      <div class="twin-analysis-error-buttons">
        <button type="button" class="btn-text" data-action="overview">${esc(_tt("twin.analysis.viewOverview"))}</button>
        ${switchBtn}
        <button type="button" class="btn-text" data-action="retry">${esc(_tt("twin.analysis.retry"))}</button>
        <button type="button" class="btn-text" data-action="resume">${esc(_tt("twin.analysis.resume"))}</button>
      </div>`;
    actions.onclick = (e) => {
      const btn = e.target.closest("[data-action]");
      if (!btn) return;
      const action = btn.getAttribute("data-action");
      if (action === "overview") _loadDefaultOverview();
      else if (action === "retry") startAnalysis(false);
      else if (action === "switch") startAnalysis(true, _suggestedEngine);
      else if (action === "resume") _startAnalysisWithResume(_activeRunId);
    };
    container.appendChild(actions);
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
            _setViewRunId(_activeRunId);
            try {
              localStorage.setItem(TWIN_ACTIVE_RUN_KEY, _activeRunId);
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
          updatedEl.textContent = _tt("twin.status.updated", { time: new Date().toLocaleTimeString() });
          updatedEl.classList.remove("loading");
        }
        break;

      case "error":
        state.failed = true;
        if (evt.suggest_engine) _suggestedEngine = evt.suggest_engine;
        _lastError = evt.message || "Unknown error";
        _saveProgressSnapshot({ status: "failed", error: _lastError });
        _finalizeToolGroup(state);
        _appendAnalysisError(evt.message || "Unknown error");
        if (updatedEl) {
          updatedEl.textContent = _tt("twin.status.error", { msg: evt.message || "" });
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
    el.innerHTML = `<span class="evolve-tg-count">⚡ ${esc(_tt("twin.tg.tools", { n: state.toolGroupTotal }))}</span> · ${parts.join(" · ")}`;
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
    _reloadCurrentView = () => loadRuntimePreview(options);
    fetch(_withRunId("/api/twin/runtime-preview"))
      .then(r => r.json())
      .then(data => renderRuntimePreview(data, options))
      .catch(e => { console.error("Failed to load runtime preview:", e); if (window.showToast) window.showToast.error('Failed to load runtime preview', 0, { label: 'Retry', callback: () => loadRuntimePreview(options) }); });
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
      return `<div class="twin-runtime-section-empty">${esc(_tt("twin.runtime.sectionEmpty"))}</div>`;
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
          <span>${esc(_tt("twin.runtime.summary"))}</span>
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
    setBreadcrumb([{ label: _tt("twin.runtime.heroTitle"), onclick: () => loadRuntimePreview() }]);

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
            <div class="twin-runtime-kicker">${esc(_tt("twin.runtime.compiledKicker"))}</div>
            <h2>${esc(_tt("twin.runtime.heroTitle"))}</h2>
            <p>${esc(_tt("twin.runtime.desc"))}</p>
            <div class="twin-runtime-compact-summary">
              <span><b>${cardCount}</b> ${esc(_tt("twin.runtime.metricCards"))}</span>
              <span><b>${traitCount}</b> ${esc(_tt("twin.runtime.metricTraits"))}</span>
              <span>${hasData ? esc(_tt("twin.runtime.ready")) : esc(_tt("twin.runtime.empty"))}</span>
            </div>
          </div>
        </div>
        <div class="twin-runtime-hero-side">
          <span class="twin-runtime-status ${hasData ? "ready" : "no-data"}">${hasData ? esc(_tt("twin.runtime.readyToSync")) : esc(_tt("twin.runtime.noData"))}</span>
          <span class="twin-runtime-target-file">CLAUDE.md</span>
          ${hasData ? `<button class="btn-text twin-runtime-sync-button twin-runtime-hero-action" id="twin-runtime-sync-btn">${esc(_tt("twin.runtime.syncBtn"))}</button>` : ""}
        </div>
      </div>
      <div class="twin-runtime-document">
        <div class="twin-runtime-document-head">
          <span>${esc(_tt("twin.runtime.compiledPreview"))}</span>
          <span>${esc(_tt("twin.runtime.cardsTraits", { cards: cardCount, traits: traitCount }))}</span>
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
    const syncRunId = _viewRunId || _activeRunId;
    const body = syncRunId ? { run_id: syncRunId } : {};
    body.lang = _getLang();
    body.action = "preview";

    fetch("/api/twin/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok) {
          if (window.showToast) window.showToast.error(_tt("twin.sync.failed", { error: data.error || "Preview failed" }));
          return;
        }
        if (!data.diff) {
          if (window.showToast) window.showToast.info("No changes to sync");
          return;
        }
        window.showSyncDiffDialog({
          title: _tt("twin.sync.confirm"),
          diff: data.diff,
          onConfirm: _executeTwinSync,
        });
      })
      .catch((e) => {
        if (window.showToast) window.showToast.error(_tt("twin.sync.failed", { error: e }));
      });
  }

  function _executeTwinSync() {
    const syncRunId = _viewRunId || _activeRunId;
    const body = syncRunId ? { run_id: syncRunId } : {};
    body.lang = _getLang();
    body.action = "execute";
    fetch("/api/twin/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          if (window.showToast) window.showToast.success(_tt("twin.sync.success", { cards: data.cards_synced || 0, traits: data.traits_synced || 0 }));
        } else {
          if (window.showToast) window.showToast.error(_tt("twin.sync.failed", { error: data.error || "unknown" }));
        }
      })
      .catch((e) => {
        if (window.showToast) window.showToast.error(_tt("twin.sync.failed", { error: e }));
      });
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
  _applyTwinCssVars();
  if (window.applyI18nDom) window.applyI18nDom(document);
})();
