"""Interactive joint teaching viewer for the KM1-like MuJoCo arm.

On macOS, run this script with mjpython:

    mjpython sim/km1_joint_teach_viewer.py

Keyboard controls:
  1-5      select joint (base_yaw / shoulder_pitch / elbow_pitch / wrist_pitch / wrist_roll)
  ← or ,   selected joint  -1 deg
  → or .   selected joint  +1 deg
  ↓ or [   selected joint  -5 deg
  ↑ or ]   selected joint  +5 deg
  P        print current joint angles and end-effector pose
  S        append current pose to the teaching CSV
  R        reset arm controls to zero
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import math
from pathlib import Path
import platform
import time

import mujoco
import mujoco.viewer
import numpy as np

from km1_workspace_sim import DEFAULT_MODEL, JOINT_NAMES, ee_position_mm, load_model, site_x_axis


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "joint_teach_poses.csv"
SAVE_FIELDS = [
    "timestamp",
    "base_yaw_deg",
    "shoulder_pitch_deg",
    "elbow_pitch_deg",
    "wrist_pitch_deg",
    "wrist_roll_deg",
    "ee_x_mm",
    "ee_y_mm",
    "ee_z_mm",
    "ee_axis_x",
    "ee_axis_y",
    "ee_axis_z",
]

# GLFW key codes for arrow keys (MuJoCo passive viewer passes raw GLFW codes)
_GLFW_KEY_RIGHT = 262
_GLFW_KEY_LEFT  = 263
_GLFW_KEY_DOWN  = 264
_GLFW_KEY_UP    = 265

STEP_FINE   = 1.0   # degrees per fine keypress
STEP_COARSE = 5.0   # degrees per coarse keypress


def configure_control_sliders(model: mujoco.MjModel, data: mujoco.MjData) -> None:
    for actuator_idx in range(model.nu):
        joint_id = int(model.actuator_trnid[actuator_idx, 0])
        if joint_id < 0:
            continue
        model.actuator_ctrllimited[actuator_idx] = 1
        model.actuator_ctrlrange[actuator_idx] = model.jnt_range[joint_id]
        qpos_addr = int(model.jnt_qposadr[joint_id])
        data.ctrl[actuator_idx] = data.qpos[qpos_addr]


def arm_qpos(model: mujoco.MjModel, data: mujoco.MjData) -> np.ndarray:
    values = []
    for name in JOINT_NAMES:
        joint_id = model.joint(name).id
        values.append(data.qpos[model.jnt_qposadr[joint_id]])
    return np.asarray(values, dtype=float)


def current_row(model: mujoco.MjModel, data: mujoco.MjData, site_id: int) -> dict[str, float | str]:
    q_deg = np.rad2deg(arm_qpos(model, data))
    ee = ee_position_mm(data, site_id)
    axis = site_x_axis(data, site_id)
    row: dict[str, float | str] = {"timestamp": datetime.now().isoformat(timespec="seconds")}
    for name, value in zip(JOINT_NAMES, q_deg):
        row[f"{name}_deg"] = round(float(value), 3)
    row["ee_x_mm"] = round(float(ee[0]), 3)
    row["ee_y_mm"] = round(float(ee[1]), 3)
    row["ee_z_mm"] = round(float(ee[2]), 3)
    row["ee_axis_x"] = round(float(axis[0]), 5)
    row["ee_axis_y"] = round(float(axis[1]), 5)
    row["ee_axis_z"] = round(float(axis[2]), 5)
    return row


def print_pose(model: mujoco.MjModel, data: mujoco.MjData, site_id: int) -> None:
    row = current_row(model, data, site_id)
    q_text = ", ".join(f"{name}={row[f'{name}_deg']}" for name in JOINT_NAMES)
    ee_text = f"ee=({row['ee_x_mm']}, {row['ee_y_mm']}, {row['ee_z_mm']}) mm"
    axis_text = f"axis=({row['ee_axis_x']}, {row['ee_axis_y']}, {row['ee_axis_z']})"
    print(f"{q_text} | {ee_text} | {axis_text}", flush=True)


def append_pose(output: Path, model: mujoco.MjModel, data: mujoco.MjData, site_id: int) -> None:
    row = current_row(model, data, site_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not output.exists() or output.stat().st_size == 0
    with output.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAVE_FIELDS)
        if needs_header:
            writer.writeheader()
        writer.writerow(row)
    print(f"saved pose -> {output}", flush=True)
    print_pose(model, data, site_id)


def reset_controls(model: mujoco.MjModel, data: mujoco.MjData) -> None:
    for actuator_idx in range(model.nu):
        data.ctrl[actuator_idx] = 0.0
    print("reset controls to zero", flush=True)


def adjust_joint(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    site_id: int,
    actuator_idx: int,
    delta_deg: float,
) -> None:
    delta_rad = math.radians(delta_deg)
    lo, hi = model.actuator_ctrlrange[actuator_idx]
    new_val = float(np.clip(data.ctrl[actuator_idx] + delta_rad, lo, hi))
    data.ctrl[actuator_idx] = new_val
    current_deg = math.degrees(new_val)
    joint_name = JOINT_NAMES[actuator_idx]
    ee = ee_position_mm(data, site_id)
    print(
        f"  {joint_name} = {current_deg:+.1f} deg"
        f"  |  ee=({ee[0]:.1f}, {ee[1]:.1f}, {ee[2]:.1f}) mm",
        flush=True,
    )


def print_help() -> None:
    print("Joint teaching viewer — keyboard controls:", flush=True)
    print("  1-5   select joint  (base_yaw=1  shoulder=2  elbow=3  wrist_pitch=4  wrist_roll=5)", flush=True)
    print("  ← or ,   -1 deg      → or .   +1 deg", flush=True)
    print("  ↓ or [   -5 deg      ↑ or ]   +5 deg", flush=True)
    print("  P  print pose    S  save pose    R  reset all to zero", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    model, data, site_id = load_model(args.model)
    configure_control_sliders(model, data)
    mujoco.mj_forward(model, data)

    print_help()
    print(f"Save file: {args.output}", flush=True)

    # mutable state shared with the key callback closure
    state = {"selected": 0}

    def on_key(key: int) -> None:
        # safely convert key to character (only for printable ASCII range)
        if 32 <= key <= 126:  # printable ASCII range
            char = chr(key).lower()
        else:
            char = None

        sel = state["selected"]

        # joint selection (1-5)
        if char and char in "12345":
            state["selected"] = int(char) - 1
            print(f"  >> joint {char}: {JOINT_NAMES[state['selected']]}", flush=True)

        # fine adjustment (±1 deg)
        elif key == _GLFW_KEY_LEFT or char == ",":
            adjust_joint(model, data, site_id, sel, -STEP_FINE)
        elif key == _GLFW_KEY_RIGHT or char == ".":
            adjust_joint(model, data, site_id, sel, +STEP_FINE)

        # coarse adjustment (±5 deg)
        elif key == _GLFW_KEY_DOWN or char == "[":
            adjust_joint(model, data, site_id, sel, -STEP_COARSE)
        elif key == _GLFW_KEY_UP or char == "]":
            adjust_joint(model, data, site_id, sel, +STEP_COARSE)

        # pose operations
        elif char == "p":
            print_pose(model, data, site_id)
        elif char == "s":
            append_pose(args.output, model, data, site_id)
        elif char == "r":
            reset_controls(model, data)

    try:
        with mujoco.viewer.launch_passive(
            model,
            data,
            key_callback=on_key,
            show_left_ui=True,
            show_right_ui=True,
        ) as viewer:
            while viewer.is_running():
                mujoco.mj_step(model, data)
                viewer.sync()
                time.sleep(model.opt.timestep)
    except RuntimeError as exc:
        if platform.system() == "Darwin" and "mjpython" in str(exc):
            raise SystemExit(
                "MuJoCo viewer on macOS must be launched with mjpython.\n"
                "Run:\n"
                "  mjpython sim/km1_joint_teach_viewer.py\n"
            ) from exc
        raise


if __name__ == "__main__":
    main()
