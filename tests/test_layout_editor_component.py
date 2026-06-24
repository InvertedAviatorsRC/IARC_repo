import re
import unittest
from pathlib import Path


COMPONENT_HTML = Path(__file__).resolve().parents[1] / "gps_telemetry_visualizer" / "layout_editor_component" / "index.html"
UI_PY = Path(__file__).resolve().parents[1] / "gps_telemetry_visualizer" / "ui.py"


class LayoutEditorComponentTests(unittest.TestCase):
    def setUp(self):
        self.html = COMPONENT_HTML.read_text(encoding="utf-8")
        self.ui = UI_PY.read_text(encoding="utf-8")

    def test_outer_editor_height_is_not_output_aspect_driven(self):
        self.assertIn('id="editor"', self.html)
        self.assertIn('id="canvas"', self.html)
        self.assertRegex(self.html, r"#editor\s*{[^}]*height:\s*100%", re.S)
        self.assertNotIn("height: clamp(", self.html)
        self.assertNotIn("wrap.style.aspectRatio", self.html)

    def test_canvas_is_fitted_inside_stable_editor(self):
        self.assertIn("function updateCanvasBounds()", self.html)
        self.assertIn("const editorWidth = editor.clientWidth", self.html)
        self.assertIn("const editorHeight = editor.clientHeight", self.html)
        self.assertIn("canvas.style.width", self.html)
        self.assertIn("canvas.style.height", self.html)

    def test_pointer_mapping_and_iframe_height_use_correct_layers(self):
        self.assertIn("canvas.getBoundingClientRect()", self.html)
        self.assertIn("editor.getBoundingClientRect().height", self.html)
        self.assertNotIn("wrap.getBoundingClientRect()", self.html)

    def test_preview_workspace_uses_a_flex_host_for_the_editor(self):
        self.assertIn('st.container(key="preview-workspace", border=False)', self.ui)
        self.assertIn(".st-key-preview-workspace", self.ui)
        self.assertIn("flex-direction: column", self.ui)
        self.assertIn('iframe[title="gps_layout_editor"]', self.ui)
        self.assertIn("height: 100% !important", self.ui)

    def test_ui_exposes_speedometer_style_selector(self):
        self.assertIn('"Speedometer style"', self.ui)
        self.assertIn('"180° half gauge"', self.ui)
        self.assertIn('"90° corner gauge"', self.ui)


if __name__ == "__main__":
    unittest.main()
