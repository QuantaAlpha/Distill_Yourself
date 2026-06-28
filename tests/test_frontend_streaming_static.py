import os
import re
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_static(path):
    with open(os.path.join(ROOT, "static", path), encoding="utf-8") as f:
        return f.read()


class TestFrontendStreamingStatic(unittest.TestCase):
    def test_shared_sse_reader_flushes_tail_buffer(self):
        script = read_static("app.js")

        self.assertIn("async function readSseStream", script)
        self.assertIn("flush(true)", script)
        self.assertIn("buffer += decoder.decode()", script)
        self.assertIn("window.readSseStream = readSseStream", script)
        reader_body = script[
            script.index("async function readSseStream"):
            script.index("// ── View Switching", script.index("async function readSseStream"))
        ]
        self.assertNotRegex(reader_body, re.compile(r"if\s*\(\s*done\s*\)\s*return\s*;"))

    def test_evolve_stream_uses_request_scope_for_cache_writes(self):
        script = read_static("evolve.js")

        self.assertIn("function getScopeCacheKey(tab, scope", script)
        self.assertIn("function getCachedTab(tab, scope", script)
        self.assertIn("function setCachedTab(tab, data, scope", script)
        self.assertIn("requestScope", script)
        self.assertIn("requestCacheKey", script)
        self.assertIn("isCurrentScopeKey", script)
        self.assertIn("setCachedTab(tab, normalized, streamState.requestScope)", script)

    def test_evolve_and_twin_use_shared_sse_reader(self):
        evolve = read_static("evolve.js")
        twin = read_static("twin.js")

        self.assertIn("window.readSseStream", evolve)
        self.assertIn("window.readSseStream", twin)
        self.assertNotIn("const reader = response.body.getReader()", evolve)
        self.assertNotIn("const reader = response.body.getReader()", twin)

    def test_evolve_stop_restores_cached_panel_and_keeps_abort_state_scoped(self):
        script = read_static("evolve.js")
        stop_body = script[
            script.index("function _stopEvolveTab(tab)"):
            script.index("/** Show a \"thinking\" indicator", script.index("function _stopEvolveTab(tab)"))
        ]
        stream_body = script[
            script.index("function _fetchEvolveTabStream"):
            script.index("function _setEvolveRefreshButton", script.index("function _fetchEvolveTabStream"))
        ]

        self.assertIn("_renderTabPanel(tab, panel)", stop_body)
        self.assertIn("updateEvolveOverviewBar()", stop_body)
        self.assertIn("if (evolveStreamAborts[tab] === abortCtrl)", stream_body)

    def test_twin_stop_restores_overview_and_clears_analysis_progress(self):
        script = read_static("twin.js")
        stop_body = script[
            script.index("function _stopAnalysis()"):
            script.index("// ── Overview", script.index("function _stopAnalysis()"))
        ]

        self.assertIn("_restoreOverviewAfterStoppedAnalysis()", stop_body)
        self.assertIn('progress.innerHTML = ""', script)
        self.assertIn("renderOverview(overviewData)", script)
        self.assertIn("loadOverview()", script)


if __name__ == "__main__":
    unittest.main()
