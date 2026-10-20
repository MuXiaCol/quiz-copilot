"""Win32 窗口样式工具：让悬浮窗永远不抢焦点。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000   # 点击/显示都不激活，不触发对方的 blur
WS_EX_TOOLWINDOW = 0x00000080   # 不进任务栏、不进 Alt+Tab
WS_EX_TRANSPARENT = 0x00000020  # 鼠标穿透
WS_EX_TOPMOST = 0x00000008

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
SWP_SHOWWINDOW = 0x0040

user32.GetWindowLongW.restype = wintypes.LONG
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_uint,
]


def ex_style(hwnd: int) -> int:
    return user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)


def _apply(hwnd: int, ex: int) -> None:
    user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, ex)


def make_noactivate(hwnd: int, click_through: bool = False) -> None:
    """置顶 + 不抢焦点（+ 可选鼠标穿透）。显示后每次都要补一次。"""
    if not hwnd:
        return
    ex = ex_style(hwnd)
    ex |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
    if click_through:
        ex |= WS_EX_TRANSPARENT
    else:
        ex &= ~WS_EX_TRANSPARENT
    _apply(hwnd, ex)
    user32.SetWindowPos(
        wintypes.HWND(hwnd), wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
    )


def set_click_through(hwnd: int, on: bool) -> None:
    if not hwnd:
        return
    ex = ex_style(hwnd)
    ex = (ex | WS_EX_TRANSPARENT) if on else (ex & ~WS_EX_TRANSPARENT)
    _apply(hwnd, ex)


def move_noactivate(hwnd: int, x: int, y: int, w: int, h: int) -> None:
    """改位置/大小但不激活、不改 Z 序。"""
    if not hwnd:
        return
    user32.SetWindowPos(
        wintypes.HWND(hwnd), wintypes.HWND(0), int(x), int(y), int(w), int(h),
        SWP_NOACTIVATE | SWP_NOOWNERZORDER | SWP_NOZORDER,
    )
