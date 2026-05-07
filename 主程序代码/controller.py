"""State-machine based control system for the autonomous reshelving demo."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable, List, Optional

import config
import motion_adapter
import perception_adapter
from coordinate_transformer import CoordinateTransformer
from decision.db_manager import DatabaseManager
from decision.task_planner import TaskPlanner
from models import BookObservation, Pose, ShelfGap, ShelfObservation, Task
from world_model import WorldModel


class RobotControlSystem:
    def __init__(self) -> None:
        self.db = DatabaseManager()
        self.planner = TaskPlanner()
        self.transformer = CoordinateTransformer()
        self.world_model = WorldModel()
        self.current_pose = Pose(*config.INITIAL_GRIP_POS)
        self.system_home_pose = Pose(*config.INITIAL_GRIP_POS)
        self.state = "BOOT"

    def run(self) -> None:
        self._load_hyperparameters()
        self.current_pose = Pose(*config.INITIAL_GRIP_POS)
        self.system_home_pose = Pose(*config.INITIAL_GRIP_POS)

        if config.SIM_MODE and config.PICK_PLACE_ONLY_MODE:
            self._transition("PICK_PLACE_ONLY")
            self.run_pick_place_only_cycle()
            return

        self._transition("GLOBAL_SCAN_BIN")
        self.perform_global_bin_scan()

        while True:
            task = self.planner.choose_next_task(self.db.pending_tasks())
            if task is None:
                unresolved = [pending for pending in self.db.pending_tasks() if pending.status != "DONE"]
                if unresolved:
                    pending_titles = [pending.title for pending in unresolved]
                    answer = self._ask_yes_no(
                        f"[CONTROL] Unresolved tasks remain {pending_titles}. Repeat global scan? (Yes/No): "
                    )
                    if answer:
                        self._transition("GLOBAL_RESCAN_BIN")
                        self.perform_global_bin_scan()
                        for unresolved_task in unresolved:
                            if unresolved_task.status in {"FAILED", "BLOCKED"}:
                                unresolved_task.status = "PENDING"
                                unresolved_task.failure_reason = None
                        continue
                    self._transition("STOPPED_BY_OPERATOR")
                    print("[CONTROL] Task stopped by operator.")
                    return
                self._transition("FINISHED")
                print("[CONTROL] All tasks are complete.")
                return

            self._transition(f"SELECT_TASK -> {task.title}")
            success = self.execute_task(task)
            if success:
                continue

            pending_titles = [pending.title for pending in self.db.pending_tasks()]
            answer = self._ask_yes_no(
                f"[CONTROL] Pending tasks remain {pending_titles}. Repeat global scan? (Yes/No): "
            )
            if answer:
                self._transition("GLOBAL_RESCAN_BIN")
                self.perform_global_bin_scan()
            else:
                self._transition("STOPPED_BY_OPERATOR")
                print("[CONTROL] Task stopped by operator.")
                return

    def _load_hyperparameters(self) -> None:
        if config.SIM_MODE:
            config.load_default_hyperparameters()
            print("[CONTROL] Using hardcoded hyperparameters for SIM_MODE.")
            print(f"[CONFIG] Initial gripper pose = {config.INITIAL_GRIP_POS}")
            return

        while True:
            raw = input(
                "Please input 11 hyperparameters: "
                "ARM_LENGTH SCAN_ARC OFFSET_X OFFSET_Y ORIENTATION "
                "TIP_GAP TIP_DEPTH SAMPLE_RATE_MS BOOK_VERT_HEIGHT SHELF_H_MIN SHELF_H_MAX\n> "
            )
            if config.parse_hyperparameters(raw):
                break
        input("Hyperparameters loaded. Press Enter to start the control workflow...")

    def perform_global_bin_scan(self) -> None:
        print("[CONTROL] Starting global return-bin scan.")
        discovered_titles: List[str] = []
        scan_height = config.BOOK_VERT_HEIGHT if config.BOOK_VERT_HEIGHT > 0.0 else self.system_home_pose.z
        for scan_pose in self.transformer.calculate_arc_points(z=scan_height):
            self._move_to(scan_pose)
            camera_pose = self.transformer.get_camera_pose(self.current_pose)
            capture_pose = Pose(camera_pose.x, camera_pose.y, camera_pose.z)
            results = perception_adapter.scan_bin_books(capture_pose)
            self._wait_sample_interval()
            for raw in results:
                observation = BookObservation(
                    title=raw["title"],
                    rel_x=raw["rel_x"],
                    rel_y=raw["rel_y"],
                    rel_z=raw["rel_z"],
                    left_edge=raw["left_edge"],
                    right_edge=raw["right_edge"],
                    depth=raw["depth"],
                    confidence=raw["confidence"],
                    capture_pose=capture_pose,
                )
                if self.world_model.remember_book(observation):
                    discovered_titles.append(observation.title)
                    world_center = self.transformer.camera_to_world(
                        capture_pose,
                        observation.center_x,
                        observation.depth,
                        observation.rel_z,
                    )
                    print(
                        "[CONTROL] New book discovered: "
                        f"{observation.title} | capture_pose={capture_pose} | world_center={world_center}"
                    )
        self.db.create_tasks_from_titles(discovered_titles)
        self._move_to(self.system_home_pose)

    def execute_task(self, task: Task) -> bool:
        task.attempt_count += 1
        task.failure_reason = None
        self._transition("LOCALIZE_BOOK")
        observation = self.localize_book_for_pick(task)
        if observation is None:
            self._mark_task_failed(task, "failed to localize target book after repeated scans")
            return False

        task.last_book_observation = observation
        task.status = "LOCALIZED"
        self._transition("PICK_BOOK")
        if not self.pick_book(task):
            return False
        task.status = "PICKED"

        self._transition("RETURN_TO_PICK_READY")
        if task.pick_ready_pose is not None:
            if not self._move_to(task.pick_ready_pose):
                self._mark_task_failed(task, "failed to return to pick-ready pose")
                return False

        self._transition("SCAN_SHELF")
        shelf = self.find_target_shelf(task)
        if shelf is None:
            self._mark_task_failed(task, f"failed to locate target shelf zone '{task.zone}'")
            return False

        self._transition("PLACE_BOOK")
        if not self.place_book(task, shelf):
            return False
        task.status = "PLACE_PLANNED"

        self._transition("TILT_CHECK")
        self.handle_tilt_check(shelf)

        self.db.mark_done(task.title)
        task.status = "DONE"
        self._transition("RETURN_HOME")
        if not self._move_to(self.system_home_pose):
            self._mark_task_failed(task, "failed to return to home pose after placement")
            return False
        print(f"[CONTROL] Task completed: {task.title}")
        return True

    def localize_book_for_pick(self, task: Task) -> Optional[BookObservation]:
        for attempt in range(1, config.BOOK_RESCAN_LIMIT + 2):
            print(f"[CONTROL] Localizing '{task.title}' in the return bin. Attempt {attempt}.")
            scan_height = config.BOOK_VERT_HEIGHT if config.BOOK_VERT_HEIGHT > 0.0 else self.system_home_pose.z
            for scan_pose in self.transformer.calculate_arc_points(z=scan_height):
                self._move_to(scan_pose)
                task.pick_ready_pose = self.current_pose
                camera_pose = self.transformer.get_camera_pose(self.current_pose)
                capture_pose = Pose(camera_pose.x, camera_pose.y, camera_pose.z)
                raw = perception_adapter.locate_book(task.title, capture_pose)
                self._wait_sample_interval()
                if raw is None:
                    continue

                observation = BookObservation(
                    title=raw["title"],
                    rel_x=raw["rel_x"],
                    rel_y=raw["rel_y"],
                    rel_z=raw["rel_z"],
                    left_edge=raw["left_edge"],
                    right_edge=raw["right_edge"],
                    depth=raw["depth"],
                    confidence=raw["confidence"],
                    capture_pose=capture_pose,
                )
                self.world_model.remember_book(observation)
                print(
                    "[CONTROL] Localized target book with pose-stamped observation: "
                    f"title={observation.title}, capture_pose={capture_pose}, "
                    f"left_edge={observation.left_edge:.1f}, right_edge={observation.right_edge:.1f}, "
                    f"depth={observation.depth:.1f}"
                )
                return observation
        return None

    def pick_book(self, task: Task) -> bool:
        if task.last_book_observation is None:
            self._mark_task_failed(task, "pick requested without localized observation")
            return False
        pick_pose = self.planner.compute_pick_pose(task.last_book_observation)
        print(
            "[CONTROL] Pick planning result: "
            f"pick_ready_pose={task.pick_ready_pose}, target_pick_pose={pick_pose}"
        )
        if not self._move_to(pick_pose):
            self._mark_task_failed(task, "failed to move to pick pose")
            return False
        if not motion_adapter.gripper_command("CLOSE"):
            self._mark_task_failed(task, "gripper close command failed")
            return False
        return True

    def find_target_shelf(self, task: Task) -> Optional[ShelfObservation]:
        scan_x = 0.0
        scan_y = config.ARM_LENGTH
        for attempt in range(1, config.SHELF_RESCAN_LIMIT + 2):
            scan_poses = self.transformer.calculate_vertical_scan_points(
                x=scan_x,
                y=scan_y,
                z_min=config.SHELF_H_MIN,
                z_max=config.SHELF_H_MAX,
            )
            print(
                f"[CONTROL] Scanning shelves for zone {task.zone}. Attempt {attempt}. "
                f"Poses: {self.transformer.describe_pose_sequence(scan_poses)}"
            )
            for scan_pose in scan_poses:
                self._move_to(scan_pose)
                camera_pose = self.transformer.get_camera_pose(self.current_pose)
                capture_pose = Pose(camera_pose.x, camera_pose.y, camera_pose.z)
                raw_shelves = perception_adapter.scan_shelves(capture_pose)
                self._wait_sample_interval()
                observations = [self._build_shelf_observation(raw, capture_pose) for raw in raw_shelves]
                for observation in observations:
                    self.world_model.remember_shelf(observation)
                    print(
                        "[CONTROL] Shelf observation stored: "
                        f"zone={observation.zone}, depth={observation.depth:.1f}, "
                        f"bottom={observation.bottom:.1f}, top={observation.top:.1f}, "
                        f"gap_count={len(observation.gaps)}"
                    )
                    if observation.zone == task.zone:
                        return observation
        return None

    def place_book(self, task: Task, shelf: ShelfObservation) -> bool:
        preferred_x = self.world_model.get_zone_base(task.zone)
        decision = self.planner.plan_placement(task, shelf, preferred_x)
        task.last_decision = decision
        self.world_model.remember_placement_decision(task.title, decision)

        if decision.selected is None or decision.approach_pose is None or decision.final_pose is None:
            task.status = "BLOCKED"
            task.failure_reason = decision.reason
            self.world_model.remember_blocked_reason(task.title, decision.reason)
            print(
                f"[CONTROL] No feasible placement found for '{task.title}' in zone {task.zone}. "
                f"Reason: {decision.reason}"
            )
            return False

        approach_pose = decision.approach_pose
        final_pose = decision.final_pose
        task.selected_gap_id = decision.selected.gap_id
        print(
            "[CONTROL] Placement planning result: "
            f"gap_id={decision.selected.gap_id}, mode={decision.selected.mode}, "
            f"preferred_x={preferred_x}, approach_pose={approach_pose}, final_pose={final_pose}"
        )
        if not self._move_to(approach_pose):
            self._mark_task_failed(task, "failed to move to placement approach pose")
            return False
        if not self._move_to(final_pose):
            self._mark_task_failed(task, "failed to move to placement final pose")
            return False
        if not motion_adapter.gripper_command("OPEN"):
            self._mark_task_failed(task, "gripper open command failed")
            return False
        self.world_model.update_zone_base(task.zone, final_pose.x, task.thickness)
        self.world_model.remember_placed_book(task.title, final_pose)
        return True

    def handle_tilt_check(self, shelf: ShelfObservation) -> None:
        if not shelf.tilted_books:
            print("[CONTROL] Tilt check passed. No tilted books detected.")
            return

        if config.SIM_MODE:
            print("[CONTROL] Tilt detected, but repair is skipped automatically in SIM_MODE.")
            return

        while True:
            answer = input(
                "[CONTROL] Tilt detected on shelf. Repair now? (Yes/No): "
            ).strip().lower()
            if answer == "yes":
                print("[CONTROL] Repair logic not implemented yet.")
            elif answer == "no":
                print("[CONTROL] Tilt repair skipped by operator.")
                return

    def run_pick_place_only_cycle(self) -> None:
        """Run minimal motion validation with fixed pick/place poses only."""
        if config.VISUALIZER:
            from visualization import initialize_recorder

            traj_csv = Path(__file__).resolve().parent.parent / "sim_output" / "control_trajectory.csv"
            initialize_recorder(traj_csv)

        plan = config.get_pick_place_plan()
        pick_approach = plan.pick_approach
        pick_pose = plan.pick
        pick_lift = plan.pick_lift
        place_transfer = plan.place_transfer
        place_approach = plan.place_approach
        place_final = plan.place_final
        place_retreat = plan.place_retreat

        print(
            "[CONTROL] Running PICK_PLACE_ONLY cycle with fixed poses: "
            f"pick_approach={pick_approach}, pick={pick_pose}, pick_lift={pick_lift}, "
            f"transfer={place_transfer}, approach={place_approach}, "
            f"final={place_final}, retreat={place_retreat}"
        )

        self._transition("MOVE_TO_PICK_APPROACH")
        self._move_to(pick_approach)
        if config.VISUALIZER:
            from visualization import record_waypoint_state

            # Pre-grasp point above the spine marker: book is still in return-bin.
            record_waypoint_state(
                pose=self.current_pose,
                held_book_visible=False,
                return_book_visible=True,
                placed_book_visible=False,
                horizontal_end_link=True,
            )

        self._transition("MOVE_TO_PICK")
        self._move_to(pick_pose)
        if config.VISUALIZER:
            from visualization import record_waypoint_state

            # At pickup point before grasp: book still in return-bin.
            record_waypoint_state(
                pose=self.current_pose,
                held_book_visible=False,
                return_book_visible=True,
                placed_book_visible=False,
                horizontal_end_link=True,
            )
        motion_adapter.gripper_command("CLOSE")
        if config.VISUALIZER:
            from visualization import record_waypoint_state

            # Same pickup pose after grasp: book switches to gripper-held.
            record_waypoint_state(
                pose=self.current_pose,
                held_book_visible=True,
                return_book_visible=False,
                placed_book_visible=False,
                horizontal_end_link=True,
            )

        self._transition("MOVE_TO_PICK_LIFT")
        self._move_to(pick_lift)
        if config.VISUALIZER:
            from visualization import record_waypoint_state

            # Lift the gripped book before rotating toward the shelf to avoid lower-edge snagging.
            record_waypoint_state(
                pose=self.current_pose,
                held_book_visible=True,
                return_book_visible=False,
                placed_book_visible=False,
                horizontal_end_link=True,
            )

        self._transition("MOVE_TO_PLACE_TRANSFER")
        self._move_to(place_transfer)
        if config.VISUALIZER:
            from visualization import record_waypoint_state

            # Shelf-side transfer point: rotate/side-move near the shelf before lowering.
            record_waypoint_state(
                pose=self.current_pose,
                held_book_visible=True,
                return_book_visible=False,
                placed_book_visible=False,
                horizontal_end_link=True,
            )

        self._transition("MOVE_TO_PLACE_APPROACH")
        self._move_to(place_approach)
        if config.VISUALIZER:
            from visualization import record_waypoint_state

            # Enable horizontal constraint at approach first to avoid
            # same-target constraint switching at final placement point.
            record_waypoint_state(
                pose=self.current_pose,
                held_book_visible=True,
                return_book_visible=False,
                placed_book_visible=False,
                horizontal_end_link=True,
            )

        self._transition("MOVE_TO_PLACE_FINAL")
        self._move_to(place_final)
        if config.VISUALIZER:
            from visualization import record_waypoint_state

            # At placement pose before release: still held by gripper.
            record_waypoint_state(
                pose=self.current_pose,
                held_book_visible=True,
                return_book_visible=False,
                placed_book_visible=False,
                horizontal_end_link=True,
            )
        motion_adapter.gripper_command("OPEN")
        if config.VISUALIZER:
            from visualization import record_waypoint_state

            # Same placement pose after release: book becomes placed on shelf.
            record_waypoint_state(
                pose=self.current_pose,
                held_book_visible=False,
                return_book_visible=False,
                placed_book_visible=True,
                horizontal_end_link=True,
            )

        self._transition("MOVE_TO_PLACE_RETREAT")
        self._move_to(place_retreat)
        if config.VISUALIZER:
            from visualization import record_waypoint_state

            # After release, move the gripper clear before handing over to manual control.
            record_waypoint_state(
                pose=self.current_pose,
                held_book_visible=False,
                return_book_visible=False,
                placed_book_visible=True,
                horizontal_end_link=True,
            )

        self._transition("GO_HOME")
        if motion_adapter.go_home():
            print("[CONTROL] Home command completed.")
        else:
            print("[CONTROL] Home command failed.")

    def _build_shelf_observation(self, raw: dict, capture_pose: Pose) -> ShelfObservation:
        gaps = [
            ShelfGap(
                gap_id=gap["gap_id"],
                start_x=capture_pose.x + gap["start_x"],
                end_x=capture_pose.x + gap.get("end_x", gap["start_x"] + gap["width"]),
                width=gap["width"],
                left_boundary_type=gap.get("left_boundary_type", "unknown"),
                right_boundary_type=gap.get("right_boundary_type", "unknown"),
                confidence=gap.get("confidence", 1.0),
            )
            for gap in raw["gaps"]
        ]
        return ShelfObservation(
            zone=raw["zone"],
            depth=capture_pose.y + raw["depth"],
            bottom=capture_pose.z + raw["bottom"],
            top=capture_pose.z + raw["top"],
            height=raw["height"],
            gaps=gaps,
            tilted_books=raw["tilted_books"],
            capture_pose=capture_pose,
        )

    def _move_to(self, target_pose: Pose) -> bool:
        success = motion_adapter.move_to(self.current_pose, target_pose)
        if success:
            self.current_pose = target_pose
            return True
        return False

    def _mark_task_failed(self, task: Task, reason: str) -> None:
        task.status = "FAILED"
        task.failure_reason = reason
        print(f"[CONTROL] Task failure for '{task.title}': {reason}")

    def _wait_sample_interval(self) -> None:
        time.sleep(config.SAMPLE_RATE_MS / 1000.0)

    def _transition(self, new_state: str) -> None:
        print(f"\n[STATE] {self.state} -> {new_state}")
        self.state = new_state

    @staticmethod
    def _ask_yes_no(prompt: str) -> bool:
        if config.SIM_MODE:
            print(prompt + " [auto-no in SIM_MODE]")
            return False

        while True:
            answer = input(prompt).strip().lower()
            if answer in {"yes", "y"}:
                return True
            if answer in {"no", "n"}:
                return False
