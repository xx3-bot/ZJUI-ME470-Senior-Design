"""Dynamic world model maintained by the control system during runtime."""

from __future__ import annotations

from typing import Dict, List, Optional

from models import BookObservation, PlacementDecision, Pose, ShelfObservation


class WorldModel:
    def __init__(self) -> None:
        self.bin_books: Dict[str, BookObservation] = {}
        self.latest_shelves: Dict[str, ShelfObservation] = {}
        self.zone_slot_bases: Dict[str, float] = {}
        self.latest_placement_decisions: Dict[str, PlacementDecision] = {}
        self.placed_books: Dict[str, Pose] = {}
        self.blocked_reasons: Dict[str, str] = {}

    def remember_book(self, observation: BookObservation) -> bool:
        existing = self.bin_books.get(observation.title)
        if existing and existing.confidence >= observation.confidence:
            return False
        self.bin_books[observation.title] = observation
        return True

    def get_book(self, title: str) -> Optional[BookObservation]:
        return self.bin_books.get(title)

    def remember_shelf(self, observation: ShelfObservation) -> None:
        self.latest_shelves[observation.zone] = observation
        if observation.zone not in self.zone_slot_bases and observation.gaps:
            self.zone_slot_bases[observation.zone] = observation.gaps[0].start_x

    def get_shelf(self, zone: str) -> Optional[ShelfObservation]:
        return self.latest_shelves.get(zone)

    def get_zone_base(self, zone: str) -> Optional[float]:
        return self.zone_slot_bases.get(zone)

    def update_zone_base(self, zone: str, placed_x: float, thickness: float) -> None:
        direction = 1 if zone.endswith("left") else -1
        self.zone_slot_bases[zone] = placed_x + direction * thickness
        print(f"[WORLD] Updated zone base for {zone} to X={self.zone_slot_bases[zone]:.1f}.")

    def remember_placement_decision(self, title: str, decision: PlacementDecision) -> None:
        self.latest_placement_decisions[title] = decision

    def remember_placed_book(self, title: str, final_pose: Pose) -> None:
        self.placed_books[title] = final_pose

    def remember_blocked_reason(self, title: str, reason: str) -> None:
        self.blocked_reasons[title] = reason

    def pending_titles(self) -> List[str]:
        return list(self.bin_books.keys())
