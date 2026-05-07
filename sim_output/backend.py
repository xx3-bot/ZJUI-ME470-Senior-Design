"""Simulation backend for motion operations."""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAIN_CODE_DIR = PROJECT_ROOT / "主程序代码"
if str(MAIN_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(MAIN_CODE_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import Pose
from sim_output.book_manager import BookManager
from sim_output.ik_helper import IKCostConfig, check_reachability
from sim_output.logger import SimLogger

import config


# Global logger and book manager instances
_logger: SimLogger | None = None
_book_manager: BookManager | None = None


def initialize(
    log_path: str | Path,
    book_x: float = 280.0,
    book_y: float = 100.0,
    book_z: float = 100.0,
) -> None:
    """
    Initialize the simulation backend.
    
    Args:
        log_path: Path to the output log file
        book_x: Initial book X position (mm) relative to the arm base yaw joint
        book_y: Initial book Y position (mm) relative to the arm base yaw joint
        book_z: Initial book Z position (mm) relative to the arm base yaw joint
    """
    global _logger, _book_manager
    _logger = SimLogger(log_path)
    _book_manager = BookManager(x=book_x, y=book_y, z=book_z)

    if config.SIM_MODE and _logger is not None:
        _logger.log_event(
            event_type="sim_mode_configuration",
            details={
                "fixed_runtime_hyperparameters": config.describe_runtime(),
                "return_book_position": {
                    "x": book_x,
                    "y": book_y,
                    "z": book_z,
                },
            },
        )


def move_to(current_pose: Pose, target_pose: Pose) -> bool:
    """
    Simulate moving the gripper to a target pose.
    
    Checks reachability using IK before returning success/failure.
    Logs all details to the log file.
    
    Args:
        current_pose: Current gripper position (x, y, z in mm)
        target_pose: Target gripper position (x, y, z in mm)
    
    Returns:
        True if target is reachable, False otherwise
    """
    if _logger is None:
        # Fallback if not initialized
        return True

    cost_config = IKCostConfig(
        weights=config.IK_COST_WEIGHTS,
        preferred_joint_angles_deg=config.IK_PREFERRED_JOINT_ANGLES_DEG,
        joint_limits_deg=config.IK_JOINT_LIMITS_DEG,
        preferred_alpha_deg=config.IK_PREFERRED_ALPHA_DEG,
    )

    # Check reachability
    ik_result = check_reachability(
        x_mm=target_pose.x,
        y_mm=target_pose.y,
        z_mm=target_pose.z,
        alpha_min_deg=config.IK_ALPHA_MIN_DEG,
        alpha_max_deg=config.IK_ALPHA_MAX_DEG,
        profile_name=config.IK_PROFILE_NAME,
        cost_config=cost_config,
    )

    if not ik_result.reachable and ik_result.reason and "no valid alpha" in ik_result.reason:
        ik_result = check_reachability(
            x_mm=target_pose.x,
            y_mm=target_pose.y,
            z_mm=target_pose.z,
            alpha_min_deg=config.IK_FALLBACK_ALPHA_MIN_DEG,
            alpha_max_deg=config.IK_FALLBACK_ALPHA_MAX_DEG,
            profile_name=config.IK_PROFILE_NAME,
            cost_config=cost_config,
        )
        if ik_result.reachable:
            ik_result = ik_result._replace(reason="Reachable with extended alpha range")
    if not ik_result.reachable and ik_result.reason and "no valid alpha" in ik_result.reason:
        ik_result = check_reachability(
            x_mm=target_pose.x,
            y_mm=target_pose.y,
            z_mm=target_pose.z,
            alpha_min_deg=-180.0,
            alpha_max_deg=180.0,
            profile_name=config.IK_PROFILE_NAME,
            relaxed_alpha_sweep=True,
            cost_config=cost_config,
        )
        if ik_result.reachable:
            ik_result = ik_result._replace(reason="Reachable with relaxed transition alpha sweep")

    # Simulate motion execution time
    time.sleep(0.1)

    book_position = _book_manager.get_position().as_tuple() if _book_manager is not None else None

    # Log the operation
    _logger.log_move_to(
        current_pose=current_pose.as_tuple(),
        target_pose=target_pose.as_tuple(),
        reachable=ik_result.reachable,
        reason=ik_result.reason,
        joint_angles=ik_result.joint_angles_deg,
        servo_pwm=ik_result.servo_pwm,
        command=ik_result.command,
        book_position=book_position,
        error_code=ik_result.error_code,
        selection_cost=ik_result.selection_cost,
        cost_breakdown=ik_result.cost_breakdown,
    )

    return ik_result.reachable


def gripper_command(command: str) -> bool:
    """
    Simulate a gripper command (OPEN or CLOSE).
    
    Args:
        command: Either "OPEN" or "CLOSE"
    
    Returns:
        True if command executed successfully
    """
    if _logger is None:
        # Fallback if not initialized
        return True

    # Simulate gripper execution time
    time.sleep(0.05)

    # Validate command
    normalized = command.upper()
    valid = normalized in ("OPEN", "CLOSE")
    message = None if valid else f"Invalid command: {command}"
    servo_pwm = None
    command_string = None
    if valid:
        servo_pwm = config.GRIPPER_OPEN_PWM if normalized == "OPEN" else config.GRIPPER_CLOSE_PWM
        command_string = (
            "{"
            f"#00{config.GRIPPER_SERVO_ID}P{servo_pwm:04d}T{config.GRIPPER_COMMAND_TIME_MS:04d}!"
            "}"
        )

    # Log the operation
    _logger.log_gripper_command(
        command=command,
        result=valid,
        message=message,
        servo_id=config.GRIPPER_SERVO_ID if valid else None,
        servo_pwm=servo_pwm,
        command_string=command_string,
    )

    return valid


def set_book_position(x: float, y: float, z: float | None = None) -> bool:
    """Update the simulated return-book target position.

    This API is intentionally simple so that a future UI or vision module can
    adjust the target XY position without depending on motion backend internals.
    """
    if _book_manager is None:
        return False

    return _book_manager.set_position(x, y, z)


def get_book_position() -> tuple[float, float, float] | None:
    """Return the current return-book target position as (x, y, z)."""
    if _book_manager is None:
        return None
    return _book_manager.get_position().as_tuple()
