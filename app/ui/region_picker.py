"""全屏框选识别区域。"""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .. import screen


class RegionPicker(QWidget):
    picked = Signal(tuple)  # (left, top, width, height) 物理像素
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("框选识别区域")
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        self._origin = None
        self._cur = None
        self._sel = QRect()

        virt = QRect()
        for s in QGuiApplication.screens():
            virt = virt.united(s.geometry())
        self.setGeometry(virt)
        self._mon = screen.monitors()[0]

    # ------------------------------------------------------------------
    def start(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._cur = self._origin
            self._sel = QRect(self._origin, self._origin)
            self.update()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._origin is not None:
            self._cur = event.position().toPoint()
            self._sel = QRect(self._origin, self._cur).normalized()
            self.update()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        self._sel = QRect(self._origin, event.position().toPoint()).normalized()
        if self._sel.width() < 20 or self._sel.height() < 20:
            self._origin = None
            self._sel = QRect()
            self.update()
            self.cancelled.emit()
            self.close()
            return
        self._finish()

    # ------------------------------------------------------------------
    def _to_physical(self, r: QRect) -> tuple[int, int, int, int]:
        win_w = max(1, self.width())
        win_h = max(1, self.height())
        sx = self._mon["width"] / win_w
        sy = self._mon["height"] / win_h
        left = int(self._mon["left"] + r.left() * sx)
        top = int(self._mon["top"] + r.top() * sy)
        width = max(1, int(r.width() * sx))
        height = max(1, int(r.height() * sy))
        return left, top, width, height

    def _finish(self) -> None:
        if self._sel.width() < 20 or self._sel.height() < 20:
            self._cancel()
            return
        rect = self._to_physical(self._sel)
        self.picked.emit(rect)
        self.close()

    def _cancel(self) -> None:
        self.cancelled.emit()
        self.close()

    # ------------------------------------------------------------------
    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(8, 10, 16, 120))

        if self._sel.width() > 0 and self._sel.height() > 0:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(self._sel, Qt.GlobalColor.transparent)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            p.setPen(QPen(QColor(88, 166, 255), 2))
            p.drawRect(self._sel.adjusted(1, 1, -1, -1))

            ph = self._to_physical(self._sel)
            label = f"{ph[2]} × {ph[3]}"
            p.setPen(QColor(255, 255, 255))
            font = p.font()
            font.setPointSize(10)
            p.setFont(font)
            tx = self._sel.left()
            ty = max(16, self._sel.top() - 8)
            p.drawText(tx + 4, ty, label)

        p.setPen(QColor(235, 238, 245))
        font = p.font()
        font.setPointSize(13)
        font.setBold(True)
        p.setFont(font)
        p.drawText(
            40, 60,
            "拖拽框选题目区域 · 回车确认 · Esc 取消",
        )
        p.end()
