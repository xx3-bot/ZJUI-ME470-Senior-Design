"""Minimal two-view grip-and-place test workflow.

This mode is intentionally smaller than the full startup scan / auto flow:
it captures only the -90 deg and 0 deg views, logs OCR output, and generates a
fresh target_sequence for a fixed safe place point.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from startup_scan import (
    ScanView,
    _CommandSession,
    _capture_frame,
    _load_camera_and_vision,
    _now_stamp,
    _process_bin_frame,
    _send_single_command,
    _write_json,
    _write_text,
)
from target_sequence import ROOT, TimingConfig, generate_target_sequence, print_command_preview


DEFAULT_OUTPUT_ROOT = ROOT / "sim_output" / "grip_place_test"
DEFAULT_PICK = (220.0, 0.0, 115.0)
PLACE_POINTS = {
    "left": (-25.0, 250.0, 124.25),
    "center": (0.0, 250.0, 124.25),
    "right": (25.0, 250.0, 124.25),
}

GRIP_PLACE_VIEWS = (
    ScanView(
        label="left",
        filename="left.png",
        joint0_deg=-90,
        pwm=833,
        sections=("shelf_reference",),
        description="-90 deg reference view; saved only, no A/B/C/D interpretation",
    ),
    ScanView(
        label="center",
        filename="center.png",
        joint0_deg=0,
        pwm=1500,
        sections=("bin",),
        description="0 deg bin view for OCR",
    ),
)


def _build_report(snapshot: dict[str, Any]) -> str:
    books = snapshot.get("bin", {}).get("books", [])
    selected_book = snapshot.get("selected_book") or {}
    target = snapshot.get("target_sequence") or {}
    lines = [
        "# Grip and Place Test Result",
        "",
        f"Status: {snapshot.get('status')}",
        f"Timestamp: {snapshot.get('timestamp')}",
        f"Output directory: {snapshot.get('output_dir')}",
        "",
        "## Fixed Test Inputs",
        f"- Pick used for target_sequence: {tuple(snapshot.get('pick_used', []))}",
        f"- Place slot: {snapshot.get('place_slot')}",
        f"- Place used for target_sequence: {tuple(snapshot.get('place_used', []))}",
        "",
        "## Vision Observation",
    ]
    if books:
        for index, book in enumerate(books, start=1):
            pick = book.get("pick_point") or {}
            lines.append(
                f"{index}. {book.get('title')} "
                f"(confidence={float(book.get('confidence', 0.0)):.3f}, "
                f"pick=({float(pick.get('x', 0.0)):.1f}, "
                f"{float(pick.get('y', 0.0)):.1f}, {float(pick.get('z', 0.0)):.1f}) mm)"
            )
    else:
        lines.append("No book OCR result was available.")

    lines.extend(
        [
            "",
            "## Selected Book",
            (
                f"- {selected_book.get('title')} logged from OCR."
                if selected_book
                else "- None. The test still generated the fixed pick/place sequence."
            ),
            "",
            "## Target Sequence",
        ]
    )
    if target.get("ok"):
        lines.extend(
            [
                f"- Trajectory: {target.get('trajectory_path')}",
                f"- Commands: {target.get('command_path')}",
                f"- Summary: {target.get('summary_path')}",
                f"- Command count: {target.get('command_count')}",
            ]
        )
    else:
        lines.append(f"- Failed: {target.get('error')}")

    lines.extend(["", "## Run Notes"])
    if snapshot.get("errors"):
        for issue in snapshot["errors"]:
            lines.append(f"- {issue}")
    else:
        lines.append("- No blocking issues recorded.")
    lines.append("- v1 logs OCR pick_point but does not use it to drive the arm.")
    lines.append("- v1 does not run +90 deg scan or ABCD shelf interpretation.")
    return "\n".join(lines) + "\n"


def run_grip_place_test(
    *,
    port: str,
    baud: int,
    fixed_step_delay: float | None,
    settle_seconds: float,
    wait_trigger: str,
    dry_run: bool = True,
    place_slot: str = "center",
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    timing: TimingConfig | None = None,
) -> Path:
    """Run the minimal two-view grip/place test and return the snapshot path."""
    if place_slot not in PLACE_POINTS:
        raise ValueError(f"Unknown grip/place slot {place_slot!r}; expected one of {sorted(PLACE_POINTS)}")

    output_dir = output_root / _now_stamp()
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / "grip_place_test_snapshot.json"
    report_path = output_dir / "grip_place_test_report.md"

    print(f"[GRIP-PLACE] Output directory: {output_dir}")
    print("[GRIP-PLACE] v1 uses fixed pick/place for target_sequence; OCR is logged only.")
    from target_sequence import wait_for_start_trigger

    wait_for_start_trigger(wait_trigger, dry_run=dry_run)

    cv2_module, camera, detect_books_in_frame, import_error = _load_camera_and_vision()
    if import_error is not None:
        print(f"[GRIP-PLACE] Vision/camera import failed: {import_error}")

    snapshot: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": "partial",
        "output_dir": str(output_dir),
        "settle_seconds": settle_seconds,
        "dry_run": dry_run,
        "place_slot": place_slot,
        "pick_used": list(DEFAULT_PICK),
        "place_used": list(PLACE_POINTS[place_slot]),
        "views": {},
        "bin": {"ok": False, "books": []},
        "selected_book": None,
        "target_sequence": {"ok": False},
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
        for view in GRIP_PLACE_VIEWS:
            print(
                f"[GRIP-PLACE] View {view.label}: joint0={view.joint0_deg} deg, "
                f"command={view.command}"
            )
            motion = _send_single_command(
                command=view.command,
                label=f"{view.label}_base",
                output_dir=output_dir,
                session=command_session,
            )
            if settle_seconds > 0:
                print(f"[GRIP-PLACE] Settling for {settle_seconds:g}s...")
                import time

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
        command_session.close()

    snapshot["bin"] = _process_bin_frame(center_frame, detect_books_in_frame)
    books = snapshot["bin"].get("books", [])
    if books:
        snapshot["selected_book"] = books[0]

    try:
        result = generate_target_sequence(
            pick=DEFAULT_PICK,
            place=PLACE_POINTS[place_slot],
            timing=timing,
            trajectory_path=output_dir / "control_trajectory.csv",
            command_path=output_dir / "hardware_command_sequence.txt",
            summary_path=output_dir / "TARGET_SEQUENCE_SUMMARY.md",
        )
        snapshot["target_sequence"] = {
            "ok": True,
            "trajectory_path": str(result.trajectory_path),
            "command_path": str(result.command_path),
            "summary_path": str(result.summary_path),
            "command_count": len(result.commands),
        }
        print_command_preview(result)
    except Exception as exc:
        snapshot["target_sequence"] = {"ok": False, "error": str(exc)}
        snapshot["errors"].append(f"target_sequence failed: {exc}")
        print(f"[GRIP-PLACE] target_sequence failed: {exc}")

    for view_label, view_record in snapshot["views"].items():
        if not view_record["motion"].get("ok", False):
            snapshot["errors"].append(f"{view_label} motion failed")
        if not view_record["capture"].get("ok", False):
            snapshot["errors"].append(f"{view_label} capture failed")
    if not snapshot["bin"].get("ok", False):
        snapshot["errors"].append("bin detection failed")
    if not snapshot["target_sequence"].get("ok", False):
        snapshot["errors"].append("target sequence generation failed")

    snapshot["status"] = "complete" if not snapshot["errors"] else "partial"
    snapshot["user_report_path"] = str(report_path)
    _write_json(snapshot_path, snapshot)
    _write_text(report_path, _build_report(snapshot))

    print(f"[GRIP-PLACE] Snapshot: {snapshot_path}")
    print(f"[GRIP-PLACE] User report: {report_path}")
    print(f"[GRIP-PLACE] Status: {snapshot['status']}")
    if snapshot["errors"]:
        print("[GRIP-PLACE] Issues:")
        for issue in snapshot["errors"]:
            print(f"  - {issue}")

    if camera is not None:
        try:
            camera.release()
        except Exception:
            pass
    return snapshot_path
