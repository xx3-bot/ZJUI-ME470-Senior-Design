"""Detect shelf sections and score coarse placement slices.

This module is the first small shelf-vision step for the demo path. It detects
large shelf panels in an image, splits each panel into five coarse slices, and
gives the edge slices a higher score because they have side-wall support.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .image_preprocess import clean_gray_for_edges

SECTION_WIDTH_MM = 81.0
SLICE_COUNT = 5
EDGE_SUPPORT_BONUS = 20.0
IMAGE_AXIS_MAX_BONUS = 10.0
ADJACENT_SUPPORT_BONUS = 12.0
BASE_SLICE_SCORE = 10.0
UNKNOWN_OCCUPANCY_PENALTY = 0.0
OCCUPIED_SLICE_PENALTY = 45.0
PARTIAL_OCCUPANCY_PENALTY = 18.0
MIN_SECTION_WIDTH_HEIGHT_RATIO = 0.18
MAX_SINGLE_SECTION_WIDTH_HEIGHT_RATIO = 0.56
MAX_PAIRED_SECTION_WIDTH_RATIO = 1.25
CAD_SHELF_BACK_WIDTH_MM = 81.0
CAD_SHELF_BACK_HEIGHT_MM = 162.0
CAD_TEMPLATE_ASPECT_RATIOS = (
    CAD_SHELF_BACK_WIDTH_MM / CAD_SHELF_BACK_HEIGHT_MM,  # full back panel
    1.0,  # partial/square visible CAD face
)


@dataclass(frozen=True)
class ShelfSlice:
    index: int
    bbox_px: tuple[int, int, int, int]
    quad_px: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]
    center_px: tuple[float, float]
    center_x_mm_local: float
    center_x_mm_centered: float
    width_mm: float
    status: str
    score: float
    support_score: float
    image_axis_score: float
    adjacent_support_score: float
    image_axis_distance_px: float
    occupancy_score: float
    occupancy_source: str
    placement_hint: str
    support_side: str
    reason: str


@dataclass(frozen=True)
class ShelfSection:
    section_id: str
    bbox_px: tuple[int, int, int, int]
    quad_px: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]
    center_px: tuple[float, float]
    width_mm: float
    camera_depth_mm: float
    depth_method: str
    slice_count: int
    confidence: float
    slices: list[ShelfSlice]


def detect_shelf_sections(
    frame: np.ndarray,
    *,
    section_width_mm: float = SECTION_WIDTH_MM,
    slice_count: int = SLICE_COUNT,
) -> list[ShelfSection]:
    """Detect two large shelf panels and split each into placement slices."""
    if frame is None or frame.size == 0:
        raise ValueError("frame is empty")
    if slice_count <= 0:
        raise ValueError("slice_count must be positive")

    h, w = frame.shape[:2]
    yellow_mask = _yellow_shelf_mask(frame)
    cad_sections = _detect_cad_guided_back_panel_sections(frame)
    if cad_sections:
        raw_sections = cad_sections
    else:
        raw_sections = []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        vertical_edges = _detect_vertical_boundaries(gray)
        horizontal_edges = _detect_horizontal_boundaries(gray)

        borders = _pick_panel_borders(vertical_edges, w)
        if borders is None:
            cleaned_gray = clean_gray_for_edges(frame).astype(np.float32)
            vertical_edges = _detect_vertical_boundaries(cleaned_gray)
            horizontal_edges = _detect_horizontal_boundaries(cleaned_gray)
            borders = _pick_panel_borders(vertical_edges, w)
        if borders is not None:
            left_outer, left_inner, right_inner, right_outer = borders
            top, bottom = _pick_panel_vertical_extent(horizontal_edges, h)

            raw_sections = [
                ("left", left_outer, top, left_inner, bottom, None),
                ("right", right_inner, top, right_outer, bottom, None),
            ]
        else:
            color_bboxes = _detect_yellow_shelf_bboxes(frame, yellow_mask=yellow_mask)
            if len(color_bboxes) >= 2:
                color_bboxes = _refine_paired_shelf_bboxes(color_bboxes[:2], yellow_mask)
                raw_sections = [
                    ("left", *color_bboxes[0], None),
                    ("right", *color_bboxes[1], None),
                ]
            elif len(color_bboxes) == 1:
                # Final fallback for the current yellow test shelf only.
                raw_sections = [
                    ("left", *color_bboxes[0], None),
                ]
            else:
                return []
    sections: list[ShelfSection] = []
    for section_id, x0, top, x1, bottom, quad_override in raw_sections:
        bbox = (int(x0), int(top), int(x1 - x0), int(bottom - top))
        quad = (
            quad_override
            if quad_override is not None
            else _section_quad_from_yellow_mask(yellow_mask, bbox, section_id=section_id)
        )
        cx = bbox[0] + bbox[2] / 2.0
        cy = bbox[1] + bbox[3] / 2.0
        occupancy_mask = (
            None
            if quad_override is not None
            else yellow_mask
            if _has_yellow_occupancy_cue(yellow_mask, bbox)
            else None
        )
        slices = slice_shelf_section(
            bbox,
            section_quad_px=quad,
            section_width_mm=section_width_mm,
            slice_count=slice_count,
            image_width_px=w,
            yellow_mask=occupancy_mask,
        )
        section_width_px = _quad_average_width_px(quad)
        camera_depth_mm = estimate_camera_depth_from_section_width(
            section_width_px,
            section_width_mm=section_width_mm,
        )
        sections.append(
            ShelfSection(
                section_id=section_id,
                bbox_px=bbox,
                quad_px=quad,
                center_px=(round(cx, 1), round(cy, 1)),
                width_mm=section_width_mm,
                camera_depth_mm=round(camera_depth_mm, 1),
                depth_method="known_section_width_pinhole",
                slice_count=slice_count,
                confidence=_section_confidence(bbox, frame.shape[:2]),
                slices=slices,
            )
        )
    return sections


def slice_shelf_section(
    bbox_px: tuple[int, int, int, int],
    *,
    section_quad_px: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]
    | None = None,
    section_width_mm: float = SECTION_WIDTH_MM,
    slice_count: int = SLICE_COUNT,
    image_width_px: int | None = None,
    yellow_mask: np.ndarray | None = None,
) -> list[ShelfSlice]:
    """Split a shelf section into fixed coarse placement slices."""
    x, y, w, h = bbox_px
    if section_quad_px is None:
        section_quad_px = _rect_quad(bbox_px)
    slice_width_px = w / slice_count
    slice_width_mm = section_width_mm / slice_count
    slices: list[ShelfSlice] = []
    occupancy = [
        _slice_occupancy_score(
            yellow_mask,
            _quad_bbox(_slice_quad(section_quad_px, index / slice_count, (index + 1) / slice_count)),
        )
        for index in range(slice_count)
    ]

    for index in range(slice_count):
        sx = x + slice_width_px * index
        slice_quad = _slice_quad(section_quad_px, index / slice_count, (index + 1) / slice_count)
        slice_bbox = _quad_bbox(slice_quad)
        cx = sx + slice_width_px / 2.0
        local_mm = slice_width_mm * (index + 0.5)
        centered_mm = local_mm - section_width_mm / 2.0
        occupancy_score, occupancy_source = occupancy[index]
        score_parts = _score_slice(
            index=index,
            slice_count=slice_count,
            center_x_px=cx,
            image_width_px=image_width_px,
            occupancy_score=occupancy_score,
            left_neighbor_occupied=index > 0 and occupancy[index - 1][0] >= 0.58,
            right_neighbor_occupied=index < slice_count - 1 and occupancy[index + 1][0] >= 0.58,
        )
        slices.append(
            ShelfSlice(
                index=index,
                bbox_px=slice_bbox,
                quad_px=slice_quad,
                center_px=_quad_center(slice_quad),
                center_x_mm_local=round(local_mm, 2),
                center_x_mm_centered=round(centered_mm, 2),
                width_mm=round(slice_width_mm, 2),
                status=score_parts["status"],
                score=score_parts["score"],
                support_score=score_parts["support_score"],
                image_axis_score=score_parts["image_axis_score"],
                adjacent_support_score=score_parts["adjacent_support_score"],
                image_axis_distance_px=score_parts["image_axis_distance_px"],
                occupancy_score=occupancy_score,
                occupancy_source=occupancy_source,
                placement_hint=score_parts["placement_hint"],
                support_side=score_parts["support_side"],
                reason=score_parts["reason"],
            )
        )
    return slices


def estimate_shelf_place_candidates(
    frame: np.ndarray,
    *,
    fixed_z_mm: float = 140.0,
    section_width_mm: float = SECTION_WIDTH_MM,
    slice_count: int = SLICE_COUNT,
) -> dict[str, Any]:
    """Return section/slice candidates for later decision or control layers."""
    sections = detect_shelf_sections(
        frame,
        section_width_mm=section_width_mm,
        slice_count=slice_count,
    )
    average_depth = _average_depth_mm(sections)
    candidates: list[dict[str, Any]] = []
    for section in sections:
        for shelf_slice in section.slices:
            candidates.append(
                {
                    "section_id": section.section_id,
                    "slice_index": shelf_slice.index,
                    "center_px": shelf_slice.center_px,
                    "center_x_mm_local": shelf_slice.center_x_mm_local,
                    "center_x_mm_centered": shelf_slice.center_x_mm_centered,
                    "camera_depth_mm": section.camera_depth_mm,
                    "fixed_z_mm": fixed_z_mm,
                    "score": shelf_slice.score,
                    "support_score": shelf_slice.support_score,
                    "image_axis_score": shelf_slice.image_axis_score,
                    "adjacent_support_score": shelf_slice.adjacent_support_score,
                    "image_axis_distance_px": shelf_slice.image_axis_distance_px,
                    "occupancy_score": shelf_slice.occupancy_score,
                    "occupancy_source": shelf_slice.occupancy_source,
                    "placement_hint": shelf_slice.placement_hint,
                    "support_side": shelf_slice.support_side,
                    "status": shelf_slice.status,
                    "reason": shelf_slice.reason,
                }
            )
    candidates.sort(key=lambda item: (-item["score"], item["section_id"], item["slice_index"]))
    return {
        "status": "complete" if sections else "no_sections_detected",
        "section_width_mm": section_width_mm,
        "camera_depth_mm": average_depth,
        "depth_method": "known_section_width_pinhole",
        "depth_note": "Camera-relative depth only; no camera-to-arm extrinsics applied.",
        "slice_count": slice_count,
        "fixed_z_mm": fixed_z_mm,
        "sections": [section_to_dict(section) for section in sections],
        "ranked_candidates": candidates,
    }


def section_to_dict(section: ShelfSection) -> dict[str, Any]:
    data = asdict(section)
    data["id"] = data.pop("section_id")
    return data


def estimate_camera_depth_from_section_width(
    section_width_px: float,
    *,
    section_width_mm: float = SECTION_WIDTH_MM,
) -> float:
    """Estimate camera-to-shelf-panel depth from known panel width."""
    if section_width_px <= 0:
        return 0.0
    import config

    fx = float(config.RGB_INTRINSICS_FX_PX)
    return fx * section_width_mm / float(section_width_px)


def _average_depth_mm(sections: list[ShelfSection]) -> float | None:
    depths = [section.camera_depth_mm for section in sections if section.camera_depth_mm > 0.0]
    if not depths:
        return None
    return round(float(sum(depths) / len(depths)), 1)


def _rect_quad(
    bbox_px: tuple[int, int, int, int],
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]:
    x, y, w, h = bbox_px
    return ((x, y), (x + w, y), (x + w, y + h), (x, y + h))


def _section_quad_from_yellow_mask(
    yellow_mask: np.ndarray,
    bbox_px: tuple[int, int, int, int],
    *,
    section_id: str | None = None,
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Estimate a perspective-aware visible shelf quad from the yellow mask.

    The shelf is not always square to the camera. Instead of forcing a single
    axis-aligned rectangle, this samples the visible yellow pixels near the top
    and bottom of the detected shelf body and lets the two side edges lean.
    """
    x, y, w, h = bbox_px
    if yellow_mask is None or yellow_mask.size == 0 or w <= 0 or h <= 0:
        return _rect_quad(bbox_px)

    image_h, image_w = yellow_mask.shape[:2]
    x0 = max(0, x)
    x1 = min(image_w, x + w)
    y0 = max(0, y)
    y1 = min(image_h, y + h)
    if x1 <= x0 or y1 <= y0:
        return _rect_quad(bbox_px)

    roi = yellow_mask[y0:y1, x0:x1]
    ys, xs = np.where(roi > 0)
    if xs.size < 80:
        return _rect_quad(bbox_px)

    top_y_local = int(np.percentile(ys, 6.0))
    bottom_y_local = int(np.percentile(ys, 94.0))
    band = max(8, int(h * 0.055))

    top_range = np.where(np.abs(ys - top_y_local) <= band)[0]
    bottom_range = np.where(np.abs(ys - bottom_y_local) <= band)[0]
    if top_range.size < 8 or bottom_range.size < 8:
        return _rect_quad(bbox_px)

    top_xs = xs[top_range]
    bottom_xs = xs[bottom_range]
    top_left = int(np.percentile(top_xs, 3.0)) + x0
    top_right = int(np.percentile(top_xs, 97.0)) + x0
    bottom_left = int(np.percentile(bottom_xs, 3.0)) + x0
    bottom_right = int(np.percentile(bottom_xs, 97.0)) + x0
    top_y = top_y_local + y0
    bottom_y = bottom_y_local + y0

    # Keep the quad sane. If the sampled mask collapses because a book covers
    # most of a shelf, fall back to the axis-aligned body detection.
    if min(top_right - top_left, bottom_right - bottom_left) < max(24, int(w * 0.25)):
        return _rect_quad(bbox_px)
    quad = ((top_left, top_y), (top_right, top_y), (bottom_right, bottom_y), (bottom_left, bottom_y))
    return _trim_visible_side_wall_from_quad(quad, section_id=section_id)


