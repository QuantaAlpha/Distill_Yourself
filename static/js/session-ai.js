/**
 * Session-scoped AI right panel — chat with AI about the current session.
 *
 * Usage:
 *   import { openSessionAiPanel, updateSessionAiHeader, restoreSessionAiMessages,
 *            submitSessionAi, _setSessionAiButton, _stopSessionAi } from './session-ai.js';
 */

import { state } from './state.js';
import { $ } from './dom.js';
import { autoResizeTextarea } from './utils.js';
import { t } from './i18n.js';
import {
  appendChatMsg, createAssistantTurn, sendChatStream,
  _appendContinueButton,
} from './chat.js';

// Forward-import saveChatToStorage lazily to avoid circular deps with evolve-page.js
// (both session-ai and evolve-page use saveChatToStorage, which lives in evolve-page).
// NOTE: saveChatToStorage is defined in evolve-page.js; we import it dynamically.

/** Open right panel -> AI tab */
export function openSessionAiPanel() {
  if (!state.currentSessionId) return;
  // Switch to AI tab + widen panel
  document.querySelectorAll(".rp-tab").forEach(t => t.classList.toggle("active", t.dataset.panel === "ai"));
  document.querySelectorAll(".rp-content").forEach(c => c.classList.toggle("hidden", !c.id.endsWith("ai")));
  // Update header
  updateSessionAiHeader();
  // Restore session chat history
  restoreSessionAiMessages();
  // Focus input
  const input = $("#session-ai-input");
  if (input) setTimeout(() => input.focus(), 100);
}

export function updateSessionAiHeader() {}

export function restoreSessionAiMessages() {
  const container = $("#session-ai-messages");
  if (!container) return;
  container.innerHTML = "";
  const cache = state.sessionChatCache[state.currentSessionId];
  if (cache && cache.messages.length) {
    cache.messages.forEach(m => appendChatMsg(container, m.role, m.content));
    // Hide presets if there are messages
    const presets = $("#session-ai-presets");
    if (presets) presets.style.display = "none";
  } else {
    const presets = $("#session-ai-presets");
    if (presets) presets.style.display = "";
  }
}

export function submitSessionAi(prompt) {
  const input = $("#session-ai-input");
  const text = prompt || (input ? input.value.trim() : "");
  if (!text || state.sessionAiLoading || !state.currentSessionId) return;
  if (input) { input.value = ""; autoResizeTextarea(input); }

  const container = $("#session-ai-messages");
  if (!container) return;

  // Capture session ID at call time (防止 loading 期间切换 session 导致写入错误 cache)
  const targetSessionId = state.currentSessionId;

  // Init cache for this session
  if (!state.sessionChatCache[targetSessionId]) {
    state.sessionChatCache[targetSessionId] = {messages: []};
  }
  const cache = state.sessionChatCache[targetSessionId];

  // Add user message
  appendChatMsg(container, "user", text);
  cache.messages.push({role: "user", content: text});

  // Hide presets
  const presets = $("#session-ai-presets");
  if (presets) presets.style.display = "none";

  // Show streaming bubble
  state.sessionAiLoading = true;
  _setSessionAiButton(true);
  const assistantTurn = state.currentSessionId === targetSessionId
    ? createAssistantTurn(container) : null;
  const handle = sendChatStream(text, "session", targetSessionId, undefined, cache.messages.slice(0, -1));
  state.sessionAiHandle = handle;
  handle
    .onText(chunk => {
      if (assistantTurn && state.currentSessionId === targetSessionId) {
        assistantTurn.updateText(chunk);
      }
    })
    .onTool(evt => {
      if (assistantTurn && state.currentSessionId === targetSessionId) {
        assistantTurn.addTool(evt);
      }
    })
    .onDone(async (fullText, isTimeout) => {
      if (state.sessionAiHandle !== handle) return;
      state.sessionAiLoading = false;
      state.sessionAiHandle = null;
      _setSessionAiButton(false);
      const reply = fullText || "(empty response)";
      cache.messages.push({role: "assistant", content: reply});
      const { saveChatToStorage } = await import('./evolve-page.js');
      saveChatToStorage();
      if (assistantTurn && state.currentSessionId === targetSessionId) {
        assistantTurn.finalize(reply);
        if (isTimeout) _appendContinueButton(container, () => submitSessionAi("继续"));
      }
    })
    .onError(async (msg) => {
      if (state.sessionAiHandle !== handle) return;
      state.sessionAiLoading = false;
      state.sessionAiHandle = null;
      _setSessionAiButton(false);
      const reply = `**Error:** ${msg}`;
      cache.messages.push({role: "assistant", content: reply});
      const { saveChatToStorage } = await import('./evolve-page.js');
      saveChatToStorage();
      if (assistantTurn && state.currentSessionId === targetSessionId) {
        assistantTurn.finalize(reply);
      }
    })
    .onAbort(async (partialText) => {
      if (state.sessionAiHandle !== handle) return;
      state.sessionAiLoading = false;
      state.sessionAiHandle = null;
      _setSessionAiButton(false);
      const reply = (partialText || "") + "\n\n*" + t("chat.stopped") + "*";
      cache.messages.push({role: "assistant", content: reply});
      const { saveChatToStorage } = await import('./evolve-page.js');
      saveChatToStorage();
      if (assistantTurn && state.currentSessionId === targetSessionId) {
        assistantTurn.finalize(reply);
        _appendContinueButton(container, () => submitSessionAi("继续"));
      }
    });
}

export function _setSessionAiButton(loading) {
  const btn = $("#session-ai-send");
  if (!btn) return;
  if (loading) { btn.textContent = t("common.stop"); btn.classList.add("btn-stop"); }
  else { btn.textContent = t("common.send"); btn.classList.remove("btn-stop"); }
}

export function _stopSessionAi() {
  if (state.sessionAiHandle) state.sessionAiHandle.abort();
  // Don't null sessionAiHandle here — let onAbort callback do cleanup
  // (otherwise the stale-callback guard blocks finalize)
  state.sessionAiLoading = false;
  _setSessionAiButton(false);
}
