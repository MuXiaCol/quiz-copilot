"""图像工具：编码、按空白行智能切带（让视觉模型看清小字）。"""
from __future__ import annotations

import hashlib
import io

import numpy as np
from PIL import Image


def png_bytes(bgr: np.ndarray) -> bytes:
    """BGR ndarray → PNG 字节。文字类截图用 PNG 比 JPEG 清晰得多。"""
    rgb = bgr[:, :, ::-1]
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(rgb)).save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def _ink_rows(bgr: np.ndarray, dark: int = 200) -> np.ndarray:
    """返回每一行的"墨量"（深色像素占比）。

    用整数加权 (B + 2G + R)/4 近似亮度：uint16 累加比 astype 后的
    float64 mean 快约 3 倍，灰度像素下结果与真亮度一致。"""
    q = bgr.astype(np.uint16)
    gray = (q[..., 0] + 2 * q[..., 1] + q[..., 2]) >> 2
    return (gray < dark).sum(axis=1) / max(1, bgr.shape[1])


def content_hash(bgr: np.ndarray, cols: int = 320, quant: int = 16) -> str:
    """原始像素的降采样量化哈希，用作答案缓存 key。

    之前拿"PNG 编码后的字节"当 key，缓存命中前也得先付整轮 PNG 编码
    （整屏秒级）；直接对抽样像素哈希不到 1ms。抽样 + 量化也让 1px 光标
    闪烁这类噪声大概率不改变 key。"""
    h, w = bgr.shape[:2]
    if h <= 0 or w <= 0:
        return ""
    k = max(1, w // cols)
    small = bgr[::k, ::k, :3]
    if small.size == 0:
        return ""
    q = small // quant
    return hashlib.sha256(q.tobytes()).hexdigest()


def smart_strips(
    bgr: np.ndarray,
    target_h: int = 1000,
    max_h: int = 1400,
    blank_ratio: float = 0.004,
) -> list[tuple[int, int]]:
    """把长图切成若干横带，切点尽量落在空白行上，避免把一道题拦腰截断。

    视觉模型对每张图独立缩放到约 1300×1300，图越扁，字保留得越大。
    """
    h = bgr.shape[0]
    if h <= max_h:
        return [(0, h)]

    ink = _ink_rows(bgr)
    blank = ink < blank_ratio

    # 候选切点：连续空白行的中点
    candidates: list[int] = []
    start = None
    for y in range(h):
        if blank[y]:
            if start is None:
                start = y
        else:
            if start is not None and y - start >= 3:
                candidates.append((start + y) // 2)
            start = None
    if start is not None and h - start >= 3:
        candidates.append((start + h) // 2)

    strips: list[tuple[int, int]] = []
    y = 0
    while y < h:
        if h - y <= max_h:
            strips.append((y, h))
            break
        ideal = y + target_h
        # 在 ideal ±tol 范围内找最近的空白行；找不到就硬切
        lo, hi = ideal - 300, min(ideal + 300, h - 1)
        near = [c for c in candidates if lo <= c <= hi]
        cut = min(near, key=lambda c: abs(c - ideal)) if near else ideal
        cut = max(y + target_h // 2, min(cut, h - 1))
        strips.append((y, cut))
        y = cut
    return strips or [(0, h)]


def strip_images(bgr: np.ndarray, target_h: int = 1000) -> list[bytes]:
    out: list[bytes] = []
    for y0, y1 in smart_strips(bgr, target_h=target_h):
        part = bgr[y0:y1]
        if part.size == 0:
            continue
        out.append(png_bytes(part))
    return out or [png_bytes(bgr)]