def _trim_visible_side_wall_from_quad(
    quad_px: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
    *,
    section_id: str | None,
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Avoid treating a strongly visible side wall as a placement slice.

    In the angled shelf view, the right shelf often shows its right side face.
    That side face is useful support geometry, but it is not the front opening
    where a book center should be placed. If the right edge fans outward hard,
    cap the lower corner close to the upper edge so slices stay on the usable
    front plane.
    """
    if section_id != "right":
        return quad_px
    top_left, top_right, bottom_right, bottom_left = quad_px
    top_width = max(1, top_right[0] - top_left[0])
    outward_px = bottom_right[0] - top_right[0]
    max_front_edge_slope_px = max(12, int(top_width * 0.08))
    if outward_px <= max_front_edge_slope_px:
        return quad_px
    capped_bottom_right = (top_right[0] + max_front_edge_slope_px, bottom_right[1])
    return (top_left, top_right, capped_bottom_right, bottom_left)


def _slice_quad(
    section_quad_px: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
    start_fraction: float,
    end_fraction: float,
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]:
    top_left, top_right, bottom_right, bottom_left = [
        np.array(point, dtype=np.float32) for point in section_quad_px
    ]

    def lerp(start: np.ndarray, end: np.ndarray, fraction: float) -> np.ndarray:
        return start + (end - start) * float(fraction)

    slice_top_left = lerp(top_left, top_right, start_fraction)
    slice_top_right = lerp(top_left, top_right, end_fraction)
    slice_bottom_right = lerp(bottom_left, bottom_right, end_fraction)
    slice_bottom_left = lerp(bottom_left, bottom_right, start_fraction)
    return tuple(
        (int(round(point[0])), int(round(point[1])))
        for point in (slice_top_left, slice_top_right, slice_bottom_right, slice_bottom_left)
    )


def _quad_bbox(
    quad_px: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
) -> tuple[int, int, int, int]:
    xs = [point[0] for point in quad_px]
    ys = [point[1] for point in quad_px]
    x0 = min(xs)
    y0 = min(ys)
    return x0, y0, max(xs) - x0, max(ys) - y0


def _quad_center(
    quad_px: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
) -> tuple[float, float]:
    xs = [point[0] for point in quad_px]
    ys = [point[1] for point in quad_px]
    return round(float(sum(xs) / len(xs)), 1), round(float(sum(ys) / len(ys)), 1)


def _quad_average_width_px(
    quad_px: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
) -> float:
    top_left, top_right, bottom_right, bottom_left = [
        np.array(point, dtype=np.float32) for point in quad_px
    ]
    top_width = float(np.linalg.norm(top_right - top_left))
    bottom_width = float(np.linalg.norm(bottom_right - bottom_left))
    return max(1.0, (top_width + bottom_width) / 2.0)


def _draw_polyline(
    overlay: np.ndarray,
    quad_px: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    points = np.array(quad_px, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(overlay, [points], isClosed=True, color=color, thickness=thickness)


def draw_shelf_scan_overlay(frame: np.ndarray, sections: list[ShelfSection]) -> np.ndarray:
    """Draw section and slice detections for debugging."""
    overlay = frame.copy()
    for section in sections:
        x, y, w, h = section.bbox_px
        color = (0, 0, 255) if section.section_id == "left" else (0, 128, 255)
        _draw_polyline(overlay, section.quad_px, color, 4)
        cv2.putText(
            overlay,
            f"{section.section_id} score-edge slices",
            (x, max(20, y - 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            color,
            2,
        )
        for shelf_slice in section.slices:
            sx, sy, _, _ = shelf_slice.bbox_px
            cx, cy = map(int, shelf_slice.center_px)
            if shelf_slice.status == "occupied":
                slice_color = (0, 0, 255)
            elif shelf_slice.status == "partial":
                slice_color = (0, 165, 255)
            elif shelf_slice.support_side != "none":
                slice_color = (0, 255, 0)
            else:
                slice_color = (255, 0, 0)
            _draw_polyline(overlay, shelf_slice.quad_px, slice_color, 1)
            cv2.circle(overlay, (cx, cy), 5, slice_color, -1)
            cv2.putText(
                overlay,
                f"{shelf_slice.index}:{shelf_slice.score:.0f}",
                (sx + 4, sy + 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                slice_color,
                2,
            )
    return overlay


def _score_slice(
    *,
    index: int,
    slice_count: int,
    center_x_px: float,
    image_width_px: int | None,
    occupancy_score: float,
    left_neighbor_occupied: bool,
    right_neighbor_occupied: bool,
) -> dict[str, Any]:
    base_score = BASE_SLICE_SCORE - UNKNOWN_OCCUPANCY_PENALTY
    axis_score, axis_distance = _image_axis_score(center_x_px, image_width_px)
    occupancy_penalty = 0.0
    if occupancy_score >= 0.58:
        occupancy_penalty = OCCUPIED_SLICE_PENALTY
    elif occupancy_score >= 0.38:
        occupancy_penalty = PARTIAL_OCCUPANCY_PENALTY

    adjacent_support_score = 0.0
    adjacent_support_side = "none"
    adjacent_hint = "center"
    if occupancy_penalty == 0.0:
        if left_neighbor_occupied:
            adjacent_support_score = ADJACENT_SUPPORT_BONUS
            adjacent_support_side = "left_book"
            adjacent_hint = "lean_left"
        elif right_neighbor_occupied:
            adjacent_support_score = ADJACENT_SUPPORT_BONUS
            adjacent_support_side = "right_book"
            adjacent_hint = "lean_right"

    if index == 0:
        support_score = EDGE_SUPPORT_BONUS
        score = base_score + support_score + axis_score + adjacent_support_score - occupancy_penalty
        status = "occupied" if occupancy_penalty >= OCCUPIED_SLICE_PENALTY else "partial" if occupancy_penalty else "free_candidate"
        return {
            "score": round(score, 2),
            "status": status,
            "support_score": support_score,
            "image_axis_score": axis_score,
            "adjacent_support_score": adjacent_support_score,
            "image_axis_distance_px": axis_distance,
            "placement_hint": "lean_left" if status != "occupied" else "occupied",
            "support_side": "left_wall",
            "reason": (
                "edge slice has left wall support; "
                f"image-axis bonus {axis_score:.1f}; "
                f"occupancy penalty {occupancy_penalty:.1f}"
            ),
        }
    if index == slice_count - 1:
        support_score = EDGE_SUPPORT_BONUS
        score = base_score + support_score + axis_score + adjacent_support_score - occupancy_penalty
        status = "occupied" if occupancy_penalty >= OCCUPIED_SLICE_PENALTY else "partial" if occupancy_penalty else "free_candidate"
        return {
            "score": round(score, 2),
            "status": status,
            "support_score": support_score,
            "image_axis_score": axis_score,
            "adjacent_support_score": adjacent_support_score,
            "image_axis_distance_px": axis_distance,
            "placement_hint": "lean_right" if status != "occupied" else "occupied",
            "support_side": "right_wall",
            "reason": (
                "edge slice has right wall support; "
                f"image-axis bonus {axis_score:.1f}; "
                f"occupancy penalty {occupancy_penalty:.1f}"
            ),
        }
    support_side = adjacent_support_side
    placement_hint = adjacent_hint
    score = base_score + axis_score + adjacent_support_score - occupancy_penalty
    status = "occupied" if occupancy_penalty >= OCCUPIED_SLICE_PENALTY else "partial" if occupancy_penalty else "free_candidate"
    if status == "occupied":
        placement_hint = "occupied"
    return {
        "score": round(score, 2),
        "status": status,
        "support_score": 0.0,
        "image_axis_score": axis_score,
        "adjacent_support_score": adjacent_support_score,
        "image_axis_distance_px": axis_distance,
        "placement_hint": placement_hint,
        "support_side": support_side,
        "reason": (
            "interior slice; "
            f"adjacent support {adjacent_support_score:.1f}; "
            f"image-axis bonus {axis_score:.1f}; "
            f"occupancy penalty {occupancy_penalty:.1f}"
        ),
    }


def _image_axis_score(center_x_px: float, image_width_px: int | None) -> tuple[float, float]:
    if image_width_px is None or image_width_px <= 0:
        return 0.0, 0.0
    axis_x = image_width_px / 2.0
    max_distance = max(axis_x, 1.0)
    distance = abs(center_x_px - axis_x)
    score = IMAGE_AXIS_MAX_BONUS * max(0.0, 1.0 - distance / max_distance)
    return round(score, 2), round(distance, 1)


def _detect_vertical_boundaries(gray: np.ndarray) -> list[tuple[int, float]]:
    h, _ = gray.shape
    y0 = max(0, int(h * 0.095))
    y1 = min(h, int(h * 0.948))
    sobel = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))[y0:y1]
    return _smoothed_edge_peaks(sobel.sum(axis=0), percentile=95.0, min_distance_px=20)


def _detect_horizontal_boundaries(gray: np.ndarray) -> list[tuple[int, float]]:
    _, w = gray.shape
    x0 = max(0, int(w * 0.11))
    x1 = min(w, int(w * 0.85))
    sobel = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))[:, x0:x1]
    return _smoothed_edge_peaks(sobel.sum(axis=1), percentile=95.0, min_distance_px=20)


def _yellow_shelf_mask(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, np.array((15, 70, 70)), np.array((42, 255, 255)))


def _detect_cad_guided_back_panel_sections(
    frame: np.ndarray,
) -> list[
    tuple[
        str,
        int,
        int,
        int,
        int,
        tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
    ]
]:
    """Detect CAD-constrained shelf backing planes from the perforation pattern.

    The 3MF model fixes a shelf module at 81 x 162 x 162 mm after print-scale.
    For vision we should therefore match a constrained CAD face rather than a
    free yellow blob: full back panels are approximately 81:162, while partial
    visible faces can be close to 81:81. Side walls may still support placement
    scoring, but this detector returns only the backing/slot plane used for
    slicing.
    """
    if frame is None or frame.size == 0:
        return []

    image_h, image_w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    local_background = cv2.GaussianBlur(gray, (31, 31), 0)
    local_contrast = cv2.absdiff(gray, local_background)
    contrast_threshold = max(18.0, float(np.percentile(local_contrast, 88.0)))
    contrast_mask = (local_contrast >= contrast_threshold).astype(np.uint8) * 255
    contrast_mask = cv2.morphologyEx(
        contrast_mask,
        cv2.MORPH_OPEN,
        np.ones((3, 3), np.uint8),
        iterations=1,
    )
    contours, _ = cv2.findContours(contrast_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    hole_centers: list[tuple[float, float]] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if not (10.0 <= area <= 360.0):
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if y < image_h * 0.18 or y > image_h * 0.92:
            continue
        aspect = w / max(h, 1)
        if not (0.45 <= aspect <= 1.8):
            continue

        blob_contrast = float(local_contrast[y : y + h, x : x + w].mean())
        if blob_contrast < contrast_threshold * 0.72:
            continue
        hole_centers.append((x + w / 2.0, y + h / 2.0))

    if len(hole_centers) < 30:
        return []

    hole_centers.sort(key=lambda point: point[0])
    clusters: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    previous_x: float | None = None
    for point in hole_centers:
        if previous_x is not None and point[0] - previous_x > 28.0:
            if current:
                clusters.append(current)
            current = []
        current.append(point)
        previous_x = point[0]
    if current:
        clusters.append(current)

    candidates: list[dict[str, Any]] = []
    for cluster in clusters:
        if len(cluster) < 35:
            continue
        points = np.array(cluster, dtype=np.float32)
        xmin, ymin = points.min(axis=0)
        xmax, ymax = points.max(axis=0)
        hole_width = float(xmax - xmin)
        hole_height = float(ymax - ymin)
        if hole_width < 45.0 or hole_height < 150.0:
            continue

        x_bins = np.linspace(xmin, xmax, 6)
        y_bins = np.linspace(ymin, ymax, 9)
        occupied_bins = np.zeros((5, 8), dtype=bool)
        for point_x, point_y in points:
            x_index = int(np.searchsorted(x_bins, point_x, side="right") - 1)
            y_index = int(np.searchsorted(y_bins, point_y, side="right") - 1)
            if 0 <= x_index < 5 and 0 <= y_index < 8:
                occupied_bins[x_index, y_index] = True
        active_columns = int((occupied_bins.sum(axis=1) > 2).sum())
        active_rows = int((occupied_bins.sum(axis=0) > 2).sum())
        # Text or book edges can form high-contrast blobs, but they do not form
        # the repeated CAD perforation grid across enough rows and columns.
        if active_columns < 4 or active_rows < 5:
            continue

        observed_ratio = hole_width / max(hole_height, 1.0)
        cad_ratio = min(
            CAD_TEMPLATE_ASPECT_RATIOS,
            key=lambda ratio: abs(observed_ratio - ratio),
        )
        if abs(observed_ratio - cad_ratio) > 0.42:
            continue

        panel_height = hole_height + max(44.0, hole_height * 0.14)
        panel_width = panel_height * cad_ratio
        # Never let a CAD-constrained panel become narrower than the actual hole
        # field. That situation usually means the visible face is partial; grow
        # conservatively while keeping the selected CAD ratio.
        if panel_width < hole_width + 18.0:
            panel_width = hole_width + 18.0
            panel_height = panel_width / cad_ratio

        center_x = float((xmin + xmax) / 2.0)
        top = float(ymin - max(18.0, panel_height * 0.045))
        bottom = top + panel_height
        left = center_x - panel_width / 2.0
        right = center_x + panel_width / 2.0
        perspective = panel_width * 0.06
        quad_float = np.array(
            [
                [left + perspective, top],
                [right - perspective, top],
                [right + perspective, bottom],
                [left - perspective, bottom],
            ],
            dtype=np.float32,
        )
        quad_float[:, 0] = np.clip(quad_float[:, 0], 0, image_w - 1)
        quad_float[:, 1] = np.clip(quad_float[:, 1], 0, image_h - 1)
        quad = tuple((int(round(x)), int(round(y))) for x, y in quad_float)
        bbox = _quad_bbox(quad)
        x, y, width, height = bbox
        if width < 60 or height < 160:
            continue
        candidates.append(
            {
                "hole_count": len(cluster),
                "x": x,
                "y": y,
                "x1": x + width,
                "y1": y + height,
                "quad": quad,
                "ratio_error": abs(observed_ratio - cad_ratio),
                "cad_ratio": cad_ratio,
            }
        )

    if not candidates:
        return []

    candidates.sort(
        key=lambda item: (
            -float(item["hole_count"]),
            float(item["ratio_error"]),
            float(item["x"]),
        )
    )
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        cx0, cx1 = int(candidate["x"]), int(candidate["x1"])
        overlaps = False
        for kept in selected:
            kx0, kx1 = int(kept["x"]), int(kept["x1"])
            overlap = max(0, min(cx1, kx1) - max(cx0, kx0))
            if overlap / max(1, min(cx1 - cx0, kx1 - kx0)) > 0.35:
                overlaps = True
                break
        if overlaps:
            continue
        selected.append(candidate)
        if len(selected) >= 2:
            break

    selected.sort(key=lambda item: int(item["x"]))
    sections = []
    for index, candidate in enumerate(selected):
        section_id = "left" if index == 0 else "right"
        sections.append(
            (
                section_id,
                int(candidate["x"]),
                int(candidate["y"]),
                int(candidate["x1"]),
                int(candidate["y1"]),
                candidate["quad"],
            )
        )
    return sections


def _detect_yellow_shelf_bboxes(
    frame: np.ndarray,
    *,
    yellow_mask: np.ndarray | None = None,
) -> list[tuple[int, int, int, int]]:
    """Detect the two yellow physical shelf bodies in the current camera view.

    The real demo shelf is made from two yellow side sections. Grayscale edge
    detection can accidentally split one physical shelf into two panels, so the
    color mask is the safer first cue when the yellow rack is visible.
    """
    h, w = frame.shape[:2]
    mask = _yellow_shelf_mask(frame) if yellow_mask is None else yellow_mask
    y0 = int(h * 0.18)
    y1 = int(h * 0.98)
    roi = mask[y0:y1]
    if roi.size == 0:
        return []

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    roi = cv2.morphologyEx(roi, cv2.MORPH_OPEN, kernel, iterations=1)
    projection = (roi > 0).sum(axis=0).astype(np.float32)
    smooth = np.convolve(projection, np.ones(15) / 15, mode="same")
    threshold = max(float(np.percentile(smooth, 70.0)), (y1 - y0) * 0.12)

    segments: list[tuple[int, int]] = []
    start: int | None = None
    for x, value in enumerate(smooth):
        if value > threshold and start is None:
            start = x
        elif (value <= threshold or x == w - 1) and start is not None:
            end = x
            if end - start >= max(18, int(w * 0.015)):
                segments.append((start, end))
            start = None
    if len(segments) < 2:
        if len(segments) == 1:
            x0, x1 = segments[0]
            section_mask = roi[:, max(0, x0) : min(w, x1)]
            ys = np.where(section_mask > 0)[0]
            if ys.size:
                sy0 = max(0, int(y0 + ys.min()) - 4)
                sy1 = min(h, int(y0 + ys.max()) + 4)
            else:
                sy0, sy1 = y0, y1
            return _sanitize_shelf_bboxes(
                [_cap_single_shelf_width((int(x0), sy0, int(x1), sy1), image_width=w)],
                image_width=w,
            )
        return _sanitize_shelf_bboxes(
            _split_connected_yellow_shelf(frame, roi, y0, y1),
            image_width=w,
        )

    # Choose the split that yields two plausible non-overlapping shelf groups.
    best: tuple[float, tuple[int, int], tuple[int, int]] | None = None
    for split in range(1, len(segments)):
        left = (segments[0][0], segments[split - 1][1])
        right = (segments[split][0], segments[-1][1])
        left_w = left[1] - left[0]
        right_w = right[1] - right[0]
        if left_w < 60 or right_w < 60:
            continue
        balance = min(left_w, right_w) / max(left_w, right_w)
        gap = right[0] - left[1]
        center_distance = abs(((left[1] + right[0]) / 2.0) - w / 2.0) / max(w, 1)
        score = balance + min(max(gap, 0), 120) / 300.0 - center_distance
        if best is None or score > best[0]:
            best = (score, left, right)
    if best is None:
        return _sanitize_shelf_bboxes(
            _split_connected_yellow_shelf(frame, roi, y0, y1),
            image_width=w,
        )

    bboxes: list[tuple[int, int, int, int]] = []
    for x0, x1 in (best[1], best[2]):
        section_mask = roi[:, max(0, x0) : min(w, x1)]
        ys = np.where(section_mask > 0)[0]
        if ys.size:
            sy0 = max(0, int(y0 + ys.min()) - 4)
            sy1 = min(h, int(y0 + ys.max()) + 4)
        else:
            sy0, sy1 = y0, y1
        bboxes.append((int(x0), sy0, int(x1), sy1))
    return _sanitize_shelf_bboxes(bboxes, image_width=w)[:2]


def _split_connected_yellow_shelf(
    frame: np.ndarray,
    roi: np.ndarray,
    y0: int,
    y1: int,
) -> list[tuple[int, int, int, int]]:
    """Fallback for views where the two yellow shelves connect into one blob."""
    h, w = frame.shape[:2]
    projection = (roi > 0).sum(axis=0).astype(np.float32)
    smooth = np.convolve(projection, np.ones(11) / 11, mode="same")
    active = np.where(smooth > max(50.0, (y1 - y0) * 0.10))[0]
    if active.size < 120:
        return []
    x0 = int(active.min())
    x1 = int(active.max())
    width = x1 - x0
    peaks: list[tuple[int, float]] = []
    for index in range(max(10, x0), min(w - 10, x1)):
        if smooth[index] == max(smooth[index - 10 : index + 11]) and smooth[index] > (y1 - y0) * 0.45:
            peaks.append((index, float(smooth[index])))
    merged: list[tuple[int, float]] = []
    for peak in peaks:
        if not merged or peak[0] - merged[-1][0] > 20:
            merged.append(peak)
        elif peak[1] > merged[-1][1]:
            merged[-1] = peak

    split_candidates = [
        (x, strength)
        for x, strength in merged
        if x0 + width * 0.25 <= x <= x0 + width * 0.62
    ]
    if split_candidates:
        split_x = int(max(split_candidates, key=lambda item: item[1])[0])
    else:
        split_x = int(x0 + width * 0.42)

    section_y0, section_y1 = _yellow_vertical_extent(roi, y0, h)
    if split_x - x0 < 60 or x1 - split_x < 60:
        return []
    return [
        (x0, section_y0, split_x, section_y1),
        (split_x, section_y0, x1, section_y1),
    ]


def _refine_paired_shelf_bboxes(
    bboxes: list[tuple[int, int, int, int]],
    yellow_mask: np.ndarray,
) -> list[tuple[int, int, int, int]]:
    """Refine paired same-model shelf detections.

    The central divider between two adjacent yellow shelves can dip below the
    strong color-projection threshold, which makes the left shelf look too
    narrow. The right shelf may also include its visible side wall. Because the
    two shelves are the same model in one frame, keep their front-plane widths
    in the same rough range.
    """
    if len(bboxes) < 2 or yellow_mask is None or yellow_mask.size == 0:
        return bboxes
    left, right = sorted(bboxes[:2], key=lambda item: item[0])
    lx0, ly0, lx1, ly1 = left
    rx0, ry0, rx1, ry1 = right
    gap = rx0 - lx1
    if gap > 0 and gap <= 80:
        image_h, image_w = yellow_mask.shape[:2]
        gx0 = max(0, lx1)
        gx1 = min(image_w, rx0)
        gy0 = max(0, min(ly0, ry0))
        gy1 = min(image_h, max(ly1, ry1))
        if gx1 > gx0 and gy1 > gy0:
            gap_yellow_fraction = float((yellow_mask[gy0:gy1, gx0:gx1] > 0).mean())
            if gap_yellow_fraction >= 0.10:
                split_x = int(round((lx1 + rx0) / 2.0))
                # Expand the left shelf into the inner divider/gap, but do not
                # move the right shelf's inner edge leftward.
                lx1 = split_x
                ly0 = min(ly0, ry0)
                ly1 = max(ly1, ry1)

    left_width = max(1, lx1 - lx0)
    right_width = max(1, rx1 - rx0)
    max_width_ratio = MAX_PAIRED_SECTION_WIDTH_RATIO
    if right_width > left_width * max_width_ratio:
        rx1 = int(round(rx0 + left_width * max_width_ratio))
    elif left_width > right_width * max_width_ratio:
        lx0 = int(round(lx1 - right_width * max_width_ratio))

    return [
        (lx0, min(ly0, ry0), lx1, max(ly1, ry1)),
        (rx0, min(ly0, ry0), rx1, max(ly1, ry1)),
    ]


def _cap_single_shelf_width(
    bbox: tuple[int, int, int, int],
    *,
    image_width: int,
) -> tuple[int, int, int, int]:
    """Constrain a single detected shelf so one blob cannot swallow neighbors.

    In startup views, a book or visible side wall may connect yellow areas into
    one large segment. A real single shelf front should have a width roughly
    proportional to its visible height, so cap obviously over-wide detections.
    """
    x0, y0, x1, y1 = bbox
    height = max(1, y1 - y0)
    max_width = int(round(height * MAX_SINGLE_SECTION_WIDTH_HEIGHT_RATIO))
    width = x1 - x0
    if width <= max_width:
        return bbox
    # Keep the left edge for the left-view startup scan. This preserves the
    # clearly visible shelf and trims the occluded neighbor/side wall.
    capped_x1 = min(image_width, x0 + max_width)
    return (x0, y0, capped_x1, y1)


def _sanitize_shelf_bboxes(
    bboxes: list[tuple[int, int, int, int]],
    *,
    image_width: int,
) -> list[tuple[int, int, int, int]]:
    """Apply minimum size and non-overlap constraints to detected sections."""
    cleaned: list[tuple[int, int, int, int]] = []
    for x0, y0, x1, y1 in sorted(bboxes, key=lambda item: item[0]):
        x0 = max(0, int(x0))
        x1 = min(image_width, int(x1))
        y0 = int(y0)
        y1 = int(y1)
        width = x1 - x0
        height = y1 - y0
        if width <= 0 or height <= 0:
            continue
        if width / max(height, 1) < MIN_SECTION_WIDTH_HEIGHT_RATIO:
            continue
        if cleaned and x0 < cleaned[-1][2]:
            midpoint = int(round((cleaned[-1][2] + x0) / 2.0))
            prev = cleaned[-1]
            cleaned[-1] = (prev[0], prev[1], max(prev[0], midpoint), prev[3])
            x0 = min(x1, midpoint)
        if x1 - x0 <= 0:
            continue
        cleaned.append((x0, y0, x1, y1))
    return cleaned


def _yellow_vertical_extent(roi: np.ndarray, y0: int, image_height: int) -> tuple[int, int]:
    ys = np.where(roi > 0)[0]
    if ys.size == 0:
        return y0, min(image_height, int(image_height * 0.98))
    return max(0, int(y0 + ys.min()) - 4), min(image_height, int(y0 + ys.max()) + 4)


def _slice_occupancy_score(
    yellow_mask: np.ndarray | None,
    bbox_px: tuple[int, int, int, int],
) -> tuple[float, str]:
    if yellow_mask is None or yellow_mask.size == 0:
        return 0.0, "not_measured"
    x, y, w, h = bbox_px
    image_h, image_w = yellow_mask.shape[:2]
    x0 = max(0, x)
    x1 = min(image_w, x + w)
    y0 = max(0, int(y + h * 0.18))
    y1 = min(image_h, int(y + h * 0.92))
    if x1 <= x0 or y1 <= y0:
        return 0.0, "empty_slice"
    yellow_fraction = float((yellow_mask[y0:y1, x0:x1] > 0).mean())
    occupancy = max(0.0, min(1.0, 1.0 - yellow_fraction))
    return round(occupancy, 3), f"yellow_visible_fraction={yellow_fraction:.3f}"


def _has_yellow_occupancy_cue(
    yellow_mask: np.ndarray,
    bbox_px: tuple[int, int, int, int],
) -> bool:
    if yellow_mask is None or yellow_mask.size == 0:
        return False
    x, y, w, h = bbox_px
    image_h, image_w = yellow_mask.shape[:2]
    x0 = max(0, x)
    x1 = min(image_w, x + w)
    y0 = max(0, int(y + h * 0.12))
    y1 = min(image_h, int(y + h * 0.94))
    if x1 <= x0 or y1 <= y0:
        return False
    yellow_fraction = float((yellow_mask[y0:y1, x0:x1] > 0).mean())
    return yellow_fraction >= 0.08


def _smoothed_edge_peaks(
    projection: np.ndarray,
    *,
    percentile: float,
    min_distance_px: int,
) -> list[tuple[int, float]]:
    smooth = np.convolve(projection, np.ones(11) / 11, mode="same")
    threshold = float(np.percentile(smooth, percentile))
    peaks: list[tuple[int, float]] = []
    for index in range(5, len(smooth) - 5):
        if smooth[index] == max(smooth[index - 5 : index + 6]) and smooth[index] > threshold:
            peaks.append((index, float(smooth[index])))

    selected: list[tuple[int, float]] = []
    for index, value in sorted(peaks, key=lambda item: item[1], reverse=True):
        if all(abs(index - kept_index) > min_distance_px for kept_index, _ in selected):
            selected.append((index, value))
    return sorted(selected)


def _pick_panel_borders(
    vertical_edges: list[tuple[int, float]],
    image_width: int,
) -> tuple[int, int, int, int] | None:
    if len(vertical_edges) < 4:
        return None
    xs = [x for x, _ in vertical_edges]
    left_outer = _first_in_range(xs, image_width * 0.08, image_width * 0.20)
    left_inner = _last_in_range(xs, image_width * 0.43, image_width * 0.485)
    right_inner = _first_in_range(xs, image_width * 0.49, image_width * 0.56)
    right_outer = _last_in_range(xs, image_width * 0.80, image_width * 0.90)
    if None in (left_outer, left_inner, right_inner, right_outer):
        return _pick_panel_borders_from_strong_edges(vertical_edges, image_width)
    return int(left_outer), int(left_inner), int(right_inner), int(right_outer)


def _pick_panel_borders_from_strong_edges(
    vertical_edges: list[tuple[int, float]],
    image_width: int,
) -> tuple[int, int, int, int] | None:
    if not vertical_edges:
        return None
    max_strength = max(strength for _, strength in vertical_edges)
    strong_xs = sorted(x for x, strength in vertical_edges if strength >= max_strength * 0.48)
    if len(strong_xs) < 3:
        return None

    center_x = image_width / 2.0
    divider = min(strong_xs, key=lambda x: abs(x - center_x))
    left_candidates = [x for x in strong_xs if x < divider - image_width * 0.08]
    right_candidates = [x for x in strong_xs if x > divider + image_width * 0.08]
    if not left_candidates or not right_candidates:
        return None

    left_outer = max(left_candidates)
    right_outer = max(right_candidates)
    # Some angled shelf views expose the central divider as a single strong edge.
    # Use it as both the right edge of the left section and the left edge of the
    # right section; slice scoring is coarse enough for this first pass.
    return int(left_outer), int(divider), int(divider), int(right_outer)


def _pick_panel_vertical_extent(horizontal_edges: list[tuple[int, float]], image_height: int) -> tuple[int, int]:
    ys = [y for y, _ in horizontal_edges]
    top = _first_in_range(ys, image_height * 0.06, image_height * 0.18)
    bottom = _last_in_range(ys, image_height * 0.88, image_height * 0.98)
    return int(top if top is not None else image_height * 0.10), int(
        bottom if bottom is not None else image_height * 0.95
    )


def _first_in_range(values: list[int], low: float, high: float) -> int | None:
    matches = [value for value in values if low <= value <= high]
    return min(matches) if matches else None


def _last_in_range(values: list[int], low: float, high: float) -> int | None:
    matches = [value for value in values if low <= value <= high]
    return max(matches) if matches else None


def _section_confidence(bbox_px: tuple[int, int, int, int], frame_shape: tuple[int, int]) -> float:
    _, _, w, h = bbox_px
    image_h, image_w = frame_shape
    if image_w <= 0 or image_h <= 0:
        return 0.0
    width_ratio = w / image_w
    height_ratio = h / image_h
    confidence = 0.45 + min(width_ratio / 0.35, 1.0) * 0.25 + min(height_ratio / 0.85, 1.0) * 0.25
    return round(min(confidence, 0.95), 2)


def save_debug_overlay(frame: np.ndarray, sections: list[ShelfSection], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), draw_shelf_scan_overlay(frame, sections))
    return output
