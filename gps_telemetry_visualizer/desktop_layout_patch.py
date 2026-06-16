from __future__ import annotations

import io
from dataclasses import replace

import matplotlib.pyplot as plt
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

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
    resize_layout_element_from_corner,
    scale_overlay_layout,
)


LAYOUT_LABELS = {
    "map": "Map",
    "speedometer": "Speedometer",
    "top_speed": "Top speed",
    "furthest_distance": "Furthest distance",
}


class CollapsibleSection(QWidget):
    def __init__(self, title: str, content: QWidget, expanded: bool = True) -> None:
        super().__init__()
        self._title = title
        self._content = content
        self._toggle = QPushButton()
        self._toggle.setObjectName("sectionToggle")
        self._toggle.clicked.connect(self._toggle_content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._toggle)
        layout.addWidget(content)

        content.setVisible(expanded)
        self._refresh_title()

    def _toggle_content(self) -> None:
        self._content.setVisible(not self._content.isVisible())
        self._refresh_title()

    def _refresh_title(self) -> None:
        marker = "v" if self._content.isVisible() else ">"
        self._toggle.setText("{} {}".format(marker, self._title))


class CompactColorControl(QWidget):
    color_changed = Signal(str)

    def __init__(self, label: str, color: str) -> None:
        super().__init__()
        self._label = label
        self._color = color
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.swatch = QPushButton("")
        self.swatch.setObjectName("colorSwatch")
        self.swatch.setFixedSize(28, 24)
        self.swatch.clicked.connect(self._choose_color)

        self.label = QLabel(label)
        self.label.setMinimumWidth(88)
        self.value = QLabel(color.upper())
        self.value.setObjectName("muted")
        self.value.setMinimumWidth(72)

        layout.addWidget(self.label)
        layout.addWidget(self.swatch)
        layout.addWidget(self.value)
        layout.addStretch()
        self._refresh()

    @property
    def color(self) -> str:
        return self._color

    def _choose_color(self) -> None:
        selected = QColorDialog.getColor(QColor(self._color), self.window(), self._label)
        if selected.isValid():
            self._color = selected.name()
            self._refresh()
            self.color_changed.emit(self._color)

    def _refresh(self) -> None:
        self.value.setText(self._color.upper())
        self.swatch.setStyleSheet(
            "QPushButton#colorSwatch {{ background: {}; border: 1px solid #536071; border-radius: 5px; }}".format(
                self._color
            )
        )


