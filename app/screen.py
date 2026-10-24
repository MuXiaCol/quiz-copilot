"""屏幕几何、截图、画面变化检测（全部使用物理像素）。"""
from __future__ import annotations

import hashlib
import threading

import mss
import numpy as np

_tls = threading.local()


def _sct() -> mss.MSS:
    """线程内复用的 mss 实例：省掉每次抓屏的初始化，也天然不会跨线程混用。"""
    s = getattr(_tls, "sct", None)
    if s is None:
        s = mss.MSS()
        _tls.sct = s
    return s


def monitors() -> list[dict]:
    """monitors[0] 是整块虚拟桌面，其余是各显示器。单位：物理像素。"""
    return [dict(m) for m in _sct().monitors]


def virtual_rect() -> tuple[int, int, int, int]:
    m = monitors()[0]
    return int(m["left"]), int(m["top"]), int(m["width"]), int(m["height"])


def grab(rect: tuple[int, int, int, int]) -> np.ndarray:
    """截取物理像素矩形 (left, top, w, h)，返回 BGR ndarray。"""
    l, t, w, h = (int(v) for v in rect)
    if w <= 0 or h <= 0:
        l, t, w, h = virtual_rect()
    shot = _sct().grab({"left": l, "top": t, "width": w, "height": h})
    return np.ascontiguousarray(np.asarray(shot)[:, :, :3])


def effective_rect(rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """region 全是 0 时退化为整块虚拟桌面。"""
    l, t, w, h = rect
    if w <= 0 or h <= 0:
        return virtual_rect()
    return l, t, w, h


def coarse_hash(img: np.ndarray, target_w: int = 150) -> str:
    """降采样 + 量化灰度 → md5。留作通用工具；变化检测请用 region_sig。"""
    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return ""
    k = max(1, w // target_w)
    small = img[::k, ::k, :3]
    if small.size == 0:
        return ""
    gray = small.mean(axis=2, dtype=np.uint16)
    q = (gray // 12).astype(np.uint8)
    return hashlib.md5(q.tobytes()).hexdigest()


def region_sig(rect: tuple[int, int, int, int], cols: int = 160) -> np.ndarray | None:
    """画面变化检测用的量化网格（约 cols 列、4 级灰度）。

    与精确哈希不同，调用方按"差异单元比例"比较两帧 sig：光标闪烁
    只动一两个单元，换页/选中/滚动会动一大片，天然区分开。"""
    try:
        l, t, w, h = (int(v) for v in rect)
        if w <= 0 or h <= 0:
            l, t, w, h = virtual_rect()
        arr = np.asarray(_sct().grab({"left": l, "top": t, "width": w, "height": h}))
        if arr.shape[0] <= 0 or arr.shape[1] <= 0:
            return None
        k = max(1, arr.shape[1] // cols)
        small = arr[::k, ::k, :3]
        gray = small.mean(axis=2, dtype=np.uint16)
        return (gray // 64).astype(np.uint8)
    except Exception:
        return None


def sig_diff(a: np.ndarray | None, b: np.ndarray | None) -> float:
    """两帧 sig 的差异比例（0~1）。形状不同视为完全不同。"""
    if a is None or b is None or a.shape != b.shape:
        return 1.0
    return float((a != b).mean())
