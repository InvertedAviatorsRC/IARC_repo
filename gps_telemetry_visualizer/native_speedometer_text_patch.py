from __future__ import annotations

from typing import Optional

from gps_telemetry_visualizer import core
from gps_telemetry_visualizer import native_speedometer_patch as speedometer_patch


def setup(native_app) -> None:
    """Install native speedometer options and tune corner speed readout placement."""
    speedometer_patch.install()
    speedometer_patch.extend_native_app(native_app)
    speedometer_patch._draw_corner_right_speedometer = _draw_corner_right_speedometer
    speedometer_patch._draw_corner_left_speedometer = _draw_corner_left_speedometer


def _draw_corner_right_speedometer(
    ax,
    speed: float,
    max_speed: float,
    config: core.RenderConfig,
    state: Optional[core.FrameVisualState],
    show_top_speed: bool,
) -> None:
    _draw_corner_speedometer(
        ax,
        speed,
        max_speed,
        config,
        state,
        show_top_speed,
        xlim=(-1.15, 0.2),
        theta1=90,
        theta2=180,
        start_angle=180.0,
        angle_direction=-1.0,
        speed_text_x=-0.32,
        speed_value_y=0.20,
        speed_unit_y=0.08,
    )


def _draw_corner_left_speedometer(
    ax,
    speed: float,
    max_speed: float,
    config: core.RenderConfig,
    state: Optional[core.FrameVisualState],
    show_top_speed: bool,
) -> None:
    _draw_corner_speedometer(
        ax,
        speed,
        max_speed,
        config,
        state,
        show_top_speed,
        xlim=(-0.2, 1.15),
        theta1=0,
        theta2=90,
        start_angle=0.0,
        angle_direction=1.0,
        speed_text_x=0.32,
        speed_value_y=0.20,
        speed_unit_y=0.08,
    )


def _draw_corner_speedometer(
    ax,
    speed: float,
    max_speed: float,
    config: core.RenderConfig,
    state: Optional[core.FrameVisualState],
    show_top_speed: bool,
    xlim: tuple[float, float],
    theta1: float,
    theta2: float,
    start_angle: float,
    angle_direction: float,
    speed_text_x: float,
    speed_value_y: float,
    speed_unit_y: float,
) -> None:
    element_scale = core._axis_element_scale(ax)
    tick_font_scale = speedometer_patch._tick_font_scale(config)
    ax.clear()
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(*xlim)
    ax.set_ylim(-0.25, 1.15)
    ax.set_facecolor((0, 0, 0, 0) if config.transparent else core.to_rgba(config.background_color))

    ax.add_patch(
        core.patches.Arc(
            (0, 0),
            2,
            2,
            theta1=theta1,
            theta2=theta2,
            linewidth=6 * element_scale,
            color=core.to_rgba(config.speedometer_color, 0.78),
        )
    )

    tick_step = core._nice_tick_step(max_speed)
    text_color = core.to_rgba(config.text_color, 0.92)
    sweep = 90.0

    for tick in core.np.arange(0, max_speed + tick_step, tick_step):
        tick = min(tick, max_speed)
        angle = core.math.radians(start_angle + angle_direction * (tick / max_speed) * sweep)
        x_outer = core.math.cos(angle)
        y_outer = core.math.sin(angle)
        x_inner = 0.84 * core.math.cos(angle)
        y_inner = 0.84 * core.math.sin(angle)
        ax.plot(
            [x_inner, x_outer],
            [y_inner, y_outer],
            linewidth=2 * element_scale,
            color=core.to_rgba(config.text_color, 0.72),
        )
        ax.text(
            0.68 * core.math.cos(angle),
            0.68 * core.math.sin(angle),
            str(int(round(tick))),
            ha="center",
            va="center",
            fontsize=8 * element_scale * tick_font_scale,
            color=text_color,
        )

    clamped_speed = max(0.0, min(float(speed), max_speed))
    needle_angle = core.math.radians(start_angle + angle_direction * (clamped_speed / max_speed) * sweep)
    ax.plot(
        [0, 0.76 * core.math.cos(needle_angle)],
        [0, 0.76 * core.math.sin(needle_angle)],
        linewidth=4 * element_scale,
        color=core.to_rgba(config.needle_color, 1.0),
    )
    ax.add_patch(core.patches.Circle((0, 0), 0.06, color=core.to_rgba(config.text_color, 1.0)))
    ax.text(
        speed_text_x,
        speed_value_y,
        "{:.1f}".format(float(speed)),
        ha="center",
        va="center",
        fontsize=22 * element_scale,
        color=core.to_rgba(config.text_color, 1.0),
        fontweight="bold",
    )
    ax.text(
        speed_text_x,
        speed_unit_y,
        core.format_speed_unit(config.speed_output_unit),
        ha="center",
        va="center",
        fontsize=9 * element_scale * tick_font_scale,
        color=core.to_rgba(config.text_color, 0.75),
    )

    if state is not None and show_top_speed:
        core._draw_top_speed_indicator(ax, state, config)
