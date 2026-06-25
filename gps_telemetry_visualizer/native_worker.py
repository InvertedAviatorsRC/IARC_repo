from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from gps_telemetry_visualizer.core import RenderConfig, render_animation


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
