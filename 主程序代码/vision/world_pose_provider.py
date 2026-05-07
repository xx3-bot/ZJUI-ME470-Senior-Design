"""视觉端"世界系抓取点提供者"。

这是视觉模块给机械运动模块的对接入口。

调用方：config.get_pick_place_plan() 在 USE_VISION_FOR_PICK / VISION_SHADOW_MODE
打开时调一次本模块，把视觉看到的书脊点喂给 PickPlacePlan.pick。

返回：
- 找到目标书 → (world_x, world_y, world_z) 毫米，世界原点 = 机械臂底座 yaw 关节
- 没找到、相机不可用、或视觉失败 → None

切换路径（按优先级）：
1. config.FAKE_VISION_PICK_POSE 不为 None → 直接返回它（Mock Injection 测试用）
2. 否则跑相机一帧 + SpineDetector + 反投影 + 外参 → 真实视觉
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Tuple

import config

if TYPE_CHECKING:  # 仅给类型检查器看；运行时不导入，避免提前拉 numpy/cv2
    import numpy as np
    from .spine_detector import SpineHit


def _fake_pose_if_set() -> Optional[Tuple[float, float, float]]:
    fake = getattr(config, "FAKE_VISION_PICK_POSE", None)
    if fake is None:
        return None
    print(
        f"[VISION] FAKE_VISION_PICK_POSE 注入 → ({fake[0]:.1f}, {fake[1]:.1f}, {fake[2]:.1f})"
    )
    return (float(fake[0]), float(fake[1]), float(fake[2]))


def _hit_pixel_height(hit: "SpineHit") -> float:
    """polygon 的"长边"像素长度，作为 spine_height 的代理。"""
    x1, y1, x2, y2 = hit.bbox
    return float(max(abs(y2 - y1), abs(x2 - x1)))


def _hit_to_world_pose(
    hit: "SpineHit", ocr_visible_height_mm: float
) -> Tuple[float, float, float]:
    """SpineHit → 世界系 (x, y, z) mm。

    ocr_visible_height_mm = 该 title 标题文字段在书脊上的物理高度 (mm)，
    即 OCR polygon 长边对应的物理量。
    深度反投影：Z = ocr_visible_height_mm * fy / pixel_h
    """
    from .intrinsics import (
        camera_to_world_mm,
        pinhole_pixel_to_camera_mm,
    )

    x1, y1, x2, y2 = hit.bbox
    cx_px = (x1 + x2) / 2.0
    cy_px = (y1 + y2) / 2.0
    pixel_h = _hit_pixel_height(hit)
    if pixel_h <= 0.0:
        return (0.0, 0.0, 0.0)
    fy = float(config.RGB_INTRINSICS_FY_PX)
    depth_mm = ocr_visible_height_mm * fy / pixel_h
    cam_xyz = pinhole_pixel_to_camera_mm(cx_px, cy_px, depth_mm)
    world_xyz = camera_to_world_mm(cam_xyz)
    print(
        f"[VISION] {hit.matched_title!r} pixel_h={pixel_h:.0f} "
        f"ocr_h={ocr_visible_height_mm:.0f}mm depth={depth_mm:.0f}mm "
        f"cam={tuple(round(v, 1) for v in cam_xyz)} "
        f"world={tuple(round(v, 1) for v in world_xyz)}"
    )
    return world_xyz


def _detect_in_frame(frame: "np.ndarray", title: str) -> Optional["SpineHit"]:
    """在已加载的 frame 上跑 SpineDetector，返回 title 命中的最高分 hit。"""
    from .spine_detector import SpineDetector

    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    hits = SpineDetector.instance().detect(frame)
    matching = [h for h in hits if h.matched_title == title]
    if not matching:
        return None
    return max(matching, key=lambda h: h.ocr_score)


def _grab_and_detect(title: str) -> Optional["SpineHit"]:
    """抓一帧 + SpineDetector，返回 title 命中的 SpineHit；失败 None。"""
    from .camera import CameraError, RGBCamera

    try:
        frame = RGBCamera.instance().read_frame()
    except CameraError as exc:
        print(f"[VISION] 相机不可用: {exc}")
        return None
    return _detect_in_frame(frame, title)


def _resolve_book_ocr_visible_height_mm(title: str) -> Optional[float]:
    """返回 title 对应的"OCR 标题文字段物理高度" (mm)。

    优先级：
    1. KNOWN_BOOK_DIMENSIONS_MM[title]["ocr_visible_height_mm"]（实测值，推荐）
    2. spine_height × OCR_TO_REAL_HEIGHT_RATIO（全局 fallback，精度差）
    """
    if not title:
        print("[VISION] title 为空，跳过")
        return None
    book_dim = config.KNOWN_BOOK_DIMENSIONS_MM.get(title)
    if book_dim is None:
        print(f"[VISION] 未知 book dimension: {title!r}")
        return None

    explicit = float(book_dim.get("ocr_visible_height_mm", 0.0))
    if explicit > 0.0:
        return explicit

    spine = float(book_dim.get("spine_height", 0.0))
    if spine <= 0.0:
        print(f"[VISION] {title!r} 缺 ocr_visible_height_mm 也缺 spine_height")
        return None
    ratio = float(getattr(config, "OCR_TO_REAL_HEIGHT_RATIO", 0.5))
    fallback = spine * ratio
    print(
        f"[VISION] {title!r} 没有 ocr_visible_height_mm，"
        f"用 spine({spine}) × ratio({ratio}) = {fallback:.1f}mm 兜底（精度差）"
    )
    return fallback


def get_pick_world_pose_from_frame(
    frame: "np.ndarray", title: str
) -> Optional[Tuple[float, float, float]]:
    """从已加载的图像帧出发的视觉路径（离线测试 / 回放用）。

    与 get_pick_world_pose 共享所有几何/外参逻辑，仅跳过相机抓帧。
    FAKE_VISION_PICK_POSE 仍然短路返回（保持注入语义一致）。
    """
    fake = _fake_pose_if_set()
    if fake is not None:
        return fake

    ocr_visible_mm = _resolve_book_ocr_visible_height_mm(title)
    if ocr_visible_mm is None:
        return None

    hit = _detect_in_frame(frame, title)
    if hit is None:
        return None
    return _hit_to_world_pose(hit, ocr_visible_mm)


def get_pick_world_pose(title: str) -> Optional[Tuple[float, float, float]]:
    """视觉对接入口（实时相机路径）。返回 (x, y, z) mm 世界坐标，或 None。"""
    fake = _fake_pose_if_set()
    if fake is not None:
        return fake

    ocr_visible_mm = _resolve_book_ocr_visible_height_mm(title)
    if ocr_visible_mm is None:
        return None

    hit = _grab_and_detect(title)
    if hit is None:
        return None
    return _hit_to_world_pose(hit, ocr_visible_mm)


# ---------------------------------------------------------------------------
# Placement 入口（新）：用 AprilTag-calibrated SHELF_POSE + slot scoring
# ---------------------------------------------------------------------------


def get_place_world_pose(zone_id: str) -> Optional[Tuple[float, float, float]]:
    """决策端选定 zone 后，视觉返回 zone 内最佳放置点的世界坐标。

    依赖：
    - 启动校准已完成（runtime_state.get_shelf_pose() 不为 None）
    - vision.slot_scorer 选 best slot

    Returns:
        (world_x, world_y, world_z) mm 或 None（未校准 / zone 无可用 slot）
    """
    fake = _fake_pose_if_set()
    if fake is not None:
        return fake

    from . import runtime_state
    from .slot_scorer import find_best_slot
    from .camera import CameraError, RGBCamera

    if runtime_state.get_shelf_pose() is None:
        print("[VISION] get_place_world_pose: shelf 未校准（请先跑 startup_calibration）")
        return None

    try:
        frame = RGBCamera.instance().read_frame()
    except CameraError as exc:
        print(f"[VISION] 相机不可用: {exc}")
        return None

    slot = find_best_slot(frame, zone_id)
    if slot is None:
        return None

    print(
        f"[VISION] zone {zone_id!r} best slot #{slot.slot_index}: "
        f"world={slot.world_xyz_mm}, clearance={slot.clearance_mm:.1f}, "
        f"score={slot.score:.2f}"
    )
    return slot.world_xyz_mm


# ---------------------------------------------------------------------------
# Pickup-via-bin（新）：用启动校准的 BIN_POSE + ray ∩ bin plane 反投影
# ---------------------------------------------------------------------------


def _pixel_to_world_on_plane(
    pixel_u: float,
    pixel_v: float,
    plane_origin_world_mm,
    plane_normal_world,
    joint0_deg: float,
) -> Optional[Tuple[float, float, float]]:
    """像素 (u, v) → 沿光线 + 平面相交 → 世界系 3D 点。

    plane: 由 origin 和 normal 决定的世界系平面。
    joint0_deg: 拍这帧时机械臂 joint 0 的角度（决定相机外参）。
    """
    import numpy as np
    from .object_localization import camera_to_world_transform

    # 像素 → 相机系射线方向（z=1 平面上的点）
    fx = float(config.RGB_INTRINSICS_FX_PX)
    fy = float(config.RGB_INTRINSICS_FY_PX)
    cx = float(config.RGB_INTRINSICS_CX_PX)
    cy = float(config.RGB_INTRINSICS_CY_PX)
    ray_cam = np.array([
        (pixel_u - cx) / fx,
        (pixel_v - cy) / fy,
        1.0,
    ], dtype=np.float64)
    ray_cam /= np.linalg.norm(ray_cam)

    # 转到世界系
    R_cam_in_arm, t_cam_in_arm = camera_to_world_transform(joint0_deg)
    ray_world = R_cam_in_arm @ ray_cam
    cam_origin_world = t_cam_in_arm
    plane_origin = np.asarray(plane_origin_world_mm, dtype=np.float64)
    plane_normal = np.asarray(plane_normal_world, dtype=np.float64)

    # 求射线 (cam_origin + lambda * ray_world) 与平面 (origin, normal) 的交点
    denom = float(np.dot(plane_normal, ray_world))
    if abs(denom) < 1e-6:
        print("[VISION] ray 平行于物体平面，无交点")
        return None
    lam = float(np.dot(plane_normal, plane_origin - cam_origin_world) / denom)
    if lam <= 0:
        print("[VISION] 交点在相机背后，跳过")
        return None
    point_world = cam_origin_world + lam * ray_world
    return tuple(float(x) for x in point_world)
