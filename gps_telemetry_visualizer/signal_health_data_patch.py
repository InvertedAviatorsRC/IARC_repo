from __future__ import annotations

import numpy as np
import pandas as pd

from gps_telemetry_visualizer import core


_ORIGINAL_PREPARE = None
_INSTALLED = False


class SignalData:
    def __init__(self, lq, rssi, snr, power):
        self.lq = lq
        self.rssi = rssi
        self.snr = snr
        self.power = power


def install() -> None:
    global _ORIGINAL_PREPARE, _INSTALLED
    if _INSTALLED:
        return
    _ORIGINAL_PREPARE = core.prepare_telemetry
    core.prepare_telemetry = prepare_telemetry
    _INSTALLED = True


def prepare_telemetry(csv_source, config):
    data = _ORIGINAL_PREPARE(csv_source, config)
    try:
        df = pd.read_csv(csv_source)
        gps_col = core._require_column(df, config.gps_col, ("gps",), "GPS")
        parsed = df[gps_col].apply(lambda value: pd.Series(core.parse_gps(value), index=["lat", "lon"]))
        df = pd.concat([df, parsed], axis=1).dropna(subset=["lat", "lon"]).reset_index(drop=True)
        data.signal_health = build_signal_data(df, data)
    except Exception:
        data.signal_health = empty_signal_data(len(data.frame_x))
    return data


def build_signal_data(df, data):
    frame_count = len(data.frame_x)
    if len(df) == 0 or frame_count == 0:
        return empty_signal_data(frame_count)
    source_time = np.linspace(0.0, float(data.total_duration_seconds), len(df))
    frame_time = np.linspace(0.0, float(data.total_duration_seconds), frame_count)
    lq = interp(df, frame_time, source_time, find_column(df, ["RQly(%)", "RQLY", "linkquality", "lq"]))
    rssi_1 = interp(df, frame_time, source_time, find_column(df, ["1RSS(dB)", "1RSS", "rssi1"]))
    rssi_2 = interp(df, frame_time, source_time, find_column(df, ["2RSS(dB)", "2RSS", "rssi2"]))
    rssi = np.fmax(rssi_1, rssi_2)
    snr = interp(df, frame_time, source_time, find_column(df, ["RSNR(dB)", "RSNR", "snr"]))
    power = interp(df, frame_time, source_time, find_column(df, ["TPWR(mW)", "TPWR", "txpower"]))
    return SignalData(lq, rssi, snr, power)


def empty_signal_data(frame_count):
    empty = np.full(max(0, int(frame_count)), np.nan, dtype=float)
    return SignalData(empty.copy(), empty.copy(), empty.copy(), empty.copy())


def find_column(df, candidates):
    columns = list(df.columns)
    normalized = {core._normalize_column(column): column for column in columns}
    for candidate in candidates:
        key = core._normalize_column(candidate)
        if key in normalized:
            return normalized[key]
    for candidate in candidates:
        key = core._normalize_column(candidate)
        for column in columns:
            if key and key in core._normalize_column(column):
                return column
    return None


def interp(df, frame_time, source_time, column):
    if not column:
        return np.full(len(frame_time), np.nan, dtype=float)
    values = pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(values)
    if not np.any(valid):
        return np.full(len(frame_time), np.nan, dtype=float)
    return np.interp(frame_time, source_time[valid], values[valid])
