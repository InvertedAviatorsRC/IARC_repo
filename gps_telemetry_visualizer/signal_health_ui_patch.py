from __future__ import annotations

from PySide6.QtWidgets import QCheckBox

from gps_telemetry_visualizer import core, native_preview
from gps_telemetry_visualizer.signal_health_layout_patch import NAME, ensure_signal_layout

_DONE = False


def install(native_app) -> None:
    global _DONE
    native_preview.LAYOUT_LABELS[NAME] = "Signal health"
    native_app.LAYOUT_LABELS[NAME] = "Signal health"
    native_app.default_overlay_layout = core.default_overlay_layout
    native_app.clone_overlay_layout = core.clone_overlay_layout
    native_app.scale_overlay_layout = core.scale_overlay_layout
    if _DONE:
        return

    build_settings = native_app.MainWindow._build_settings_group
    connect_signals = native_app.MainWindow._connect_preview_signals
    make_config = native_app.MainWindow._config
    sync_controls = native_app.MainWindow._sync_layout_controls
    controls_changed = native_app.MainWindow._layout_controls_changed

    def _build_settings_group(self):
        group = build_settings(self)
        self.signal_health_checkbox = QCheckBox("Signal health overlay")
        self.signal_health_checkbox.setChecked(False)
        self.signal_color_checkbox = QCheckBox("Color-code signal bars")
        self.signal_color_checkbox.setChecked(True)
        group.layout().addWidget(self.signal_health_checkbox)
        group.layout().addWidget(self.signal_color_checkbox)
        return group

    def _connect_preview_signals(self):
        connect_signals(self)
        self.signal_health_checkbox.toggled.connect(self.schedule_preview)
        self.signal_health_checkbox.toggled.connect(self._update_preview_layout)
        self.signal_color_checkbox.toggled.connect(self.schedule_preview)

    def _config(self, include_time=True):
        ensure_signal_layout(self.overlay_layout, self.output_width.value(), self.output_height.value())
        config = make_config(self, include_time)
        config.show_signal_health = self.signal_health_checkbox.isChecked()
        config.signal_bars_color_mode = "color" if self.signal_color_checkbox.isChecked() else "white"
        config.layout = core.clone_overlay_layout(self.overlay_layout)
        return config

    def _sync_layout_controls(self):
        ensure_signal_layout(self.overlay_layout, self.output_width.value(), self.output_height.value())
        sync_controls(self)

    def _layout_controls_changed(self):
        controls_changed(self)
        if NAME in self.layout_controls:
            setattr(self.overlay_layout, NAME, self._layout_from_controls(NAME))
            self._update_preview_layout()
            self.schedule_preview()

    native_app.MainWindow._build_settings_group = _build_settings_group
    native_app.MainWindow._connect_preview_signals = _connect_preview_signals
    native_app.MainWindow._config = _config
    native_app.MainWindow._sync_layout_controls = _sync_layout_controls
    native_app.MainWindow._layout_controls_changed = _layout_controls_changed
    _DONE = True
