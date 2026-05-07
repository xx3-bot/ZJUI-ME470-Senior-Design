"""运行时状态：启动校准之后视觉模块在内存里维护的"bin/shelf 在世界系下的位姿"。

config.py 存的是**编译期常量**（书架/还书框的几何模型 + 相机外参）。
本模块存的是**启动时通过 AprilTag 算出来的"物体在世界系的位姿"**。

启动校准流程（参见 vision/object_localization.py）：
    object_localization.run_startup_calibration() 调用一次
    → 检测 BIN/SHELF 的 AprilTag → 算出位姿 → 写到 runtime_state.BIN_POSE / SHELF_POSE
    → 之后所有 world_pose_provider 的查询都从这两个 pose 出发

如果未校准就调 get_bin_pose() / get_shelf_pose()，返回 None；上层负责处理。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class ObjectPose:
    """物体（bin / shelf）几何参考点在世界系下的 6D 位姿。

    Attributes:
        origin_world_mm: 物体几何参考点（建议=前面板左下角）在世界系的位置 (3,)
        rotation_world: 物体本体坐标系到世界系的 3×3 旋转矩阵
                       即 world_pt = rotation_world @ object_local_pt + origin_world_mm
        plane_normal_world: 物体"前平面"在世界系下的单位法向（朝相机方向）
                           用来做 ray-plane 反投影
        confidence: 校准置信度 [0, 1]，多个 tag 检测一致性高 → 接近 1
    """
    origin_world_mm: Tuple[float, float, float]
    rotation_world: np.ndarray
    plane_normal_world: Tuple[float, float, float]
    confidence: float


# 模块级单例：startup_calibration 写、world_pose_provider 读
_BIN_POSE: Optional[ObjectPose] = None
_SHELF_POSE: Optional[ObjectPose] = None


def set_bin_pose(pose: ObjectPose) -> None:
    global _BIN_POSE
    _BIN_POSE = pose


def set_shelf_pose(pose: ObjectPose) -> None:
    global _SHELF_POSE
    _SHELF_POSE = pose


def get_bin_pose() -> Optional[ObjectPose]:
    return _BIN_POSE


def get_shelf_pose() -> Optional[ObjectPose]:
    return _SHELF_POSE


def is_calibrated() -> bool:
    return _BIN_POSE is not None and _SHELF_POSE is not None


def reset() -> None:
    """主要给测试用：清除已有校准结果。"""
    global _BIN_POSE, _SHELF_POSE
    _BIN_POSE = None
    _SHELF_POSE = None
