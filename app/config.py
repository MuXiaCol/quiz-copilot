"""配置读写：%APPDATA%\\QuizCopilot\\config.json"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

APP_NAME = "QuizCopilot"


def app_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = app_dir() / "config.json"
DB_PATH = app_dir() / "cache.db"
LOG_PATH = app_dir() / "quizcopilot.log"


DEFAULTS: dict[str, Any] = {
    "api": {
        # 任何支持图片输入的 OpenAI 兼容端点都行
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-flash",
        # 思考等级：off / low / high / max
        # deepseek-flash 服务端默认是「思考开启 + effort=high」，这里显式降档省钱提速。
        # 注意思考模式会忽略 temperature。
        "thinking": "low",
        "temperature": 0,
        "timeout": 90,
        "max_tokens": 2000,
    },
    "capture": {
        # 物理像素 (left, top, width, height)；全 0 表示整块屏幕
        "region": [0, 0, 0, 0],
        # 长截图按这个高度切成横带再发给模型，切点尽量落在空白行上
        "strip_h": 1000,
    },
    "ui": {
        "width": 430,
        "opacity": 0.94,
        "font_size": 14,
        "margin": 14,
        "show_reason": True,
        "max_height_ratio": 0.72,
        "click_through": False,
    },
    "behavior": {
        "auto_mode": False,
        "poll_interval_ms": 1200,
        "settle_polls": 2,
        "use_cache": True,
        "vote_low_confidence": True,
        "low_confidence": 0.70,
    },
    "hotkeys": {
        # 全局热键，值为 Qt 键名（F1..F12, A..Z 加 Ctrl/Alt/Shift 前缀即可，如 "Ctrl+Alt+Q"）
        "capture": "F5",     # 开始识别
        "toggle": "F6",      # 显隐悬浮窗
        "pick": "F7",        # 重新框选识别区域
        "settings": "F8",    # 打开设置
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


class Config:
    """点号访问的配置对象：cfg.get("api.model") / cfg.set("ui.width", 500)"""

    def __init__(self, path: Path | None = None):
        self.path = path or CONFIG_PATH
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    # ---------- IO ----------
    def load(self) -> None:
        try:
            if self.path.exists():
                disk = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(disk, dict):
                    _deep_merge(self.data, disk)
        except Exception:
            # 配置损坏不应阻塞启动，直接用默认值
            pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, self.path)

    # ---------- 访问 ----------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    # ---------- 便捷属性 ----------
    @property
    def region(self) -> tuple[int, int, int, int]:
        r = self.get("capture.region") or [0, 0, 0, 0]
        try:
            l, t, w, h = (int(x) for x in r)
            return l, t, w, h
        except Exception:
            return 0, 0, 0, 0

    def set_region(self, rect: tuple[int, int, int, int]) -> None:
        self.set("capture.region", [int(v) for v in rect])

    @property
    def has_key(self) -> bool:
        return bool(str(self.get("api.api_key", "")).strip())