class LayoutPreview(QLabel):
    layout_changed = Signal(str, float, float, float)
    selected_changed = Signal(str)
    HANDLE_SIZE = 12

    def __init__(self) -> None:
        super().__init__("Select a CSV to preview.")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(720, 520)
        self.setFixedHeight(520)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setObjectName("preview")
        self.setMouseTracking(True)
        self._pixmap = None
        self._layout = default_overlay_layout(1920, 1080, "both")
        self._canvas = CanvasConfig(1920, 1080)
        self._config = RenderConfig()
        self._selected = "map"
        self._dragging = False
        self._drag_mode = "move"
        self._resize_corner = None

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

            if selected:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#22c55e"))
                for handle in self._handle_rects(screen_rect).values():
                    painter.drawRect(handle)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._pixmap is None:
            return
        point = self._event_point(event)
        handle = self._hit_handle(point)
        if handle is not None:
            self._dragging = True
            self._drag_mode = "resize"
            self._resize_corner = handle
            self.selected_changed.emit(self._selected)
            self._emit_resized_layout(point)
            self.update()
            return

        selected = self._hit_test(point)
        if selected is not None:
            self._selected = selected
            self._dragging = True
            self._drag_mode = "move"
            self._resize_corner = None
            self.selected_changed.emit(selected)
            x, y = self._output_point(point)
            scale = getattr(getattr(self._layout, selected), "scale", 1.0)
            self.layout_changed.emit(selected, x, y, scale)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._pixmap is None:
            return
        point = self._event_point(event)
        if not self._dragging:
            self._update_cursor(point)
            return
        if self._drag_mode == "resize":
            self._emit_resized_layout(point)
            return
        x, y = self._output_point(point)
        scale = getattr(getattr(self._layout, self._selected), "scale", 1.0)
        self.layout_changed.emit(self._selected, x, y, scale)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = False
        self._drag_mode = "move"
        self._resize_corner = None
        self._update_cursor(self._event_point(event))

    def _hit_test(self, point: QPointF) -> str | None:
        bounds = compute_layout_bounds(self._layout, self._canvas, self._config)
        for name in reversed(tuple(LAYOUT_LABELS)):
            box = bounds[name]
            if box.visible and self._screen_rect(box).contains(point):
                return name
        return None

    def _hit_handle(self, point: QPointF) -> str | None:
        bounds = compute_layout_bounds(self._layout, self._canvas, self._config)
        box = bounds.get(self._selected)
        if box is None or not box.visible:
            return None
        for corner, rect in self._handle_rects(self._screen_rect(box)).items():
            if rect.contains(point):
                return corner
        return None

    def _handle_rects(self, screen_rect: QRectF) -> dict[str, QRectF]:
        size = float(self.HANDLE_SIZE)
        half = size / 2.0
        points = {
            "top_left": QPointF(screen_rect.left(), screen_rect.top()),
            "top_right": QPointF(screen_rect.right(), screen_rect.top()),
            "bottom_left": QPointF(screen_rect.left(), screen_rect.bottom()),
            "bottom_right": QPointF(screen_rect.right(), screen_rect.bottom()),
        }
        return {
            name: QRectF(point.x() - half, point.y() - half, size, size)
            for name, point in points.items()
        }

    def _emit_resized_layout(self, point: QPointF) -> None:
        x, y = self._output_point(point)
        resized = resize_layout_element_from_corner(
            self._layout,
            self._selected,
            self._canvas,
            self._resize_corner or "bottom_right",
            x,
            y,
            self._config,
        )
        element = getattr(resized, self._selected)
        self.layout_changed.emit(self._selected, element.x, element.y, element.scale)

    def _update_cursor(self, point: QPointF) -> None:
        handle = self._hit_handle(point)
        if handle in ("top_left", "bottom_right"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif handle in ("top_right", "bottom_left"):
            self.setCursor(Qt.SizeBDiagCursor)
        elif self._hit_test(point) is not None:
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.unsetCursor()

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
_ORIGINAL_CREATE_ANIMATION = desktop.MainWindow.create_animation
_ORIGINAL_RENDER_FINISHED = desktop.MainWindow._render_finished
_ORIGINAL_RENDER_FAILED = desktop.MainWindow._render_failed


def apply_patch() -> None:
    desktop.LayoutPreview = LayoutPreview
    desktop.MainWindow.__init__ = _patched_init
    desktop.MainWindow._build_controls_panel = _build_controls_panel
    desktop.MainWindow._build_file_group = _build_file_group
    desktop.MainWindow._build_export_group = _build_export_group
    desktop.MainWindow._build_elements_group = _build_elements_group
    desktop.MainWindow._build_colors_group = _build_colors_group
    desktop.MainWindow._build_advanced_group = _build_advanced_group
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
    desktop.MainWindow.create_animation = create_animation
    desktop.MainWindow._render_finished = _render_finished
    desktop.MainWindow._render_failed = _render_failed


def main() -> None:
    apply_patch()
    desktop.main()


def _patched_init(self) -> None:
    desktop.QMainWindow.__init__(self)
    self.setWindowTitle("GPS Telemetry Visualizer")
    self.resize(1500, 860)
    self.setMinimumSize(1240, 760)

    self.csv_path = ""
    self.columns = []
    self.render_thread = None
    self.render_worker = None
    self.preview_frames = []
    self.preview_frame_index = 0
    self.overlay_layout = default_overlay_layout(1920, 1080, "both")
    self.layout_canvas_width = 1920
    self.layout_canvas_height = 1080
    self.layout_controls = {}
    self._syncing_layout_controls = False
    self.selected_layout_element = "map"
    self.preview_timer = desktop.QTimer(self)
    self.preview_timer.setSingleShot(True)
    self.preview_timer.timeout.connect(self.refresh_preview)
    self.preview_playback_timer = desktop.QTimer(self)
    self.preview_playback_timer.timeout.connect(self._advance_preview_frame)

    root = QWidget()
    self.setCentralWidget(root)
    main_layout = QGridLayout(root)
    main_layout.setContentsMargins(14, 14, 14, 14)
    main_layout.setHorizontalSpacing(14)
    main_layout.setVerticalSpacing(0)
    main_layout.setColumnStretch(0, 2)
    main_layout.setColumnStretch(1, 6)

    main_layout.addWidget(self._build_controls_panel(), 0, 0)
    main_layout.addWidget(self._build_preview_panel(), 0, 1)

    self._connect_preview_signals()
    self._update_transparency_controls()
    self._sync_layout_controls()
    self._update_preview_layout()


def _build_controls_panel(self) -> QWidget:
    scroll = QScrollArea()
    scroll.setObjectName("panel")
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setMinimumWidth(390)
    scroll.setMaximumWidth(520)
    scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)

    title = QLabel("Controls")
    title.setObjectName("sectionTitle")
    layout.addWidget(title)

    layout.addWidget(CollapsibleSection("File", self._build_file_group(), expanded=True))
    layout.addWidget(CollapsibleSection("Export", self._build_export_group(), expanded=True))
    layout.addWidget(CollapsibleSection("Elements", self._build_elements_group(), expanded=True))
    layout.addWidget(CollapsibleSection("Colors", self._build_colors_group(), expanded=True))
    layout.addWidget(CollapsibleSection("Advanced settings", self._build_advanced_group(), expanded=False))
    layout.addStretch()
    scroll.setWidget(panel)
    return scroll


