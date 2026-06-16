from __future__ import annotations

import os
import sys
import io
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSlider,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from gps_telemetry_visualizer.core import (
    RenderConfig,
    default_output_name,
    detect_columns,
    prepare_telemetry,
    render_animation,
    render_static_preview,
)


TIME_SLIDER_SCALE = 10


class CsvDropZone(QFrame):
    file_dropped = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropZone")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self.title = QLabel("Drop CSV Here")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setObjectName("dropTitle")
        self.subtitle = QLabel("or use Browse CSV")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setObjectName("dropSubtitle")
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._has_csv(event):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path.lower().endswith(".csv"):
            self.file_dropped.emit(path)
            event.acceptProposedAction()

    @staticmethod
    def _has_csv(event: QDragEnterEvent) -> bool:
        return any(url.toLocalFile().lower().endswith(".csv") for url in event.mimeData().urls())


class ColorButton(QPushButton):
    color_changed = Signal(str)

    def __init__(self, label: str, color: str) -> None:
        super().__init__(label)
        self._label = label
        self._color = color
        self.clicked.connect(self._choose_color)
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
        self.setText("{}  {}".format(self._label, self._color))
        self.setMinimumHeight(36)
        self.setStyleSheet(
            "QPushButton {{ border: 1px solid #536071; border-radius: 7px; padding: 7px; "
            "background: {}; color: {}; }}".format(self._color, _contrast_text(self._color))
        )


class RenderWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, csv_path: str, output_path: str, config: RenderConfig) -> None:
        super().__init__()
        self.csv_path = csv_path
        self.output_path = output_path
        self.config = config

    @Slot()
    def run(self) -> None:
        try:
            rendered = render_animation(
                self.csv_path,
                self.output_path,
                self.config,
                progress_callback=lambda current, total: self.progress.emit(current, total),
            )
            self.finished.emit(str(rendered))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GPS Telemetry Visualizer")
        self.resize(1380, 760)
        self.setMinimumSize(1180, 680)

        self.csv_path = ""
        self.columns = []
        self.render_thread = None
        self.render_worker = None
        self.preview_frames = []
        self.preview_frame_index = 0
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.refresh_preview)
        self.preview_playback_timer = QTimer(self)
        self.preview_playback_timer.timeout.connect(self._advance_preview_frame)

        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QGridLayout(root)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setHorizontalSpacing(18)
        main_layout.setVerticalSpacing(0)
        main_layout.setColumnStretch(0, 1)
        main_layout.setColumnStretch(1, 1)
        main_layout.setColumnStretch(2, 3)

        main_layout.addWidget(self._build_file_panel(), 0, 0)
        main_layout.addWidget(self._build_settings_panel(), 0, 1)
        main_layout.addWidget(self._build_preview_panel(), 0, 2)

        self._connect_preview_signals()
        self._update_transparency_controls()

    def _build_file_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("panel")
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(360)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("CSV")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.drop_zone = CsvDropZone()
        self.drop_zone.file_dropped.connect(self.set_csv_file)
        self.drop_zone.setMinimumHeight(170)
        layout.addWidget(self.drop_zone)

        browse_csv = QPushButton("Browse CSV")
        browse_csv.clicked.connect(self.browse_csv)
        layout.addWidget(browse_csv)

        self.csv_label = QLabel("No CSV selected")
        self.csv_label.setWordWrap(True)
        self.csv_label.setObjectName("muted")
        layout.addWidget(self.csv_label)

        layout.addSpacing(20)
        output_title = QLabel("Output")
        output_title.setObjectName("sectionTitle")
        layout.addWidget(output_title)

        folder_row = QHBoxLayout()
        self.output_folder = QLineEdit(str(Path.cwd() / "output"))
        browse_folder = QPushButton("Browse")
        browse_folder.clicked.connect(self.browse_output_folder)
        folder_row.addWidget(self.output_folder)
        folder_row.addWidget(browse_folder)
        layout.addLayout(folder_row)

        self.file_type = QComboBox()
        self.file_type.addItems(["mp4", "mov"])
        self.file_type.currentTextChanged.connect(self._file_type_changed)
        layout.addWidget(QLabel("File type"))
        layout.addWidget(self.file_type)

        self.output_name = QLineEdit(default_output_name("both", "mp4"))
        layout.addWidget(QLabel("Output file name"))
        layout.addWidget(self.output_name)

        layout.addStretch()
        return panel

    def _build_settings_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("panel")
        panel.setMinimumWidth(330)
        panel.setMaximumWidth(390)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Settings")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        self.export_mode = QComboBox()
        self.export_mode.addItems(["both", "map", "speedometer"])
        self.export_mode.currentTextChanged.connect(self._sync_output_name_extension)
        _set_control_width(self.export_mode)
        form.addRow("Output", self.export_mode)

        self.gps_col = _editable_combo("GPS")
        self.speed_col = _editable_combo("GSpd(kmh)")
        self.heading_col = _editable_combo("Hdg(°)")
        self.altitude_col = _editable_combo("Alt(m)")
        form.addRow("GPS column", self.gps_col)
        form.addRow("Speed column", self.speed_col)
        form.addRow("Heading column", self.heading_col)
        form.addRow("Altitude column", self.altitude_col)

        self.speed_input_unit = QComboBox()
        self.speed_input_unit.addItems(["kmh", "mph", "ms"])
        self.speed_output_unit = QComboBox()
        self.speed_output_unit.addItems(["mph", "kmh", "ms"])
        _set_control_width(self.speed_input_unit)
        _set_control_width(self.speed_output_unit)
        form.addRow("Input speed unit", self.speed_input_unit)
        form.addRow("Output speed unit", self.speed_output_unit)

        self.fps = QSpinBox()
        self.fps.setRange(10, 60)
        self.fps.setSingleStep(5)
        self.fps.setValue(30)
        _set_control_width(self.fps)
        form.addRow("FPS", self.fps)

        self.seconds_between = QDoubleSpinBox()
        self.seconds_between.setRange(0.2, 3.0)
        self.seconds_between.setSingleStep(0.1)
        self.seconds_between.setValue(1.0)
        _set_control_width(self.seconds_between)
        form.addRow("Seconds between GPS points", self.seconds_between)

        self.auto_max_speed = QCheckBox("Auto max speed")
        self.auto_max_speed.setChecked(True)
        self.auto_max_speed.toggled.connect(lambda checked: self.max_speed.setEnabled(not checked))
        form.addRow("", self.auto_max_speed)

        self.max_speed = QDoubleSpinBox()
        self.max_speed.setRange(1.0, 500.0)
        self.max_speed.setSingleStep(5.0)
        self.max_speed.setValue(60.0)
        self.max_speed.setEnabled(False)
        _set_control_width(self.max_speed)
        form.addRow("Max speed", self.max_speed)

        layout.addLayout(form)
        layout.addStretch()
        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        title = QLabel("Preview")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.preview = QLabel("Select a CSV to preview.")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(460, 360)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setObjectName("preview")
        layout.addWidget(self.preview, 1)

        timeline_title = QLabel("Timeline")
        timeline_title.setObjectName("subsectionTitle")
        layout.addWidget(timeline_title)

        self.playhead_time, self.playhead_time_label = _time_slider()
        self.start_time, self.start_time_label = _time_slider()
        self.end_time, self.end_time_label = _time_slider()
        self.playhead_time.setToolTip("Scrub the preview frame without changing the export range.")
        self.start_time.setToolTip("Set where the rendered export should start.")
        self.end_time.setToolTip("Set where the rendered export should end.")
        self.playhead_time.valueChanged.connect(self._time_slider_changed)
        self.start_time.valueChanged.connect(self._time_slider_changed)
        self.end_time.valueChanged.connect(self._time_slider_changed)
        layout.addWidget(_labeled_slider_row("Preview position", self.playhead_time, self.playhead_time_label))
        layout.addWidget(_labeled_slider_row("Trim start", self.start_time, self.start_time_label))
        layout.addWidget(_labeled_slider_row("Trim end", self.end_time, self.end_time_label))

        colors_title = QLabel("Colors")
        colors_title.setObjectName("subsectionTitle")
        layout.addWidget(colors_title)

        color_grid = QGridLayout()
        color_grid.setHorizontalSpacing(10)
        color_grid.setVerticalSpacing(8)
        self.path_color = ColorButton("Path", "#00d5ff")
        self.speedometer_color = ColorButton("Speedometer", "#00d5ff")
        self.start_marker_color = ColorButton("Start star", "#ffd43b")
        self.dot_color = ColorButton("Position dot", "#ff3355")
        self.needle_color = ColorButton("Needle", "#ff3355")
        self.background_color = ColorButton("Background", "#101820")
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

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        return panel

    def _connect_preview_signals(self) -> None:
        widgets = [
            self.export_mode,
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
        ]
        for widget in widgets:
            if hasattr(widget, "currentTextChanged"):
                widget.currentTextChanged.connect(self.schedule_preview)
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self.schedule_preview)
            if hasattr(widget, "toggled"):
                widget.toggled.connect(self.schedule_preview)

        for button in [
            self.path_color,
            self.speedometer_color,
            self.start_marker_color,
            self.dot_color,
            self.needle_color,
            self.background_color,
        ]:
            button.color_changed.connect(self.schedule_preview)

        self.seconds_between.valueChanged.connect(lambda _: self._refresh_time_range(reset=False))

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
            self.schedule_preview()
        except Exception as exc:
            QMessageBox.warning(self, "CSV Error", str(exc))

    def _populate_combo(self, combo: QComboBox, selected: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(self.columns)
        combo.setCurrentText(selected)
        combo.blockSignals(False)

    def schedule_preview(self) -> None:
        if self.csv_path:
            self.preview_timer.start(450)

    def _show_preview_frame(self) -> None:
        if not self.preview_frames:
            return
        pixmap = self.preview_frames[self.preview_frame_index]
        scaled = pixmap.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(scaled)

    def _advance_preview_frame(self) -> None:
        if not self.preview_frames:
            self.preview_playback_timer.stop()
            return
        self.preview_frame_index = (self.preview_frame_index + 1) % len(self.preview_frames)
        self._show_preview_frame()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._show_preview_frame()

    def _time_slider_changed(self) -> None:
        sender = self.sender()
        if sender is self.start_time and self.start_time.value() >= self.end_time.value():
            if self.start_time.value() < self.start_time.maximum():
                self.end_time.blockSignals(True)
                self.end_time.setValue(self.start_time.value() + 1)
                self.end_time.blockSignals(False)
            else:
                self.start_time.blockSignals(True)
                self.start_time.setValue(max(self.start_time.minimum(), self.end_time.value() - 1))
                self.start_time.blockSignals(False)
        elif sender is self.end_time and self.end_time.value() <= self.start_time.value():
            if self.end_time.value() > self.end_time.minimum():
                self.start_time.blockSignals(True)
                self.start_time.setValue(self.end_time.value() - 1)
                self.start_time.blockSignals(False)
            else:
                self.end_time.blockSignals(True)
                self.end_time.setValue(min(self.end_time.maximum(), self.start_time.value() + 1))
                self.end_time.blockSignals(False)

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

    def refresh_preview(self) -> None:
        self.preview_playback_timer.stop()
        self.preview_frames = []
        self.preview_frame_index = 0

        if not self.csv_path:
            self.preview.setText("Select a CSV to preview.")
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
            self.preview_frames.append(pixmap)

            self._show_preview_frame()

            self.status.setText(
                "{} valid GPS rows from {} total rows. Previewing {}. Export trim: {} to {}. Max speed: {:.1f} {}.".format(
                    data.valid_rows,
                    data.source_rows,
                    _format_seconds(self.playhead_time.value() / TIME_SLIDER_SCALE),
                    _format_seconds(data.start_time),
                    _format_seconds(data.end_time),
                    data.max_speed,
                    self.speed_output_unit.currentText().upper(),
                )
            )
        except Exception as exc:
            self.preview.setText("Preview unavailable.")
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
        QMessageBox.information(self, "Created", "Created {}".format(output_path))

    @Slot(str)
    def _render_failed(self, message: str) -> None:
        self.create_button.setEnabled(True)
        self.status.setText(message)
        QMessageBox.critical(self, "Render Failed", message)

    def _sync_output_name_extension(self) -> None:
        if not self.output_name.text().strip() or self.output_name.text().startswith("telemetry_"):
            self.output_name.setText(default_output_name(self.export_mode.currentText(), self.file_type.currentText()))

    def _file_type_changed(self) -> None:
        self._sync_output_name_extension()
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

    def _config(self, include_time: bool = True) -> RenderConfig:
        transparent = self.file_type.currentText() == "mov" and self.transparent.isChecked()
        start_time = self.start_time.value() / TIME_SLIDER_SCALE if include_time and self.start_time.isEnabled() else 0.0
        end_time = self.end_time.value() / TIME_SLIDER_SCALE if include_time and self.end_time.isEnabled() else None
        return RenderConfig(
            export_mode=self.export_mode.currentText(),
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
            background_color=self.background_color.color,
            transparent=transparent,
            start_time=start_time,
            end_time=end_time,
        )


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
    _set_control_width(combo)
    return combo


def _set_control_width(widget: QWidget) -> None:
    widget.setMinimumWidth(190)
    widget.setMaximumWidth(190)


def _time_slider() -> tuple[QSlider, QLabel]:
    slider = QSlider(Qt.Horizontal)
    slider.setRange(0, 1)
    slider.setEnabled(False)
    slider.setMinimumWidth(190)
    label = QLabel("0.0s")
    label.setObjectName("muted")
    label.setMinimumWidth(46)
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return slider, label


def _labeled_slider_row(title: str, slider: QSlider, label: QLabel) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    title_label = QLabel(title)
    title_label.setObjectName("muted")
    title_label.setMinimumWidth(104)
    layout.addWidget(title_label)
    layout.addWidget(slider, 1)
    layout.addWidget(label)
    return row


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


def _contrast_text(color: str) -> str:
    value = QColor(color)
    brightness = (value.red() * 299 + value.green() * 587 + value.blue() * 114) / 1000
    return "#101820" if brightness > 150 else "#ffffff"


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
    QWidget#panel {
        background: #151b24;
        border: 1px solid #252f3d;
        border-radius: 10px;
    }
    QLabel#sectionTitle {
        font-size: 18px;
        font-weight: 700;
        color: #f5f8fb;
        margin-bottom: 8px;
    }
    QLabel#subsectionTitle {
        font-size: 14px;
        font-weight: 700;
        color: #d6dce4;
        margin-top: 4px;
    }
    QLabel#muted {
        color: #9aa6b5;
    }
    QFrame#dropZone, QLabel#preview {
        border: 1px dashed #4d6d8d;
        border-radius: 8px;
        background: #0b1017;
        min-height: 180px;
    }
    QLabel#dropTitle {
        font-size: 20px;
        font-weight: 700;
        background: transparent;
    }
    QLabel#dropSubtitle {
        color: #98a5b6;
        background: transparent;
    }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: #0b1017;
        color: #edf2f7;
        border: 1px solid #3a4655;
        border-radius: 6px;
        padding: 6px;
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
        border: 1px solid #38bdf8;
    }
    QComboBox::drop-down {
        border: none;
        width: 24px;
    }
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
        width: 18px;
        background: #111926;
        border: none;
    }
    QPushButton {
        background: #1d2633;
        color: #edf2f7;
        border: 1px solid #3a4655;
        border-radius: 6px;
        padding: 8px 10px;
    }
    QPushButton:hover {
        background: #253246;
    }
    QPushButton#createButton {
        background: #0ea5e9;
        color: #ffffff;
        font-weight: 700;
        padding: 12px;
    }
    QPushButton#createButton:disabled {
        background: #426277;
    }
    QCheckBox {
        spacing: 8px;
        color: #d6dce4;
    }
    QProgressBar {
        background: #0b1017;
        border: 1px solid #3a4655;
        border-radius: 6px;
        height: 8px;
        text-align: center;
    }
    QProgressBar::chunk {
        background: #0ea5e9;
        border-radius: 5px;
    }
    """


if __name__ == "__main__":
    main()
