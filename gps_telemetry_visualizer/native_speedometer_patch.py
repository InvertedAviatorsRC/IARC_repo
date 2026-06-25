from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel

from gps_telemetry_visualizer import core


_PATCHED = False
_ORIGINAL_DRAW_SPEEDOMETER = None
_NATIVE_APP_PATCHED = False


def install() -> None:
    """Register native-only speedometer variants that are still backed by core rendering."""
    global _PATCHED, _ORIGINAL_DRAW_SPEEDOMETER

    for style in ("corner_left",):
        if style not in core.VALID_SPEEDOMETER_STYLES:
            core.VALID_SPEEDOMETER_STYLES = (*core.VALID_SPEEDOMETER_STYLES, style)

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
        if config.speedometer_style == "corner":
            _draw_corner_right_speedometer(ax, speed, max_speed, config, state, show_top_speed)
            return
        _draw_half_speedometer(ax, speed, max_speed, config, state, show_top_speed)

    core.draw_speedometer = _draw_speedometer
    _PATCHED = True


def extend_native_app(native_app) -> None:
    """Add native app controls for speedometer variants that do not belong in legacy UIs yet."""
    global _NATIVE_APP_PATCHED

    native_app.SPEEDOMETER_STYLES.setdefault("90° corner gauge — lower left", "corner_left")

    if _NATIVE_APP_PATCHED:
        return

    original_build_settings_group = native_app.MainWindow._build_settings_group
    original_connect_preview_signals = native_app.MainWindow._connect_preview_signals
    original_config = native_app.MainWindow._config

    def _build_settings_group(self):
        group = original_build_settings_group(self)
        row = QHBoxLayout()
        self.speedometer_tick_font_scale = QDoubleSpinBox()
        self.speedometer_tick_font_scale.setRange(0.5, 3.0)
        self.speedometer_tick_font_scale.setSingleStep(0.1)
        self.speedometer_tick_font_scale.setValue(1.0)
        self.speedometer_tick_font_scale.setDecimals(1)
        self.speedometer_tick_font_scale.setSuffix("x")
        self.speedometer_tick_font_scale.setMaximumWidth(90)
        row.addWidget(QLabel("Tick/unit font size"))
        row.addWidget(self.speedometer_tick_font_scale)
        row.addStretch()
        group.layout().addLayout(row)
        return group

    def _connect_preview_signals(self):
        original_connect_preview_signals(self)
        self.speedometer_tick_font_scale.valueChanged.connect(self.schedule_preview)

    def _config(self, include_time: bool = True):
        config = original_config(self, include_time)
        if hasattr(self, "speedometer_tick_font_scale"):
            config.speedometer_tick_font_scale = self.speedometer_tick_font_scale.value()
        return config

    native_app.MainWindow._build_settings_group = _build_settings_group
    native_app.MainWindow._connect_preview_signals = _connect_preview_signals
    native_app.MainWindow._config = _config
    _NATIVE_APP_PATCHED = True


def _tick_font_scale(config: core.RenderConfig) -> float:
    return max(0.5, min(3.0, float(getattr(config, "speedometer_tick_font_scale", 1.0))))


def _draw_half_speedometer(
    ax,
    speed: float,
    max_speed: float,
    config: core.RenderConfig,
    state: Optional[core.FrameVisualState],
    show_top_speed: bool,
) -> None:
    element_scale = core._axis_element_scale(ax)
    tick_font_scale = _tick_font_scale(config)
    ax.clear()
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-0.62, 1.25)
    ax.set_facecolor((0, 0, 0, 0) if config.transparent else core.to_rgba(config.background_color))

    arc = core.patches.Arc(
        (0, 0),
        2,
        2,
        theta1=20,
        theta2=160,
        linewidth=6 * element_scale,
        color=core.to_rgba(config.speedometer_color, 0.78),
    )
    ax.add_patch(arc)

    tick_step = core._nice_tick_step(max_speed)
    text_color = core.to_rgba(config.text_color, 0.92)

    for tick in core.np.arange(0, max_speed + tick_step, tick_step):
        tick = min(tick, max_speed)
        angle = core.math.radians(160 - (tick / max_speed) * 140)
        x_outer = core.math.cos(angle)
        y_outer = core.math.sin(angle)
        x_inner = 0.86 * core.math.cos(angle)
        y_inner = 0.86 * core.math.sin(angle)

        ax.plot([x_inner, x_outer], [y_inner, y_outer], linewidth=2 * element_scale, color=core.to_rgba(config.text_color, 0.72))
        ax.text(
            0.7 * core.math.cos(angle),
            0.7 * core.math.sin(angle),
            str(int(round(tick))),
            ha="center",
            va="center",
            fontsize=9 * element_scale * tick_font_scale,
            color=text_color,
        )

    clamped_speed = max(0.0, min(float(speed), max_speed))
    needle_angle = core.math.radians(160 - (clamped_speed / max_speed) * 140)
    ax.plot(
        [0, 0.78 * core.math.cos(needle_angle)],
        [0, 0.78 * core.math.sin(needle_angle)],
        linewidth=4 * element_scale,
        color=core.to_rgba(config.needle_color, 1.0),
    )

    ax.add_patch(core.patches.Circle((0, 0), 0.06, color=core.to_rgba(config.text_color, 1.0)))
    ax.text(
        0,
        0.4,
        "{:.1f}".format(float(speed)),
        ha="center",
        va="center",
        fontsize=28 * element_scale,
        color=core.to_rgba(config.text_color, 1.0),
        fontweight="bold",
    )
    ax.text(
        0,
        0.25,
        core.format_speed_unit(config.speed_output_unit),
        ha="center",
        va="center",
        fontsize=11 * element_scale * tick_font_scale,
        color=core.to_rgba(config.text_color, 0.75),
    )

    if state is not None and show_top_speed:
        core._draw_top_speed_indicator(ax, state, config)


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
        speed_text_x=-0.35,
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
        speed_text_x=0.35,
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
) -> None:
    element_scale = core._axis_element_scale(ax)
    tick_font_scale = _tick_font_scale(config)
    ax.clear()
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(*xlim)
    ax.set_ylim(-0.25, 1.15)
    ax.set_facecolor((0, 0, 0, 0) if config.transparent else core.to_rgba(config.background_color))

    arc = core.patches.Arc(
        (0, 0),
        2,
        2,
        theta1=theta1,
        theta2=theta2,
        linewidth=6 * element_scale,
        color=core.to_rgba(config.speedometer_color, 0.78),
    )
    ax.add_patch(arc)

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
        -0.07,
        "{:.1f}".format(float(speed)),
        ha="center",
        va="center",
        fontsize=22 * element_scale,
        color=core.to_rgba(config.text_color, 1.0),
        fontweight="bold",
    )
    ax.text(
        speed_text_x,
        -0.18,
        core.format_speed_unit(config.speed_output_unit),
        ha="center",
        va="center",
        fontsize=9 * element_scale * tick_font_scale,
        color=core.to_rgba(config.text_color, 0.75),
    )

    if state is not None and show_top_speed:
        core._draw_top_speed_indicator(ax, state, config)
