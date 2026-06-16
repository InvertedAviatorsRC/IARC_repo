from __future__ import annotations

import io
import math
import os
import re
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple

_mpl_config_dir = Path(tempfile.gettempdir()) / "gps-telemetry-visualizer-matplotlib"
_mpl_config_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_config_dir))

import matplotlib

matplotlib.use("Agg", force=True)

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.animation import FFMpegWriter, FuncAnimation
from matplotlib.colors import to_rgba


VALID_EXPORT_MODES = ("map", "speedometer", "both")
VALID_SPEED_UNITS = ("kmh", "mph", "ms")
LAYOUT_ELEMENT_NAMES = ("map", "speedometer", "top_speed", "furthest_distance")
SPEED_RECORD_THRESHOLDS = {
    "mph": 0.5,
    "kmh": 0.804672,
    "ms": 0.22352,
}
DISTANCE_RECORD_THRESHOLD_METERS = 3.048
RECORD_HIGHLIGHT_SECONDS = 3.0
RECORD_HIGHLIGHT_COLOR = "#22c55e"


@dataclass
class RenderConfig:
    export_mode: str = "both"
    fps: int = 30
    seconds_between_gps_points: float = 1.0
    gps_col: str = "GPS"
    speed_col: str = "GSpd(kmh)"
    heading_col: str = "Hdg(°)"
    altitude_col: str = "Alt(m)"
    speed_input_unit: str = "kmh"
    speed_output_unit: str = "mph"
    max_speed: Optional[float] = None
    path_color: str = "#00d5ff"
    dot_color: str = "#ff3355"
    start_marker_color: str = "#ffd43b"
    speedometer_color: str = "#00d5ff"
    needle_color: str = "#ff3355"
    text_color: str = "#ffffff"
    background_color: str = "#101820"
    transparent: bool = True
    padding: float = 10.0
    start_time: float = 0.0
    end_time: Optional[float] = None
    output_width: int = 1920
    output_height: int = 1080
    layout: Optional["OverlayLayout"] = None


@dataclass
class TelemetryData:
    frame_x: np.ndarray
    frame_y: np.ndarray
    frame_speed: np.ndarray
    frame_heading: np.ndarray
    frame_altitude: np.ndarray
    bounds: Tuple[float, float, float, float]
    max_speed: float
    source_rows: int
    valid_rows: int
    gps_col: str
    speed_col: Optional[str]
    heading_col: Optional[str]
    altitude_col: Optional[str]
    total_duration_seconds: float
    start_time: float
    end_time: float


@dataclass(frozen=True)
class FrameVisualState:
    frame_index: int
    current_speed: float
    current_x: float
    current_y: float
    top_speed: float
    top_speed_highlight: bool
    current_distance_m: float
    furthest_distance_m: float
    distance_highlight: bool


@dataclass
class MapArtists:
    trail_line: object
    start_marker: object
    dot: object


@dataclass(frozen=True)
class CanvasConfig:
    width: int = 1920
    height: int = 1080


@dataclass
class ElementLayout:
    x: float
    y: float
    visible: bool = True


@dataclass
class OverlayLayout:
    map: ElementLayout = field(default_factory=lambda: ElementLayout(540, 480, True))
    speedometer: ElementLayout = field(default_factory=lambda: ElementLayout(1380, 430, True))
    top_speed: ElementLayout = field(default_factory=lambda: ElementLayout(1380, 790, True))
    furthest_distance: ElementLayout = field(default_factory=lambda: ElementLayout(540, 830, True))


@dataclass(frozen=True)
class ElementBounds:
    name: str
    x: float
    y: float
    width: float
    height: float
    visible: bool = True

    @property
    def left(self) -> float:
        return self.x - self.width / 2

    @property
    def top(self) -> float:
        return self.y - self.height / 2

    @property
    def right(self) -> float:
        return self.x + self.width / 2

    @property
    def bottom(self) -> float:
        return self.y + self.height / 2


@dataclass
class CompositionArtists:
    ax_map: object = None
    map_artists: Optional[MapArtists] = None
    ax_speedometer: object = None
    ax_top_speed: object = None
    ax_furthest_distance: object = None


ProgressCallback = Optional[Callable[[int, int], None]]


def parse_gps(value: object) -> Tuple[Optional[float], Optional[float]]:
    """Parse values like '44.766099 -93.331609' or '44.766099,-93.331609'."""
    nums = re.findall(r"-?\d+(?:\.\d+)?", str(value))
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    return None, None


def convert_speed(value: object, input_unit: str = "kmh", output_unit: str = "mph") -> float:
    if input_unit not in VALID_SPEED_UNITS:
        raise ValueError("input_unit must be one of: {}".format(", ".join(VALID_SPEED_UNITS)))
    if output_unit not in VALID_SPEED_UNITS:
        raise ValueError("output_unit must be one of: {}".format(", ".join(VALID_SPEED_UNITS)))

    numeric_value = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric_value):
        numeric_value = 0.0
    numeric_value = float(numeric_value)

    if input_unit == "kmh":
        speed_ms = numeric_value / 3.6
    elif input_unit == "mph":
        speed_ms = numeric_value * 0.44704
    else:
        speed_ms = numeric_value

    if output_unit == "kmh":
        return speed_ms * 3.6
    if output_unit == "mph":
        return speed_ms / 0.44704
    return speed_ms


