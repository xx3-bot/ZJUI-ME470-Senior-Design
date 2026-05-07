"""共用的可视化叠加层。

L1 离线脚本和 L2 实时窗口都用这里画 OCR polygon / spine bbox / 文字。
"""

from __future__ import annotations

from typing import Iterable

import cv2
import numpy as np

from .spine_detector import SpineHit


_OCR_POLY_COLOR = (0, 0, 255)      # 红：原始 OCR polygon
_BBOX_COLOR = (0, 200, 0)           # 绿：聚类后的 spine bbox
_TEXT_COLOR = (0, 200, 0)
_TEXT_BG = (0, 0, 0)


def _put_label(frame: np.ndarray, x: int, y: int, text: str) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.6
    thickness = 1
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    cv2.rectangle(frame, (x, y - th - 4), (x + tw + 4, y + 2), _TEXT_BG, -1)
    cv2.putText(frame, text, (x + 2, y - 2), font, scale, _TEXT_COLOR, thickness, cv2.LINE_AA)


def draw_hits(frame: np.ndarray, hits: Iterable[SpineHit]) -> np.ndarray:
    """在 frame 副本上画 hit 的可视化结果，返回新 ndarray。"""
    annotated = frame.copy()
    for hit in hits:
        for poly in hit.polygons:
            pts = poly.polygon.astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(annotated, [pts], True, _OCR_POLY_COLOR, 1)
        x1, y1, x2, y2 = hit.bbox
        cv2.rectangle(annotated, (x1, y1), (x2, y2), _BBOX_COLOR, 2)
        label = (
            f"{hit.matched_title} | tilt={hit.tilt_deg:+.1f} | "
            f"score={hit.ocr_score:.2f}"
        )
        _put_label(annotated, x1, max(20, y1 - 4), label)
    return annotated
