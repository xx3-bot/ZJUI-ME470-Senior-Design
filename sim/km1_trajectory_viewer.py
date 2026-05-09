"""Visualize a KM1-like arm trajectory in MuJoCo.

Targets are supplied as CSV rows in millimeters:

    x_mm,y_mm,z_mm
    0,160,80
    0,180,120

The script checks each target with the selected project IK profile first, then
uses the MuJoCo numeric IK model to animate a smooth joint-space trajectory.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import platform
from pathlib import Path
import time

import mujoco
import mujoco.viewer
import numpy as np

from km1_workspace_sim import (
    DEFAULT_MODEL,
    JOINT_NAMES,
    ee_position_mm,
    horizontal_radial_axis,
    load_model,
    set_qpos,
    solve_ik_position,
    solve_ik_position_with_axis,
)
from vendor_km1_kinematics import ERROR_MEANINGS, PROFILES, parse_alpha_range, solve_pose


ROOT = Path(__file__).resolve().parent
DEFAULT_TRAJECTORY = ROOT / "examples" / "sample_trajectory.csv"
LOW_SHELF_TOP_Z_M = 0.040
RETURN_BOOK_SPINE_TO_COVER_CENTER_M = np.array([0.070, 0.0, 0.0], dtype=float)
RETURN_BOOK_PAGES_OFFSET_M = np.array([0.004, 0.0, 0.0], dtype=float)
BOOK_GEOMS_LOCAL = (
    (np.array([0.003, 0.000, 0.000], dtype=float), np.array([0.006, 0.005, 0.100], dtype=float)),
    (np.array([0.070, 0.000, 0.000], dtype=float), np.array([0.070, 0.005, 0.100], dtype=float)),
    (np.array([0.074, 0.001, 0.000], dtype=float), np.array([0.060, 0.004, 0.092], dtype=float)),
)
_GLFW_KEY_RIGHT = 262
_GLFW_KEY_LEFT = 263
_GLFW_KEY_DOWN = 264
_GLFW_KEY_UP = 265
_GLFW_KEY_SPACE = 32
JOINT_STEP_FINE_DEG = 1.0
JOINT_STEP_COARSE_DEG = 5.0
WRIST_ROLL_JOINT_INDEX = 4
CENTER_UP_Q_DEG = np.array([0.0, -90.0, 0.0, 0.0, 0.0], dtype=float)
# Viewer startup pose only. Keep MuJoCo's internal geometry unchanged, but start
# playback from the same visually straight/upright pose used after the final
# retreat so simulation and hardware tests are easier to compare.
OBSERVED_Z_START_Q_DEG = CENTER_UP_Q_DEG.copy()
PREFERRED_PICK_SEED_DEG = [28.88, -53.57, 97.98, -46.52, 0.0]


@dataclass(frozen=True)
class Waypoint:
    target: np.ndarray
    held_book_visible: bool = True
    return_book_visible: bool = False
    placed_book_visible: bool = False
    horizontal_end_link: bool | None = None
    base_only_from_previous: bool = False


def parse_bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_optional_bool(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    return parse_bool(value, False)


def read_targets(path: Path) -> list[Waypoint]:
    waypoints: list[Waypoint] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            waypoints.append(
                Waypoint(
                    target=np.array(
                    [
                        float(row["x_mm"]),
                        float(row["y_mm"]),
                        float(row["z_mm"]),
                    ],
                    dtype=float,
                    ),
                    held_book_visible=parse_bool(row.get("held_book_visible"), True),
                    return_book_visible=parse_bool(row.get("return_book_visible"), False),
                    placed_book_visible=parse_bool(row.get("placed_book_visible"), False),
                    horizontal_end_link=parse_optional_bool(row.get("horizontal_end_link")),
                    base_only_from_previous=parse_bool(row.get("base_only_from_previous"), False),
                ),
            )
    return waypoints


def interpolate(q0: np.ndarray, q1: np.ndarray, steps: int) -> list[np.ndarray]:
    if steps <= 1:
        return [q1.copy()]
    points = []
    for idx in range(steps):
        blend = idx / float(steps - 1)
        smooth = blend * blend * (3.0 - 2.0 * blend)
        points.append((1.0 - smooth) * q0 + smooth * q1)
    return points


def build_animation_frames(
    q_waypoints: list[np.ndarray],
    waypoints: list[Waypoint],
    steps_per_segment: int,
    initial_q: np.ndarray | None = None,
    final_q: np.ndarray | None = None,
    hold_steps: int = 12,
) -> list[tuple[np.ndarray, bool, bool, bool]]:
    """Build animation frames, keeping state-change holds short at repeated poses."""
    if not q_waypoints:
        return []

    frames: list[tuple[np.ndarray, bool, bool, bool]] = []
    current = q_waypoints[0].copy() if initial_q is None else initial_q.copy()
    for idx, (q_waypoint, waypoint) in enumerate(zip(q_waypoints, waypoints)):
        same_pose = np.allclose(current, q_waypoint, atol=1e-8)
        if same_pose:
            segment = [q_waypoint.copy() for _ in range(max(1, hold_steps))]
        else:
            segment = interpolate(current, q_waypoint, steps_per_segment)
        frames.extend(
            (
                q,
                waypoint.held_book_visible,
                waypoint.return_book_visible,
                waypoint.placed_book_visible,
            )
            for q in segment
        )
        current = q_waypoint.copy()
    if final_q is not None:
        if waypoints:
            last_waypoint = waypoints[-1]
            segment = interpolate(current, final_q, steps_per_segment)
            frames.extend(
                (
                    q,
                    last_waypoint.held_book_visible,
                    last_waypoint.return_book_visible,
                    last_waypoint.placed_book_visible,
                )
                for q in segment
            )
    return frames


def build_animation_segments(
    q_waypoints: list[np.ndarray],
    waypoints: list[Waypoint],
    steps_per_segment: int,
    initial_q: np.ndarray | None = None,
    final_q: np.ndarray | None = None,
    hold_steps: int = 12,
) -> list[list[tuple[np.ndarray, bool, bool, bool]]]:
    """Build one playable animation segment per trajectory step."""
    if not q_waypoints:
        return []

    segments: list[list[tuple[np.ndarray, bool, bool, bool]]] = []
    current = q_waypoints[0].copy() if initial_q is None else initial_q.copy()
    for q_waypoint, waypoint in zip(q_waypoints, waypoints):
        same_pose = np.allclose(current, q_waypoint, atol=1e-8)
        if same_pose:
            q_segment = [q_waypoint.copy() for _ in range(max(1, hold_steps))]
        else:
            q_segment = interpolate(current, q_waypoint, steps_per_segment)
        segments.append(
            [
                (
                    q,
                    waypoint.held_book_visible,
                    waypoint.return_book_visible,
                    waypoint.placed_book_visible,
                )
                for q in q_segment
            ]
        )
        current = q_waypoint.copy()

    if final_q is not None and waypoints:
        last_waypoint = waypoints[-1]
        segments.append(
            [
                (
                    q,
                    last_waypoint.held_book_visible,
                    last_waypoint.return_book_visible,
                    last_waypoint.placed_book_visible,
                )
                for q in interpolate(current, final_q, steps_per_segment)
            ]
        )
    return segments


def configure_control_sliders(model: mujoco.MjModel, data: mujoco.MjData) -> None:
    """Expose joint position actuators in the MuJoCo right-side Control panel."""
    for actuator_idx in range(model.nu):
        joint_id = int(model.actuator_trnid[actuator_idx, 0])
        if joint_id < 0:
            continue
        model.actuator_ctrllimited[actuator_idx] = 1
        model.actuator_ctrlrange[actuator_idx] = model.jnt_range[joint_id]
        qpos_addr = int(model.jnt_qposadr[joint_id])
        data.ctrl[actuator_idx] = data.qpos[qpos_addr]


def sync_controls_to_arm_qpos(model: mujoco.MjModel, data: mujoco.MjData) -> None:
    """Set actuator targets to the current arm pose before handing control to sliders."""
    for actuator_idx in range(min(model.nu, len(JOINT_NAMES))):
        joint_id = int(model.actuator_trnid[actuator_idx, 0])
        if joint_id < 0:
            continue
        qpos_addr = int(model.jnt_qposadr[joint_id])
        data.ctrl[actuator_idx] = data.qpos[qpos_addr]


def straighten_wrist_roll(q: np.ndarray) -> np.ndarray:
    """Return a copy with wrist roll straightened for stable book orientation."""
    q_straight = q.copy()
    if len(q_straight) > WRIST_ROLL_JOINT_INDEX:
        q_straight[WRIST_ROLL_JOINT_INDEX] = 0.0
    return q_straight


def apply_controls_to_arm_qpos(model: mujoco.MjModel, data: mujoco.MjData) -> None:
    """Apply slider/key targets directly to arm qpos for stable manual teaching."""
    for actuator_idx in range(min(model.nu, len(JOINT_NAMES))):
        joint_id = int(model.actuator_trnid[actuator_idx, 0])
        if joint_id < 0:
            continue
        qpos_addr = int(model.jnt_qposadr[joint_id])
        lo, hi = model.jnt_range[joint_id]
        data.qpos[qpos_addr] = float(np.clip(data.ctrl[actuator_idx], lo, hi))
    mujoco.mj_forward(model, data)


def print_joint_control_help() -> None:
    print("Manual joint controls after stop:", flush=True)
    print("  0-4 select arm joint: 0=base 1=shoulder 2=elbow 3=wrist_pitch 4=wrist_roll", flush=True)
    print("  5 is reserved for gripper; the current MuJoCo XML has no gripper actuator yet", flush=True)
    print("  Left/Right adjust selected joint by -/+1 deg", flush=True)
    print("  Down/Up adjust selected joint by -/+5 deg", flush=True)


def adjust_selected_joint(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    site_id: int,
    actuator_idx: int | None,
    delta_deg: float,
) -> None:
    if actuator_idx is None:
        print("  selected control has no actuator in the current model", flush=True)
        return
    if actuator_idx < 0 or actuator_idx >= min(model.nu, len(JOINT_NAMES)):
        print("  selected joint is outside the current model actuator range", flush=True)
        return

    delta_rad = np.deg2rad(delta_deg)
    lo, hi = model.actuator_ctrlrange[actuator_idx]
    data.ctrl[actuator_idx] = float(np.clip(data.ctrl[actuator_idx] + delta_rad, lo, hi))
    apply_controls_to_arm_qpos(model, data)
    ee = ee_position_mm(data, site_id)
    print(
        f"  {JOINT_NAMES[actuator_idx]} = {np.rad2deg(data.ctrl[actuator_idx]):+.1f} deg"
        f" | ee=({ee[0]:.1f}, {ee[1]:.1f}, {ee[2]:.1f}) mm",
        flush=True,
    )


def matrix_to_quat_wxyz(rotation: np.ndarray) -> np.ndarray:
    trace = float(np.trace(rotation))
    if trace > 0.0:
        scale = np.sqrt(trace + 1.0) * 2.0
        return np.array(
            [
                0.25 * scale,
                (rotation[2, 1] - rotation[1, 2]) / scale,
                (rotation[0, 2] - rotation[2, 0]) / scale,
                (rotation[1, 0] - rotation[0, 1]) / scale,
            ],
            dtype=float,
        )

    axis = int(np.argmax(np.diag(rotation)))
    if axis == 0:
        scale = np.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]) * 2.0
        quat = np.array(
            [
                (rotation[2, 1] - rotation[1, 2]) / scale,
                0.25 * scale,
                (rotation[0, 1] + rotation[1, 0]) / scale,
                (rotation[0, 2] + rotation[2, 0]) / scale,
            ],
            dtype=float,
        )
    elif axis == 1:
        scale = np.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]) * 2.0
        quat = np.array(
            [
                (rotation[0, 2] - rotation[2, 0]) / scale,
                (rotation[0, 1] + rotation[1, 0]) / scale,
                0.25 * scale,
                (rotation[1, 2] + rotation[2, 1]) / scale,
            ],
            dtype=float,
        )
    else:
        scale = np.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]) * 2.0
        quat = np.array(
            [
                (rotation[1, 0] - rotation[0, 1]) / scale,
                (rotation[0, 2] + rotation[2, 0]) / scale,
                (rotation[1, 2] + rotation[2, 1]) / scale,
                0.25 * scale,
            ],
            dtype=float,
        )
    return quat / np.linalg.norm(quat)


def local_book_corners() -> np.ndarray:
    corners: list[np.ndarray] = []
    for center, size in BOOK_GEOMS_LOCAL:
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                for sz in (-1.0, 1.0):
                    corners.append(center + size * np.array([sx, sy, sz], dtype=float))
    return np.asarray(corners, dtype=float)


def placed_book_pose_from_release(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    site_id: int,
    q_release: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    set_qpos(model, data, q_release)
    position = np.asarray(data.site_xpos[site_id], dtype=float).copy()
    rotation = np.asarray(data.site_xmat[site_id], dtype=float).reshape(3, 3).copy()
    corners_world = position + local_book_corners() @ rotation.T
    position[2] += LOW_SHELF_TOP_Z_M - float(corners_world[:, 2].min())
    return position, matrix_to_quat_wxyz(rotation)


def find_placed_book_pose(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    site_id: int,
    waypoints: list[Waypoint],
    q_waypoints: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    for waypoint, q in zip(waypoints, q_waypoints):
        if waypoint.placed_book_visible:
            return placed_book_pose_from_release(model, data, site_id, q)
    return placed_book_pose_from_release(model, data, site_id, q_waypoints[-1])


def find_return_book_grasp_position(waypoints: list[Waypoint]) -> np.ndarray:
    grasp_target = waypoints[0].target
    for waypoint in waypoints:
        if waypoint.return_book_visible:
            grasp_target = waypoint.target
    return grasp_target / 1000.0


def solve_mujoco_waypoints(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    site_id: int,
    waypoints: list[Waypoint],
    horizontal_end_link: bool,
    strict_ik: bool,
) -> list[np.ndarray]:
    q_waypoints: list[np.ndarray] = []
    seed_angles_deg = [
        [90, 0, 0, 0, 0],
        [90, -45, 20, 80, 0],
        [90, -60, 15, 110, 0],
        [90, -75, 35, 90, 0],
        [70, -55, 20, 100, 0],
        [110, -55, 20, 100, 0],
        [90, 20, 20, -40, 0],
    ]
    previous_target: np.ndarray | None = None
    previous_q: np.ndarray | None = None
    for waypoint in waypoints:
        target = waypoint.target
        if previous_target is not None and np.allclose(target, previous_target, atol=1e-6):
            assert previous_q is not None
            print(
                "MuJoCo IK "
                f"target={target.round(1).tolist()} reused previous joint solution"
            )
            q_waypoints.append(previous_q.copy())
            set_qpos(model, data, previous_q)
            continue

        best = None
        active_horizontal_end_link = (
            horizontal_end_link
            if waypoint.horizontal_end_link is None
            else waypoint.horizontal_end_link
        )
        seed_qs = []
        if previous_q is not None:
            seed_qs.append(previous_q.copy())
        if waypoint.return_book_visible:
            seed_qs.append(np.deg2rad(PREFERRED_PICK_SEED_DEG))
        seed_qs.extend(np.deg2rad(seed_deg) for seed_deg in seed_angles_deg)
        for seed_q in seed_qs:
            set_qpos(model, data, seed_q)
            if active_horizontal_end_link:
                ok, q, actual, error, axis_error = solve_ik_position_with_axis(
                    model,
                    data,
                    site_id,
                    target,
                    horizontal_radial_axis(target),
                )
            else:
                ok, q, actual, error = solve_ik_position(model, data, site_id, target)
                axis_error = 0.0
            if best is None or (error + 50.0 * axis_error) < (best[3] + 50.0 * best[4]):
                best = (ok, q, actual, error, axis_error)
            if ok:
                break

        assert best is not None
        ok, q, actual, error, axis_error = best
        print(
            "MuJoCo IK "
            f"target={target.round(1).tolist()} ok={ok} "
            f"actual={actual.round(1).tolist()} error={error:.1f} mm "
            f"axis_error={axis_error:.3f}"
        )
        if not ok and strict_ik:
            raise RuntimeError(f"MuJoCo IK failed for target {target.tolist()}")
        if not ok:
            print(
                "[WARN] MuJoCo IK using nearest solution for visualization "
                f"target={target.round(1).tolist()} error={error:.1f} mm"
            )
        if waypoint.base_only_from_previous and previous_q is not None:
            q = q.copy()
            q[1:] = previous_q[1:]
            print(
                "MuJoCo IK "
                f"target={target.round(1).tolist()} using base-only transition; "
                "joint1-4 held from previous waypoint"
            )
        elif active_horizontal_end_link:
            q = straighten_wrist_roll(q)
        q_waypoints.append(q)
        set_qpos(model, data, q)
        previous_target = target.copy()
        previous_q = q.copy()
    return q_waypoints


def print_vendor_check(
    waypoints: list[Waypoint],
    profile_name: str,
    alpha_min: float | None,
    alpha_max: float | None,
) -> None:
    profile = PROFILES[profile_name]
    print(f"Vendor IK precheck profile={profile_name}")
    if alpha_min is not None or alpha_max is not None:
        print(f"  alpha constraint: {alpha_min}..{alpha_max} deg")
    for waypoint in waypoints:
        target = waypoint.target
        result = solve_pose(target[0], target[1], target[2], profile, alpha_min_deg=alpha_min, alpha_max_deg=alpha_max)
        status = "ok" if result.ok else f"fail:{result.error_code} {ERROR_MEANINGS[result.error_code]}"
        pwm = result.servo_pwm if result.servo_pwm is not None else ""
        print(f"  target={target.round(1).tolist()} -> {status} pwm={pwm}")


def set_book_visibility(
    model: mujoco.MjModel,
    held_visible: bool,
    return_visible: bool,
    placed_visible: bool,
) -> None:
    for name in ("held_book_spine", "held_book_cover", "held_book_pages"):
        model.geom(name).rgba[3] = 1.0 if held_visible else 0.0
    for name in ("return_book_cover", "return_book_pages"):
        model.geom(name).rgba[3] = 1.0 if return_visible else 0.0
    for name in ("placed_book_spine", "placed_book_cover", "placed_book_pages"):
        model.geom(name).rgba[3] = 1.0 if placed_visible else 0.0


def set_return_book_pose(model: mujoco.MjModel, grasp_position_m: np.ndarray) -> None:
    cover_position = grasp_position_m + RETURN_BOOK_SPINE_TO_COVER_CENTER_M
    model.geom("side_return_bin_hint").pos[:2] = grasp_position_m[:2]
    model.geom("return_book_cover").pos[:] = cover_position
    model.geom("return_book_pages").pos[:] = cover_position + RETURN_BOOK_PAGES_OFFSET_M


def set_placed_book_pose(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    position: np.ndarray,
    quat_wxyz: np.ndarray,
) -> None:
    qpos_addr = model.joint("placed_book_free").qposadr[0]
    data.qpos[qpos_addr : qpos_addr + 3] = position
    data.qpos[qpos_addr + 3 : qpos_addr + 7] = quat_wxyz


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    available_profiles = [name for name in sorted(PROFILES) if name != "esp32_factory"]
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--trajectory", type=Path, default=DEFAULT_TRAJECTORY)
    parser.add_argument("--profile", choices=available_profiles, default="measured_grasp")
    parser.add_argument("--alpha-range", help="Optional vendor IK gripper angle constraint, for example -45:-25.")
    parser.add_argument(
        "--free-end-link",
        action="store_true",
        help="Disable the default horizontal end-link orientation constraint in the MuJoCo viewer.",
    )
    parser.add_argument("--steps-per-segment", type=int, default=80)
    parser.add_argument("--fps", type=float, default=60.0)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument(
        "--start-from-model-default",
        action="store_true",
        help="Start playback from the MuJoCo XML default pose instead of the upright/center-up viewer start pose.",
    )
    parser.add_argument(
        "--strict-ik",
        action="store_true",
        help="Fail instead of using the nearest MuJoCo IK solution for unreachable visualization targets.",
    )
    args = parser.parse_args()

    waypoints = read_targets(args.trajectory)
    if not waypoints:
        raise RuntimeError(f"No targets found in {args.trajectory}")

    alpha_min, alpha_max = parse_alpha_range(args.alpha_range)
    print_vendor_check(waypoints, args.profile, alpha_min, alpha_max)
    model, data, site_id = load_model(args.model)
    configure_control_sliders(model, data)
    initial_q = (
        data.qpos[: len(JOINT_NAMES)].copy()
        if args.start_from_model_default
        else np.deg2rad(OBSERVED_Z_START_Q_DEG)
    )
    q_waypoints = solve_mujoco_waypoints(
        model,
        data,
        site_id,
        waypoints,
        not args.free_end_link,
        args.strict_ik,
    )
    placed_position, placed_quat = find_placed_book_pose(model, data, site_id, waypoints, q_waypoints)
    return_book_grasp_position = find_return_book_grasp_position(waypoints)

    segments = build_animation_segments(
        q_waypoints,
        waypoints,
        args.steps_per_segment,
        initial_q=initial_q,
        final_q=np.deg2rad(CENTER_UP_Q_DEG),
    )

    frame_period = 1.0 / args.fps
    print("Viewer opening. Close the window to exit.")
    if not args.loop:
        print("Press Space to run each trajectory step. After the final step, joint control sliders become active.")
        print_joint_control_help()

    state: dict[str, bool | int | None] = {
        "manual_control": False,
        "selected_actuator": 0,
        "advance_requested": False,
    }

    def on_key(key: int) -> None:
        if 32 <= key <= 126:
            char = chr(key).lower()
        else:
            char = None

        if key == _GLFW_KEY_SPACE and not state["manual_control"]:
            state["advance_requested"] = True
            return

        if char is not None and char in "012345":
            idx = int(char)
            if idx < min(model.nu, len(JOINT_NAMES)):
                state["selected_actuator"] = idx
                print(f"  selected {idx}: {JOINT_NAMES[idx]}", flush=True)
            else:
                state["selected_actuator"] = None
                print(f"  selected {idx}: reserved/no actuator in current model", flush=True)
            return

        if not state["manual_control"]:
            return

        selected = state["selected_actuator"]
        if key == _GLFW_KEY_LEFT:
            adjust_selected_joint(model, data, site_id, selected if isinstance(selected, int) else None, -JOINT_STEP_FINE_DEG)
        elif key == _GLFW_KEY_RIGHT:
            adjust_selected_joint(model, data, site_id, selected if isinstance(selected, int) else None, JOINT_STEP_FINE_DEG)
        elif key == _GLFW_KEY_DOWN:
            adjust_selected_joint(model, data, site_id, selected if isinstance(selected, int) else None, -JOINT_STEP_COARSE_DEG)
        elif key == _GLFW_KEY_UP:
            adjust_selected_joint(model, data, site_id, selected if isinstance(selected, int) else None, JOINT_STEP_COARSE_DEG)

    try:
        with mujoco.viewer.launch_passive(
            model,
            data,
            key_callback=on_key,
            show_left_ui=True,
            show_right_ui=True,
        ) as viewer:
            manual_control = False
            active_segment: list[tuple[np.ndarray, bool, bool, bool]] | None = None
            segment_idx = -1
            frame_idx = 0
            q = initial_q.copy()
            if waypoints:
                first_waypoint = waypoints[0]
                held_visible = first_waypoint.held_book_visible
                return_visible = first_waypoint.return_book_visible
                placed_visible = first_waypoint.placed_book_visible
            else:
                held_visible = False
                return_visible = True
                placed_visible = False
            set_book_visibility(model, held_visible, return_visible, placed_visible)
            set_return_book_pose(model, return_book_grasp_position)
            set_placed_book_pose(model, data, placed_position, placed_quat)
            set_qpos(model, data, q)
            while viewer.is_running():
                if manual_control:
                    set_book_visibility(model, held_visible, return_visible, placed_visible)
                    set_return_book_pose(model, return_book_grasp_position)
                    set_placed_book_pose(model, data, placed_position, placed_quat)
                    apply_controls_to_arm_qpos(model, data)
                    viewer.sync()
                    time.sleep(frame_period)
                    continue

                if active_segment is None:
                    if bool(state.get("advance_requested")):
                        state["advance_requested"] = False
                        segment_idx += 1
                        if segment_idx >= len(segments):
                            sync_controls_to_arm_qpos(model, data)
                            manual_control = True
                            state["manual_control"] = True
                            print("Trajectory stopped. Joint control sliders are active.", flush=True)
                            continue
                        active_segment = segments[segment_idx]
                        frame_idx = 0
                        print(f"Running trajectory step {segment_idx + 1}/{len(segments)}", flush=True)
                    viewer.sync()
                    time.sleep(frame_period)
                    continue

                q, held_visible, return_visible, placed_visible = active_segment[frame_idx]
                set_book_visibility(model, held_visible, return_visible, placed_visible)
                set_return_book_pose(model, return_book_grasp_position)
                set_placed_book_pose(model, data, placed_position, placed_quat)
                set_qpos(model, data, q)
                viewer.sync()
                time.sleep(frame_period)
                frame_idx += 1
                if frame_idx >= len(active_segment):
                    if args.loop:
                        active_segment = None
                        if segment_idx >= len(segments) - 1:
                            segment_idx = -1
                        print("Step complete. Press Space for next step.", flush=True)
                    else:
                        active_segment = None
                        if segment_idx >= len(segments) - 1:
                            sync_controls_to_arm_qpos(model, data)
                            manual_control = True
                            state["manual_control"] = True
                            print("Trajectory stopped. Joint control sliders are active.", flush=True)
                        else:
                            print("Step complete. Press Space for next step.", flush=True)
    except RuntimeError as exc:
        if platform.system() == "Darwin" and "mjpython" in str(exc):
            raise SystemExit(
                "MuJoCo viewer on macOS must be launched with mjpython.\n"
                "Run:\n"
                "  mjpython sim/km1_trajectory_viewer.py\n"
                "or:\n"
                "  mjpython sim/km1_trajectory_viewer.py --loop\n"
            ) from exc
        raise


if __name__ == "__main__":
    main()
