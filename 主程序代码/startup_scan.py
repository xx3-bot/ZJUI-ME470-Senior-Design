"""Two-view startup scan workflow for world-model perception handoff.

Current standard startup scan:

1. Capture the front/bin view at 0 deg and start bin analysis in the background.
2. Rotate base left and capture the shelf/world-context view while bin analysis runs.
3. Return to measured home/straight.
4. Collect the bin/shelf analysis futures and build a conservative world snapshot.

This workflow does not execute pick/place hardware. It prepares perception and
task-planning data for inspection before the later Auto execution step.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
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
        label="center",
        filename="center.png",
        joint0_deg=0,
        pwm=1500,
        sections=("bin",),
        description="0 deg bin view",
    ),
    ScanView(
        label="left",
        filename="left.png",
        joint0_deg=-87,
        pwm=2144,
        sections=("shelf",),
        description="left shelf/world-context view with slight yaw correction",
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


def _load_camera_and_vision() -> tuple[Any | None, Any | None, dict[str, Any], str | None]:
    try:
        import cv2
        from vision.bin_scanner import detect_books_in_frame
        from vision.bin_slot_scanner import (
            detect_book_instances_in_frame,
            draw_bin_grid_geometry,
            draw_book_instances,
            estimate_bin_grid_geometry,
        )
        from vision.camera import RGBCamera
        from vision.lateral_pose_provider import scan_book_pick_poses_with_unknowns_from_frame
        from vision.shelf_scanner import (
            detect_shelf_sections,
            draw_shelf_scan_overlay,
            estimate_shelf_place_candidates,
        )

        return cv2, RGBCamera.instance(), {
            "detect_books_in_frame": detect_books_in_frame,
            "detect_book_instances_in_frame": detect_book_instances_in_frame,
            "draw_book_instances": draw_book_instances,
            "estimate_bin_grid_geometry": estimate_bin_grid_geometry,
            "draw_bin_grid_geometry": draw_bin_grid_geometry,
            "scan_book_pick_poses_with_unknowns_from_frame": scan_book_pick_poses_with_unknowns_from_frame,
            "detect_shelf_sections": detect_shelf_sections,
            "draw_shelf_scan_overlay": draw_shelf_scan_overlay,
            "estimate_shelf_place_candidates": estimate_shelf_place_candidates,
        }, None
    except Exception as exc:
        return None, None, {}, str(exc)


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


def _preflight_camera_access(
    *,
    camera: Any | None,
    import_error: str | None,
) -> str | None:
    """Verify camera access before moving hardware for a scan."""
    if import_error is not None:
        return f"vision/camera import failed: {import_error}"
    if camera is None:
        return "camera is not available"
    try:
        camera.read_frame()
    except Exception as exc:
        return f"camera preflight failed: {exc}"
    return None


def _future_result_or_error(
    future: Future[dict[str, Any]] | None,
    fallback: dict[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    if future is None:
        return fallback
    try:
        return future.result()
    except Exception as exc:  # noqa: BLE001 - keep startup snapshot usable.
        record = dict(fallback)
        record["error"] = str(exc)
        print(f"[STARTUP-SCAN] {label} analysis failed: {exc}")
        return record


def _process_bin_frame(
    frame: Any | None,
    vision_modules: dict[str, Any],
    cv2_module: Any | None,
    output_dir: Path,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_view": "center",
        "ok": False,
        "books": [],
        "book_instances": [],
        "pick_candidates": [],
        "unknown_texts": [],
    }
    if frame is None:
        record["error"] = "center frame is missing"
        return record
    detect_books_in_frame = vision_modules.get("detect_books_in_frame")
    if detect_books_in_frame is None:
        record["error"] = "detect_books_in_frame is not available"
        return record

    try:
        books = detect_books_in_frame(frame)
        record["books"] = books
        record["book_count"] = len(books)

        detect_instances = vision_modules.get("detect_book_instances_in_frame")
        if detect_instances is not None:
            record["book_instances"] = detect_instances(frame)
            draw_instances = vision_modules.get("draw_book_instances")
            if cv2_module is not None and draw_instances is not None:
                overlay = draw_instances(frame, record["book_instances"])
                overlay_path = output_dir / "center_book_instances_overlay.png"
                if cv2_module.imwrite(str(overlay_path), overlay):
                    record["book_instances_overlay_path"] = str(overlay_path)
                    print(f"[STARTUP-SCAN] Book/entity overlay: {overlay_path}")

        scan_picks = vision_modules.get("scan_book_pick_poses_with_unknowns_from_frame")
        if scan_picks is not None:
            pick_result = scan_picks(frame)
            record["pick_candidates"] = list(pick_result.get("candidates", []))
            record["unknown_texts"] = list(pick_result.get("unknown_texts", []))

        estimate_grid = vision_modules.get("estimate_bin_grid_geometry")
        if estimate_grid is not None:
            grid = estimate_grid(frame)
            record["bin_grid_geometry"] = grid
            draw_grid = vision_modules.get("draw_bin_grid_geometry")
            if cv2_module is not None and draw_grid is not None:
                overlay = draw_grid(frame, grid)
                overlay_path = output_dir / "center_bin_grid_overlay.png"
                if cv2_module.imwrite(str(overlay_path), overlay):
                    record["bin_grid_overlay_path"] = str(overlay_path)
                    print(f"[STARTUP-SCAN] Bin grid/depth overlay: {overlay_path}")

        record["ok"] = bool(record["books"] or record["book_instances"] or record["pick_candidates"])
        print(
            f"[STARTUP-SCAN] Bin detection produced books={len(record['books'])}, "
            f"instances={len(record['book_instances'])}, "
            f"pick_candidates={len(record['pick_candidates'])}, "
            f"grid_depth={record.get('bin_grid_geometry', {}).get('arm_depth_mm')}."
        )
    except Exception as exc:
        record["error"] = str(exc)
        print(f"[STARTUP-SCAN] Bin detection failed: {exc}")
    return record


def _process_shelf_frame(
    frame: Any | None,
    vision_modules: dict[str, Any],
    cv2_module: Any | None,
    output_dir: Path,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_view": "left",
        "ok": False,
        "sections": [],
        "ranked_candidates": [],
    }
    if frame is None:
        record["error"] = "left frame is missing"
        return record

    estimator = vision_modules.get("estimate_shelf_place_candidates")
    if estimator is None:
        record["error"] = "estimate_shelf_place_candidates is not available"
        return record

    try:
        shelf = estimator(frame)
        record.update(shelf)
        record["ok"] = shelf.get("status") == "complete"
        detect_sections = vision_modules.get("detect_shelf_sections")
        draw_overlay = vision_modules.get("draw_shelf_scan_overlay")
        if cv2_module is not None and detect_sections is not None and draw_overlay is not None:
            sections = detect_sections(frame)
            overlay = draw_overlay(frame, sections)
            overlay_path = output_dir / "left_shelf_overlay.png"
            if cv2_module.imwrite(str(overlay_path), overlay):
                record["overlay_path"] = str(overlay_path)
                print(f"[STARTUP-SCAN] Shelf calibrated overlay: {overlay_path}")
        print(
            f"[STARTUP-SCAN] Shelf scan status={record.get('status')} "
            f"candidates={len(record.get('ranked_candidates', []))}."
        )
    except Exception as exc:
        record["error"] = str(exc)
        print(f"[STARTUP-SCAN] Shelf scan failed: {exc}")
    return record


def _section_world_x_offset(section_id: str) -> float:
    """Temporary demo shelf frame: two same-width shelves centered around X=0."""
    import config

    pitch = config.DEMO_SHELF_SECTION_WIDTH_MM + config.DEMO_SHELF_SECTION_GAP_MM
    if section_id == "left":
        return -pitch / 2.0
    if section_id == "right":
        return pitch / 2.0
    return 0.0


def _edge_safe_place_x(
    *,
    section_origin_x: float,
    centered_x: float,
    support_side: str,
) -> tuple[float, float]:
    """Shift wall-supported edge slots slightly inward for real placement.

    The planner still prefers edge slots as leaning supports, but the hardware
    target should be safely inside the plastic shelf rather than exactly at the
    outer slice center. This protects against small shelf-origin/calibration
    errors that otherwise put a book just outside the physical wall.
    """
    import config

    inset = float(getattr(config, "DEMO_SHELF_EDGE_PLACE_INSET_MM", 0.0))
    adjustment = 0.0
    if support_side == "left_wall":
        adjustment = inset
    elif support_side == "right_wall":
        adjustment = -inset
    return section_origin_x + centered_x + adjustment, adjustment


def _build_initialized_shelf_world_model(shelf_record: dict[str, Any]) -> dict[str, Any]:
    """Freeze startup shelf slices into the simple A-route world model.

    This does not claim full live shelf localization. It turns the first clean
    scan into deterministic shelf slots; later loops should update occupancy in
    WorldModel instead of recalculating every place point from fresh shelf vision.
    """
    import config

    slots: list[dict[str, Any]] = []
    sections_out: list[dict[str, Any]] = []
    section_labels = {"left": "A", "right": "B"}
    for section in shelf_record.get("sections", []):
        section_id = str(section.get("id") or section.get("section_id") or "")
        section_origin_x = _section_world_x_offset(section_id)
        section_entry = {
            "section_id": section_id,
            "section_label": section_labels.get(section_id, section_id or "unknown"),
            "bbox_px": section.get("bbox_px"),
            "quad_px": section.get("quad_px"),
            "camera_depth_mm": section.get("camera_depth_mm"),
            "world_x_offset_mm": round(section_origin_x, 2),
            "slice_ids": [],
        }
        for shelf_slice in section.get("slices", []):
            slice_index = int(shelf_slice.get("index", 0))
            centered_x = float(shelf_slice.get("center_x_mm_centered", 0.0))
            support_side = str(shelf_slice.get("support_side", "none"))
            place_x, edge_inset = _edge_safe_place_x(
                section_origin_x=section_origin_x,
                centered_x=centered_x,
                support_side=support_side,
            )
            place = (
                place_x,
                float(config.DEMO_SHELF_PLACE_Y_MM),
                float(config.DEMO_SHELF_PLACE_Z_MM),
            )
            slot_id = f"{section_id}:{slice_index}"
            section_entry["slice_ids"].append(slot_id)
            slots.append(
                {
                    "slot_id": slot_id,
                    "section_id": section_id,
                    "section_label": section_entry["section_label"],
                    "slice_index": slice_index,
                    "place": [round(float(value), 2) for value in place],
                    "raw_place_x_mm": round(float(section_origin_x + centered_x), 2),
                    "edge_inset_mm": round(float(edge_inset), 2),
                    "status": shelf_slice.get("status", "unknown"),
                    "score": float(shelf_slice.get("score", 0.0)),
                    "support_side": support_side,
                    "placement_hint": shelf_slice.get("placement_hint", "center"),
                    "occupancy_score": shelf_slice.get("occupancy_score"),
                    "center_px": shelf_slice.get("center_px"),
                    "quad_px": shelf_slice.get("quad_px"),
                    "occupied": False,
                    "source": "startup_scan_initialized_shelf",
                }
            )
        sections_out.append(section_entry)

    slots.sort(
        key=lambda slot: (
            -float(slot.get("score", 0.0)),
            str(slot.get("section_id", "")),
            int(slot.get("slice_index", 9999)),
        )
    )
    for rank, slot in enumerate(slots, start=1):
        slot["rank"] = rank

    return {
        "source": "startup_scan_left_view",
        "strategy": "A_initialize_once_then_update_world_model",
        "coordinate_note": (
            "Temporary demo arm-frame placement model: X comes from initialized shelf slice; "
            "Y/Z are fixed demo safety values from config."
        ),
        "place_y_mm": float(config.DEMO_SHELF_PLACE_Y_MM),
        "place_z_mm": float(config.DEMO_SHELF_PLACE_Z_MM),
        "section_width_mm": float(config.DEMO_SHELF_SECTION_WIDTH_MM),
        "section_gap_mm": float(config.DEMO_SHELF_SECTION_GAP_MM),
        "sections": sections_out,
        "slots": slots,
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


def _build_task_queue(
    bin_record: dict[str, Any],
    shelf_record: dict[str, Any],
    shelf_world_model: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    import config

    instances_by_title = {
        str(item.get("title")): item for item in bin_record.get("book_instances", [])
    }
    shelf_candidates = list((shelf_world_model or {}).get("slots", []))
    if not shelf_candidates:
        shelf_candidates = list(shelf_record.get("ranked_candidates", []))
    pick_candidates = list(bin_record.get("pick_candidates", []))
    title_order = {title: index for index, title in enumerate(config.KNOWN_BOOK_TITLES)}
    pick_candidates.sort(
        key=lambda item: (
            title_order.get(str(item.get("title")), len(title_order)),
            -float(item.get("confidence", 0.0)),
        )
    )

    tasks: list[dict[str, Any]] = []
    for index, pick in enumerate(pick_candidates):
        title = str(pick.get("title", "<unknown>"))
        instance = instances_by_title.get(title, {})
        shelf_candidate = shelf_candidates[index % len(shelf_candidates)] if shelf_candidates else None
        tasks.append(
            {
                "index": index + 1,
                "title": title,
                "confidence": float(pick.get("confidence", 0.0)),
                "pick": pick.get("pick"),
                "pick_source": "center_view_lateral_pose_provider",
                "entity_bbox": instance.get("entity_bbox"),
                "raw_entity_bbox": instance.get("raw_entity_bbox"),
                "ocr_bbox": instance.get("ocr_bbox", pick.get("bbox")),
                "tilt_deg": pick.get("tilt_deg", instance.get("ocr_tilt_deg")),
                "book_dimensions_mm": pick.get(
                    "book_dimensions_mm",
                    instance.get("book_dimensions_mm", config.get_book_dimensions_mm(title)),
                ),
                "shelf_candidate": shelf_candidate,
                "place": None if shelf_candidate is None else shelf_candidate.get("place"),
                "place_status": (
                    "candidate_from_initialized_shelf_world_model"
                    if shelf_candidate is not None
                    else "pending_no_shelf_candidate"
                ),
                "execution_status": "planned_only_not_sent",
            }
        )
    return tasks


def _build_user_report(snapshot: dict[str, Any]) -> str:
    books = snapshot.get("bin", {}).get("books", [])
    book_instances = snapshot.get("bin", {}).get("book_instances", [])
    pick_candidates = snapshot.get("bin", {}).get("pick_candidates", [])
    picks_by_title = {
        str(item.get("title")): item
        for item in pick_candidates
        if item.get("title") is not None
    }
    shelf_candidates = snapshot.get("shelf", {}).get("ranked_candidates", [])
    shelf_world_slots = snapshot.get("shelf_world_model", {}).get("slots", [])
    task_queue = snapshot.get("task_queue", [])
    planned_tasks = snapshot.get("planned_tasks", [])
    unknown_titles = snapshot.get("unknown_titles", [])
    lines = [
        "# Startup Scan Result",
        "",
        f"Status: {snapshot.get('status')}",
        f"Timestamp: {snapshot.get('timestamp')}",
        f"Output directory: {snapshot.get('output_dir')}",
        "",
        "## Captured Views",
        "- Left view: base -90 deg, shelf/world context.",
        "- Center view: base 0 deg, bin/books.",
        "",
        "## Detected Books",
    ]
    if books or pick_candidates:
        detected_rows = books or pick_candidates
        for index, book in enumerate(detected_rows, start=1):
            title = str(book.get("title", "<unknown>"))
            pick_candidate = picks_by_title.get(title, book)
            pick = pick_candidate.get("pick") or []
            pick_text = "pending"
            if len(pick) >= 3:
                pick_text = f"({float(pick[0]):.1f}, {float(pick[1]):.1f}, {float(pick[2]):.1f})"
            lines.append(
                f"{index}. {title} "
                f"(confidence={float(book.get('confidence', 0.0)):.3f}, "
                f"pick={pick_text} mm, "
                f"source={pick_candidate.get('source', 'vision_pending')})"
            )
    else:
        lines.append("No books were detected in the center/bin view.")

    lines.extend(["", "## World Snapshot"])
    lines.append(f"- Book entities linked to OCR: {len(book_instances)}")
    lines.append(f"- Pick candidates: {len(pick_candidates)}")
    lines.append(f"- Shelf placement candidates: {len(shelf_candidates)}")
    lines.append(f"- Initialized shelf world slots: {len(shelf_world_slots)}")
    grid = snapshot.get("bin", {}).get("bin_grid_geometry") or {}
    if grid:
        lines.append(
            f"- Bin grid depth estimate: arm X={grid.get('arm_depth_mm')} mm "
            f"(camera depth={grid.get('camera_depth_mm')} mm); "
            f"overlay={snapshot.get('bin', {}).get('bin_grid_overlay_path')}"
        )

    lines.extend(["", "## Task Queue"])
    if task_queue:
        for task in task_queue:
            shelf = task.get("shelf_candidate") or {}
            hint = shelf.get("placement_hint", "pending")
            support = shelf.get("support_side", "unknown")
            slot = shelf.get("slot_id") or f"{shelf.get('section_id', '?')}:{shelf.get('slice_index', '?')}"
            lines.append(
                f"{task['index']}. {task.get('title')}: pick candidate ready; "
                f"shelf slot={slot}, hint={hint}, support={support}; not sent to hardware."
            )
    else:
        lines.append("No task queue was created.")

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
    lines.append("- Startup scan initializes the world snapshot; it does not execute pick/place hardware.")
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
    """Run the two-view startup scan and return the snapshot JSON path."""
    output_dir = output_root / _now_stamp()
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / "startup_scan_snapshot.json"

    print(f"[STARTUP-SCAN] Output directory: {output_dir}")
    wait_for_start_trigger(wait_trigger, dry_run=dry_run)

    cv2_module, camera, vision_modules, import_error = _load_camera_and_vision()
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
        "shelf": {"ok": False, "sections": [], "ranked_candidates": []},
        "shelf_world_model": {"source": "not_initialized", "slots": []},
        "home": {},
        "errors": [],
    }
    if import_error is not None:
        snapshot["errors"].append(f"vision/camera import failed: {import_error}")

    camera_preflight_error = _preflight_camera_access(camera=camera, import_error=import_error)
    if camera_preflight_error is not None:
        snapshot["errors"].append(camera_preflight_error)
        snapshot["status"] = "partial"
        report_path = output_dir / "startup_scan_report.md"
        snapshot["user_report_path"] = str(report_path)
        _write_json(snapshot_path, snapshot)
        _write_text(report_path, _build_user_report(snapshot))
        print(f"[STARTUP-SCAN] Camera preflight failed before hardware motion: {camera_preflight_error}")
        print(f"[STARTUP-SCAN] Snapshot: {snapshot_path}")
        print(f"[STARTUP-SCAN] User report: {report_path}")
        if camera is not None:
            try:
                camera.release()
            except Exception:
                pass
        return snapshot_path

    command_session = _CommandSession(
        port=port,
        baud=baud,
        fixed_step_delay=fixed_step_delay,
        dry_run=dry_run,
    )
    analysis_futures: dict[str, Future[dict[str, Any]]] = {}
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="startup_scan")
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
            if capture.get("ok"):
                if view.label == "center":
                    print("[STARTUP-SCAN] Submitting bin analysis while scan continues.")
                    analysis_futures["bin"] = executor.submit(
                        _process_bin_frame,
                        frame,
                        vision_modules,
                        cv2_module,
                        output_dir,
                    )
                elif view.label == "left":
                    print("[STARTUP-SCAN] Submitting shelf analysis.")
                    analysis_futures["shelf"] = executor.submit(
                        _process_shelf_frame,
                        frame,
                        vision_modules,
                        cv2_module,
                        output_dir,
                    )

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

    print("[STARTUP-SCAN] Waiting for background vision analysis...")
    snapshot["bin"] = _future_result_or_error(
        analysis_futures.get("bin"),
        {
            "source_view": "center",
            "ok": False,
            "books": [],
            "book_instances": [],
            "pick_candidates": [],
            "unknown_texts": [],
            "error": "center analysis was not started",
        },
        label="Bin",
    )
    snapshot["shelf"] = _future_result_or_error(
        analysis_futures.get("shelf"),
        {
            "source_view": "left",
            "ok": False,
            "sections": [],
            "ranked_candidates": [],
            "error": "shelf analysis was not started",
        },
        label="Shelf",
    )
    executor.shutdown(wait=True)
    snapshot["shelf_world_model"] = _build_initialized_shelf_world_model(snapshot["shelf"])
    planned_tasks, unknown_titles = _catalog_entries_for_books(snapshot["bin"].get("books", []))
    snapshot["planned_tasks"] = planned_tasks
    snapshot["unknown_titles"] = unknown_titles
    snapshot["task_queue"] = _build_task_queue(
        snapshot["bin"],
        snapshot["shelf"],
        snapshot["shelf_world_model"],
    )

    for view_label, view_record in snapshot["views"].items():
        if not view_record["motion"].get("ok", False):
            snapshot["errors"].append(f"{view_label} motion failed")
        if not view_record["capture"].get("ok", False):
            snapshot["errors"].append(f"{view_label} capture failed")
    if not snapshot["home"].get("ok", False):
        snapshot["errors"].append("home command failed")
    if not snapshot["bin"].get("ok", False):
        snapshot["errors"].append("bin detection failed")
    if not snapshot["shelf"].get("ok", False):
        snapshot["errors"].append("shelf scan incomplete")

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
