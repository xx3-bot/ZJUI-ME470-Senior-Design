"""IK helper using measured_grasp profile from vendor kinematics."""

from __future__ import annotations

from dataclasses import replace
import sys
from pathlib import Path
from typing import Mapping, NamedTuple


# Import vendor kinematics from sim directory
SIM_DIR = Path(__file__).resolve().parent.parent / "sim"
sys.path.insert(0, str(SIM_DIR))

try:
    from vendor_km1_kinematics import PROFILES, analyze_pose, solve_pose, ERROR_MEANINGS
except ImportError as e:
    raise ImportError(
        f"Failed to import vendor_km1_kinematics from {SIM_DIR}: {e}"
    )


class IKResult(NamedTuple):
    """Result of IK computation."""

    reachable: bool
    reason: str | None = None
    target_pose_mm: tuple[float, float, float] | None = None
    alpha_deg: float | None = None
    joint_angles_deg: tuple[float, ...] | None = None
    servo_pwm: tuple[int, ...] | None = None
    command: str | None = None
    error_code: int | None = None
    selection_cost: float | None = None
    cost_breakdown: dict[str, float] | None = None


class IKCostConfig(NamedTuple):
    """Optional candidate-ranking weights for future joint optimization."""

    weights: Mapping[str, float]
    preferred_joint_angles_deg: tuple[float, ...]
    joint_limits_deg: tuple[tuple[float, float], ...]
    preferred_alpha_deg: float | None = None
    previous_joint_angles_deg: tuple[float, ...] | None = None


def _normalized_square(value: float, scale: float) -> float:
    if scale <= 1e-9:
        return 0.0
    return (value / scale) ** 2


def _score_candidate(
    joint_angles_deg: tuple[float, ...],
    alpha_deg: float | None,
    cost_config: IKCostConfig | None,
) -> tuple[float, dict[str, float]]:
    """Return a weighted score for one IK candidate.

    With all weights set to zero this returns zero for every candidate, and the
    caller preserves the previous solver behavior by keeping the later valid
    alpha on ties.
    """
    if cost_config is None:
        return 0.0, {}

    weights = cost_config.weights
    joint_limit = 0.0
    for angle, limits in zip(joint_angles_deg, cost_config.joint_limits_deg):
        lower, upper = limits
        center = (lower + upper) / 2.0
        half_range = (upper - lower) / 2.0
        joint_limit += _normalized_square(angle - center, half_range)

    preferred_posture = 0.0
    for angle, preferred in zip(joint_angles_deg, cost_config.preferred_joint_angles_deg):
        preferred_posture += _normalized_square(angle - preferred, 180.0)

    motion_smoothness = 0.0
    if cost_config.previous_joint_angles_deg is not None:
        for angle, previous in zip(joint_angles_deg, cost_config.previous_joint_angles_deg):
            motion_smoothness += _normalized_square(angle - previous, 180.0)

    alpha_cost = 0.0
    if alpha_deg is not None and cost_config.preferred_alpha_deg is not None:
        alpha_cost = _normalized_square(alpha_deg - cost_config.preferred_alpha_deg, 180.0)

    breakdown = {
        "joint_limit": joint_limit,
        "preferred_posture": preferred_posture,
        "motion_smoothness": motion_smoothness,
        "alpha": alpha_cost,
    }
    total = sum(weights.get(name, 0.0) * value for name, value in breakdown.items())
    return total, breakdown


def _within_joint_limits(
    joint_angles_deg: tuple[float, ...],
    joint_limits_deg: tuple[tuple[float, float], ...],
) -> bool:
    for angle, (lower, upper) in zip(joint_angles_deg, joint_limits_deg):
        if angle < lower or angle > upper:
            return False
    return True


