import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_app_js():
    with open(os.path.join(ROOT, "static", "app.js"), encoding="utf-8") as f:
        return f.read()


def read_index_html():
    with open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8") as f:
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
        self.assertNotIn('<script defer src="https://d3js.org/d3.v7.min.js"></script>', html)

    def test_keyboard_help_matches_actual_main_view_shortcuts(self):
        html = read_index_html()

        self.assertIn("<tr><td><kbd>2</kbd></td><td>AI Evolve</td></tr>", html)
        self.assertIn("<tr><td><kbd>4</kbd></td><td>Distill Yourself</td></tr>", html)
        self.assertNotIn("<tr><td><kbd>2</kbd></td><td>Sessions</td></tr>", html)
        self.assertNotIn("<tr><td><kbd>4</kbd></td><td>AI page</td></tr>", html)

    def test_poll_reruns_active_search_after_index_generation_changes(self):
        script = read_app_js()

        self.assertIn('currentView === "search"', script)
        self.assertIn("doSearch(searchInput.value.trim())", script)


if __name__ == "__main__":
    unittest.main()
