"""MuJoCo workspace and inverse-kinematics helper for a KM1-like arm.

This is a planning/analysis tool, not a calibrated digital twin yet.
All command-line target inputs and CSV outputs are in millimeters so the results
can be compared directly with the existing main control program.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Iterable

import mujoco
import numpy as np


ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = ROOT / "km1_arm.xml"
DEFAULT_OUT = ROOT / "workspace_samples.csv"
JOINT_NAMES = [
    "base_yaw",
    "shoulder_pitch",
    "elbow_pitch",
    "wrist_pitch",
    "wrist_roll",
]


def load_model(path: Path) -> tuple[mujoco.MjModel, mujoco.MjData, int]:
    model = mujoco.MjModel.from_xml_path(str(path))
    data = mujoco.MjData(model)
    site_id = model.site("ee_site").id
    return model, data, site_id


def joint_ranges(model: mujoco.MjModel) -> np.ndarray:
    ranges = []
    for name in JOINT_NAMES:
        joint_id = model.joint(name).id
        ranges.append(model.jnt_range[joint_id])
    return np.asarray(ranges, dtype=float)


def set_qpos(model: mujoco.MjModel, data: mujoco.MjData, q: np.ndarray) -> None:
    data.qpos[: len(JOINT_NAMES)] = q
    mujoco.mj_forward(model, data)


def ee_position_mm(data: mujoco.MjData, site_id: int) -> np.ndarray:
    return np.asarray(data.site_xpos[site_id], dtype=float) * 1000.0


def site_x_axis(data: mujoco.MjData, site_id: int) -> np.ndarray:
    rotation = np.asarray(data.site_xmat[site_id], dtype=float).reshape(3, 3)
    return rotation[:, 0]


def horizontal_radial_axis(target_mm: np.ndarray) -> np.ndarray:
    axis = np.array([target_mm[0], target_mm[1], 0.0], dtype=float)
    norm = np.linalg.norm(axis)
    if norm < 1e-9:
        return np.array([0.0, 1.0, 0.0], dtype=float)
    return axis / norm


def write_workspace_csv(
    rows: Iterable[tuple[np.ndarray, np.ndarray]],
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "x_mm",
                "y_mm",
                "z_mm",
                "base_yaw_deg",
                "shoulder_pitch_deg",
                "elbow_pitch_deg",
                "wrist_pitch_deg",
                "wrist_roll_deg",
            ]
        )
        for pos_mm, q_rad in rows:
            writer.writerow([*pos_mm.tolist(), *np.rad2deg(q_rad).tolist()])


def sample_workspace(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    site_id: int,
    sample_count: int,
    seed: int,
    output: Path,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    ranges = joint_ranges(model)
    low = ranges[:, 0]
    high = ranges[:, 1]

    rows: list[tuple[np.ndarray, np.ndarray]] = []
    positions = np.zeros((sample_count, 3), dtype=float)
    for idx in range(sample_count):
        q = rng.uniform(low, high)
        set_qpos(model, data, q)
        pos = ee_position_mm(data, site_id)
        positions[idx] = pos
        rows.append((pos, q.copy()))

    write_workspace_csv(rows, output)
    return positions


def print_position_bounds(label: str, positions: np.ndarray) -> None:
    mins = positions.min(axis=0)
    maxs = positions.max(axis=0)
    radial_xy = np.linalg.norm(positions[:, :2], axis=1)
    print(f"  {label}:")
    print(f"    count: {len(positions)}")
    print(f"    x range: {mins[0]:8.1f} .. {maxs[0]:8.1f}")
    print(f"    y range: {mins[1]:8.1f} .. {maxs[1]:8.1f}")
    print(f"    z range: {mins[2]:8.1f} .. {maxs[2]:8.1f}")
    print(f"    horizontal radius: {radial_xy.min():.1f} .. {radial_xy.max():.1f}")


def print_workspace_summary(positions: np.ndarray, min_safe_z_mm: float = 0.0) -> None:
    mins = positions.min(axis=0)
    maxs = positions.max(axis=0)
    center = positions.mean(axis=0)
    radial_xy = np.linalg.norm(positions[:, :2], axis=1)
    forward = positions[positions[:, 1] > 0]
    safe_forward = positions[(positions[:, 1] > 0) & (positions[:, 2] >= min_safe_z_mm)]

    print("Workspace summary, all units mm")
    print(f"  samples: {len(positions)}")
    print(f"  x range: {mins[0]:8.1f} .. {maxs[0]:8.1f}")
    print(f"  y range: {mins[1]:8.1f} .. {maxs[1]:8.1f}")
    print(f"  z range: {mins[2]:8.1f} .. {maxs[2]:8.1f}")
    print(f"  mean xyz: {center[0]:8.1f}, {center[1]:8.1f}, {center[2]:8.1f}")
    print(f"  horizontal radius: {radial_xy.min():.1f} .. {radial_xy.max():.1f}")
    if len(forward):
        print_position_bounds("forward half-space, y > 0", forward)
    if len(safe_forward):
        print_position_bounds(f"safe forward region, y > 0 and z >= {min_safe_z_mm:.1f}", safe_forward)


def clamp_to_joint_limits(model: mujoco.MjModel, q: np.ndarray) -> np.ndarray:
    ranges = joint_ranges(model)
    return np.clip(q, ranges[:, 0], ranges[:, 1])


def solve_ik_position(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    site_id: int,
    target_mm: np.ndarray,
    max_iters: int = 250,
    tolerance_mm: float = 3.0,
    damping: float = 1e-3,
) -> tuple[bool, np.ndarray, np.ndarray, float]:
    target_m = target_mm / 1000.0
    q = data.qpos[: len(JOINT_NAMES)].copy()
    jacp = np.zeros((3, model.nv))
    jacr = np.zeros((3, model.nv))

    for _ in range(max_iters):
        set_qpos(model, data, q)
        current = np.asarray(data.site_xpos[site_id], dtype=float)
        error = target_m - current
        error_mm = float(np.linalg.norm(error) * 1000.0)
        if error_mm <= tolerance_mm:
            return True, q.copy(), current * 1000.0, error_mm

        mujoco.mj_jacSite(model, data, jacp, jacr, site_id)
        jac = jacp[:, : len(JOINT_NAMES)]
        lhs = jac @ jac.T + damping * np.eye(3)
        dq = jac.T @ np.linalg.solve(lhs, error)
        step_limit = math.radians(4.0)
        dq = np.clip(dq, -step_limit, step_limit)
        q = clamp_to_joint_limits(model, q + dq)

    set_qpos(model, data, q)
    final = ee_position_mm(data, site_id)
    return False, q.copy(), final, float(np.linalg.norm(target_mm - final))


def solve_ik_position_with_axis(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    site_id: int,
    target_mm: np.ndarray,
    desired_x_axis: np.ndarray,
    max_iters: int = 350,
    tolerance_mm: float = 4.0,
    axis_tolerance: float = 0.04,
    position_weight: float = 1.0,
    axis_weight: float = 0.02,
    damping: float = 1e-3,
) -> tuple[bool, np.ndarray, np.ndarray, float, float]:
    target_m = target_mm / 1000.0
    desired_x_axis = desired_x_axis / max(np.linalg.norm(desired_x_axis), 1e-9)
    q = data.qpos[: len(JOINT_NAMES)].copy()
    jacp = np.zeros((3, model.nv))
    jacr = np.zeros((3, model.nv))

    for _ in range(max_iters):
        set_qpos(model, data, q)
        current = np.asarray(data.site_xpos[site_id], dtype=float)
        current_axis = site_x_axis(data, site_id)
        pos_error = target_m - current
        axis_error = np.cross(current_axis, desired_x_axis)
        error_mm = float(np.linalg.norm(pos_error) * 1000.0)
        axis_error_norm = float(np.linalg.norm(axis_error))
        if error_mm <= tolerance_mm and axis_error_norm <= axis_tolerance:
            return True, q.copy(), current * 1000.0, error_mm, axis_error_norm

        mujoco.mj_jacSite(model, data, jacp, jacr, site_id)
        jac = np.vstack(
            (
                position_weight * jacp[:, : len(JOINT_NAMES)],
                axis_weight * jacr[:, : len(JOINT_NAMES)],
            )
        )
        error = np.concatenate((position_weight * pos_error, axis_weight * axis_error))
        lhs = jac @ jac.T + damping * np.eye(6)
        dq = jac.T @ np.linalg.solve(lhs, error)
        step_limit = math.radians(3.0)
        dq = np.clip(dq, -step_limit, step_limit)
        q = clamp_to_joint_limits(model, q + dq)

    set_qpos(model, data, q)
    final = ee_position_mm(data, site_id)
    final_axis_error = float(np.linalg.norm(np.cross(site_x_axis(data, site_id), desired_x_axis)))
    return False, q.copy(), final, float(np.linalg.norm(target_mm - final)), final_axis_error


def run_ik_grid(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    site_id: int,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    z_range: tuple[float, float],
    step_mm: float,
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    success = 0
    with output.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "target_x_mm",
                "target_y_mm",
                "target_z_mm",
                "success",
                "actual_x_mm",
                "actual_y_mm",
                "actual_z_mm",
                "error_mm",
                "base_yaw_deg",
                "shoulder_pitch_deg",
                "elbow_pitch_deg",
                "wrist_pitch_deg",
                "wrist_roll_deg",
            ]
        )
        for x in np.arange(x_range[0], x_range[1] + 1e-9, step_mm):
            for y in np.arange(y_range[0], y_range[1] + 1e-9, step_mm):
                for z in np.arange(z_range[0], z_range[1] + 1e-9, step_mm):
                    ok, q, actual, error = solve_ik_position(
                        model, data, site_id, np.array([x, y, z], dtype=float)
                    )
                    total += 1
                    success += int(ok)
                    writer.writerow(
                        [
                            x,
                            y,
                            z,
                            int(ok),
                            *actual.tolist(),
                            error,
                            *np.rad2deg(q).tolist(),
                        ]
                    )
    print(f"IK grid success: {success}/{total} ({success / max(total, 1):.1%})")
    print(f"Wrote grid result: {output}")


def show_viewer(model: mujoco.MjModel, data: mujoco.MjData, site_id: int, target: np.ndarray | None) -> None:
    import mujoco.viewer

    if target is not None:
        ok, q, actual, error = solve_ik_position(model, data, site_id, target)
        set_qpos(model, data, q)
        print(f"IK target={target.tolist()} success={ok} actual={actual.round(1).tolist()} error={error:.1f} mm")

    with mujoco.viewer.launch_passive(model, data) as viewer:
        print("Viewer open. Close the window to exit.")
        while viewer.is_running():
            mujoco.mj_step(model, data)
            viewer.sync()


def parse_range(text: str) -> tuple[float, float]:
    left, right = text.split(":", 1)
    return float(left), float(right)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--samples", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=470)
    parser.add_argument("--workspace-csv", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--target-mm", nargs=3, type=float, metavar=("X", "Y", "Z"))
    parser.add_argument("--viewer", action="store_true")
    parser.add_argument("--ik-grid", action="store_true")
    parser.add_argument("--grid-csv", type=Path, default=ROOT / "ik_grid.csv")
    parser.add_argument("--x-range", type=parse_range, default=parse_range("-220:220"))
    parser.add_argument("--y-range", type=parse_range, default=parse_range("120:460"))
    parser.add_argument("--z-range", type=parse_range, default=parse_range("20:520"))
    parser.add_argument("--grid-step-mm", type=float, default=40.0)
    parser.add_argument("--min-safe-z-mm", type=float, default=0.0)
    args = parser.parse_args()

    model, data, site_id = load_model(args.model)

    positions = sample_workspace(
        model,
        data,
        site_id,
        sample_count=args.samples,
        seed=args.seed,
        output=args.workspace_csv,
    )
    print_workspace_summary(positions, min_safe_z_mm=args.min_safe_z_mm)
    print(f"Wrote workspace samples: {args.workspace_csv}")

    target = np.asarray(args.target_mm, dtype=float) if args.target_mm else None
    if target is not None:
        ok, q, actual, error = solve_ik_position(model, data, site_id, target)
        print("Single target IK, all units mm/degrees")
        print(f"  target:  {target.round(1).tolist()}")
        print(f"  success: {ok}")
        print(f"  actual:  {actual.round(1).tolist()}")
        print(f"  error:   {error:.2f}")
        print(f"  joints:  {np.rad2deg(q).round(2).tolist()}")

    if args.ik_grid:
        run_ik_grid(
            model,
            data,
            site_id,
            x_range=args.x_range,
            y_range=args.y_range,
            z_range=args.z_range,
            step_mm=args.grid_step_mm,
            output=args.grid_csv,
        )

    if args.viewer:
        show_viewer(model, data, site_id, target)


if __name__ == "__main__":
    main()