def detect_columns(columns: Iterable[str]) -> dict:
    column_list = list(columns)

    return {
        "gps": _find_column(column_list, "GPS", ("gps",)),
        "speed": _find_column(column_list, "GSpd(kmh)", ("gspd", "speed")),
        "heading": _find_column(column_list, "Hdg(°)", ("hdg", "heading")),
        "altitude": _find_column(column_list, "Alt(m)", ("alt", "altitude")),
    }


def prepare_telemetry(csv_source, config: RenderConfig) -> TelemetryData:
    _validate_config(config)
    df = pd.read_csv(csv_source)
    source_rows = len(df)

    gps_col = _require_column(df, config.gps_col, ("gps",), "GPS")
    speed_col = _find_column(df.columns, config.speed_col, ("gspd", "speed"))
    heading_col = _find_column(df.columns, config.heading_col, ("hdg", "heading"))
    altitude_col = _find_column(df.columns, config.altitude_col, ("alt", "altitude"))

    parsed = df[gps_col].apply(lambda value: pd.Series(parse_gps(value), index=["lat", "lon"]))
    df = pd.concat([df, parsed], axis=1)
    df = df.dropna(subset=["lat", "lon"]).reset_index(drop=True)

    if df.empty:
        raise ValueError("No valid GPS rows were found in the selected CSV.")

    if speed_col:
        df["speed_converted"] = df[speed_col].apply(
            lambda value: convert_speed(value, config.speed_input_unit, config.speed_output_unit)
        )
    else:
        df["speed_converted"] = 0.0

    lat0 = float(df["lat"].iloc[0])
    lon0 = float(df["lon"].iloc[0])
    meters_per_degree_lon = 111_320 * math.cos(math.radians(lat0))
    df["x"] = (df["lon"].astype(float) - lon0) * meters_per_degree_lon
    df["y"] = (df["lat"].astype(float) - lat0) * 110_540

    frame_x, frame_y, frame_speed, frame_heading, frame_altitude = _smooth_frames(
        df,
        fps=config.fps,
        seconds_between_points=config.seconds_between_gps_points,
        heading_col=heading_col,
        altitude_col=altitude_col,
    )
    total_duration_seconds = max(0.0, (len(frame_x) - 1) / float(config.fps))
    (
        frame_x,
        frame_y,
        frame_speed,
        frame_heading,
        frame_altitude,
        render_start_time,
        render_end_time,
    ) = _trim_frames(
        frame_x,
        frame_y,
        frame_speed,
        frame_heading,
        frame_altitude,
        fps=config.fps,
        start_time=config.start_time,
        end_time=config.end_time,
        total_duration_seconds=total_duration_seconds,
    )

    max_speed = _resolve_max_speed(pd.Series(frame_speed), config.max_speed)
    bounds = _frame_bounds(frame_x, frame_y, float(config.padding))

    return TelemetryData(
        frame_x=frame_x,
        frame_y=frame_y,
        frame_speed=frame_speed,
        frame_heading=frame_heading,
        frame_altitude=frame_altitude,
        bounds=bounds,
        max_speed=max_speed,
        source_rows=source_rows,
        valid_rows=len(df),
        gps_col=gps_col,
        speed_col=speed_col,
        heading_col=heading_col,
        altitude_col=altitude_col,
        total_duration_seconds=total_duration_seconds,
        start_time=render_start_time,
        end_time=render_end_time,
    )


def compute_frame_states(data: TelemetryData, config: RenderConfig) -> list[FrameVisualState]:
    highlight_frames = max(1, int(round(RECORD_HIGHLIGHT_SECONDS * config.fps)))
    speed_threshold = SPEED_RECORD_THRESHOLDS[config.speed_output_unit]

    start_x = float(data.frame_x[0])
    start_y = float(data.frame_y[0])
    top_speed = float(data.frame_speed[0])
    highlighted_top_speed = top_speed
    speed_highlight_until = -1
    furthest_distance = 0.0
    highlighted_distance = 0.0
    distance_highlight_until = -1
    states = []

    for frame, (x_value, y_value, speed_value) in enumerate(
        zip(data.frame_x, data.frame_y, data.frame_speed)
    ):
        speed = float(speed_value)
        if speed > top_speed:
            top_speed = speed
        if frame > 0 and top_speed >= highlighted_top_speed + speed_threshold:
            highlighted_top_speed = top_speed
            speed_highlight_until = frame + highlight_frames

        distance = math.hypot(float(x_value) - start_x, float(y_value) - start_y)
        if distance > furthest_distance:
            furthest_distance = distance
        if frame > 0 and furthest_distance >= highlighted_distance + DISTANCE_RECORD_THRESHOLD_METERS:
            highlighted_distance = furthest_distance
            distance_highlight_until = frame + highlight_frames

        states.append(
            FrameVisualState(
                frame_index=frame,
                current_speed=speed,
                current_x=float(x_value),
                current_y=float(y_value),
                top_speed=top_speed,
                top_speed_highlight=frame < speed_highlight_until,
                current_distance_m=distance,
                furthest_distance_m=furthest_distance,
                distance_highlight=frame < distance_highlight_until,
            )
        )

    return states


