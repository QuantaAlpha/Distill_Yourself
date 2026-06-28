import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RuntimePreviewStaticTests(unittest.TestCase):
    def test_runtime_preview_renders_partitioned_sections(self):
        twin_js = (ROOT / "static" / "twin.js").read_text(encoding="utf-8")
        style_css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")

        self.assertIn("function renderRuntimePreviewSections", twin_js)
        self.assertIn("twin-runtime-compact-summary", twin_js)
        self.assertIn("twin-runtime-section-list", twin_js)
        self.assertIn("twin-runtime-section-card", style_css)
        self.assertNotIn("max-height: 58vh", style_css)
        self.assertIn('toggle("twin-persona-card", name === "overview")', twin_js)
        self.assertIn("twin-runtime-hero-action", twin_js)
        self.assertNotIn("twin-runtime-actions", twin_js)
        self.assertIn('data-nav="sync"', twin_js)
        self.assertNotIn("focusContent: true", twin_js)
        self.assertIn("function focusRuntimePreviewContent", twin_js)
        self.assertIn("function resetTwinScrollTop", twin_js)
        self.assertIn("else resetTwinScrollTop()", twin_js)
        self.assertIn("overflow-anchor: none", style_css)
        self.assertIn('show("twin-persona-card")', twin_js)
        self.assertIn("twin-runtime-open-hint", twin_js)
        self.assertNotIn("function renderRuntimePersonaSummary", twin_js)
        self.assertNotIn("twin-runtime-feature", twin_js)
        self.assertNotIn("twin-runtime-persona", style_css)
        self.assertIn("twin-persona-card-hint", html := (ROOT / "static" / "index.html").read_text(encoding="utf-8"))
        self.assertIn("twin-persona-card", html)
        self.assertIn("personaCardEl.onclick = () => loadRuntimePreview()", twin_js)
        self.assertNotIn("personaCardEl.onclick = openPersonaOptions", twin_js)
        self.assertIn("stopImmediatePropagation", twin_js)


if __name__ == "__main__":
    unittest.main()
