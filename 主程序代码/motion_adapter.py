"""运动模块适配层。

重点：
1. 控制系统只通过这里给你们发指令。
2. 控制系统发的是“当前夹爪坐标 -> 目标夹爪坐标”，路径规划由你们自己完成。
3. 除了移动，还有两个单独指令：OPEN / CLOSE。
4. 只有当动作真的完成后，才能返回 True。否则主控不会进入下一步。
"""

from __future__ import annotations

import interfaces
from models import Pose


def move_to(current_pose: Pose, target_pose: Pose) -> bool:
    """把夹爪从 current_pose 移动到 target_pose。

    参数说明：
    - current_pose: 当前夹爪世界坐标
    - target_pose: 目标夹爪世界坐标

    返回要求：
    - 运动完成后返回 True
    - 如果失败，未来可以返回 False，主控会进入失败处理逻辑

    重要：
    - 这里不要要求主控传速度、关节角、轨迹点等额外参数。
    - 这些属于运动模块内部实现。
    """

    return interfaces.motion_move_to(current_pose, target_pose)


def gripper_command(command: str) -> bool:
    """夹爪指令。

    当前只允许两种：
    - OPEN: 松开爪子
    - CLOSE: 收紧爪子

    返回要求：
    - 执行完成后返回 True
    """

    return interfaces.motion_gripper_command(command)


def go_home() -> bool:
    """Return robot to home pose through dedicated controller command."""
    return interfaces.motion_go_home()