def frame_state_at(data: TelemetryData, config: RenderConfig, frame_index: int) -> FrameVisualState:
    states = compute_frame_states(data, config)
    frame = max(0, min(len(states) - 1, int(frame_index)))
    return states[frame]


def format_speed_unit(speed_unit: str) -> str:
    if speed_unit == "ms":
        return "M/S"
    return speed_unit.upper()


def format_distance(distance_m: float, speed_unit: str) -> str:
    distance_m = max(0.0, float(distance_m))
    if speed_unit == "mph":
        feet = distance_m * 3.280839895
        if feet < 5280:
            return "{:,.0f} FT".format(feet)
        return "{:.1f} MI".format(feet / 5280)

    if distance_m < 1000:
        return "{:,.0f} M".format(distance_m)
    return "{:.1f} KM".format(distance_m / 1000)


def canvas_from_config(config: RenderConfig) -> CanvasConfig:
    return CanvasConfig(int(config.output_width), int(config.output_height))


def default_overlay_layout(width: int, height: int, export_mode: str = "both") -> OverlayLayout:
    width = int(width)
    height = int(height)
    aspect = width / float(height)
    map_visible = export_mode in ("map", "both")
    speed_visible = export_mode in ("speedometer", "both")

    if aspect >= 1.2:
        layout = OverlayLayout(
            map=ElementLayout(width * 0.29, height * 0.46, map_visible),
            speedometer=ElementLayout(width * 0.72, height * 0.43, speed_visible),
            furthest_distance=ElementLayout(width * 0.29, height * 0.83, map_visible),
            top_speed=ElementLayout(width * 0.72, height * 0.78, speed_visible),
        )
    elif aspect <= 0.85:
        layout = OverlayLayout(
            map=ElementLayout(width * 0.5, height * 0.26, map_visible),
            speedometer=ElementLayout(width * 0.5, height * 0.68, speed_visible),
            furthest_distance=ElementLayout(width * 0.5, height * 0.49, map_visible),
            top_speed=ElementLayout(width * 0.5, height * 0.88, speed_visible),
        )
    else:
        layout = OverlayLayout(
            map=ElementLayout(width * 0.32, height * 0.42, map_visible),
            speedometer=ElementLayout(width * 0.68, height * 0.42, speed_visible),
            furthest_distance=ElementLayout(width * 0.32, height * 0.76, map_visible),
            top_speed=ElementLayout(width * 0.68, height * 0.76, speed_visible),
        )

    return layout


def resolve_overlay_layout(config: RenderConfig) -> OverlayLayout:
    if config.layout is None:
        return default_overlay_layout(config.output_width, config.output_height, config.export_mode)
    return clone_overlay_layout(config.layout)


def clone_overlay_layout(layout: OverlayLayout) -> OverlayLayout:
    return OverlayLayout(
        map=ElementLayout(layout.map.x, layout.map.y, layout.map.visible),
        speedometer=ElementLayout(layout.speedometer.x, layout.speedometer.y, layout.speedometer.visible),
        top_speed=ElementLayout(layout.top_speed.x, layout.top_speed.y, layout.top_speed.visible),
        furthest_distance=ElementLayout(
            layout.furthest_distance.x,
            layout.furthest_distance.y,
            layout.furthest_distance.visible,
        ),
    )


def scale_overlay_layout(layout: OverlayLayout, old_width: int, old_height: int, new_width: int, new_height: int) -> OverlayLayout:
    old_width = max(1, int(old_width))
    old_height = max(1, int(old_height))
    new_width = int(new_width)
    new_height = int(new_height)

    def scaled(element: ElementLayout) -> ElementLayout:
        return ElementLayout(
            element.x / old_width * new_width,
            element.y / old_height * new_height,
            element.visible,
        )

    return OverlayLayout(
        map=scaled(layout.map),
        speedometer=scaled(layout.speedometer),
        top_speed=scaled(layout.top_speed),
        furthest_distance=scaled(layout.furthest_distance),
    )


def overlay_layout_to_dict(layout: OverlayLayout) -> dict:
    return {
        "map": _element_layout_to_dict(layout.map),
        "speedometer": _element_layout_to_dict(layout.speedometer),
        "top_speed": _element_layout_to_dict(layout.top_speed),
        "furthest_distance": _element_layout_to_dict(layout.furthest_distance),
    }


