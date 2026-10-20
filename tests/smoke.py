"""离线冒烟测试：不依赖 API，验证模块导入、窗口构建、答案渲染。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import Config  # noqa: E402
from app.solver import Answer, _build_answers, extract_json  # noqa: E402
from app.ui.overlay import OverlayWindow  # noqa: E402


SAMPLE_JSON = """
```json
{"answers":[
 {"no":1,"type":"单选题","stem":"维护重点经济领域安全面临的风险挑战不包括","answer":["B"],
  "option_text":"经济主权安全风险","confidence":0.95,
  "reason":"重点经济领域指金融、粮食、能源资源与产业链供应链安全。"},
 {"no":2,"type":"单选题","stem":"已经成为推进中国式现代化的生力军的是","answer":"B",
  "option_text":"民营经济","confidence":0.93,"reason":"民营经济是生力军和高质量发展的重要基础。"},
 {"no":3,"type":"多选题","stem":"新时代经济安全包括","answer":["a","c"],
  "option_text":"金融安全；粮食安全","confidence":0.8,"reason":"多选。"},
 {"no":4,"type":"判断题","stem":"经济安全是国家安全的基础","answer":"正确",
  "option_text":"对","confidence":0.99,"reason":"教材原文。"}
]}
```
"""


def main() -> int:
    payload = extract_json(SAMPLE_JSON)
    assert payload is not None, "JSON 抽取失败"
    answers = _build_answers(payload)
    print(f"解析出 {len(answers)} 题")
    for a in answers:
        print(f"  第{a.no}题 {a.qtype} -> {a.badge}  ({a.confidence:.0%})  {a.option_text}")

    assert answers[1].letters == ["B"], answers[1].letters
    assert answers[2].letters == ["A", "C"], answers[2].letters
    assert answers[3].letters == ["对"], answers[3].letters

    app = QApplication([])  # noqa: F841
    cfg = Config()
    win = OverlayWindow(cfg)
    win.show_answers(answers)
    win.show()
    print("窗口尺寸:", win.width(), "x", win.height())
    print("（真实外观见 tests/launch_test.py 生成的 overlay_live.png）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
