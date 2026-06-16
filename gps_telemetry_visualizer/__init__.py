"""GPS telemetry visualization package."""

from gps_telemetry_visualizer.core import (
    RenderConfig,
    FrameVisualState,
    TelemetryData,
    compute_frame_states,
    convert_speed,
    format_distance,
    format_speed_unit,
    frame_state_at,
    parse_gps,
    prepare_telemetry,
    render_animation,
    render_preview_frames,
    render_static_preview,
)

__all__ = [
    "RenderConfig",
    "FrameVisualState",
    "TelemetryData",
    "compute_frame_states",
    "convert_speed",
    "format_distance",
    "format_speed_unit",
    "frame_state_at",
    "parse_gps",
    "prepare_telemetry",
    "render_animation",
    "render_preview_frames",
    "render_static_preview",
]

__version__ = "0.1.0"