def overlay_layout_from_dict(value: object, width: int, height: int, export_mode: str = "both") -> OverlayLayout:
    default_layout = default_overlay_layout(width, height, export_mode)
    if not isinstance(value, dict):
        return default_layout

    def parsed(name: str) -> ElementLayout:
        default_element = getattr(default_layout, name)
        raw = value.get(name, {})
        if not isinstance(raw, dict):
            return default_element
        return ElementLayout(
            float(raw.get("x", raw.get("center_x", default_element.x))),
            float(raw.get("y", raw.get("center_y", default_element.y))),
            bool(raw.get("visible", default_element.visible)),
        )

    return OverlayLayout(
        map=parsed("map"),
        speedometer=parsed("speedometer"),
        top_speed=parsed("top_speed"),
        furthest_distance=parsed("furthest_distance"),
    )


def compute_element_bounds(name: str, layout: OverlayLayout, canvas: CanvasConfig, config: Optional[RenderConfig] = None) -> ElementBounds:
    if name not in LAYOUT_ELEMENT_NAMES:
        raise ValueError("Unknown layout element: {}".format(name))
    element = getattr(layout, name)
    width, height = _element_size(name, canvas)
    return ElementBounds(name, float(element.x), float(element.y), float(width), float(height), bool(element.visible))


def compute_layout_bounds(layout: OverlayLayout, canvas: CanvasConfig, config: Optional[RenderConfig] = None) -> dict[str, ElementBounds]:
    return {name: compute_element_bounds(name, layout, canvas, config) for name in LAYOUT_ELEMENT_NAMES}


def preview_to_output_coordinates(
    preview_x: float,
    preview_y: float,
    preview_width: float,
    preview_height: float,
    canvas: CanvasConfig,
) -> Tuple[float, float]:
    if preview_width <= 0 or preview_height <= 0:
        raise ValueError("preview_width and preview_height must be positive")
    return (
        float(preview_x) / float(preview_width) * canvas.width,
        float(preview_y) / float(preview_height) * canvas.height,
    )


def layout_warnings(layout: OverlayLayout, canvas: CanvasConfig, config: Optional[RenderConfig] = None) -> list[str]:
    bounds = compute_layout_bounds(layout, canvas, config)
    warnings = []
    visible_bounds = [box for box in bounds.values() if box.visible]

    for box in visible_bounds:
        visibility = _box_visibility(box, canvas)
        label = _element_label(box.name)
        if visibility == "outside":
            warnings.append("{} is completely outside the output frame and will not appear in the rendered video.".format(label))
        elif visibility == "partial":
            warnings.append("{} is partially outside the output frame and will be cropped.".format(label))

    for index, first in enumerate(visible_bounds):
        for second in visible_bounds[index + 1 :]:
            if _boxes_overlap(first, second):
                warnings.append("{} overlaps {}.".format(_element_label(first.name), _element_label(second.name).lower()))

    return warnings


def render_static_preview(csv_source, config: RenderConfig, frame_fraction: float = 0.65, frame_time: Optional[float] = None):
    data = prepare_telemetry(csv_source, config)
    states = compute_frame_states(data, config)
    if frame_time is None:
        frame = int(len(data.frame_x) * frame_fraction)
    else:
        frame = int(round(max(0.0, frame_time) * config.fps))
    frame = max(0, min(len(data.frame_x) - 1, frame))
    fig, artists = _build_composition(data, config)
    _update_composition(artists, data, config, frame, states[frame])
    return fig


def render_preview_frames(csv_source, config: RenderConfig, frame_count: int = 28, dpi: int = 110) -> Tuple[list[bytes], TelemetryData]:
    data = prepare_telemetry(csv_source, config)
    states = compute_frame_states(data, config)
    fig, artists = _build_composition(data, config)

    frame_count = max(1, min(int(frame_count), len(data.frame_x)))
    frame_indexes = np.linspace(0, len(data.frame_x) - 1, frame_count, dtype=int)
    rendered_frames = []

    for frame in frame_indexes:
        _update_composition(artists, data, config, frame, states[frame])
        buffer = io.BytesIO()
        fig.savefig(
            buffer,
            format="png",
            dpi=fig.dpi,
            facecolor=fig.get_facecolor(),
            transparent=config.transparent,
        )
        rendered_frames.append(buffer.getvalue())

    plt.close(fig)
    return rendered_frames, data


def render_animation(csv_source, output_path, config: RenderConfig, progress_callback: ProgressCallback = None) -> Path:
    output = Path(output_path).expanduser().resolve()
    if output.suffix.lower() != ".mov" and config.transparent:
        config = replace(config, transparent=False)

    data = prepare_telemetry(csv_source, config)
    states = compute_frame_states(data, config)
    output.parent.mkdir(parents=True, exist_ok=True)

    _configure_ffmpeg()

    fig, artists = _build_composition(data, config)

    def update(frame):
        state = states[frame]
        changed_artists = _update_composition(artists, data, config, frame, state)

        if progress_callback:
            progress_callback(frame + 1, len(data.frame_x))

        return changed_artists

    animation = FuncAnimation(
        fig,
        update,
        frames=len(data.frame_x),
        interval=1000 / config.fps,
        blit=False,
    )

    writer = _build_writer(output, config)
    savefig_kwargs = {"transparent": config.transparent} if output.suffix.lower() == ".mov" else {}
    animation.save(str(output), writer=writer, dpi=fig.dpi, savefig_kwargs=savefig_kwargs)
    plt.close(fig)
    return output


