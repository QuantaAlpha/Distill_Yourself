/**
 * AI Chat infrastructure — shared primitives for both session AI and global AI.
 *
 * Usage:
 *   import { appendChatMsg, openMsgModal, showChatLoading, createAssistantTurn,
 *            sendChatRequest, sendChatStream, _appendContinueButton } from './chat.js';
 */

import { state } from './state.js';
import { $ } from './dom.js';
import { esc, readSseStream, renderMarkdownSimple } from './utils.js';
import { t } from './i18n.js';

// ── Smart auto-scroll ──────────────────────────────────────
export function _shouldAutoScroll(container) {
  return container.scrollHeight - container.scrollTop - container.clientHeight < 80;
}
export function _autoScroll(container) {
  if (_shouldAutoScroll(container)) {
    container.scrollTop = container.scrollHeight;
  }
}

/** Append a chat message bubble to a container */
export function appendChatMsg(container, role, content) {
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.style.position = "relative";
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.innerHTML = role === "assistant" ? renderMarkdownSimple(content) : esc(content).replace(/\n/g, "<br>");
  div.appendChild(bubble);

  if (role === "assistant") {
    // Actions bar (expand button)
    const actions = document.createElement("div");
    actions.className = "chat-msg-actions";
    const expandBtn = document.createElement("button");
    expandBtn.className = "chat-msg-expand";
    expandBtn.textContent = "⤢";
    expandBtn.title = "Full screen";
    expandBtn.onclick = (e) => {
      e.stopPropagation();
      openMsgModal(content);
    };
    actions.appendChild(expandBtn);
    div.appendChild(actions);

    // Check after render if content is long enough to fold
    requestAnimationFrame(() => {
      if (bubble.scrollHeight > 300) {
        bubble.classList.add("foldable", "folded");
        bubble.style.maxHeight = "300px";
        const toggle = document.createElement("button");
        toggle.className = "chat-fold-toggle";
        toggle.textContent = t("chat.fold.expand");
        toggle.onclick = () => {
          const isFolded = bubble.classList.contains("folded");
          bubble.classList.toggle("folded", !isFolded);
          bubble.style.maxHeight = isFolded ? "none" : "300px";
          toggle.textContent = isFolded ? t("chat.fold.collapse") : t("chat.fold.expand");
        };
        div.appendChild(toggle);
      }
    });
  }

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

export function openMsgModal(content) {
  const modal = document.getElementById("msg-modal");
  if (!modal) return;
  const body = modal.querySelector(".msg-modal-body");
  if (body) body.innerHTML = renderMarkdownSimple(content);
  modal.classList.remove("hidden");
  const close = modal.querySelector(".msg-modal-close");
  const backdrop = modal.querySelector(".msg-modal-backdrop");
  const controller = new AbortController();
  function closeModal() {
    modal.classList.add("hidden");
    controller.abort();
  }
  if (close) close.addEventListener("click", closeModal, { signal: controller.signal });
  if (backdrop) backdrop.addEventListener("click", closeModal, { signal: controller.signal });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeModal();
  }, { signal: controller.signal });
}

/** Show loading indicator in a container, return the element for later removal */
export function showChatLoading(container, description) {
  const el = document.createElement("div");
  el.className = "chat-msg assistant";
  el.innerHTML = `<div class="chat-bubble"><div class="chat-loading"><span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="chat-loading-text">${esc(description)}</span></div></div>`;
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
  return el;
}

/**
 * Create a ChatGPT-style assistant turn: a vertical stream of
 * tool-cards and text-blocks, appended as SSE events arrive.
 * Returns {addTool(evt), updateText(accumulated), finalize(fullText)}
 */
