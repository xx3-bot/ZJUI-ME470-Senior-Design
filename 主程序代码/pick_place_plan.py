"""Shared pick/place pose plan for the minimal MuJoCo validation flow.

This module is the handoff point for future perception or planning code. The
controller reads one plan shape; today it is filled by defaults or CLI args,
and later a vision module can fill the same fields directly.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from models import Pose


DEFAULT_PICK_APPROACH_CLEARANCE_MM = 100.0
DEFAULT_POST_GRASP_LIFT_MM = 65.0
DEFAULT_POST_GRASP_RETRACT_MM = 50.0
DEFAULT_MIN_POST_GRASP_RADIUS_MM = 170.0


@dataclass(frozen=True)
class PickPlacePlan:
    """Cartesian waypoints in millimeters for the minimal pick/place flow."""

    pick_approach: Pose
    pick: Pose
    pick_lift: Pose
    place_transfer: Pose
    place_approach: Pose
    place_final: Pose
    place_retreat: Pose


def from_tuples(
    pick: tuple[float, float, float],
    place_approach: tuple[float, float, float],
    place_final: tuple[float, float, float],
    place_retreat: tuple[float, float, float],
    pick_approach: tuple[float, float, float] | None = None,
    pick_approach_clearance: float = DEFAULT_PICK_APPROACH_CLEARANCE_MM,
    pick_lift: tuple[float, float, float] | None = None,
    post_grasp_lift: float = DEFAULT_POST_GRASP_LIFT_MM,
    post_grasp_retract: float = DEFAULT_POST_GRASP_RETRACT_MM,
    min_post_grasp_radius: float = DEFAULT_MIN_POST_GRASP_RADIUS_MM,
    place_transfer: tuple[float, float, float] | None = None,
) -> PickPlacePlan:
    """Build a plan from tuple coordinates."""
    if pick_approach is None:
        pick_approach = (
            pick[0],
            pick[1],
            pick[2] + pick_approach_clearance,
        )
    if pick_lift is None:
        pick_lift = derive_post_grasp_pose(
            pick,
            post_grasp_lift=post_grasp_lift,
            post_grasp_retract=post_grasp_retract,
            min_post_grasp_radius=min_post_grasp_radius,
        )
    if place_transfer is None:
        place_transfer = (
            place_final[0],
            place_retreat[1],
            pick_lift[2],
        )
    return PickPlacePlan(
        pick_approach=Pose(*pick_approach),
        pick=Pose(*pick),
        pick_lift=Pose(*pick_lift),
        place_transfer=Pose(*place_transfer),
        place_approach=Pose(*place_approach),
        place_final=Pose(*place_final),
        place_retreat=Pose(*place_retreat),
    )


def derive_post_grasp_pose(
    pick: tuple[float, float, float],
    *,
    post_grasp_lift: float = DEFAULT_POST_GRASP_LIFT_MM,
    post_grasp_retract: float = DEFAULT_POST_GRASP_RETRACT_MM,
    min_post_grasp_radius: float = DEFAULT_MIN_POST_GRASP_RADIUS_MM,
) -> tuple[float, float, float]:
    """Return the post-grasp extract pose: retract toward origin while lifting."""
    x, y, z = pick
    radius = math.hypot(x, y)
    if radius > min_post_grasp_radius and post_grasp_retract > 0.0:
        target_radius = max(radius - post_grasp_retract, min_post_grasp_radius)
        if target_radius < radius:
            scale = target_radius / radius
            x = x * scale
            y = y * scale
    return (x, y, z + post_grasp_lift)
