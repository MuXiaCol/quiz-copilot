"""单题答案卡片。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..solver import Answer
from . import theme


class Badge(QLabel):
    """左侧的答案徽章，扫一眼就能对上选项。"""

    RADIUS = 9

    def __init__(self, letter: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._letter = (letter or "?").strip()
        n = len(self._letter)
        height = 34
        width = 34 if n <= 1 else min(76, 22 + 15 * n)
        self._color = (
            theme.color_for(self._letter) if n <= 1 else theme.ACCENT
        )
        self.setFixedSize(width, height)
        self.setText(self._letter)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(theme.ui_font(14 if n <= 1 else 12, bold=True))
        self.setStyleSheet("color: white; background: transparent;")

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), self.RADIUS, self.RADIUS)
        p.fillPath(path, self._color)
        p.end()
        super().paintEvent(event)


class AnswerCard(QFrame):
    def __init__(self, ans: Answer, show_reason: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("answerCard")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(
            "#answerCard { background: rgba(255,255,255,20);"
            " border: 1px solid rgba(255,255,255,14); border-radius: 10px; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 9, 10, 9)
        root.setSpacing(6)

        # ---- 顶行：题号 + 题型 + 置信度 ----
        head = QHBoxLayout()
        head.setSpacing(6)
        title = QLabel(f"第 {ans.no} 题 · {ans.qtype}")
        title.setFont(theme.ui_font(9))
        title.setStyleSheet(f"color: {theme.TEXT_DIM.name()};")
        head.addWidget(title)

        if ans.from_cache:
            tag = QLabel("缓存")
            tag.setFont(theme.ui_font(8))
            tag.setStyleSheet("color: #6c7a89; background: rgba(255,255,255,12);"
                              "border-radius: 6px; padding: 1px 5px;")
            head.addWidget(tag)

        head.addStretch(1)

        conf = QLabel(f"{int(ans.confidence * 100)}%")
        conf.setFont(theme.ui_font(9, bold=True))
        conf.setStyleSheet(
            f"color: {theme.confidence_color(ans.confidence).name()};"
            "background: rgba(255,255,255,12); border-radius: 6px; padding: 1px 6px;"
        )
        head.addWidget(conf)
        root.addLayout(head)

        # ---- 主体 ----
        letters = "".join(ans.letters)
        is_choice = bool(letters) and all(
            len(l) == 1 and l.upper() in "ABCDEFGH" for l in ans.letters
        )
        is_judge = ans.qtype == "判断题" or letters in ("对", "错")

        body = QHBoxLayout()
        body.setSpacing(10)

        if is_choice or is_judge:
            body.addWidget(Badge(letters or "?"), 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        rows = ans.display_rows()
        if is_judge:
            rows = []          # 判断对错只靠徽章，再写一遍"对"是废话

        multi = bool(getattr(ans, "is_multi", False))
        for i, row in enumerate(rows):
            lbl = QLabel(row)
            lbl.setWordWrap(True)
            lbl.setFont(theme.ui_font(11, bold=(i == 0)))
            # 多选的每一行都是答案，统一用高亮色；单选/填空只有第一行是答案
            color = theme.TEXT if (i == 0 or multi) else theme.TEXT_DIM
            lbl.setStyleSheet(f"color: {color.name()}; background: transparent;")
            text_col.addWidget(lbl)

        if text_col.count() == 0:
            text_col.addStretch(1)

        body.addLayout(text_col, 1)
        root.addLayout(body)

        # ---- 理由 ----
        if show_reason and ans.reason:
            reason = QLabel(ans.reason)
            reason.setWordWrap(True)
            reason.setFont(theme.ui_font(9))
            reason.setStyleSheet(f"color: {theme.TEXT_FAINT.name()};")
            root.addWidget(reason)

        if ans.stem:
            self.setToolTip(ans.stem)


class EmptyCard(QFrame):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("emptyCard")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 22, 14, 22)
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFont(theme.ui_font(10))
        lbl.setStyleSheet(f"color: {theme.TEXT_FAINT.name()}; background: transparent;")
        lay.addWidget(lbl)
        self.setStyleSheet(
            "#emptyCard { background: rgba(255,255,255,10);"
            " border: 1px solid rgba(255,255,255,12); border-radius: 10px; }"
        )
