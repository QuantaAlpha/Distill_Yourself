/**
 * Conversation rendering — load session, render messages, tool blocks.
 *
 * Usage:
 *   import { loadSession, renderMessages, ... } from './conversation.js';
 */

import { state } from './state.js';
import { $, $$ } from './dom.js';
import { esc, formatDate, formatTime, renderMarkdown } from './utils.js';
import { t } from './i18n.js';

// ── Late-bound references to functions in other modules ──────────
// Set by the main module via registerConversationDeps() to avoid
// circular imports.
let _deps = {
  showView: () => {},
  buildOutline: () => {},
  highlightOutlineItem: () => {},
  jumpToMessage: () => {},
  updateSessionAiHeader: () => {},
  restoreSessionAiMessages: () => {},
};

export function registerConversationDeps(deps) {
  Object.assign(_deps, deps);
}

// ── Load Session ─────────────────────────────────────────────────
export async function loadSession(sessionId, jumpToIndex, pushHistory = true) {
  // Cancel any in-flight session load
  if (state._sessionAbort) state._sessionAbort.abort();
  state._sessionAbort = new AbortController();

  state.currentSessionId = sessionId;
  if (pushHistory) {
    history.pushState({ view: "conversation", sessionId }, "", `#${sessionId}`);
  }
  $$('#session-list li').forEach(li => {
    li.classList.toggle('active', li.dataset.id === sessionId);
  });

  const messagesContainer = $("#messages-container");
  const convTitle = $("#conv-title");
  const convMeta = $("#conv-meta");

  _deps.showView("conversation");
  messagesContainer.innerHTML = '<div class="insights-loading"><div class="skeleton-block"></div><div class="skeleton-block" style="width:85%"></div><div class="skeleton-block" style="width:60%"></div></div>';

  try {
    const resp = await fetch(`/api/session/${sessionId}`, { signal: state._sessionAbort.signal });
    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    const data = await resp.json();
    convTitle.textContent = data.title;
    const metaParts = [`${data.project} · ${formatDate(data.date)} · ${data.messages.length} messages`];
    convMeta.innerHTML = "";
    convMeta.appendChild(document.createTextNode(metaParts[0]));
    if (data.filePath) {
      const pathRow = document.createElement("div");
      pathRow.className = "conv-filepath-row";
      const pathText = document.createElement("span");
      pathText.textContent = data.filePath;
      pathRow.appendChild(pathText);
      const copyBtn = document.createElement("button");
      copyBtn.className = "conv-filepath-copy";
      copyBtn.title = t("conv.copyPath");
      copyBtn.textContent = "📋";
      copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(data.filePath).then(() => {
          copyBtn.textContent = "✅";
          setTimeout(() => { copyBtn.textContent = "📋"; }, 1500);
        });
      });
      pathRow.appendChild(copyBtn);
      convMeta.appendChild(pathRow);
    }

    state.currentMessages = data.messages;
    renderMessages(data.messages);
    _deps.buildOutline(data.messages);
    // Switch to AI tab
    document.querySelectorAll(".rp-tab").forEach(t => t.classList.toggle("active", t.dataset.panel === "ai"));
    document.querySelectorAll(".rp-content").forEach(c => c.classList.toggle("hidden", !c.id.endsWith("ai")));
    _deps.updateSessionAiHeader();
    _deps.restoreSessionAiMessages();

    // Outline scroll tracking (remove previous listener to prevent leaks)
    const mc = document.getElementById("messages-container");
    if (state._scrollHandler) mc.removeEventListener("scroll", state._scrollHandler);
    let _scrollTick = false;
    state._scrollHandler = () => {
      if (_scrollTick || !state.outlineVisible) return;
      _scrollTick = true;
      requestAnimationFrame(() => {
        _scrollTick = false;
        const userMsgs = mc.querySelectorAll(".msg.user-msg");
        const containerTop = mc.getBoundingClientRect().top;
        let closest = null;
        for (const el of userMsgs) {
          const r = el.getBoundingClientRect();
          if (r.top <= containerTop + 100) closest = el;
        }
        if (closest) _deps.highlightOutlineItem(parseInt(closest.dataset.idx));
      });
    };
    mc.addEventListener("scroll", state._scrollHandler, { passive: true });

    if (typeof jumpToIndex === "number") {
      setTimeout(() => _deps.jumpToMessage(jumpToIndex), 100);
    }
  } catch (err) {
    if (err.name === "AbortError") return; // superseded by newer load
    messagesContainer.innerHTML = `<div style="padding:40px;text-align:center;color:#e57373">${esc(t("conv.loadFailed", { msg: err.message }))}</div>`;
  }
}

