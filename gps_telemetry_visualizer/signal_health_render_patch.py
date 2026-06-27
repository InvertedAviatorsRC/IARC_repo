from __future__ import annotations

import math

import matplotlib.patches as patches

from gps_telemetry_visualizer import core
from gps_telemetry_visualizer.signal_health_data_patch import empty_signal_data
from gps_telemetry_visualizer.signal_health_layout_patch import NAME, ensure_signal_layout

_INSTALLED = False
_ORIGINAL_BUILD = None
_ORIGINAL_UPDATE = None


def install() -> None:
    global _INSTALLED, _ORIGINAL_BUILD, _ORIGINAL_UPDATE
    if _INSTALLED:
        return
    _ORIGINAL_BUILD = core._build_composition
    _ORIGINAL_UPDATE = core._update_composition
    core._build_composition = build_composition
    core._update_composition = update_composition
    _INSTALLED = True


def build_composition(data, config):
    fig, artists = _ORIGINAL_BUILD(data, config)
    if not getattr(config, "show_signal_health", False):
        return fig, artists
    canvas = core.canvas_from_config(config)
    layout = ensure_signal_layout(core.resolve_overlay_layout(config), canvas.width, canvas.height)
    box = core.compute_layout_bounds(layout, canvas, config).get(NAME)
    if box is not None and box.visible:
        artists.ax_signal_health = fig.add_axes(core._bounds_to_axes_rect(box, canvas))
        artists.ax_signal_health._element_scale = box.scale
        core._configure_text_axis(artists.ax_signal_health, config)
    return fig, artists


def update_composition(artists, data, config, frame, state):
    changed = _ORIGINAL_UPDATE(artists, data, config, frame, state)
    ax = getattr(artists, "ax_signal_health", None)
    if ax is not None and getattr(config, "show_signal_health", False):
        changed.extend(draw_signal_bars(ax, data, config, frame))
    return changed


def draw_signal_bars(ax, data, config, frame):
    sig = getattr(data, "signal_health", empty_signal_data(len(data.frame_x)))
    frame = max(0, min(int(frame), len(data.frame_x) - 1))
    scale = core._axis_element_scale(ax)
    ax.clear()
    ax._element_scale = scale
    core._configure_text_axis(ax, config)
    ax.add_patch(
        patches.FancyBboxPatch(
            (0.02, 0.04), 0.96, 0.90,
            boxstyle="round,pad=0.03,rounding_size=0.06",
            transform=ax.transAxes,
            linewidth=1.2 * scale,
            edgecolor=core.to_rgba(config.text_color, 0.24),
            facecolor=core.to_rgba("#050912", 0.42 if config.transparent else 0.72),
        )
    )
    ax.text(0.08, 0.84, "SIGNAL", ha="left", va="center", fontsize=13 * scale, fontweight="bold", color=core.to_rgba(config.text_color, 0.95), transform=ax.transAxes)
    white = getattr(config, "signal_bars_color_mode", "color") == "white"
    rows = [
        ("LQ", value(sig.lq, frame), 0, 100, "%", False),
        ("RSSI", value(sig.rssi, frame), -120, -40, " dB", False),
        ("SNR", value(sig.snr, frame), -10, 20, " dB", False),
        ("TX", value(sig.power, frame), 0, 1000, " mW", True),
    ]
    for row, y in zip(rows, [0.64, 0.48, 0.32, 0.16]):
        draw_bar(ax, row[0], row[1], row[2], row[3], row[4], row[5], y, config, scale, white)
    return list(ax.texts) + list(ax.patches)


def draw_bar(ax, label, val, lo, hi, suffix, log_scale, y, config, scale, white):
    frac = fraction(val, lo, hi, log_scale)
    bar_color = core.to_rgba(config.text_color, 0.92) if white else core.to_rgba(metric_color(label, val), 0.95)
    ax.text(0.08, y, label, ha="left", va="center", fontsize=10 * scale, fontweight="bold", color=core.to_rgba(config.text_color, 0.82), transform=ax.transAxes)
    ax.add_patch(patches.FancyBboxPatch((0.28, y - 0.035), 0.42, 0.07, boxstyle="round,pad=0.01,rounding_size=0.025", transform=ax.transAxes, linewidth=0, facecolor=core.to_rgba(config.text_color, 0.17)))
    ax.add_patch(patches.FancyBboxPatch((0.28, y - 0.035), 0.42 * frac, 0.07, boxstyle="round,pad=0.01,rounding_size=0.025", transform=ax.transAxes, linewidth=0, facecolor=bar_color))
    ax.text(0.76, y, format_metric(val, suffix), ha="left", va="center", fontsize=10 * scale, fontweight="bold", color=core.to_rgba(config.text_color, 0.92), transform=ax.transAxes)


def value(values, frame):
    if len(values) == 0:
        return float("nan")
    return float(values[max(0, min(frame, len(values) - 1))])


def fraction(val, lo, hi, log_scale):
    if not math.isfinite(val):
        return 0.0
    if log_scale:
        val = math.log10(max(0, val) + 1)
        lo = math.log10(max(0, lo) + 1)
        hi = math.log10(max(0, hi) + 1)
    return max(0.0, min(1.0, (val - lo) / max(1e-9, hi - lo)))


def metric_color(label, val):
    if not math.isfinite(val):
        return "#64748b"
    if label == "LQ":
        return "#22c55e" if val >= 90 else "#facc15" if val >= 70 else "#ff3355"
    if label == "RSSI":
        return "#22c55e" if val >= -80 else "#facc15" if val >= -100 else "#ff3355"
    if label == "SNR":
        return "#22c55e" if val >= 8 else "#facc15" if val >= 0 else "#ff3355"
    return "#38bdf8"


def format_metric(val, suffix):
    if not math.isfinite(val):
        return "--"
    if suffix == "%":
        return "{:.0f}%".format(val)
    if suffix == " mW":
        return "{:.0f} mW".format(val)
    return "{:.0f}{}".format(val, suffix)
