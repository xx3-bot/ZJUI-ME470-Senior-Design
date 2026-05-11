"""待归还书框扫描 pipeline。

OCR-first 版本：
1. 从 iPhone 相机拿一帧
2. SpineDetector 整帧 OCR + 聚类 + 模糊匹配 → SpineHit 列表
3. 用"假标定"把命中 spine 的 bbox 中心/边缘像素映射成相机系毫米
4. 按 CONTROL_INTERFACE_SPEC 拼出 dict 返回给主控

注意：
- mock 与真实的切换在 perception_adapter.py，这里不管
- 没匹配到 KNOWN_BOOK_TITLES 的 spine 会被跳过
- camera_pose 现阶段不用，但保留参数以兼容真机标定后的接口
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

import config
from models import Pose

from .camera import CameraError, RGBCamera
from .intrinsics import pixel_to_camera_mm, pixel_x_to_mm
from .spine_detector import SpineDetector, SpineHit


def _grab_frame() -> Optional[np.ndarray]:
    try:
        return RGBCamera.instance().read_frame()
    except CameraError as exc:
        print(f"[VISION] 相机不可用: {exc}")
        return None


def _compose_pick_point(rel_x: float) -> Dict[str, float | str]:
    """Build the v1 candidate pick point from lateral vision output.

    The current y/z assignments are temporary fixed values. Keep this as a
    single handoff point so startup calibration can later replace them without
    changing the output shape consumed by planning/control.
    """
    return {
        "x": float(rel_x),
        "y": float(config.BIN_PICK_DEPTH_MM),
        "z": float(config.BIN_PICK_GRASP_HEIGHT_MM),
        "source": "fixed_bin_pick_v1",
    }


def _hit_to_book_dict(
    hit: SpineHit, frame_size: Tuple[int, int]
) -> Dict[str, object]:
    x1, y1, x2, y2 = hit.bbox
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    rel_x, rel_y, rel_z = pixel_to_camera_mm(cx, cy, frame_size)
    left_edge = pixel_x_to_mm(float(x1), frame_size[0])
    right_edge = pixel_x_to_mm(float(x2), frame_size[0])
    confidence = max(0.0, min(1.0, hit.ocr_score))
    pick_point = _compose_pick_point(float(rel_x))
    return {
        "title": hit.matched_title,
        "rel_x": float(rel_x),
        "rel_y": float(rel_y),
        "rel_z": float(rel_z),
        "left_edge": float(left_edge),
        "right_edge": float(right_edge),
        "depth": float(rel_y),
        "pick_point": pick_point,
        "confidence": float(confidence),
    }


def detect_books_in_frame(frame: np.ndarray) -> List[Dict[str, object]]:
    """对一帧图像跑 SpineDetector 并拼出主控期望的 dict 列表。"""
    detector = SpineDetector.instance()
    hits = detector.detect(frame)
    if not hits:
        return []
    h, w = frame.shape[:2]
    return [_hit_to_book_dict(hit, (w, h)) for hit in hits]


def scan_bin_books(camera_pose: Pose) -> List[Dict[str, object]]:
    """扫描书框：OCR-first 流水线。"""
    frame = _grab_frame()
    if frame is None:
        print("[VISION] scan_bin_books: 没有可用画面，返回空列表")
        return []
    books = detect_books_in_frame(frame)
    print(
        f"[VISION] scan_bin_books(camera_pose={camera_pose}) -> {len(books)} books"
    )
    return books


def locate_book(title: str, camera_pose: Pose) -> Optional[Dict[str, object]]:
    """精定位某一本目标书；返回最匹配的一条，没找到返回 None。"""
    frame = _grab_frame()
    if frame is None:
        print("[VISION] locate_book: 没有可用画面")
        return None
    candidates = [b for b in detect_books_in_frame(frame) if b["title"] == title]
    if not candidates:
        print(
            f"[VISION] locate_book(title={title}, camera_pose={camera_pose}) -> not found"
        )
        return None
    best = max(candidates, key=lambda b: b["confidence"])
    print(
        f"[VISION] locate_book(title={title}, camera_pose={camera_pose}) -> found"
    )
    return best
