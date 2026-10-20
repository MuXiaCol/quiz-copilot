"""屏幕几何、截图、画面变化检测（全部使用物理像素）。"""
from __future__ import annotations

import hashlib

import mss
import numpy as np


def monitors() -> list[dict]:
    """monitors[0] 是整块虚拟桌面，其余是各显示器。单位：物理像素。"""
    with mss.mss() as sct:
        return [dict(m) for m in sct.monitors]


def virtual_rect() -> tuple[int, int, int, int]:
    m = monitors()[0]
    return int(m["left"]), int(m["top"]), int(m["width"]), int(m["height"])


def grab(rect: tuple[int, int, int, int]) -> np.ndarray:
    """截取物理像素矩形 (left, top, w, h)，返回 BGR ndarray。"""
    l, t, w, h = (int(v) for v in rect)
    if w <= 0 or h <= 0:
        l, t, w, h = virtual_rect()
    with mss.mss() as sct:
        shot = sct.grab({"left": l, "top": t, "width": w, "height": h})
        arr = np.asarray(shot)
    return np.ascontiguousarray(arr[:, :, :3])


def effective_rect(rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """region 全是 0 时退化为整块虚拟桌面。"""
    l, t, w, h = rect
    if w <= 0 or h <= 0:
        return virtual_rect()
    return l, t, w, h


def coarse_hash(img: np.ndarray, target_w: int = 150) -> str:
    """降采样 + 量化灰度 → md5。用来判断画面有没有变化，成本极低。"""
    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return ""
    k = max(1, w // target_w)
    small = img[::k, ::k]
    if small.size == 0:
        return ""
    gray = small.astype(np.float32).mean(axis=2)
    q = (gray // 12).astype(np.uint8)
    return hashlib.md5(q.tobytes()).hexdigest()


def region_hash(rect: tuple[int, int, int, int]) -> str:
    try:
        return coarse_hash(grab(rect))
    except Exception:
        return ""
