"""AprilTag / ArUco 检测 + 单 tag 6D 位姿估计。

底层用 cv2.aruco（OpenCV 4.7+）。封装两件事：
1. detect_tags(frame): 在一帧里检测所有 tag，返回 {tag_id: 4 角点像素位置}
2. tag_pose_from_corners(...): 用 cv2.solvePnP 把单个 tag 的角点像素 → 相机系 6D 位姿

不直接处理 bin/shelf 几何；那是 object_localization.py 的事。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import cv2
import numpy as np

import config


@dataclass(frozen=True)
class TagDetection:
    """单个 AprilTag 在一帧中的检测结果（含相机系下 6D 位姿）。"""
    tag_id: int
    corners_pixel: np.ndarray   # (4, 2) float — TL, TR, BR, BL
    R_tag_in_cam: np.ndarray    # (3, 3) — 旋转矩阵
    t_tag_in_cam_mm: np.ndarray # (3,)   — tag 中心在相机系下的位置 (mm)


_DICT_NAME_TO_CONST: Dict[str, int] = {
    "DICT_4X4_50":  cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_5X5_50":  cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_6X6_50":  cv2.aruco.DICT_6X6_50,
}


def _camera_intrinsic_matrix() -> np.ndarray:
    return np.array([
        [config.RGB_INTRINSICS_FX_PX, 0.0,                          config.RGB_INTRINSICS_CX_PX],
        [0.0,                          config.RGB_INTRINSICS_FY_PX, config.RGB_INTRINSICS_CY_PX],
        [0.0,                          0.0,                          1.0],
    ], dtype=np.float64)


def _make_detector() -> "cv2.aruco.ArucoDetector":
    dict_name = getattr(config, "APRILTAG_DICT_NAME", "DICT_4X4_50")
    dict_const = _DICT_NAME_TO_CONST.get(dict_name, cv2.aruco.DICT_4X4_50)
    aruco_dict = cv2.aruco.getPredefinedDictionary(dict_const)
    params = cv2.aruco.DetectorParameters()
    return cv2.aruco.ArucoDetector(aruco_dict, params)


def _tag_object_points(size_mm: float) -> np.ndarray:
    """Tag 4 个角点在 tag 自身坐标系下的 3D 位置。

    tag 中心为原点，z=0 平面，角点顺序 TL, TR, BR, BL。
    """
    s = size_mm / 2.0
    return np.array([
        [-s,  s, 0.0],   # TL
        [ s,  s, 0.0],   # TR
        [ s, -s, 0.0],   # BR
        [-s, -s, 0.0],   # BL
    ], dtype=np.float64)


def tag_pose_from_corners(
    corners_pixel: np.ndarray,
    tag_size_mm: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """单 tag PnP：4 角点像素 → tag 在相机系下的 (R, t)。

    Returns:
        R: (3, 3) 旋转矩阵
        t: (3,) tag 中心在相机系下位置 (mm)
    """
    obj_pts = _tag_object_points(tag_size_mm)
    img_pts = corners_pixel.astype(np.float64).reshape(-1, 1, 2)
    K = _camera_intrinsic_matrix()
    dist = np.zeros((5, 1), dtype=np.float64)  # 假设畸变可忽略；标定 RMS 0.299px 没用畸变也很准
    ok, rvec, tvec = cv2.solvePnP(
        obj_pts, img_pts, K, dist,
        flags=cv2.SOLVEPNP_IPPE_SQUARE,  # 平面正方形 tag 专用解法
    )
    if not ok:
        raise RuntimeError("solvePnP 失败")
    R, _ = cv2.Rodrigues(rvec)
    return R, tvec.reshape(3)


def detect_tags(frame: np.ndarray) -> Dict[int, np.ndarray]:
    """检测画面里所有 AprilTag，返回 {tag_id: corners_pixel (4, 2)}.

    没检测到任何 tag 时返回空 dict（不抛错）。
    """
    if frame is None or frame.size == 0:
        return {}
    detector = _make_detector()
    corners_list, ids, _rejected = detector.detectMarkers(frame)
    if ids is None:
        return {}
    out: Dict[int, np.ndarray] = {}
    for i, tag_id_arr in enumerate(ids):
        tag_id = int(tag_id_arr[0])
        corners = corners_list[i].reshape(4, 2)
        out[tag_id] = corners
    return out


def detect_with_pose(
    frame: np.ndarray, expected_tags: Dict[int, float]
) -> Dict[int, TagDetection]:
    """检测画面里指定的 tag，返回每个 tag 的完整 6D 位姿。

    Args:
        frame: BGR ndarray
        expected_tags: {tag_id: tag_size_mm}，告诉本函数"我期望看到这些 tag，
                       它们的物理边长是多少"

    Returns: {tag_id: TagDetection} —— 没检测到的 tag 不会出现在 dict 里
    """
    raw = detect_tags(frame)
    out: Dict[int, TagDetection] = {}
    for tag_id, size_mm in expected_tags.items():
        corners = raw.get(tag_id)
        if corners is None:
            continue
        try:
            R, t = tag_pose_from_corners(corners, size_mm)
        except RuntimeError as exc:
            print(f"[APRILTAG] tag_id={tag_id} solvePnP 失败: {exc}")
            continue
        out[tag_id] = TagDetection(
            tag_id=tag_id,
            corners_pixel=corners,
            R_tag_in_cam=R,
            t_tag_in_cam_mm=t,
        )
    return out
