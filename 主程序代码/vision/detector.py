"""YOLO 书本检测器封装。

只输出 COCO class=73 (book) 的边界框。
模型懒加载，首次 detect() 时再 load 权重。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

import config


@dataclass(frozen=True)
class BookBBox:
    """一本书在图像里的检测框（像素坐标）。"""

    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def area(self) -> int:
        return max(0, self.x2 - self.x1) * max(0, self.y2 - self.y1)


class BookDetector:
    """YOLOv8 书本检测器（懒加载单例）。"""

    _instance: Optional["BookDetector"] = None

    def __init__(self, model_path: str, class_id: int, min_conf: float) -> None:
        self._model_path = model_path
        self._class_id = class_id
        self._min_conf = min_conf
        self._model = None  # ultralytics.YOLO

    @classmethod
    def instance(cls) -> "BookDetector":
        if cls._instance is None:
            cls._instance = cls(
                model_path=config.YOLO_MODEL_PATH,
                class_id=config.YOLO_BOOK_CLASS_ID,
                min_conf=config.YOLO_MIN_CONF,
            )
        return cls._instance

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from ultralytics import YOLO  # 懒加载，避免冷启动阻塞

        self._model = YOLO(self._model_path)

    def detect(self, frame: np.ndarray) -> List[BookBBox]:
        """在一帧 BGR 图像中检测所有书的边界框。"""
        self._ensure_loaded()
        assert self._model is not None
        results = self._model.predict(
            source=frame,
            classes=[self._class_id],
            conf=self._min_conf,
            verbose=False,
            show=False,
        )
        if not results:
            return []

        h, w = frame.shape[:2]
        boxes: List[BookBBox] = []
        for box in results[0].boxes:
            xyxy = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            x1 = max(0, int(xyxy[0]))
            y1 = max(0, int(xyxy[1]))
            x2 = min(w, int(xyxy[2]))
            y2 = min(h, int(xyxy[3]))
            if x2 <= x1 or y2 <= y1:
                continue
            boxes.append(BookBBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf))
        return boxes