// ── Render Messages ──────────────────────────────────────────────
export function renderMessages(messages) {
  const messagesContainer = $("#messages-container");
  messagesContainer.innerHTML = "";

  // Group messages into turns: user turn vs assistant turn (consecutive assistant + tool_result)
  const turns = [];
  let currentTurn = null;

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    const isUser = msg.type === "user";
    const isToolResult = msg.type === "tool_result";

    if (isUser && !isToolResult) {
      // User message starts a new user turn
      currentTurn = { type: "user", messages: [msg], startIdx: i };
      turns.push(currentTurn);
      currentTurn = null; // user turns are always single
    } else {
      // Assistant or tool_result → group into assistant turn
      if (!currentTurn || currentTurn.type !== "assistant") {
        currentTurn = { type: "assistant", messages: [], startIdx: i };
        turns.push(currentTurn);
      }
      currentTurn.messages.push(msg);
    }
  }

  // Render each turn
  let msgIdx = 0;
  turns.forEach((turn) => {
    if (turn.type === "user") {
      const el = createUserMsgEl(turn.messages[0], msgIdx);
      messagesContainer.appendChild(el);
      msgIdx++;
    } else {
      const el = createAssistantTurnEl(turn.messages, msgIdx);
      messagesContainer.appendChild(el);
      msgIdx += turn.messages.length;
    }
  });

  // Reset filters
  state.userOnlyMode = false;
  state.allCollapsed = false;
  $("#btn-user-only").classList.remove("active");
  $("#btn-collapse-all").classList.remove("active");
}

const COLLAPSE_THRESHOLD = 300; // chars — collapse texts longer than this

export function createUserMsgEl(msg, idx) {
  const div = document.createElement("div");
  div.className = "msg user-msg";
  div.dataset.idx = idx;
  div.dataset.type = "user";
  div.id = `msg-${idx}`;
  if (msg.isSidechain) div.classList.add("sidechain");

  const timeStr = msg.timestamp ? formatTime(msg.timestamp) : "";
  const hasLong = msg.content.some(b => b.type === "text" && b.text.length > COLLAPSE_THRESHOLD);
  let html = `<div class="msg-label">${hasLong ? '<span class="msg-collapse-toggle open">▶</span>' : ""}<span style="font-size:14px">👤</span> ${t("conv.you")} <span style="font-weight:400;font-size:10px;color:var(--text-muted)">${timeStr}</span>${hasLong ? `<span class="msg-fold">${t("conv.showMore")}</span>` : ""}</div>`;

  for (const block of msg.content) {
    if (block.type === "text") {
      const isLong = block.text.length > COLLAPSE_THRESHOLD;
      html += `<div class="text-collapsible${isLong ? " collapsed" : ""}">`;
      html += `<div class="msg-text">${renderMarkdown(block.text)}</div>`;
      if (isLong) html += `<button class="text-toggle">${t("conv.showMore")}</button>`;
      html += `</div>`;
    } else if (block.type === "image") {
      html += `<div class="image-placeholder">🖼️ ${block.alt || t("conv.image")}</div>`;
    }
  }

  div.innerHTML = html;
  bindUserFoldToggle(div);
  return div;
}

