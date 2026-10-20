"""配色与字体常量。"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont

BG = QColor(22, 24, 30)
BORDER = QColor(255, 255, 255, 30)
TEXT = QColor(238, 240, 245)
TEXT_DIM = QColor(160, 166, 180)
TEXT_FAINT = QColor(120, 126, 140)
ACCENT = QColor(88, 166, 255)

OPTION_COLORS = {
    "A": QColor(47, 158, 68),
    "B": QColor(28, 126, 214),
    "C": QColor(232, 89, 12),
    "D": QColor(112, 72, 232),
    "E": QColor(201, 42, 120),
    "F": QColor(12, 154, 154),
    "G": QColor(150, 120, 30),
    "H": QColor(90, 90, 100),
    "对": QColor(47, 158, 68),
    "错": QColor(201, 42, 42),
}

FONT_FAMILY = "Microsoft YaHei UI"


def ui_font(size: int = 12, bold: bool = False) -> QFont:
    f = QFont(FONT_FAMILY, size)
    f.setBold(bold)
    return f


def color_for(letter: str) -> QColor:
    return OPTION_COLORS.get(letter.strip().upper()[:1] if letter else "", ACCENT)


def confidence_color(conf: float) -> QColor:
    if conf >= 0.85:
        return QColor(56, 176, 92)
    if conf >= 0.65:
        return QColor(222, 160, 40)
    return QColor(214, 74, 74)
