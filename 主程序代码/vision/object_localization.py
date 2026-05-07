"""启动时一键校准 bin / shelf 在世界系下的位姿。

流程总览：
1. 机械臂转 joint 0 = JOINT0_BIN_SCAN_DEG，C920e 拍一帧
2. 用 cv2.aruco 检测 BIN_MODEL.tags 里所有期望的 tag → 各自给出相机系下 6D 位姿
3. 通过相机相对机械臂底座的固定外参（CAMERA_MOUNT_*）+ 当前 joint 0 角度
   把 tag 位姿从相机系转到机械臂世界系
4. 用每个 tag 在 bin 物体上的局部偏移（BIN_MODEL.tags[id].offset_mm）
   反推出 bin "几何参考点" 在世界系的位姿
5. 多个 tag 的反推结果取平均（旋转用 SVD 投影，位移用算术平均）→ 写入 runtime_state.set_bin_pose
6. shelf 同样的流程

可独立 import 调用，也可由 main.py 启动时调用一次。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

import config

from . import runtime_state
from .apriltag_calibrator import TagDetection, detect_with_pose


# ---------------------------------------------------------------------------
# Camera mount transform: 相机系 → 机械臂世界系
# ---------------------------------------------------------------------------


def _rotation_matrix_y(deg: float) -> np.ndarray:
    """绕世界 y 轴（垂直轴）旋转的 3×3 矩阵。"""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([
        [ c, 0.0,  s],
        [0.0, 1.0, 0.0],
        [-s, 0.0,  c],
    ], dtype=np.float64)


def _rotation_matrix_x(deg: float) -> np.ndarray:
    """绕世界 x 轴旋转的 3×3 矩阵。"""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([
        [1.0, 0.0, 0.0],
        [0.0,  c, -s],
        [0.0,  s,  c],
    ], dtype=np.float64)


def camera_to_world_transform(joint0_deg: float) -> Tuple[np.ndarray, np.ndarray]:
    """返回当前 joint 0 角度下，相机相对机械臂底座的 (R_cam_in_arm, t_cam_in_arm)。

    模型假设：
    - 相机刚性安装在 joint 0 转盘上
    - 相机镜头中心相对 joint 0 轴心的偏移 = CAMERA_MOUNT_OFFSET_MM
    - 相机光轴在 joint 0 = 0° 时朝 +y_world，仰角 = CAMERA_MOUNT_PITCH_DEG
    - joint 0 旋转 → 相机绕 y_world 轴旋转 joint0_deg
    """
    R_pitch = _rotation_matrix_x(config.CAMERA_MOUNT_PITCH_DEG)
    R_yaw = _rotation_matrix_y(joint0_deg)
    # 相机本体坐标到世界系：先应用 pitch 让光轴上仰，再绕 y 转 joint0
    R_cam_in_arm = R_yaw @ R_pitch
    # 相机原点位置：joint 0 = 0 时给 CAMERA_MOUNT_OFFSET_MM；joint 0 转后位置也跟着转
    t_cam_in_arm_zero = np.array(config.CAMERA_MOUNT_OFFSET_MM, dtype=np.float64)
    t_cam_in_arm = R_yaw @ t_cam_in_arm_zero
    return R_cam_in_arm, t_cam_in_arm


# ---------------------------------------------------------------------------
# 单 tag → 物体几何参考点的位姿反推
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ObjectPoseEstimate:
    """单 tag 反推出的"物体参考点位姿"。多 tag 时取平均。"""
    R_object_in_world: np.ndarray   # (3, 3)
    t_object_in_world_mm: np.ndarray # (3,)
    contributing_tag_id: int


def _tag_pose_to_object_pose(
    detection: TagDetection,
    tag_offset_in_object_mm: Tuple[float, float, float],
    R_cam_in_arm: np.ndarray,
    t_cam_in_arm_mm: np.ndarray,
) -> _ObjectPoseEstimate:
    """单 tag 检测 + 已知 tag 在物体上的局部偏移 → 物体参考点在世界系下位姿。

    数学链：
    - tag 在世界系：
        R_tag_in_world = R_cam_in_arm @ R_tag_in_cam
        t_tag_in_world = R_cam_in_arm @ t_tag_in_cam + t_cam_in_arm
    - 物体参考点 = tag 中心 - R_tag_in_world @ tag_offset_in_object
      （tag 是 rigid 贴在物体上的，所以物体姿态 = tag 姿态）
    """
    R_tag_in_world = R_cam_in_arm @ detection.R_tag_in_cam
    t_tag_in_world = R_cam_in_arm @ detection.t_tag_in_cam_mm + t_cam_in_arm_mm

    offset_in_object = np.array(tag_offset_in_object_mm, dtype=np.float64)
    t_object_in_world = t_tag_in_world - R_tag_in_world @ offset_in_object

    return _ObjectPoseEstimate(
        R_object_in_world=R_tag_in_world,
        t_object_in_world_mm=t_object_in_world,
        contributing_tag_id=detection.tag_id,
    )


def _average_estimates(
    estimates: List[_ObjectPoseEstimate],
) -> Tuple[np.ndarray, np.ndarray, float]:
    """多个 tag 的反推结果取平均。

    旋转：先平均后用 SVD 投影回 SO(3)
    位移：算术平均
    confidence：基于多个估计的位移一致性（差异越小，置信度越高）
    """
    if not estimates:
        raise ValueError("没有 tag 估计可平均")

    # 位移平均
    t_avg = np.mean([e.t_object_in_world_mm for e in estimates], axis=0)

    # 旋转平均：把每个 R 当成 (3,3)，先算术平均，再 SVD 投影到 SO(3)
    R_sum = np.sum([e.R_object_in_world for e in estimates], axis=0)
    U, _, Vt = np.linalg.svd(R_sum)
    R_avg = U @ Vt
    if np.linalg.det(R_avg) < 0:
        # 防止反射
        Vt_fixed = Vt.copy()
        Vt_fixed[-1, :] *= -1.0
        R_avg = U @ Vt_fixed

    # confidence: 位移分散度 → 越小越好
    if len(estimates) == 1:
        confidence = 0.7  # 单 tag 给个保守值
    else:
        spreads = np.std([e.t_object_in_world_mm for e in estimates], axis=0)
        max_spread_mm = float(np.max(spreads))
        # 经验：< 5mm 散度 → 1.0；> 30mm → 0.3
        confidence = max(0.3, min(1.0, 1.0 - (max_spread_mm - 5.0) / 25.0))

    return R_avg, t_avg, confidence


# ---------------------------------------------------------------------------
# 一键校准入口
# ---------------------------------------------------------------------------


def calibrate_object_from_frame(
    frame: np.ndarray,
    object_model: dict,
    joint0_deg: float,
) -> Optional[runtime_state.ObjectPose]:
    """对一帧图，按 object_model（BIN_MODEL 或 SHELF_MODEL）反推物体在世界系的位姿。

    object_model 必须含 "tags" 字段：{tag_id: {"size_mm": ..., "offset_mm": ...}, ...}

    Returns:
        ObjectPose 或 None（一个 tag 都没检测到）
    """
    expected_tags = {tid: info["size_mm"] for tid, info in object_model["tags"].items()}
    detections = detect_with_pose(frame, expected_tags)

    if not detections:
        print(
            f"[OBJ-LOC] 未检测到任何期望的 tag (期望 {list(expected_tags.keys())})。"
            f" 请检查 tag 是否被遮挡 / 拍照角度"
        )
        return None

    R_cam_in_arm, t_cam_in_arm = camera_to_world_transform(joint0_deg)

    estimates: List[_ObjectPoseEstimate] = []
    for tag_id, det in detections.items():
        offset_mm = object_model["tags"][tag_id]["offset_mm"]
        est = _tag_pose_to_object_pose(det, offset_mm, R_cam_in_arm, t_cam_in_arm)
        estimates.append(est)

    R_avg, t_avg, confidence = _average_estimates(estimates)

    # 物体平面法向（在物体本体系下默认 +z）→ 转到世界系
    plane_normal_local = np.array(
        object_model.get("zone_plane_normal")  # shelf 用
        or object_model.get("pickable_plane_normal", (0.0, 0.0, 1.0))  # bin 用
    , dtype=np.float64)
    plane_normal_world = R_avg @ plane_normal_local

    print(
        f"[OBJ-LOC] 用 {len(detections)} 个 tag 校准: "
        f"origin={t_avg.round(1).tolist()} mm, conf={confidence:.2f}, "
        f"contributing_tags={list(detections.keys())}"
    )

    return runtime_state.ObjectPose(
        origin_world_mm=tuple(float(x) for x in t_avg),
        rotation_world=R_avg,
        plane_normal_world=tuple(float(x) for x in plane_normal_world),
        confidence=float(confidence),
    )


def run_startup_calibration(
    frame_for_bin: np.ndarray,
    frame_for_shelf: np.ndarray,
) -> bool:
    """主入口：传入两帧（一帧看 bin，一帧看 shelf），完成校准，写入 runtime_state。

    主控（main.py）负责：
    - 把机械臂转到 JOINT0_BIN_SCAN_DEG，拍一帧 → 传给 frame_for_bin
    - 把机械臂转到 JOINT0_SHELF_SCAN_DEG，拍一帧 → 传给 frame_for_shelf

    Returns:
        True  if 两个物体都成功校准
        False if 任何一个失败（已打日志）
    """
    bin_pose = calibrate_object_from_frame(
        frame_for_bin, config.BIN_MODEL, config.JOINT0_BIN_SCAN_DEG)
    shelf_pose = calibrate_object_from_frame(
        frame_for_shelf, config.SHELF_MODEL, config.JOINT0_SHELF_SCAN_DEG)

    if bin_pose is None:
        print("[OBJ-LOC] 启动校准失败：bin 定位失败")
        return False
    if shelf_pose is None:
        print("[OBJ-LOC] 启动校准失败：shelf 定位失败")
        return False

    runtime_state.set_bin_pose(bin_pose)
    runtime_state.set_shelf_pose(shelf_pose)
    print("[OBJ-LOC] 启动校准成功")
    return True