export function createAssistantTurnEl(messages, startIdx) {
  const div = document.createElement("div");
  div.className = "msg assistant-turn";
  div.dataset.idx = startIdx;
  div.dataset.type = "assistant";
  div.id = `msg-${startIdx}`;

  // Collect all blocks in order
  const allBlocks = [];
  for (const msg of messages) {
    for (const block of msg.content) {
      allBlocks.push(block);
    }
  }

  // Stats for turn header
  let toolUseCount = 0;
  let thinkingCount = 0;
  const toolNameSet = new Set();
  for (const block of allBlocks) {
    if (block.type === "tool_use") { toolUseCount++; toolNameSet.add(block.name); }
    else if (block.type === "thinking") { thinkingCount++; }
  }
  const hasProcessBlocks = toolUseCount > 0 || thinkingCount > 0;

  // Group consecutive process blocks (tool_use/tool_result/thinking)
  const groups = [];
  let curProcessGroup = null;
  for (const block of allBlocks) {
    const isProcess = block.type === "tool_use" || block.type === "tool_result" || block.type === "thinking";
    if (isProcess) {
      if (!curProcessGroup) {
        curProcessGroup = { type: "process", blocks: [] };
        groups.push(curProcessGroup);
      }
      curProcessGroup.blocks.push(block);
    } else {
      curProcessGroup = null;
      groups.push({ type: "content", block });
    }
  }

  let html = "";
  const firstTs = messages[0]?.timestamp;
  const timeStr = firstTs ? formatTime(firstTs) : "";

  // Turn-level collapse bar (only when there are tool/thinking blocks)
  if (hasProcessBlocks) {
    let parts = [];
    if (toolUseCount > 0) parts.push(t("conv.toolCalls", { n: toolUseCount }));
    if (thinkingCount > 0) parts.push(t("conv.thinkingCount", { n: thinkingCount }));
    html += `<div class="turn-collapse-bar collapsed">
      <span class="turn-collapse-toggle">▶</span>
      <span class="turn-collapse-label">${t("conv.agent")}</span>
      <span class="turn-collapse-summary">${parts.join(" · ")}</span>
      ${timeStr ? `<span class="turn-collapse-time">${timeStr}</span>` : ""}
    </div>`;
  }

  html += `<div class="turn-body"${hasProcessBlocks ? ' style="display:none"' : ""}>`;

  for (const group of groups) {
    if (group.type === "process") {
      const gToolCount = group.blocks.filter(b => b.type === "tool_use").length;
      const gToolNames = [...new Set(group.blocks.filter(b => b.type === "tool_use").map(b => b.name))];
      const autoCollapse = gToolCount >= 2;

      if (autoCollapse) {
        html += `<div class="tool-call-group collapsed">`;
        html += `<div class="tool-group-header">
          <span class="tool-group-toggle">▶</span>
          <span class="tool-group-label">${t("conv.toolCalls", { n: gToolCount })}</span>
          <span class="tool-group-names">${esc(gToolNames.join(", "))}</span>
        </div>`;
        html += `<div class="tool-group-body" style="display:none">`;
      }

      for (const block of group.blocks) {
        switch (block.type) {
          case "tool_use": html += renderToolUse(block); break;
          case "tool_result": html += renderToolResult(block); break;
          case "thinking": html += renderThinking(block); break;
        }
      }

      if (autoCollapse) {
        html += `</div></div>`;
      }
    } else if (group.block) {
      const block = group.block;
      if (block.type === "text" && block.text?.trim()) {
        const isLong = block.text.length > COLLAPSE_THRESHOLD;
        html += `<div class="reply-card${isLong ? " collapsed" : ""}">`;
        html += `<div class="reply-label"><span style="font-size:13px">🤖</span> ${t("conv.assistant")}<button class="reply-copy" title="${t("conv.replyCopy.title")}">📋</button>${isLong ? ` <span class="reply-fold">${t("conv.showMore")}</span>` : ""}</div>`;
        html += `<div class="msg-text">${renderMarkdown(block.text)}</div>`;
        if (isLong) html += `<button class="text-toggle reply-text-toggle">${t("conv.showMore")}</button>`;
        html += `</div>`;
      } else if (block.type === "image") {
        html += `<div class="image-placeholder">🖼️ ${block.alt || t("conv.image")}</div>`;
      }
    }
  }

  html += `</div>`; // close turn-body

  if (timeStr && !hasProcessBlocks) {
    html += `<div class="turn-time">${timeStr}</div>`;
  }

  div.innerHTML = html;
  bindReplyFoldToggles(div);
  bindToolToggles(div);
  bindTurnCollapseToggle(div);
  bindToolGroupToggles(div);
  return div;
}

