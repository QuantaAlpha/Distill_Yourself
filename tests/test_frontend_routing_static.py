import os
import re
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_app_js():
    # The live frontend is modular (static/js/*.js). Concatenate the routing-
    # relevant modules so assertions cover the code actually served.
    parts = []
    for rel in ("js/app.js", "js/state.js"):
        with open(os.path.join(ROOT, "static", rel), encoding="utf-8") as f:
            parts.append(f.read())
    return "\n".join(parts)


def read_index_html():
    with open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8") as f:
        return f.read()


def read_static(relpath):
    with open(os.path.join(ROOT, "static", relpath), encoding="utf-8") as f:
        return f.read()


class TestFrontendRoutingStatic(unittest.TestCase):
    def test_main_views_are_restored_from_hash(self):
        script = read_app_js()

        self.assertIn("MAIN_VIEW_HASHES", script)
        for view in ("sessions", "insights", "ai", "twin"):
            self.assertIn(f'"{view}"', script)
        self.assertIn("restoreViewFromHash", script)

    def test_session_hash_restore_is_separate_from_main_view_hashes(self):
        script = read_app_js()

        self.assertIn("restoreSessionFromHash", script)
        self.assertIn("MAIN_VIEW_HASHES.has(hash)", script)
        self.assertIn("loadSession(hash, undefined, false)", script)

    def test_d3_loads_before_app_can_restore_ai_view(self):
        html = read_index_html()

        self.assertIn("https://d3js.org/d3.v7.min.js", html)
        self.assertNotIn(
            '<script defer src="https://d3js.org/d3.v7.min.js"></script>', html
        )

    def test_keyboard_help_matches_actual_main_view_shortcuts(self):
        html = read_index_html()
        self.assertRegex(
            html,
            re.compile(r"<td><kbd>2</kbd></td>\s*<td>AI Evolve</td>"),
        )
        self.assertRegex(
            html,
            re.compile(r"<td><kbd>4</kbd></td>\s*<td>Distill Yourself</td>"),
        )
        self.assertNotRegex(
            html, re.compile(r"<td><kbd>2</kbd></td>\s*<td>Sessions</td>")
        )
        self.assertNotRegex(
            html, re.compile(r"<td><kbd>4</kbd></td>\s*<td>AI page</td>")
        )

    def test_poll_reruns_active_search_after_index_generation_changes(self):
        script = read_app_js()

        self.assertIn('currentView === "search"', script)
        self.assertIn("doSearch(dom.searchInput.value.trim())", script)

    def test_welcome_cards_include_three_primary_entrypoints_and_six_insights(self):
        html = read_index_html()
        script = read_app_js()

        self.assertEqual(
            len(re.findall(r'<button\b[^>]*class="welcome-card\b', html)), 9
        )
        for action in (
            "sessions",
            "ai",
            "twin",
            "heatmap",
            "hotspots",
            "errors",
            "profile",
            "health",
            "snippets",
        ):
            self.assertIn(f'data-action="{action}"', html)

        self.assertIn('<span class="welcome-card-title">Sessions</span>', html)
        self.assertIn('<span class="welcome-card-title">AI Evolve</span>', html)
        self.assertIn('<span class="welcome-card-title">Distill Yourself</span>', html)
        self.assertIn('action === "sessions"', script)
        self.assertIn('action === "twin"', script)

    def test_welcome_cards_use_premium_primary_and_tool_groups(self):
        html = read_index_html()

        self.assertIn('class="welcome-primary-grid"', html)
        self.assertIn('class="welcome-tools-head"', html)
        self.assertIn('class="welcome-tool-grid"', html)
        self.assertEqual(html.count("welcome-primary-card"), 3)
        self.assertEqual(html.count("welcome-tool-card"), 6)

    def test_mobile_topbar_can_shrink_without_horizontal_overflow(self):
        css_path = os.path.join(ROOT, "static", "css", "layout.css")
        with open(css_path, encoding="utf-8") as f:
            css = f.read()

        self.assertIn("@media (max-width: 768px)", css)
        self.assertIn(".topbar-right { display: flex; }", css)
        self.assertIn(".search-wrapper { min-width: 0;", css)

    def test_engine_scope_uses_shared_getter_and_preserves_saved_engine_before_detection(
        self,
    ):
        app = read_static("js/app.js")
        evolve_page = read_static("js/evolve-page.js")

        self.assertIn('new Set(["auto", ...state.availableEngines])', app)
        self.assertIn("new Set([", evolve_page)
        self.assertIn('state.globalScopeEngine || "auto"', evolve_page)
        self.assertIn('"auto"', evolve_page)
        self.assertIn("...state.availableEngines", evolve_page)
        self.assertIn("state.availableEngines.length &&", evolve_page)
        self.assertIn("window.getEvolveScope = getSharedEvolveScope", evolve_page)
        self.assertIn("engineSelect.disabled = engineOptions.length <= 1", evolve_page)
        self.assertIn("renderAiScopeBar();", app)

    def test_ai_scope_and_chat_restore_state_from_local_storage(self):
        app = read_static("js/app.js")
        evolve_page = read_static("js/evolve-page.js")
        state_js = read_static("js/state.js")

        self.assertIn('localStorage.getItem("chatview-ai-scope-source")', state_js)
        self.assertIn('localStorage.getItem("chatview-ai-scope-date")', state_js)
        self.assertIn('localStorage.getItem("chatview-ai-scope-project")', state_js)
        self.assertIn('localStorage.getItem("chatview-ai-active-chat-id")', evolve_page)
        self.assertIn("localStorage.setItem(", evolve_page)
        self.assertIn('"chatview-ai-active-chat-id"', evolve_page)
        self.assertIn('localStorage.getItem("chatview-evolve-active-tab")', evolve_page)
        self.assertIn('"chatview-evolve-active-tab"', evolve_page)
        self.assertIn("loadChatFromStorage()", app)

    def test_ai_page_reinit_detaches_old_evolve_streams_before_rehydrate(self):
        evolve_page = read_static("js/evolve-page.js")
        init_body = evolve_page[
            evolve_page.index("export function initAiPage()") : evolve_page.index(
                "export function notifyEvolveScopeChanged()",
                evolve_page.index("export function initAiPage()"),
            )
        ]

        self.assertIn("window.abortEvolveStreams(true, true)", init_body)
        self.assertIn("window.initEvolveView", init_body)

    def test_new_global_chat_persists_immediately(self):
        evolve_page = read_static("js/evolve-page.js")
        init_new_body = evolve_page[
            evolve_page.index(
                "export function initNewGlobalChat()"
            ) : evolve_page.index(
                "export function newGlobalChat()",
                evolve_page.index("export function initNewGlobalChat()"),
            )
        ]

        self.assertIn("saveChatToStorage();", init_new_body)

    def test_analysis_history_has_rename_delete_and_smart_default_titles(self):
        evolve_page = read_static("js/evolve-page.js")
        chat_css = read_static("css/chat.css")

        self.assertIn("function _deriveGlobalChatTitle(chat)", evolve_page)
        self.assertIn("function _extractMeaningfulTitle(text)", evolve_page)
        self.assertIn("function _formatGlobalChatMeta(chat)", evolve_page)
        self.assertIn("chat.updatedAt = new Date().toISOString();", evolve_page)
        self.assertIn("export function renameGlobalChat(chatId)", evolve_page)
        self.assertIn("export function deleteGlobalChat(chatId)", evolve_page)
        self.assertIn("export function resetGlobalChatTitle(chatId)", evolve_page)
        self.assertIn('li.addEventListener("contextmenu"', evolve_page)
        self.assertIn('data-action="rename"', evolve_page)
        self.assertIn('data-action="delete"', evolve_page)
        self.assertIn("chat-meta", evolve_page)
        self.assertIn(".chat-history-menu", chat_css)
        self.assertIn(".chat-meta", chat_css)
        self.assertIn(".session-item.active .chat-history-more", chat_css)

    def test_evolve_updated_header_is_js_owned_not_static_i18n_default(self):
        html = read_index_html()

        self.assertIn('id="evolve-tab-updated"', html)
        self.assertNotIn('id="evolve-tab-updated" data-i18n="evolve.notAnalyzed"', html)


if __name__ == "__main__":
    unittest.main()
