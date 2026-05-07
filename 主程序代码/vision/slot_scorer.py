"""Shelf zone 内的 slot 评分（placement 用）。

在已校准 SHELF_POSE 之后，给某个 zone 找一个空位放新书。

算法：
1. 已知 zone 在世界系下的几何（中心、宽、高）+ shelf 位姿
2. 把 zone 横向均分为 N=slot_count 个 slot
3. 检测 zone ROI 内已有书的位置（用 SpineDetector / OCR）
4. 对每个 slot 计算 clearance（左右最近书脊的距离）
5. clearance ≥ GRIPPER_OPEN_WIDTH + SAFETY_MARGIN 才有效
6. 取得分最高的 slot 返回

**注意**：当前实现是骨架，slot 占用检测的具体方法（YOLO 还是 SpineDetector）
等真机数据回来再调。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

import config

from . import runtime_state


@dataclass(frozen=True)
class SlotScore:
    """单个 slot 的评分结果。"""
    slot_index: int                            # 0..N-1
    pixel_center: Tuple[int, int]              # 在 zone ROI 内的像素中心 (u, v)
    world_xyz_mm: Tuple[float, float, float]   # 该 slot 在世界系下的中心点
    clearance_mm: float                        # 实际可用横向空隙（min 左/右）
    score: float                               # 评分（高=优先选）；< 阈值时 = -inf


def _zone_origin_world_mm(zone_id: str) -> Optional[np.ndarray]:
    """zone 中心在世界系下的位置；shelf 没校准就 None。"""
    shelf_pose = runtime_state.get_shelf_pose()
    if shelf_pose is None:
        return None
    zone = config.SHELF_MODEL["zones"].get(zone_id)
    if zone is None:
        return None
    offset_local = np.array(zone["center_offset_mm"], dtype=np.float64)
    origin_world = np.array(shelf_pose.origin_world_mm, dtype=np.float64)
    return shelf_pose.rotation_world @ offset_local + origin_world


def _detect_books_in_zone(frame: np.ndarray, zone_id: str) -> List[Tuple[int, int, int, int]]:
    """在 zone 区域里检测已有书的 bbox（像素坐标）。

    当前简化实现：跑 SpineDetector 全图 → 取所有 hit。
    将来可以裁到 zone ROI 区域提速 + 减误检。

    Returns: list of (x1, y1, x2, y2) 像素 bbox
    """
    from .spine_detector import SpineDetector

    detector = SpineDetector.instance()
    hits = detector.detect(frame)
    return [hit.bbox for hit in hits]


def _zone_pixel_extent(
    frame_shape: Tuple[int, int], zone_id: str
) -> Optional[Tuple[int, int, int]]:
    """计算 zone 在画面里的横向像素范围 (x_left, x_right, y_center)。

    简化实现：暂时假设 zone 占整帧（TODO: 等校准 + 投影逻辑完整后用 SHELF_POSE
    把 zone 几何投影到画面）。这样即便 SHELF_POSE 没校准也能跑通骨架测试。
    """
    h, w = frame_shape[:2]
    # TODO: 用 shelf_pose + zone center_offset + zone width 投影到画面，
    # 得到准确的 zone 在像素空间的覆盖范围
    return (0, w, h // 2)


def find_best_slot(frame: np.ndarray, zone_id: str) -> Optional[SlotScore]:
    """对指定 zone 找最佳放置 slot。

    Returns:
        SlotScore 或 None（zone 没有可用 slot / shelf 未校准）
    """
    if runtime_state.get_shelf_pose() is None:
        print("[SLOT] shelf 未校准，无法评分")
        return None
    zone = config.SHELF_MODEL["zones"].get(zone_id)
    if zone is None:
        print(f"[SLOT] 未知 zone: {zone_id!r}")
        return None

    extent = _zone_pixel_extent(frame.shape, zone_id)
    if extent is None:
        return None
    x_left, x_right, y_center = extent

    # zone 内已有书的 bbox
    book_bboxes = _detect_books_in_zone(frame, zone_id)
    book_x_centers = sorted([
        (b[0] + b[2]) / 2.0 for b in book_bboxes
    ])

    slot_count = int(zone["slot_count"])
    slot_width_px = (x_right - x_left) / slot_count

    # 评分阈值：clearance 要 ≥ 这个像素宽度，slot 才有效
    # 简化：用 slot 宽的 60% 作为像素阈值（TODO: 用实际深度 + fx 算物理 mm）
    required_clearance_px = slot_width_px * 0.6

    candidates: List[SlotScore] = []
    for i in range(slot_count):
        slot_cx = x_left + slot_width_px * (i + 0.5)
        # 该 slot 与所有书的最小横向距离
        if not book_x_centers:
            clearance_px = max(slot_cx - x_left, x_right - slot_cx)
        else:
            distances = [abs(slot_cx - bx) for bx in book_x_centers]
            clearance_px = min(distances)

        if clearance_px < required_clearance_px:
            score = float("-inf")
        else:
            score = float(clearance_px - required_clearance_px)

        # 把像素中心反投影到世界系（用 shelf_pose）
        world_xyz = _project_zone_pixel_to_world(zone_id, slot_cx, y_center)

        candidates.append(SlotScore(
            slot_index=i,
            pixel_center=(int(slot_cx), int(y_center)),
            world_xyz_mm=world_xyz,
            clearance_mm=float(clearance_px),  # TODO: 转 mm
            score=score,
        ))

    valid = [c for c in candidates if c.score != float("-inf")]
    if not valid:
        print(f"[SLOT] zone {zone_id} 没有可用 slot（都被书塞满或 clearance 不足）")
        return None
    return max(valid, key=lambda c: c.score)


def _project_zone_pixel_to_world(
    zone_id: str, pixel_x: float, pixel_y: float
) -> Tuple[float, float, float]:
    """zone 内一个像素中心点 → 世界系坐标。

    简化实现：直接用 zone 中心 + zone 内横向偏移（按像素比例分到 zone width）。
    TODO: 真正的 ray ∩ plane 计算（等 world_pose_provider 重构完）。
    """
    zone_center = _zone_origin_world_mm(zone_id)
    if zone_center is None:
        return (0.0, 0.0, 0.0)
    zone = config.SHELF_MODEL["zones"][zone_id]
    grasp_z = float(zone["grasp_z_mm"])
    return (float(zone_center[0]), float(zone_center[1]), grasp_z)
