from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy

from gps_telemetry_visualizer.core import (
    CanvasConfig,
    OverlayLayout,
    RenderConfig,
    compute_layout_bounds,
    default_overlay_layout,
    resize_layout_element_from_corner,
)


LAYOUT_LABELS = {
    "map": "Map",
    "speedometer": "Speedometer",
    "top_speed": "Top speed",
    "furthest_distance": "Furthest distance",
}


class PreviewCanvas(QLabel):
    layout_changed = Signal(str, float, float, float)
    selected_changed = Signal(str)

    HANDLE_SIZE = 12

    def __init__(self) -> None:
        super().__init__("Select a CSV to preview.")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(720, 500)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setObjectName("preview")
        self.setMouseTracking(True)

        self._pixmap: QPixmap | None = None
        self._layout = default_overlay_layout(1920, 1080, "both")
        self._canvas = CanvasConfig(1920, 1080)
        self._config = RenderConfig()
        self._selected = "map"
        self._dragging = False
        self._drag_mode = "move"
        self._resize_corner: str | None = None

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
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor("#0b1017"))
            painter.setPen(QColor("#9aa6b5"))
            painter.drawText(self.rect(), Qt.AlignCenter, self.text())
            painter.end()
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
            painter.setBrush(Qt.NoBrush)
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
        if selected is None:
            return
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
        return {name: QRectF(point.x() - half, point.y() - half, size, size) for name, point in points.items()}

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
