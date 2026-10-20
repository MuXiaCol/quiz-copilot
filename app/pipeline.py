"""流水线：画面变化检测 + 后台求解线程。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from . import screen, solver
from .cache import AnswerCache
from .config import Config


class SolveWorker(QThread):
    """在工作线程里跑 截图 + 调模型，绝不阻塞 UI。"""

    status = Signal(str)
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, cfg: Config, cache: AnswerCache, rect: tuple[int, int, int, int],
                 parent: QObject | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.cache = cache
        self.rect = rect

    def run(self) -> None:
        try:
            self.status.emit("截图中…")
            img = screen.grab(self.rect)
            answers = solver.solve(img, self.cfg, self.cache, self.status.emit)
            self.done.emit(answers)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"{type(e).__name__}: {e}")


class ChangeWatcher(QObject):
    """轮询屏幕，画面稳定下来且与上次不同就发一次信号。"""

    changed = Signal()

    def __init__(self, cfg: Config, parent: QObject | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.paused = False
        self._timer = QTimer(self)
        self._timer.setInterval(int(cfg.get("behavior.poll_interval_ms", 1200)))
        self._timer.timeout.connect(self._tick)
        self._last = ""
        self._pending = ""
        self._stable = 0

    def set_region(self, rect: tuple[int, int, int, int]) -> None:
        self._last = ""
        self._pending = ""
        self._stable = 0

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        if self.paused:
            return
        h = screen.region_hash(screen.effective_rect(self.cfg.region))
        if not h:
            return
        if h != self._pending:
            self._pending = h
            self._stable = 0
            return
        self._stable += 1
        if self._stable < int(self.cfg.get("behavior.settle_polls", 2)):
            return
        if h != self._last:
            self._last = h
            self.changed.emit()


class Pipeline(QObject):
    """UI 与求解之间的调度器，同一时刻只允许一个求解在跑。"""

    status = Signal(str)
    answers = Signal(list)
    failed = Signal(str)

    def __init__(self, cfg: Config, cache: AnswerCache, parent: QObject | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.cache = cache
        self._worker: SolveWorker | None = None
        self._queued = False

    @property
    def busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def run(self, rect: tuple[int, int, int, int] | None = None) -> None:
        if self.busy:
            self._queued = True
            self.status.emit("稍等，正在处理上一张…")
            return
        if not self.cfg.has_key:
            self.failed.emit("还没填 API Key，按 F8 打开设置填一下")
            return
        target = rect or self.cfg.region
        self._worker = SolveWorker(self.cfg, self.cache, screen.effective_rect(target))
        self._worker.status.connect(self.status)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _finish(self) -> None:
        if self._worker is not None:
            self._worker.wait(2000)
            self._worker.deleteLater()
            self._worker = None
        if self._queued:
            self._queued = False
            QTimer.singleShot(150, self.run)

    def _on_done(self, answers: list) -> None:
        self.answers.emit(answers)
        self._finish()

    def _on_failed(self, msg: str) -> None:
        self.failed.emit(msg)
        self._finish()
