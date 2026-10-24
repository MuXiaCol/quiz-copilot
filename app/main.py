"""应用入口：装配悬浮窗、热键、托盘、流水线。"""
from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import APP_NAME, __version__
from .cache import AnswerCache
from .config import LOG_PATH, Config
from .hotkeys import HotkeyManager
from .pipeline import ChangeWatcher, Pipeline
from .ui.overlay import OverlayWindow
from .ui.region_picker import RegionPicker
from .ui.settings_dialog import SettingsDialog


def log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(28, 126, 214))
    p.drawRoundedRect(3, 3, 58, 58, 15, 15)
    p.setPen(QColor(255, 255, 255))
    f = QFont("Microsoft YaHei UI", 26)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "Q")
    p.end()
    return QIcon(pm)


class App:
    def __init__(self, qapp: QApplication):
        self.qapp = qapp
        self.cfg = Config()
        self.cache = AnswerCache()
        self._picker: RegionPicker | None = None
        self._settings: SettingsDialog | None = None
        # 用户按 F6 主动藏起来之后，任何后台行为都不得把它弹回来
        self._user_hidden = False

        self.overlay = OverlayWindow(self.cfg)
        self.pipeline = Pipeline(self.cfg, self.cache)
        self.watcher = ChangeWatcher(self.cfg)

        self._wire()
        self._build_tray()

        self.hotkeys = HotkeyManager(dict(self.cfg.get("hotkeys") or {}))
        self.hotkeys.triggered.connect(self._on_hotkey)
        fails = self.hotkeys.register_all()
        if fails:
            log("hotkey register failed: " + "; ".join(fails))
            QTimer.singleShot(600, lambda: self.overlay.set_status("热键占用：" + "、".join(fails)))

        self.overlay.show_no_activate()
        self.overlay.set_status_region(self.cfg.region)

        if self.cfg.get("behavior.auto_mode", False):
            self.watcher.start()

        if not self.cfg.has_key:
            QTimer.singleShot(400, self._maybe_first_run)
        else:
            self.overlay.set_status("就绪")

    def _maybe_first_run(self) -> None:
        if not self.cfg.has_key:
            self.open_settings()

    # ------------------------------------------------------------------
    def _wire(self) -> None:
        self.pipeline.status.connect(self.overlay.set_status)
        self.pipeline.answers.connect(self._on_answers)
        self.pipeline.partial.connect(self._on_partial)
        self.pipeline.failed.connect(self._on_failed)
        # 自动模式是"后台行为"，必须显式标记成 auto，否则会把用户藏起来的窗口弹回来
        self.watcher.changed.connect(lambda: self.do_capture(auto=True))

        self.overlay.open_settings.connect(self.open_settings)
        self.overlay.hide_requested.connect(self.overlay.hide)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_icon(), self.qapp)
        self.tray.setToolTip(f"{APP_NAME} {__version__}")
        menu = QMenu()

        act_cap = QAction("识别当前题目", menu)
        act_cap.triggered.connect(self.do_capture)
        menu.addAction(act_cap)

        act_toggle = QAction("显示 / 隐藏悬浮窗", menu)
        act_toggle.triggered.connect(self.toggle_overlay)
        menu.addAction(act_toggle)

        act_pick = QAction("框选识别区域…", menu)
        act_pick.triggered.connect(self.open_picker)
        menu.addAction(act_pick)

        menu.addSeparator()

        self.act_auto = QAction("自动模式", menu, checkable=True)
        self.act_auto.setChecked(bool(self.cfg.get("behavior.auto_mode", False)))
        self.act_auto.toggled.connect(self._toggle_auto)
        menu.addAction(self.act_auto)

        self.act_through = QAction("鼠标穿透", menu, checkable=True)
        self.act_through.setChecked(bool(self.cfg.get("ui.click_through", False)))
        self.act_through.toggled.connect(self.overlay.set_click_through)
        menu.addAction(self.act_through)

        menu.addSeparator()

        act_set = QAction("设置…", menu)
        act_set.triggered.connect(self.open_settings)
        menu.addAction(act_set)

        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.quit)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_overlay()

    def _on_hotkey(self, name: str) -> None:
        if name == "capture":
            self.do_capture()
        elif name == "toggle":
            self.toggle_overlay()
        elif name == "pick":
            self.open_picker()
        elif name == "settings":
            self.open_settings()

    # ------------------------------------------------------------------
    def _show_overlay(self) -> None:
        """只有用户没主动藏起来时才真的弹出来。"""
        if self._user_hidden:
            return
        self.overlay.show_no_activate()

    def _set_hidden(self, hidden: bool) -> None:
        self._user_hidden = bool(hidden)
        if hidden:
            self.overlay.hide()
            # 藏起来就静默：不弹窗，也不后台偷偷截图烧 API
            self.watcher.paused = True
            log("悬浮窗已隐藏，自动模式暂停")
        else:
            self.overlay.show_no_activate()
            log("悬浮窗已恢复")
            if self.cfg.get("behavior.auto_mode", False):
                self.watcher.paused = False
                self.watcher.start()

    def toggle_overlay(self) -> None:
        self._set_hidden(not self._user_hidden)

    def do_capture(self, auto: bool = False) -> None:
        if self._picker is not None:
            return
        if auto and self._user_hidden:
            return                       # 后台自动识别不打扰隐藏状态
        if not auto and self._user_hidden:
            self._set_hidden(False)      # 手动识别 = 想看到结果
        self.watcher.paused = True
        self.pipeline.run()

    def _on_partial(self, answers: list) -> None:
        """流式过程中的半成品：只刷新卡片内容，不动 watcher、不弹窗。"""
        self.overlay.show_answers(answers)

    def _on_answers(self, answers: list) -> None:
        self.overlay.show_answers(answers)   # 内容总是更新，窗口可以继续藏着
        if self._user_hidden:
            return
        self.overlay.show_no_activate()
        self.watcher.paused = False
        if self.cfg.get("behavior.auto_mode", False):
            self.watcher.start()

    def _on_failed(self, message: str) -> None:
        self.overlay.show_error(message)
        log("pipeline error: " + message)
        if self._user_hidden:
            return
        self.overlay.show_no_activate()
        self.watcher.paused = False

    # ------------------------------------------------------------------
    def open_picker(self) -> None:
        if self._picker is not None:
            return
        self.watcher.paused = True
        self.overlay.set_status("框选中…")
        picker = RegionPicker()
        self._picker = picker
        picker.picked.connect(self._on_region_picked)
        picker.cancelled.connect(self._on_pick_cancelled)
        picker.start()

    def _close_picker(self) -> None:
        if self._picker is not None:
            self._picker.deleteLater()
            self._picker = None

    def _on_region_picked(self, rect: tuple) -> None:
        self._close_picker()
        self.cfg.set_region(rect)
        self.cfg.save()
        self.watcher.set_region(rect)
        self.watcher.paused = False
        self.overlay.set_status_region(rect)
        if self.cfg.get("behavior.auto_mode", False):
            self.watcher.start()
        if self._settings is not None:
            self.watcher.paused = True      # 设置窗口还开着，先别自动抓
            self._restore_settings()
            return
        self._set_hidden(False)             # 刚框完区域，明确要让用户看到
        QTimer.singleShot(120, self.do_capture)

    def _on_pick_cancelled(self) -> None:
        self._close_picker()
        self.watcher.paused = self._user_hidden
        self.overlay.set_status("已取消框选")
        if self._settings is not None:
            self._restore_settings()
            return
        self._show_overlay()

    # ------------------------------------------------------------------
    def open_settings(self) -> None:
        if self._settings is not None:
            self._settings.raise_()
            self._settings.activateWindow()
            return
        self.watcher.paused = True
        dlg = SettingsDialog(self.cfg)
        self._settings = dlg
        dlg.pick_region_requested.connect(self._pick_from_settings)
        dlg.finished.connect(lambda _: self._on_settings_closed())
        dlg.exec()

    def _pick_from_settings(self) -> None:
        """从设置里点"重新框选"：先把对话框藏起来，免得挡住要框的页面。"""
        if self._settings is not None:
            self._settings.hide()
        self.open_picker()

    def _restore_settings(self) -> None:
        if self._settings is not None:
            self._settings.show()
            self._settings.raise_()
            self._settings.activateWindow()
            self._settings.refresh_region()

    def _on_settings_closed(self) -> None:
        self._settings = None
        self.cfg.load()
        # 复用同一个 HotkeyManager：新建实例会让旧注册还在，同一组合键再注册必然失败
        fails = self.hotkeys.set_actions(dict(self.cfg.get("hotkeys") or {}))
        if fails:
            log("hotkey re-register failed: " + "; ".join(fails))
        self.overlay.apply_style()
        self.overlay.set_click_through(bool(self.cfg.get("ui.click_through", False)))
        self.overlay.set_status("就绪")
        self._set_hidden(False)             # 明确点开过设置，回来时应该能看到
        self.watcher.paused = False
        if self.cfg.get("behavior.auto_mode", False):
            self.watcher.start()
        else:
            self.watcher.stop()

    def _toggle_auto(self, on: bool) -> None:
        self.cfg.set("behavior.auto_mode", bool(on))
        self.cfg.save()
        if on and not self._user_hidden:
            self.watcher.paused = False
            self.watcher.start()
        else:
            self.watcher.stop()

    # ------------------------------------------------------------------
    def quit(self) -> None:
        try:
            self.hotkeys.unregister_all()
        except Exception:
            pass
        self.cache.close()
        self.tray.hide()
        self.qapp.quit()


def _excepthook(exc_type, exc, tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    log(text)
    sys.__excepthook__(exc_type, exc, tb)


def _apply_dark_palette(qapp: QApplication) -> None:
    """透明窗里的子控件会按调色板自动填充底色，统一改成深色才不会冒出白块。"""
    qapp.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(30, 32, 38))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(238, 240, 245))
    pal.setColor(QPalette.ColorRole.Base, QColor(22, 24, 30))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(40, 43, 50))
    pal.setColor(QPalette.ColorRole.Text, QColor(238, 240, 245))
    pal.setColor(QPalette.ColorRole.Button, QColor(45, 48, 56))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(238, 240, 245))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(28, 126, 214))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(40, 43, 50))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(238, 240, 245))
    qapp.setPalette(pal)


def main() -> int:
    sys.excepthook = _excepthook
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setApplicationVersion(__version__)
    qapp.setQuitOnLastWindowClosed(False)
    _apply_dark_palette(qapp)

    app = App(qapp)  # noqa: F841  保持引用
    log(f"--- start {APP_NAME} {__version__} ---")
    return qapp.exec()
