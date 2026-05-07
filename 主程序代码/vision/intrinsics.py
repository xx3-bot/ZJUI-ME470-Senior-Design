"""像素 ↔ 相机系 ↔ 世界系（机械臂底座）的坐标换算。

两套接口：

1. 旧版 fake 常数法（保留兼容 bin_scanner.py 的 shadow logging）
   - pixel_to_camera_mm(u, v, frame_size)
   - pixel_x_to_mm(u, frame_width)
   返回的 mm 是用 PIXEL_TO_MM 占位常数算的，不是物理真值。

2. 新版针孔模型（world_pose_provider.py 用）
   - pinhole_pixel_to_camera_mm(u, v, depth_mm)
        用 fx/fy/cx/cy 反投影。需要外部提供 depth。
   - estimate_depth_from_known_height_mm(pixel_h, real_h_mm)
        已知物体真实高度反推距离。
   - camera_to_world_mm(cam_xyz_mm)
        把相机系毫米坐标按外参旋转 + 平移到机械臂底座系。

世界坐标系约定（与队友 motion 模块对齐）：
- 原点 = 机械臂底座 yaw 关节
- x = 左右，y = 前后，z = 离地高度（mm）

相机系约定：
- 光心为原点
- x_cam = 像面右
- y_cam = 像面下
- z_cam = 沿光轴向前（远离相机）
"""

from __future__ import annotations

from typing import Tuple

import config


# ---------------------------------------------------------------------------
# 旧版 fake 常数法（保留以免破坏 bin_scanner.py）
# ---------------------------------------------------------------------------

_LEGACY_PIXEL_TO_MM: float = 0.5
_LEGACY_ASSUMED_BIN_DEPTH_MM: float = 400.0


def pixel_to_camera_mm(
    u: float,
    v: float,
    frame_size: Tuple[int, int],
) -> Tuple[float, float, float]:
    """旧 fake 接口：保留以兼容 bin_scanner.py。"""
    width, height = frame_size
    cx_px = width / 2.0
    cy_px = height / 2.0
    rel_x = (u - cx_px) * _LEGACY_PIXEL_TO_MM
    rel_z = -(v - cy_px) * _LEGACY_PIXEL_TO_MM
    rel_y = _LEGACY_ASSUMED_BIN_DEPTH_MM
    return (rel_x, rel_y, rel_z)


def pixel_x_to_mm(u: float, frame_width: int) -> float:
    """旧 fake 接口：保留。"""
    return (u - frame_width / 2.0) * _LEGACY_PIXEL_TO_MM


# ---------------------------------------------------------------------------
# 新版针孔反投影（world_pose_provider 主路径）
# ---------------------------------------------------------------------------


def pinhole_pixel_to_camera_mm(
    u: float, v: float, depth_mm: float
) -> Tuple[float, float, float]:
    """像素 (u,v) + 已知深度 (mm) → 相机系 (x_cam, y_cam, z_cam) mm。

    标准针孔反投影：
        x_cam = (u - cx) * Z / fx
        y_cam = (v - cy) * Z / fy
        z_cam = Z
    """
    fx = float(config.RGB_INTRINSICS_FX_PX)
    fy = float(config.RGB_INTRINSICS_FY_PX)
    cx = float(config.RGB_INTRINSICS_CX_PX)
    cy = float(config.RGB_INTRINSICS_CY_PX)
    x_cam = (u - cx) * depth_mm / fx
    y_cam = (v - cy) * depth_mm / fy
    z_cam = depth_mm
    return (x_cam, y_cam, z_cam)


def estimate_depth_from_known_height_mm(
    pixel_height: float, real_height_mm: float
) -> float:
    """已知物体真实高度 + polygon 长边像素长度 → 反推距离 (mm)。

    OCR polygon 只覆盖书脊有字部分，物理高度 = real_height_mm * ratio (ratio < 1)。
    Z = (real_height * OCR_TO_REAL_HEIGHT_RATIO) * fy / pixel_height
    """
    if pixel_height <= 0:
        return 0.0
    fy = float(config.RGB_INTRINSICS_FY_PX)
    ratio = max(0.01, float(config.OCR_TO_REAL_HEIGHT_RATIO))
    ocr_visible_mm = real_height_mm * ratio
    return ocr_visible_mm * fy / pixel_height


# ---------------------------------------------------------------------------
# 相机外参：相机系 mm → 机械臂底座系 mm
# ---------------------------------------------------------------------------


def _orientation_rotation(mode: str) -> Tuple[Tuple[float, float, float], ...]:
    """三个朝向枚举对应的 3x3 旋转矩阵（相机系 → 世界系）。

    相机系 (x_cam=右, y_cam=下, z_cam=前)
    世界系 (x_world=左右, y_world=前后, z_world=高度)
    """
    if mode == "FORWARD_HORIZONTAL":
        # 光轴朝 +y_world：z_cam→+y, x_cam→+x, y_cam→-z
        return (
            (1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.0, -1.0, 0.0),
        )
    if mode == "ARM_FACING":
        # 光轴朝 -y_world：z_cam→-y, x_cam→-x, y_cam→-z
        return (
            (-1.0, 0.0, 0.0),
            (0.0, 0.0, -1.0),
            (0.0, -1.0, 0.0),
        )
    if mode == "TOP_DOWN":
        # 光轴朝 -z_world：z_cam→-z, x_cam→+x, y_cam→+y
        return (
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, -1.0),
        )
    raise ValueError(f"未知 CAMERA_ORIENTATION_MODE: {mode}")


def camera_to_world_mm(
    cam_xyz_mm: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    """相机系 mm → 世界系（机械臂底座系）mm。

    world = R @ cam + t

    其中 R 由 CAMERA_ORIENTATION_MODE 决定，t 是 CAMERA_TRANSLATION_MM。
    """
    R = _orientation_rotation(config.CAMERA_ORIENTATION_MODE)
    tx, ty, tz = config.CAMERA_TRANSLATION_MM
    cx, cy, cz = cam_xyz_mm
    wx = R[0][0] * cx + R[0][1] * cy + R[0][2] * cz + tx
    wy = R[1][0] * cx + R[1][1] * cy + R[1][2] * cz + ty
    wz = R[2][0] * cx + R[2][1] * cy + R[2][2] * cz + tz
    return (wx, wy, wz)
