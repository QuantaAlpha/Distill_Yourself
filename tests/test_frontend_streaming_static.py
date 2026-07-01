import os
import re
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_static(path):
    with open(os.path.join(ROOT, "static", path), encoding="utf-8") as f:
        return f.read()


class TestFrontendStreamingStatic(unittest.TestCase):
    def test_shared_sse_reader_flushes_tail_buffer(self):
        # The shared SSE reader lives in static/js/utils.js; app.js exposes it
        # on window for the non-module root scripts (evolve.js / twin.js).
        reader = read_static("js/utils.js")
        app = read_static("js/app.js")

        self.assertIn("async function readSseStream", reader)
        self.assertIn("flush(true)", reader)
        self.assertIn("buffer += decoder.decode()", reader)
        self.assertIn("window.readSseStream = readSseStream", app)
        reader_body = reader[
            reader.index("async function readSseStream") : reader.index(
                "// ── Textarea auto-resize",
                reader.index("async function readSseStream"),
            )
        ]
        self.assertNotRegex(
            reader_body, re.compile(r"if\s*\(\s*done\s*\)\s*return\s*;")
        )

    def test_evolve_stream_uses_request_scope_for_cache_writes(self):
        script = read_static("evolve.js")

        self.assertIn("function getScopeCacheKey(tab, scope", script)
        self.assertIn("function getCachedTab(tab, scope", script)
        self.assertIn("function setCachedTab(tab, data, scope", script)
        self.assertIn("requestScope", script)
        self.assertIn("requestCacheKey", script)
        self.assertIn("isCurrentScopeKey", script)
        self.assertIn("setCachedTab(tab, normalized, streamState.requestScope)", script)

    def test_evolve_cache_reads_exact_engine_first_then_shared_scope_fallback(self):
        script = read_static("evolve.js")

        self.assertIn("const exactKey = getScopeCacheKey(tab, targetScope)", script)
        self.assertIn(
            "if (evolveCache[exactKey]) return evolveCache[exactKey];", script
        )
        self.assertIn('key.startsWith(prefix + "::")', script)

    def test_evolve_cache_migrates_legacy_lang_scoped_keys(self):
        script = read_static("evolve.js")

        self.assertIn("function _migrateLegacyLangScopedCache()", script)
        self.assertIn('key.split("::").length < 6', script)
        self.assertIn(
            "const legacyKey = getLegacyScopeCacheKey(tab, targetScope);", script
        )
        self.assertIn("_migrateLegacyLangScopedCache();", script)

    def test_evolve_preloaded_inactive_panels_stay_hidden(self):
        script = read_static("evolve.js")
        ensure_body = script[
            script.index("function _ensureTabPanel") : script.index(
                "/** Render tab content",
                script.index("function _ensureTabPanel"),
            )
        ]

        self.assertIn(
            'panel.style.display = tab === evolveActiveTab ? "" : "none";',
            ensure_body,
        )

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
            script.index("function _stopEvolveTab(tab)") : script.index(
                '/** Show a "thinking" indicator',
                script.index("function _stopEvolveTab(tab)"),
            )
        ]
        stream_body = script[
            script.index("function _fetchEvolveTabStream") : script.index(
                "function _setEvolveRefreshButton",
                script.index("function _fetchEvolveTabStream"),
            )
        ]

        self.assertIn("_renderTabPanel(tab, panel)", stop_body)
        self.assertIn("_syncEvolveChrome(tab, scope)", stop_body)
        self.assertIn("if (evolveStreamAborts[tab] === abortCtrl)", stream_body)

    def test_twin_stop_preserves_progress_snapshot_and_does_not_clear_details(self):
        script = read_static("twin.js")
        stop_body = script[
            script.index("async function _stopAnalysis()") : script.index(
                "// ── Overview", script.index("async function _stopAnalysis()")
            )
        ]

        self.assertIn("_refreshAuthoritativeProgressSnapshot", stop_body)
        self.assertIn("_renderRunProgress(run, false)", stop_body)
        self.assertNotIn("_restoreOverviewAfterStoppedAnalysis()", stop_body)
        self.assertNotIn('progress.innerHTML = ""', stop_body)

    def test_evolve_stream_handles_timeout_usage_and_persists_errors(self):
        script = read_static("evolve.js")
        handler_body = script[
            script.index("function _handleEvolveStreamEvent") : script.index(
                "function refreshEvolveTab",
                script.index("function _handleEvolveStreamEvent"),
            )
        ]
        # Stream switch must handle timeout and usage events explicitly
        self.assertIn('case "timeout":', handler_body)
        self.assertIn('case "usage":', handler_body)
        # error/timeout must persist to cache so the failure survives re-render
        # (otherwise the panel silently resets to "Not analyzed yet")
        self.assertIn("setCachedTab(tab, { _error:", handler_body)

    def test_twin_history_click_views_run_and_resume_is_explicit(self):
        script = read_static("twin.js")
        history_body = script[
            script.index("function _renderRunHistory()") : script.index(
                "/** Show a resume prompt",
                script.index("function _renderRunHistory()"),
            )
        ]

        self.assertIn("_selectTwinRunForViewing(rid)", history_body)
        self.assertIn("twin-run-resume", history_body)
        self.assertIn("_startAnalysisWithResume(rid)", history_body)
        self.assertNotIn(
            "const go = () => { if (!analysisRunning) _startAnalysisWithResume(rid); };",
            history_body,
        )

    def test_twin_history_fetches_ten_runs_and_label_matches(self):
        script = read_static("twin.js")

        self.assertIn('fetch("/api/twin/runs?limit=10")', script)
        self.assertIn('"twin.progress.history.title": "历史记录（最近 10 次）"', script)
        self.assertIn('"twin.progress.history.title": "Recent runs (last 10)"', script)

    def test_twin_separates_viewed_run_from_running_run_and_default_overview(self):
        script = read_static("twin.js")

        self.assertIn("let _viewRunId", script)
        self.assertIn("TWIN_VIEW_RUN_KEY", script)
        self.assertIn("function _runScopedUrl(url, runId)", script)
        self.assertIn("_withRunId(url, { includeViewRun: false })", script)
        self.assertIn("function _loadDefaultOverview()", script)
        self.assertIn("function _selectTwinRunForViewing(runId)", script)

    def test_twin_overview_has_run_switcher(self):
        script = read_static("twin.js")

        self.assertIn(
            "function _renderOverviewRunSwitcher(container, currentRunId)", script
        )
        self.assertIn("loadOverview(rid)", script)
        self.assertIn("twin-overview-run-switcher", script)

    def test_twin_progress_css_uses_theme_tokens_and_dark_overrides(self):
        css = read_static("css/twin.css")

        self.assertIn("--twin-progress-success", css)
        self.assertIn("--twin-progress-running", css)
        self.assertIn("--twin-progress-surface", css)
        self.assertIn('html[data-theme="dark"]', css)

    def test_evolve_no_cache_is_not_rendered_as_failure(self):
        script = read_static("evolve.js")
        # no_cache means "never analyzed", not an analysis failure — it must
        # not be cached/rendered as an _error state.
        self.assertIn('data._error && data._error !== "no_cache"', script)
        self.assertIn("cached && cached.data && !cached.data._error", script)

    def test_evolve_stream_passes_timeout_param(self):
        script = read_static("evolve.js")
        fetch_body = script[
            script.index("function _fetchEvolveTab(tab)") : script.index(
                "function _fetchEvolveTabStream",
                script.index("function _fetchEvolveTab(tab)"),
            )
        ]
        self.assertIn("timeout", fetch_body)

    def test_evolve_reattaches_via_backend_progress_and_true_cancel(self):
        script = read_static("evolve.js")

        self.assertIn("/api/evolve/progress", script)
        self.assertIn("/api/evolve/cancel", script)
        self.assertIn("active-run-id", script)
        self.assertIn("window.abortEvolveStreams = function", script)
        self.assertIn("detachOnly", script)

    def test_evolve_recovered_runs_continue_polling_until_terminal_state(self):
        script = read_static("evolve.js")

        self.assertIn("function _scheduleRecoveredRunPoll(tab, requestScope)", script)
        self.assertIn("_scheduleRecoveredRunPoll(tab, requestScope);", script)
        self.assertIn("setTimeout(poll, 2000)", script)

    def test_evolve_recovered_pollers_keep_chrome_in_running_state(self):
        script = read_static("evolve.js")

        self.assertIn("function _isTabBusy(", script)
        self.assertIn("!!evolveRecoveredRunPollers[tab]", script)

        for marker in (
            "function _updateEvolveHeader",
            "function _updateTabStatusIndicators",
            "function _setEvolveRefreshButton",
        ):
            body = script[
                script.index(marker) : script.index(
                    "function ", script.index(marker) + len(marker)
                )
            ]
            self.assertIn("_isTabBusy(", body, marker)

    def test_evolve_init_checks_backend_progress_before_rendering_empty_state(self):
        script = read_static("evolve.js")
        init_body = script[
            script.index("window.initEvolveView = function") : script.index(
                "/** Clear cached entries",
                script.index("window.initEvolveView = function"),
            )
        ]

        self.assertIn("_showProgressCheckState()", init_body)
        self.assertIn("_restoreEvolveRunState().finally", init_body)
        self.assertLess(
            init_body.index("_restoreEvolveRunState().finally"),
            init_body.index("switchEvolveTab(evolveActiveTab)"),
        )
        self.assertIn("return fetch(`/api/evolve/progress?${params}`)", script)
        self.assertNotIn("evolveLoadingTabs = {};", init_body)

    def test_evolve_header_state_uses_shared_renderer_across_restore_paths(self):
        script = read_static("evolve.js")

        self.assertIn("function _updateEvolveHeader(", script)
        self.assertIn("function _syncEvolveChrome(", script)

        for marker in (
            "function switchEvolveTab",
            "function _applyRecoveredRun",
            "function refreshEvolveTab",
            'window.addEventListener("localechange"',
        ):
            body = script[
                script.index(marker) : script.index(
                    "function ", script.index(marker) + len(marker)
                )
                if marker.startswith("function ")
                else script.index(
                    "// app.js runs its first applyI18nDom",
                    script.index(marker),
                )
            ]
            self.assertTrue(
                "_syncEvolveChrome(" in body or "_updateEvolveHeader(" in body,
                marker,
            )

    def test_evolve_sync_chrome_keeps_header_scoped_to_active_tab(self):
        script = read_static("evolve.js")
        chrome_body = script[
            script.index("function _syncEvolveChrome(") : script.index(
                "function _updateEvolveHeader(",
                script.index("function _syncEvolveChrome("),
            )
        ]

        self.assertIn("_updateEvolveHeader(evolveActiveTab", chrome_body)

    def test_evolve_progress_summary_block_matches_twin_style(self):
        script = read_static("evolve.js")

        self.assertIn("function _progressSummaryHtml(", script)
        self.assertIn("function _updateProgressSummary(", script)
        self.assertIn("evolve-progress-summary", script)
        self.assertIn("_updateProgressSummary(tab, progressState, true)", script)

    def test_evolve_progress_summary_styles_exist(self):
        css = read_static("css/evolve.css")

        self.assertIn(".evolve-progress-summary", css)
        self.assertIn(".evolve-progress-head", css)
        self.assertIn(".evolve-progress-runid", css)
        self.assertIn(".evolve-progress-live", css)
        self.assertIn("@keyframes evolve-progress-glow", css)

    def test_evolve_restore_does_not_persist_inactive_running_as_error(self):
        script = read_static("evolve.js")
        restore_body = script[
            script.index("function _applyRecoveredRun") : script.index(
                "function _renderRecoveredProgress",
                script.index("function _applyRecoveredRun"),
            )
        ]

        self.assertIn('run.status === "running"', restore_body)
        self.assertNotIn(
            "Analysis interrupted: no active backend process", restore_body
        )
        self.assertNotRegex(
            restore_body,
            re.compile(r'run\.status\s*===\s*"running"[\s\S]{0,240}setCachedTab\('),
        )

    def test_evolve_progress_restore_consumes_server_cache_payload(self):
        script = read_static("evolve.js")
        restore_body = script[
            script.index("function _applyRecoveredRun") : script.index(
                "function _renderRecoveredProgress",
                script.index("function _applyRecoveredRun"),
            )
        ]

        self.assertIn("cache", restore_body)
        self.assertIn("normalizeEvolveData(tab, cache.data)", restore_body)

    def test_evolve_server_loaded_cache_resyncs_active_header(self):
        script = read_static("evolve.js")

        interrupted_body = script[
            script.index("function _showInterruptedBanner") : script.index(
                "function bindEvolveEvents",
                script.index("function _showInterruptedBanner"),
            )
        ]
        preload_body = script[
            script.index("function _loadServerCacheForMissingTabs") : script.index(
                "function _progressParams",
                script.index("function _loadServerCacheForMissingTabs"),
            )
        ]

        self.assertIn("_syncEvolveChrome(tab, scope)", interrupted_body)
        self.assertIn("_syncEvolveChrome(tab, scope)", preload_body)

    def test_evolve_restore_running_clears_transient_timeout_cache(self):
        script = read_static("evolve.js")
        clear_body = script[
            script.index("function _isTransientEvolveError") : script.index(
                "/** Clear cached entries",
                script.index("function _isTransientEvolveError"),
            )
        ]
        restore_body = script[
            script.index("function _applyRecoveredRun") : script.index(
                "function _renderRecoveredProgress",
                script.index("function _applyRecoveredRun"),
            )
        ]
        refresh_body = script[
            script.index("function refreshEvolveTab") : script.index(
                "function refreshAllEvolveTabs",
                script.index("function refreshEvolveTab"),
            )
        ]

        self.assertIn('text.startsWith("Timeout")', clear_body)
        self.assertIn('"AI analysis timed out"', clear_body)
        self.assertIn("_clearCachedTabTransientError(tab, requestScope)", restore_body)
        self.assertIn("_clearCachedTabTransientError(tab, requestScope)", refresh_body)
        self.assertLess(
            restore_body.index("_clearCachedTabTransientError(tab, requestScope)"),
            restore_body.index("_markTabLoading(tab, requestScope)"),
        )

    def test_evolve_server_cache_loaders_do_not_overwrite_running_tabs(self):
        script = read_static("evolve.js")
        interrupted_body = script[
            script.index("function _showInterruptedBanner") : script.index(
                "function bindEvolveEvents",
                script.index("function _showInterruptedBanner"),
            )
        ]
        server_cache_body = script[
            script.index("function _loadServerCacheForMissingTabs") : script.index(
                "function _progressParams",
                script.index("function _loadServerCacheForMissingTabs"),
            )
        ]

        for body in (interrupted_body, server_cache_body):
            self.assertIn("if (_isTabBusy(tab, scope)) return;", body)
            self.assertGreaterEqual(
                body.count("if (_isTabBusy(tab, scope)) return;"),
                2,
            )

    def test_evolve_restore_paths_cover_all_profile_tabs(self):
        script = read_static("evolve.js")
        self.assertIn(
            'const EVOLVE_TABS = ["profile", "memory", "rules", "signals", "patterns"]',
            script,
        )
        for tab in ("profile", "memory", "rules", "signals", "patterns"):
            self.assertIn(f'"{tab}"', script)

        for marker in (
            "function _clearStaleErrorCache",
            "function _showInterruptedBanner",
            "function _updateTabStatusIndicators",
            "function updateEvolveOverviewBar",
            "function _loadServerCacheForMissingTabs",
            "function refreshAllEvolveTabs",
        ):
            body = script[
                script.index(marker) : script.index(
                    "function ", script.index(marker) + len(marker)
                )
            ]
            self.assertIn("EVOLVE_TABS", body)

    def test_evolve_detach_keeps_recovered_progress_pollers_alive(self):
        script = read_static("evolve.js")
        abort_body = script[
            script.index("window.abortEvolveStreams = function") : script.index(
                "window.navigateToEvolveTab",
                script.index("window.abortEvolveStreams = function"),
            )
        ]

        self.assertIn("if (!detachOnly)", abort_body)
        self.assertIn("keepRecoveredPollers", abort_body)
        self.assertIn("_stopRecoveredRunPoll(tab)", abort_body)
        self.assertIn("ctrl.keepRecoveredPollers = !!keepRecoveredPollers;", abort_body)

    def test_evolve_detach_only_restarts_recovered_poll_for_page_reentry(self):
        script = read_static("evolve.js")
        stream_body = script[
            script.index("function _fetchEvolveTabStream") : script.index(
                "function _setEvolveRefreshButton",
                script.index("function _fetchEvolveTabStream"),
            )
        ]

        self.assertIn("abortCtrl.keepRecoveredPollers = false;", stream_body)
        self.assertIn(
            "if (abortCtrl.detachOnly && abortCtrl.keepRecoveredPollers) {",
            stream_body,
        )
        self.assertIn("_scheduleRecoveredRunPoll(tab, requestScope);", stream_body)

    def test_evolve_locale_change_preserves_recovered_running_panel(self):
        script = read_static("evolve.js")
        locale_body = script[
            script.index('window.addEventListener("localechange"') : script.index(
                "// app.js runs its first applyI18nDom",
                script.index('window.addEventListener("localechange"'),
            )
        ]

        self.assertIn("!evolveStreamAborts[evolveActiveTab]", locale_body)
        self.assertIn(
            "!_isTabBusy(evolveActiveTab, getEvolveScope())",
            locale_body,
        )

    def test_evolve_header_dynamic_node_removes_static_i18n_binding(self):
        script = read_static("evolve.js")

        self.assertIn("function _getEvolveUpdatedEl()", script)
        self.assertIn('el.hasAttribute("data-i18n")', script)
        self.assertIn('el.removeAttribute("data-i18n")', script)

    def test_evolve_refresh_controls_use_scope_aware_loading_checks(self):
        script = read_static("evolve.js")
        bind_body = script[
            script.index("function bindEvolveEvents()") : script.index(
                "function switchEvolveTab(",
                script.index("function bindEvolveEvents()"),
            )
        ]

        self.assertIn("_isTabBusy(evolveActiveTab, activeScope)", bind_body)
        self.assertNotIn("evolveLoadingTabs[evolveActiveTab]", bind_body)

    def test_evolve_terminal_events_do_not_require_stream_container(self):
        script = read_static("evolve.js")
        handler_body = script[
            script.index("function _handleEvolveStreamEvent") : script.index(
                "function refreshEvolveTab",
                script.index("function _handleEvolveStreamEvent"),
            )
        ]

        self.assertRegex(
            handler_body,
            re.compile(
                r'const needsContainer\s*=\s*evt.type === "tool"\s*\|\|\s*evt.type === "text"\s*\|\|\s*evt.type === "result"'
            ),
        )
        self.assertIn("if (!container && needsContainer) return;", handler_body)

    def test_twin_failed_analysis_keeps_recoverable_progress_view(self):
        script = read_static("twin.js")

        progress_button_body = script[
            script.index("function _updateProgressButton()") : script.index(
                "function _stopAnalysis()",
                script.index("function _updateProgressButton()"),
            )
        ]
        finish_body = script[
            script.index("function _finishAnalysis(") : script.index(
                "/** Handle a single SSE event",
                script.index("function _finishAnalysis("),
            )
        ]

        self.assertIn("let hasAnalysisProgress = false", script)
        self.assertIn("analysisRunning || hasAnalysisProgress", progress_button_body)
        self.assertIn("_markAnalysisFailed(", finish_body)
        self.assertIn("function _appendAnalysisErrorActions", script)
        self.assertIn('data-action="overview"', script)
        self.assertIn('data-action="retry"', script)
        self.assertIn('data-action="resume"', script)


if __name__ == "__main__":
    unittest.main()
