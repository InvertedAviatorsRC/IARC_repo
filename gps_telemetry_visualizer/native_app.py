from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from PySide6.QtCore import Qt, QThread, QTimer, Slot
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QUrl

from gps_telemetry_visualizer.core import (
    CanvasConfig,
    ElementLayout,
    OverlayLayout,
    RenderConfig,
    clone_overlay_layout,
    default_output_name,
    default_overlay_layout,
    detect_columns,
    prepare_telemetry,
    render_static_preview,
    scale_overlay_layout,
)
from gps_telemetry_visualizer.native_controls import CollapsibleSection, ColorControl, CsvDropZone
from gps_telemetry_visualizer.native_preview import LAYOUT_LABELS, PreviewCanvas
from gps_telemetry_visualizer.native_worker import RenderWorker
from gps_telemetry_visualizer.presets import (
    LayoutPreset,
    delete_layout_preset,
    load_layout_presets,
    save_layout_preset,
)


TIME_SLIDER_SCALE = 10
RESOLUTION_PRESETS = {
    "3840 x 2160 - 4K UHD": (3840, 2160),
    "2560 x 1440 - 1440p": (2560, 1440),
    "1920 x 1080 - 1080p": (1920, 1080),
    "1280 x 720 - 720p": (1280, 720),
    "1080 x 1920 - vertical 1080p": (1080, 1920),
    "2160 x 3840 - vertical 4K": (2160, 3840),
    "1080 x 1080 - square": (1080, 1080),
    "Custom": None,
}
SPEEDOMETER_STYLES = {
    "180° half gauge": "half",
    "90° corner gauge": "corner",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GPS Telemetry Visualizer")
        self.resize(1500, 860)
        self.setMinimumSize(1180, 720)

        self.csv_path = ""
        self.columns: list[str] = []
        self.render_thread: QThread | None = None
        self.render_worker: RenderWorker | None = None
        self.preview_frames: list[QPixmap] = []
        self.preview_frame_index = 0
        self.overlay_layout = default_overlay_layout(1920, 1080, "both")
        self.layout_canvas_width = 1920
        self.layout_canvas_height = 1080
        self.layout_controls: dict[str, dict[str, object]] = {}
        self._syncing_layout_controls = False
        self.selected_layout_element = "map"

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.refresh_preview)

        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QGridLayout(root)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setHorizontalSpacing(14)
        main_layout.setVerticalSpacing(0)
        main_layout.setColumnStretch(0, 0)
        main_layout.setColumnStretch(1, 1)
        main_layout.addWidget(self._build_controls_panel(), 0, 0)
        main_layout.addWidget(self._build_preview_panel(), 0, 1)

        self._connect_preview_signals()
        self._update_transparency_controls()
        self._reload_preset_menu()
        self._sync_layout_controls()
        self._update_preview_layout()

    def _build_controls_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("panel")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(390)
        scroll.setMaximumWidth(500)
        scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Controls")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        layout.addWidget(CollapsibleSection("CSV", self._build_file_group(), expanded=True))
        layout.addWidget(CollapsibleSection("Output", self._build_output_group(), expanded=True))
        layout.addWidget(CollapsibleSection("Resolution", self._build_resolution_group(), expanded=True))
        layout.addWidget(CollapsibleSection("Settings", self._build_settings_group(), expanded=True))
        layout.addWidget(CollapsibleSection("Colors", self._build_colors_group(), expanded=True))
        layout.addWidget(CollapsibleSection("Layout presets", self._build_presets_group(), expanded=True))
        layout.addWidget(CollapsibleSection("Elements", self._build_elements_group(), expanded=True))
        layout.addStretch()
        scroll.setWidget(panel)
        return scroll

    def _build_file_group(self) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.drop_zone = CsvDropZone()
        self.drop_zone.file_dropped.connect(self.set_csv_file)
        self.drop_zone.setMinimumHeight(118)
        self.drop_zone.setMaximumHeight(138)
        layout.addWidget(self.drop_zone)

        browse_csv = QPushButton("Browse CSV")
        browse_csv.clicked.connect(self.browse_csv)
        layout.addWidget(browse_csv)

        self.csv_label = QLabel("No CSV selected")
        self.csv_label.setWordWrap(True)
        self.csv_label.setObjectName("muted")
        layout.addWidget(self.csv_label)
        return group

    def _build_output_group(self) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        folder_row = QHBoxLayout()
        self.output_folder = QLineEdit(str(Path.cwd() / "output"))
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
        self.transparent.toggled.connect(self._update_background_controls)
        type_row.addWidget(QLabel("File type"))
        type_row.addWidget(self.file_type)
        type_row.addSpacing(10)
        type_row.addWidget(self.transparent)
        type_row.addStretch()
        layout.addLayout(type_row)

        self.output_name = QLineEdit(default_output_name("both", "mp4"))
        layout.addWidget(QLabel("Output file name"))
        layout.addWidget(self.output_name)
        return group

    def _build_resolution_group(self) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.resolution_preset = QComboBox()
        self.resolution_preset.addItems(list(RESOLUTION_PRESETS))
        self.resolution_preset.setCurrentText("1920 x 1080 - 1080p")
        self.resolution_preset.currentTextChanged.connect(self._resolution_changed)
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
        self._resolution_changed()
        return group

    def _build_settings_group(self) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        self.gps_col = _editable_combo("GPS")
        self.speed_col = _editable_combo("GSpd(kmh)")
        self.heading_col = _editable_combo("Hdg(°)")
        self.altitude_col = _editable_combo("Alt(m)")
        form.addRow("GPS column", self.gps_col)
        form.addRow("Speed column", self.speed_col)
        form.addRow("Heading column", self.heading_col)
        form.addRow("Altitude column", self.altitude_col)
        layout.addLayout(form)

        units_row = QHBoxLayout()
        self.speed_input_unit = QComboBox()
        self.speed_input_unit.addItems(["kmh", "mph", "ms"])
        self.speed_input_unit.setMaximumWidth(90)
        self.speed_output_unit = QComboBox()
        self.speed_output_unit.addItems(["mph", "kmh", "ms"])
        self.speed_output_unit.setMaximumWidth(90)
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
        self.fps.setMaximumWidth(80)
        self.seconds_between = QDoubleSpinBox()
        self.seconds_between.setRange(0.2, 3.0)
        self.seconds_between.setSingleStep(0.1)
        self.seconds_between.setValue(1.0)
        self.seconds_between.setMaximumWidth(90)
        timing_row.addWidget(QLabel("FPS"))
        timing_row.addWidget(self.fps)
        timing_row.addWidget(QLabel("GPS seconds"))
        timing_row.addWidget(self.seconds_between)
        timing_row.addStretch()
        layout.addLayout(timing_row)

        self.speedometer_style = QComboBox()
        self.speedometer_style.addItems(list(SPEEDOMETER_STYLES))
        layout.addWidget(QLabel("Speedometer style"))
        layout.addWidget(self.speedometer_style)

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

    def _build_colors_group(self) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.path_color = ColorControl("Path", "#00d5ff")
        self.dot_color = ColorControl("Position dot", "#ff3355")
        self.start_marker_color = ColorControl("Start star", "#ffd43b")
        self.speedometer_color = ColorControl("Speedometer", "#00d5ff")
        self.needle_color = ColorControl("Needle", "#ff3355")
        self.background_color = ColorControl("Background", "#101820")
        for control in (
            self.path_color,
            self.dot_color,
            self.start_marker_color,
            self.speedometer_color,
            self.needle_color,
            self.background_color,
        ):
            layout.addWidget(control)
        return group

    def _build_presets_group(self) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.preset_combo = QComboBox()
        layout.addWidget(self.preset_combo)
        self.preset_name = QLineEdit()
        self.preset_name.setPlaceholderText("Preset name")
        layout.addWidget(self.preset_name)

        row = QHBoxLayout()
        load = QPushButton("Load")
        load.clicked.connect(self._load_selected_preset)
        save = QPushButton("Save")
        save.clicked.connect(self._save_preset)
        delete = QPushButton("Delete")
        delete.clicked.connect(self._delete_selected_preset)
        row.addWidget(load)
        row.addWidget(save)
        row.addWidget(delete)
        layout.addLayout(row)

        reset = QPushButton("Reset layout")
        reset.clicked.connect(self._reset_layout)
        layout.addWidget(reset)
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

        grid = QGridLayout()
        grid.setHorizontalSpacing(7)
        grid.setVerticalSpacing(5)
        grid.addWidget(QLabel("Element"), 0, 0)
        grid.addWidget(QLabel("Show"), 0, 1)
        grid.addWidget(QLabel("X"), 0, 2)
        grid.addWidget(QLabel("Y"), 0, 3)
        grid.addWidget(QLabel("Scale"), 0, 4)
        for row, name in enumerate(LAYOUT_LABELS, start=1):
            self._add_layout_controls(grid, row, name)
        layout.addLayout(grid)
        return group

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        title = QLabel("Preview")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.preview = PreviewCanvas()
        self.preview.layout_changed.connect(self._preview_layout_changed)
        self.preview.selected_changed.connect(self._preview_selected_changed)
        layout.addWidget(self.preview, 1)

        self.playhead_time, self.playhead_time_label = _time_slider()
        self.start_time, self.start_time_label = _time_slider()
        self.end_time, self.end_time_label = _time_slider()
        self.playhead_time.valueChanged.connect(self._time_slider_changed)
        self.start_time.valueChanged.connect(self._time_slider_changed)
        self.end_time.valueChanged.connect(self._time_slider_changed)
        layout.addWidget(_labeled_slider_row("Preview position", self.playhead_time, self.playhead_time_label))
        layout.addWidget(_labeled_slider_row("Trim start", self.start_time, self.start_time_label))
        layout.addWidget(_labeled_slider_row("Trim end", self.end_time, self.end_time_label))

        self.create_button = QPushButton("Create")
        self.create_button.setObjectName("createButton")
        self.create_button.clicked.connect(self.create_animation)
        layout.addWidget(self.create_button)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        return panel

    def _add_layout_controls(self, grid: QGridLayout, row: int, name: str) -> None:
        select = QPushButton(LAYOUT_LABELS[name])
        select.setMinimumWidth(92)
        select.clicked.connect(lambda checked=False, element=name: self._preview_selected_changed(element))

        visible = QCheckBox()
        visible.toggled.connect(self._layout_controls_changed)

        x_spin = QDoubleSpinBox()
        x_spin.setRange(-20000, 20000)
        x_spin.setDecimals(1)
        x_spin.setSingleStep(1.0)
        x_spin.setMinimumWidth(80)
        x_spin.valueChanged.connect(self._layout_controls_changed)

        y_spin = QDoubleSpinBox()
        y_spin.setRange(-20000, 20000)
        y_spin.setDecimals(1)
        y_spin.setSingleStep(1.0)
        y_spin.setMinimumWidth(80)
        y_spin.valueChanged.connect(self._layout_controls_changed)

        scale_spin = QDoubleSpinBox()
        scale_spin.setRange(10.0, 100000.0)
        scale_spin.setDecimals(0)
        scale_spin.setSingleStep(5.0)
        scale_spin.setSuffix("%")
        scale_spin.setMinimumWidth(74)
        scale_spin.valueChanged.connect(self._layout_controls_changed)

        reset = QPushButton("Reset")
        reset.clicked.connect(lambda checked=False, element=name: self._reset_layout_element(element))

        grid.addWidget(select, row, 0)
        grid.addWidget(visible, row, 1, Qt.AlignCenter)
        grid.addWidget(x_spin, row, 2)
        grid.addWidget(y_spin, row, 3)
        grid.addWidget(scale_spin, row, 4)
        grid.addWidget(reset, row, 5)
        self.layout_controls[name] = {"visible": visible, "x": x_spin, "y": y_spin, "scale": scale_spin}

    def _connect_preview_signals(self) -> None:
        widgets = [
            self.gps_col,
            self.speed_col,
            self.heading_col,
            self.altitude_col,
            self.speed_input_unit,
            self.speed_output_unit,
            self.fps,
            self.seconds_between,
            self.playhead_time,
            self.start_time,
            self.end_time,
            self.auto_max_speed,
            self.max_speed,
            self.file_type,
            self.transparent,
            self.resolution_preset,
            self.output_width,
            self.output_height,
            self.speedometer_style,
        ]
        for widget in widgets:
            if hasattr(widget, "currentTextChanged"):
                widget.currentTextChanged.connect(self.schedule_preview)
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self.schedule_preview)
            if hasattr(widget, "toggled"):
                widget.toggled.connect(self.schedule_preview)

        for control in (
            self.path_color,
            self.dot_color,
            self.start_marker_color,
            self.speedometer_color,
            self.needle_color,
            self.background_color,
        ):
            control.color_changed.connect(self.schedule_preview)

        self.seconds_between.valueChanged.connect(lambda _: self._refresh_time_range(reset=False))
        self.speedometer_style.currentTextChanged.connect(self._speedometer_style_changed)

    def browse_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose CSV", str(Path.cwd()), "CSV files (*.csv)")
        if path:
            self.set_csv_file(path)

    def browse_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder", self.output_folder.text())
        if folder:
            self.output_folder.setText(folder)

    def set_csv_file(self, path: str) -> None:
        self.csv_path = path
        self.csv_label.setText(path)
        self.drop_zone.title.setText(Path(path).name)
        self.drop_zone.subtitle.setText("Drag a different CSV here to replace it")
        try:
            self.columns = list(pd.read_csv(path, nrows=0).columns)
            detected = detect_columns(self.columns)
            self._populate_combo(self.gps_col, detected.get("gps") or "GPS")
            self._populate_combo(self.speed_col, detected.get("speed") or "GSpd(kmh)")
            self._populate_combo(self.heading_col, detected.get("heading") or "Hdg(°)")
            self._populate_combo(self.altitude_col, detected.get("altitude") or "Alt(m)")
            self._refresh_time_range(reset=True)
            self.schedule_preview(immediate=True)
        except Exception as exc:
            QMessageBox.warning(self, "CSV Error", str(exc))

    def _populate_combo(self, combo: QComboBox, selected: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(self.columns)
        combo.setCurrentText(selected)
        combo.blockSignals(False)

    def schedule_preview(self, immediate: bool = False) -> None:
        if not self.csv_path:
            return
        self.preview_timer.start(20 if immediate else 350)

    def refresh_preview(self) -> None:
        if not self.csv_path:
            self.preview.clear_preview("Select a CSV to preview.")
            return

        try:
            render_config = self._config()
            data = prepare_telemetry(self.csv_path, render_config)
            preview_time = self.playhead_time.value() / TIME_SLIDER_SCALE
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
            self.preview_frames = [pixmap]
            self.preview.set_preview(pixmap, self.overlay_layout, self._current_canvas(), render_config)
            self.status.setText(
                "{} valid GPS rows. Preview {}. Trim {} to {}.".format(
                    data.valid_rows,
                    _format_seconds(self.playhead_time.value() / TIME_SLIDER_SCALE),
                    _format_seconds(data.start_time),
                    _format_seconds(data.end_time),
                )
            )
        except Exception as exc:
            self.preview.clear_preview("Preview unavailable.")
            self.status.setText(str(exc))

    def create_animation(self) -> None:
        if not self.csv_path:
            QMessageBox.warning(self, "Missing CSV", "Choose a CSV before creating the animation.")
            return
        output_folder = Path(self.output_folder.text()).expanduser()
        output_name = _with_extension(self.output_name.text(), self.file_type.currentText())
        output_path = str(output_folder / output_name)

        self.create_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status.setText("Rendering...")

        self.render_thread = QThread(self)
        self.render_worker = RenderWorker(self.csv_path, output_path, self._config())
        self.render_worker.moveToThread(self.render_thread)
        self.render_thread.started.connect(self.render_worker.run)
        self.render_worker.progress.connect(self._set_progress)
        self.render_worker.finished.connect(self._render_finished)
        self.render_worker.failed.connect(self._render_failed)
        self.render_worker.finished.connect(self.render_thread.quit)
        self.render_worker.failed.connect(self.render_thread.quit)
        self.render_thread.finished.connect(self.render_worker.deleteLater)
        self.render_thread.finished.connect(self.render_thread.deleteLater)
        self.render_thread.start()

    @Slot(int, int)
    def _set_progress(self, current: int, total: int) -> None:
        if total:
            self.progress.setValue(int((current / total) * 100))

    @Slot(str)
    def _render_finished(self, output_path: str) -> None:
        self.create_button.setEnabled(True)
        self.progress.setValue(100)
        self.status.setText("Created {}".format(output_path))
        reply = QMessageBox.information(
            self,
            "Created",
            "Created {}\n\nOpen the output folder?".format(output_path),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(output_path).parent)))

    @Slot(str)
    def _render_failed(self, message: str) -> None:
        self.create_button.setEnabled(True)
        self.status.setText(message)
        QMessageBox.critical(self, "Render Failed", message)

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
                controls["scale"].setValue(float(element.scale) * 100.0)
        finally:
            self._syncing_layout_controls = False
        self.selected_layout_label.setText(
            "Selected: {}. Drag to move; use corner handles to resize.".format(
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
        self.schedule_preview()

    def _preview_selected_changed(self, name: str) -> None:
        if name not in LAYOUT_LABELS:
            return
        self.selected_layout_element = name
        self.preview.set_selected(name)
        self._sync_layout_controls()

    def _reset_layout_element(self, name: str) -> None:
        defaults = default_overlay_layout(self.output_width.value(), self.output_height.value(), "both", self._speedometer_style())
        setattr(self.overlay_layout, name, getattr(defaults, name))
        self._sync_layout_controls()
        self._update_preview_layout()
        self.schedule_preview()

    def _reset_layout(self) -> None:
        self.overlay_layout = default_overlay_layout(
            self.output_width.value(),
            self.output_height.value(),
            "both",
            self._speedometer_style(),
        )
        self._sync_layout_controls()
        self._update_preview_layout()
        self.schedule_preview()

    def _resolution_changed(self) -> None:
        preset = RESOLUTION_PRESETS.get(self.resolution_preset.currentText())
        is_custom = preset is None
        old_width = getattr(self, "layout_canvas_width", self.output_width.value())
        old_height = getattr(self, "layout_canvas_height", self.output_height.value())
        self.output_width.setEnabled(is_custom)
        self.output_height.setEnabled(is_custom)
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
        self.schedule_preview()

    def _speedometer_style_changed(self) -> None:
        self._update_preview_layout()
        self.schedule_preview()

    def _file_type_changed(self) -> None:
        if self.output_name.text().startswith("telemetry_"):
            self.output_name.setText(default_output_name("both", self.file_type.currentText()))
        self._update_transparency_controls()
        self.schedule_preview()

    def _update_transparency_controls(self) -> None:
        is_mov = self.file_type.currentText() == "mov"
        if is_mov:
            self.transparent.setEnabled(True)
            self.transparent.setToolTip("MOV uses the ProRes 4444 codec, which supports alpha transparency.")
        else:
            self.transparent.blockSignals(True)
            self.transparent.setChecked(False)
            self.transparent.blockSignals(False)
            self.transparent.setEnabled(False)
            self.transparent.setToolTip("Transparent backgrounds are only available for MOV exports.")
        self._update_background_controls()

    def _update_background_controls(self) -> None:
        self.background_color.setVisible(not (self.transparent.isEnabled() and self.transparent.isChecked()))
        self.schedule_preview()

    def _time_slider_changed(self) -> None:
        sender = self.sender()
        if sender is self.start_time and self.start_time.value() >= self.end_time.value():
            self.end_time.setValue(min(self.start_time.maximum(), self.start_time.value() + 1))
        elif sender is self.end_time and self.end_time.value() <= self.start_time.value():
            self.start_time.setValue(max(self.end_time.minimum(), self.end_time.value() - 1))

        clamped_playhead = min(max(self.playhead_time.value(), self.start_time.value()), self.end_time.value())
        if clamped_playhead != self.playhead_time.value():
            self.playhead_time.blockSignals(True)
            self.playhead_time.setValue(clamped_playhead)
            self.playhead_time.blockSignals(False)

        self._update_time_labels()
        self.schedule_preview()

    def _refresh_time_range(self, reset: bool) -> None:
        if not self.csv_path:
            return
        try:
            data = prepare_telemetry(self.csv_path, self._config(include_time=False))
        except Exception:
            return
        max_tick = max(1, int(round(data.total_duration_seconds * TIME_SLIDER_SCALE)))
        current_start = self.start_time.value()
        current_end = self.end_time.value()
        current_playhead = self.playhead_time.value()
        if reset or current_end <= 1:
            current_start = 0
            current_end = max_tick
            current_playhead = 0
        else:
            current_start = min(current_start, max_tick - 1)
            current_end = min(max(current_end, current_start + 1), max_tick)
            current_playhead = min(max(current_playhead, current_start), current_end)
        for slider, value in (
            (self.playhead_time, current_playhead),
            (self.start_time, current_start),
            (self.end_time, current_end),
        ):
            slider.blockSignals(True)
            slider.setRange(0, max_tick)
            slider.setEnabled(data.total_duration_seconds > 0)
            slider.setValue(value)
            slider.blockSignals(False)
        self._update_time_labels()

    def _update_time_labels(self) -> None:
        self.playhead_time_label.setText(_format_seconds(self.playhead_time.value() / TIME_SLIDER_SCALE))
        self.start_time_label.setText(_format_seconds(self.start_time.value() / TIME_SLIDER_SCALE))
        self.end_time_label.setText(_format_seconds(self.end_time.value() / TIME_SLIDER_SCALE))

    def _reload_preset_menu(self) -> None:
        self._presets = load_layout_presets()
        current = self.preset_combo.currentText() if hasattr(self, "preset_combo") else ""
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("")
        self.preset_combo.addItems(sorted(self._presets))
        if current in self._presets:
            self.preset_combo.setCurrentText(current)
        self.preset_combo.blockSignals(False)

    def _save_preset(self) -> None:
        name = self.preset_name.text().strip() or self.preset_combo.currentText().strip()
        if not name:
            QMessageBox.warning(self, "Preset name", "Enter a preset name before saving.")
            return
        save_layout_preset(
            LayoutPreset(
                name,
                self.output_width.value(),
                self.output_height.value(),
                clone_overlay_layout(self.overlay_layout),
                self._speedometer_style(),
            )
        )
        self._reload_preset_menu()
        self.preset_combo.setCurrentText(name)
        self.status.setText("Saved preset {}".format(name))

    def _load_selected_preset(self) -> None:
        name = self.preset_combo.currentText()
        preset = self._presets.get(name)
        if not preset:
            return
        self._set_resolution(preset.output_width, preset.output_height)
        self.speedometer_style.setCurrentText(_style_label(preset.speedometer_style))
        self.overlay_layout = clone_overlay_layout(preset.layout)
        self._sync_layout_controls()
        self._update_preview_layout()
        self.schedule_preview()

    def _delete_selected_preset(self) -> None:
        name = self.preset_combo.currentText()
        if not name:
            return
        delete_layout_preset(name)
        self._reload_preset_menu()
        self.status.setText("Deleted preset {}".format(name))

    def _set_resolution(self, width: int, height: int) -> None:
        label = next((name for name, size in RESOLUTION_PRESETS.items() if size == (width, height)), "Custom")
        self.resolution_preset.setCurrentText(label)
        self.output_width.setValue(width)
        self.output_height.setValue(height)

    def _config(self, include_time: bool = True) -> RenderConfig:
        transparent = self.file_type.currentText() == "mov" and self.transparent.isChecked()
        start_time = self.start_time.value() / TIME_SLIDER_SCALE if include_time and self.start_time.isEnabled() else 0.0
        end_time = self.end_time.value() / TIME_SLIDER_SCALE if include_time and self.end_time.isEnabled() else None
        return RenderConfig(
            export_mode="both",
            fps=self.fps.value(),
            seconds_between_gps_points=self.seconds_between.value(),
            gps_col=self.gps_col.currentText(),
            speed_col=self.speed_col.currentText(),
            heading_col=self.heading_col.currentText(),
            altitude_col=self.altitude_col.currentText(),
            speed_input_unit=self.speed_input_unit.currentText(),
            speed_output_unit=self.speed_output_unit.currentText(),
            max_speed=None if self.auto_max_speed.isChecked() else self.max_speed.value(),
            path_color=self.path_color.color,
            dot_color=self.dot_color.color,
            start_marker_color=self.start_marker_color.color,
            speedometer_color=self.speedometer_color.color,
            needle_color=self.needle_color.color,
            speedometer_style=self._speedometer_style(),
            background_color=self.background_color.color,
            transparent=transparent,
            start_time=start_time,
            end_time=end_time,
            output_width=self.output_width.value(),
            output_height=self.output_height.value(),
            layout=clone_overlay_layout(self.overlay_layout),
        )

    def _speedometer_style(self) -> str:
        return SPEEDOMETER_STYLES.get(self.speedometer_style.currentText(), "half")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("GPS Telemetry Visualizer")
    app.setStyleSheet(_stylesheet())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


def _editable_combo(default: str) -> QComboBox:
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItem(default)
    combo.setCurrentText(default)
    combo.setMinimumWidth(175)
    return combo


def _time_slider() -> tuple[QSlider, QLabel]:
    slider = QSlider(Qt.Horizontal)
    slider.setRange(0, 1)
    slider.setEnabled(False)
    label = QLabel("0.0s")
    label.setObjectName("muted")
    label.setMinimumWidth(48)
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return slider, label


def _labeled_slider_row(title: str, slider: QSlider, label: QLabel) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    title_label = QLabel(title)
    title_label.setObjectName("muted")
    title_label.setMinimumWidth(112)
    layout.addWidget(title_label)
    layout.addWidget(slider, 1)
    layout.addWidget(label)
    return row


def _style_label(style: str) -> str:
    for label, value in SPEEDOMETER_STYLES.items():
        if value == style:
            return label
    return "180° half gauge"


def _format_seconds(seconds: float) -> str:
    minutes = int(seconds // 60)
    remaining = seconds - minutes * 60
    if minutes:
        return "{}:{:04.1f}".format(minutes, remaining)
    return "{:.1f}s".format(remaining)


def _with_extension(name: str, extension: str) -> str:
    root, _ = os.path.splitext(name.strip())
    if not root:
        root = "telemetry_output"
    return root + "." + extension.lstrip(".")


def _stylesheet() -> str:
    return """
    QWidget {
        background: #0f141c;
        color: #e8edf3;
        font-size: 13px;
    }
    QMainWindow {
        background: #0f141c;
    }
    QWidget#panel, QScrollArea#panel {
        background: #151b24;
        border: 1px solid #252f3d;
        border-radius: 10px;
    }
    QScrollArea {
        border: none;
    }
    QLabel#sectionTitle {
        font-size: 18px;
        font-weight: 700;
        color: #f5f8fb;
        margin-bottom: 6px;
    }
    QLabel#muted {
        color: #9aa6b5;
    }
    QFrame#dropZone, QLabel#preview {
        border: 1px dashed #4d6d8d;
        border-radius: 8px;
        background: #0b1017;
    }
    QLabel#dropTitle {
        font-size: 19px;
        font-weight: 700;
        background: transparent;
    }
    QLabel#dropSubtitle {
        color: #9aa6b5;
        background: transparent;
    }
    QPushButton {
        background: #1d2733;
        border: 1px solid #334155;
        border-radius: 7px;
        padding: 7px 10px;
    }
    QPushButton:hover {
        background: #263342;
    }
    QPushButton#createButton {
        background: #2563eb;
        border-color: #3b82f6;
        font-weight: 700;
        min-height: 34px;
    }
    QPushButton#sectionToggle {
        text-align: left;
        font-weight: 700;
        background: #111827;
    }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: #0b1017;
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 5px;
        min-height: 24px;
    }
    QCheckBox {
        spacing: 6px;
    }
    QProgressBar {
        border: 1px solid #334155;
        border-radius: 6px;
        text-align: center;
        background: #0b1017;
    }
    QProgressBar::chunk {
        background: #22c55e;
        border-radius: 5px;
    }
    """


if __name__ == "__main__":
    main()
