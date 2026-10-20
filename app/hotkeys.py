"""全局热键：RegisterHotKey（不装键盘钩子、不需要管理员权限）。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

user32 = ctypes.WinDLL("user32", use_last_error=True)

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODS = {"Ctrl": MOD_CONTROL, "Control": MOD_CONTROL, "Alt": MOD_ALT,
         "Shift": MOD_SHIFT, "Win": MOD_WIN}

_NAMED: dict[str, int] = {
    "Space": 0x20, "Enter": 0x0D, "Return": 0x0D, "Esc": 0x1B, "Escape": 0x1B,
    "Tab": 0x09, "Backspace": 0x08, "Insert": 0x2D, "Delete": 0x2E,
    "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22,
    "Left": 0x25, "Right": 0x27, "Up": 0x26, "Down": 0x28,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
_NAMED.update({f"F{i}": 0x6F + i for i in range(1, 25)})


def parse_hotkey(spec: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+Q' / 'F5' → (modifiers, vk)。"""
    if not spec:
        return None
    mods = 0
    key: str | None = None
    for part in str(spec).replace(" ", "").split("+"):
        if not part:
            continue
        if part in _MODS:
            mods |= _MODS[part]
        else:
            key = part
    if not key:
        return None
    if key.upper() in _NAMED:
        vk = _NAMED[key.upper()]
    elif len(key) == 1 and key.upper().isalnum():
        vk = ord(key.upper())
    elif key.upper().startswith("F") and key[1:].isdigit():
        vk = 0x6F + int(key[1:])
    else:
        return None
    return mods | MOD_NOREPEAT, vk


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self._cb = callback

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        if eventType in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            try:
                msg = wintypes.MSG.from_address(int(message))
            except Exception:
                return False, 0
            if msg.message == WM_HOTKEY:
                self._cb(int(msg.wParam))
        return False, 0


class HotkeyManager(QObject):
    """actions: {"capture": "F5", "toggle": "F6", ...}"""

    triggered = Signal(str)

    def __init__(self, actions: dict[str, str], parent: QObject | None = None):
        super().__init__(parent)
        self._ids: dict[int, str] = {}
        self._actions = dict(actions)
        self._next_id = 0xA000
        self._fails: list[str] = []
        self._filter = _Filter(self._on_hotkey)
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)

    def set_actions(self, actions: dict[str, str]) -> list[str]:
        """换一套热键：先注销旧的再注册，避免同一组合键被自己占住。"""
        self._actions = dict(actions)
        return self.register_all()

    def register_all(self) -> list[str]:
        self.unregister_all()
        self._fails = []
        for name, spec in self._actions.items():
            parsed = parse_hotkey(spec)
            if parsed is None:
                self._fails.append(f"{name}: 无法解析 {spec!r}")
                continue
            mods, vk = parsed
            hid = self._next_id
            self._next_id += 1
            if user32.RegisterHotKey(None, hid, mods, vk):
                self._ids[hid] = name
            else:
                self._fails.append(f"{spec} 被占用")
        return list(self._fails)

    def unregister_all(self) -> None:
        for hid in list(self._ids):
            user32.UnregisterHotKey(None, hid)
        self._ids.clear()

    def _on_hotkey(self, hid: int) -> None:
        name = self._ids.get(hid)
        if name:
            self.triggered.emit(name)
