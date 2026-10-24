"""流水线：画面变化检测 + 后台求解线程。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, QTimer, Signal

import numpy as np

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


class _HashSignals(QObject):
    hashed = Signal(object)


class _HashJob(QRunnable):
    """线程池里跑"截屏 + 量化网格"。整屏一次上百毫秒，放 UI 线程会周期性卡顿。"""

    def __init__(self, sig: _HashSignals, rect: tuple[int, int, int, int]):
        super().__init__()
        self._sig = sig
        self._rect = rect

    def run(self) -> None:
        self._sig.hashed.emit(screen.region_sig(self._rect))


class ChangeWatcher(QObject):
    """轮询屏幕，画面稳定下来且与上次不同就发一次信号。

    截图量化在线程池里算，UI 线程只做比较；同一时刻只有一个任务在飞。
    稳定性用"差异单元比例 ≤ 容差"判定，光标闪烁、角落倒计时跳动这类
    微小噪声不会再把画面判成"一直在变"。
    """

    changed = Signal()

    def __init__(self, cfg: Config, parent: QObject | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.paused = False
        self._timer = QTimer(self)
        self._timer.setInterval(int(cfg.get("behavior.poll_interval_ms", 800)))
        self._timer.timeout.connect(self._tick)
        self._last: np.ndarray | None = None
        self._pending: np.ndarray | None = None
        self._stable = 0
        self._busy = False
        self._sig = _HashSignals()
        self._sig.hashed.connect(self._on_hashed)

    def _tolerance(self) -> float:
        return float(self.cfg.get("behavior.change_tolerance", 0.02))

    def set_region(self, rect: tuple[int, int, int, int]) -> None:
        self._last = None
        self._pending = None
        self._stable = 0

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        if self.paused or self._busy:
            return
        self._busy = True
        QThreadPool.globalInstance().start(
            _HashJob(self._sig, screen.effective_rect(self.cfg.region))
        )

    def _same(self, a: np.ndarray | None, b: np.ndarray | None) -> bool:
        return screen.sig_diff(a, b) <= self._tolerance()

    def _on_hashed(self, sig) -> None:
        self._busy = False
        if sig is None:
            return
        if not self._same(sig, self._pending):
            self._pending = sig
            self._stable = 0
            return
        self._stable += 1
        if self._stable < int(self.cfg.get("behavior.settle_polls", 2)):
            return
        if not self._same(sig, self._last):
            self._last = sig
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
        # 线程结束后自我销毁；不在 UI 线程上 wait() 卡等待
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.status.connect(self.status)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _finish(self) -> None:
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