def draw_speedometer(
    ax,
    speed: float,
    max_speed: float,
    config: RenderConfig,
    state: Optional[FrameVisualState] = None,
    show_top_speed: bool = True,
) -> None:
    ax.clear()
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-0.62, 1.25)
    ax.set_facecolor((0, 0, 0, 0) if config.transparent else to_rgba(config.background_color))

    arc = patches.Arc(
        (0, 0),
        2,
        2,
        theta1=20,
        theta2=160,
        linewidth=6,
        color=to_rgba(config.speedometer_color, 0.78),
    )
    ax.add_patch(arc)

    tick_step = _nice_tick_step(max_speed)
    text_color = to_rgba(config.text_color, 0.92)

    for tick in np.arange(0, max_speed + tick_step, tick_step):
        tick = min(tick, max_speed)
        angle = math.radians(160 - (tick / max_speed) * 140)
        x_outer = math.cos(angle)
        y_outer = math.sin(angle)
        x_inner = 0.86 * math.cos(angle)
        y_inner = 0.86 * math.sin(angle)

        ax.plot([x_inner, x_outer], [y_inner, y_outer], linewidth=2, color=to_rgba(config.text_color, 0.72))
        ax.text(
            0.7 * math.cos(angle),
            0.7 * math.sin(angle),
            str(int(round(tick))),
            ha="center",
            va="center",
            fontsize=9,
            color=text_color,
        )

    clamped_speed = max(0.0, min(float(speed), max_speed))
    needle_angle = math.radians(160 - (clamped_speed / max_speed) * 140)
    ax.plot(
        [0, 0.78 * math.cos(needle_angle)],
        [0, 0.78 * math.sin(needle_angle)],
        linewidth=4,
        color=to_rgba(config.needle_color, 1.0),
    )

    ax.add_patch(patches.Circle((0, 0), 0.06, color=to_rgba(config.text_color, 1.0)))
    ax.text(
        0,
        0.4,
        "{:.1f}".format(float(speed)),
        ha="center",
        va="center",
        fontsize=28,
        color=to_rgba(config.text_color, 1.0),
        fontweight="bold",
    )
    ax.text(
        0,
        0.25,
        format_speed_unit(config.speed_output_unit),
        ha="center",
        va="center",
        fontsize=11,
        color=to_rgba(config.text_color, 0.75),
    )

    if state is not None and show_top_speed:
        _draw_top_speed_indicator(ax, state, config)


def default_output_name(export_mode: str, extension: str) -> str:
    extension = extension.lstrip(".")
    return "telemetry_{}_overlay.{}".format(export_mode, extension)


def _validate_config(config: RenderConfig) -> None:
    if config.export_mode not in VALID_EXPORT_MODES:
        raise ValueError("export_mode must be one of: {}".format(", ".join(VALID_EXPORT_MODES)))
    if config.fps <= 0:
        raise ValueError("fps must be greater than 0")
    if config.seconds_between_gps_points <= 0:
        raise ValueError("seconds_between_gps_points must be greater than 0")
    if config.start_time < 0:
        raise ValueError("start_time must be greater than or equal to 0")
    if config.end_time is not None and config.end_time <= config.start_time:
        raise ValueError("end_time must be greater than start_time")
    if int(config.output_width) <= 0 or int(config.output_height) <= 0:
        raise ValueError("output_width and output_height must be positive integers")
    convert_speed(0, config.speed_input_unit, config.speed_output_unit)


def _find_column(columns: Iterable[str], preferred: str, keywords: Tuple[str, ...]) -> Optional[str]:
    column_list = list(columns)
    if preferred in column_list:
        return preferred

    normalized_preferred = _normalize_column(preferred)
    for column in column_list:
        if _normalize_column(column) == normalized_preferred:
            return column

    for keyword in keywords:
        for column in column_list:
            if keyword in _normalize_column(column):
                return column

    return None


def _require_column(df: pd.DataFrame, preferred: str, keywords: Tuple[str, ...], label: str) -> str:
    column = _find_column(df.columns, preferred, keywords)
    if not column:
        raise ValueError("{} column was not found. Choose the correct column in the app settings.".format(label))
    return column


