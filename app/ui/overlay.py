"""悬浮窗：置顶、半透明、固定左下角、永不抢焦点。"""
from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config import Config
from ..win32util import make_noactivate
from . import theme
from .card import AnswerCard, EmptyCard

HINTS = "F5 识别   ·   F6 显隐   ·   F7 框选   ·   F8 设置"


class OverlayWindow(QWidget):
    open_settings = Signal()
    request_capture = Signal()
    hide_requested = Signal()

    def __init__(self, cfg: Config):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.cfg = cfg
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("QuizCopilot")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._build_ui()
        self.set_status("就绪")
        l, t, w, h = cfg.region
        if w > 0 and h > 0:
            self.clear("按 F5 识别当前区域（F7 重新框选）")
            self.set_status_region((l, t, w, h))
        else:
            self.clear("先按 F7 框选题目区域 —— 只框题干和选项，别框地址栏和侧边目录")

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._inner = QWidget()
        self._inner.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        lay = QVBoxLayout(self._inner)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(7)
        outer.addWidget(self._inner)

        # 顶栏
        head = QHBoxLayout()
        head.setSpacing(7)

        dot = QLabel("●")
        dot.setFont(theme.ui_font(9))
        dot.setStyleSheet(f"color: {theme.ACCENT.name()};")
        head.addWidget(dot)

        self._title = QLabel("QuizCopilot")
        self._title.setFont(theme.ui_font(10, bold=True))
        self._title.setStyleSheet(f"color: {theme.TEXT.name()};")
        head.addWidget(self._title)

        self._status = QLabel("")
        self._status.setFont(theme.ui_font(9))
        self._status.setStyleSheet(f"color: {theme.TEXT_DIM.name()};")
        head.addWidget(self._status, 1)

        for text, tip, slot in (
            ("⚙", "设置 (F8)", self.open_settings.emit),
            ("✕", "隐藏 (F6)", self.hide_requested.emit),
        ):
            btn = QPushButton(text)
            btn.setFixedSize(20, 20)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tip)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setFont(theme.ui_font(9))
            btn.setStyleSheet(
                "QPushButton { color: #9aa2b1; background: transparent; border: none;"
                " border-radius: 5px; }"
                "QPushButton:hover { background: rgba(255,255,255,28); color: #fff; }"
            )
            btn.clicked.connect(slot)
            head.addWidget(btn)
        lay.addLayout(head)

        # 内容区
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.viewport().setStyleSheet("background: transparent;")
        self._scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent;"
            " border: none; }"
            "QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,40);"
            " border-radius: 3px; min-height: 24px; }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
            "QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }"
        )

        self._container = QWidget()
        self._container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._container.setAutoFillBackground(False)
        self._container.setStyleSheet("background: transparent;")
        self._vbox = QVBoxLayout(self._container)
        self._vbox.setContentsMargins(0, 0, 2, 0)
        self._vbox.setSpacing(6)
        self._vbox.addStretch(1)
        self._scroll.setWidget(self._container)
        lay.addWidget(self._scroll, 1)

        # 底栏
        self._hint = QLabel(HINTS)
        self._hint.setFont(theme.ui_font(8))
        self._hint.setStyleSheet(f"color: {theme.TEXT_FAINT.name()};")
        lay.addWidget(self._hint)

    # ------------------------------------------------------------- 状态更新
    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def _clear_items(self) -> None:
        while self._vbox.count() > 1:
            item = self._vbox.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)   # 立刻从父级摘掉，否则还会按旧几何继续绘制
                w.deleteLater()

    def clear(self, message: str = "") -> None:
        self._clear_items()
        if message:
            self._vbox.insertWidget(0, EmptyCard(message))
        self._relayout()

    def show_answers(self, answers: list) -> None:
        self._clear_items()
        show_reason = bool(self.cfg.get("ui.show_reason", True))
        for ans in answers:
            card = AnswerCard(ans, show_reason)
            self._vbox.insertWidget(self._vbox.count() - 1, card)
        cached = all(getattr(a, "from_cache", False) for a in answers) if answers else False
        self.set_status(f"{len(answers)} 题" + (" · 缓存" if cached else ""))
        self._relayout()

    def show_error(self, message: str) -> None:
        self._clear_items()
        self._vbox.insertWidget(0, EmptyCard(message))
        self.set_status("出错")
        self._relayout()

    def _max_height(self) -> int:
        scr = self.screen() or QApplication.primaryScreen()
        ratio = float(self.cfg.get("ui.max_height_ratio", 0.72))
        return max(220, int(scr.availableGeometry().height() * ratio)) if scr else 600

    def _relayout(self, reschedule: bool = True) -> None:
        """按内容算高度，再钉到左下角。

        新插入的子控件要等事件循环跑过一次 polish，sizeHint 才准，
        所以这里先立刻算一次（可能偏小），下一拍再算一次收敛。
        """
        width = int(self.cfg.get("ui.width", 430))
        head_h, foot_h, pad = 26, 20, 22

        self._container.ensurePolished()
        for i in range(self._vbox.count()):
            item = self._vbox.itemAt(i)
            w = item.widget() if item else None
            if w is not None:
                w.ensurePolished()
        self._vbox.invalidate()
        self._vbox.activate()
        self._container.adjustSize()
        content_h = self._container.sizeHint().height()
        if os.environ.get("QUIZCOPILOT_DEBUG"):
            print(f"[relayout] vbox={self._vbox.count()} hint={self._container.sizeHint()} "
                  f"content_h={content_h}")

        desired = head_h + content_h + foot_h + pad
        height = max(110, min(desired, self._max_height()))
        body_h = max(40, height - head_h - foot_h - pad)

        self._scroll.setFixedHeight(min(body_h, max(40, content_h)))
        self._inner.setFixedWidth(width)
        self.setFixedSize(width, height)
        self.anchor_bottom_left()

        if reschedule:
            QTimer.singleShot(0, lambda: self._relayout(reschedule=False))

    def anchor_bottom_left(self) -> None:
        """固定屏幕左下角。"""
        scr = self.screen() or QApplication.primaryScreen()
        if scr is None:
            return
        avail = scr.availableGeometry()
        margin = int(self.cfg.get("ui.margin", 14))
        x = avail.left() + margin
        y = avail.bottom() - self.height() - margin + 1
        self.move(int(x), int(y))

    def apply_style(self) -> None:
        self._relayout()

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 13, 13)

        alpha = int(255 * float(self.cfg.get("ui.opacity", 0.94)))
        p.fillPath(path, QColor(theme.BG.red(), theme.BG.green(), theme.BG.blue(), alpha))
        p.setPen(QPen(theme.BORDER, 1))
        p.drawPath(path)
        p.end()

    # ------------------------------------------------------------------ 显示
    def show_no_activate(self) -> None:
        self.show()
        self._relayout()
        make_noactivate(int(self.winId()), bool(self.cfg.get("ui.click_through", False)))

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        make_noactivate(int(self.winId()), bool(self.cfg.get("ui.click_through", False)))

    def toggle_visible(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show_no_activate()

    def set_click_through(self, on: bool) -> None:
        self.cfg.set("ui.click_through", on)
        self.cfg.save()
        make_noactivate(int(self.winId()), on)

    def set_status_region(self, rect: tuple[int, int, int, int]) -> None:
        l, t, w, h = rect
        if w <= 0 or h <= 0:
            self.set_status("整屏")
        else:
            self.set_status(f"区域 {w}×{h}")
