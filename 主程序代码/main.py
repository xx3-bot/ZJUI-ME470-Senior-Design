"""Program entry point for the autonomous book reshelving control system."""

from __future__ import annotations

import argparse
from pathlib import Path

import config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the book reshelving control system.")
    parser.add_argument(
        "--sim-mode",
        action="store_true",
        help="Enable sim_output motion backend and logging.",
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
        help="Record trajectory and open MuJoCo visualization after execution.",
    )
    parser.add_argument(
        "--run-target-sequence",
        action="store_true",
        help="Generate a pick/place hardware sequence from --pick/--place and optionally send it.",
    )
    parser.add_argument(
        "--target-viewer",
        action="store_true",
        help="Generate a target-sequence trajectory from --pick/--place and open the MuJoCo viewer.",
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
        default="/dev/ttyUSB0",
        help="Serial port used by --run-target-sequence when not in --dry-run.",
    )
    parser.add_argument(
        "--hardware-baud",
        type=int,
        default=115200,
        help="Serial baud rate used by --run-target-sequence.",
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
            "For --run-target-sequence, wait for a start trigger after command generation. "
            "Dry-run skips the wait. Current hardware testing uses 'space'; 'button' is reserved."
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
        help="For --run-target-sequence, generate and print commands without opening serial.",
    )
    parser.add_argument(
        "--use-vision-for-pick",
        action="store_true",
        help=(
            "Replace FIXED_PICK_POSE with vision.world_pose_provider output. "
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
            "Inject a fixed pose into vision.world_pose_provider.get_pick_world_pose. "
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
    args = parser.parse_args()

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
        if args.pick is None or args.place is None:
            parser.error("--run-target-sequence requires --pick X Y Z and --place X Y Z")
        from target_sequence import (
            TimingConfig,
            generate_target_sequence,
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
            pick=tuple(args.pick),
            place=tuple(args.place),
            timing=timing,
        )
        print_command_preview(result)
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
    sim_mode = (
        args.sim_mode
        or viewer_mode
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
    if sim_mode or viewer_mode:
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
