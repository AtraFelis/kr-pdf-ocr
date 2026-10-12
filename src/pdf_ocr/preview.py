"""PDF image display with zoom-independent rectangular selections."""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .selection import Region


class PagePreview(QWidget):
    region_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = QPixmap()
        self.region = Region()
        self.zoom = 1.0
        self.drag_start = None
        self.drag_end = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFixedSize(480, 600)

    def set_image(self, image):
        rgb = image.convert("RGB")
        data = rgb.tobytes()
        self.pixmap = QPixmap.fromImage(
            QImage(
                data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888
            ).copy()
        )
        rgb.close()
        self.set_zoom(self.zoom)

    def set_zoom(self, value):
        self.zoom = value
        if not self.pixmap.isNull():
            self.setFixedSize(
                round(self.pixmap.width() * value) + 32,
                round(self.pixmap.height() * value) + 32,
            )
        self.update()

    def set_region(self, region):
        self.region = region
        self.update()

    def clear_image(self):
        self.pixmap = QPixmap()
        self.drag_start = self.drag_end = None
        self.update()

    def image_rect(self):
        return QRectF(
            16, 16, self.pixmap.width() * self.zoom, self.pixmap.height() * self.zoom
        )

    def relative_point(self, point):
        rect = self.image_rect()
        return QPointF(
            min(1, max(0, (point.x() - rect.left()) / rect.width())),
            min(1, max(0, (point.y() - rect.top()) / rect.height())),
        )

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self.pixmap.isNull()
            and self.image_rect().contains(event.position())
        ):
            self.drag_start = self.relative_point(event.position())
            self.drag_end = self.drag_start

    def mouseMoveEvent(self, event):
        if self.drag_start is not None:
            self.drag_end = self.relative_point(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.drag_start is None:
            return
        end = self.relative_point(event.position())
        start = self.drag_start
        self.drag_start = self.drag_end = None
        if (
            abs(start.x() - end.x()) * self.image_rect().width() >= 3
            and abs(start.y() - end.y()) * self.image_rect().height() >= 3
        ):
            self.region = Region(
                min(start.x(), end.x()),
                min(start.y(), end.y()),
                max(start.x(), end.x()),
                max(start.y(), end.y()),
            )
            self.region_changed.emit(self.region)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#edf1f7"))
        if self.pixmap.isNull():
            painter.setPen(QColor("#64748b"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "PDF를 열면 페이지가 표시됩니다.",
            )
            return
        target = self.image_rect()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
        region = self.region
        relative = QRectF(
            region.left,
            region.top,
            region.right - region.left,
            region.bottom - region.top,
        )
        if self.drag_start is not None:
            relative = QRectF(self.drag_start, self.drag_end).normalized()
        selection = QRectF(
            target.left() + relative.left() * target.width(),
            target.top() + relative.top() * target.height(),
            relative.width() * target.width(),
            relative.height() * target.height(),
        )
        painter.fillRect(selection, QColor(49, 92, 235, 25))
        painter.setPen(QPen(QColor("#315ceb"), 2))
        painter.drawRect(selection)