def _normalize_column(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _resolve_max_speed(speed_series: pd.Series, requested_max_speed: Optional[float]) -> float:
    if requested_max_speed is not None and requested_max_speed > 0:
        return float(requested_max_speed)

    top_speed = float(pd.to_numeric(speed_series, errors="coerce").fillna(0).max())
    if top_speed <= 0:
        return 5.0
    return float(max(5, int(math.ceil(top_speed / 5.0) * 5)))


def _trim_frames(
    frame_x: np.ndarray,
    frame_y: np.ndarray,
    frame_speed: np.ndarray,
    frame_heading: np.ndarray,
    frame_altitude: np.ndarray,
    fps: int,
    start_time: float,
    end_time: Optional[float],
    total_duration_seconds: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    if len(frame_x) <= 1 or total_duration_seconds <= 0:
        return frame_x, frame_y, frame_speed, frame_heading, frame_altitude, 0.0, 0.0

    start = min(max(0.0, float(start_time)), total_duration_seconds)
    end = total_duration_seconds if end_time is None else min(float(end_time), total_duration_seconds)
    if start >= total_duration_seconds:
        raise ValueError("Start time must be before the end of the telemetry data.")
    if end <= start:
        raise ValueError("End time must be after start time.")

    start_frame = max(0, min(len(frame_x) - 1, int(math.floor(start * fps))))
    end_frame = max(start_frame, min(len(frame_x) - 1, int(math.ceil(end * fps))))
    if end_frame == start_frame and end_frame < len(frame_x) - 1:
        end_frame += 1

    return (
        frame_x[start_frame : end_frame + 1],
        frame_y[start_frame : end_frame + 1],
        frame_speed[start_frame : end_frame + 1],
        frame_heading[start_frame : end_frame + 1],
        frame_altitude[start_frame : end_frame + 1],
        start_frame / float(fps),
        end_frame / float(fps),
    )


def _frame_bounds(frame_x: np.ndarray, frame_y: np.ndarray, padding: float) -> Tuple[float, float, float, float]:
    xmin = float(np.min(frame_x)) - padding
    xmax = float(np.max(frame_x)) + padding
    ymin = float(np.min(frame_y)) - padding
    ymax = float(np.max(frame_y)) + padding
    return xmin, xmax, ymin, ymax


def _smooth_frames(
    df: pd.DataFrame,
    fps: int,
    seconds_between_points: float,
    heading_col: Optional[str],
    altitude_col: Optional[str],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if len(df) == 1:
        return (
            df["x"].to_numpy(dtype=float),
            df["y"].to_numpy(dtype=float),
            df["speed_converted"].to_numpy(dtype=float),
            _column_or_zeros(df, heading_col),
            _column_or_zeros(df, altitude_col),
        )

    frame_x = []
    frame_y = []
    frame_speed = []
    frame_heading = []
    frame_altitude = []
    interp_steps = max(1, int(round(fps * seconds_between_points)))

    for index in range(len(df) - 1):
        x0, x1 = float(df["x"].iloc[index]), float(df["x"].iloc[index + 1])
        y0, y1 = float(df["y"].iloc[index]), float(df["y"].iloc[index + 1])
        s0 = float(df["speed_converted"].iloc[index])
        s1 = float(df["speed_converted"].iloc[index + 1])
        h0, h1 = _pair_value(df, heading_col, index)
        a0, a1 = _pair_value(df, altitude_col, index)

        for step in range(interp_steps):
            t = step / interp_steps
            eased_t = _smoothstep(t)
            frame_x.append(x0 + (x1 - x0) * eased_t)
            frame_y.append(y0 + (y1 - y0) * eased_t)
            frame_speed.append(s0 + (s1 - s0) * t)
            frame_heading.append(h0 + (h1 - h0) * t)
            frame_altitude.append(a0 + (a1 - a0) * t)

    frame_x.append(float(df["x"].iloc[-1]))
    frame_y.append(float(df["y"].iloc[-1]))
    frame_speed.append(float(df["speed_converted"].iloc[-1]))
    frame_heading.append(_numeric_cell(df, heading_col, -1))
    frame_altitude.append(_numeric_cell(df, altitude_col, -1))

    return (
        np.asarray(frame_x, dtype=float),
        np.asarray(frame_y, dtype=float),
        np.asarray(frame_speed, dtype=float),
        np.asarray(frame_heading, dtype=float),
        np.asarray(frame_altitude, dtype=float),
    )


def _smoothstep(t: float) -> float:
    return t * t * (3 - 2 * t)


def _pair_value(df: pd.DataFrame, column: Optional[str], index: int) -> Tuple[float, float]:
    return _numeric_cell(df, column, index), _numeric_cell(df, column, index + 1)


def _numeric_cell(df: pd.DataFrame, column: Optional[str], index: int) -> float:
    if not column:
        return 0.0
    value = pd.to_numeric(df[column].iloc[index], errors="coerce")
    if pd.isna(value):
        return 0.0
    return float(value)


def _column_or_zeros(df: pd.DataFrame, column: Optional[str]) -> np.ndarray:
    if not column:
        return np.zeros(len(df), dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(0).to_numpy(dtype=float)


def _build_composition(data: TelemetryData, config: RenderConfig) -> Tuple[object, CompositionArtists]:
    canvas = canvas_from_config(config)
    layout = resolve_overlay_layout(config)
    facecolor = (0, 0, 0, 0) if config.transparent else to_rgba(config.background_color)
    dpi = 100
    fig = plt.figure(figsize=(canvas.width / dpi, canvas.height / dpi), dpi=dpi, facecolor=facecolor)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    bounds = compute_layout_bounds(layout, canvas, config)
    artists = CompositionArtists()

    if bounds["map"].visible:
        artists.ax_map = fig.add_axes(_bounds_to_axes_rect(bounds["map"], canvas))
        artists.map_artists = _setup_map_artists(artists.ax_map, data, config)

    if bounds["speedometer"].visible:
        artists.ax_speedometer = fig.add_axes(_bounds_to_axes_rect(bounds["speedometer"], canvas))

    if bounds["top_speed"].visible:
        artists.ax_top_speed = fig.add_axes(_bounds_to_axes_rect(bounds["top_speed"], canvas))
        _configure_text_axis(artists.ax_top_speed, config)

    if bounds["furthest_distance"].visible:
        artists.ax_furthest_distance = fig.add_axes(_bounds_to_axes_rect(bounds["furthest_distance"], canvas))
        _configure_text_axis(artists.ax_furthest_distance, config)

    return fig, artists


def _update_composition(
    artists: CompositionArtists,
    data: TelemetryData,
    config: RenderConfig,
    frame: int,
    state: FrameVisualState,
) -> list:
    changed_artists = []

    if artists.ax_map is not None and artists.map_artists is not None:
        _update_map_artists(artists.map_artists, data, frame, state)
        changed_artists.extend(
            [
                artists.map_artists.trail_line,
                artists.map_artists.start_marker,
                artists.map_artists.dot,
            ]
        )

    if artists.ax_speedometer is not None:
        draw_speedometer(artists.ax_speedometer, state.current_speed, data.max_speed, config, state=None, show_top_speed=False)
        changed_artists.extend(artists.ax_speedometer.patches)
        changed_artists.extend(artists.ax_speedometer.lines)
        changed_artists.extend(artists.ax_speedometer.texts)

    if artists.ax_top_speed is not None:
        changed_artists.extend(_draw_record_indicator(
            artists.ax_top_speed,
            "TOP SPEED",
            "{:.1f} {}".format(state.top_speed, format_speed_unit(config.speed_output_unit)),
            state.top_speed_highlight,
            config,
        ))

    if artists.ax_furthest_distance is not None:
        changed_artists.extend(_draw_record_indicator(
            artists.ax_furthest_distance,
            "FURTHEST DISTANCE",
            format_distance(state.furthest_distance_m, config.speed_output_unit),
            state.distance_highlight,
            config,
        ))

    return changed_artists


def _build_figure(data: TelemetryData, config: RenderConfig):
    facecolor = (0, 0, 0, 0) if config.transparent else to_rgba(config.background_color)

    if config.export_mode == "both":
        fig = plt.figure(figsize=(12, 6), facecolor=facecolor)
        ax_map = fig.add_subplot(1, 2, 1)
        ax_speed = fig.add_subplot(1, 2, 2)
    elif config.export_mode == "map":
        fig, ax_map = plt.subplots(figsize=(8, 8), facecolor=facecolor)
        ax_speed = None
    else:
        fig, ax_speed = plt.subplots(figsize=(6, 4), facecolor=facecolor)
        ax_map = None

    if ax_map is not None:
        _configure_map_axis(ax_map, data, config)

    return fig, ax_map, ax_speed


def _configure_map_axis(ax_map, data: TelemetryData, config: RenderConfig) -> None:
    xmin, xmax, ymin, ymax = data.bounds
    ax_map.set_xlim(xmin, xmax)
    ax_map.set_ylim(ymin, ymax)
    ax_map.set_aspect("equal", adjustable="box")
    ax_map.set_facecolor((0, 0, 0, 0) if config.transparent else to_rgba(config.background_color))
    ax_map.axis("off")


def _setup_map_artists(ax_map, data: TelemetryData, config: RenderConfig):
    _configure_map_axis(ax_map, data, config)
    trail_line, = ax_map.plot([], [], linewidth=4, color=to_rgba(config.path_color, 0.85), zorder=1)
    start_marker, = ax_map.plot(
        [data.frame_x[0]],
        [data.frame_y[0]],
        marker="*",
        linestyle="None",
        markersize=20,
        markeredgewidth=0,
        color=to_rgba(config.start_marker_color, 1.0),
        zorder=3,
    )
    dot, = ax_map.plot([], [], "o", markersize=14, color=to_rgba(config.dot_color, 1.0), zorder=4)
    return MapArtists(trail_line, start_marker, dot)


def _update_map_artists(
    artists: MapArtists,
    data: TelemetryData,
    frame: int,
    state: FrameVisualState,
) -> None:
    artists.trail_line.set_data(data.frame_x[: frame + 1], data.frame_y[: frame + 1])
    artists.start_marker.set_data([data.frame_x[0]], [data.frame_y[0]])
    artists.dot.set_data([state.current_x], [state.current_y])


def _draw_top_speed_indicator(ax, state: FrameVisualState, config: RenderConfig) -> None:
    title = ax.text(
        0,
        -0.33,
        "TOP SPEED",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
    )
    value = ax.text(
        0,
        -0.48,
        "{:.1f} {}".format(state.top_speed, format_speed_unit(config.speed_output_unit)),
        ha="center",
        va="center",
        fontsize=16,
        fontweight="bold",
    )
    _update_record_texts(
        title,
        value,
        "TOP SPEED",
        "{:.1f} {}".format(state.top_speed, format_speed_unit(config.speed_output_unit)),
        state.top_speed_highlight,
        config,
    )


def _update_record_texts(title_text, value_text, title: str, value: str, highlighted: bool, config: RenderConfig) -> None:
    alpha = 1.0 if highlighted else 0.5
    color = RECORD_HIGHLIGHT_COLOR if highlighted else config.text_color
    rgba = to_rgba(color, alpha)
    title_text.set_text(title)
    title_text.set_color(rgba)
    value_text.set_text(value)
    value_text.set_color(rgba)


def _draw_record_indicator(ax, title: str, value: str, highlighted: bool, config: RenderConfig) -> list:
    ax.clear()
    _configure_text_axis(ax, config)
    title_text = ax.text(
        0.5,
        0.66,
        title,
        ha="center",
        va="center",
        fontsize=18,
        fontweight="bold",
        transform=ax.transAxes,
    )
    value_text = ax.text(
        0.5,
        0.31,
        value,
        ha="center",
        va="center",
        fontsize=30,
        fontweight="bold",
        transform=ax.transAxes,
    )
    _update_record_texts(title_text, value_text, title, value, highlighted, config)
    return [title_text, value_text]


def _configure_text_axis(ax, config: RenderConfig) -> None:
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_facecolor((0, 0, 0, 0) if config.transparent else to_rgba(config.background_color))


def _finalize_figure(fig) -> None:
    fig.tight_layout(pad=0.25)
    fig.subplots_adjust(bottom=0.18)


def _element_layout_to_dict(element: ElementLayout) -> dict:
    return {"x": float(element.x), "y": float(element.y), "visible": bool(element.visible)}


def _element_size(name: str, canvas: CanvasConfig) -> Tuple[float, float]:
    width = float(canvas.width)
    height = float(canvas.height)
    aspect = width / max(1.0, height)

    if name == "map":
        if aspect >= 1.2:
            return width * 0.42, height * 0.62
        if aspect <= 0.85:
            return width * 0.82, height * 0.34
        return width * 0.58, height * 0.48

    if name == "speedometer":
        if aspect >= 1.2:
            return width * 0.34, height * 0.42
        if aspect <= 0.85:
            return width * 0.76, height * 0.28
        return width * 0.42, height * 0.34

    if name == "top_speed":
        return min(width * 0.38, 640.0), max(86.0, min(height * 0.13, 150.0))

    if name == "furthest_distance":
        return min(width * 0.42, 700.0), max(86.0, min(height * 0.13, 150.0))

    raise ValueError("Unknown layout element: {}".format(name))


def _bounds_to_axes_rect(bounds: ElementBounds, canvas: CanvasConfig) -> list[float]:
    return [
        bounds.left / canvas.width,
        1.0 - (bounds.top + bounds.height) / canvas.height,
        bounds.width / canvas.width,
        bounds.height / canvas.height,
    ]


def _box_visibility(box: ElementBounds, canvas: CanvasConfig) -> str:
    outside = box.right <= 0 or box.left >= canvas.width or box.bottom <= 0 or box.top >= canvas.height
    if outside:
        return "outside"
    partial = box.left < 0 or box.top < 0 or box.right > canvas.width or box.bottom > canvas.height
    if partial:
        return "partial"
    return "inside"


def _boxes_overlap(first: ElementBounds, second: ElementBounds) -> bool:
    return not (
        first.right <= second.left
        or first.left >= second.right
        or first.bottom <= second.top
        or first.top >= second.bottom
    )


def _element_label(name: str) -> str:
    return {
        "map": "Map",
        "speedometer": "Speedometer",
        "top_speed": "Top-speed indicator",
        "furthest_distance": "Furthest-distance indicator",
    }[name]


def _nice_tick_step(max_speed: float) -> int:
    if max_speed <= 30:
        return 5
    if max_speed <= 80:
        return 10
    return 20


def _configure_ffmpeg() -> None:
    try:
        import imageio_ffmpeg

        matplotlib.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass


def _build_writer(output: Path, config: RenderConfig):
    if output.suffix.lower() == ".mov":
        return FFMpegWriter(
            fps=config.fps,
            codec="prores_ks",
            extra_args=["-pix_fmt", "yuva444p10le", "-profile:v", "4444"],
        )
    return FFMpegWriter(fps=config.fps, bitrate=3000)
