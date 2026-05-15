"""Thin service layer used by the local-development desktop console.

The console deliberately calls the current algorithm modules in-place. That
keeps day-to-day updates cheap: edit the main project code, restart the UI, and
the new behavior is loaded without rebuilding a packaged app.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
import json
from pathlib import Path
import traceback
from typing import Any, Callable


CODE_DIR = Path(__file__).resolve().parents[1]
ROOT = CODE_DIR.parent
SIM_OUTPUT_DIR = ROOT / "sim_output"


@dataclass(frozen=True)
class OperationResult:
    ok: bool
    message: str
    payload: dict[str, Any]
    stdout: str = ""


@dataclass(frozen=True)
class RecentRun:
    kind: str
    path: Path
    timestamp: str


class ControlConsoleService:
    """Stable facade around the current script-oriented implementation."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self.code_dir = root / "主程序代码"
        self.sim_output_dir = root / "sim_output"

    def project_status(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "code_dir": str(self.code_dir),
            "sim_output_dir": str(self.sim_output_dir),
            "latest_detected_loop": self._path_or_none(self.latest_detected_loop_dir()),
            "latest_startup_scan": self._path_or_none(self.latest_startup_scan_dir()),
            "target_summary": self._path_or_none(self.sim_output_dir / "TARGET_SEQUENCE_SUMMARY.md"),
            "target_commands": self._path_or_none(self.sim_output_dir / "hardware_command_sequence.txt"),
            "camera": self.camera_status(),
            "hardware_ports": self.hardware_port_status(),
        }

    def camera_status(self) -> dict[str, Any]:
        try:
            import config
            import cv2

            index = getattr(config, "RGB_CAMERA_INDEX", 0)
            capture = cv2.VideoCapture(index)
            try:
                opened = bool(capture.isOpened())
                return {"ok": opened, "index": index, "message": "camera opened" if opened else "camera not opened"}
            finally:
                capture.release()
        except Exception as exc:  # noqa: BLE001 - status panels must not crash.
            return {"ok": False, "message": str(exc)}

    def hardware_port_status(self) -> dict[str, Any]:
        try:
            from hardware_port import _list_ports, format_candidates

            candidates = _list_ports()
            return {
                "ok": any(candidate.score > 0 for candidate in candidates),
                "candidates": [candidate.__dict__ for candidate in candidates],
                "message": format_candidates(candidates),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "candidates": [], "message": str(exc)}

    def parameter_snapshot(self) -> dict[str, Any]:
        import config
        import target_sequence

        names = [
            "RGB_CAMERA_INDEX",
            "CAMERA_POSITION_IN_ARM_MM",
            "CAMERA_PIXEL_TO_ARM_Y_SIGN",
            "BIN_PICK_DEPTH_MM",
            "BIN_PICK_GRASP_HEIGHT_MM",
            "BIN_DEPTH_CORRECTION_MM",
            "DEMO_SHELF_PLACE_Y_MM",
            "DEMO_SHELF_PLACE_Z_MM",
            "KNOWN_BOOK_TITLES",
        ]
        target_names = [
            "PICK_INSERT_READY_RETRACT_MM",
            "PICK_INSERT_READY_Z_OFFSET_MM",
            "POST_GRASP_LIFT_MM",
            "POST_GRASP_RETRACT_MM",
            "POST_RELEASE_BACKOFF_MM",
            "POST_RELEASE_BACKOFF_Z_OFFSET_MM",
            "POST_RELEASE_RETREAT_MIN_Z_MM",
            "GRIPPER_PRE_OPEN_COMMAND",
            "GRIPPER_CLOSE_COMMAND",
            "GRIPPER_OPEN_COMMAND",
            "PLACEMENT_SUPPORT_MODE",
            "LEFT_WALL_WRIST_ROLL_DEG",
        ]
        return {
            "config": {name: getattr(config, name, None) for name in names},
            "target_sequence": {name: getattr(target_sequence, name, None) for name in target_names},
        }

    def scan_books(self) -> OperationResult:
        def run() -> dict[str, Any]:
            from vision.lateral_pose_provider import scan_book_pick_poses_with_unknowns_from_camera

            return dict(scan_book_pick_poses_with_unknowns_from_camera())

        return self._capture_operation("scan_books", run)

    def run_target_sequence_dry(
        self,
        pick: tuple[float, float, float],
        place: tuple[float, float, float],
    ) -> OperationResult:
        def run() -> dict[str, Any]:
            from target_sequence import TimingConfig, generate_target_sequence

            result = generate_target_sequence(pick=pick, place=place, timing=TimingConfig())
            return {
                "trajectory_path": str(result.trajectory_path),
                "command_path": str(result.command_path),
                "summary_path": str(result.summary_path),
                "command_count": len(result.commands),
                "commands": list(result.commands),
            }

        return self._capture_operation("run_target_sequence_dry", run)

    def prepare_detected_books_run(
        self,
        *,
        max_books: int | None = None,
        dry_run: bool = True,
    ) -> OperationResult:
        def run() -> dict[str, Any]:
            import config
            from detected_books_loop import run_detected_books_loop
            from hardware_port import AUTO_PORT
            from target_sequence import TimingConfig

            snapshot_path = run_detected_books_loop(
                place_start=(
                    0.0,
                    float(getattr(config, "DEMO_SHELF_PLACE_Y_MM", 250.0)),
                    float(getattr(config, "DEMO_SHELF_PLACE_Z_MM", 140.0)),
                ),
                loop_place_step_mm=float(getattr(config, "DEMO_SHELF_SECTION_WIDTH_MM", 81.0)),
                max_loop_books=max_books,
                port=AUTO_PORT,
                baud=115200,
                fixed_step_delay=None,
                wait_trigger="none",
                dry_run=dry_run,
                timing=TimingConfig(),
                use_initialized_shelf_model=True,
                mode_name="control_console_detected_books_loop",
            )
            snapshot = self.read_json(snapshot_path) or {}
            return {
                "snapshot_path": str(snapshot_path),
                "report_path": str(Path(snapshot_path).with_name("detected_books_loop_report.md")),
                "output_dir": str(Path(snapshot_path).parent),
                "snapshot": snapshot,
            }

        return self._capture_operation("prepare_detected_books_run", run)

    def execute_prepared_run(self) -> OperationResult:
        return OperationResult(
            False,
            "execute_prepared_run is intentionally disabled in the first local-development console",
            {
                "reason": (
                    "V1 keeps hardware sending behind the existing CLI until the dry-run order, "
                    "physical trigger policy, and emergency-stop behavior are reviewed in the UI."
                )
            },
        )

    def latest_detected_loop_dir(self) -> Path | None:
        root = self.sim_output_dir / "detected_books_loop"
        return self._latest_child_dir(root)

    def latest_startup_scan_dir(self) -> Path | None:
        root = self.sim_output_dir / "startup_scan"
        return self._latest_child_dir(root)

    def recent_runs(self) -> list[RecentRun]:
        runs: list[RecentRun] = []
        for kind, root in (
            ("detected_books_loop", self.sim_output_dir / "detected_books_loop"),
            ("startup_scan", self.sim_output_dir / "startup_scan"),
            ("grip_place_test", self.sim_output_dir / "grip_place_test"),
        ):
            for child in sorted(root.glob("*"), reverse=True)[:8]:
                if child.is_dir():
                    runs.append(RecentRun(kind=kind, path=child, timestamp=child.name))
        return sorted(runs, key=lambda item: item.timestamp, reverse=True)

    def latest_visual_paths(self) -> list[Path]:
        paths: list[Path] = []
        for directory in (self.latest_detected_loop_dir(), self.latest_startup_scan_dir()):
            if directory is None:
                continue
            for name in (
                "bin_plan_overlay.png",
                "shelf_plan_overlay.png",
                "center_book_instances_overlay.png",
                "center_bin_grid_overlay.png",
                "left_shelf_overlay.png",
            ):
                path = directory / name
                if path.exists():
                    paths.append(path)
        return paths

    def latest_decision_report(self) -> str:
        directory = self.latest_detected_loop_dir()
        if directory is None:
            return "No detected-books loop output found yet."
        return self.read_text(directory / "detected_books_loop_report.md") or "Report file not found."

    def latest_snapshot(self) -> dict[str, Any]:
        directory = self.latest_detected_loop_dir()
        if directory is None:
            return {}
        return self.read_json(directory / "detected_books_loop_snapshot.json") or {}

    def latest_command_text(self) -> str:
        paths = [
            self.sim_output_dir / "current_detected_book_sequence" / "hardware_command_sequence.txt",
            self.sim_output_dir / "hardware_command_sequence.txt",
        ]
        directory = self.latest_detected_loop_dir()
        if directory is not None:
            paths.insert(0, directory / "loop_hardware_command_sequence.txt")
        for path in paths:
            text = self.read_text(path)
            if text:
                return text
        return "No hardware command sequence found yet."

    def latest_summary_text(self) -> str:
        paths = [
            self.sim_output_dir / "current_detected_book_sequence" / "TARGET_SEQUENCE_SUMMARY.md",
            self.sim_output_dir / "TARGET_SEQUENCE_SUMMARY.md",
        ]
        for path in paths:
            text = self.read_text(path)
            if text:
                return text
        return "No target sequence summary found yet."

    def read_text(self, path: Path) -> str:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="ascii", errors="replace")
        except Exception:
            return ""
        return ""

    def read_json(self, path: Path) -> dict[str, Any] | None:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return None

    def _capture_operation(self, name: str, func: Callable[[], dict[str, Any]]) -> OperationResult:
        buffer = StringIO()
        try:
            with redirect_stdout(buffer), redirect_stderr(buffer):
                payload = func()
            return OperationResult(True, f"{name} completed", payload, buffer.getvalue())
        except Exception as exc:  # noqa: BLE001 - show recoverable errors in the console.
            return OperationResult(
                False,
                f"{name} failed: {exc}",
                {"error": str(exc), "traceback": traceback.format_exc()},
                buffer.getvalue(),
            )

    @staticmethod
    def _latest_child_dir(root: Path) -> Path | None:
        if not root.exists():
            return None
        children = [path for path in root.iterdir() if path.is_dir()]
        return sorted(children, reverse=True)[0] if children else None

    @staticmethod
    def _path_or_none(path: Path | None) -> str | None:
        if path is None:
            return None
        return str(path) if path.exists() else None
