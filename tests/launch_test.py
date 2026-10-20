"""真实窗口启动测试：跑 3 秒验证不崩溃，然后自动退出。

注意：会真的在桌面左下角弹出悬浮窗，并短暂注册 F5~F8 全局热键。
"""
from __future__ import annotations

import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.main import App, _apply_dark_palette  # noqa: E402
from app.solver import Answer  # noqa: E402

DEMO = [
    Answer(no=1, qtype="单选题", stem="维护重点经济领域安全面临的风险挑战不包括",
           letters=["B"], option_text="经济主权安全风险", confidence=0.95,
           reason="重点经济领域指金融、粮食、能源资源与产业链供应链安全。"),
    Answer(no=2, qtype="单选题", stem="已经成为推进中国式现代化生力军的是",
           letters=["B"], option_text="民营经济", confidence=0.93,
           reason="民营经济是生力军，高质量发展的重要基础。"),
    Answer(no=3, qtype="多选题", stem="新时代经济安全面临的风险挑战包括",
           letters=["A", "C", "D"],
           option_texts=["金融安全风险", "粮食安全风险", "产业链供应链安全风险"],
           confidence=0.82,
           reason="金融、粮食、产业链供应链均属重点经济领域安全风险。"),
    Answer(no=4, qtype="判断题", stem="经济安全是国家安全的基础",
           letters=["对"], option_text="对", confidence=0.88,
           reason="教材原文表述。"),
]


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    _apply_dark_palette(qapp)

    app = App(qapp)
    # 防止首次运行自动弹出设置对话框挡住测试
    QTimer.singleShot(80, lambda: app.cfg.set("api.api_key", "sk-selftest"))

    def populate() -> None:
        app.overlay.show_answers(DEMO)

    def grab() -> None:
        out = Path(__file__).resolve().parent / "overlay_live.png"
        app.overlay.grab().save(str(out))
        print(f"preview: {out}  size={app.overlay.width()}x{app.overlay.height()}")

    QTimer.singleShot(1200, populate)
    QTimer.singleShot(2000, grab)
    QTimer.singleShot(2800, app.quit)
    rc = qapp.exec()
    print(f"launch ok, rc={rc}, overlay={app.overlay.width()}x{app.overlay.height()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
