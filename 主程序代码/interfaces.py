"""当前文件是 mock 数据源。

说明：
1. 这个文件里的函数现在只是为了让控制系统在没有真实视觉/运动模块时也能跑通。
2. 真正联调时，建议队友优先修改 perception_adapter.py 和 motion_adapter.py，
   让那两个适配层去调用他们自己的代码。
3. 如果只是想改测试场景，而不想碰主控逻辑，可以直接改这里的 mock 数据。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict, List

import config
from models import Pose

# Simulation backend imports are lazily initialized if SIM_MODE is active.
_sim_move_to = None
_sim_gripper_command = None
_sim_backend_initialized = False
_visualizer_initialized = False


def _ensure_sim_backend() -> None:
    """Initialize simulation backend when SIM_MODE is enabled."""
    global _sim_move_to, _sim_gripper_command, _sim_backend_initialized
    if _sim_backend_initialized or not config.SIM_MODE:
        return

    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from sim_output.backend import initialize as sim_backend_initialize, move_to as sim_move_to, gripper_command as sim_gripper_command

        _sim_move_to = sim_move_to
        _sim_gripper_command = sim_gripper_command
        sim_backend_initialize(
            config.SIM_OUTPUT_LOG_PATH,
            book_x=config.RETURN_BOOK_X,
            book_y=config.RETURN_BOOK_Y,
            book_z=config.RETURN_BOOK_Z,
        )
        _sim_backend_initialized = True
    except ImportError as exc:
        raise ImportError(f"Unable to import sim_output backend for SIM_MODE: {exc}") from exc


def _ensure_visualizer() -> None:
    """Initialize the optional trajectory recorder when enabled."""
    global _visualizer_initialized
    if _visualizer_initialized or not config.VISUALIZER:
        return

    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from visualization import initialize_recorder

        traj_csv = repo_root / "sim_output" / "control_trajectory.csv"
        initialize_recorder(traj_csv)
        _visualizer_initialized = True
    except ImportError as exc:
        print(f"[TRAJECTORY] Unable to initialize recorder: {exc}")


def _record_waypoint(pose: Pose) -> None:
    """Record a waypoint for trajectory visualization."""
    if not config.VISUALIZER:
        return

    _ensure_visualizer()
    if not _visualizer_initialized:
        return

    try:
        from visualization import record_waypoint

        record_waypoint(pose)
    except ImportError:
        pass


BIN_BOOKS = [
    {"title": "Control Systems", "world_x": -85.0, "world_y": 405.0, "world_z": 0.0, "width": 22.0},
    {"title": "Robotics Dynamics", "world_x": 10.0, "world_y": 418.0, "world_z": 0.0, "width": 20.0},
    {"title": "Microcontrollers", "world_x": 88.0, "world_y": 410.0, "world_z": 0.0, "width": 18.0},
]

SHELF_ZONES = {
    "A_left": {
        "scan_y": 340.0,
        "bottom": 95.0,
        "top": 255.0,
        "depth": 260.0,
        "gaps": [
            {
                "gap_id": 1,
                "start_x": -150.0,
                "end_x": -78.0,
                "width": 72.0,
                "left_boundary_type": "book",
                "right_boundary_type": "open",
                "confidence": 0.96,
            }
        ],
    },
    "A_right": {
        "scan_y": 340.0,
        "bottom": 95.0,
        "top": 255.0,
        "depth": 260.0,
        "gaps": [
            {
                "gap_id": 1,
                "start_x": 35.0,
                "end_x": 115.0,
                "width": 80.0,
                "left_boundary_type": "book",
                "right_boundary_type": "open",
                "confidence": 0.94,
            }
        ],
    },
    "B_left": {
        "scan_y": 340.0,
        "bottom": 360.0,
        "top": 520.0,
        "depth": 265.0,
        "gaps": [
            {
                "gap_id": 1,
                "start_x": -145.0,
                "end_x": -77.0,
                "width": 68.0,
                "left_boundary_type": "book",
                "right_boundary_type": "open",
                "confidence": 0.95,
            }
        ],
    },
    "B_right": {
        "scan_y": 340.0,
        "bottom": 360.0,
        "top": 520.0,
        "depth": 265.0,
        "gaps": [
            {
                "gap_id": 1,
                "start_x": 40.0,
                "end_x": 115.0,
                "width": 75.0,
                "left_boundary_type": "book",
                "right_boundary_type": "open",
                "confidence": 0.95,
            }
        ],
    },
}


def vision_scan_bin_books(camera_pose: Pose) -> List[Dict[str, float]]:
    """Return all books currently visible in the return-bin scan."""
    visible: List[Dict[str, float]] = []
    for book in BIN_BOOKS:
        rel_x = book["world_x"] - camera_pose.x
        rel_y = book["world_y"] - camera_pose.y
        if abs(rel_x) <= 95.0 and 80.0 <= rel_y <= 260.0:
            visible.append(
                {
                    "title": book["title"],
                    "rel_x": rel_x,
                    "rel_y": rel_y,
                    "rel_z": 0.0,
                    "left_edge": rel_x - book["width"] / 2.0,
                    "right_edge": rel_x + book["width"] / 2.0,
                    "depth": rel_y,
                    "confidence": 0.97,
                }
            )
    print(f"[VISION] vision_scan_bin_books(camera_pose={camera_pose}) -> {len(visible)} books")
    return visible


def vision_locate_book(title: str, camera_pose: Pose) -> Dict[str, float] | None:
    """Return a precise observation for a single target book."""
    for book in BIN_BOOKS:
        if book["title"] != title:
            continue
        rel_x = book["world_x"] - camera_pose.x
        rel_y = book["world_y"] - camera_pose.y
        if abs(rel_x) <= 100.0 and 60.0 <= rel_y <= 280.0:
            result = {
                "title": title,
                "rel_x": rel_x,
                "rel_y": rel_y,
                "rel_z": 0.0,
                "left_edge": rel_x - book["width"] / 2.0,
                "right_edge": rel_x + book["width"] / 2.0,
                "depth": rel_y,
                "confidence": 0.99,
            }
            print(f"[VISION] vision_locate_book(title={title}, camera_pose={camera_pose}) -> found")
            return result
    print(f"[VISION] vision_locate_book(title={title}, camera_pose={camera_pose}) -> not found")
    return None


def vision_scan_shelves(camera_pose: Pose) -> List[Dict[str, object]]:
    """Return shelf-layer observations visible around the current camera pose."""
    visible: List[Dict[str, object]] = []
    for zone, shelf in SHELF_ZONES.items():
        if abs(camera_pose.z - ((shelf["bottom"] + shelf["top"] ) / 2.0)) > 110.0:
            continue

        rel_depth = shelf["depth"] - camera_pose.y
        gaps = [
            {
                "gap_id": gap["gap_id"],
                "start_x": gap["start_x"] - camera_pose.x,
                "end_x": gap["end_x"] - camera_pose.x,
                "width": gap["width"],
                "left_boundary_type": gap["left_boundary_type"],
                "right_boundary_type": gap["right_boundary_type"],
                "confidence": gap["confidence"],
            }
            for gap in shelf["gaps"]
        ]
        visible.append(
            {
                "zone": zone,
                "depth": rel_depth,
                "bottom": shelf["bottom"] - camera_pose.z,
                "top": shelf["top"] - camera_pose.z,
                "height": shelf["top"] - shelf["bottom"],
                "gaps": gaps,
                "tilted_books": zone == "A_right",
            }
        )

    print(f"[VISION] vision_scan_shelves(camera_pose={camera_pose}) -> {len(visible)} shelf observations")
    return visible


def motion_move_to(current_pose: Pose, target_pose: Pose) -> bool:
    """Move the gripper from one pose to another and block until complete."""
    if config.SIM_MODE:
        _ensure_sim_backend()
        print(
            "[MOTION][SIM] move_to request: "
            f"from ({current_pose.x:.1f}, {current_pose.y:.1f}, {current_pose.z:.1f}) "
            f"to ({target_pose.x:.1f}, {target_pose.y:.1f}, {target_pose.z:.1f})"
        )
        if _sim_move_to is not None:
            result = _sim_move_to(current_pose, target_pose)
            print(f"[MOTION][SIM] move_to result: {result}")
            if config.VISUALIZER and result and not config.PICK_PLACE_ONLY_MODE:
                _record_waypoint(target_pose)
            if not result:
                print("[MOTION][SIM] forcing move_to success in SIM_MODE for visualization.")
                return True
            return result

    print(
        "[MOTION] move_to request: "
        f"from ({current_pose.x:.1f}, {current_pose.y:.1f}, {current_pose.z:.1f}) "
        f"to ({target_pose.x:.1f}, {target_pose.y:.1f}, {target_pose.z:.1f})"
    )
    if config.VISUALIZER and not config.PICK_PLACE_ONLY_MODE:
        _record_waypoint(target_pose)
    time.sleep(0.1)
    print("[MOTION] move_to ack: True")
    return True


def motion_gripper_command(command: str) -> bool:
    """Block until the mock gripper completes OPEN or CLOSE."""
    if config.SIM_MODE:
        _ensure_sim_backend()
        if _sim_gripper_command is not None:
            return _sim_gripper_command(command)

    print(f"[MOTION] gripper command: {command}")
    time.sleep(0.05)
    print("[MOTION] gripper ack: True")
    return True


def motion_go_home() -> bool:
    """Send a dedicated home command (not a Cartesian point)."""
    if config.SIM_MODE:
        _ensure_sim_backend()
        print("[MOTION][SIM] go_home command acknowledged.")
        return True

    print("[MOTION] go_home command acknowledged.")
    return True


def set_return_book_position(x: float, y: float, z: float | None = None) -> bool:
    """Update the return book target position in the simulation backend."""
    if not config.SIM_MODE:
        print("[INTERFACES] set_return_book_position requires SIM_MODE to be enabled.")
        return False

    _ensure_sim_backend()
    if _sim_move_to is None:
        return False

    try:
        from sim_output.backend import set_book_position
    except ImportError as exc:
        raise ImportError(f"Unable to import sim_output backend for setting book position: {exc}") from exc

    return set_book_position(x, y, z)


def get_return_book_position() -> tuple[float, float, float] | None:
    """Get the current return book target position from the sim backend."""
    if not config.SIM_MODE:
        return None

    _ensure_sim_backend()
    try:
        from sim_output.backend import get_book_position
    except ImportError as exc:
        raise ImportError(f"Unable to import sim_output backend for reading book position: {exc}") from exc

    return get_book_position()
