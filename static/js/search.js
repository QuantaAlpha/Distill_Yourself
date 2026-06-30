/**
 * Search functionality — doSearch, renderSearchResults, highlightQuery, jumpToMessage.
 *
 * Usage:
 *   import { doSearch, renderSearchResults, highlightQuery, jumpToMessage } from './search.js';
 */

import { state } from './state.js';
import { dom } from './dom.js';
import { esc, escRegex, formatDate } from './utils.js';
import { t } from './lang.js';

// ── Search ─────────────────────────────────────────────────────
export async function doSearch(query) {
  if (!query || query.length < 2) {
    if (!state.currentSessionId) {
      const { showView } = await import('./app.js');
      showView("sessions");
    }
    return;
  }

  // Cancel any in-flight search
  if (state._searchAbort) state._searchAbort.abort();
  state._searchAbort = new AbortController();

  const { showView } = await import('./app.js');
  showView("search");
  dom.searchResultsList.innerHTML = '<li style="padding:20px;color:var(--text-muted)">Searching…</li>';

  let results;
  try {
    const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}`, { signal: state._searchAbort.signal });
    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    results = await resp.json();
  } catch (err) {
    if (err.name === "AbortError") return; // superseded by newer search
    dom.searchResultsList.innerHTML = `<li style="padding:20px;color:#e57373">Search failed: ${esc(err.message)}</li>`;
    return;
  }

  state.lastSearchResults = results;
  state.lastSearchQuery = query;
  renderSearchResults();
}

export function renderSearchResults() {
  const results = state.lastSearchResults;
  const query = state.lastSearchQuery;
  dom.searchResultCount.textContent = t("search.count", { n: results.length });

  if (results.length === 0) {
    dom.searchResultsList.innerHTML = `<li style="padding:20px;color:var(--text-muted)">${esc(t("search.noResults"))}</li>`;
    return;
  }

  const sorted = [...results];
  const sortMode = dom.searchSortSelect.value;
  const ts = r => r.timestamp || r.date || "";
  if (sortMode === "date-desc") {
    sorted.sort((a, b) => ts(b).localeCompare(ts(a)));
  } else if (sortMode === "date-asc") {
    sorted.sort((a, b) => ts(a).localeCompare(ts(b)));
  }
  // "relevance" keeps original backend order

  dom.searchResultsList.innerHTML = "";
  sorted.forEach((r) => {
    const li = document.createElement("li");
    const dateStr = r.date ? formatDate(r.date) : "";
    const snippet = highlightQuery(r.snippet, query);
    li.innerHTML = `
      <div class="sr-title">${esc(r.title)}</div>
      <div class="sr-project">${esc(r.project)} · ${dateStr}</div>
      <div class="sr-snippet">${snippet}</div>
    `;
    li.addEventListener("click", async () => {
      dom.searchInput.value = "";
      const { loadSession } = await import('./app.js');
      loadSession(r.sessionId, r.messageIndex);
    });
    dom.searchResultsList.appendChild(li);
  });
}

export function highlightQuery(text, query) {
  if (!query) return esc(text);
  const escaped = esc(text);
  const qEsc = escRegex(query);
  return escaped.replace(new RegExp(qEsc, "gi"), (m) => `<mark>${m}</mark>`);
}

// ── Jump to message ────────────────────────────────────────────
export function jumpToMessage(idx) {
  const el = document.getElementById(`msg-${idx}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.style.outline = "2px solid var(--search-highlight)";
  el.style.outlineOffset = "2px";
  setTimeout(() => {
    el.style.outline = "";
    el.style.outlineOffset = "";
  }, 3000);
}