def _build_file_group(self) -> QWidget:
    group = QWidget()
    layout = QVBoxLayout(group)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    self.drop_zone = desktop.CsvDropZone()
    self.drop_zone.file_dropped.connect(self.set_csv_file)
    self.drop_zone.setMinimumHeight(118)
    self.drop_zone.setMaximumHeight(132)
    layout.addWidget(self.drop_zone)

    browse_csv = QPushButton("Browse CSV")
    browse_csv.clicked.connect(self.browse_csv)
    layout.addWidget(browse_csv)

    self.csv_label = QLabel("No CSV selected")
    self.csv_label.setWordWrap(True)
    self.csv_label.setObjectName("muted")
    layout.addWidget(self.csv_label)
    return group


def _build_export_group(self) -> QWidget:
    group = QWidget()
    layout = QVBoxLayout(group)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    folder_row = QHBoxLayout()
    self.output_folder = QLineEdit(str(desktop.Path.cwd() / "output"))
    browse_folder = QPushButton("Browse")
    browse_folder.setMaximumWidth(82)
    browse_folder.clicked.connect(self.browse_output_folder)
    folder_row.addWidget(self.output_folder, 1)
    folder_row.addWidget(browse_folder)
    layout.addWidget(QLabel("Output folder"))
    layout.addLayout(folder_row)

    type_row = QHBoxLayout()
    self.file_type = QComboBox()
    self.file_type.addItems(["mp4", "mov"])
    self.file_type.setMaximumWidth(92)
    self.file_type.currentTextChanged.connect(self._file_type_changed)
    self.transparent = QCheckBox("Transparent background")
    self.transparent.setChecked(False)
    self.transparent.toggled.connect(self._update_background_controls)
    type_row.addWidget(QLabel("File type"))
    type_row.addWidget(self.file_type)
    type_row.addSpacing(10)
    type_row.addWidget(self.transparent)
    type_row.addStretch()
    layout.addLayout(type_row)

    self.resolution_preset = QComboBox()
    self.resolution_preset.addItems(list(desktop.RESOLUTION_PRESETS))
    self.resolution_preset.setCurrentText("1920 x 1080 - 1080p")
    self.resolution_preset.currentTextChanged.connect(self._resolution_changed)
    layout.addWidget(QLabel("Resolution"))
    layout.addWidget(self.resolution_preset)

    self.resolution_size_row = QWidget()
    size_layout = QHBoxLayout(self.resolution_size_row)
    size_layout.setContentsMargins(0, 0, 0, 0)
    size_layout.setSpacing(8)
    self.output_width = QSpinBox()
    self.output_width.setRange(1, 10000)
    self.output_width.setValue(1920)
    self.output_width.setMaximumWidth(112)
    self.output_width.valueChanged.connect(self._resolution_changed)
    self.output_height = QSpinBox()
    self.output_height.setRange(1, 10000)
    self.output_height.setValue(1080)
    self.output_height.setMaximumWidth(112)
    self.output_height.valueChanged.connect(self._resolution_changed)
    size_layout.addWidget(QLabel("W"))
    size_layout.addWidget(self.output_width)
    size_layout.addWidget(QLabel("H"))
    size_layout.addWidget(self.output_height)
    size_layout.addStretch()
    layout.addWidget(self.resolution_size_row)

    self.output_name = QLineEdit(desktop.default_output_name("both", "mp4"))
    layout.addWidget(QLabel("Output file name"))
    layout.addWidget(self.output_name)

    self.export_mode = QComboBox()
    self.export_mode.addItems(["both"])
    self.export_mode.setVisible(False)
    layout.addWidget(self.export_mode)
    self._resolution_changed()
    return group


