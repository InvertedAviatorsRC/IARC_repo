from __future__ import annotations

from gps_telemetry_visualizer.signal_health_data_patch import install as install_data
from gps_telemetry_visualizer.signal_health_layout_patch import install as install_layout
from gps_telemetry_visualizer.signal_health_render_patch import install as install_render
from gps_telemetry_visualizer.signal_health_ui_patch import install as install_ui


def setup(native_app) -> None:
    install_data()
    install_layout()
    install_render()
    install_ui(native_app)
