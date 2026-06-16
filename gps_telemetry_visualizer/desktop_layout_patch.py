from __future__ import annotations

import io
from dataclasses import replace

import matplotlib.pyplot as plt
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from gps_telemetry_visualizer import desktop
from gps_telemetry_visualizer.core import (
    CanvasConfig,
    ElementLayout,
    OverlayLayout,
    RenderConfig,
    clone_overlay_layout,
    compute_layout_bounds,
    default_overlay_layout,
    layout_warnings,
    prepare_telemetry,
    render_static_preview,
    scale_overlay_layout,
)


LAYOUT_LABELS = {
    "map": "Map",
    "speedometer": "Speedometer",
    "top_speed": "Top speed",
    "furthest_distance": "Furthest distance",
}


class LayoutPreview(QLabel):
    layout_changed = Signal(str, float, float)
    selected_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__("Select a CSV to preview.")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(460, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setObjectName("preview")
        self.setMouseTracking(True)
        self._pixmap = None
        self._layout = default_overlay_layout(1920, 1080, "both")
        self._canvas = CanvasConfig(1920, 1080)
        self._config = RenderConfig()
        self._selected = "map"
        self._dragging = False

    def set_preview(self, pixmap: QPixmap, layout: OverlayLayout, canvas: CanvasConfig, config: RenderConfig) -> None:
        self._pixmap = pixmap
        self.setText("")
        self.set_layout(layout, canvas, config)

    def set_layout(self, layout: OverlayLayout, canvas: CanvasConfig, config: RenderConfig) -> None:
        self._layout = layout
        self._canvas = canvas
        self._config = config
        self.update()

    def set_selected(self, name: str) -> None:
        if name in LAYOUT_LABELS:
            self._selected = name
            self.update()

    def clear_preview(self, message: str) -> None:
        self._pixmap = None
        self.setText(message)
        self.update()

    def paintEvent(self, event) -> None:
        if self._pixmap is None:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0b1017"))
        image_rect = self._image_rect()
        painter.drawPixmap(image_rect.toRect(), self._pixmap)

        bounds = compute_layout_bounds(self._layout, self._canvas, self._config)
        for name, box in bounds.items():
            if not box.visible:
                continue
            screen_rect = self._screen_rect(box)
            selected = name == self._selected
            pen = QPen(QColor("#22c55e" if selected else "#dbeafe"))
            pen.setWidth(3 if selected else 1)
            pen.setStyle(Qt.SolidLine if selected else Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(screen_rect)

            label_rect = QRectF(screen_rect.left(), screen_rect.top() - 22, 150, 20)
            painter.fillRect(label_rect, QColor(10, 16, 24, 210))
            painter.setPen(QColor("#e8edf3"))
            painter.drawText(label_rect.adjusted(6, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, LAYOUT_LABELS[name])

        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._pixmap is None:
            return
        point = self._event_point(event)
        selected = self._hit_test(point)
        if selected is not None:
            self._selected = selected
            self._dragging = True
            self.selected_changed.emit(selected)
            x, y = self._output_point(point)
            self.layout_changed.emit(selected, x, y)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._dragging or self._pixmap is None:
            return
        x, y = self._output_point(self._event_point(event))
        self.layout_changed.emit(self._selected, x, y)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = False

    def _hit_test(self, point: QPointF) -> str | None:
        bounds = compute_layout_bounds(self._layout, self._canvas, self._config)
        for name in reversed(tuple(LAYOUT_LABELS)):
            box = bounds[name]
            if box.visible and self._screen_rect(box).contains(point):
                return name
        return None

    def _image_rect(self) -> QRectF:
        available_width = max(1.0, float(self.width()))
        available_height = max(1.0, float(self.height()))
        canvas_aspect = self._canvas.width / max(1.0, float(self._canvas.height))
        available_aspect = available_width / available_height
        if available_aspect > canvas_aspect:
            height = available_height
            width = height * canvas_aspect
            left = (available_width - width) / 2.0
            top = 0.0
        else:
            width = available_width
            height = width / canvas_aspect
            left = 0.0
            top = (available_height - height) / 2.0
        return QRectF(left, top, width, height)

    def _screen_rect(self, box) -> QRectF:
        image_rect = self._image_rect()
        scale_x = image_rect.width() / max(1.0, float(self._canvas.width))
        scale_y = image_rect.height() / max(1.0, float(self._canvas.height))
        return QRectF(
            image_rect.left() + box.left * scale_x,
            image_rect.top() + box.top * scale_y,
            box.width * scale_x,
            box.height * scale_y,
        )

    def _output_point(self, point: QPointF) -> tuple[float, float]:
        image_rect = self._image_rect()
        return (
            (point.x() - image_rect.left()) / max(1.0, image_rect.width()) * self._canvas.width,
            (point.y() - image_rect.top()) / max(1.0, image_rect.height()) * self._canvas.height,
        )

    @staticmethod
    def _event_point(event: QMouseEvent) -> QPointF:
        if hasattr(event, "position"):
            return event.position()
        return QPointF(event.pos())


_ORIGINAL_INIT = desktop.MainWindow.__init__
_ORIGINAL_CONFIG = desktop.MainWindow._config


def apply_patch() -> None:
    desktop.LayoutPreview = LayoutPreview
    desktop.MainWindow.__init__ = _patched_init
    desktop.MainWindow._build_preview_panel = _build_preview_panel
    desktop.MainWindow._add_layout_controls = _add_layout_controls
    desktop.MainWindow._show_preview_frame = _show_preview_frame
    desktop.MainWindow._current_canvas = _current_canvas
    desktop.MainWindow._update_preview_layout = _update_preview_layout
    desktop.MainWindow._sync_layout_controls = _sync_layout_controls
    desktop.MainWindow._layout_controls_changed = _layout_controls_changed
    desktop.MainWindow._layout_from_controls = _layout_from_controls
    desktop.MainWindow._preview_layout_changed = _preview_layout_changed
    desktop.MainWindow._preview_selected_changed = _preview_selected_changed
    desktop.MainWindow._reset_layout_element = _reset_layout_element
    desktop.MainWindow._reset_layout = _reset_layout
    desktop.MainWindow._update_layout_warning_status = _update_layout_warning_status
    desktop.MainWindow.refresh_preview = refresh_preview
    desktop.MainWindow._resolution_changed = _resolution_changed
    desktop.MainWindow._config = _config


def main() -> None:
    apply_patch()
    desktop.main()


def _patched_init(self) -> None:
    self.overlay_layout = default_overlay_layout(1920, 1080, "both")
    self.layout_canvas_width = 1920
    self.layout_canvas_height = 1080
    self.layout_controls = {}
    self._syncing_layout_controls = False
    self.selected_layout_element = "map"
    _ORIGINAL_INIT(self)
    self.output_width.valueChanged.connect(self._resolution_changed)
    self.output_height.valueChanged.connect(self._resolution_changed)
    self._sync_layout_controls()
    self._update_preview_layout()


def _build_preview_panel(self) -> QWidget:
    panel = QWidget()
    panel.setObjectName("panel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(10)
    title = QLabel("Preview")
    title.setObjectName("sectionTitle")
    layout.addWidget(title)

    self.preview = LayoutPreview()
    self.preview.layout_changed.connect(self._preview_layout_changed)
    self.preview.selected_changed.connect(self._preview_selected_changed)
    layout.addWidget(self.preview, 1)

    timeline_title = QLabel("Timeline")
    timeline_title.setObjectName("subsectionTitle")
    layout.addWidget(timeline_title)

    self.playhead_time, self.playhead_time_label = desktop._time_slider()
    self.start_time, self.start_time_label = desktop._time_slider()
    self.end_time, self.end_time_label = desktop._time_slider()
    self.playhead_time.setToolTip("Scrub the preview frame without changing the export range.")
    self.start_time.setToolTip("Set where the rendered export should start.")
    self.end_time.setToolTip("Set where the rendered export should end.")
    self.playhead_time.valueChanged.connect(self._time_slider_changed)
    self.start_time.valueChanged.connect(self._time_slider_changed)
    self.end_time.valueChanged.connect(self._time_slider_changed)
    layout.addWidget(desktop._labeled_slider_row("Preview position", self.playhead_time, self.playhead_time_label))
    layout.addWidget(desktop._labeled_slider_row("Trim start", self.start_time, self.start_time_label))
    layout.addWidget(desktop._labeled_slider_row("Trim end", self.end_time, self.end_time_label))

    layout_title = QLabel("Layout")
    layout_title.setObjectName("subsectionTitle")
    layout.addWidget(layout_title)

    self.selected_layout_label = QLabel("Drag an element in the preview, or enter exact center coordinates.")
    self.selected_layout_label.setObjectName("muted")
    self.selected_layout_label.setWordWrap(True)
    layout.addWidget(self.selected_layout_label)

    layout_grid = QGridLayout()
    layout_grid.setHorizontalSpacing(8)
    layout_grid.setVerticalSpacing(6)
    layout_grid.addWidget(QLabel("Element"), 0, 0)
    layout_grid.addWidget(QLabel("Show"), 0, 1)
    layout_grid.addWidget(QLabel("X"), 0, 2)
    layout_grid.addWidget(QLabel("Y"), 0, 3)
    for row, name in enumerate(LAYOUT_LABELS, start=1):
        self._add_layout_controls(layout_grid, row, name)
    layout.addLayout(layout_grid)

    reset_layout = QPushButton("Reset layout")
    reset_layout.clicked.connect(self._reset_layout)
    layout.addWidget(reset_layout)

    colors_title = QLabel("Colors")
    colors_title.setObjectName("subsectionTitle")
    layout.addWidget(colors_title)

    color_grid = QGridLayout()
    color_grid.setHorizontalSpacing(10)
    color_grid.setVerticalSpacing(8)
    self.path_color = desktop.ColorButton("Path", "#00d5ff")
    self.speedometer_color = desktop.ColorButton("Speedometer", "#00d5ff")
    self.start_marker_color = desktop.ColorButton("Start star", "#ffd43b")
    self.dot_color = desktop.ColorButton("Position dot", "#ff3355")
    self.needle_color = desktop.ColorButton("Needle", "#ff3355")
    self.background_color = desktop.ColorButton("Background", "#101820")
    color_grid.addWidget(self.path_color, 0, 0)
    color_grid.addWidget(self.speedometer_color, 0, 1)
    color_grid.addWidget(self.start_marker_color, 1, 0)
    color_grid.addWidget(self.dot_color, 1, 1)
    color_grid.addWidget(self.needle_color, 2, 0)
    color_grid.addWidget(self.background_color, 2, 1)
    layout.addLayout(color_grid)

    self.transparent = QCheckBox("Transparent background")
    self.transparent.setChecked(False)
    self.transparent.toggled.connect(self._update_background_controls)
    layout.addWidget(self.transparent)

    action_row = QHBoxLayout()
    refresh = QPushButton("Refresh Preview")
    refresh.clicked.connect(self.refresh_preview)
    self.create_button = QPushButton("Create")
    self.create_button.setObjectName("createButton")
    self.create_button.clicked.connect(self.create_animation)
    action_row.addWidget(refresh)
    action_row.addWidget(self.create_button)
    layout.addLayout(action_row)

    self.progress = desktop.QProgressBar()
    self.progress.setVisible(False)
    layout.addWidget(self.progress)

    self.status = QLabel("")
    self.status.setWordWrap(True)
    self.status.setObjectName("muted")
    layout.addWidget(self.status)
    return panel


def _add_layout_controls(self, grid: QGridLayout, row: int, name: str) -> None:
    select = QPushButton(LAYOUT_LABELS[name])
    select.clicked.connect(lambda checked=False, element=name: self._preview_selected_changed(element))

    visible = QCheckBox()
    visible.toggled.connect(self._layout_controls_changed)

    x_spin = QDoubleSpinBox()
    x_spin.setRange(-20000, 20000)
    x_spin.setDecimals(1)
    x_spin.setSingleStep(1.0)
    x_spin.valueChanged.connect(self._layout_controls_changed)

    y_spin = QDoubleSpinBox()
    y_spin.setRange(-20000, 20000)
    y_spin.setDecimals(1)
    y_spin.setSingleStep(1.0)
    y_spin.valueChanged.connect(self._layout_controls_changed)

    reset = QPushButton("Reset")
    reset.clicked.connect(lambda checked=False, element=name: self._reset_layout_element(element))

    grid.addWidget(select, row, 0)
    grid.addWidget(visible, row, 1, Qt.AlignCenter)
    grid.addWidget(x_spin, row, 2)
    grid.addWidget(y_spin, row, 3)
    grid.addWidget(reset, row, 4)
    self.layout_controls[name] = {"visible": visible, "x": x_spin, "y": y_spin}


def _show_preview_frame(self) -> None:
    if not self.preview_frames:
        return
    pixmap = self.preview_frames[self.preview_frame_index]
    self.preview.set_preview(pixmap, self.overlay_layout, self._current_canvas(), self._config())


def _current_canvas(self) -> CanvasConfig:
    return CanvasConfig(self.output_width.value(), self.output_height.value())


def _update_preview_layout(self) -> None:
    self.preview.set_layout(self.overlay_layout, self._current_canvas(), self._config())


def _sync_layout_controls(self) -> None:
    if not self.layout_controls:
        return
    self._syncing_layout_controls = True
    try:
        for name, controls in self.layout_controls.items():
            element = getattr(self.overlay_layout, name)
            controls["visible"].setChecked(element.visible)
            controls["x"].setValue(float(element.x))
            controls["y"].setValue(float(element.y))
    finally:
        self._syncing_layout_controls = False
    self.selected_layout_label.setText(
        "Selected: {}. Drag it in the preview, or enter exact center coordinates.".format(
            LAYOUT_LABELS.get(self.selected_layout_element, "Map")
        )
    )


def _layout_controls_changed(self) -> None:
    if self._syncing_layout_controls:
        return
    self.overlay_layout = OverlayLayout(
        map=self._layout_from_controls("map"),
        speedometer=self._layout_from_controls("speedometer"),
        top_speed=self._layout_from_controls("top_speed"),
        furthest_distance=self._layout_from_controls("furthest_distance"),
    )
    self._update_preview_layout()
    self._update_layout_warning_status()
    self.schedule_preview()


def _layout_from_controls(self, name: str) -> ElementLayout:
    controls = self.layout_controls[name]
    return ElementLayout(controls["x"].value(), controls["y"].value(), controls["visible"].isChecked())


def _preview_layout_changed(self, name: str, x: float, y: float) -> None:
    if name not in LAYOUT_LABELS:
        return
    self.selected_layout_element = name
    element = getattr(self.overlay_layout, name)
    setattr(self.overlay_layout, name, ElementLayout(x, y, element.visible))
    self._sync_layout_controls()
    self._update_preview_layout()
    self._update_layout_warning_status()
    self.schedule_preview()


def _preview_selected_changed(self, name: str) -> None:
    if name not in LAYOUT_LABELS:
        return
    self.selected_layout_element = name
    self.preview.set_selected(name)
    self._sync_layout_controls()


def _reset_layout_element(self, name: str) -> None:
    defaults = default_overlay_layout(self.output_width.value(), self.output_height.value(), self.export_mode.currentText())
    setattr(self.overlay_layout, name, getattr(defaults, name))
    self._sync_layout_controls()
    self._update_preview_layout()
    self._update_layout_warning_status()
    self.schedule_preview()


def _reset_layout(self) -> None:
    self.overlay_layout = default_overlay_layout(
        self.output_width.value(),
        self.output_height.value(),
        self.export_mode.currentText(),
    )
    self._sync_layout_controls()
    self._update_preview_layout()
    self._update_layout_warning_status()
    self.schedule_preview()


def _update_layout_warning_status(self, base_message: str | None = None) -> None:
    warnings = layout_warnings(self.overlay_layout, self._current_canvas(), self._config())
    message = base_message or self.status.text()
    if warnings:
        message = "{}\n{}".format(message, "\n".join(warnings)) if message else "\n".join(warnings)
    self.status.setText(message)


def refresh_preview(self) -> None:
    self.preview_playback_timer.stop()
    self.preview_frames = []
    self.preview_frame_index = 0

    if not self.csv_path:
        self.preview.clear_preview("Select a CSV to preview.")
        return

    try:
        render_config = self._config()
        data = prepare_telemetry(self.csv_path, render_config)
        preview_time = self.playhead_time.value() / desktop.TIME_SLIDER_SCALE
        preview_time = min(max(preview_time, data.start_time), data.end_time) - data.start_time
        fig = render_static_preview(self.csv_path, render_config, frame_time=preview_time)
        buffer = io.BytesIO()
        fig.savefig(
            buffer,
            format="png",
            dpi=105,
            facecolor=fig.get_facecolor(),
            transparent=render_config.transparent,
        )
        plt.close(fig)

        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")
        self.preview_frames.append(pixmap)
        self._show_preview_frame()

        status_message = (
            "{} valid GPS rows from {} total rows. Previewing {}. Export trim: {} to {}. Max speed: {:.1f} {}.".format(
                data.valid_rows,
                data.source_rows,
                desktop._format_seconds(self.playhead_time.value() / desktop.TIME_SLIDER_SCALE),
                desktop._format_seconds(data.start_time),
                desktop._format_seconds(data.end_time),
                data.max_speed,
                self.speed_output_unit.currentText().upper(),
            )
        )
        self._update_layout_warning_status(status_message)
    except Exception as exc:
        self.preview.clear_preview("Preview unavailable.")
        self.status.setText(str(exc))


def _resolution_changed(self) -> None:
    preset = desktop.RESOLUTION_PRESETS.get(self.resolution_preset.currentText())
    is_custom = preset is None
    old_width = getattr(self, "layout_canvas_width", self.output_width.value())
    old_height = getattr(self, "layout_canvas_height", self.output_height.value())
    self.output_width.setEnabled(is_custom)
    self.output_height.setEnabled(is_custom)
    if preset is not None:
        width, height = preset
        self.output_width.blockSignals(True)
        self.output_height.blockSignals(True)
        self.output_width.setValue(width)
        self.output_height.setValue(height)
        self.output_width.blockSignals(False)
        self.output_height.blockSignals(False)
    new_width = self.output_width.value()
    new_height = self.output_height.value()
    if hasattr(self, "overlay_layout") and (new_width != old_width or new_height != old_height):
        self.overlay_layout = scale_overlay_layout(self.overlay_layout, old_width, old_height, new_width, new_height)
        self.layout_canvas_width = new_width
        self.layout_canvas_height = new_height
        self._sync_layout_controls()
        self._update_preview_layout()
        self._update_layout_warning_status()
    self.schedule_preview()


def _config(self, include_time: bool = True) -> RenderConfig:
    return replace(_ORIGINAL_CONFIG(self, include_time), layout=clone_overlay_layout(self.overlay_layout))