// ── Toggle / Fold Bindings ───────────────────────────────────────
export function bindTextToggles(container) {
  container.querySelectorAll(".text-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wrapper = btn.parentElement;
      const isCollapsed = wrapper.classList.contains("collapsed");
      wrapper.classList.toggle("collapsed", !isCollapsed);
      btn.textContent = isCollapsed ? t("conv.showLess") : t("conv.showMore");
    });
  });
}

export function bindUserFoldToggle(container) {
  const triangle = container.querySelector(".msg-collapse-toggle");
  const foldBtn = container.querySelector(".msg-fold");
  const textToggle = container.querySelector(".text-toggle");
  const collapsible = container.querySelector(".text-collapsible");
  if (!collapsible) return;

  function toggle() {
    const isCollapsed = collapsible.classList.contains("collapsed");
    collapsible.classList.toggle("collapsed", !isCollapsed);
    const label = isCollapsed ? t("conv.collapse") : t("conv.showMore");
    if (foldBtn) foldBtn.textContent = label;
    if (textToggle) textToggle.textContent = label;
    if (triangle) triangle.classList.toggle("open", isCollapsed);
  }

  if (triangle) triangle.addEventListener("click", toggle);
  if (foldBtn) foldBtn.addEventListener("click", toggle);
  if (textToggle) textToggle.addEventListener("click", toggle);
}

export function bindReplyFoldToggles(container) {
  container.querySelectorAll(".reply-card").forEach((card) => {
    const topBtn = card.querySelector(".reply-fold");
    const bottomBtn = card.querySelector(".reply-text-toggle");

    if (topBtn || bottomBtn) {
      function toggle(e) {
        if (e) e.stopPropagation();
        const isCollapsed = card.classList.contains("collapsed");
        card.classList.toggle("collapsed", !isCollapsed);
        const label = isCollapsed ? t("conv.collapse") : t("conv.showMore");
        if (topBtn) topBtn.textContent = label;
        if (bottomBtn) bottomBtn.textContent = label;
      }
      if (topBtn) topBtn.addEventListener("click", toggle);
      if (bottomBtn) bottomBtn.addEventListener("click", toggle);
    }

    // Copy button on reply card
    const copyBtn = card.querySelector(".reply-copy");
    if (copyBtn) {
      copyBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const textEl = card.querySelector(".msg-text");
        if (!textEl) return;
        navigator.clipboard.writeText(textEl.innerText).then(() => {
          copyBtn.textContent = "✅";
          setTimeout(() => { copyBtn.textContent = "📋"; }, 1500);
        });
      });
    }
  });
}

export function bindToolToggles(container) {
  container.querySelectorAll(".tool-header, .thinking-header").forEach((header) => {
    header.addEventListener("click", () => {
      const body = header.nextElementSibling;
      const toggle = header.querySelector(".tool-toggle");
      if (body) body.style.display = body.style.display === "none" ? "" : "none";
      if (toggle) toggle.classList.toggle("open");
    });
  });
}

export function bindTurnCollapseToggle(container) {
  const bar = container.querySelector(".turn-collapse-bar");
  if (!bar) return;
  bar.addEventListener("click", () => {
    const body = container.querySelector(".turn-body");
    const toggle = bar.querySelector(".turn-collapse-toggle");
    if (!body) return;
    const isOpen = toggle.classList.contains("open");
    body.style.display = isOpen ? "none" : "";
    toggle.classList.toggle("open", !isOpen);
    bar.classList.toggle("collapsed", isOpen);
  });
}

export function bindToolGroupToggles(container) {
  container.querySelectorAll(".tool-group-header").forEach((header) => {
    header.addEventListener("click", () => {
      const group = header.parentElement;
      const body = group.querySelector(".tool-group-body");
      const toggle = header.querySelector(".tool-group-toggle");
      if (!body) return;
      const isCollapsed = body.style.display === "none";
      body.style.display = isCollapsed ? "" : "none";
      if (toggle) toggle.classList.toggle("open", isCollapsed);
      group.classList.toggle("collapsed", !isCollapsed);
    });
  });
}

