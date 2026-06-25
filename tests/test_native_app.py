import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NativeAppTests(unittest.TestCase):
    def test_packaging_uses_native_entry_point(self):
        macos_script = (ROOT / "scripts" / "build_macos_app.sh").read_text(encoding="utf-8")
        desktop_entry = (ROOT / "native_desktop_app.py").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("native_desktop_app.py", macos_script)
        self.assertNotIn("streamlit_desktop_app.py", macos_script)
        self.assertIn("gps_telemetry_visualizer.native_app", desktop_entry)
        self.assertIn('gps-vis-native = "gps_telemetry_visualizer.native_app:main"', pyproject)

    def test_native_window_can_be_constructed(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from gps_telemetry_visualizer.native_app import MainWindow

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        try:
            self.assertEqual(window.windowTitle(), "GPS Telemetry Visualizer")
            self.assertEqual(window.speedometer_style.currentText(), "180° half gauge")
            self.assertIsNotNone(window.preview)
        finally:
            window.close()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
