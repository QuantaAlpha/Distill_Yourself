/**
 * Utility functions extracted from app.js.
 *
 * Usage:
 *   import { api, esc, renderMarkdown, ... } from './utils.js';
 */

import { $ } from './dom.js';

// ── API helper ───────────────────────────────────────────────────
export async function api(path) {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

// ── Theme toggle (tri-state: system → light → dark) ──────────
const THEME_MODE_KEY = "chatview-theme-mode";
const LEGACY_THEME_KEY = "chatview-theme";

function getStoredThemeMode() {
  const m = localStorage.getItem(THEME_MODE_KEY);
  if (m === "system" || m === "light" || m === "dark") return m;
  const legacy = localStorage.getItem(LEGACY_THEME_KEY);
  return legacy === "dark" || legacy === "light" ? legacy : "system";
}

function systemPrefersDark() {
  return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
}

function resolveTheme(mode) {
  if (mode === "system") return systemPrefersDark() ? "dark" : "light";
  return mode;
}

function themeGlyph(mode) {
  if (mode === "system") return "◐";
  return mode === "dark" ? "☀" : "☾";
}

function applyThemeMode(mode) {
  document.documentElement.dataset.theme = resolveTheme(mode);
  const btn = $("#theme-toggle");
  if (btn) {
    btn.textContent = themeGlyph(mode);
    btn.title = `Theme: ${mode}`;
  }
}

export function initThemeToggle() {
  let mode = getStoredThemeMode();
  applyThemeMode(mode);

  if (window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => { if (getStoredThemeMode() === "system") applyThemeMode("system"); };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }

  const btn = $("#theme-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const order = ["system", "light", "dark"];
    mode = order[(order.indexOf(getStoredThemeMode()) + 1) % order.length];
    localStorage.setItem(THEME_MODE_KEY, mode);
    applyThemeMode(mode);
  });
}

// ── HTML / string helpers ────────────────────────────────────────
export function esc(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export function escRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// ── Date / time / size formatters ────────────────────────────────
export function formatDate(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric", year: "numeric" });
  } catch { return isoStr; }
}

export function formatTime(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}

export function formatSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return bytes + "B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(0) + "KB";
  return (bytes / 1048576).toFixed(1) + "MB";
}

// ── SSE stream reader ────────────────────────────────────────────
export async function readSseStream(response, onEvent) {
  if (!response.ok) {
    let detail = "";
    try { detail = await response.text(); } catch { detail = ""; }
    throw new Error(detail || `HTTP ${response.status}`);
  }
  if (!response.body) {
    throw new Error("Streaming response body is missing");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function dispatchBlock(block) {
    const lines = block.split(/\r?\n/);
    for (const rawLine of lines) {
      const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
      if (!line.startsWith("data:")) continue;
      const data = line.slice(5).trimStart();
      if (!data) continue;
      try {
        onEvent(JSON.parse(data));
      } catch { /* skip malformed event */ }
    }
  }

  function flush(final) {
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() || "";
    for (const part of parts) {
      if (part.trim()) dispatchBlock(part);
    }
    if (final && buffer.trim()) {
      dispatchBlock(buffer);
      buffer = "";
    }
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      flush(true);
      return;
    }
    buffer += decoder.decode(value, {stream: true});
    flush(false);
  }
}

// ── Textarea auto-resize ─────────────────────────────────────────
export function autoResizeTextarea(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, parseInt(getComputedStyle(el).maxHeight) || 120) + "px";
}

