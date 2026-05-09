"""Build and optionally send a target-driven pick/place hardware sequence."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import math
from pathlib import Path
import subprocess
import sys
import termios
import tty


ROOT = Path(__file__).resolve().parent.parent
SIM_DIR = ROOT / "sim"
SIM_OUTPUT_DIR = ROOT / "sim_output"
DEFAULT_TRAJECTORY_PATH = SIM_OUTPUT_DIR / "control_trajectory.csv"
DEFAULT_COMMAND_PATH = SIM_OUTPUT_DIR / "hardware_command_sequence.txt"
DEFAULT_SUMMARY_PATH = SIM_OUTPUT_DIR / "TARGET_SEQUENCE_SUMMARY.md"
DEFAULT_SEND_SCRIPT = SIM_OUTPUT_DIR / "send_hardware_sequence.py"

PICK_APPROACH_CLEARANCE_MM = 100.0
POST_GRASP_LIFT_MM = 45.0
TRANSPORT_RETRACT_MM = 70.0
MIN_TRANSPORT_RADIUS_MM = 170.0
TRANSPORT_RETRACT_TRIGGER_RADIUS_MM = 240.0
DEFAULT_RETREAT_Y_MM = 220.0
DEFAULT_STEP_TIME_MS = 1500
BASE_ONLY_TIME_MS = 2500
DEFAULT_SMALL_MOVE_FAST_THRESHOLD_PWM = 20
DEFAULT_MEDIUM_MOVE_THRESHOLD_PWM = 120
DEFAULT_SMALL_MOVE_TIME_MS = 400
DEFAULT_MEDIUM_MOVE_TIME_MS = 800
DEFAULT_NORMAL_MOVE_TIME_MS = 1500
GRIPPER_CLOSE_COMMAND = "{#005P1700T1000!}"
GRIPPER_OPEN_COMMAND = "{#005P1400T1000!}"
HARDWARE_HOME_COMMAND = (
    "{#000P1500T1500!#001P2000T1500!#002P2000T1500!"
    "#003P0850T1500!#004P1500T1500!#005P1500T1500!}"
)

PWM_CENTER = 1500.0
PWM_PER_DEG = 1000.0 / 135.0
WRIST_ROLL_JOINT_INDEX = 4
PREFERRED_PICK_SEED_DEG = [28.88, -53.57, 97.98, -46.52, 0.0]


@dataclass(frozen=True)
class TargetSequenceResult:
    trajectory_path: Path
    command_path: Path
    summary_path: Path
    commands: list[str]
    command_metadata: list["CommandMetadata"]


@dataclass(frozen=True)
class TimingConfig:
    small_move_fast_threshold_pwm: int = DEFAULT_SMALL_MOVE_FAST_THRESHOLD_PWM
    medium_move_threshold_pwm: int = DEFAULT_MEDIUM_MOVE_THRESHOLD_PWM
    small_move_time_ms: int = DEFAULT_SMALL_MOVE_TIME_MS
    medium_move_time_ms: int = DEFAULT_MEDIUM_MOVE_TIME_MS
    normal_move_time_ms: int = DEFAULT_NORMAL_MOVE_TIME_MS

    def __post_init__(self) -> None:
        if self.small_move_fast_threshold_pwm < 0:
            raise ValueError("small_move_fast_threshold_pwm must be non-negative")
        if self.medium_move_threshold_pwm <= self.small_move_fast_threshold_pwm:
            raise ValueError("medium_move_threshold_pwm must be greater than small_move_fast_threshold_pwm")
        for name in ("small_move_time_ms", "medium_move_time_ms", "normal_move_time_ms"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class CommandMetadata:
    label: str
    command: str
    pwm: tuple[int, ...] | None = None
    deltas: tuple[int, ...] | None = None
    times_ms: tuple[int, ...] | None = None
    note: str = ""


@dataclass(frozen=True)
class TargetWaypoint:
    label: str
    x: float
    y: float
    z: float
    held_book_visible: bool
    return_book_visible: bool
    placed_book_visible: bool
    horizontal_end_link: bool = True
    base_only_from_previous: bool = False


def _validate_xyz(name: str, xyz: tuple[float, float, float]) -> None:
    if len(xyz) != 3:
        raise ValueError(f"{name} must have exactly 3 values")
    if any(value != value for value in xyz):
        raise ValueError(f"{name} contains NaN")
    if xyz[2] < 0:
        raise ValueError(f"{name}.z must be non-negative, got {xyz[2]}")


def build_target_waypoints(
    pick: tuple[float, float, float],
    place: tuple[float, float, float],
    retreat_y: float = DEFAULT_RETREAT_Y_MM,
) -> list[TargetWaypoint]:
    """Derive the generic pick/place waypoint policy from two target points."""
    _validate_xyz("pick", pick)
    _validate_xyz("place", place)

    pick_x, pick_y, pick_z = pick
    place_x, place_y, place_z = place
    approach_z = pick_z + PICK_APPROACH_CLEARANCE_MM
    transport_z = pick_z + POST_GRASP_LIFT_MM
    retract_x, retract_y = _retract_xy_toward_origin(pick_x, pick_y, TRANSPORT_RETRACT_MM)
    waypoints = [
        TargetWaypoint("pick_approach", pick_x, pick_y, approach_z, False, True, False),
        TargetWaypoint("pick", pick_x, pick_y, pick_z, False, True, False),
        TargetWaypoint("gripper_close_pose", pick_x, pick_y, pick_z, True, False, False),
        TargetWaypoint("pick_lift", pick_x, pick_y, transport_z, True, False, False),
    ]
    if (retract_x, retract_y) != (pick_x, pick_y):
        waypoints.append(TargetWaypoint("transport_retract", retract_x, retract_y, transport_z, True, False, False))
    waypoints.extend(
        [
        TargetWaypoint(
            "place_transfer_base_only",
            place_x,
            retreat_y,
            transport_z,
            True,
            False,
            False,
            base_only_from_previous=True,
        ),
        TargetWaypoint("place_approach", place_x, place_y, transport_z, True, False, False),
        TargetWaypoint("place_final", place_x, place_y, place_z, True, False, False),
        TargetWaypoint("gripper_open_pose", place_x, place_y, place_z, False, False, True),
        TargetWaypoint("place_retreat", place_x, retreat_y, transport_z, False, False, True),
        ]
    )
    return waypoints


def _retract_xy_toward_origin(x_mm: float, y_mm: float, distance_mm: float) -> tuple[float, float]:
    radius = math.hypot(x_mm, y_mm)
    if radius <= TRANSPORT_RETRACT_TRIGGER_RADIUS_MM or distance_mm <= 0.0:
        return x_mm, y_mm
    target_radius = max(radius - min(distance_mm, radius), MIN_TRANSPORT_RADIUS_MM)
    if target_radius >= radius:
        return x_mm, y_mm
    scale = target_radius / radius
    return x_mm * scale, y_mm * scale


def write_trajectory_csv(waypoints: list[TargetWaypoint], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "x_mm",
                "y_mm",
                "z_mm",
                "held_book_visible",
                "return_book_visible",
                "placed_book_visible",
                "horizontal_end_link",
                "base_only_from_previous",
            ]
        )
        for waypoint in waypoints:
            writer.writerow(
                [
                    waypoint.x,
                    waypoint.y,
                    waypoint.z,
                    int(waypoint.held_book_visible),
                    int(waypoint.return_book_visible),
                    int(waypoint.placed_book_visible),
                    int(waypoint.horizontal_end_link),
                    int(waypoint.base_only_from_previous),
                ]
            )


def _ensure_sim_import_path() -> None:
    sim_dir = str(SIM_DIR)
    if sim_dir not in sys.path:
        sys.path.insert(0, sim_dir)


def solve_waypoint_angles(trajectory_path: Path):
    """Use the MuJoCo IK solver without importing or opening the viewer."""
    _ensure_sim_import_path()
    try:
        import numpy as np

        from km1_workspace_sim import (
            DEFAULT_MODEL,
            horizontal_radial_axis,
            load_model,
            set_qpos,
            solve_ik_position,
            solve_ik_position_with_axis,
        )
    except ImportError as exc:
        raise SystemExit(
            "MuJoCo sequence generation dependencies are missing.\n"
            "Install them in the runtime environment before hardware execution: "
            "python3 -m pip install mujoco numpy"
        ) from exc

    waypoints = read_trajectory_csv(trajectory_path, np)
    if not waypoints:
        raise SystemExit(f"No trajectory waypoints found in {trajectory_path}")

    model, data, site_id = load_model(DEFAULT_MODEL)
    q_waypoints = solve_target_waypoints(
        model,
        data,
        site_id,
        waypoints,
        np,
        set_qpos,
        solve_ik_position,
        solve_ik_position_with_axis,
        horizontal_radial_axis,
    )
    return waypoints, q_waypoints, np


def _csv_bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def read_trajectory_csv(path: Path, np_module) -> list[TargetWaypoint]:
    del np_module
    waypoints: list[TargetWaypoint] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=1):
            waypoints.append(
                TargetWaypoint(
                    label=f"waypoint_{index:02d}",
                    x=float(row["x_mm"]),
                    y=float(row["y_mm"]),
                    z=float(row["z_mm"]),
                    held_book_visible=_csv_bool(row.get("held_book_visible"), True),
                    return_book_visible=_csv_bool(row.get("return_book_visible"), False),
                    placed_book_visible=_csv_bool(row.get("placed_book_visible"), False),
                    horizontal_end_link=_csv_bool(row.get("horizontal_end_link"), True),
                    base_only_from_previous=_csv_bool(row.get("base_only_from_previous"), False),
                )
            )
    return waypoints


def _waypoint_target(waypoint: TargetWaypoint, np_module):
    return np_module.array([waypoint.x, waypoint.y, waypoint.z], dtype=float)


def _straighten_wrist_roll(q, np_module):
    q_straight = q.copy()
    if len(q_straight) > WRIST_ROLL_JOINT_INDEX:
        q_straight[WRIST_ROLL_JOINT_INDEX] = 0.0
    return q_straight


def solve_target_waypoints(
    model,
    data,
    site_id: int,
    waypoints: list[TargetWaypoint],
    np_module,
    set_qpos,
    solve_ik_position,
    solve_ik_position_with_axis,
    horizontal_radial_axis,
):
    """Solve target waypoints using the same seed/base-only policy as the debug viewer."""
    q_waypoints = []
    seed_angles_deg = [
        [90, 0, 0, 0, 0],
        [90, -45, 20, 80, 0],
        [90, -60, 15, 110, 0],
        [90, -75, 35, 90, 0],
        [70, -55, 20, 100, 0],
        [110, -55, 20, 100, 0],
        [90, 20, 20, -40, 0],
    ]
    previous_target = None
    previous_q = None
    for waypoint in waypoints:
        target = _waypoint_target(waypoint, np_module)
        if previous_target is not None and np_module.allclose(target, previous_target, atol=1e-6):
            q_waypoints.append(previous_q.copy())
            set_qpos(model, data, previous_q)
            continue

        seed_qs = []
        if previous_q is not None:
            seed_qs.append(previous_q.copy())
        if waypoint.return_book_visible:
            seed_qs.append(np_module.deg2rad(PREFERRED_PICK_SEED_DEG))
        seed_qs.extend(np_module.deg2rad(seed_deg) for seed_deg in seed_angles_deg)

        best = None
        for seed_q in seed_qs:
            set_qpos(model, data, seed_q)
            if waypoint.horizontal_end_link:
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

        if best is None:
            raise RuntimeError(f"MuJoCo IK did not produce a candidate for {target.tolist()}")
        ok, q, actual, error, axis_error = best
        print(
            "MuJoCo IK "
            f"target={target.round(1).tolist()} ok={ok} "
            f"actual={actual.round(1).tolist()} error={error:.1f} mm "
            f"axis_error={axis_error:.3f}"
        )
        if not ok:
            raise RuntimeError(f"MuJoCo IK failed for target {target.tolist()}")
        if waypoint.base_only_from_previous and previous_q is not None:
            q = q.copy()
            q[1:] = previous_q[1:]
            print(
                "MuJoCo IK "
                f"target={target.round(1).tolist()} using base-only transition; "
                "joint1-4 held from previous waypoint"
            )
        elif waypoint.horizontal_end_link:
            q = _straighten_wrist_roll(q, np_module)

        q_waypoints.append(q)
        set_qpos(model, data, q)
        previous_target = target.copy()
        previous_q = q.copy()
    return q_waypoints


def pwm_from_mujoco_angles_deg(q_deg: list[float]) -> tuple[int, int, int, int, int]:
    """Convert MuJoCo displayed joint angles to calibrated raw PWM values."""
    base_yaw, shoulder, elbow, wrist_pitch, wrist_roll = q_deg
    pwm = (
        PWM_CENTER + base_yaw * PWM_PER_DEG,
        PWM_CENTER - (shoulder + 90.0) * PWM_PER_DEG,
        PWM_CENTER + elbow * PWM_PER_DEG,
        PWM_CENTER - wrist_pitch * PWM_PER_DEG,
        PWM_CENTER + wrist_roll * PWM_PER_DEG,
    )
    return tuple(int(round(value)) for value in pwm)


def arm_command_from_q(
    q_deg: list[float],
    time_ms: int = DEFAULT_STEP_TIME_MS,
    base_only: bool = False,
) -> str:
    pwm = pwm_from_mujoco_angles_deg(q_deg)
    if base_only:
        return f"{{#000P{pwm[0]:04d}T{time_ms:04d}!}}"
    return (
        "{"
        f"#000P{pwm[0]:04d}T{time_ms:04d}!"
        f"#001P{pwm[1]:04d}T{time_ms:04d}!"
        f"#002P{pwm[2]:04d}T{time_ms:04d}!"
        f"#003P{pwm[3]:04d}T{time_ms:04d}!"
        f"#004P{pwm[4]:04d}T{time_ms:04d}!"
        "}"
    )


def _time_for_delta(delta_pwm: int, timing: TimingConfig) -> int:
    if delta_pwm < timing.small_move_fast_threshold_pwm:
        return timing.small_move_time_ms
    if delta_pwm < timing.medium_move_threshold_pwm:
        return timing.medium_move_time_ms
    return timing.normal_move_time_ms


def _times_for_pwm_delta(
    pwm: tuple[int, int, int, int, int],
    previous_pwm: tuple[int, int, int, int, int] | None,
    timing: TimingConfig,
) -> tuple[int, int, int, int, int]:
    if previous_pwm is None:
        return (timing.normal_move_time_ms,) * 5
    return tuple(
        _time_for_delta(abs(current - previous), timing)
        for current, previous in zip(pwm, previous_pwm)
    )


def arm_command_from_pwm(
    pwm: tuple[int, int, int, int, int],
    times_ms: tuple[int, int, int, int, int],
) -> str:
    return (
        "{"
        f"#000P{pwm[0]:04d}T{times_ms[0]:04d}!"
        f"#001P{pwm[1]:04d}T{times_ms[1]:04d}!"
        f"#002P{pwm[2]:04d}T{times_ms[2]:04d}!"
        f"#003P{pwm[3]:04d}T{times_ms[3]:04d}!"
        f"#004P{pwm[4]:04d}T{times_ms[4]:04d}!"
        "}"
    )


def build_hardware_commands(
    waypoints,
    q_waypoints,
    np_module,
    timing: TimingConfig,
) -> tuple[list[str], list[CommandMetadata]]:
    """Build the verified raw ASCII sequence from solved MuJoCo poses."""
    q_deg = [np_module.rad2deg(q).tolist() for q in q_waypoints]
    pwm_by_waypoint = [pwm_from_mujoco_angles_deg(q) for q in q_deg]
    waypoint_index_by_label = {waypoint.label: index for index, waypoint in enumerate(waypoints)}

    commands: list[str] = []
    metadata: list[CommandMetadata] = []
    previous_arm_pwm: tuple[int, int, int, int, int] | None = None

    def add_arm_step(label: str) -> None:
        nonlocal previous_arm_pwm
        waypoint_index = waypoint_index_by_label[label]
        pwm = pwm_by_waypoint[waypoint_index]
        times = _times_for_pwm_delta(pwm, previous_arm_pwm, timing)
        deltas = (
            tuple(0 for _ in pwm)
            if previous_arm_pwm is None
            else tuple(abs(current - previous) for current, previous in zip(pwm, previous_arm_pwm))
        )
        command = arm_command_from_pwm(pwm, times)
        commands.append(command)
        metadata.append(
            CommandMetadata(
                label=label,
                command=command,
                pwm=pwm,
                deltas=deltas,
                times_ms=times,
                note="dynamic arm timing",
            )
        )
        previous_arm_pwm = pwm

    def add_gripper_step(label: str, command: str, note: str) -> None:
        commands.append(command)
        metadata.append(CommandMetadata(label=label, command=command, note=note))

    add_arm_step("pick_approach")
    add_arm_step("pick")
    add_gripper_step("gripper_close", GRIPPER_CLOSE_COMMAND, "fixed gripper close")
    add_arm_step("pick_lift")
    if "transport_retract" in waypoint_index_by_label:
        add_arm_step("transport_retract")

    place_transfer_index = waypoint_index_by_label["place_transfer_base_only"]
    base_pwm = pwm_by_waypoint[place_transfer_index][0]
    base_previous = previous_arm_pwm[0] if previous_arm_pwm is not None else base_pwm
    base_delta = abs(base_pwm - base_previous)
    base_command = f"{{#000P{base_pwm:04d}T{BASE_ONLY_TIME_MS:04d}!}}"
    commands.append(base_command)
    metadata.append(
        CommandMetadata(
            label="place_transfer_base_only",
            command=base_command,
            pwm=(base_pwm,),
            deltas=(base_delta,),
            times_ms=(BASE_ONLY_TIME_MS,),
            note="fixed base-only transfer; joint1-joint5 not re-commanded",
        )
    )
    previous_arm_pwm = pwm_by_waypoint[place_transfer_index]

    add_arm_step("place_approach")
    add_arm_step("place_final")
    add_gripper_step("gripper_open", GRIPPER_OPEN_COMMAND, "fixed safe release")
    add_arm_step("place_retreat")
    commands.append(HARDWARE_HOME_COMMAND)
    metadata.append(
        CommandMetadata(
            label="measured_hardware_home",
            command=HARDWARE_HOME_COMMAND,
            note="fixed measured home command",
        )
    )
    return commands, metadata


def build_fixed_hardware_commands(waypoints, q_waypoints, np_module) -> list[str]:
    """Build the historical fixed-time command sequence for comparison/debug."""
    q_deg = [np_module.rad2deg(q).tolist() for q in q_waypoints]
    commands = [
        arm_command_from_q(q_deg[0]),
        arm_command_from_q(q_deg[1]),
        GRIPPER_CLOSE_COMMAND,
        arm_command_from_q(q_deg[3]),
        arm_command_from_q(q_deg[4]),
        arm_command_from_q(q_deg[5], time_ms=BASE_ONLY_TIME_MS, base_only=True),
        arm_command_from_q(q_deg[6]),
        arm_command_from_q(q_deg[7]),
        GRIPPER_OPEN_COMMAND,
        arm_command_from_q(q_deg[9]),
        HARDWARE_HOME_COMMAND,
    ]
    return commands


def write_command_file(commands: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(commands) + "\n", encoding="ascii")


def write_summary(
    path: Path,
    pick: tuple[float, float, float],
    place: tuple[float, float, float],
    waypoints: list[TargetWaypoint],
    q_waypoints,
    commands: list[str],
    command_metadata: list[CommandMetadata],
    timing: TimingConfig,
    np_module,
) -> None:
    rows = []
    q_deg = [np_module.rad2deg(q).tolist() for q in q_waypoints]
    command_by_label = {
        "pick_approach": commands[0],
        "pick": commands[1],
        "gripper_close_pose": commands[2],
        "pick_lift": commands[3],
        "transport_retract": commands[4],
        "place_transfer_base_only": commands[5],
        "place_approach": commands[6],
        "place_final": commands[7],
        "gripper_open_pose": commands[8],
        "place_retreat": commands[9],
    }
    for index, waypoint in enumerate(waypoints, start=1):
        angles = ", ".join(f"{value:.3f}" for value in q_deg[index - 1])
        rows.append(
            "| "
            f"{index:02d} | {waypoint.label} | "
            f"({waypoint.x:.2f}, {waypoint.y:.2f}, {waypoint.z:.2f}) | "
            f"[{angles}] | `{command_by_label[waypoint.label]}` |"
        )

    content = [
        "# Target Sequence Summary",
        "",
        "Generated by `主程序代码/main.py --run-target-sequence`.",
        "",
        f"- pick xyz: `{pick}`",
        f"- place xyz: `{place}`",
        f"- pick approach clearance: `{PICK_APPROACH_CLEARANCE_MM} mm`",
        f"- post-grasp lift: `{POST_GRASP_LIFT_MM} mm`",
        f"- transport retract toward origin: `{TRANSPORT_RETRACT_MM} mm`",
        f"- base-only transfer time: `{BASE_ONLY_TIME_MS} ms`",
        (
            "- dynamic arm timing: "
            f"`delta < {timing.small_move_fast_threshold_pwm} PWM -> {timing.small_move_time_ms} ms`, "
            f"`delta < {timing.medium_move_threshold_pwm} PWM -> {timing.medium_move_time_ms} ms`, "
            f"otherwise `{timing.normal_move_time_ms} ms`"
        ),
        f"- gripper close: `{GRIPPER_CLOSE_COMMAND}`",
        f"- gripper open/release: `{GRIPPER_OPEN_COMMAND}`",
        f"- final measured home: `{HARDWARE_HOME_COMMAND}`",
        "",
        "| Step | Meaning | Target xyz mm | MuJoCo angles deg `[base, shoulder, elbow, wrist_pitch, wrist_roll]` | Command/action |",
        "| ---: | --- | --- | --- | --- |",
        *rows,
        f"| {len(waypoints) + 1:02d} | measured_hardware_home | measured hardware pose | n/a | `{commands[-1]}` |",
        "",
        "## PWM Delta / Timing Audit",
        "",
        "| Step | Meaning | PWM | Delta from previous arm pose | Per-servo T ms | Note |",
        "| ---: | --- | --- | --- | --- | --- |",
        *[
            "| "
            f"{index:02d} | {item.label} | "
            f"{'' if item.pwm is None else list(item.pwm)} | "
            f"{'' if item.deltas is None else list(item.deltas)} | "
            f"{'' if item.times_ms is None else list(item.times_ms)} | "
            f"{item.note} |"
            for index, item in enumerate(command_metadata, start=1)
        ],
        "",
        "Use raw ASCII commands only. Do not wrap direct PWM commands with `G0001`.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(content), encoding="utf-8")


def generate_target_sequence(
    pick: tuple[float, float, float],
    place: tuple[float, float, float],
    timing: TimingConfig = TimingConfig(),
    trajectory_path: Path = DEFAULT_TRAJECTORY_PATH,
    command_path: Path = DEFAULT_COMMAND_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
) -> TargetSequenceResult:
    waypoints_for_csv = build_target_waypoints(pick, place)
    write_trajectory_csv(waypoints_for_csv, trajectory_path)
    mujoco_waypoints, q_waypoints, np_module = solve_waypoint_angles(trajectory_path)
    commands, command_metadata = build_hardware_commands(
        waypoints_for_csv,
        q_waypoints,
        np_module,
        timing,
    )
    write_command_file(commands, command_path)
    write_summary(
        summary_path,
        pick,
        place,
        waypoints_for_csv,
        q_waypoints,
        commands,
        command_metadata,
        timing,
        np_module,
    )
    return TargetSequenceResult(trajectory_path, command_path, summary_path, commands, command_metadata)


def print_command_preview(result: TargetSequenceResult) -> None:
    print(f"[TARGET] trajectory: {result.trajectory_path}")
    print(f"[TARGET] commands:   {result.command_path}")
    print(f"[TARGET] summary:    {result.summary_path}")
    print("[TARGET] command preview:")
    for index, command in enumerate(result.commands, start=1):
        print(f"  {index:02d}: {command}")


def send_hardware_sequence(
    command_path: Path,
    port: str,
    baud: int,
    fixed_step_delay: float | None,
    dry_run: bool,
) -> None:
    cmd = [
        sys.executable,
        str(DEFAULT_SEND_SCRIPT),
        "--commands",
        str(command_path),
        "--port",
        port,
        "--baud",
        str(baud),
    ]
    if fixed_step_delay is not None:
        cmd.extend(["--fixed-step-delay", str(fixed_step_delay)])
    if dry_run:
        cmd.append("--dry-run")
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def wait_for_start_trigger(mode: str, dry_run: bool = False) -> None:
    if mode == "none":
        return
    if dry_run:
        print(f"[TRIGGER] dry-run mode: skipping {mode!r} start trigger wait.")
        return
    if mode == "button":
        raise SystemExit(
            "Physical button trigger is reserved for the future GPIO/ROS2 integration. "
            "Use --wait-trigger space for current testing."
        )
    if mode != "space":
        raise ValueError(f"Unsupported trigger mode: {mode}")

    print("[TRIGGER] Ready. Press Space or Enter to start the full hardware sequence.")
    if not sys.stdin.isatty():
        input("[TRIGGER] stdin is not a TTY; press Enter to start...")
        return

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            char = sys.stdin.read(1)
            if char in {" ", "\n", "\r"}:
                print("\n[TRIGGER] Start trigger received.")
                return
            if char == "\x03":
                raise KeyboardInterrupt
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
