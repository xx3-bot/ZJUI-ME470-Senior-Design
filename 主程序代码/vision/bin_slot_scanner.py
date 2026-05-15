"""Bind OCR title hits to edge-detected physical book entities.

This is the first step toward a real bin-slot scanner:

1. OCR answers "which book is this?"
2. Edge/entity detection answers "where is the physical book body?"
3. Association binds both signals into one BookInstance.

The module is intentionally not wired into hardware control yet. It provides a
safer candidate source for the next vision iteration, where bin slot geometry
can replace the current OCR-bbox-center pick estimate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, List, Optional, Tuple

import cv2
import numpy as np

import config

from .image_preprocess import edge_mask
from .spine_detector import SpineDetector, SpineHit


BBox = Tuple[int, int, int, int]  # x1, y1, x2, y2

# Local bin-grid span hypotheses. The camera often sees only partial bottom
# grid structure, not the full bin width. Include slot widths, divider thickness,
# adjacent slot/gap widths, and common combinations.
BIN_GRID_KNOWN_SPANS_MM: Tuple[float, ...] = (5.0, 10.0, 12.5, 15.0, 20.0, 22.5, 25.0, 32.5)
BIN_CAMERA_DEPTH_PLAUSIBLE_RANGE_MM: Tuple[float, float] = (90.0, 260.0)
BIN_ARM_DEPTH_PLAUSIBLE_RANGE_MM: Tuple[float, float] = (190.0, 340.0)
BIN_GRID_ROI = (0.38, 0.70, 0.64, 0.98)  # x1, y1, x2, y2 as image fractions
TITLE_OVERLAY_LABELS = {
    "羊皮卷": "YPJ",
    "人性的弱点": "RXDRD",
    "鬼谷子": "GGZ",
    "墨菲定律": "MFDL",
    "聊斋志异": "LZZY",
    "毛泽东思想概况": "MZDSXGK",
    "习近平新时代中国特色社会主义思想概论": "XJP",
}


@dataclass(frozen=True)
class BookEntity:
    bbox: BBox
    raw_bbox: BBox
    quad: Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int], Tuple[int, int]]
    area_px: float
    aspect_ratio: float
    tilt_deg: float
    confidence: float


@dataclass(frozen=True)
class BookInstance:
    title: str
    confidence: float
    ocr_bbox: BBox
    entity_bbox: BBox
    raw_entity_bbox: BBox
    entity_quad: Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int], Tuple[int, int]]
    ocr_tilt_deg: float
    entity_tilt_deg: float
    association_score: float
    book_dimensions_mm: dict
    source: str = "ocr_edge_entity_v1"


@dataclass(frozen=True)
class BinGridSpan:
    kind: str
    x1_px: int
    x2_px: int
    width_px: int
    matched_width_mm: float
    camera_depth_mm: float
    arm_depth_mm: float
    confidence: float


def estimate_bin_grid_geometry(frame: np.ndarray) -> dict:
    """Estimate bin distance from visible local grid spans.

    This does not require the full bin width to be visible. It looks for visible
    yellow/orange bottom-grid spans and matches their pixel widths to known
    physical spans such as 10 mm slots, 12.5 mm small gaps, 22.5 mm large gaps,
    and 32.5 mm slot+gap pitch.
    """
    if frame is None or frame.size == 0:
        return {"status": "empty_frame", "spans": [], "camera_depth_mm": None, "arm_depth_mm": None}

    h, w = frame.shape[:2]
    fx = _scaled_fx_for_frame_width(w)
    x1, y1, x2, y2 = _grid_roi_px(w, h)
    roi = frame[y1:y2, x1:x2]
    mask = _yellow_bin_mask(roi)
    segments = _active_x_segments(mask, min_width_px=4)
    edge_peaks = _vertical_grid_edge_peaks(mask, x_offset=x1)

    spans: list[BinGridSpan] = []
    for start, end, width in segments:
        global_start = x1 + start
        global_end = x1 + end
        match = _best_physical_span_match(width, fx)
        if match is None:
            continue
        physical_mm, camera_depth_mm, confidence = match
        arm_depth_mm = camera_depth_mm + float(config.CAMERA_POSITION_IN_ARM_MM[0])
        spans.append(
            BinGridSpan(
                kind="yellow_segment",
                x1_px=int(global_start),
                x2_px=int(global_end),
                width_px=int(width),
                matched_width_mm=physical_mm,
                camera_depth_mm=round(camera_depth_mm, 1),
                arm_depth_mm=round(arm_depth_mm, 1),
                confidence=confidence,
            )
        )

    plausible_spans = [
        span
        for span in spans
        if BIN_ARM_DEPTH_PLAUSIBLE_RANGE_MM[0] <= span.arm_depth_mm <= BIN_ARM_DEPTH_PLAUSIBLE_RANGE_MM[1]
    ]
    best_span = max(plausible_spans, key=lambda span: span.confidence) if plausible_spans else None
    arm_depth = best_span.arm_depth_mm if best_span is not None else None
    median_arm_depth = (
        round(float(np.median([span.arm_depth_mm for span in plausible_spans])), 1)
        if plausible_spans
        else None
    )
    camera_depth = (
        round(arm_depth - float(config.CAMERA_POSITION_IN_ARM_MM[0]), 1)
        if arm_depth is not None
        else None
    )
    return {
        "status": "complete" if plausible_spans else "partial_no_plausible_depth",
        "camera_depth_mm": camera_depth,
        "arm_depth_mm": arm_depth,
        "median_arm_depth_mm": median_arm_depth,
        "selected_span": asdict(best_span) if best_span is not None else None,
        "depth_method": "visible_bin_grid_local_spans_with_camera_extrinsics",
        "fx_scaled_px": round(fx, 2),
        "camera_x_offset_mm": float(config.CAMERA_POSITION_IN_ARM_MM[0]),
        "roi_px": [x1, y1, x2, y2],
        "known_spans_mm": list(BIN_GRID_KNOWN_SPANS_MM),
        "camera_depth_plausible_range_mm": list(BIN_CAMERA_DEPTH_PLAUSIBLE_RANGE_MM),
        "arm_depth_plausible_range_mm": list(BIN_ARM_DEPTH_PLAUSIBLE_RANGE_MM),
        "edge_peaks_px": edge_peaks,
        "spans": [asdict(span) for span in spans],
    }


def draw_bin_grid_geometry(frame: np.ndarray, grid: dict) -> np.ndarray:
    """Draw visible bin grid spans and matched metric hypotheses."""
    annotated = frame.copy()
    x1, y1, x2, y2 = [int(value) for value in grid.get("roi_px", [0, 0, 0, 0])]
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 255, 0), 2)
    for x in grid.get("edge_peaks_px", []):
        cv2.line(annotated, (int(x), y1), (int(x), y2), (0, 255, 255), 2)

    selected = grid.get("selected_span") or {}
    selected_key = (
        int(selected.get("x1_px", -1)),
        int(selected.get("x2_px", -1)),
        int(selected.get("width_px", -1)),
    )
    top_spans = sorted(
        grid.get("spans", []),
        key=lambda item: float(item.get("confidence", 0.0)),
        reverse=True,
    )[:4]
    label_row = 0
    for span in top_spans:
        sx1 = int(span["x1_px"])
        sx2 = int(span["x2_px"])
        width_px = int(span["width_px"])
        matched_mm = float(span["matched_width_mm"])
        arm_depth_mm = float(span["arm_depth_mm"])
        is_selected = (sx1, sx2, width_px) == selected_key
        color = (0, 255, 0) if is_selected else (0, 180, 255)
        thickness = 3 if is_selected else 1
        cv2.rectangle(annotated, (sx1, y1 + 15), (sx2, y2 - 15), color, 2)
        if is_selected:
            label = f"selected {width_px}px={matched_mm:g}mm armX={arm_depth_mm:.0f}"
            _put_label(annotated, sx1, max(32, y1 - 38), label)
        else:
            cv2.line(annotated, (sx1, y1 + 10), (sx1, y1 + 35), color, thickness)
            cv2.line(annotated, (sx2, y1 + 10), (sx2, y1 + 35), color, thickness)
            cv2.putText(
                annotated,
                f"{matched_mm:g}mm",
                (max(8, x1), min(y2 - 8, y1 + 28 + label_row * 22)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
                cv2.LINE_AA,
            )
            label_row += 1
    if grid.get("arm_depth_mm") is not None:
        _put_label(annotated, max(8, x1), max(28, y1 - 8), f"arm X ~ {grid['arm_depth_mm']} mm")
    return annotated


def detect_book_instances_in_frame(frame: np.ndarray) -> list[dict]:
    """Return OCR-title hits bound to edge-detected physical book entities."""
    if frame is None or frame.size == 0:
        return []

    hits = SpineDetector.instance().detect(frame)
    entities = detect_book_entities(frame)
    instances: list[BookInstance] = []
    used_entity_indices: set[int] = set()

    for hit in hits:
        match = _best_entity_for_hit(hit, entities, used_entity_indices)
        if match is None:
            continue
        entity_index, entity, score = match
        used_entity_indices.add(entity_index)
        instances.append(
            BookInstance(
                title=hit.matched_title,
                confidence=float(hit.ocr_score),
                ocr_bbox=hit.bbox,
                entity_bbox=entity.bbox,
                raw_entity_bbox=entity.raw_bbox,
                entity_quad=entity.quad,
                ocr_tilt_deg=float(hit.tilt_deg),
                entity_tilt_deg=float(entity.tilt_deg),
                association_score=float(score),
                book_dimensions_mm=dict(config.get_book_dimensions_mm(hit.matched_title)),
            )
        )

    return [asdict(instance) for instance in instances]


def detect_book_entities(frame: np.ndarray) -> list[BookEntity]:
    """Detect tall physical book-like entities from cleaned Canny edges."""
    edges = edge_mask(frame, low_threshold=40, high_threshold=120, close_kernel=(5, 5))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    frame_h, frame_w = frame.shape[:2]
    min_h = frame_h * 0.08
    min_area = frame_w * frame_h * 0.00001

    entities: list[BookEntity] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        raw_bbox = (int(x), int(y), int(x + w), int(y + h))
        area = float(cv2.contourArea(contour))
        if h < min_h or w < 8 or area < min_area:
            continue
        aspect = float(h / max(w, 1))
        if aspect < 1.5:
            continue
        confidence = _entity_confidence(w, h, area, frame.shape[:2])
        refined_bbox = _refined_bbox_from_edge_pixels(contour, edges, raw_bbox)
        quad = _bbox_quad(refined_bbox)
        entities.append(
            BookEntity(
                bbox=refined_bbox,
                raw_bbox=raw_bbox,
                quad=quad,
                area_px=area,
                aspect_ratio=aspect,
                tilt_deg=_contour_tilt_deg(contour),
                confidence=confidence,
            )
        )

    return sorted(entities, key=lambda entity: (entity.confidence, entity.area_px), reverse=True)


def draw_book_instances(frame: np.ndarray, instances: Iterable[dict]) -> np.ndarray:
    """Draw cleaned edges, entity quads, OCR boxes, and title/tilt labels."""
    annotated = frame.copy()
    edges = edge_mask(frame, low_threshold=40, high_threshold=120, close_kernel=(5, 5))
    edge_color = np.zeros_like(annotated)
    edge_color[edges > 0] = (0, 255, 255)
    annotated = cv2.addWeighted(annotated, 0.86, edge_color, 0.55, 0)
    for index, instance in enumerate(instances, start=1):
        ex1, ey1, ex2, ey2 = _tuple_bbox(instance["entity_bbox"])
        ox1, oy1, ox2, oy2 = _tuple_bbox(instance["ocr_bbox"])
        quad = np.asarray(instance.get("entity_quad") or [], dtype=np.int32)
        if quad.shape == (4, 2):
            cv2.polylines(annotated, [quad.reshape(-1, 1, 2)], True, (255, 180, 0), 5)
        else:
            cv2.rectangle(annotated, (ex1, ey1), (ex2, ey2), (255, 180, 0), 3)
        cv2.rectangle(annotated, (ox1, oy1), (ox2, oy2), (0, 255, 0), 3)
        dims = instance.get("book_dimensions_mm", {})
        profile = dims.get("size_profile", "?")
        title = str(instance.get("title", "book"))
        title_label = TITLE_OVERLAY_LABELS.get(title, f"B{index}")
        label = (
            f"{index}. {title_label} "
            f"ocr={float(instance['ocr_tilt_deg']):+.1f} "
            f"entity={float(instance['entity_tilt_deg']):+.1f} "
            f"{profile}"
        )
        _put_label(annotated, ex1, max(24, ey1 - 8), label)
    return annotated


def _best_entity_for_hit(
    hit: SpineHit,
    entities: list[BookEntity],
    used_entity_indices: set[int],
) -> Optional[tuple[int, BookEntity, float]]:
    best: Optional[tuple[int, BookEntity, float]] = None
    for index, entity in enumerate(entities):
        if index in used_entity_indices:
            continue
        score = _association_score(hit.bbox, entity.bbox)
        if score <= 0:
            continue
        if best is None or score > best[2]:
            best = (index, entity, score)
    return best


def _association_score(ocr_bbox: BBox, entity_bbox: BBox) -> float:
    ox1, oy1, ox2, oy2 = ocr_bbox
    ex1, ey1, ex2, ey2 = entity_bbox
    ocx = (ox1 + ox2) / 2.0
    ocy = (oy1 + oy2) / 2.0
    ecx = (ex1 + ex2) / 2.0
    ew = max(ex2 - ex1, 1)
    eh = max(ey2 - ey1, 1)

    center_inside = ex1 <= ocx <= ex2 and ey1 <= ocy <= ey2
    x_overlap = max(0, min(ox2, ex2) - max(ox1, ex1)) / max(ox2 - ox1, 1)
    y_overlap = max(0, min(oy2, ey2) - max(oy1, ey1)) / max(oy2 - oy1, 1)
    x_closeness = max(0.0, 1.0 - abs(ocx - ecx) / ew)

    if not center_inside and x_overlap < 0.35:
        return 0.0
    score = 0.45 * float(center_inside) + 0.25 * x_overlap + 0.15 * y_overlap + 0.15 * x_closeness
    # Prefer entities large enough to plausibly be a full book body.
    if eh > ew * 3.0:
        score += 0.05
    return min(score, 1.0)


def _entity_confidence(w: int, h: int, area: float, frame_shape: tuple[int, int]) -> float:
    frame_h, frame_w = frame_shape
    height_score = min(h / max(frame_h * 0.55, 1), 1.0)
    aspect_score = min((h / max(w, 1)) / 6.0, 1.0)
    area_score = min(area / max(frame_w * frame_h * 0.015, 1), 1.0)
    return round(0.35 * height_score + 0.35 * aspect_score + 0.30 * area_score, 3)


def _contour_tilt_deg(contour: np.ndarray) -> float:
    rect = cv2.minAreaRect(contour)
    (_cx, _cy), (rw, rh), angle = rect
    if rw <= 0 or rh <= 0:
        return 0.0
    # Normalize so 0 means vertical book body; positive means top leaning right.
    if rh >= rw:
        tilt = float(angle)
    else:
        tilt = float(angle + 90.0)
    while tilt > 45.0:
        tilt -= 90.0
    while tilt < -45.0:
        tilt += 90.0
    return tilt


def _refined_bbox_from_edge_pixels(
    contour: np.ndarray,
    edges: np.ndarray,
    fallback: BBox,
) -> BBox:
    """Trim coarse contour bounds using edge-pixel percentiles inside it.

    The raw contour can include shadows or connected background strokes. Taking
    robust percentiles of the cleaned edge pixels keeps the main book-body
    structure while discarding sparse outliers.
    """
    mask = np.zeros(edges.shape, dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, -1)
    ys, xs = np.where((edges > 0) & (mask > 0))
    if len(xs) < 50:
        return fallback
    x1 = int(round(np.percentile(xs, 1)))
    x2 = int(round(np.percentile(xs, 99)))
    y1 = int(round(np.percentile(ys, 1)))
    y2 = int(round(np.percentile(ys, 99)))
    if x2 <= x1 or y2 <= y1:
        return fallback
    return x1, y1, x2, y2


def _bbox_quad(
    bbox: BBox,
) -> Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
    x1, y1, x2, y2 = bbox
    return ((x1, y1), (x2, y1), (x2, y2), (x1, y2))


def _scaled_fx_for_frame_width(frame_width_px: int) -> float:
    reference_width = float(config.RGB_FRAME_WIDTH or 1280)
    return float(config.RGB_INTRINSICS_FX_PX) * float(frame_width_px) / reference_width


def _grid_roi_px(frame_width: int, frame_height: int) -> BBox:
    x1f, y1f, x2f, y2f = BIN_GRID_ROI
    return (
        int(round(frame_width * x1f)),
        int(round(frame_height * y1f)),
        int(round(frame_width * x2f)),
        int(round(frame_height * y2f)),
    )


def _yellow_bin_mask(roi: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([8, 45, 45]), np.array([45, 255, 255]))
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=1,
    )
    return cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 9)),
        iterations=1,
    )


def _active_x_segments(mask: np.ndarray, *, min_width_px: int) -> list[tuple[int, int, int]]:
    projection = mask.sum(axis=0).astype(float) / 255.0
    if not np.any(projection > 0):
        return []
    threshold = max(8.0, float(np.percentile(projection[projection > 0], 30)))
    active = projection > threshold
    segments: list[tuple[int, int, int]] = []
    start: int | None = None
    for index, is_active in enumerate(active):
        if is_active and start is None:
            start = index
        at_end = index == len(active) - 1
        if (not is_active or at_end) and start is not None:
            end = index - 1 if not is_active else index
            width = end - start + 1
            if width >= min_width_px:
                segments.append((start, end, width))
            start = None
    return segments


def _vertical_grid_edge_peaks(mask: np.ndarray, *, x_offset: int) -> list[int]:
    edges = cv2.Canny(mask, 50, 150)
    projection = edges.sum(axis=0).astype(float) / 255.0
    if not np.any(projection > 0):
        return []
    smooth = np.convolve(projection, np.ones(7) / 7, mode="same")
    threshold = max(4.0, float(np.percentile(smooth, 88)))
    peaks: list[tuple[int, float]] = []
    for index, value in sorted(enumerate(smooth), key=lambda item: item[1], reverse=True):
        if value < threshold:
            break
        if all(abs(index - existing) > 10 for existing, _score in peaks):
            peaks.append((index, float(value)))
        if len(peaks) >= 24:
            break
    return [x_offset + index for index, _score in sorted(peaks)]


def _best_physical_span_match(width_px: int, fx_px: float) -> tuple[float, float, float] | None:
    best: tuple[float, float, float] | None = None
    camera_x = float(config.CAMERA_POSITION_IN_ARM_MM[0])
    preferred_arm_depth = float(config.BIN_PICK_DEPTH_MM)
    for physical_mm in BIN_GRID_KNOWN_SPANS_MM:
        camera_depth_mm = fx_px * physical_mm / max(width_px, 1)
        arm_depth_mm = camera_depth_mm + camera_x
        if not (
            BIN_CAMERA_DEPTH_PLAUSIBLE_RANGE_MM[0]
            <= camera_depth_mm
            <= BIN_CAMERA_DEPTH_PLAUSIBLE_RANGE_MM[1]
        ):
            continue
        if not (
            BIN_ARM_DEPTH_PLAUSIBLE_RANGE_MM[0]
            <= arm_depth_mm
            <= BIN_ARM_DEPTH_PLAUSIBLE_RANGE_MM[1]
        ):
            continue
        confidence = max(0.0, 1.0 - abs(arm_depth_mm - preferred_arm_depth) / 80.0)
        # Prefer larger physical spans when the depth fit is similarly plausible;
        # small 5 mm divider detections are useful but noisier.
        confidence += min(physical_mm / 32.5, 1.0) * 0.08
        candidate = (physical_mm, camera_depth_mm, round(min(confidence, 1.0), 3))
        if best is None or candidate[2] > best[2]:
            best = candidate
    return best


def _tuple_bbox(value: object) -> BBox:
    x1, y1, x2, y2 = value  # type: ignore[misc]
    return int(x1), int(y1), int(x2), int(y2)


def _put_label(frame: np.ndarray, x: int, y: int, text: str) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.68
    thickness = 2
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    cv2.rectangle(frame, (x, y - th - 7), (x + tw + 8, y + 4), (0, 0, 0), -1)
    cv2.putText(frame, text, (x + 4, y - 3), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)