def _build_elements_group(self) -> QWidget:
    group = QWidget()
    layout = QVBoxLayout(group)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    self.selected_layout_label = QLabel("Selected: Map. Drag to move; use corner handles to resize.")
    self.selected_layout_label.setObjectName("muted")
    self.selected_layout_label.setWordWrap(True)
    layout.addWidget(self.selected_layout_label)

    layout_grid = QGridLayout()
    layout_grid.setHorizontalSpacing(7)
    layout_grid.setVerticalSpacing(5)
    layout_grid.setColumnMinimumWidth(0, 106)
    layout_grid.setColumnMinimumWidth(1, 38)
    layout_grid.setColumnMinimumWidth(2, 82)
    layout_grid.setColumnMinimumWidth(3, 82)
    layout_grid.setColumnMinimumWidth(4, 78)
    layout_grid.setColumnMinimumWidth(5, 62)
    layout_grid.setColumnStretch(0, 2)
    layout_grid.setColumnStretch(2, 1)
    layout_grid.setColumnStretch(3, 1)
    layout_grid.setColumnStretch(4, 1)
    layout_grid.addWidget(QLabel("Element"), 0, 0)
    layout_grid.addWidget(QLabel("Show"), 0, 1)
    layout_grid.addWidget(QLabel("X"), 0, 2)
    layout_grid.addWidget(QLabel("Y"), 0, 3)
    layout_grid.addWidget(QLabel("Scale"), 0, 4)
    for row, name in enumerate(LAYOUT_LABELS, start=1):
        self._add_layout_controls(layout_grid, row, name)
    layout.addLayout(layout_grid)

    reset_layout = QPushButton("Reset layout")
    reset_layout.clicked.connect(self._reset_layout)
    layout.addWidget(reset_layout)
    return group


def _build_colors_group(self) -> QWidget:
    group = QWidget()
    layout = QVBoxLayout(group)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    color_grid = QGridLayout()
    color_grid.setHorizontalSpacing(8)
    color_grid.setVerticalSpacing(5)
    self.path_color = CompactColorControl("Path", "#00d5ff")
    self.speedometer_color = CompactColorControl("Speedometer", "#00d5ff")
    self.start_marker_color = CompactColorControl("Start star", "#ffd43b")
    self.dot_color = CompactColorControl("Position dot", "#ff3355")
    self.needle_color = CompactColorControl("Needle", "#ff3355")
    self.background_color = CompactColorControl("Background", "#101820")
    color_grid.addWidget(self.path_color, 0, 0)
    color_grid.addWidget(self.speedometer_color, 1, 0)
    color_grid.addWidget(self.start_marker_color, 2, 0)
    color_grid.addWidget(self.dot_color, 3, 0)
    color_grid.addWidget(self.needle_color, 4, 0)
    color_grid.addWidget(self.background_color, 5, 0)
    layout.addLayout(color_grid)
    return group


