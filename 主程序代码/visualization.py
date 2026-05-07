"""Record trajectory waypoints for MuJoCo visualization."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path
from typing import Optional

from models import Pose


class TrajectoryRecorder:
    """Record all gripper move_to waypoints to a CSV file for later visualization."""

    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)
        self.waypoints: list[tuple[float, float, float, bool, bool, bool, bool | None]] = []
        # Default scene state: book is in return bin, not held.
        self.held_book_visible = False
        self.return_book_visible = True
        self.placed_book_visible = False
        self.horizontal_end_link: bool | None = None

    def record_waypoint(self, pose: Pose) -> None:
        """Add a gripper target pose to the trajectory."""
        self.record_waypoint_state(
            pose=pose,
            held_book_visible=self.held_book_visible,
            return_book_visible=self.return_book_visible,
            placed_book_visible=self.placed_book_visible,
            horizontal_end_link=self.horizontal_end_link,
        )

    def record_waypoint_state(
        self,
        pose: Pose,
        held_book_visible: bool,
        return_book_visible: bool,
        placed_book_visible: bool,
        horizontal_end_link: bool | None = None,
    ) -> None:
        """Add a gripper target pose with book visibility state."""
        self.held_book_visible = held_book_visible
        self.return_book_visible = return_book_visible
        self.placed_book_visible = placed_book_visible
        self.horizontal_end_link = horizontal_end_link
        self.waypoints.append(
            (
                pose.x,
                pose.y,
                pose.z,
                held_book_visible,
                return_book_visible,
                placed_book_visible,
                horizontal_end_link,
            )
        )

    def save_trajectory(self) -> None:
        """Write all waypoints to CSV file."""
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        with self.csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "x_mm",
                    "y_mm",
                    "z_mm",
                    "held_book_visible",
                    "return_book_visible",
                    "placed_book_visible",
                    "horizontal_end_link",
                ]
            )
            for x, y, z, held_visible, return_visible, placed_visible, horizontal_end_link in self.waypoints:
                writer.writerow(
                    [
                        x,
                        y,
                        z,
                        int(held_visible),
                        int(return_visible),
                        int(placed_visible),
                        "" if horizontal_end_link is None else int(horizontal_end_link),
                    ]
                )
        print(f"[TRAJECTORY] Saved {len(self.waypoints)} waypoints to {self.csv_path}")

    def launch_viewer(self) -> None:
        """Open the trajectory in MuJoCo viewer using km1_trajectory_viewer.py."""
        if not self.waypoints:
            print("[TRAJECTORY] No waypoints recorded, skipping viewer.")
            return

        sim_dir = Path(__file__).resolve().parent.parent / "sim"
        viewer_script = sim_dir / "km1_trajectory_viewer.py"

        if not viewer_script.exists():
            print(f"[TRAJECTORY] Cannot find viewer script: {viewer_script}")
            return

        print(f"[TRAJECTORY] Launching MuJoCo viewer with {len(self.waypoints)} waypoints...")
        try:
            subprocess.run(
                ["mjpython", str(viewer_script), "--trajectory", str(self.csv_path), "--free-end-link"],
                cwd=str(sim_dir),
                check=False,
            )
        except FileNotFoundError:
            print(
                "[TRAJECTORY] mjpython not found. Install MuJoCo: pip install mujoco"
            )


_recorder: Optional[TrajectoryRecorder] = None


def initialize_recorder(csv_path: str | Path) -> None:
    """Initialize the trajectory recorder."""
    global _recorder
    _recorder = TrajectoryRecorder(csv_path)


def record_waypoint(pose: Pose) -> None:
    """Record a waypoint to the trajectory."""
    if _recorder is not None:
        _recorder.record_waypoint(pose)


def record_waypoint_state(
    pose: Pose,
    held_book_visible: bool,
    return_book_visible: bool,
    placed_book_visible: bool,
    horizontal_end_link: bool | None = None,
) -> None:
    """Record a waypoint with book-visibility state for pickup/place animation."""
    if _recorder is not None:
        _recorder.record_waypoint_state(
            pose=pose,
            held_book_visible=held_book_visible,
            return_book_visible=return_book_visible,
            placed_book_visible=placed_book_visible,
            horizontal_end_link=horizontal_end_link,
        )


def save_and_view() -> None:
    """Save the trajectory and launch the MuJoCo viewer."""
    if _recorder is not None:
        _recorder.save_trajectory()
        _recorder.launch_viewer()
