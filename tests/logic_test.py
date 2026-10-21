"""纯逻辑测试：不导入 Qt。

CI 的 windows-latest 上 Qt 平台插件初始化可能失败（进程级 abort，没有 traceback），
所以把"必须通过"的部分和"依赖 GUI 环境"的部分拆开：
    tests/logic_test.py   ← 这个，任何环境都能跑，CI 里卡失败
    tests/smoke.py        ← 那个，需要能起 Qt，CI 里只做尽力而为
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# CI 的 Windows runner 上 stdout 是 cp1252，打印中文会抛 UnicodeEncodeError。
# 这个坑让 v1.0.0 / v1.0.1 的构建全挂在这一步，所以每个测试脚本开头都强制 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cache import AnswerCache, text_key  # noqa: E402
from app.config import Config  # noqa: E402
from app.solver import _build_answers, extract_json, thinking_kwargs  # noqa: E402

SAMPLE_JSON = """
```json
{"answers":[
 {"no":1,"type":"单选题","stem":"维护重点经济领域安全面临的风险挑战不包括","answer":["B"],
  "option_text":"经济主权安全风险","confidence":0.95,
  "reason":"重点经济领域指金融、粮食、能源资源与产业链供应链安全。"},
 {"no":2,"type":"单选题","stem":"已经成为推进中国式现代化的生力军的是","answer":"B",
  "option_text":"民营经济","confidence":0.93,"reason":"民营经济是生力军。"},
 {"no":3,"type":"多选题","stem":"新时代经济安全包括","answer":["a","c"],
  "option_texts":["金融安全","粮食安全"],"confidence":0.8,"reason":"多选。"},
 {"no":4,"type":"判断题","stem":"经济安全是国家安全的基础","answer":"正确",
  "option_text":"对","confidence":0.99,"reason":"教材原文。"}
]}
```
"""


def test_json_and_answers() -> None:
    payload = extract_json(SAMPLE_JSON)
    assert payload is not None, "JSON 抽取失败（```json 围栏没剥掉？）"

    answers = _build_answers(payload)
    assert len(answers) == 4, len(answers)

    # 单选题：字符串 "B" 和数组 ["B"] 都要能归一化
    assert answers[0].letters == ["B"], answers[0].letters
    assert answers[1].letters == ["B"], answers[1].letters
    # 多选题：小写输入要转大写并保序
    assert answers[2].letters == ["A", "C"], answers[2].letters
    # 判断题："正确" → "对"
    assert answers[3].letters == ["对"], answers[3].letters
    # 排序稳定
    assert [a.no for a in answers] == [1, 2, 3, 4]

    # 多选逐项分行
    rows = answers[2].display_rows()
    assert rows == ["A. 金融安全", "C. 粮食安全"], rows
    assert answers[2].is_multi is True
    assert answers[0].is_multi is False

    # 判断题不产生正文行（只靠徽章）
    assert answers[3].badge == "对"
    print("  JSON 抽取 + 答案归一化 ✓")


def test_config_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "config.json"
        cfg = Config(path)
        cfg.set("api.api_key", "sk-test-000")
        cfg.set("ui.width", 512)
        cfg.set_region((10, 20, 300, 400))
        cfg.save()

        again = Config(path)
        assert again.get("api.api_key") == "sk-test-000"
        assert again.get("ui.width") == 512
        assert again.region == (10, 20, 300, 400)
        assert again.has_key is True

        # 点号访问不存在时要返回默认值而不是抛异常
        assert again.get("no.such.key", "fallback") == "fallback"
    print("  Config 读写 ✓")


def test_cache() -> None:
    with tempfile.TemporaryDirectory() as td:
        cache = AnswerCache(Path(td) / "c.db")
        key = text_key("q1")
        assert cache.get(key) is None
        cache.put(key, {"answers": [{"no": 1, "answer": ["B"]}]})
        got = cache.get(key)
        assert got is not None and got["answers"][0]["answer"] == ["B"], got
        assert cache.count() == 1
        cache.clear()
        assert cache.count() == 0
        cache.close()
    print("  sqlite 缓存读写 ✓")


def test_thinking_levels() -> None:
    """api.thinking 必须翻译成正确的请求参数。"""
    with tempfile.TemporaryDirectory() as td:
        cfg = Config(Path(td) / "config.json")

        # 默认必须是 low：deepseek-flash 服务端默认是 high，不显式降就一直在跑最高档
        assert cfg.get("api.thinking") == "low", cfg.get("api.thinking")
        kw = thinking_kwargs(cfg)
        assert kw["reasoning_effort"] == "low", kw
        assert kw["extra_body"] == {"thinking": {"type": "enabled"}}, kw

        for level in ("high", "max"):
            cfg.set("api.thinking", level)
            assert thinking_kwargs(cfg)["reasoning_effort"] == level

        # off 走 disabled，不下发 reasoning_effort
        cfg.set("api.thinking", "off")
        kw = thinking_kwargs(cfg)
        assert kw == {"extra_body": {"thinking": {"type": "disabled"}}}, kw
        assert "reasoning_effort" not in kw

        # 乱填一律回落到 low，不能把非法值发给服务端
        for bad in ("", "medium", "超", None, 123):
            cfg.set("api.thinking", bad)
            assert thinking_kwargs(cfg)["reasoning_effort"] == "low", bad

        # 大小写和空格要能吃
        cfg.set("api.thinking", "  HIGH ")
        assert thinking_kwargs(cfg)["reasoning_effort"] == "high"
        cfg.set("api.thinking", "OFF ")
        assert thinking_kwargs(cfg) == {"extra_body": {"thinking": {"type": "disabled"}}}
    print("  思考等级映射 ✓")


def main() -> int:
    print("纯逻辑测试（不依赖 Qt）")
    test_json_and_answers()
    test_config_roundtrip()
    test_cache()
    test_thinking_levels()
    print("全部通过 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
