"""PDF 미리보기에서 상대 좌표의 추출·재인식 영역과 실제 검출 다각형을 표시한다."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget

from .selection import Region


class PagePreview(QWidget):
    """확대율과 무관한 상대 영역을 선택할 수 있는 PDF 이미지 위젯이다."""

    region_changed = Signal(object)
    retry_region_changed = Signal(object)

    def __init__(self, parent=None):
        """빈 이미지·전체 영역·드래그 상태와 미리보기 위젯의 초기 크기를 설정한다."""
        super().__init__(parent)
        self.pixmap = QPixmap()
        self.region = Region()
        self.retry_region = None
        self.retry_mode = False
        self.polygons = []
        self.zoom = 1.0
        self.drag_start = None
        self.drag_end = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFixedSize(480, 600)

    def set_image(self, image):
        """PIL 이미지를 소유한 Qt 픽셀 데이터로 복사하고 현재 확대율을 적용한다."""
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
        """확대율과 표시 크기를 갱신하며 저장된 상대 선택 좌표는 유지한다."""
        self.zoom = value
        if not self.pixmap.isNull():
            self.setFixedSize(
                round(self.pixmap.width() * value) + 32,
                round(self.pixmap.height() * value) + 32,
            )
        self.update()

    def set_region(self, region):
        """상대 선택 영역을 갱신하고 다시 그리기를 요청한다."""
        self.region = region
        self.update()

    def clear_image(self):
        """이전 페이지 이미지와 진행 중 드래그를 비우고 다시 그린다."""
        self.pixmap = QPixmap()
        self.drag_start = self.drag_end = None
        self.retry_region = None
        self.polygons = []
        self.update()

    def set_polygons(self, polygons):
        """원시 OCR의 전체 페이지 상대 다각형을 표시용으로 복사한다."""
        for polygon in polygons:
            if len(polygon) < 3 or any(
                not math.isfinite(value) or not 0 <= value <= 1
                for point in polygon
                for value in point
            ):
                raise ValueError("검출 다각형은 유한한 0~1 상대 좌표여야 합니다.")
        self.polygons = [[QPointF(x, y) for x, y in polygon] for polygon in polygons]
        self.update()

    def set_retry_mode(self, enabled):
        """드래그 대상을 재인식으로 전환하며 기존 추출 영역은 유지한다."""
        self.retry_mode = enabled
        self.drag_start = self.drag_end = None
        self.update()

    def image_rect(self):
        """위젯 여백과 확대율을 반영한 페이지 이미지 표시 사각형을 반환한다."""
        return QRectF(
            16, 16, self.pixmap.width() * self.zoom, self.pixmap.height() * self.zoom
        )

    def relative_point(self, point):
        """표시 이미지 위 점을 0~1 상대 좌표로 바꾸고 경계 밖 값은 제한한다."""
        rect = self.image_rect()
        return QPointF(
            min(1, max(0, (point.x() - rect.left()) / rect.width())),
            min(1, max(0, (point.y() - rect.top()) / rect.height())),
        )

    def mousePressEvent(self, event):
        """이미지 안에서 시작한 왼쪽 클릭을 상대 좌표 드래그의 시작으로 기록한다."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self.pixmap.isNull()
            and self.image_rect().contains(event.position())
        ):
            self.drag_start = self.relative_point(event.position())
            self.drag_end = self.drag_start

    def mouseMoveEvent(self, event):
        """진행 중 드래그의 상대 끝점을 갱신하고 임시 선택을 다시 그린다."""
        if self.drag_start is not None:
            self.drag_end = self.relative_point(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        """충분한 크기의 드래그를 정규화한 영역으로 확정하고 선택 변경 신호를 보낸다."""
        if event.button() != Qt.MouseButton.LeftButton or self.drag_start is None:
            return
        end = self.relative_point(event.position())
        start = self.drag_start
        self.drag_start = self.drag_end = None
        if (
            abs(start.x() - end.x()) * self.image_rect().width() >= 3
            and abs(start.y() - end.y()) * self.image_rect().height() >= 3
        ):
            region = Region(
                min(start.x(), end.x()),
                min(start.y(), end.y()),
                max(start.x(), end.x()),
                max(start.y(), end.y()),
            )
            if self.retry_mode:
                self.retry_region = region
                self.retry_region_changed.emit(region)
            else:
                self.region = region
                self.region_changed.emit(region)
        self.update()

    def paintEvent(self, event):
        """빈 화면 또는 페이지 이미지와 저장·드래그 중 선택 영역을 그린다."""
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
        painter.setPen(QPen(QColor("#13845b"), 1))
        for polygon in self.polygons:
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(
                            target.left() + p.x() * target.width(),
                            target.top() + p.y() * target.height(),
                        )
                        for p in polygon
                    ]
                )
            )
        region = self.retry_region if self.retry_mode else self.region
        if region is None and self.drag_start is None:
            return
        region = region or Region()
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
