"""Static catalog and task management for the autonomous reshelving workflow."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from models import BookCatalogEntry, Task


class DatabaseManager:
    """Represents the control-side view of the catalog and task list.

    For now this is a local in-memory stand-in for the real database-backed module.
    The perception side only needs to return book titles. The control system uses
    the title to query this catalog and obtain the target shelf zone and nominal
    book thickness.
    """

    def __init__(self) -> None:
        self.catalog: Dict[str, BookCatalogEntry] = {
            "Control Systems": BookCatalogEntry(
                title="Control Systems",
                zone="A_left",
                thickness=32.0,
                nominal_height_min=80.0,
                nominal_height_max=260.0,
            ),
            "Robotics Dynamics": BookCatalogEntry(
                title="Robotics Dynamics",
                zone="A_right",
                thickness=28.0,
                nominal_height_min=80.0,
                nominal_height_max=260.0,
            ),
            "Microcontrollers": BookCatalogEntry(
                title="Microcontrollers",
                zone="B_left",
                thickness=24.0,
                nominal_height_min=320.0,
                nominal_height_max=520.0,
            ),
            "Signals and Systems": BookCatalogEntry(
                title="Signals and Systems",
                zone="B_right",
                thickness=30.0,
                nominal_height_min=320.0,
                nominal_height_max=520.0,
            ),
        }
        self.tasks: Dict[str, Task] = {}

    def create_tasks_from_titles(self, titles: Iterable[str]) -> List[Task]:
        """Build pending tasks from the scanned book titles."""
        created: List[Task] = []
        for title in titles:
            entry = self.catalog.get(title)
            if not entry:
                print(f"[DB] Title '{title}' is not in the catalog, skipping task creation.")
                continue
            if title in self.tasks:
                continue

            task = Task(title=entry.title, zone=entry.zone, thickness=entry.thickness)
            self.tasks[title] = task
            created.append(task)
            print(f"[DB] Created task for '{title}' -> target zone {entry.zone}.")
        return created

    def get_task(self, title: str) -> Optional[Task]:
        return self.tasks.get(title)

    def pending_tasks(self) -> List[Task]:
        return [task for task in self.tasks.values() if task.status != "DONE"]

    def mark_done(self, title: str) -> None:
        if title in self.tasks:
            self.tasks[title].status = "DONE"

    def get_catalog_entry(self, title: str) -> Optional[BookCatalogEntry]:
        return self.catalog.get(title)
