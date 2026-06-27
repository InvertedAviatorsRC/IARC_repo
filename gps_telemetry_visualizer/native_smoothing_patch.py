from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd

from gps_telemetry_visualizer import core


_PATCHED = False
_ORIGINAL_SMOOTH_FRAMES = None


def install() -> None:
    """Patch telemetry interpolation so repeated GPS rows still render as continuous motion."""
    global _PATCHED, _ORIGINAL_SMOOTH_FRAMES
    if _PATCHED:
        return
    _ORIGINAL_SMOOTH_FRAMES = core._smooth_frames
    core._smooth_frames = _smooth_frames_continuous
    _PATCHED = True


def _smooth_frames_continuous(
    df: pd.DataFrame,
    fps: int,
    seconds_between_points: float,
    heading_col: Optional[str],
    altitude_col: Optional[str],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if len(df) <= 1:
        return _ORIGINAL_SMOOTH_FRAMES(df, fps, seconds_between_points, heading_col, altitude_col)

    source_time = np.arange(len(df), dtype=float) * float(seconds_between_points)
    total_duration = float(source_time[-1])
    if total_duration <= 0:
        return _ORIGINAL_SMOOTH_FRAMES(df, fps, seconds_between_points, heading_col, altitude_col)

    x = df["x"].to_numpy(dtype=float)
    y = df["y"].to_numpy(dtype=float)
    speed = df["speed_converted"].to_numpy(dtype=float)
    heading = core._column_or_zeros(df, heading_col)
    altitude = core._column_or_zeros(df, altitude_col)

    key_indices = _meaningful_key_indices(x, y, speed, heading, altitude)
    key_time = source_time[key_indices]
    frame_count = max(2, int(round(total_duration * float(fps))) + 1)
    frame_time = np.linspace(0.0, total_duration, frame_count)

    return (
        _smooth_interpolate(key_time, x[key_indices], frame_time),
        _smooth_interpolate(key_time, y[key_indices], frame_time),
        np.interp(frame_time, key_time, speed[key_indices]),
        np.interp(frame_time, key_time, heading[key_indices]),
        np.interp(frame_time, key_time, altitude[key_indices]),
    )


def _meaningful_key_indices(
    x: np.ndarray,
    y: np.ndarray,
    speed: np.ndarray,
    heading: np.ndarray,
    altitude: np.ndarray,
) -> np.ndarray:
    changed = np.zeros(len(x), dtype=bool)
    changed[0] = True
    changed[-1] = True

    changed[1:] |= np.abs(np.diff(x)) > 1e-6
    changed[1:] |= np.abs(np.diff(y)) > 1e-6
    changed[1:] |= np.abs(np.diff(speed)) > 1e-6
    changed[1:] |= np.abs(np.diff(heading)) > 1e-6
    changed[1:] |= np.abs(np.diff(altitude)) > 1e-6

    key_indices = np.flatnonzero(changed)
    if len(key_indices) < 2:
        return np.array([0, len(x) - 1], dtype=int)
    return key_indices


def _smooth_interpolate(key_time: np.ndarray, values: np.ndarray, frame_time: np.ndarray) -> np.ndarray:
    if len(key_time) < 2:
        return np.full_like(frame_time, float(values[0]), dtype=float)

    result = np.empty_like(frame_time, dtype=float)
    segment = np.searchsorted(key_time, frame_time, side="right") - 1
    segment = np.clip(segment, 0, len(key_time) - 2)

    t0 = key_time[segment]
    t1 = key_time[segment + 1]
    v0 = values[segment]
    v1 = values[segment + 1]
    duration = np.maximum(t1 - t0, 1e-9)
    local_t = np.clip((frame_time - t0) / duration, 0.0, 1.0)
    eased_t = local_t * local_t * (3.0 - 2.0 * local_t)
    return v0 + (v1 - v0) * eased_t
