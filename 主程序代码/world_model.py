"""Dynamic world model maintained by the control system during runtime."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models import BookObservation, PlacementDecision, Pose, ShelfObservation


class WorldModel:
    def __init__(self) -> None:
        self.bin_books: Dict[str, BookObservation] = {}
        self.latest_shelves: Dict[str, ShelfObservation] = {}
        self.zone_slot_bases: Dict[str, float] = {}
        self.latest_placement_decisions: Dict[str, PlacementDecision] = {}
        self.placed_books: Dict[str, Pose] = {}
        self.blocked_reasons: Dict[str, str] = {}
        self.demo_bin_books: Dict[str, dict] = {}
        self.demo_planned_placements: Dict[str, dict] = {}
        self.demo_shelf_occupancy: List[dict] = []
        self.demo_shelf_model: dict[str, Any] = {}
        self.demo_shelf_slots: List[dict[str, Any]] = []

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

    def remember_demo_bin_book(
        self,
        *,
        title: str,
        pick: tuple[float, float, float],
        confidence: float,
        bbox: tuple,
        tilt_deg: float | None = None,
        book_dimensions_mm: dict | None = None,
    ) -> None:
        """Record a detected-books-loop candidate without forcing old BookObservation shape."""
        self.demo_bin_books[title] = {
            "title": title,
            "pick": [float(value) for value in pick],
            "confidence": float(confidence),
            "bbox": list(bbox),
            "tilt_deg": None if tilt_deg is None else float(tilt_deg),
            "book_dimensions_mm": dict(book_dimensions_mm or {}),
        }

    def remember_demo_planned_placement(
        self,
        *,
        title: str,
        place: tuple[float, float, float],
        source: str,
        shelf_slot: dict[str, Any] | None = None,
    ) -> None:
        slot_index = len(self.demo_planned_placements) + 1
        self.demo_planned_placements[title] = {
            "title": title,
            "place": [float(value) for value in place],
            "source": source,
            "slot": f"demo shelf slot {slot_index}",
            "shelf_slot": dict(shelf_slot or {}),
        }

    def remember_demo_shelf_occupancy(
        self,
        *,
        title: str,
        place: tuple[float, float, float],
        command_start: int,
        command_end: int,
        shelf_slot: dict[str, Any] | None = None,
    ) -> None:
        slot_record = dict(shelf_slot or {})
        self.demo_shelf_occupancy.append(
            {
                "title": title,
                "place": [float(value) for value in place],
                "x": float(place[0]),
                "slot": f"demo shelf slot {len(self.demo_shelf_occupancy) + 1}",
                "shelf_slot": slot_record,
                "command_start": int(command_start),
                "command_end": int(command_end),
            }
        )
        if slot_record.get("slot_id"):
            self.mark_demo_shelf_slot_occupied(
                str(slot_record["slot_id"]),
                title=title,
                place=place,
            )
        self.remember_placed_book(title, Pose(*place))

    def initialize_demo_shelf_model(self, shelf_model: dict[str, Any]) -> None:
        """Freeze startup-scan shelf slices as the demo shelf world model."""
        self.demo_shelf_model = dict(shelf_model or {})
        slots = list(self.demo_shelf_model.get("slots", []))
        self.demo_shelf_slots = [dict(slot) for slot in slots]

    def next_demo_shelf_slot(self, *, preferred_index: int = 0) -> dict[str, Any] | None:
        """Return the best unoccupied initialized shelf slot for the next book."""
        free_slots = [
            slot
            for slot in self.demo_shelf_slots
            if not slot.get("occupied") and str(slot.get("status")) in {"free_candidate", "unknown"}
        ]
        if not free_slots:
            return None
        free_slots.sort(
            key=lambda slot: (
                -float(slot.get("score", 0.0)),
                int(slot.get("rank", 9999)),
                str(slot.get("section_id", "")),
                int(slot.get("slice_index", 9999)),
            )
        )
        index = min(max(preferred_index, 0), len(free_slots) - 1)
        return dict(free_slots[index])

    def mark_demo_shelf_slot_occupied(
        self,
        slot_id: str,
        *,
        title: str,
        place: tuple[float, float, float],
    ) -> None:
        for slot in self.demo_shelf_slots:
            if str(slot.get("slot_id")) == slot_id:
                slot["occupied"] = True
                slot["occupied_by"] = title
                slot["occupied_place"] = [float(value) for value in place]
                break

    def demo_summary(self) -> dict:
        return {
            "bin_books": list(self.demo_bin_books.keys()),
            "planned_placements": [
                {
                    "title": item["title"],
                    "place": item["place"],
                    "source": item["source"],
                    "shelf_slot": item.get("shelf_slot", {}),
                }
                for item in self.demo_planned_placements.values()
            ],
            "planned_placements_human": [
                f"{item['title']} -> {item['slot']}"
                for item in self.demo_planned_placements.values()
            ],
            "occupied_demo_shelf_x": [item["x"] for item in self.demo_shelf_occupancy],
            "occupied_demo_shelf_slots": [
                f"{item['slot']} ({item['title']})"
                for item in self.demo_shelf_occupancy
            ],
            "initialized_shelf_model": {
                "source": self.demo_shelf_model.get("source"),
                "slot_count": len(self.demo_shelf_slots),
                "free_slot_count": len(
                    [slot for slot in self.demo_shelf_slots if not slot.get("occupied")]
                ),
                "occupied_slots": [
                    {
                        "slot_id": slot.get("slot_id"),
                        "title": slot.get("occupied_by"),
                    }
                    for slot in self.demo_shelf_slots
                    if slot.get("occupied")
                ],
            },
            "blocked_reasons": dict(self.blocked_reasons),
        }
