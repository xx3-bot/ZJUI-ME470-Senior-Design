"""Task selection and pose planning for the autonomous reshelving controller."""

from __future__ import annotations

from typing import Iterable, Optional

import config
from coordinate_transformer import CoordinateTransformer
from decision.placement_opportunity_planner import PlacementOpportunityPlanner
from models import BookObservation, PlacementDecision, Pose, ShelfGap, ShelfObservation, Task


class TaskPlanner:
    def __init__(self) -> None:
        self.placement_planner = PlacementOpportunityPlanner()

    def choose_next_task(self, tasks: Iterable[Task]) -> Optional[Task]:
        pending = [task for task in tasks if task.status in {"PENDING", "LOCALIZED", "PICKED"}]
        if not pending:
            return None
        return sorted(
            pending,
            key=lambda task: (
                task.attempt_count,
                task.title,
            ),
        )[0]

    def compute_pick_pose(self, observation: BookObservation) -> Pose:
        """Compute a target gripper pose for picking a book from the return bin."""
        book_center_world = CoordinateTransformer.camera_to_world(
            observation.capture_pose,
            observation.center_x,
            observation.depth,
            observation.rel_z,
        )
        if observation.span > config.TIP_GAP:
            print(
                f"[PLAN] Warning: observed span {observation.span:.1f} mm exceeds TIP_GAP "
                f"{config.TIP_GAP:.1f} mm. Mock run will continue."
            )
        return Pose(
            x=book_center_world.x,
            y=book_center_world.y + config.TIP_DEPTH,
            z=book_center_world.z,
        )

    def choose_gap(self, task: Task, shelf: ShelfObservation, preferred_x: Optional[float]) -> Optional[ShelfGap]:
        """Choose a gap that can hold the target book."""
        feasible = [
            gap for gap in shelf.gaps if gap.width >= task.thickness + config.PLACEMENT_SIDE_CLEARANCE
        ]
        if not feasible:
            return None

        if preferred_x is None:
            return feasible[0]

        return min(feasible, key=lambda gap: abs(gap.start_x - preferred_x))

    def plan_placement(
        self, task: Task, shelf: ShelfObservation, preferred_x: Optional[float]
    ) -> PlacementDecision:
        return self.placement_planner.plan(task, shelf, preferred_x)

    def compute_place_poses(self, task: Task, shelf: ShelfObservation, gap: ShelfGap) -> tuple[Pose, Pose]:
        """Compute an approach pose and the final release pose for reshelving."""
        direction = 1 if task.zone.endswith("left") else -1
        target_x = gap.start_x + min(task.thickness / 2.0, max(gap.width - task.thickness, 0.0))
        final_z = shelf.bottom + min(
            config.PLACEMENT_BOTTOM_CLEARANCE,
            max(4.0, (shelf.height - config.BOOK_VERT_HEIGHT) / 2.0),
        )
        final_pose = Pose(
            x=target_x,
            y=shelf.depth + config.TIP_DEPTH,
            z=final_z,
        )
        approach_pose = Pose(
            x=target_x - direction * config.PLACEMENT_SIDE_CLEARANCE,
            y=final_pose.y - config.PLACEMENT_REAR_CLEARANCE,
            z=final_pose.z + 2.0,
        )
        return approach_pose, final_pose
