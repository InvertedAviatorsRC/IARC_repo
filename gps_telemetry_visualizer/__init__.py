"""GPS telemetry visualization package."""

from gps_telemetry_visualizer.core import (
    RenderConfig,
    TelemetryData,
    convert_speed,
    parse_gps,
    prepare_telemetry,
    render_animation,
    render_preview_frames,
    render_static_preview,
)

__all__ = [
    "RenderConfig",
    "TelemetryData",
    "convert_speed",
    "parse_gps",
    "prepare_telemetry",
    "render_animation",
    "render_preview_frames",
    "render_static_preview",
]

__version__ = "0.1.0"
