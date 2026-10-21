"""回归测试：F6 隐藏之后，后台行为不得把悬浮窗弹回来。

对应 bug：auto_mode 打开时，ChangeWatcher 每次检测到画面变化都会走 do_capture()，
那条路径里有 show_no_activate()，于是用户藏起来的窗口过一会儿又冒出来了。

注意：会短暂注册 F5~F8 全局热键并建一个托盘图标，跑完自动退出。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 必须在 import app.config 之前改 APPDATA：CONFIG_PATH 是模块级常量
_TMP = tempfile.mkdtemp(prefix="qcp_hidden_")
os.environ["APPDATA"] = _TMP
_cfg_dir = Path(_TMP) / "QuizCopilot"
_cfg_dir.mkdir(parents=True, exist_ok=True)
(_cfg_dir / "config.json").write_text(
    json.dumps(
        {
            "api": {"api_key": "sk-regression", "base_url": "https://example.invalid/v1"},
            "behavior": {"auto_mode": True},
            "ui": {"click_through": False},
        },
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.main import App, _apply_dark_palette  # noqa: E402
from app.solver import Answer  # noqa: E402


def answer() -> Answer:
    return Answer(1, "单选题", "测试", ["B"], "选项 B", 0.9, "因为")


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    _apply_dark_palette(qapp)

    app = App(qapp)
    qapp.processEvents()

    # 把真正的流水线换成计数器：这里只验证"该不该弹窗 / 该不该去抓"，
    # 不能真的发网络请求，否则工作线程在解释器退出时被销毁会崩。
    captures: list[int] = []
    app.pipeline.run = lambda *a, **k: captures.append(1)

    assert app.cfg.get("behavior.auto_mode") is True
    assert app.overlay.isVisible(), "启动时悬浮窗应该是可见的"
    print(f"启动: visible={app.overlay.isVisible()} auto_mode={app.cfg.get('behavior.auto_mode')}")

    # ---- 按 F6 ----
    app.toggle_overlay()
    qapp.processEvents()
    assert app._user_hidden is True
    assert not app.overlay.isVisible(), "F6 之后应该隐藏"
    assert app.watcher.paused is True, "隐藏时自动模式必须暂停"
    print(f"F6 后: hidden={app._user_hidden} visible={app.overlay.isVisible()} watcher.paused={app.watcher.paused}")

    # ---- 后台自动识别（原来就是它把窗口弹回来的）----
    app.do_capture(auto=True)
    qapp.processEvents()
    assert not app.overlay.isVisible(), "自动模式的 do_capture 不应该弹窗"
    assert not captures, "隐藏时自动模式不应该去截图/调模型（省钱）"
    print(f"auto do_capture 之后: visible={app.overlay.isVisible()} 抓取次数={len(captures)}  ✓")

    # ---- 后台识别跑完，答案回来了（原来 _on_answers 无条件 show）----
    app._on_answers([answer()])
    qapp.processEvents()
    assert not app.overlay.isVisible(), "_on_answers 不应该把隐藏的窗口弹回来"
    print(f"_on_answers 之后: visible={app.overlay.isVisible()}  ✓")

    # ---- 后台识别失败，走 _on_failed 也不能弹 ----
    app._on_failed("模拟错误")
    qapp.processEvents()
    assert not app.overlay.isVisible(), "_on_failed 不应该把隐藏的窗口弹回来"
    print(f"_on_failed 之后: visible={app.overlay.isVisible()}  ✓")

    # ---- 再按一次 F6，应该回来，并且自动模式恢复 ----
    app.toggle_overlay()
    qapp.processEvents()
    assert app._user_hidden is False
    assert app.overlay.isVisible(), "再按 F6 应该重新显示"
    assert app.watcher.paused is False, "恢复显示后自动模式应该重新允许"
    print(f"再按 F6: visible={app.overlay.isVisible()} watcher.paused={app.watcher.paused}  ✓")

    # ---- 隐藏状态下按 F5（手动识别）应该主动弹出来，并且真的去抓 ----
    app.toggle_overlay()
    qapp.processEvents()
    assert not app.overlay.isVisible()
    app.do_capture(auto=False)
    qapp.processEvents()
    assert app.overlay.isVisible(), "手动识别应该主动显示窗口"
    assert len(captures) == 1, "手动识别应该真的发起一次抓取"
    print(f"隐藏时手动 do_capture: visible={app.overlay.isVisible()} 抓取次数={len(captures)}  ✓")

    app.quit()
    print("\n全部通过 ✓ —— F6 隐藏后不会再自己冒出来")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
