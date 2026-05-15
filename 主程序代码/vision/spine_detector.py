"""OCR-first 书脊检测器。

整体策略（参考 test_paddleocr.py，避开 gap_ocr.py 的多角度反投影坑）：

1. SpineOCR 跑一次整帧 OCR
2. 只保留长边竖直的 polygon（书脊上的字）
3. 按 polygon 中心 x 聚类成 spine（同一根书脊的字 x 相近）
4. 每个 spine：拼接所有 polygon 的文本 → 模糊匹配 KNOWN_BOOK_TITLES
5. 命中后：bbox = polygon 顶点的最小外接矩形；tilt = polygon 长边的平均角度
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from .ocr import OcrPolygon, SpineOCR


_SPINE_CLUSTER_X_PX = 80.0


@dataclass
class _SpineCluster:
    polygons: List[OcrPolygon] = field(default_factory=list)

    @property
    def center_x(self) -> float:
        return float(np.mean([p.center[0] for p in self.polygons]))


@dataclass(frozen=True)
class SpineHit:
    """一根命中 KNOWN_BOOK_TITLES 的书脊。"""

    matched_title: str
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2) 像素
    tilt_deg: float                  # 0 = 完全竖直；正数 = 顶部向右倾
    ocr_score: float                 # 0~1，OCR 平均分 × 模糊匹配分
    polygons: List[OcrPolygon]       # 簇内原始 polygon，可视化用


def _polygon_long_edge_angle_deg(poly: np.ndarray) -> float:
    """polygon 长边相对其自然轴的倾角。

    - 文字横排（长边水平）：返回相对 x 轴的倾角，0=完全水平
    - 文字竖排（长边竖直）：返回相对 y 轴的倾角，0=完全竖直
    正负代表倾斜方向；幅度即"歪了几度"。
    """
    edge_top = poly[1] - poly[0]
    edge_bottom = poly[2] - poly[3]
    edge_left = poly[3] - poly[0]
    edge_right = poly[2] - poly[1]
    horiz_len = (np.linalg.norm(edge_top) + np.linalg.norm(edge_bottom)) / 2.0
    vert_len = (np.linalg.norm(edge_left) + np.linalg.norm(edge_right)) / 2.0

    if horiz_len >= vert_len:
        avg = (edge_top + edge_bottom) / 2.0
        dx, dy = float(avg[0]), float(avg[1])
        if dx < 0:
            dx, dy = -dx, -dy
        if dx == 0:
            return 90.0
        return math.degrees(math.atan2(dy, dx))
    avg = (edge_left + edge_right) / 2.0
    dx, dy = float(avg[0]), float(avg[1])
    if dy < 0:
        dx, dy = -dx, -dy
    if dy == 0:
        return 90.0 if dx != 0 else 0.0
    return math.degrees(math.atan2(dx, dy))


def _cluster_polygons(polys: List[OcrPolygon]) -> List[_SpineCluster]:
    clusters: List[_SpineCluster] = []
    polys_sorted = sorted(polys, key=lambda p: p.center[0])
    for poly in polys_sorted:
        cx = poly.center[0]
        matched: Optional[_SpineCluster] = None
        for cluster in clusters:
            if abs(cluster.center_x - cx) < _SPINE_CLUSTER_X_PX:
                matched = cluster
                break
        if matched is None:
            clusters.append(_SpineCluster(polygons=[poly]))
        else:
            matched.polygons.append(poly)
    return clusters


def _cluster_to_hit(
    cluster: _SpineCluster, ocr: SpineOCR
) -> Optional[SpineHit]:
    cluster.polygons.sort(key=lambda p: p.center[1])
    combined = "".join(p.text for p in cluster.polygons)
    title, match_score = ocr.match_title(combined)
    if title is None:
        return None

    # 只保留 polygon 文字"含 title 字符"的子集来算 bbox/tilt。
    # 这样可以剔除同一根书脊上无关的文字（出版社 / 作者名 / 副标题），
    # 让 bbox 紧贴标题区域，pixel_h 反推深度才准。
    title_chars = set(title)
    title_polys = [
        p for p in cluster.polygons if any(ch in title_chars for ch in p.text)
    ]
    if not title_polys:
        # fuzzy 匹配命中但没有 polygon 含 title 字符（极少见）→ 用全部兜底
        title_polys = list(cluster.polygons)

    all_pts = np.concatenate([p.polygon for p in title_polys], axis=0)
    x1, y1 = np.min(all_pts, axis=0)
    x2, y2 = np.max(all_pts, axis=0)
    tilt = float(
        np.mean([_polygon_long_edge_angle_deg(p.polygon) for p in title_polys])
    )
    avg_ocr = float(np.mean([p.score for p in title_polys]))
    score = float(avg_ocr * match_score)
    return SpineHit(
        matched_title=title,
        bbox=(int(x1), int(y1), int(x2), int(y2)),
        tilt_deg=tilt,
        ocr_score=max(0.0, min(1.0, score)),
        polygons=title_polys,
    )


class SpineDetector:
    """整帧 OCR → 聚类 → 模糊匹配 → SpineHit。"""

    _instance: Optional["SpineDetector"] = None

    def __init__(self) -> None:
        self._ocr = SpineOCR.instance()

    @classmethod
    def instance(cls) -> "SpineDetector":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def detect(self, frame: np.ndarray) -> List[SpineHit]:
        polys = self._ocr.recognize_polygons(frame)
        if not polys:
            return []
        # 横排封面和竖排书脊都让进，靠模糊匹配把不相关的 polygon 滤掉
        clusters = _cluster_polygons(polys)
        hits: List[SpineHit] = []
        for cluster in clusters:
            hit = _cluster_to_hit(cluster, self._ocr)
            if hit is not None:
                hits.append(hit)
        return hits

    def detect_with_unknown_texts(self, frame: np.ndarray) -> tuple[List[SpineHit], List[dict]]:
        """Return known-title hits plus OCR clusters not matched to the catalog.

        The unknown list is intentionally conservative and report-only. It helps
        the operator notice a visible book/text that did not map to
        config.KNOWN_BOOK_TITLES, without letting that text drive motion.
        """
        polys = self._ocr.recognize_polygons(frame)
        if not polys:
            return [], []
        clusters = _cluster_polygons(polys)
        hits: List[SpineHit] = []
        unknowns: List[dict] = []
        seen_unknown: set[str] = set()
        for cluster in clusters:
            cluster.polygons.sort(key=lambda p: p.center[1])
            hit = _cluster_to_hit(cluster, self._ocr)
            if hit is not None:
                hits.append(hit)
                continue

            text = "".join(p.text for p in cluster.polygons).strip()
            if len(text) < 2 or text in seen_unknown:
                continue
            if not any(p.is_vertical_text for p in cluster.polygons):
                continue
            all_pts = np.concatenate([p.polygon for p in cluster.polygons], axis=0)
            x1, y1 = np.min(all_pts, axis=0)
            x2, y2 = np.max(all_pts, axis=0)
            score = float(np.mean([p.score for p in cluster.polygons]))
            unknowns.append(
                {
                    "text": text,
                    "confidence": max(0.0, min(1.0, score)),
                    "bbox": (int(x1), int(y1), int(x2), int(y2)),
                    "reason": "recognized OCR text did not match KNOWN_BOOK_TITLES",
                }
            )
            seen_unknown.add(text)
        return hits, unknowns
