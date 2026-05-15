"""Program entry point for the autonomous book reshelving control system."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

import config
from hardware_port import AUTO_PORT


DEFAULT_HARDWARE_PICK = (218.0, 120.23, 115.0)
DEFAULT_HARDWARE_PLACE = (-40.0, 260.0, 124.25)
DEFAULT_INTERACTIVE_FIXED_STEP_DELAY = 2.5


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_loop_report(snapshot: dict) -> str:
    lines = [
        "# Detected Books Loop Report",
        "",
        f"Status: {snapshot.get('status')}",
        f"Timestamp: {snapshot.get('timestamp')}",
        f"Output directory: {snapshot.get('output_dir')}",
        f"Dry run: {snapshot.get('dry_run')}",
        f"Command file: {snapshot.get('combined_command_path')}",
        f"Command count: {snapshot.get('combined_command_count')}",
        "",
        "## Task Order",
    ]
    tasks = snapshot.get("tasks", [])
    if not tasks:
        lines.append("No tasks were generated.")
    for task in tasks:
        lines.append(
            f"{task['index']}. {task['title']} "
            f"confidence={task['confidence']:.2f} "
            f"pick={tuple(task['pick'])} place={tuple(task['place'])} "
            f"commands={task['command_count']}"
        )
    lines.extend(["", "## Notes"])
    for note in snapshot.get("notes", []):
        lines.append(f"- {note}")
    if snapshot.get("errors"):
        lines.extend(["", "## Errors"])
        for error in snapshot["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def _print_report(title: str, report: str) -> None:
    print()
    print(f"===== {title} =====")
    print(report.rstrip())
    print(f"===== end {title} =====")
    print()


def _format_vec(values: tuple[float, float, float]) -> str:
    return " ".join(f"{value:g}" for value in values)


def _read_input(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        print()
        return ""


def _prompt_choice() -> str:
    print()
    print("ME470 Integrated Algorithm")
    print("1. Run hardware command sequence")
    print("   Generate a fresh trajectory from pick/place and send it to the arm.")
    print("2. Dry run hardware path")
    print("   Generate the same trajectory/commands, but do not open the serial port.")
    print("3. Simulation mode")
    print("   Run the sim_output backend for feasibility/logging; no hardware commands.")
    print("4. Target viewer")
    print("   Generate pick/place trajectory and open the MuJoCo animation.")
    print("5. Startup scan")
    print("   Sweep left-90/0 deg, capture shelf/bin frames, and initialize a world snapshot.")
    print("6. Grip and place test")
    print("   Capture left-90/0 deg only, log OCR, and generate a fixed place dry-run.")
    print("7. Auto demo / detected-books loop")
    print("   Detect known books from one bin frame, plan a demo queue, and dry-run by default.")
    print("q. Quit")
    print()
    return _read_input("Select mode [2]: ").strip().lower() or "2"


def _prompt_float(label: str, default: float) -> float:
    while True:
        raw = _read_input(f"{label} [{default:g}]: ").strip()
        if raw == "":
            return default
        try:
            return float(raw)
        except ValueError:
            print("Please enter a number, or press Enter for the default.")


def _prompt_int(label: str, default: int) -> int:
    while True:
        raw = _read_input(f"{label} [{default}]: ").strip()
        if raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            print("Please enter an integer, or press Enter for the default.")


def _prompt_optional_int(label: str, default: int | None = None) -> int | None:
    default_text = "all" if default is None else str(default)
    while True:
        raw = _read_input(f"{label} [{default_text}]: ").strip().lower()
        if raw == "":
            return default
        if raw in {"all", "none", "0"}:
            return None
        try:
            value = int(raw)
        except ValueError:
            print("Please enter a positive integer, 0/all, or press Enter for the default.")
            continue
        if value <= 0:
            return None
        return value


def _prompt_vec3(label: str, default: tuple[float, float, float]) -> tuple[float, float, float]:
    while True:
        raw = _read_input(f"{label} X Y Z [{_format_vec(default)}]: ").strip()
        if raw == "":
            return default
        parts = raw.replace(",", " ").split()
        if len(parts) != 3:
            print("Please enter exactly three numbers: X Y Z.")
            continue
        try:
            return (float(parts[0]), float(parts[1]), float(parts[2]))
        except ValueError:
            print("Please enter numbers only, or press Enter for the default.")


def _prompt_text(label: str, default: str) -> str:
    raw = _read_input(f"{label} [{default}]: ").strip()
    return raw or default


def _prompt_wait_trigger(default: str = "space") -> str:
    choices = {"none", "space", "button"}
    while True:
        raw = _read_input(f"Wait trigger: none / space / button [{default}]: ").strip().lower()
        value = raw or default
        if value in choices:
            return value
        print("Please enter one of: none, space, button.")


def _prompt_place_slot(default: str = "center") -> str:
    choices = {"left", "center", "right"}
    while True:
        raw = _read_input(f"Place slot: left / center / right [{default}]: ").strip().lower()
        value = raw or default
        if value in choices:
            return value
        print("Please enter one of: left, center, right.")


def _append_vec3(argv: list[str], flag: str, values: tuple[float, float, float]) -> None:
    argv.append(flag)
    argv.extend(f"{value:g}" for value in values)


def _interactive_argv() -> list[str]:
    choice = _prompt_choice()
    if choice in {"q", "quit", "exit"}:
        print("Exiting.")
        raise SystemExit(0)

    if choice not in {"1", "2", "3", "4", "5", "6", "7"}:
        print("Unknown selection; defaulting to dry run.")
        choice = "2"

    argv: list[str] = []
    if choice in {"1", "2", "4"}:
        pick = _prompt_vec3("Pick point", DEFAULT_HARDWARE_PICK)
        place = _prompt_vec3("Place point", DEFAULT_HARDWARE_PLACE)
        _append_vec3(argv, "--pick", pick)
        _append_vec3(argv, "--place", place)

    if choice == "1":
        argv.append("--run-target-sequence")
        argv.extend(["--hardware-port", _prompt_text("Hardware serial port", AUTO_PORT)])
        argv.extend(["--hardware-baud", str(_prompt_int("Hardware baud", 115200))])
        fixed_delay = _prompt_float("Fixed delay after each command, seconds", DEFAULT_INTERACTIVE_FIXED_STEP_DELAY)
        argv.extend(["--fixed-step-delay", f"{fixed_delay:g}"])
        argv.extend(["--wait-trigger", _prompt_wait_trigger("space")])
        return argv

    if choice == "2":
        argv.append("--run-target-sequence")
        argv.append("--dry-run")
        return argv

    if choice == "3":
        argv.append("--sim-mode")
        book_x = _prompt_float("Book/pick X", config.RETURN_BOOK_X)
        book_y = _prompt_float("Book/pick Y", config.RETURN_BOOK_Y)
        book_z = _prompt_float("Book/pick Z", config.RETURN_BOOK_Z)
        argv.extend(["--book-xy", f"{book_x:g}", f"{book_y:g}"])
        argv.extend(["--book-z", f"{book_z:g}"])

        place_final = _prompt_vec3("Sim final place point", config.FIXED_PLACE_FINAL_POSE)
        _append_vec3(argv, "--place-final", place_final)
        place_retreat = _prompt_vec3("Sim retreat point", config.FIXED_PLACE_RETREAT_POSE)
        _append_vec3(argv, "--place-retreat", place_retreat)
        place_approach = _prompt_vec3("Sim approach point", config.FIXED_PLACE_APPROACH_POSE)
        _append_vec3(argv, "--place-approach", place_approach)
        return argv

    if choice == "5":
        argv.append("--startup-scan")
        argv.extend(["--hardware-port", _prompt_text("Hardware serial port", AUTO_PORT)])
        argv.extend(["--hardware-baud", str(_prompt_int("Hardware baud", 115200))])
        fixed_delay = _prompt_float("Fixed delay after each command, seconds", DEFAULT_INTERACTIVE_FIXED_STEP_DELAY)
        argv.extend(["--fixed-step-delay", f"{fixed_delay:g}"])
        settle = _prompt_float("Settle time at each scan angle, seconds", 4.0)
        argv.extend(["--startup-scan-settle-seconds", f"{settle:g}"])
        argv.extend(["--wait-trigger", _prompt_wait_trigger("space")])
        return argv

    if choice == "6":
        argv.append("--grip-place-test")
        argv.append("--dry-run")
        argv.extend(["--grip-place-slot", _prompt_place_slot("center")])
        settle = _prompt_float("Settle time at each test angle, seconds", 4.0)
        argv.extend(["--startup-scan-settle-seconds", f"{settle:g}"])
        argv.extend(["--wait-trigger", _prompt_wait_trigger("none")])
        return argv

    if choice == "7":
        argv.append("--auto-demo")
        argv.append("--dry-run")
        print("Using latest startup-scan shelf world model by default.")
        step = _prompt_float("Demo shelf +X step per book, mm", 15.0)
        argv.extend(["--loop-place-step-mm", f"{step:g}"])
        max_books = _prompt_optional_int("Max books for this run (0/all = all detected)", None)
        if max_books is not None:
            argv.extend(["--max-loop-books", str(max_books)])
        camera_index = _prompt_text("Camera index", "0")
        argv.extend(["--camera-index", camera_index])
        argv.extend(["--wait-trigger", _prompt_wait_trigger("none")])
        return argv

    argv.append("--target-viewer")
    return argv


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the book reshelving control system.")
    parser.add_argument(
        "--sim-mode",
        action="store_true",
        help="Simulation backend only. Does not generate or send hardware commands.",
    )
    parser.add_argument(
        "--book-xy",
        nargs=2,
        type=float,
        metavar=("X", "Y"),
        help=(
            "Set the pick/book XY position in millimeters relative to the arm base yaw joint "
            "(robot body center). X is left/right and Y is forward/back. In pick-place-only mode, "
            "this directly changes the MuJoCo pickup waypoint."
        ),
    )
    parser.add_argument(
        "--book-z",
        type=float,
        help="Optional pick/book Z position in millimeters. In pick-place-only mode, this directly changes the pickup waypoint.",
    )
    parser.add_argument(
        "--pick-approach",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="Override the pre-grasp waypoint above the pickup point in millimeters.",
    )
    parser.add_argument(
        "--pick-approach-clearance",
        type=float,
        metavar="MM",
        help="Set the derived pre-grasp Z clearance above --book-z in millimeters.",
    )
    parser.add_argument(
        "--pick-lift",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="Override the post-grasp lift waypoint in millimeters.",
    )
    parser.add_argument(
        "--post-grasp-lift",
        type=float,
        metavar="MM",
        help="Set the derived post-grasp vertical lift above --book-z in millimeters.",
    )
    parser.add_argument(
        "--place-approach",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="Override the placement approach waypoint in millimeters.",
    )
    parser.add_argument(
        "--place-transfer",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="Override the shelf-side high transfer waypoint before lowering in millimeters.",
    )
    parser.add_argument(
        "--place-final",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="Override the final placement/release waypoint in millimeters.",
    )
    parser.add_argument(
        "--place-retreat",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="Override the post-release retreat waypoint in millimeters.",
    )
    parser.add_argument(
        "--sim-log-path",
        type=Path,
        help="Optional path for the sim_output log file.",
    )
    parser.add_argument(
        "--viewer",
        action="store_true",
        help="Simulation/debug only: record trajectory and open MuJoCo visualization after execution.",
    )
    parser.add_argument(
        "--run-target-sequence",
        action="store_true",
        help="Formal hardware path: generate a fresh pick/place command sequence from --pick/--place and optionally send it.",
    )
    parser.add_argument(
        "--run-detected-books-loop",
        action="store_true",
        help=(
            "Detect all known books in the current camera frame, order them by "
            "config.KNOWN_BOOK_TITLES, then run one pick/place sequence per book. "
            "Uses --place as the first placement point, then steps right in X."
        ),
    )
    parser.add_argument(
        "--auto-demo",
        action="store_true",
        help=(
            "Current standard demo Auto shell. Uses the detected-books loop, "
            "records world-model state, prechecks target_sequence commands, "
            "prints a plan, then waits for the selected trigger before hardware send."
        ),
    )
    parser.add_argument(
        "--target-viewer",
        action="store_true",
        help="Simulation/debug only: generate a target-sequence trajectory from --pick/--place and open the MuJoCo viewer.",
    )
    parser.add_argument(
        "--startup-scan",
        action="store_true",
        help=(
            "Run the two-view startup scan workflow. Sends base-only left-90/0 deg commands, "
            "captures shelf/bin frames, returns home, and writes a world snapshot JSON."
        ),
    )
    parser.add_argument(
        "--startup-scan-settle-seconds",
        type=float,
        default=4.0,
        help="Seconds to wait after each startup scan base move before capturing a frame.",
    )
    parser.add_argument(
        "--startup-scan-output-dir",
        type=Path,
        help="Optional output root for startup scan snapshots.",
    )
    parser.add_argument(
        "--grip-place-test",
        action="store_true",
        help=(
            "Run the minimal two-view grip/place test. Captures left-90 and 0 deg views, "
            "logs OCR, and generates target_sequence for a fixed test place point."
        ),
    )
    parser.add_argument(
        "--grip-place-slot",
        choices=["left", "center", "right"],
        default="center",
        help="Fixed place slot used by --grip-place-test.",
    )
    parser.add_argument(
        "--grip-place-output-dir",
        type=Path,
        help="Optional output root for grip/place test snapshots.",
    )
    parser.add_argument(
        "--detected-loop-output-dir",
        type=Path,
        help="Optional output root for detected-books loop / auto-demo snapshots.",
    )
    parser.add_argument(
        "--shelf-model-snapshot",
        type=Path,
        help=(
            "Startup-scan snapshot JSON used to initialize shelf slots for --auto-demo/"
            "--run-detected-books-loop. If omitted, the latest startup scan is used."
        ),
    )
    parser.add_argument(
        "--no-auto-shelf-model",
        action="store_true",
        help=(
            "Disable A-route initialized shelf model lookup for --auto-demo/"
            "--run-detected-books-loop and use --place + --loop-place-step-mm instead."
        ),
    )
    parser.add_argument(
        "--skip-auto-startup-scan",
        action="store_true",
        help=(
            "For --auto-demo, reuse --shelf-model-snapshot or the latest startup scan "
            "instead of running a fresh startup scan first."
        ),
    )
    parser.add_argument(
        "--pick",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="Book-spine grasp point in millimeters for --run-target-sequence or --target-viewer.",
    )
    parser.add_argument(
        "--place",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="Final shelf placement point in millimeters for --run-target-sequence or --target-viewer.",
    )
    parser.add_argument(
        "--hardware-port",
        default=AUTO_PORT,
        help="Serial port used by hardware paths. Use 'auto' to detect the arm controller.",
    )
    parser.add_argument(
        "--hardware-baud",
        type=int,
        default=115200,
        help="Serial baud rate used by --run-target-sequence.",
    )
    parser.add_argument(
        "--camera-index",
        default=None,
        help=(
            "Override config.RGB_CAMERA_INDEX for camera-based workflows. "
            "Current robot-mounted camera is index 0."
        ),
    )
    parser.add_argument(
        "--fixed-step-delay",
        type=float,
        default=None,
        help="Optional fixed delay passed to the hardware sender after each command.",
    )
    parser.add_argument(
        "--wait-trigger",
        choices=["none", "space", "button"],
        default="space",
        help=(
            "For --run-target-sequence, --startup-scan, or --grip-place-test, wait for a start trigger "
            "before sending hardware commands. Dry-run skips the wait. Current "
            "hardware testing uses 'space'; 'button' is reserved."
        ),
    )
    parser.add_argument(
        "--small-move-fast-threshold-pwm",
        type=int,
        default=20,
        help="PWM delta below this value uses --small-move-time-ms.",
    )
    parser.add_argument(
        "--medium-move-threshold-pwm",
        type=int,
        default=120,
        help="PWM delta below this value uses --medium-move-time-ms; larger moves use normal time.",
    )
    parser.add_argument(
        "--small-move-time-ms",
        type=int,
        default=400,
        help="Per-servo T time for very small PWM deltas.",
    )
    parser.add_argument(
        "--medium-move-time-ms",
        type=int,
        default=800,
        help="Per-servo T time for medium PWM deltas.",
    )
    parser.add_argument(
        "--normal-move-time-ms",
        type=int,
        default=1500,
        help="Per-servo T time for normal/larger PWM deltas and first arm command.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print commands without opening serial for hardware-oriented paths.",
    )
    parser.add_argument(
        "--max-loop-books",
        type=int,
        default=None,
        help="Optional cap for --run-detected-books-loop during testing.",
    )
    parser.add_argument(
        "--loop-place-step-mm",
        type=float,
        default=15.0,
        help=(
            "For --run-detected-books-loop, shift each next placement point to "
            "the right by this many millimeters along +X."
        ),
    )
    parser.add_argument(
        "--use-vision-for-pick",
        action="store_true",
        help=(
            "Replace FIXED_PICK_POSE with vision.lateral_pose_provider output. "
            "Requires camera + PaddleOCR available. Falls back to FIXED_PICK_POSE "
            "if vision returns None."
        ),
    )
    parser.add_argument(
        "--vision-shadow-mode",
        action="store_true",
        help=(
            "Run vision pose detection in parallel for logging only; do not "
            "replace FIXED_PICK_POSE. Useful to verify the data pipeline without "
            "changing demo behavior."
        ),
    )
    parser.add_argument(
        "--fake-vision-pose",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help=(
            "Inject a fixed pose into the vision pick provider. "
            "Used to verify the PickPlacePlan wiring without exercising the real camera/OCR."
        ),
    )
    parser.add_argument(
        "--startup-calibrate",
        action="store_true",
        help=(
            "Run AprilTag-based startup calibration of bin and shelf positions. "
            "Captures 2 frames (bin and shelf) and writes runtime_state. "
            "Currently uses single frame for both (smoke test); real demo "
            "should rotate joint 0 between captures."
        ),
    )
    argv = _interactive_argv() if len(sys.argv) == 1 else sys.argv[1:]
    args = parser.parse_args(argv)

    sim_override_flags = (
        args.sim_mode
        or args.viewer
        or args.book_xy is not None
        or args.book_z is not None
        or args.pick_approach is not None
        or args.pick_approach_clearance is not None
        or args.pick_lift is not None
        or args.post_grasp_lift is not None
        or args.place_transfer is not None
        or args.place_approach is not None
        or args.place_final is not None
        or args.place_retreat is not None
        or args.sim_log_path is not None
    )

    if args.run_target_sequence and (args.target_viewer or args.run_detected_books_loop or args.auto_demo or sim_override_flags):
        parser.error(
            "--run-target-sequence is the formal hardware-generation path. "
            "Do not combine it with --sim-mode, --viewer, --target-viewer, "
            "--run-detected-books-loop, --auto-demo, or simulation waypoint overrides."
        )
    if args.run_detected_books_loop and args.auto_demo:
        parser.error("Use either --run-detected-books-loop or --auto-demo, not both.")
    if (args.run_detected_books_loop or args.auto_demo) and (
        args.target_viewer
        or args.startup_scan
        or args.grip_place_test
        or args.startup_calibrate
        or sim_override_flags
        or args.pick is not None
    ):
        parser.error(
            "--run-detected-books-loop/--auto-demo is an independent hardware-generation path. "
            "Do not combine it with viewer/sim/startup/grip-place workflows or --pick."
        )
    if args.max_loop_books is not None and args.max_loop_books <= 0:
        parser.error("--max-loop-books must be positive when provided.")
    if args.loop_place_step_mm < 0:
        parser.error("--loop-place-step-mm must be non-negative.")
    if args.target_viewer and sim_override_flags:
        parser.error(
            "--target-viewer is a simulation/debug viewer path. "
            "Do not combine it with --sim-mode, --viewer, or pick-place-only simulation overrides."
        )
    if args.startup_scan and (
        args.run_target_sequence
        or args.run_detected_books_loop
        or args.auto_demo
        or args.target_viewer
        or args.grip_place_test
        or args.startup_calibrate
        or sim_override_flags
        or args.pick is not None
        or args.place is not None
    ):
        parser.error(
            "--startup-scan is an independent startup workflow. "
            "Do not combine it with target sequence, startup calibration, viewer, sim, --pick, or --place arguments."
        )
    if args.grip_place_test and (
        args.run_target_sequence
        or args.run_detected_books_loop
        or args.auto_demo
        or args.target_viewer
        or args.startup_scan
        or args.startup_calibrate
        or sim_override_flags
        or args.pick is not None
        or args.place is not None
    ):
        parser.error(
            "--grip-place-test is an independent minimal workflow. "
            "Do not combine it with target sequence, startup scan/calibration, viewer, sim, --pick, or --place arguments."
        )

    # Vision integration flags (apply before sim_mode init / controller import,
    # so config.get_pick_place_plan() sees the right state on first call).
    if args.use_vision_for_pick:
        config.USE_VISION_FOR_PICK = True
    if args.vision_shadow_mode:
        config.VISION_SHADOW_MODE = True
    if args.fake_vision_pose is not None:
        config.FAKE_VISION_PICK_POSE = (
            float(args.fake_vision_pose[0]),
            float(args.fake_vision_pose[1]),
            float(args.fake_vision_pose[2]),
        )
    if args.camera_index is not None:
        raw_camera_index = str(args.camera_index)
        if raw_camera_index.lower() == "auto":
            parser.error("--camera-index auto is disabled for this hardware setup; use --camera-index 0")
        else:
            try:
                config.RGB_CAMERA_INDEX = int(raw_camera_index)
            except ValueError:
                parser.error("--camera-index must be an integer or 'auto'")

    if args.startup_scan:
        from startup_scan import DEFAULT_OUTPUT_ROOT, run_startup_scan

        output_root = args.startup_scan_output_dir or DEFAULT_OUTPUT_ROOT
        run_startup_scan(
            port=args.hardware_port,
            baud=args.hardware_baud,
            fixed_step_delay=args.fixed_step_delay,
            settle_seconds=args.startup_scan_settle_seconds,
            wait_trigger=args.wait_trigger,
            dry_run=args.dry_run,
            output_root=output_root,
        )
        return

    if args.grip_place_test:
        from grip_place_test import DEFAULT_OUTPUT_ROOT, run_grip_place_test
        from target_sequence import TimingConfig

        output_root = args.grip_place_output_dir or DEFAULT_OUTPUT_ROOT
        timing = TimingConfig(
            small_move_fast_threshold_pwm=args.small_move_fast_threshold_pwm,
            medium_move_threshold_pwm=args.medium_move_threshold_pwm,
            small_move_time_ms=args.small_move_time_ms,
            medium_move_time_ms=args.medium_move_time_ms,
            normal_move_time_ms=args.normal_move_time_ms,
        )
        run_grip_place_test(
            port=args.hardware_port,
            baud=args.hardware_baud,
            fixed_step_delay=args.fixed_step_delay,
            settle_seconds=args.startup_scan_settle_seconds,
            wait_trigger=args.wait_trigger,
            dry_run=True,
            place_slot=args.grip_place_slot,
            output_root=output_root,
            timing=timing,
        )
        return

    if args.startup_calibrate:
        from vision.camera import CameraError, RGBCamera
        from vision.object_localization import run_startup_calibration

        try:
            cam = RGBCamera.instance()
            frame_bin = cam.read_frame()
            # TODO: 真实 demo 时这里要先转 joint 0 = JOINT0_SHELF_SCAN_DEG，等到位再拍
            #       现在 smoke test 用同一帧（要求 bin + shelf 都在画面里同时看到）
            frame_shelf = cam.read_frame()
        except CameraError as exc:
            print(f"[CAL] 启动校准失败：相机不可用：{exc}")
            return

        ok = run_startup_calibration(frame_bin, frame_shelf)
        if not ok:
            print("[CAL] 启动校准失败，请检查 AprilTag 是否被遮挡或贴反")
            return
        print("[CAL] 启动校准完成")

    if args.run_detected_books_loop or args.auto_demo:
        if args.no_auto_shelf_model and args.place is None:
            parser.error(
                "--no-auto-shelf-model requires --place X Y Z for --run-detected-books-loop/--auto-demo"
            )
        from detected_books_loop import DEFAULT_OUTPUT_ROOT, run_detected_books_loop
        from target_sequence import TimingConfig

        timing = TimingConfig(
            small_move_fast_threshold_pwm=args.small_move_fast_threshold_pwm,
            medium_move_threshold_pwm=args.medium_move_threshold_pwm,
            small_move_time_ms=args.small_move_time_ms,
            medium_move_time_ms=args.medium_move_time_ms,
            normal_move_time_ms=args.normal_move_time_ms,
        )
        shelf_model_snapshot = args.shelf_model_snapshot
        if (
            args.auto_demo
            and not args.no_auto_shelf_model
            and not args.skip_auto_startup_scan
            and shelf_model_snapshot is None
        ):
            from startup_scan import DEFAULT_OUTPUT_ROOT as STARTUP_SCAN_OUTPUT_ROOT
            from startup_scan import run_startup_scan

            print(
                "[AUTO] Running startup scan first to initialize shelf world model. "
                "Use --skip-auto-startup-scan to reuse an existing snapshot.",
                flush=True,
            )
            shelf_model_snapshot = run_startup_scan(
                port=args.hardware_port,
                baud=args.hardware_baud,
                fixed_step_delay=args.fixed_step_delay,
                settle_seconds=args.startup_scan_settle_seconds,
                wait_trigger="none",
                dry_run=args.dry_run,
                output_root=args.startup_scan_output_dir or STARTUP_SCAN_OUTPUT_ROOT,
            )
            try:
                startup_snapshot = json.loads(shelf_model_snapshot.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 - user-facing runtime guard.
                print(f"[AUTO] Startup scan finished but snapshot could not be read: {exc}")
                return
            startup_slots = (startup_snapshot.get("shelf_world_model") or {}).get("slots", [])
            if not startup_slots:
                print(
                    "[AUTO] Startup scan did not initialize any shelf slots, so Auto demo stopped "
                    "before planning motion."
                )
                for issue in startup_snapshot.get("errors", []):
                    print(f"[AUTO] Startup issue: {issue}")
                print(f"[AUTO] Snapshot: {shelf_model_snapshot}")
                return
        try:
            run_detected_books_loop(
                place_start=None if args.place is None else tuple(args.place),
                loop_place_step_mm=args.loop_place_step_mm,
                max_loop_books=args.max_loop_books,
                port=args.hardware_port,
                baud=args.hardware_baud,
                fixed_step_delay=args.fixed_step_delay,
                wait_trigger=args.wait_trigger,
                dry_run=args.dry_run,
                timing=timing,
                shelf_model_snapshot=shelf_model_snapshot,
                use_initialized_shelf_model=not args.no_auto_shelf_model,
                output_root=args.detected_loop_output_dir or DEFAULT_OUTPUT_ROOT,
                mode_name="auto_demo" if args.auto_demo else "detected_books_loop",
            )
        except RuntimeError as exc:
            parser.error(f"--run-detected-books-loop/--auto-demo: {exc}")
        return

    if args.target_viewer:
        if args.pick is None or args.place is None:
            parser.error("--target-viewer requires --pick X Y Z and --place X Y Z")
        import subprocess
        from target_sequence import DEFAULT_TRAJECTORY_PATH, build_target_waypoints, write_trajectory_csv

        waypoints = build_target_waypoints(tuple(args.pick), tuple(args.place))
        write_trajectory_csv(waypoints, DEFAULT_TRAJECTORY_PATH)
        print(f"[TARGET VIEWER] trajectory: {DEFAULT_TRAJECTORY_PATH}")
        print("[TARGET VIEWER] waypoints:")
        for index, waypoint in enumerate(waypoints, start=1):
            print(
                f"  {index:02d}: {waypoint.label} "
                f"({waypoint.x:.2f}, {waypoint.y:.2f}, {waypoint.z:.2f})"
            )
        subprocess.run(
            [
                "mjpython",
                "sim/km1_trajectory_viewer.py",
                "--trajectory",
                str(DEFAULT_TRAJECTORY_PATH),
                "--free-end-link",
            ],
            check=True,
        )
        return

    if args.run_target_sequence:
        pick = args.pick
        # 2026-05-11: 允许 --run-target-sequence + --use-vision-for-pick 组合：
        # 不带 --pick 时，自动调一次视觉抓帧 + OCR 算 pick_pose。
        if pick is None and args.use_vision_for_pick:
            from vision.lateral_pose_provider import get_pick_pose_from_camera

            title = config.KNOWN_BOOK_TITLES[0] if config.KNOWN_BOOK_TITLES else ""
            vision_pose = get_pick_pose_from_camera(title)
            if vision_pose is None:
                parser.error(
                    "--use-vision-for-pick: 视觉返回 None（相机不可用 / OCR 未命中目标书）。"
                    "请显式传 --pick X Y Z，或检查 bin 里的书 / 重试。"
                )
            print(
                f"[RUNTIME] Vision-derived pick = "
                f"({vision_pose[0]:.1f}, {vision_pose[1]:.1f}, {vision_pose[2]:.1f}) mm "
                f"for title={title!r}",
                flush=True,
            )
            pick = list(vision_pose)
        if pick is None or args.place is None:
            parser.error(
                "--run-target-sequence requires --pick X Y Z and --place X Y Z "
                "(or --use-vision-for-pick to auto-derive --pick from camera)."
            )
        print(
            "[RUNTIME] Formal hardware-generation path: generating a fresh "
            "trajectory and command sequence from this run's --pick/--place. "
            "No sim backend or MuJoCo viewer will be launched.",
            flush=True,
        )
        from target_sequence import (
            TimingConfig,
            generate_target_sequence,
            preflight_hardware_sender,
            print_command_preview,
            send_hardware_sequence,
            wait_for_start_trigger,
        )

        timing = TimingConfig(
            small_move_fast_threshold_pwm=args.small_move_fast_threshold_pwm,
            medium_move_threshold_pwm=args.medium_move_threshold_pwm,
            small_move_time_ms=args.small_move_time_ms,
            medium_move_time_ms=args.medium_move_time_ms,
            normal_move_time_ms=args.normal_move_time_ms,
        )
        result = generate_target_sequence(
            pick=tuple(pick),
            place=tuple(args.place),
            timing=timing,
        )
        print_command_preview(result)
        preflight_hardware_sender(args.hardware_port, dry_run=args.dry_run)
        wait_for_start_trigger(args.wait_trigger, dry_run=args.dry_run)
        send_hardware_sequence(
            command_path=result.command_path,
            port=args.hardware_port,
            baud=args.hardware_baud,
            fixed_step_delay=args.fixed_step_delay,
            dry_run=args.dry_run,
        )
        return

    viewer_mode = args.viewer
    sim_mode = sim_override_flags
    if sim_mode or viewer_mode:
        print(
            "[RUNTIME] Simulation/viewer path enabled. This path uses the "
            "sim_output backend and does not send hardware commands.",
            flush=True,
        )
        book_x = args.book_xy[0] if args.book_xy is not None else None
        book_y = args.book_xy[1] if args.book_xy is not None else None
        book_z = args.book_z if args.book_z is not None else None
        log_path = str(args.sim_log_path) if args.sim_log_path is not None else None
        config.configure_sim_mode(
            sim_mode,
            book_x=book_x,
            book_y=book_y,
            book_z=book_z,
            log_path=log_path,
            viewer=viewer_mode,
            pick_approach=tuple(args.pick_approach) if args.pick_approach is not None else None,
            pick_approach_clearance=args.pick_approach_clearance,
            pick_lift=tuple(args.pick_lift) if args.pick_lift is not None else None,
            post_grasp_lift=args.post_grasp_lift,
            place_transfer=tuple(args.place_transfer) if args.place_transfer is not None else None,
            place_approach=tuple(args.place_approach) if args.place_approach is not None else None,
            place_final=tuple(args.place_final) if args.place_final is not None else None,
            place_retreat=tuple(args.place_retreat) if args.place_retreat is not None else None,
        )
    from controller import RobotControlSystem

    robot = RobotControlSystem()
    robot.run()

    if viewer_mode:
        from visualization import save_and_view

        save_and_view()


if __name__ == "__main__":
    main()