def _build_advanced_group(self) -> QWidget:
    group = QWidget()
    layout = QVBoxLayout(group)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setHorizontalSpacing(10)
    form.setVerticalSpacing(8)

    self.gps_col = desktop._editable_combo("GPS")
    self.speed_col = desktop._editable_combo("GSpd(kmh)")
    self.heading_col = desktop._editable_combo("Hdg(°)")
    self.altitude_col = desktop._editable_combo("Alt(m)")
    form.addRow("GPS column", self.gps_col)
    form.addRow("Speed column", self.speed_col)
    form.addRow("Heading column", self.heading_col)
    form.addRow("Altitude column", self.altitude_col)
    layout.addLayout(form)

    units_row = QHBoxLayout()
    self.speed_input_unit = QComboBox()
    self.speed_input_unit.addItems(["kmh", "mph", "ms"])
    self.speed_input_unit.setMaximumWidth(92)
    self.speed_output_unit = QComboBox()
    self.speed_output_unit.addItems(["mph", "kmh", "ms"])
    self.speed_output_unit.setMaximumWidth(92)
    units_row.addWidget(QLabel("Input"))
    units_row.addWidget(self.speed_input_unit)
    units_row.addWidget(QLabel("Output"))
    units_row.addWidget(self.speed_output_unit)
    units_row.addStretch()
    layout.addLayout(units_row)

    timing_row = QHBoxLayout()
    self.fps = QSpinBox()
    self.fps.setRange(10, 60)
    self.fps.setSingleStep(5)
    self.fps.setValue(30)
    self.fps.setMaximumWidth(84)
    self.seconds_between = QDoubleSpinBox()
    self.seconds_between.setRange(0.2, 3.0)
    self.seconds_between.setSingleStep(0.1)
    self.seconds_between.setValue(1.0)
    self.seconds_between.setMaximumWidth(92)
    timing_row.addWidget(QLabel("FPS"))
    timing_row.addWidget(self.fps)
    timing_row.addWidget(QLabel("GPS seconds"))
    timing_row.addWidget(self.seconds_between)
    timing_row.addStretch()
    layout.addLayout(timing_row)

    speed_row = QHBoxLayout()
    self.auto_max_speed = QCheckBox("Auto max speed")
    self.auto_max_speed.setChecked(True)
    self.auto_max_speed.toggled.connect(lambda checked: self.max_speed.setEnabled(not checked))
    self.max_speed = QDoubleSpinBox()
    self.max_speed.setRange(1.0, 500.0)
    self.max_speed.setSingleStep(5.0)
    self.max_speed.setValue(60.0)
    self.max_speed.setEnabled(False)
    self.max_speed.setMaximumWidth(96)
    speed_row.addWidget(self.auto_max_speed)
    speed_row.addWidget(self.max_speed)
    speed_row.addStretch()
    layout.addLayout(speed_row)
    return group


