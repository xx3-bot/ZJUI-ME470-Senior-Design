"""Detected-books demo workflow.

This module keeps the current practical demo path close to the future Auto
shape: vision produces bin books, a small placement model acts as the temporary
decision provider, world_model records runtime state, and target_sequence stays
the only hardware command generator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import config
from models import Pose
from target_sequence import (
    HARDWARE_HOME_COMMAND,
    ROOT,
    TimingConfig,
    generate_target_sequence,
    print_command_preview,
    preflight_hardware_sender,
    send_hardware_sequence,
    wait_for_start_trigger,
    write_command_file,
)
from vision.lateral_pose_provider import scan_book_pick_poses_with_unknowns_from_camera
from world_model import WorldModel


DEFAULT_OUTPUT_ROOT = ROOT / "sim_output" / "detected_books_loop"
CURRENT_SEQUENCE_ROOT = ROOT / "sim_output" / "current_detected_book_sequence"


@dataclass(frozen=True)
class DemoShelfPlacementModel:
    """Temporary shelf-placement provider for the current demo area."""

    start_place: tuple[float, float, float] | None
    step_x_mm: float
    initialized_slots: tuple[dict[str, Any], ...] = ()
    source: str = "fixed_demo_shelf_model"

    def placement_for_index(self, index_zero_based: int) -> tuple[tuple[float, float, float], dict[str, Any] | None]:
        if self.initialized_slots:
            if index_zero_based < 0 or index_zero_based >= len(self.initialized_slots):
                raise RuntimeError("initialized shelf model has no free slot for this book")
            slot = dict(self.initialized_slots[index_zero_based])
            place = tuple(float(value) for value in slot["place"])
            return place, slot
        if self.start_place is None:
            raise RuntimeError("no shelf placement model is available")
        return (
            float(self.start_place[0]) + index_zero_based * float(self.step_x_mm),
            float(self.start_place[1]),
            float(self.start_place[2]),
        ), None

    def place_for_index(self, index_zero_based: int) -> tuple[float, float, float]:
        place, _ = self.placement_for_index(index_zero_based)
        return place


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def latest_startup_scan_snapshot() -> Path | None:
    startup_root = ROOT / "sim_output" / "startup_scan"
    snapshots = sorted(startup_root.glob("*/startup_scan_snapshot.json"), reverse=True)
    return snapshots[0] if snapshots else None


def _load_initialized_shelf_slots(snapshot_path: Path | None) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    if snapshot_path is None:
        return {}, ()
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[LOOP] Could not load shelf snapshot {snapshot_path}: {exc}")
        return {}, ()

    model = dict(snapshot.get("shelf_world_model") or {})
    if not model.get("slots") and snapshot.get("shelf"):
        print(
            f"[LOOP] Snapshot {snapshot_path} does not contain shelf_world_model; "
            "rerun --startup-scan once so Auto demo can use the initialized shelf model."
        )
    slots = [
        dict(slot)
        for slot in model.get("slots", [])
        if str(slot.get("status", "free_candidate")) in {"free_candidate", "unknown"}
        and not bool(slot.get("occupied"))
        and slot.get("place") is not None
    ]
    slots.sort(
        key=lambda slot: (
            -float(slot.get("score", 0.0)),
            int(slot.get("rank", 9999)),
            str(slot.get("section_id", "")),
            int(slot.get("slice_index", 9999)),
        )
    )
    if slots:
        model["loaded_from"] = str(snapshot_path)
    return model, tuple(slots)


def _load_startup_bin_scan(snapshot_path: Path | None) -> dict[str, Any]:
    """Reuse bin perception from the startup scan for one coherent Auto run."""
    if snapshot_path is None:
        return {}
    try:
        snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - live camera fallback is acceptable here.
        print(f"[LOOP] Could not load startup bin snapshot {snapshot_path}: {exc}")
        return {}

    bin_result = dict(snapshot.get("bin") or {})
    candidates = list(bin_result.get("pick_candidates") or [])
    if not candidates:
        return {}

    return {
        "source": "startup_scan_snapshot",
        "snapshot_path": str(snapshot_path),
        "candidates": candidates,
        "unknown_texts": list(bin_result.get("unknown_texts") or []),
        "camera_error": None,
    }


def _build_loop_report(snapshot: dict[str, Any]) -> str:
    tasks = snapshot.get("tasks", [])
    skipped = snapshot.get("skipped_tasks", [])
    unknown_texts = snapshot.get("unknown_texts", [])
    lines = [
        "# Auto Demo Result",
        "",
        f"Run status: {snapshot.get('status')}",
        f"Mode: {snapshot.get('mode')}",
        f"Books planned: {len(tasks)}",
        f"Books needing attention: {len(skipped) + len(unknown_texts)}",
        f"Dry run: {snapshot.get('dry_run')}",
        "",
        "## What The Robot Plans To Do",
    ]
    if not tasks:
        lines.append("No known catalog books were ready for robot handling.")
    for task in tasks:
        human_pick = task.get("human_pick", "detected in bin")
        human_place = task.get("human_place", "demo shelf position")
        tilt_text = _human_tilt_description(task.get("tilt_deg"))
        lines.append(
            f"{task['index']}. Move **{task['title']}** from {human_pick} "
            f"to {human_place}. {tilt_text} Confidence {task['confidence']:.2f}."
        )

    lines.extend(["", "## Needs Human Attention"])
    if not skipped and not unknown_texts and not snapshot.get("errors"):
        lines.append("None.")
    for item in unknown_texts:
        lines.append(
            f"- OCR saw `{item.get('text')}` but it is not in the known-book list; "
            "leave it for manual handling or add it to the catalog."
        )
    for task in skipped:
        lines.append(f"- {task.get('title', '<unknown>')}: {task.get('reason')}")
    for error in snapshot.get("errors", []):
        lines.append(f"- {error}")

    lines.extend(["", "## Technical Files"])
    lines.append(f"- Output directory: {snapshot.get('output_dir')}")
    lines.append(f"- Combined command file: {snapshot.get('combined_command_path')}")
    lines.append(f"- Combined command count: {snapshot.get('combined_command_count')}")
    for path in snapshot.get("visual_plan_paths", []):
        lines.append(f"- Visual plan overlay: {path}")

    lines.extend(["", "## World Model Summary"])
    world = snapshot.get("world_model", {})
    lines.append(f"- Detected bin books: {world.get('bin_books', [])}")
    lines.append(f"- Planned shelf positions: {world.get('planned_placements_human', [])}")
    lines.append(f"- Occupied demo shelf slots: {world.get('occupied_demo_shelf_slots', [])}")

    lines.extend(["", "## Notes"])
    for note in snapshot.get("notes", []):
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def _print_report(title: str, report: str) -> None:
    print()
    print(f"===== {title} =====")
    print(report.rstrip())
    print(f"===== end {title} =====")
    print()


def _draw_label(cv2_module: Any, image: Any, text: str, origin: tuple[int, int], color: tuple[int, int, int]) -> None:
    x, y = origin
    cv2_module.putText(
        image,
        text,
        (x, y),
        cv2_module.FONT_HERSHEY_SIMPLEX,
        0.72,
        (0, 0, 0),
        5,
        cv2_module.LINE_AA,
    )
    cv2_module.putText(
        image,
        text,
        (x, y),
        cv2_module.FONT_HERSHEY_SIMPLEX,
        0.72,
        color,
        2,
        cv2_module.LINE_AA,
    )


def _write_plan_overlays(snapshot: dict[str, Any], output_dir: Path) -> list[str]:
    """Write user-facing overlays for pick order and shelf placement order."""
    try:
        import cv2
        import numpy as np
    except Exception as exc:  # noqa: BLE001 - overlays are non-blocking.
        print(f"[LOOP] Visual plan overlay unavailable: {exc}")
        return []

    startup_snapshot_path = snapshot.get("shelf_model_snapshot")
    if not startup_snapshot_path:
        return []
    try:
        startup_snapshot = json.loads(Path(str(startup_snapshot_path)).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - overlays are non-blocking.
        print(f"[LOOP] Visual plan overlay could not read startup snapshot: {exc}")
        return []

    views = startup_snapshot.get("views") or {}
    center_path = views.get("center", {}).get("capture", {}).get("image_path")
    left_path = views.get("left", {}).get("capture", {}).get("image_path")
    tasks = list(snapshot.get("tasks", []))
    written: list[str] = []

    if center_path:
        image = cv2.imread(str(center_path))
        if image is not None:
            for task in tasks:
                index = int(task.get("index", 0))
                bbox = task.get("bbox") or []
                if len(bbox) < 4:
                    continue
                x, y, w, h = [int(round(float(value))) for value in bbox[:4]]
                cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 255), 3)
                cv2.circle(image, (x + w // 2, y + h // 2), 7, (0, 255, 255), -1)
                _draw_label(cv2, image, f"#{index} PICK", (max(8, x), max(28, y - 10)), (0, 255, 255))
            path = output_dir / "bin_plan_overlay.png"
            if cv2.imwrite(str(path), image):
                written.append(str(path))

    if left_path:
        image = cv2.imread(str(left_path))
        if image is not None:
            for task in tasks:
                index = int(task.get("index", 0))
                shelf_slot = task.get("shelf_slot") or {}
                quad = shelf_slot.get("quad_px") or []
                if len(quad) != 4:
                    continue
                points = np.array(quad, dtype=np.int32)
                cv2.polylines(image, [points], True, (255, 0, 255), 4, cv2.LINE_AA)
                center = points.mean(axis=0).astype(int)
                cv2.circle(image, tuple(center), 8, (255, 0, 255), -1, cv2.LINE_AA)
                _draw_label(
                    cv2,
                    image,
                    f"#{index} PLACE",
                    (max(8, int(center[0]) - 55), max(28, int(center[1]) - 16)),
                    (255, 0, 255),
                )
            path = output_dir / "shelf_plan_overlay.png"
            if cv2.imwrite(str(path), image):
                written.append(str(path))

    if written:
        print("[LOOP] Visual plan overlays:")
        for path in written:
            print(f"  - {path}")
    return written


def _open_visual_plan_paths(paths: list[str]) -> None:
    if not paths or sys.platform != "darwin":
        return
    for path in paths:
        try:
            subprocess.run(["open", path], check=False)
        except Exception as exc:  # noqa: BLE001 - preview must not fail the run.
            print(f"[LOOP] Could not open visual overlay {path}: {exc}")


def _print_execution_plan(snapshot: dict[str, Any]) -> None:
    print()
    print("===== ME470 Auto Demo Screen =====")
    print(f"Status: {snapshot.get('status')} | Dry run: {snapshot.get('dry_run')}")
    print(f"Known books planned: {len(snapshot.get('tasks', []))}")
    if snapshot.get("unknown_texts"):
        print(f"Unknown OCR text needing manual attention: {len(snapshot['unknown_texts'])}")
    print()
    print("Planned actions:")
    tasks = snapshot.get("tasks", [])
    if not tasks:
        print("  <none>")
    for task in tasks:
        print(
            f"  {task['index']:02d}. {task['title']} "
            f"from {task.get('human_pick')} -> {task.get('human_place')} "
            f"tilt={float(task.get('tilt_deg', 0.0)):+.1f}deg "
            f"commands={task['command_count']}"
        )
    unknown_texts = snapshot.get("unknown_texts", [])
    if unknown_texts:
        print("Manual attention:")
        for item in unknown_texts:
            print(f"  - OCR text {item.get('text')!r} is not in the known-book list.")
    skipped = snapshot.get("skipped_tasks", [])
    if skipped:
        print("Skipped:")
        for task in skipped:
            print(f"  - {task.get('title', '<unknown>')}: {task.get('reason')}")
    print(f"Combined command count: {snapshot.get('combined_command_count')}")
    print(f"Command file: {snapshot.get('combined_command_path')}")
    print("===== end ME470 Auto Demo Screen =====")
    print()


def _candidate_title(candidate: dict[str, Any]) -> str:
    return str(candidate.get("title", "<unknown>"))


def _human_tilt_description(tilt_deg: Any) -> str:
    if tilt_deg is None:
        return "Book tilt was not measured."
    try:
        tilt = float(tilt_deg)
    except (TypeError, ValueError):
        return "Book tilt was not measured."
    if abs(tilt) < 2.0:
        return "Book is nearly vertical."
    direction = "top leaning right" if tilt > 0 else "top leaning left"
    return f"Book is {direction} by about {abs(tilt):.1f} deg."


def _record_candidate_in_world(world: WorldModel, candidate: dict[str, Any]) -> None:
    pick = tuple(float(value) for value in candidate["pick"])
    world.remember_demo_bin_book(
        title=_candidate_title(candidate),
        pick=pick,
        confidence=float(candidate.get("confidence", 0.0)),
        bbox=tuple(candidate.get("bbox", ())),
        tilt_deg=(
            None
            if candidate.get("tilt_deg") is None
            else float(candidate.get("tilt_deg", 0.0))
        ),
        book_dimensions_mm=dict(candidate.get("book_dimensions_mm", {})),
    )


def _human_pick_description(pick: tuple[float, float, float]) -> str:
    lateral = float(pick[1])
    if abs(lateral) < 8.0:
        return "near the bin center"
    side = "+Y/right-side" if lateral > 0 else "-Y/left-side"
    return f"{side} of the bin"


def _human_place_description(
    place: tuple[float, float, float],
    slot_index: int,
    shelf_slot: dict[str, Any] | None = None,
) -> str:
    if shelf_slot:
        section = shelf_slot.get("section_label") or shelf_slot.get("section_id")
        slice_index = shelf_slot.get("slice_index")
        hint = shelf_slot.get("placement_hint", "center")
        return f"shelf {section} slice {slice_index} ({hint}) at X={place[0]:.0f} mm"
    return f"demo shelf slot {slot_index} at X={place[0]:.0f} mm"


def run_detected_books_loop(
    *,
    place_start: tuple[float, float, float] | None,
    loop_place_step_mm: float,
    max_loop_books: int | None,
    port: str,
    baud: int,
    fixed_step_delay: float | None,
    wait_trigger: str,
    dry_run: bool,
    timing: TimingConfig,
    shelf_model_snapshot: Path | None = None,
    use_initialized_shelf_model: bool = True,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    mode_name: str = "detected_books_loop",
) -> Path:
    """Prepare and optionally execute the detected-books loop."""
    output_dir = output_root / _now_stamp()
    snapshot_path = output_dir / "detected_books_loop_snapshot.json"
    report_path = output_dir / "detected_books_loop_report.md"
    loop_command_path = output_dir / "loop_hardware_command_sequence.txt"
    current_trajectory_path = CURRENT_SEQUENCE_ROOT / "control_trajectory.csv"
    current_command_path = CURRENT_SEQUENCE_ROOT / "hardware_command_sequence.txt"
    current_summary_path = CURRENT_SEQUENCE_ROOT / "TARGET_SEQUENCE_SUMMARY.md"
    CURRENT_SEQUENCE_ROOT.mkdir(parents=True, exist_ok=True)
    world = WorldModel()
    shelf_model: dict[str, Any] = {}
    initialized_slots: tuple[dict[str, Any], ...] = ()
    if use_initialized_shelf_model:
        if shelf_model_snapshot is None:
            shelf_model_snapshot = latest_startup_scan_snapshot()
        shelf_model, initialized_slots = _load_initialized_shelf_slots(shelf_model_snapshot)
    if initialized_slots:
        world.initialize_demo_shelf_model(shelf_model)
        placement_model = DemoShelfPlacementModel(
            start_place=None,
            step_x_mm=loop_place_step_mm,
            initialized_slots=initialized_slots,
            source="initialized_shelf_world_model",
        )
        print(
            f"[LOOP] Using initialized shelf world model with {len(initialized_slots)} free slot(s) "
            f"from {shelf_model.get('loaded_from')}.",
            flush=True,
        )
    else:
        if place_start is None:
            raise RuntimeError("没有可用的 shelf 初始化模型；请先运行 --startup-scan，或显式传 --place X Y Z")
        placement_model = DemoShelfPlacementModel(
            start_place=place_start,
            step_x_mm=loop_place_step_mm,
            source="fixed_demo_shelf_model",
        )

    snapshot: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": mode_name,
        "status": "partial",
        "output_dir": str(output_dir),
        "dry_run": bool(dry_run),
        "place_start": None if place_start is None else [float(value) for value in place_start],
        "place_step_mm": float(loop_place_step_mm),
        "shelf_model_source": placement_model.source,
        "shelf_model_snapshot": None if shelf_model_snapshot is None else str(shelf_model_snapshot),
        "initialized_shelf_slot_count": len(initialized_slots),
        "known_book_order": list(config.KNOWN_BOOK_TITLES),
        "tasks": [],
        "skipped_tasks": [],
        "unknown_texts": [],
        "combined_command_path": str(loop_command_path),
        "combined_command_count": 0,
        "errors": [],
        "world_model": {},
        "notes": [
            "Vision provides bin pick candidates through vision.lateral_pose_provider.",
            "A-route shelf logic: startup scan initializes shelf slots; execution updates WorldModel occupancy.",
            "WorldModel records detected books, planned placements, and occupied demo shelf positions.",
            "target_sequence.py remains the only hardware command-generation path.",
            "Intermediate per-book home commands are omitted; final book keeps measured home.",
        ],
    }

    scan_result = (
        _load_startup_bin_scan(shelf_model_snapshot)
        if mode_name == "auto_demo"
        else {}
    )
    if scan_result:
        print(
            "[RUNTIME] Auto demo: reusing bin pick candidates from startup_scan_snapshot; "
            "building a world-model-backed queue, then generating target_sequence commands.",
            flush=True,
        )
    else:
        print(
            "[RUNTIME] Detected-books loop: detecting known books in one camera frame, "
            "building a world-model-backed demo queue, then generating target_sequence commands.",
            flush=True,
        )
        scan_result = scan_book_pick_poses_with_unknowns_from_camera()
    snapshot["bin_candidate_source"] = scan_result.get("source", "live_camera")
    if scan_result.get("snapshot_path"):
        snapshot["bin_candidate_snapshot"] = scan_result["snapshot_path"]
    candidates = list(scan_result.get("candidates", []))
    unknown_texts = list(scan_result.get("unknown_texts", []))
    snapshot["unknown_texts"] = unknown_texts
    camera_error = scan_result.get("camera_error")
    if camera_error:
        snapshot["errors"].append(f"camera error: {camera_error}")
    if not candidates:
        snapshot["errors"].append("no known books detected")
        snapshot["status"] = "failed"
        snapshot["world_model"] = world.demo_summary()
        _write_json(snapshot_path, snapshot)
        report = _build_loop_report(snapshot)
        _write_text(report_path, report)
        _print_report("Detected Books Loop Report", report)
        raise RuntimeError("没有检测到任何可抓取的已知书")

    print("[RUNTIME] Detected candidates:")
    for index, candidate in enumerate(candidates, start=1):
        _record_candidate_in_world(world, candidate)
        pick_pose = candidate["pick"]
        try:
            place_pose, shelf_slot = placement_model.placement_for_index(index - 1)
            placement_source = placement_model.source
        except RuntimeError:
            place_pose, shelf_slot = (0.0, 0.0, 0.0), None
            placement_source = "no_initialized_slot_available"
        world.remember_demo_planned_placement(
            title=_candidate_title(candidate),
            place=place_pose,
            source=placement_source,
            shelf_slot=shelf_slot,
        )
        slot_text = ""
        if shelf_slot:
            slot_text = (
                f" slot={shelf_slot.get('slot_id')} "
                f"hint={shelf_slot.get('placement_hint')}"
            )
        print(
            f"  {index:02d}. {_candidate_title(candidate)!r} "
            f"pick=({pick_pose[0]:.1f}, {pick_pose[1]:.1f}, {pick_pose[2]:.1f}) "
            f"place=({place_pose[0]:.1f}, {place_pose[1]:.1f}, {place_pose[2]:.1f}) "
            f"{slot_text} "
            f"confidence={float(candidate.get('confidence', 0.0)):.2f} "
            f"tilt={float(candidate.get('tilt_deg', 0.0)):+.1f}deg"
        )

    combined_commands: list[str] = []
    feasible_count = 0
    for index, candidate in enumerate(candidates, start=1):
        if max_loop_books is not None and feasible_count >= max_loop_books:
            break
        title = _candidate_title(candidate)
        pick_pose = tuple(float(value) for value in candidate["pick"])
        try:
            place_pose, shelf_slot = placement_model.placement_for_index(feasible_count)
        except RuntimeError as exc:
            reason = f"shelf placement failed: {exc}"
            print(f"[LOOP] Skipping {title!r}: {reason}")
            snapshot["skipped_tasks"].append(
                {
                    "index": index,
                    "title": title,
                    "pick": [float(value) for value in pick_pose],
                    "place": None,
                    "human_pick": _human_pick_description(pick_pose),
                    "human_place": "no initialized shelf slot available",
                    "reason": reason,
                }
            )
            world.remember_blocked_reason(title, reason)
            continue
        print(
            f"[LOOP] {index}/{len(candidates)}: prechecking {title!r} "
            f"pick=({pick_pose[0]:.1f}, {pick_pose[1]:.1f}, {pick_pose[2]:.1f}) "
            f"place=({place_pose[0]:.1f}, {place_pose[1]:.1f}, {place_pose[2]:.1f})",
            flush=True,
        )
        try:
            result = generate_target_sequence(
                pick=pick_pose,
                place=place_pose,
                timing=timing,
                trajectory_path=current_trajectory_path,
                command_path=current_command_path,
                summary_path=current_summary_path,
            )
        except Exception as exc:  # noqa: BLE001 - report per-book planning failures.
            reason = f"target_sequence failed: {exc}"
            print(f"[LOOP] Skipping {title!r}: {reason}")
            snapshot["skipped_tasks"].append(
                {
            "index": index,
            "title": title,
            "pick": [float(value) for value in pick_pose],
            "place": [float(value) for value in place_pose],
            "human_pick": _human_pick_description(pick_pose),
            "human_place": _human_place_description(place_pose, index, shelf_slot),
            "reason": reason,
        }
            )
            world.remember_blocked_reason(title, reason)
            continue

        print_command_preview(result)
        commands = list(result.commands)
        is_last_candidate = index == len(candidates)
        if not is_last_candidate and commands and commands[-1] == HARDWARE_HOME_COMMAND:
            commands = commands[:-1]
        command_start = len(combined_commands) + 1
        combined_commands.extend(commands)
        command_end = len(combined_commands)
        feasible_count += 1
        world.remember_demo_shelf_occupancy(
            title=title,
            place=place_pose,
            command_start=command_start,
            command_end=command_end,
            shelf_slot=shelf_slot,
        )
        snapshot["tasks"].append(
            {
                "index": feasible_count,
                "source_candidate_index": index,
                "title": title,
                "confidence": float(candidate.get("confidence", 0.0)),
                "bbox": list(candidate.get("bbox", ())),
                "tilt_deg": float(candidate.get("tilt_deg", 0.0)),
                "tilt_direction": candidate.get("tilt_direction", "unknown"),
                "suggested_place_tilt_deg": float(
                    candidate.get("suggested_place_tilt_deg", 0.0)
                ),
                "book_dimensions_mm": candidate.get("book_dimensions_mm", {}),
                "pick": [float(value) for value in pick_pose],
                "place": [float(value) for value in place_pose],
                "human_pick": _human_pick_description(pick_pose),
                "human_place": _human_place_description(place_pose, feasible_count, shelf_slot),
                "shelf_slot": dict(shelf_slot or {}),
                "trajectory_path": str(result.trajectory_path),
                "command_path": str(result.command_path),
                "summary_path": str(result.summary_path),
                "command_start": command_start,
                "command_end": command_end,
                "command_count": len(commands),
                "intermediate_home_omitted": not is_last_candidate,
                "placement_source": placement_model.source,
            }
        )

    if not combined_commands:
        write_command_file([], loop_command_path)
        snapshot["errors"].append("no feasible target sequences were generated")
        snapshot["status"] = "failed"
        snapshot["world_model"] = world.demo_summary()
        _write_json(snapshot_path, snapshot)
        report = _build_loop_report(snapshot)
        _write_text(report_path, report)
        _print_report("Detected Books Loop Report", report)
        raise RuntimeError("没有生成任何可执行的 target_sequence")

    if combined_commands[-1] != HARDWARE_HOME_COMMAND:
        combined_commands.append(HARDWARE_HOME_COMMAND)
        if snapshot["tasks"]:
            last_task = snapshot["tasks"][-1]
            last_task["command_end"] = len(combined_commands)
            last_task["command_count"] = int(last_task["command_count"]) + 1
            last_task["intermediate_home_omitted"] = False
            last_task["final_home_appended_after_skips"] = True

    write_command_file(combined_commands, loop_command_path)
    snapshot["combined_command_count"] = len(combined_commands)
    snapshot["status"] = "prepared_with_skips" if snapshot["skipped_tasks"] else "prepared"
    snapshot["world_model"] = world.demo_summary()
    snapshot["visual_plan_paths"] = _write_plan_overlays(snapshot, output_dir)
    _write_json(snapshot_path, snapshot)
    report = _build_loop_report(snapshot)
    _write_text(report_path, report)
    print(
        f"[LOOP] Combined command sequence: {loop_command_path} "
        f"({len(combined_commands)} commands for {len(snapshot['tasks'])} feasible book(s))",
        flush=True,
    )
    print(f"[LOOP] Snapshot: {snapshot_path}")
    print(f"[LOOP] Report:   {report_path}")
    _print_execution_plan(snapshot)

    preflight_hardware_sender(port, dry_run=dry_run)
    wait_for_start_trigger(wait_trigger, dry_run=dry_run)
    send_hardware_sequence(
        command_path=loop_command_path,
        port=port,
        baud=baud,
        fixed_step_delay=fixed_step_delay,
        dry_run=dry_run,
    )
    snapshot["status"] = "dry_run_complete" if dry_run else "sent"
    snapshot["world_model"] = world.demo_summary()
    _write_json(snapshot_path, snapshot)
    report = _build_loop_report(snapshot)
    _write_text(report_path, report)
    _print_report("Detected Books Loop Report", report)
    _open_visual_plan_paths(list(snapshot.get("visual_plan_paths", [])))
    return snapshot_path