export function createAssistantTurn(container) {
  const turn = document.createElement("div");
  turn.className = "assistant-turn";

  // Init indicator
  const initEl = document.createElement("div");
  initEl.className = "turn-init";
  initEl.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="turn-init-text">Thinking…</span>';
  turn.appendChild(initEl);

  container.appendChild(turn);
  _autoScroll(container);

  let _currentTextBlock = null; // the active .text-block element
  let _blockText = ""; // text accumulated for the CURRENT block only
  let _renderTimer = null;
  let _started = false;
  let _runningCards = []; // queue of running tool cards (FIFO for done matching)

  function _ensureStarted() {
    if (!_started) {
      _started = true;
      if (initEl.parentNode) initEl.remove();
    }
  }

  function _ensureTextBlock() {
    if (!_currentTextBlock) {
      _currentTextBlock = document.createElement("div");
      _currentTextBlock.className = "text-block";
      _currentTextBlock.innerHTML = '<span class="stream-cursor">▍</span>';
      turn.appendChild(_currentTextBlock);
    }
    return _currentTextBlock;
  }

  return {
    el: turn,

    addTool(evt) {
      _ensureStarted();

      if (evt.status === "running") {
        // Remove cursor from the previous text block
        if (_currentTextBlock) {
          const cursor = _currentTextBlock.querySelector(".stream-cursor");
          if (cursor) cursor.remove();
        }
        // Reset per-block accumulator; close current text block
        _blockText = "";
        _currentTextBlock = null;
        // Create a new tool card
        const card = document.createElement("div");
        card.className = "tool-card running";
        const detail = evt.detail ? esc(evt.detail) : "";
        card.innerHTML = `<div class="tool-card-header"><span class="tool-status-dot"></span><span class="tool-card-name">${esc(evt.name)}</span><span class="tool-card-detail">${detail}</span><span class="tool-card-chevron">›</span></div><div class="tool-card-body"><pre class="tool-card-output"></pre></div>`;
        turn.appendChild(card);
        _runningCards.push(card);
      } else if (evt.status === "done" && _runningCards.length) {
        // Complete the oldest running card (FIFO)
        const card = _runningCards.shift();
        card.classList.remove("running");
        card.classList.add("done");
        // Update output if provided
        if (evt.detail) {
          const outputEl = card.querySelector(".tool-card-output");
          if (outputEl) outputEl.textContent = evt.detail;
        }
        // Make it collapsible
        const header = card.querySelector(".tool-card-header");
        if (header) {
          header.onclick = () => card.classList.toggle("expanded");
        }
      }
      _autoScroll(container);
    },

    updateText(chunk) {
      _ensureStarted();
      _blockText += chunk;
      const block = _ensureTextBlock();
      if (!_renderTimer) {
        _renderTimer = requestAnimationFrame(() => {
          _renderTimer = null;
          block.innerHTML = renderMarkdownSimple(_blockText) + '<span class="stream-cursor">▍</span>';
          _autoScroll(container);
        });
      }
    },

    finalize(fullText) {
      _ensureStarted();
      turn.classList.add("done");
      // Remove all streaming cursors from earlier blocks
      turn.querySelectorAll(".stream-cursor").forEach(c => c.remove());
      // Render final block text (without cursor)
      if (_blockText || fullText) {
        const block = _ensureTextBlock();
        block.innerHTML = renderMarkdownSimple(_blockText || fullText);
        // Add action buttons
        const actions = document.createElement("div");
        actions.className = "text-block-actions";
        const expandBtn = document.createElement("button");
        expandBtn.className = "text-action-btn";
        expandBtn.textContent = "⤢";
        expandBtn.title = "Full screen";
        expandBtn.onclick = (e) => { e.stopPropagation(); openMsgModal(fullText); };
        actions.appendChild(expandBtn);
        const copyBtn = document.createElement("button");
        copyBtn.className = "text-action-btn";
        copyBtn.textContent = "📋";
        copyBtn.title = "Copy";
        copyBtn.onclick = () => {
          navigator.clipboard.writeText(fullText).then(() => {
            copyBtn.textContent = "✓";
            setTimeout(() => { copyBtn.textContent = "📋"; }, 1500);
          });
        };
        actions.appendChild(copyBtn);
        block.appendChild(actions);
      } else if (initEl.parentNode) {
        initEl.remove(); // clean up if no content at all
      }
      _autoScroll(container);
    },
  };
}

/** Send chat request to backend (legacy non-streaming) */
export function sendChatRequest(prompt, contextType, sessionId, scope) {
  const body = {prompt, contextType, sessionId: sessionId || null};
  if (scope) body.scope = scope;
  return fetch("/api/chat", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  }).then(r => r.json());
}

/**
 * Stream a chat request via SSE. Returns an object with:
 *   .onText(fn)  — called with accumulated text on each text chunk
 *   .onTool(fn)  — called with {name, status, detail} for tool events
 *   .onDone(fn)  — called with final full text
 *   .onError(fn) — called with error message
 *   .abort()     — cancel the stream
 */
export function sendChatStream(prompt, contextType, sessionId, scope, messages) {
  const body = {prompt, contextType, sessionId: sessionId || null, timeout: state.chatTimeout};
  if (scope) body.scope = scope;
  if (messages && messages.length) body.messages = messages;
  const callbacks = { text: null, tool: null, done: null, error: null, abort: null };
  const controller = new AbortController();

  const handle = {
    onText(fn) { callbacks.text = fn; return handle; },
    onTool(fn) { callbacks.tool = fn; return handle; },
    onDone(fn) { callbacks.done = fn; return handle; },
    onError(fn) { callbacks.error = fn; return handle; },
    onAbort(fn) { callbacks.abort = fn; return handle; },
    abort() { controller.abort(); },
  };

  const streamState = { text: "" }; // accumulator shared across events

  fetch("/api/chat/stream", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
    signal: controller.signal,
  }).then(response => readSseStream(response, evt => _handleStreamEvent(evt, callbacks, streamState)))
    .catch(err => {
    if (err.name === "AbortError") {
      if (callbacks.abort) callbacks.abort(streamState.text);
    } else if (callbacks.error) {
      callbacks.error(err.message);
    }
  });

  return handle;
}

export function _appendContinueButton(container, onClick) {
  const wrap = document.createElement("div");
  wrap.className = "chat-continue-wrap";
  const btn = document.createElement("button");
  btn.className = "btn-continue";
  btn.textContent = t("chat.continue.btn");
  btn.addEventListener("click", () => {
    wrap.remove();
    onClick();
  });
  wrap.appendChild(btn);
  container.appendChild(wrap);
  _autoScroll(container);
}

export function _handleStreamEvent(evt, callbacks, streamState) {
  switch (evt.type) {
    case "text":
      streamState.text += evt.content;
      if (callbacks.text) callbacks.text(evt.content);
      break;
    case "tool":
      if (callbacks.tool) callbacks.tool(evt);
      break;
    case "result":
      streamState.text = evt.content;
      break;
    case "done":
      if (callbacks.done) callbacks.done(evt.content || streamState.text);
      break;
    case "timeout":
      // Timeout with partial text — treat as done-with-partial so history is preserved
      streamState.text = evt.content || streamState.text;
      if (callbacks.done) callbacks.done(streamState.text, true); // second arg = isTimeout
      break;
    case "error":
      if (callbacks.error) callbacks.error(evt.message);
      break;
  }
}