def _build_preview_panel(self) -> QWidget:
    panel = QWidget()
    panel.setObjectName("panel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(8)

    self.preview = LayoutPreview()
    self.preview.layout_changed.connect(self._preview_layout_changed)
    self.preview.selected_changed.connect(self._preview_selected_changed)
    layout.addWidget(self.preview)

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

    self.create_button = QPushButton("Create")
    self.create_button.setObjectName("createButton")
    self.create_button.clicked.connect(self.create_animation)
    layout.addWidget(self.create_button)

    self.progress = desktop.QProgressBar()
    self.progress.setVisible(False)
    layout.addWidget(self.progress)

    self.status = QLabel("")
    self.status.setWordWrap(True)
    self.status.setObjectName("warning")
    self.status.setVisible(False)
    self.status.setStyleSheet(
        "QLabel#warning { background: #2a1f12; color: #ffdca8; border: 1px solid #8a5a18; "
        "border-radius: 6px; padding: 7px; }"
    )
    layout.addWidget(self.status)
    layout.addStretch()
    return panel


def _add_layout_controls(self, grid: QGridLayout, row: int, name: str) -> None:
    select = QPushButton(LAYOUT_LABELS[name])
    select.setMinimumWidth(100)
    select.clicked.connect(lambda checked=False, element=name: self._preview_selected_changed(element))

    visible = QCheckBox()
    visible.toggled.connect(self._layout_controls_changed)

    x_spin = QDoubleSpinBox()
    x_spin.setRange(-20000, 20000)
    x_spin.setDecimals(1)
    x_spin.setSingleStep(1.0)
    x_spin.setMinimumWidth(82)
    x_spin.valueChanged.connect(self._layout_controls_changed)

    y_spin = QDoubleSpinBox()
    y_spin.setRange(-20000, 20000)
    y_spin.setDecimals(1)
    y_spin.setSingleStep(1.0)
    y_spin.setMinimumWidth(82)
    y_spin.valueChanged.connect(self._layout_controls_changed)

    scale_spin = QDoubleSpinBox()
    scale_spin.setRange(10.0, 100000.0)
    scale_spin.setDecimals(0)
    scale_spin.setSingleStep(5.0)
    scale_spin.setSuffix("%")
    scale_spin.setMinimumWidth(78)
    scale_spin.valueChanged.connect(self._layout_controls_changed)

    reset = QPushButton("Reset")
    reset.setMinimumWidth(62)
    reset.clicked.connect(lambda checked=False, element=name: self._reset_layout_element(element))

    grid.addWidget(select, row, 0)
    grid.addWidget(visible, row, 1, Qt.AlignCenter)
    grid.addWidget(x_spin, row, 2)
    grid.addWidget(y_spin, row, 3)
    grid.addWidget(scale_spin, row, 4)
    grid.addWidget(reset, row, 5)
    self.layout_controls[name] = {"visible": visible, "x": x_spin, "y": y_spin, "scale": scale_spin}


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
            controls["scale"].setValue(float(getattr(element, "scale", 1.0)) * 100.0)
    finally:
        self._syncing_layout_controls = False
    self.selected_layout_label.setText(
        "Selected: {}. Drag to move, use corner handles to resize, or enter exact values.".format(
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
    return ElementLayout(
        controls["x"].value(),
        controls["y"].value(),
        controls["visible"].isChecked(),
        controls["scale"].value() / 100.0,
    )


def _preview_layout_changed(self, name: str, x: float, y: float, scale: float = 1.0) -> None:
    if name not in LAYOUT_LABELS:
        return
    self.selected_layout_element = name
    element = getattr(self.overlay_layout, name)
    setattr(self.overlay_layout, name, ElementLayout(x, y, element.visible, scale))
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
    warnings = _active_layout_warnings(self)
    message = ""
    if warnings:
        message = "Warnings:\n- " + "\n- ".join(warnings)
    self.status.setText(message)
    self.status.setVisible(bool(warnings))


def _active_layout_warnings(self) -> list[str]:
    warnings = layout_warnings(self.overlay_layout, self._current_canvas(), self._config())
    if not any(getattr(self.overlay_layout, name).visible for name in LAYOUT_LABELS):
        warnings.append("No overlay elements are visible. The rendered video will be blank.")
    return warnings


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
    if hasattr(self, "resolution_size_row"):
        self.resolution_size_row.setVisible(is_custom)
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


def create_animation(self) -> None:
    self.status.setVisible(True)
    _ORIGINAL_CREATE_ANIMATION(self)


def _render_finished(self, output_path: str) -> None:
    self.status.setVisible(True)
    _ORIGINAL_RENDER_FINISHED(self, output_path)


def _render_failed(self, message: str) -> None:
    self.status.setVisible(True)
    _ORIGINAL_RENDER_FAILED(self, message)


def _config(self, include_time: bool = True) -> RenderConfig:
    return replace(_ORIGINAL_CONFIG(self, include_time), layout=clone_overlay_layout(self.overlay_layout))
