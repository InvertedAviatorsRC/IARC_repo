from __future__ import annotations

import io
import math
import os
import re
import tempfile
from dataclasses import dataclass, replace
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
    speedometer_color: str = "#00d5ff"
    needle_color: str = "#ff3355"
    text_color: str = "#ffffff"
    background_color: str = "#101820"
    transparent: bool = True
    padding: float = 10.0
    start_time: float = 0.0
    end_time: Optional[float] = None


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


def render_static_preview(csv_source, config: RenderConfig, frame_fraction: float = 0.65, frame_time: Optional[float] = None):
    data = prepare_telemetry(csv_source, config)
    fig, ax_map, ax_speed = _build_figure(data, config)
    if frame_time is None:
        frame = int(len(data.frame_x) * frame_fraction)
    else:
        frame = int(round(max(0.0, frame_time) * config.fps))
    frame = max(0, min(len(data.frame_x) - 1, frame))

    if ax_map is not None:
        line, dot = _setup_map_artists(ax_map, data, config)
        line.set_data(data.frame_x[: frame + 1], data.frame_y[: frame + 1])
        dot.set_data([data.frame_x[frame]], [data.frame_y[frame]])

    if ax_speed is not None:
        draw_speedometer(ax_speed, data.frame_speed[frame], data.max_speed, config)

    fig.tight_layout(pad=0.2)
    return fig


def render_preview_frames(csv_source, config: RenderConfig, frame_count: int = 28, dpi: int = 110) -> Tuple[list[bytes], TelemetryData]:
    data = prepare_telemetry(csv_source, config)
    fig, ax_map, ax_speed = _build_figure(data, config)
    trail_line = dot = None
    if ax_map is not None:
        trail_line, dot = _setup_map_artists(ax_map, data, config)

    frame_count = max(1, min(int(frame_count), len(data.frame_x)))
    frame_indexes = np.linspace(0, len(data.frame_x) - 1, frame_count, dtype=int)
    rendered_frames = []

    for frame in frame_indexes:
        if ax_map is not None:
            trail_line.set_data(data.frame_x[: frame + 1], data.frame_y[: frame + 1])
            dot.set_data([data.frame_x[frame]], [data.frame_y[frame]])

        if ax_speed is not None:
            draw_speedometer(ax_speed, data.frame_speed[frame], data.max_speed, config)

        fig.tight_layout(pad=0.2)
        buffer = io.BytesIO()
        fig.savefig(
            buffer,
            format="png",
            dpi=dpi,
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
    output.parent.mkdir(parents=True, exist_ok=True)

    _configure_ffmpeg()

    fig, ax_map, ax_speed = _build_figure(data, config)
    trail_line = dot = None
    if ax_map is not None:
        trail_line, dot = _setup_map_artists(ax_map, data, config)

    def update(frame):
        artists = []

        if ax_map is not None:
            trail_line.set_data(data.frame_x[: frame + 1], data.frame_y[: frame + 1])
            dot.set_data([data.frame_x[frame]], [data.frame_y[frame]])
            artists.extend([trail_line, dot])

        if ax_speed is not None:
            draw_speedometer(ax_speed, data.frame_speed[frame], data.max_speed, config)
            artists.extend(ax_speed.patches)
            artists.extend(ax_speed.lines)
            artists.extend(ax_speed.texts)

        if progress_callback:
            progress_callback(frame + 1, len(data.frame_x))

        return artists

    animation = FuncAnimation(
        fig,
        update,
        frames=len(data.frame_x),
        interval=1000 / config.fps,
        blit=False,
    )

    writer = _build_writer(output, config)
    savefig_kwargs = {"transparent": config.transparent} if output.suffix.lower() == ".mov" else {}
    animation.save(str(output), writer=writer, savefig_kwargs=savefig_kwargs)
    plt.close(fig)
    return output


def draw_speedometer(ax, speed: float, max_speed: float, config: RenderConfig) -> None:
    ax.clear()
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-0.35, 1.25)
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
        config.speed_output_unit.upper(),
        ha="center",
        va="center",
        fontsize=11,
        color=to_rgba(config.text_color, 0.75),
    )


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
    trail_line, = ax_map.plot([], [], linewidth=4, color=to_rgba(config.path_color, 0.85))
    dot, = ax_map.plot([], [], "o", markersize=14, color=to_rgba(config.dot_color, 1.0))
    return trail_line, dot


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
