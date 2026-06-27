from __future__ import annotations

import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from PySide6.QtWidgets import QCheckBox

from gps_telemetry_visualizer import core


_PATCHED_CORE = False
_PATCHED_NATIVE_APP = False
_ORIGINAL_SETUP_MAP_ARTISTS = None
_ORIGINAL_UPDATE_MAP_ARTISTS = None

_SPEED_TRAIL_CMAP = LinearSegmentedColormap.from_list(
    "speed_trail",
    ["#00d5ff", "#ffe066", "#ff3355"],
)


def install_core() -> None:
    """Install speed-colored map trail rendering hooks."""
    global _PATCHED_CORE, _ORIGINAL_SETUP_MAP_ARTISTS, _ORIGINAL_UPDATE_MAP_ARTISTS
    if _PATCHED_CORE:
        return

    _ORIGINAL_SETUP_MAP_ARTISTS = core._setup_map_artists
    _ORIGINAL_UPDATE_MAP_ARTISTS = core._update_map_artists
    core._setup_map_artists = _setup_map_artists
    core._update_map_artists = _update_map_artists
    _PATCHED_CORE = True


def setup(native_app) -> None:
    """Add the native UI control for speed-colored GPS trail rendering."""
    global _PATCHED_NATIVE_APP
    install_core()

    if _PATCHED_NATIVE_APP:
        return

    original_build_settings_group = native_app.MainWindow._build_settings_group
    original_connect_preview_signals = native_app.MainWindow._connect_preview_signals
    original_config = native_app.MainWindow._config

    def _build_settings_group(self):
        group = original_build_settings_group(self)
        self.speed_colored_trail_checkbox = QCheckBox("Speed-colored trail")
        self.speed_colored_trail_checkbox.setChecked(False)
        group.layout().addWidget(self.speed_colored_trail_checkbox)
        return group

    def _connect_preview_signals(self):
        original_connect_preview_signals(self)
        self.speed_colored_trail_checkbox.toggled.connect(self.schedule_preview)

    def _config(self, include_time: bool = True):
        config = original_config(self, include_time)
        checkbox = getattr(self, "speed_colored_trail_checkbox", None)
        config.speed_colored_trail = bool(checkbox and checkbox.isChecked())
        return config

    native_app.MainWindow._build_settings_group = _build_settings_group
    native_app.MainWindow._connect_preview_signals = _connect_preview_signals
    native_app.MainWindow._config = _config
    _PATCHED_NATIVE_APP = True


def _setup_map_artists(ax_map, data: core.TelemetryData, config: core.RenderConfig):
    if not getattr(config, "speed_colored_trail", False):
        return _ORIGINAL_SETUP_MAP_ARTISTS(ax_map, data, config)

    core._configure_map_axis(ax_map, data, config)
    element_scale = core._axis_element_scale(ax_map)

    trail_line = LineCollection(
        [],
        cmap=_SPEED_TRAIL_CMAP,
        norm=Normalize(*_trail_speed_limits(data.frame_speed)),
        linewidths=4 * element_scale,
        alpha=0.95,
        zorder=1,
    )
    trail_line.set_capstyle("round")
    trail_line.set_joinstyle("round")
    ax_map.add_collection(trail_line)

    start_marker, = ax_map.plot(
        [data.frame_x[0]],
        [data.frame_y[0]],
        marker="*",
        linestyle="None",
        markersize=20 * element_scale,
        markeredgewidth=0,
        color=core.to_rgba(config.start_marker_color, 1.0),
        zorder=3,
    )
    dot, = ax_map.plot(
        [],
        [],
        "o",
        markersize=14 * element_scale,
        color=core.to_rgba(config.dot_color, 1.0),
        zorder=4,
    )
    return core.MapArtists(trail_line, start_marker, dot)


def _update_map_artists(
    artists: core.MapArtists,
    data: core.TelemetryData,
    frame: int,
    state: core.FrameVisualState,
) -> None:
    if not isinstance(artists.trail_line, LineCollection):
        _ORIGINAL_UPDATE_MAP_ARTISTS(artists, data, frame, state)
        return

    frame = max(0, min(int(frame), len(data.frame_x) - 1))
    trail_x = data.frame_x[: frame + 1]
    trail_y = data.frame_y[: frame + 1]
    trail_speed = data.frame_speed[: frame + 1]

    if len(trail_x) < 2:
        artists.trail_line.set_segments([])
        artists.trail_line.set_array(np.asarray([], dtype=float))
    else:
        artists.trail_line.set_segments(_build_trail_segments(trail_x, trail_y))
        artists.trail_line.set_array(np.asarray(trail_speed[1:], dtype=float))
        artists.trail_line.set_norm(Normalize(*_trail_speed_limits(data.frame_speed)))

    artists.start_marker.set_data([data.frame_x[0]], [data.frame_y[0]])
    artists.dot.set_data([state.current_x], [state.current_y])


def _build_trail_segments(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    points = np.column_stack([x, y]).reshape(-1, 1, 2)
    return np.concatenate([points[:-1], points[1:]], axis=1)


def _trail_speed_limits(speed: np.ndarray) -> tuple[float, float]:
    vmax = float(np.nanmax(speed)) if len(speed) else 0.0
    if not np.isfinite(vmax) or vmax <= 0:
        vmax = 1.0
    return 0.0, vmax
