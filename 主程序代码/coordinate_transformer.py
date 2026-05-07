"""Coordinate transformation helpers for camera, gripper, and world poses."""

from __future__ import annotations

import math
from typing import Iterable, List

import config
from models import Pose


class CoordinateTransformer:
    @staticmethod
    def get_camera_pose(gripper_pose: Pose) -> Pose:
        """Compute the camera-center pose from the gripper pose and the mounting offsets."""
        if config.GRIP_ORIENTATION == "UP":
            return Pose(gripper_pose.x - config.OFFSET_X, gripper_pose.y - config.OFFSET_Y, gripper_pose.z)
        if config.GRIP_ORIENTATION == "DOWN":
            return Pose(gripper_pose.x - config.OFFSET_X, gripper_pose.y + config.OFFSET_Y, gripper_pose.z)
        if config.GRIP_ORIENTATION == "LEFT":
            return Pose(gripper_pose.x + config.OFFSET_X, gripper_pose.y - config.OFFSET_Y, gripper_pose.z)
        if config.GRIP_ORIENTATION == "RIGHT":
            return Pose(gripper_pose.x - config.OFFSET_X, gripper_pose.y - config.OFFSET_Y, gripper_pose.z)
        return gripper_pose

    @staticmethod
    def camera_to_world(camera_pose: Pose, rel_x: float, rel_y: float, rel_z: float = 0.0) -> Pose:
        """Convert perception data expressed in the camera frame into the world frame."""
        return Pose(
            camera_pose.x + rel_x,
            camera_pose.y + rel_y,
            camera_pose.z + rel_z,
        )

    @staticmethod
    def calculate_arc_points(z: float = 0.0, steps: int | None = None) -> List[Pose]:
        """Generate gripper poses for horizontal sweep scanning over the return bin."""
        step_count = steps if steps is not None else config.BOOK_SCAN_STEPS
        start_angle = -config.SCAN_ARC / 2.0
        max_xy_radius = math.sqrt(max(0.0, config.ARM_LENGTH ** 2 - z ** 2))
        points: List[Pose] = []
        for index in range(step_count + 1):
            angle_deg = start_angle + (config.SCAN_ARC / step_count) * index
            angle_rad = math.radians(angle_deg)
            x = max_xy_radius * math.sin(angle_rad)
            y = max_xy_radius * math.cos(angle_rad)
            points.append(Pose(x, y, z))
        return points

    @staticmethod
    def calculate_vertical_scan_points(x: float, y: float, z_min: float, z_max: float) -> List[Pose]:
        """Generate vertical scan poses for searching shelf layers."""
        if z_max < z_min:
            z_min, z_max = z_max, z_min

        points: List[Pose] = []
        current_z = z_min
        while current_z <= z_max + 1e-6:
            points.append(Pose(x, y, current_z))
            current_z += config.SHELF_SCAN_STEP_MM

        if not points or points[-1].z < z_max:
            points.append(Pose(x, y, z_max))
        return points

    @staticmethod
    def describe_pose_sequence(poses: Iterable[Pose]) -> str:
        return ", ".join(f"({pose.x:.1f}, {pose.y:.1f}, {pose.z:.1f})" for pose in poses)