// ── Tool Rendering ───────────────────────────────────────────────
export function renderToolUse(block) {
  const inputStr = typeof block.input === "string"
    ? block.input
    : JSON.stringify(block.input, null, 2);
  // Tool-type CSS class for color coding
  const toolClass = getToolClass(block.name);
  // Tool-specific icon
  const icon = getToolIcon(block.name);
  // Determine a concise summary for the tool header
  let summary = "";
  if (block.input && typeof block.input === "object") {
    const pick = (v) => (typeof v === "string" ? v : (v == null ? "" : JSON.stringify(v)));
    if (block.input.command) summary = pick(block.input.command).substring(0, 80);
    else if (block.input.file_path) summary = pick(block.input.file_path);
    else if (block.input.pattern) summary = pick(block.input.pattern);
    else if (block.input.query) summary = pick(block.input.query).substring(0, 60);
    else if (block.input.description) summary = pick(block.input.description).substring(0, 60);
    else if (block.input.prompt) summary = pick(block.input.prompt).substring(0, 60);
  }
  // For Agent, show only the prompt in body
  const isAgent = (block.name || "").toLowerCase() === "agent";
  const bodyContent = isAgent && block.input && block.input.prompt
    ? block.input.prompt
    : inputStr;
  return `
    <div class="tool-block ${toolClass}">
      <div class="tool-header">
        <span class="tool-icon">${icon}</span>
        <span class="tool-name">${esc(block.name)}</span>
        ${summary ? `<span style="color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:400px">${esc(summary)}</span>` : ""}
        <span class="tool-toggle">▶</span>
      </div>
      <div class="tool-body${isAgent ? ' agent-prompt' : ''}" style="display:none">${esc(bodyContent)}</div>
    </div>`;
}

export function getToolClass(name) {
  const n = (name || "").toLowerCase();
  if (n === "bash") return "tool-bash";
  if (n === "read") return "tool-read";
  if (n === "edit") return "tool-edit";
  if (n.includes("grep")) return "tool-grep";
  if (n === "write") return "tool-write";
  if (n === "agent") return "tool-agent";
  if (n === "glob") return "tool-glob";
  return "";
}

export function getToolIcon(name) {
  const n = (name || "").toLowerCase();
  if (n === "bash") return "⚡";
  if (n === "read") return "📖";
  if (n === "edit") return "✏️";
  if (n.includes("grep")) return "🔍";
  if (n === "write") return "📝";
  if (n === "agent") return "🤖";
  if (n === "glob") return "📁";
  if (n.includes("todo")) return "📋";
  if (n.includes("web") || n.includes("fetch")) return "🌐";
  if (n.includes("skill")) return "⚙️";
  return "🔧";
}

export function renderToolResult(block) {
  let content = typeof block.content === "string" ? block.content : JSON.stringify(block.content);
  // Codex / CUA outputs arrive as a JSON-stringified array of {type,text|image} parts.
  // Flatten them into readable text instead of dumping raw JSON.
  if (typeof content === "string" && /^\s*\[/.test(content)) {
    try {
      const parsed = JSON.parse(content);
      if (Array.isArray(parsed)) {
        content = parsed.map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object") {
            if (item.type === "image" || item.image_url) return `🖼️ ${item.alt || t("conv.image")}`;
            if (typeof item.text === "string") return item.text;
          }
          return JSON.stringify(item);
        }).join("\n");
      }
    } catch { /* keep original string on parse failure */ }
  }
  return `
    <div class="tool-block tool-result">
      <div class="tool-header">
        <span class="tool-icon">📋</span>
        <span class="tool-name">${t("conv.result")}</span>
        <span class="tool-toggle">▶</span>
      </div>
      <div class="tool-body" style="display:none">${esc(content)}</div>
    </div>`;
}

export function renderThinking(block) {
  return `
    <div class="thinking-block">
      <div class="thinking-header">
        <span>💭</span>
        <span>${t("conv.thinking")}</span>
        <span class="tool-toggle">▶</span>
      </div>
      <div class="thinking-body" style="display:none">${esc(block.text)}</div>
    </div>`;
}

// ── User-only filter ─────────────────────────────────────────────
export function applyUserOnlyFilter() {
  $$(".msg").forEach((el) => {
    if (state.userOnlyMode) {
      // Show only user messages, hide assistant turns
      const isUser = el.classList.contains("user-msg");
      el.style.display = isUser ? "" : "none";
    } else {
      el.style.display = "";
    }
  });
}
