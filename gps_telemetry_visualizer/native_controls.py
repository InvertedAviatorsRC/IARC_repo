from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QColorDialog
from PySide6.QtCore import Qt


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
        if any(url.toLocalFile().lower().endswith(".csv") for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path.lower().endswith(".csv"):
            self.file_dropped.emit(path)
            event.acceptProposedAction()


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


class ColorControl(QWidget):
    color_changed = Signal(str)

    def __init__(self, label: str, color: str) -> None:
        super().__init__()
        self._label = label
        self._color = color
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        self.label = QLabel(label)
        self.label.setMinimumWidth(96)
        self.swatch = QPushButton("")
        self.swatch.setObjectName("colorSwatch")
        self.swatch.setFixedSize(30, 24)
        self.swatch.clicked.connect(self._choose_color)
        self.value = QLabel(color.upper())
        self.value.setObjectName("muted")
        self.value.setMinimumWidth(76)

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