// ── Markdown renderer ────────────────────────────────────────────
export function renderMarkdown(text, opts) {
  if (!text) return "";
  const wrapParagraphs = opts && opts.wrapParagraphs;

  function restorePlaceholders(value, blocks, inlines) {
    return value
      .replace(/\x00CB(\d+)\x00/g, (_, i) => blocks[+i])
      .replace(/\x00IC(\d+)\x00/g, (_, i) => inlines[+i]);
  }

  function renderTable(block) {
    const lines = block.trim().split(/\n/);
    if (lines.length < 2 || !/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[1])) {
      return block;
    }
    const split = (line) => line.replace(/^\s*\|?|\|?\s*$/g, "").split("|").map(c => c.trim());
    const headers = split(lines[0]);
    const rows = lines.slice(2).map(split);
    const thead = `<thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead>`;
    const tbody = `<tbody>${rows.map(r => `<tr>${headers.map((_, i) => `<td>${r[i] || ""}</td>`).join("")}</tr>`).join("")}</tbody>`;
    return `<table class="md-table">${thead}${tbody}</table>`;
  }

  function renderLists(value) {
    const lines = value.split("\n");
    const out = [];
    let listType = "";
    let listItems = [];
    const closeList = () => {
      if (!listType) return;
      out.push(`<${listType}>${listItems.join("")}</${listType}>`);
      listType = "";
      listItems = [];
    };
    const addItem = (type, html, indent, task) => {
      if (listType !== type) closeList();
      listType = type;
      const margin = indent ? ` style="margin-left:${Math.min(indent * 14, 56)}px"` : "";
      const cls = task ? ' class="task-list-item"' : "";
      listItems.push(`<li${cls}${margin}>${html}</li>`);
    };

    for (const line of lines) {
      let m = line.match(/^(\s*)[-*]\s+\[([ xX])\]\s+(.+)$/);
      if (m) {
        const checked = /x/i.test(m[2]) ? " checked" : "";
        addItem("ul", `<input type="checkbox" disabled${checked}> ${m[3]}`, Math.floor(m[1].length / 2), true);
        continue;
      }
      m = line.match(/^(\s*)[-*]\s+(.+)$/);
      if (m) {
        addItem("ul", m[2], Math.floor(m[1].length / 2), false);
        continue;
      }
      m = line.match(/^(\s*)\d+\.\s+(.+)$/);
      if (m) {
        addItem("ol", m[2], Math.floor(m[1].length / 2), false);
        continue;
      }
      closeList();
      out.push(line);
    }
    closeList();
    return out.join("\n");
  }

  // Extract code blocks BEFORE escaping to preserve raw content
  const codeBlocks = [];
  let s = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(`<pre${wrapParagraphs ? '' : ' class="md-pre"'}><code>${esc(code)}</code></pre>`);
    return `\x00CB${idx}\x00`;
  });
  // Extract inline code before escaping
  const inlineCode = [];
  s = s.replace(/`([^`]+)`/g, (_, code) => {
    const idx = inlineCode.length;
    inlineCode.push(`<code${wrapParagraphs ? '' : ' class="md-code"'}>${esc(code)}</code>`);
    return `\x00IC${idx}\x00`;
  });
  // Now escape the rest
  s = esc(s);
  // Links
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+|\/[^)\s]*)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  // Bold
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Blockquotes
  s = s.replace(/(^|\n)((?:&gt;\s?.+(?:\n|$))+)/g, (_, prefix, block) => {
    const body = block.split("\n")
      .filter(Boolean)
      .map(line => line.replace(/^&gt;\s?/, ""))
      .join("<br>");
    return `${prefix}<blockquote>${body}</blockquote>`;
  });
  // Headings
  s = s.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  s = s.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  s = s.replace(/^# (.+)$/gm, '<h2>$1</h2>');
  // Horizontal rule (always apply)
  s = s.replace(/^---$/gm, '<hr>');
  // Tables and lists
  s = s.replace(/(^|\n)((?:\s*\|.*\|\s*\n?){2,})/g, (_, prefix, block) => `${prefix}${renderTable(block)}`);
  s = renderLists(s);
  // Paragraph wrapping or simple line breaks
  if (wrapParagraphs) {
    s = s.replace(/\n{2,}/g, '</p><p>');
    s = s.replace(/\n/g, '<br>');
    s = '<p>' + s + '</p>';
    s = s.replace(/<p>\s*<(h[234]|pre|ul|ol|hr|blockquote|table)/g, '<$1');
    s = s.replace(/<\/(h[234]|pre|ul|ol|hr|blockquote|table)>\s*<\/p>/g, '</$1>');
    s = s.replace(/<p>\s*<\/p>/g, '');
  } else {
    s = s.replace(/\n/g, '<br>');
  }
  // Restore code blocks and inline code
  return restorePlaceholders(s, codeBlocks, inlineCode);
}

// ── Markdown simple wrapper ──────────────────────────────────────
export function renderMarkdownSimple(text) {
  return renderMarkdown(text, { wrapParagraphs: true });
}
