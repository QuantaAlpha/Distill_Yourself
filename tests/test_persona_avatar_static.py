import os
import re
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_static(path):
    with open(os.path.join(ROOT, "static", path), encoding="utf-8") as f:
        return f.read()


class TestPersonaAvatarStaticIntegration(unittest.TestCase):
    def test_rive_lottie_not_blocking_in_index_html(self):
        """Rive/Lottie scripts should not be in index.html (removed for faster startup)."""
        html = read_static("index.html")
        self.assertNotIn("rive.js", html)
        self.assertNotIn("lottie.min.js", html)

    def test_twin_view_has_persona_avatar_mount(self):
        html = read_static("index.html")

        self.assertIn('id="twin-persona-avatar"', html)
        self.assertIn('id="twin-persona-img"', html)
        self.assertIn('id="twin-persona-title"', html)
        self.assertIn('id="twin-persona-traits"', html)
        self.assertIn('id="twin-persona-options"', html)
        self.assertIn('class="hidden"', html)
        self.assertIn('role="dialog"', html)

    def test_twin_js_opens_deduplicated_scrollable_avatar_picker(self):
        script = read_static("twin.js")

        self.assertIn("COGNITIVE_MODEL_OPTIONS", script)
        self.assertIn("AVATAR_STYLE_OPTIONS", script)
        self.assertIn("groupAvatarOptions", script)
        self.assertIn("twin-persona-group", script)
        self.assertIn("twin-persona-style-options", script)
        self.assertIn("renderPersonaOptions", script)
        self.assertIn("openPersonaOptions", script)
        self.assertIn("closePersonaOptions", script)
        self.assertIn("USER_PERSONA_SELECTION_KEY", script)
        self.assertEqual(len(re.findall(r'id: "cm_', script)), 48)
        self.assertEqual(len(re.findall(r'avatarId: "P\d{2}-[AB]"', script)), 32)
        self.assertEqual(len(re.findall(r'image: "assets/cognitive-avatars/v2/images/', script)), 32)

    def test_twin_css_avatar_picker_is_modal_and_scrollable(self):
        css = read_static("style.css")

        self.assertIn("#twin-persona-options", css)
        self.assertIn("position: fixed", css)
        self.assertIn("overflow-y: auto", css)
        self.assertIn("max-height", css)

    def test_twin_avatar_picker_groups_multiple_types_per_row(self):
        css = read_static("style.css")

        self.assertIn(".twin-persona-group", css)
        self.assertIn(".twin-persona-style-options", css)
        self.assertIn("grid-template-columns: repeat(auto-fill, minmax(268px, 1fr))", css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", css)
        self.assertIn("width: 112px", css)
        self.assertIn("height: 112px", css)
        self.assertIn("@media (max-width: 720px)", css)
        self.assertIn("grid-template-columns: 1fr", css)

    def test_manual_avatar_selection_does_not_replace_ai_type_text(self):
        script = read_static("twin.js")

        self.assertNotIn("titleEl.textContent = manualOption.name", script)
        self.assertNotIn("subtitleEl.textContent = `已手动选择", script)
        self.assertNotIn("替换当前头像和名称", script)

    @unittest.skipUnless(
        "PERSONA_PRESETS" in open(os.path.join(ROOT, "static", "twin.js")).read(),
        "persona features not yet integrated into twin.js",
    )
    def test_twin_js_maps_traits_to_local_persona_assets(self):
        script = read_static("twin.js")

        self.assertIn("PERSONA_PRESETS", script)
        self.assertIn("PERSONA_TEMPLATE_RULES", script)
        self.assertIn("derivePersonaPreset", script)
        self.assertIn("scorePersonaTemplate", script)
        self.assertIn("renderPersonaAvatar", script)
        self.assertRegex(script, re.compile(r"assets/persona/.+\.json"))

    @unittest.skipUnless(
        "renderRivePersona" in open(os.path.join(ROOT, "static", "twin.js")).read(),
        "persona renderers not yet integrated into twin.js",
    )
    def test_twin_js_has_rive_first_lottie_fallback_renderer(self):
        script = read_static("twin.js")

        self.assertIn("renderRivePersona", script)
        self.assertIn("renderLottiePersona", script)
        self.assertIn("fallbackRenderer", script)
        self.assertIn(".riv", script)

    @unittest.skipUnless(
        "PERSONA_PRESETS" in open(os.path.join(ROOT, "static", "twin.js")).read(),
        "persona presets not yet integrated into twin.js",
    )
    def test_persona_presets_use_local_rive_avatar_artboards(self):
        script = read_static("twin.js")

        relative_path = "assets/persona/avatars.riv"
        for artboard, state_machine in (
            ("Avatar 1", "avatar"),
            ("Avatar 2", "avatar2"),
            ("Avatar 3", "avatar3"),
        ):
            self.assertIn(f'riveArtboard: "{artboard}"', script)
            self.assertIn(f'riveStateMachine: "{state_machine}"', script)

        self.assertEqual(script.count(f'riveAsset: "{relative_path}"'), 3)
        asset_path = os.path.join(ROOT, "static", relative_path)
        with open(asset_path, "rb") as asset:
            self.assertEqual(asset.read(4), b"RIVE")


if __name__ == "__main__":
    unittest.main()
