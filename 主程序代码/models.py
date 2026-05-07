"""Shared data models used by the control, planning, and mock interface layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class BookObservation:
    title: str
    rel_x: float
    rel_y: float
    rel_z: float
    left_edge: float
    right_edge: float
    depth: float
    confidence: float
    capture_pose: Pose

    @property
    def span(self) -> float:
        return abs(self.right_edge - self.left_edge)

    @property
    def center_x(self) -> float:
        return (self.left_edge + self.right_edge) / 2.0


@dataclass
class ShelfGap:
    gap_id: int
    start_x: float
    end_x: float
    width: float
    left_boundary_type: str = "unknown"
    right_boundary_type: str = "unknown"
    confidence: float = 1.0


@dataclass
class ShelfObservation:
    zone: str
    depth: float
    bottom: float
    top: float
    height: float
    gaps: List[ShelfGap]
    tilted_books: bool
    capture_pose: Pose


@dataclass
class PlacementOpportunity:
    gap_id: int
    mode: str
    target_x: float
    fit_margin: float
    left_clearance: float
    right_clearance: float
    left_boundary_type: str
    right_boundary_type: str
    distance_to_preferred: float
    is_tight: bool
    confidence: float = 1.0


@dataclass
class ScoredPlacementOpportunity:
    opportunity: PlacementOpportunity
    score: float
    rejected: bool
    reason: str


@dataclass
class PlacementDecision:
    selected: Optional[PlacementOpportunity]
    scored_candidates: List[ScoredPlacementOpportunity]
    approach_pose: Optional[Pose]
    final_pose: Optional[Pose]
    reason: str


@dataclass
class BookCatalogEntry:
    title: str
    zone: str
    thickness: float
    nominal_height_min: float
    nominal_height_max: float


@dataclass
class Task:
    title: str
    zone: str
    thickness: float
    status: str = "PENDING"
    attempt_count: int = 0
    failure_reason: Optional[str] = None
    last_book_observation: Optional[BookObservation] = None
    pick_ready_pose: Optional[Pose] = None
    selected_gap_id: Optional[int] = None
    last_decision: Optional[PlacementDecision] = None
    notes: List[str] = field(default_factory=list)
