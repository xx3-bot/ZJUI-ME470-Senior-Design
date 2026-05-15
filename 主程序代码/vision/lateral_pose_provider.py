"""仅返回横向坐标 Y（mm，arm frame）的简化视觉入口。

坐标约定（2026-05-11）：
    +X = 机械臂前方（朝 bin）   +Z = 上    +Y = 横向

设计前提：
- bin 物理固定，对齐机械臂中轴
- 书都顶到 bin 后壁
- 抓握的 X（深度）和 Z（高度）由机械同学硬编码：
      X = config.BIN_PICK_DEPTH_MM
      Z = config.BIN_PICK_GRASP_HEIGHT_MM
- 抓握的 Y（横向）由本模块算

数学（针孔反投影，固定 camera-frame 深度）：
    1. OCR 找到书脊中心列像素 u
    2. cv2.undistortPoints 矫正镜头畸变得到归一化坐标 x_norm（已除掉 fx）
    3. Y_camera_frame_mm = x_norm × config.BIN_FIXED_DEPTH_MM
    4. Y_arm_mm          = SIGN × Y_camera_frame_mm + CAMERA_Y_OFFSET_MM
       （SIGN = config.CAMERA_PIXEL_TO_ARM_Y_SIGN，装机后实测决定 +1/-1）

为什么这条路比 world_pose_provider 那条稳：
- 不反推深度（depth 是常数 = BIN_FIXED_DEPTH_MM）
- 不依赖书的物理高度估计（OCR_TO_REAL_HEIGHT_RATIO 之类全无关）
- 误差来源只有：Z 假设偏差 + 边缘畸变 + OCR 中心抖动 + 相机 yaw
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

import cv2
import numpy as np

import config

if TYPE_CHECKING:  # 仅给类型检查用，避免运行时强依赖
    from .spine_detector import SpineHit


_INTRINSICS_JSON = Path(__file__).resolve().parent / "intrinsics_calibration.json"

# 模块级缓存：标定结果不会变，读一次即可
_CACHED_K: Optional[np.ndarray] = None
_CACHED_DIST: Optional[np.ndarray] = None


def _camera_matrix_and_dist() -> Tuple[np.ndarray, np.ndarray]:
    """读 intrinsics_calibration.json → (K 3x3, dist 5,).

    config.py 里只有 fx/fy/cx/cy；JSON 里有完整 5 元 distortion，
    本模块需要 distortion 来做 undistortPoints。
    """
    global _CACHED_K, _CACHED_DIST
    if _CACHED_K is not None and _CACHED_DIST is not None:
        return _CACHED_K, _CACHED_DIST

    with _INTRINSICS_JSON.open(encoding="utf-8") as f:
        data = json.load(f)

    K = np.array([
        [data["fx"], 0.0,         data["cx"]],
        [0.0,        data["fy"],  data["cy"]],
        [0.0,        0.0,         1.0],
    ], dtype=np.float64)
    dist = np.asarray(data["distortion"], dtype=np.float64).reshape(-1)

    _CACHED_K, _CACHED_DIST = K, dist
    return K, dist


def _bbox_center(hit: "SpineHit") -> Tuple[float, float]:
    """SpineHit.bbox = (x1, y1, x2, y2) → 中心像素 (u, v)."""
    x1, y1, x2, y2 = hit.bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _pixel_to_camera_frame_y_mm(
    u_pixel: float, v_pixel: float, depth_mm: float,
) -> float:
    """像素 (u, v) + camera-frame 深度 → camera-frame 横向 mm（带畸变矫正）。

    cv2.undistortPoints 默认输出归一化坐标（已经除以 fx/fy，已矫正畸变）。
    所以最终 Y_cam = x_norm * depth，没有 fx/cx 残留。
    """
    K, dist = _camera_matrix_and_dist()
    pts = np.array([[[u_pixel, v_pixel]]], dtype=np.float64)
    undistorted = cv2.undistortPoints(pts, K, dist).reshape(-1, 2)[0]
    x_norm = float(undistorted[0])
    return x_norm * float(depth_mm)


def get_book_arm_y_mm(
    frame: np.ndarray, title: str
) -> Optional[float]:
    """主入口：一帧图 + title → arm-frame 横向 Y (mm)。

    Args:
        frame: BGR ndarray（已 EXIF 矫正）
        title: 目标书名（OCR 模糊匹配 config.KNOWN_BOOK_TITLES）

    Returns:
        Y_arm_mm（机械臂世界系 Y）；找不到目标书则 None。
    """
    from .spine_detector import SpineDetector  # 局部 import，避开冷启动 PaddleOCR

    if frame is None or frame.size == 0:
        print("[LATERAL] 空帧")
        return None

    hits = SpineDetector.instance().detect(frame)
    matching = [h for h in hits if h.matched_title == title]
    if not matching:
        all_titles = sorted({h.matched_title for h in hits}) or ["<无任何检测>"]
        print(f"[LATERAL] 未命中 {title!r}；本帧 OCR 命中 = {all_titles}")
        return None

    hit = max(matching, key=lambda h: h.ocr_score)
    u_pixel, v_pixel = _bbox_center(hit)

    depth_mm = float(config.BIN_FIXED_DEPTH_MM)
    cam_y_offset_mm = float(config.CAMERA_Y_OFFSET_MM)
    sign = int(config.CAMERA_PIXEL_TO_ARM_Y_SIGN)

    cam_frame_y_mm = _pixel_to_camera_frame_y_mm(u_pixel, v_pixel, depth_mm)
    arm_y_mm = sign * cam_frame_y_mm + cam_y_offset_mm

    print(
        f"[LATERAL] {title!r} bbox={hit.bbox} u={u_pixel:.1f} v={v_pixel:.1f} "
        f"score={hit.ocr_score:.2f} | "
        f"Z_cam={depth_mm:.0f}mm cam_y={cam_frame_y_mm:+.1f}mm "
        f"sign={sign:+d} offset={cam_y_offset_mm:+.1f}mm → arm_y={arm_y_mm:+.1f}mm"
    )
    return arm_y_mm


def get_book_pick_pose(
    frame: np.ndarray, title: str
) -> Optional[Tuple[float, float, float]]:
    """一站式：一帧图 + title → 完整抓握位姿 (arm_X, arm_Y, arm_Z) mm。

    给机械同学直接喂的格式。X 和 Z 是硬编码的常数；Y 是视觉算的。

    Returns:
        (X, Y, Z) mm 三元组，arm 世界系；找不到目标则 None。
    """
    arm_y = get_book_arm_y_mm(frame, title)
    if arm_y is None:
        return None
    arm_x = float(config.BIN_PICK_DEPTH_MM)
    arm_z = float(config.BIN_PICK_GRASP_HEIGHT_MM)
    pose = (arm_x, arm_y, arm_z)
    print(f"[LATERAL] pick_pose = ({pose[0]:+.1f}, {pose[1]:+.1f}, {pose[2]:+.1f}) mm")
    return pose


def _hit_to_arm_y_mm(hit: "SpineHit", depth_mm: float | None = None) -> float:
    u_pixel, v_pixel = _bbox_center(hit)
    depth_mm = float(config.BIN_FIXED_DEPTH_MM if depth_mm is None else depth_mm)
    cam_y_offset_mm = float(config.CAMERA_Y_OFFSET_MM)
    sign = int(config.CAMERA_PIXEL_TO_ARM_Y_SIGN)
    cam_frame_y_mm = _pixel_to_camera_frame_y_mm(u_pixel, v_pixel, depth_mm)
    arm_y_mm = sign * cam_frame_y_mm + cam_y_offset_mm
    print(
        f"[LATERAL] {hit.matched_title!r} bbox={hit.bbox} u={u_pixel:.1f} v={v_pixel:.1f} "
        f"score={hit.ocr_score:.2f} | Z_cam={depth_mm:.0f}mm "
        f"cam_y={cam_frame_y_mm:+.1f}mm sign={sign:+d} "
        f"offset={cam_y_offset_mm:+.1f}mm → arm_y={arm_y_mm:+.1f}mm"
    )
    return arm_y_mm


def _estimate_current_bin_depth(frame: np.ndarray) -> Dict[str, object]:
    """Estimate current bin/book depth from the visible bin grid.

    The config depth is now only a fallback. Real runs may move the bin closer
    or farther, so detected-books loop should plan from this frame's geometry.
    """
    try:
        from .bin_slot_scanner import estimate_bin_grid_geometry

        grid = estimate_bin_grid_geometry(frame)
    except Exception as exc:  # noqa: BLE001 - fallback keeps the demo path alive.
        print(f"[LATERAL] bin depth estimate failed; using config fallback: {exc}")
        grid = {"status": "depth_estimate_error", "error": str(exc)}

    arm_x = grid.get("arm_depth_mm")
    camera_depth = grid.get("camera_depth_mm")
    if arm_x is None or camera_depth is None:
        arm_x = float(config.BIN_PICK_DEPTH_MM)
        camera_depth = float(config.BIN_FIXED_DEPTH_MM)
        source = "config_fallback"
    else:
        arm_x = float(arm_x)
        raw_arm_x = arm_x
        correction = float(getattr(config, "BIN_DEPTH_CORRECTION_MM", 0.0))
        arm_x = raw_arm_x + correction
        camera_depth = arm_x - float(config.CAMERA_POSITION_IN_ARM_MM[0])
        source = "visible_bin_grid"

    print(
        f"[LATERAL] current bin depth: arm_x={arm_x:.1f}mm "
        f"camera_depth={camera_depth:.1f}mm source={source}"
    )
    return {
        "arm_x_mm": arm_x,
        "camera_depth_mm": camera_depth,
        "source": source,
        "bin_grid_geometry": grid,
    }


def _tilt_direction(tilt_deg: float) -> str:
    if tilt_deg > 2.0:
        return "top_to_right"
    if tilt_deg < -2.0:
        return "top_to_left"
    return "near_vertical"


def _hit_metadata(hit: "SpineHit") -> Dict[str, object]:
    dimensions = config.get_book_dimensions_mm(hit.matched_title)
    tilt_deg = float(hit.tilt_deg)
    suggested_tilt = max(-10.0, min(10.0, tilt_deg))
    return {
        "tilt_deg": tilt_deg,
        "tilt_direction": _tilt_direction(tilt_deg),
        "suggested_place_tilt_deg": suggested_tilt,
        "book_dimensions_mm": dimensions,
    }


def get_all_book_pick_poses_from_frame(frame: np.ndarray) -> List[Dict[str, object]]:
    """Detect every known book in one frame and return ordered pick candidates.

    Ordering follows config.KNOWN_BOOK_TITLES. If the same title appears more
    than once, candidates for that title are ordered left-to-right in image
    space as a stable tie-breaker.
    """
    from .spine_detector import SpineDetector

    if frame is None or frame.size == 0:
        print("[LATERAL] 空帧")
        return []

    hits = SpineDetector.instance().detect(frame)
    if not hits:
        print("[LATERAL] 本帧没有命中任何 KNOWN_BOOK_TITLES")
        return []

    title_order = {title: index for index, title in enumerate(config.KNOWN_BOOK_TITLES)}
    ordered_hits = sorted(
        hits,
        key=lambda hit: (
            title_order.get(hit.matched_title, len(title_order)),
            _bbox_center(hit)[0],
            -hit.ocr_score,
        ),
    )

    depth = _estimate_current_bin_depth(frame)
    arm_x = float(depth["arm_x_mm"])
    camera_depth = float(depth["camera_depth_mm"])
    candidates: List[Dict[str, object]] = []
    for hit in ordered_hits:
        arm_y = _hit_to_arm_y_mm(hit, depth_mm=camera_depth)
        pose = (
            arm_x,
            float(arm_y),
            float(config.BIN_PICK_GRASP_HEIGHT_MM),
        )
        print(
            f"[LATERAL] loop candidate: {hit.matched_title!r} "
            f"pick=({pose[0]:+.1f}, {pose[1]:+.1f}, {pose[2]:+.1f}) mm"
        )
        candidates.append(
            {
                "title": hit.matched_title,
                "pick": pose,
                "confidence": float(hit.ocr_score),
                "bbox": hit.bbox,
                "pick_depth_source": depth["source"],
                "bin_grid_geometry": depth.get("bin_grid_geometry"),
                **_hit_metadata(hit),
            }
        )
    return candidates


def _hits_to_pick_candidates(
    hits: List["SpineHit"],
    *,
    arm_x_mm: float | None = None,
    camera_depth_mm: float | None = None,
    pick_depth_source: str = "config_fallback",
    bin_grid_geometry: dict | None = None,
) -> List[Dict[str, object]]:
    title_order = {title: index for index, title in enumerate(config.KNOWN_BOOK_TITLES)}
    ordered_hits = sorted(
        hits,
        key=lambda hit: (
            title_order.get(hit.matched_title, len(title_order)),
            _bbox_center(hit)[0],
            -hit.ocr_score,
        ),
    )

    candidates: List[Dict[str, object]] = []
    arm_x = float(config.BIN_PICK_DEPTH_MM if arm_x_mm is None else arm_x_mm)
    camera_depth = float(config.BIN_FIXED_DEPTH_MM if camera_depth_mm is None else camera_depth_mm)
    for hit in ordered_hits:
        arm_y = _hit_to_arm_y_mm(hit, depth_mm=camera_depth)
        pose = (
            arm_x,
            float(arm_y),
            float(config.BIN_PICK_GRASP_HEIGHT_MM),
        )
        print(
            f"[LATERAL] loop candidate: {hit.matched_title!r} "
            f"pick=({pose[0]:+.1f}, {pose[1]:+.1f}, {pose[2]:+.1f}) mm"
        )
        candidates.append(
            {
                "title": hit.matched_title,
                "pick": pose,
                "confidence": float(hit.ocr_score),
                "bbox": hit.bbox,
                "pick_depth_source": pick_depth_source,
                "bin_grid_geometry": bin_grid_geometry,
                **_hit_metadata(hit),
            }
        )
    return candidates


def scan_book_pick_poses_with_unknowns_from_frame(
    frame: np.ndarray,
) -> Dict[str, object]:
    """Detect known book picks and report OCR text not matched to the catalog."""
    from .spine_detector import SpineDetector

    if frame is None or frame.size == 0:
        print("[LATERAL] 空帧")
        return {"candidates": [], "unknown_texts": []}

    hits, unknown_texts = SpineDetector.instance().detect_with_unknown_texts(frame)
    if not hits:
        print("[LATERAL] 本帧没有命中任何 KNOWN_BOOK_TITLES")
    depth = _estimate_current_bin_depth(frame)
    return {
        "candidates": _hits_to_pick_candidates(
            hits,
            arm_x_mm=float(depth["arm_x_mm"]),
            camera_depth_mm=float(depth["camera_depth_mm"]),
            pick_depth_source=str(depth["source"]),
            bin_grid_geometry=depth.get("bin_grid_geometry"),
        ),
        "unknown_texts": unknown_texts,
        "bin_grid_geometry": depth.get("bin_grid_geometry"),
        "pick_depth_source": depth["source"],
    }


def scan_book_pick_poses_with_unknowns_from_camera() -> Dict[str, object]:
    """Realtime Auto entry: one frame -> known candidates + unknown OCR text."""
    from .camera import CameraError, RGBCamera

    try:
        frame = RGBCamera.instance().read_frame()
    except CameraError as exc:
        print(f"[LATERAL] 相机不可用: {exc}")
        return {"candidates": [], "unknown_texts": [], "camera_error": str(exc)}
    return scan_book_pick_poses_with_unknowns_from_frame(frame)


def get_all_book_pick_poses_from_camera() -> List[Dict[str, object]]:
    """Realtime loop entry: capture one frame and return all ordered pick poses."""
    from .camera import CameraError, RGBCamera

    try:
        frame = RGBCamera.instance().read_frame()
    except CameraError as exc:
        print(f"[LATERAL] 相机不可用: {exc}")
        return []
    return get_all_book_pick_poses_from_frame(frame)


def _fake_pose_if_set() -> Optional[Tuple[float, float, float]]:
    """FAKE_VISION_PICK_POSE 注入短路（给 --fake-vision-pose CLI flag 用）。"""
    fake = getattr(config, "FAKE_VISION_PICK_POSE", None)
    if fake is None:
        return None
    print(
        f"[LATERAL] FAKE_VISION_PICK_POSE 注入 → "
        f"({fake[0]:.1f}, {fake[1]:.1f}, {fake[2]:.1f})"
    )
    return (float(fake[0]), float(fake[1]), float(fake[2]))


def get_pick_pose_from_camera(
    title: str,
) -> Optional[Tuple[float, float, float]]:
    """实时入口：抓相机一帧 + 算 → (arm_X, arm_Y, arm_Z) mm。

    给 config.get_pick_place_plan() 在 USE_VISION_FOR_PICK / VISION_SHADOW_MODE
    打开时调用。

    短路：config.FAKE_VISION_PICK_POSE 不为 None → 直接返回，跳过相机和 OCR。
    否则：抓一帧 → OCR → 找 title → 算 pick_pose。
    相机不可用或目标书未命中时返回 None，主控会回退到 FIXED_PICK_POSE。
    """
    fake = _fake_pose_if_set()
    if fake is not None:
        return fake

    from .camera import CameraError, RGBCamera

    try:
        frame = RGBCamera.instance().read_frame()
    except CameraError as exc:
        print(f"[LATERAL] 相机不可用: {exc}")
        return None
    return get_book_pick_pose(frame, title)
