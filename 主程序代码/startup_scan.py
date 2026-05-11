"""Three-view startup scan workflow for bin/shelf perception handoff."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import time
from typing import Any

from target_sequence import (
    DEFAULT_SEND_SCRIPT,
    HARDWARE_HOME_COMMAND,
    ROOT,
    wait_for_start_trigger,
)


DEFAULT_OUTPUT_ROOT = ROOT / "sim_output" / "startup_scan"
DEFAULT_SETTLE_SECONDS = 4.0
BASE_MOVE_TIME_MS = 2500


@dataclass(frozen=True)
class ScanView:
    label: str
    filename: str
    joint0_deg: int
    pwm: int
    sections: tuple[str, ...]
    description: str

    @property
    def command(self) -> str:
        return f"{{#000P{self.pwm:04d}T{BASE_MOVE_TIME_MS}!}}"


SCAN_VIEWS = (
    ScanView(
        label="left",
        filename="left.png",
        joint0_deg=-90,
        pwm=833,
        sections=("A", "B"),
        description="-90 deg shelf view: left side=A, right side=B",
    ),
    ScanView(
        label="center",
        filename="center.png",
        joint0_deg=0,
        pwm=1500,
        sections=("bin",),
        description="0 deg bin view",
    ),
    ScanView(
        label="right",
        filename="right.png",
        joint0_deg=90,
        pwm=2167,
        sections=("C", "D"),
        description="+90 deg shelf view: left side=C, right side=D",
    ),
)


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _command_file_path(output_dir: Path, label: str) -> Path:
    return output_dir / f"{label}_command.txt"


def _load_sender_module() -> Any:
    spec = importlib.util.spec_from_file_location("me470_send_hardware_sequence", DEFAULT_SEND_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load sender script: {DEFAULT_SEND_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CommandSession:
    def __init__(
        self,
        *,
        port: str,
        baud: int,
        fixed_step_delay: float | None,
        dry_run: bool,
    ) -> None:
        self._port = port
        self._baud = baud
        self._fixed_step_delay = fixed_step_delay
        self._dry_run = dry_run
        self._sender: Any | None = None
        self._serial: Any | None = None
        self.error: str | None = None

        if dry_run:
            return
        try:
            self._sender = _load_sender_module()
            self._serial = self._sender._open_serial(port, baud, 0.1)
            time.sleep(2.0)
            print(f"[STARTUP-SCAN] Opened {port} @ {baud}")
            self._sender._drain_until_quiet(self._serial, 1.0, 8.0)
            self._serial.reset_input_buffer()
        except Exception as exc:
            self.error = str(exc)
            print(f"[STARTUP-SCAN] Serial session failed: {exc}")
            self.close()

    def send(self, label: str, command: str) -> dict[str, Any]:
        record: dict[str, Any] = {
            "label": label,
            "command": command,
            "ok": False,
            "dry_run": self._dry_run,
        }
        if self._dry_run:
            print(f"[STARTUP-SCAN] DRY-RUN command {label}: {command}")
            record["ok"] = True
            return record
        if self.error is not None or self._serial is None or self._sender is None:
            record["error"] = self.error or "serial session is not open"
            print(f"[STARTUP-SCAN] Command {label!r} skipped: {record['error']}")
            return record

        try:
            print(f"[STARTUP-SCAN] TX {label}: {command}")
            self._serial.write(command.encode("ascii"))
            self._serial.flush()
            self._sender._read_until_feedback(self._serial, "", 0.5)
            delay = (
                self._fixed_step_delay
                if self._fixed_step_delay is not None
                else self._sender._command_duration_s(command) + 0.7
            )
            if delay > 0:
                print(f"[STARTUP-SCAN] Waiting {delay:.2f}s after command...")
                time.sleep(delay)
            record["ok"] = True
        except Exception as exc:
            record["error"] = str(exc)
            print(f"[STARTUP-SCAN] Command {label!r} failed: {exc}")
        return record

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None


def _send_single_command(
    *,
    command: str,
    label: str,
    output_dir: Path,
    session: _CommandSession,
) -> dict[str, Any]:
    command_path = _command_file_path(output_dir, label)
    command_path.write_text(command + "\n", encoding="utf-8")

    record = session.send(label, command)
    record["command_path"] = str(command_path)
    return record


def _load_camera_and_vision() -> tuple[Any | None, Any | None, Any | None, str | None]:
    try:
        import cv2
        from vision.bin_scanner import detect_books_in_frame
        from vision.camera import RGBCamera

        return cv2, RGBCamera.instance(), detect_books_in_frame, None
    except Exception as exc:
        return None, None, None, str(exc)


def _capture_frame(
    *,
    cv2_module: Any | None,
    camera: Any | None,
    view: ScanView,
    output_dir: Path,
) -> tuple[Any | None, dict[str, Any]]:
    image_path = output_dir / view.filename
    record: dict[str, Any] = {
        "image_path": str(image_path),
        "ok": False,
    }
    if cv2_module is None or camera is None:
        record["error"] = "camera/vision modules are not available"
        print(f"[STARTUP-SCAN] Capture {view.label!r} skipped: camera unavailable")
        return None, record

    try:
        frame = camera.read_frame()
        if not cv2_module.imwrite(str(image_path), frame):
            raise RuntimeError(f"cv2.imwrite returned False for {image_path}")
        record["ok"] = True
        print(f"[STARTUP-SCAN] Captured {view.label}: {image_path}")
        return frame, record
    except Exception as exc:
        record["error"] = str(exc)
        print(f"[STARTUP-SCAN] Capture {view.label!r} failed: {exc}")
        return None, record


def _process_bin_frame(
    frame: Any | None,
    detect_books_in_frame: Any | None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_view": "center",
        "ok": False,
        "books": [],
    }
    if frame is None:
        record["error"] = "center frame is missing"
        return record
    if detect_books_in_frame is None:
        record["error"] = "detect_books_in_frame is not available"
        return record

    try:
        books = detect_books_in_frame(frame)
        record["books"] = books
        record["book_count"] = len(books)
        record["ok"] = True
        print(f"[STARTUP-SCAN] Bin detection produced {len(books)} book(s).")
    except Exception as exc:
        record["error"] = str(exc)
        print(f"[STARTUP-SCAN] Bin detection failed: {exc}")
    return record


def _section_records(views: dict[str, dict[str, Any]]) -> dict[str, Any]:
    left_image = views.get("left", {}).get("capture", {}).get("image_path")
    right_image = views.get("right", {}).get("capture", {}).get("image_path")
    return {
        "status": "pending_or_partial",
        "note": (
            "Shelf section interpretation is intentionally not forced in v1. "
            "The captured shelf images are preserved for the vision/planning handoff."
        ),
        "sections": {
            "A": {"view": "left", "side": "left", "image_path": left_image},
            "B": {"view": "left", "side": "right", "image_path": left_image},
            "C": {"view": "right", "side": "left", "image_path": right_image},
            "D": {"view": "right", "side": "right", "image_path": right_image},
        },
    }


def _catalog_entries_for_books(books: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    import config

    tasks: list[dict[str, Any]] = []
    unknown_titles: list[str] = []
    seen: set[str] = set()
    for book in books:
        title = str(book.get("title", ""))
        if not title or title in seen:
            continue
        seen.add(title)
        entry = config.KNOWN_BOOK_DIMENSIONS_MM.get(title)
        catalog_zone = None
        catalog_thickness = None
        try:
            from decision.db_manager import DatabaseManager

            db_entry = DatabaseManager().get_catalog_entry(title)
            if db_entry is not None:
                catalog_zone = db_entry.zone
                catalog_thickness = db_entry.thickness
        except Exception:
            pass

        if catalog_zone is None:
            unknown_titles.append(title)
        tasks.append(
            {
                "title": title,
                "target_zone": catalog_zone,
                "thickness_mm": catalog_thickness
                if catalog_thickness is not None
                else (entry or {}).get("thickness"),
                "confidence": book.get("confidence"),
                "pick_point": book.get("pick_point"),
            }
        )
    return tasks, unknown_titles


def _build_user_report(snapshot: dict[str, Any]) -> str:
    books = snapshot.get("bin", {}).get("books", [])
    planned_tasks = snapshot.get("planned_tasks", [])
    unknown_titles = snapshot.get("unknown_titles", [])
    lines = [
        "# Startup Scan Result",
        "",
        f"Status: {snapshot.get('status')}",
        f"Timestamp: {snapshot.get('timestamp')}",
        f"Output directory: {snapshot.get('output_dir')}",
        "",
        "## Detected Books",
    ]
    if books:
        for index, book in enumerate(books, start=1):
            pick = book.get("pick_point") or {}
            lines.append(
                f"{index}. {book.get('title')} "
                f"(confidence={float(book.get('confidence', 0.0)):.3f}, "
                f"rel_x={float(book.get('rel_x', 0.0)):.1f} mm, "
                f"pick=({float(pick.get('x', 0.0)):.1f}, "
                f"{float(pick.get('y', 0.0)):.1f}, {float(pick.get('z', 0.0)):.1f}) mm)"
            )
    else:
        lines.append("No books were detected in the center/bin view.")

    lines.extend(["", "## Planned Catalog Tasks"])
    if planned_tasks:
        for index, task in enumerate(planned_tasks, start=1):
            lines.append(
                f"{index}. {task.get('title')} -> zone={task.get('target_zone')} "
                f"thickness={task.get('thickness_mm')} mm"
            )
    else:
        lines.append("No catalog tasks were created from the detected books.")

    lines.extend(["", "## Unknown Titles"])
    if unknown_titles:
        for title in unknown_titles:
            lines.append(f"- {title}")
    else:
        lines.append("None.")

    lines.extend(["", "## Run Notes"])
    if snapshot.get("errors"):
        for issue in snapshot["errors"]:
            lines.append(f"- {issue}")
    else:
        lines.append("- No blocking issues recorded.")
    lines.append("- This is a demo/user-facing summary, not an external library-system update.")
    return "\n".join(lines) + "\n"


def run_startup_scan(
    *,
    port: str,
    baud: int,
    fixed_step_delay: float | None,
    settle_seconds: float = DEFAULT_SETTLE_SECONDS,
    wait_trigger: str = "space",
    dry_run: bool = False,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    """Run the three-view startup scan and return the snapshot JSON path."""
    output_dir = output_root / _now_stamp()
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / "startup_scan_snapshot.json"

    print(f"[STARTUP-SCAN] Output directory: {output_dir}")
    wait_for_start_trigger(wait_trigger, dry_run=dry_run)

    cv2_module, camera, detect_books_in_frame, import_error = _load_camera_and_vision()
    if import_error is not None:
        print(f"[STARTUP-SCAN] Vision/camera import failed: {import_error}")

    snapshot: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": "partial",
        "output_dir": str(output_dir),
        "settle_seconds": settle_seconds,
        "dry_run": dry_run,
        "views": {},
        "bin": {"ok": False, "books": []},
        "shelf_sections": {},
        "home": {},
        "errors": [],
    }
    if import_error is not None:
        snapshot["errors"].append(f"vision/camera import failed: {import_error}")

    command_session = _CommandSession(
        port=port,
        baud=baud,
        fixed_step_delay=fixed_step_delay,
        dry_run=dry_run,
    )
    center_frame = None
    try:
        for view in SCAN_VIEWS:
            print(
                f"[STARTUP-SCAN] View {view.label}: joint0={view.joint0_deg} deg, "
                f"command={view.command}"
            )
            motion = _send_single_command(
                command=view.command,
                label=f"{view.label}_base",
                output_dir=output_dir,
                session=command_session,
            )
            if settle_seconds > 0:
                print(f"[STARTUP-SCAN] Settling for {settle_seconds:g}s...")
                time.sleep(settle_seconds)

            frame, capture = _capture_frame(
                cv2_module=cv2_module,
                camera=camera,
                view=view,
                output_dir=output_dir,
            )
            if view.label == "center":
                center_frame = frame

            snapshot["views"][view.label] = {
                "joint0_deg": view.joint0_deg,
                "pwm": view.pwm,
                "sections": list(view.sections),
                "description": view.description,
                "motion": motion,
                "capture": capture,
            }
    finally:
        print("[STARTUP-SCAN] Sending home/straight command.")
        home = _send_single_command(
            command=HARDWARE_HOME_COMMAND,
            label="home_straight",
            output_dir=output_dir,
            session=command_session,
        )
        snapshot["home"] = home
        command_session.close()

    snapshot["bin"] = _process_bin_frame(center_frame, detect_books_in_frame)
    snapshot["shelf_sections"] = _section_records(snapshot["views"])
    planned_tasks, unknown_titles = _catalog_entries_for_books(snapshot["bin"].get("books", []))
    snapshot["planned_tasks"] = planned_tasks
    snapshot["unknown_titles"] = unknown_titles

    for view_label, view_record in snapshot["views"].items():
        if not view_record["motion"].get("ok", False):
            snapshot["errors"].append(f"{view_label} motion failed")
        if not view_record["capture"].get("ok", False):
            snapshot["errors"].append(f"{view_label} capture failed")
    if not snapshot["home"].get("ok", False):
        snapshot["errors"].append("home command failed")
    if not snapshot["bin"].get("ok", False):
        snapshot["errors"].append("bin detection failed")
    if snapshot["shelf_sections"].get("status") != "complete":
        snapshot["errors"].append("shelf section interpretation pending_or_partial")

    snapshot["status"] = "complete" if not snapshot["errors"] else "partial"
    report_path = output_dir / "startup_scan_report.md"
    snapshot["user_report_path"] = str(report_path)
    _write_json(snapshot_path, snapshot)
    _write_text(report_path, _build_user_report(snapshot))
    print(f"[STARTUP-SCAN] Snapshot: {snapshot_path}")
    print(f"[STARTUP-SCAN] User report: {report_path}")
    print(f"[STARTUP-SCAN] Status: {snapshot['status']}")
    if snapshot["errors"]:
        print("[STARTUP-SCAN] Issues:")
        for issue in snapshot["errors"]:
            print(f"  - {issue}")

    if camera is not None:
        try:
            camera.release()
        except Exception:
            pass
    return snapshot_path
