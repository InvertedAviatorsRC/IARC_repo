from __future__ import annotations

from typing import Optional

from gps_telemetry_visualizer import core


_PATCHED = False
_ORIGINAL_DRAW_SPEEDOMETER = None


def install() -> None:
    """Register native-only speedometer variants that are still backed by core rendering."""
    global _PATCHED, _ORIGINAL_DRAW_SPEEDOMETER

    if "corner_left" not in core.VALID_SPEEDOMETER_STYLES:
        core.VALID_SPEEDOMETER_STYLES = (*core.VALID_SPEEDOMETER_STYLES, "corner_left")

    if _PATCHED:
        return

    _ORIGINAL_DRAW_SPEEDOMETER = core.draw_speedometer

    def _draw_speedometer(
        ax,
        speed: float,
        max_speed: float,
        config: core.RenderConfig,
        state: Optional[core.FrameVisualState] = None,
        show_top_speed: bool = True,
    ) -> None:
        if config.speedometer_style == "corner_left":
            _draw_corner_left_speedometer(ax, speed, max_speed, config, state, show_top_speed)
            return
        _ORIGINAL_DRAW_SPEEDOMETER(ax, speed, max_speed, config, state, show_top_speed)

    core.draw_speedometer = _draw_speedometer
    _PATCHED = True


def _draw_corner_left_speedometer(
    ax,
    speed: float,
    max_speed: float,
    config: core.RenderConfig,
    state: Optional[core.FrameVisualState],
    show_top_speed: bool,
) -> None:
    """Draw a mirrored quarter-circle gauge intended for lower-left placement."""
    element_scale = core._axis_element_scale(ax)
    ax.clear()
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(-0.2, 1.15)
    ax.set_ylim(-0.25, 1.15)
    ax.set_facecolor((0, 0, 0, 0) if config.transparent else core.to_rgba(config.background_color))

    arc = core.patches.Arc(
        (0, 0),
        2,
        2,
        theta1=0,
        theta2=90,
        linewidth=6 * element_scale,
        color=core.to_rgba(config.speedometer_color, 0.78),
    )
    ax.add_patch(arc)

    tick_step = core._nice_tick_step(max_speed)
    text_color = core.to_rgba(config.text_color, 0.92)
    start_angle = 0.0
    sweep = 90.0

    for tick in core.np.arange(0, max_speed + tick_step, tick_step):
        tick = min(tick, max_speed)
        angle = core.math.radians(start_angle + (tick / max_speed) * sweep)
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
            fontsize=8 * element_scale,
            color=text_color,
        )

    clamped_speed = max(0.0, min(float(speed), max_speed))
    needle_angle = core.math.radians(start_angle + (clamped_speed / max_speed) * sweep)
    ax.plot(
        [0, 0.76 * core.math.cos(needle_angle)],
        [0, 0.76 * core.math.sin(needle_angle)],
        linewidth=4 * element_scale,
        color=core.to_rgba(config.needle_color, 1.0),
    )
    ax.add_patch(core.patches.Circle((0, 0), 0.06, color=core.to_rgba(config.text_color, 1.0)))
    ax.text(
        0.35,
        -0.07,
        "{:.1f}".format(float(speed)),
        ha="center",
        va="center",
        fontsize=22 * element_scale,
        color=core.to_rgba(config.text_color, 1.0),
        fontweight="bold",
    )
    ax.text(
        0.35,
        -0.18,
        core.format_speed_unit(config.speed_output_unit),
        ha="center",
        va="center",
        fontsize=9 * element_scale,
        color=core.to_rgba(config.text_color, 0.75),
    )

    if state is not None and show_top_speed:
        core._draw_top_speed_indicator(ax, state, config)
