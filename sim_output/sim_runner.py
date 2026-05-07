"""Simple runner for sim_output backend verification."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAIN_CODE_DIR = PROJECT_ROOT / "主程序代码"
if str(MAIN_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(MAIN_CODE_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sim_output.backend import initialize, move_to, gripper_command
from models import Pose
from pick_place_plan import DEFAULT_PICK_APPROACH_CLEARANCE_MM


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a simple sim_output backend test.")
    parser.add_argument("--log-path", type=Path, default=Path("sim_output") / "sim_output.log")
    parser.add_argument("--book-xy", nargs=2, type=float, metavar=("X", "Y"), default=[280.0, 100.0])
    parser.add_argument("--book-z", type=float, default=100.0, help="Book target Z position in millimeters.")
    args = parser.parse_args()

    initialize(args.log_path, book_x=args.book_xy[0], book_y=args.book_xy[1], book_z=args.book_z)

    current_pose = Pose(0.0, 0.0, args.book_z + DEFAULT_PICK_APPROACH_CLEARANCE_MM)
    target_pose = Pose(args.book_xy[0], args.book_xy[1], args.book_z)

    print("Testing move_to...")
    success = move_to(current_pose, target_pose)
    print(f"move_to success={success}")

    print("Testing gripper_command OPEN...")
    result_open = gripper_command("OPEN")
    print(f"OPEN result={result_open}")

    print("Testing gripper_command CLOSE...")
    result_close = gripper_command("CLOSE")
    print(f"CLOSE result={result_close}")


if __name__ == "__main__":
    main()
