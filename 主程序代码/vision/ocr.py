"""书脊 OCR + 模糊匹配 KNOWN_BOOK_TITLES。

PaddleOCR 已开 use_textline_orientation=True，能直接读竖直书脊文字，
所以不再做 90° 旋转 pass（之前 gap_ocr.py 那套会让方向判定翻车）。

对外暴露：
- SpineOCR.recognize_polygons(frame) → [OcrPolygon]，整帧 OCR 的 polygon 级输出
  spine_detector 用这个做聚类。
- SpineOCR.recognize_title(crop) → (title, score)，对一段 crop 直接出标题。
  保留给 bin_scanner 兼容旧路径调用。
- SpineOCR.match_title(text) → (title, score)，单独的模糊匹配工具方法。
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

import config

logging.getLogger("ppocr").setLevel(logging.WARNING)

_CHAR_OVERLAP_RATIO = 0.5


def _maybe_downscale(frame: np.ndarray) -> Tuple[np.ndarray, float]:
    """长边超过 OCR_MAX_INPUT_SIDE 时下采样，避免压垮 PaddleOCR server 模型。

    返回 (resized, scale)；scale = resized / original。
    """
    h, w = frame.shape[:2]
    max_side = max(h, w)
    limit = int(getattr(config, "OCR_MAX_INPUT_SIDE", 1600))
    if max_side <= limit:
        return frame, 1.0
    scale = limit / float(max_side)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    print(
        f"[VISION] OCR 输入下采样: {w}x{h} -> {new_w}x{new_h} (scale={scale:.3f})"
    )
    return resized, scale


@dataclass(frozen=True)
class OcrPolygon:
    """单条 OCR 文本块（带四点 polygon）。"""

    text: str
    score: float
    polygon: np.ndarray  # shape (4, 2), float

    @property
    def center(self) -> Tuple[float, float]:
        cx = float(np.mean(self.polygon[:, 0]))
        cy = float(np.mean(self.polygon[:, 1]))
        return (cx, cy)

    @property
    def is_vertical_text(self) -> bool:
        """长边判定（不依赖 PaddleOCR 顶点顺序）：

        把 polygon 当四边形，看哪一对对边更长。
        长对边方向更接近垂直 → 文字竖直走向（书脊）。
        """
        pts = self.polygon
        edge_a = (pts[1] - pts[0] + pts[2] - pts[3]) / 2.0
        edge_b = (pts[3] - pts[0] + pts[2] - pts[1]) / 2.0
        long_axis = edge_a if np.linalg.norm(edge_a) >= np.linalg.norm(edge_b) else edge_b
        return abs(float(long_axis[1])) > abs(float(long_axis[0]))


class SpineOCR:
    """PaddleOCR 识别器（懒加载单例）。"""

    _instance: Optional["SpineOCR"] = None

    def __init__(self, lang: str, min_score: float, fuzzy_cutoff: float) -> None:
        self._lang = lang
        self._min_score = min_score
        self._fuzzy_cutoff = fuzzy_cutoff
        self._ocr = None  # paddleocr.PaddleOCR

    @classmethod
    def instance(cls) -> "SpineOCR":
        if cls._instance is None:
            cls._instance = cls(
                lang=config.OCR_LANG,
                min_score=config.OCR_MIN_SCORE,
                fuzzy_cutoff=config.OCR_FUZZY_MATCH_CUTOFF,
            )
        return cls._instance

    def _ensure_loaded(self) -> None:
        if self._ocr is not None:
            return
        from paddleocr import PaddleOCR  # 懒加载

        # use_doc_orientation_classify=False：不让 PaddleOCR 自己判定整张图朝向
        # 然后内部旋转，否则返回的 polygon 在旋转后的坐标系里，外部根本对不齐。
        # use_doc_unwarping=False：同理，关掉文档去畸变，避免坐标系再被改一次。
        # use_textline_orientation 仍然开，单行文字方向（横/竖）该转还是会转，
        # 但坐标系不会被改。
        det_name = getattr(config, "OCR_DET_MODEL_NAME", None)
        rec_name = getattr(config, "OCR_REC_MODEL_NAME", None)
        kwargs = dict(
            use_textline_orientation=True,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            lang=self._lang,
        )
        if det_name:
            kwargs["text_detection_model_name"] = det_name
        if rec_name:
            kwargs["text_recognition_model_name"] = rec_name
        self._ocr = PaddleOCR(**kwargs)

    def recognize_polygons(self, frame: np.ndarray) -> List[OcrPolygon]:
        """整帧 OCR；返回所有通过 min_score 过滤的文本块（带 polygon）。

        polygon 坐标始终在传入 frame 的原始坐标系中：内部如果做了下采样，
        OCR 出的坐标会按比例还原后再返回。
        """
        if frame is None or frame.size == 0:
            return []
        small, scale = _maybe_downscale(frame)
        self._ensure_loaded()
        assert self._ocr is not None
        try:
            result = self._ocr.predict(small)
        except Exception as exc:
            print(f"[VISION-OCR] PaddleOCR 推理失败: {exc}")
            return []
        if not (result and result[0] and isinstance(result[0], dict)):
            return []
        res = result[0]
        polys = res.get("dt_polys") or []
        texts = res.get("rec_texts") or []
        scores = res.get("rec_scores") or []
        inv = 1.0 / scale if scale != 0 else 1.0
        out: List[OcrPolygon] = []
        for poly, text, score in zip(polys, texts, scores):
            text_str = str(text).strip()
            if not text_str:
                continue
            score_val = float(score)
            if score_val < self._min_score:
                continue
            poly_arr = np.asarray(poly, dtype=np.float32).reshape(-1, 2)
            if poly_arr.shape[0] != 4:
                continue
            if scale != 1.0:
                poly_arr = (poly_arr * inv).astype(np.float32)
            out.append(OcrPolygon(text=text_str, score=score_val, polygon=poly_arr))
        return out

    def match_title(self, combined: str) -> Tuple[Optional[str], float]:
        """把拼接后的文本对照 KNOWN_BOOK_TITLES 做模糊匹配。"""
        if not combined:
            return (None, 0.0)
        for title in config.KNOWN_BOOK_TITLES:
            if title in combined or combined in title:
                return (title, 1.0)
        best_title: Optional[str] = None
        best_overlap = 0.0
        for title in config.KNOWN_BOOK_TITLES:
            if not title:
                continue
            common = sum(1 for c in title if c in combined)
            overlap = common / len(title)
            if overlap > best_overlap:
                best_overlap = overlap
                best_title = title
        if best_title is not None and best_overlap >= _CHAR_OVERLAP_RATIO:
            return (best_title, best_overlap)
        matches = difflib.get_close_matches(
            combined,
            config.KNOWN_BOOK_TITLES,
            n=1,
            cutoff=self._fuzzy_cutoff,
        )
        if matches:
            ratio = difflib.SequenceMatcher(None, combined, matches[0]).ratio()
            return (matches[0], ratio)
        return (None, 0.0)

    def recognize_title(self, crop: np.ndarray) -> Tuple[Optional[str], float]:
        """对一段书脊 crop 直接出标题（保留给旧调用路径用）。"""
        if crop is None or crop.size == 0:
            return (None, 0.0)
        if crop.shape[0] < 20 or crop.shape[1] < 20:
            return (None, 0.0)
        polys = self.recognize_polygons(crop)
        if not polys:
            return (None, 0.0)
        combined = "".join(p.text for p in polys)
        best_score = max(p.score for p in polys)
        title, match_score = self.match_title(combined)
        if title is None:
            return (None, 0.0)
        return (title, float(best_score * match_score))