def _solve_pose_with_cost(
    x_mm: float,
    y_mm: float,
    z_mm: float,
    profile,
    alpha_min_deg: float | None,
    alpha_max_deg: float | None,
    cost_config: IKCostConfig | None,
):
    step = -1 if profile.alpha_stop_deg <= profile.alpha_start_deg else 1
    best = None
    best_cost: float | None = None
    best_breakdown: dict[str, float] | None = None
    for alpha in range(profile.alpha_start_deg, profile.alpha_stop_deg + step, step):
        if alpha_min_deg is not None and alpha < alpha_min_deg:
            continue
        if alpha_max_deg is not None and alpha > alpha_max_deg:
            continue
        result = analyze_pose(x_mm, y_mm, z_mm, alpha, profile)
        if not result.ok or result.servo_angles_deg is None:
            continue
        if cost_config is not None and not _within_joint_limits(
            result.servo_angles_deg,
            cost_config.joint_limits_deg,
        ):
            continue
        cost, breakdown = _score_candidate(result.servo_angles_deg, result.alpha_deg, cost_config)
        if best_cost is None or cost <= best_cost:
            best = result
            best_cost = cost
            best_breakdown = breakdown
    return best, best_cost, best_breakdown


def check_reachability(
    x_mm: float,
    y_mm: float,
    z_mm: float,
    alpha_min_deg: float = -45.0,
    alpha_max_deg: float = -25.0,
    profile_name: str = "measured_grasp",
    relaxed_alpha_sweep: bool = False,
    cost_config: IKCostConfig | None = None,
) -> IKResult:
    """
    Check if a target pose is reachable using the measured_grasp profile.
    
    Args:
        x_mm: Target x coordinate in millimeters relative to the arm base yaw joint (left/right).
        y_mm: Target y coordinate in millimeters relative to the arm base yaw joint (forward/back).
        z_mm: Target z coordinate in millimeters (height above base).
        alpha_min_deg: Minimum gripper angle constraint (default -45°)
        alpha_max_deg: Maximum gripper angle constraint (default -25°)
        profile_name: Kinematics profile to use (default "measured_grasp")
        relaxed_alpha_sweep: When True, ignore the profile's narrow alpha
            search sweep and scan the requested alpha range directly. This is
            for simulation transition waypoints where the gripper orientation is
            not the shelf-placement constraint.
        cost_config: Optional IK candidate-ranking config. Default weights are
            expected to be zero for current behavior, leaving room for future
            joint-posture tuning without changing the control state machine.
    
    Returns:
        IKResult containing reachability, reason if not reachable, and full IK plan if reachable.
    """
    if profile_name not in PROFILES:
        return IKResult(
            reachable=False,
            reason=f"Unknown profile '{profile_name}'",
            error_code=-1,
        )

    profile = PROFILES[profile_name]
    if relaxed_alpha_sweep:
        profile = replace(
            profile,
            alpha_start_deg=int(alpha_min_deg),
            alpha_stop_deg=int(alpha_max_deg),
        )
    if cost_config is None:
        ik_result = solve_pose(
            x_mm=x_mm,
            y_mm=y_mm,
            z_mm=z_mm,
            profile=profile,
            alpha_min_deg=alpha_min_deg,
            alpha_max_deg=alpha_max_deg,
        )
        selection_cost = None
        cost_breakdown = None
    else:
        ik_result, selection_cost, cost_breakdown = _solve_pose_with_cost(
            x_mm=x_mm,
            y_mm=y_mm,
            z_mm=z_mm,
            profile=profile,
            alpha_min_deg=alpha_min_deg,
            alpha_max_deg=alpha_max_deg,
            cost_config=cost_config,
        )
        if ik_result is None:
            ik_result = solve_pose(
                x_mm=x_mm,
                y_mm=y_mm,
                z_mm=z_mm,
                profile=profile,
                alpha_min_deg=alpha_min_deg,
                alpha_max_deg=alpha_max_deg,
            )

    if not ik_result.ok:
        error_msg = ERROR_MEANINGS.get(ik_result.error_code, "Unknown error")
        return IKResult(
            reachable=False,
            reason=f"IK failed ({ik_result.error_code}): {error_msg}",
            target_pose_mm=(x_mm, y_mm, z_mm),
            error_code=ik_result.error_code,
        )

    return IKResult(
        reachable=True,
        target_pose_mm=(x_mm, y_mm, z_mm),
        alpha_deg=ik_result.alpha_deg,
        joint_angles_deg=ik_result.servo_angles_deg,
        servo_pwm=ik_result.servo_pwm,
        command=ik_result.command,
        error_code=0,
        selection_cost=selection_cost,
        cost_breakdown=cost_breakdown,
    )
