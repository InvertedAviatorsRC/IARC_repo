import re
import unittest
from pathlib import Path


COMPONENT_HTML = Path(__file__).resolve().parents[1] / "gps_telemetry_visualizer" / "layout_editor_component" / "index.html"


class LayoutEditorComponentTests(unittest.TestCase):
    def setUp(self):
        self.html = COMPONENT_HTML.read_text(encoding="utf-8")

    def test_outer_editor_height_is_not_output_aspect_driven(self):
        self.assertIn('id="editor"', self.html)
        self.assertIn('id="canvas"', self.html)
        self.assertRegex(self.html, r"#editor\s*{[^}]*height:\s*clamp\(", re.S)
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


if __name__ == "__main__":
    unittest.main()
