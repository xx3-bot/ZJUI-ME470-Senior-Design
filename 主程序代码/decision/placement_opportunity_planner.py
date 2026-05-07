"""Generate and score candidate placement opportunities for a shelf observation."""

from __future__ import annotations

from typing import List, Optional

import config
from models import (
    PlacementDecision,
    PlacementOpportunity,
    Pose,
    ScoredPlacementOpportunity,
    ShelfGap,
    ShelfObservation,
    Task,
)


class PlacementOpportunityPlanner:
    """Lightweight, explainable placement planner.

    This module stays on the decision side of the system: it selects a shelf
    target and explains the choice. The existing control path still owns motion
    waypoints, IK, visualization, and hardware command generation.
    """

    def generate_opportunities(
        self, task: Task, shelf: ShelfObservation, preferred_x: Optional[float]
    ) -> List[PlacementOpportunity]:
        opportunities: List[PlacementOpportunity] = []
        minimum_margin = config.PLACEMENT_SIDE_CLEARANCE

        for gap in shelf.gaps:
            fit_margin = gap.width - task.thickness
            target_positions = self._candidate_target_positions(gap, task.thickness)

            for mode, target_x in target_positions:
                left_clearance = max(0.0, target_x - gap.start_x)
                right_edge = target_x + task.thickness
                right_clearance = max(0.0, gap.end_x - right_edge)
                distance_to_preferred = (
                    abs(target_x - preferred_x) if preferred_x is not None else 0.0
                )
                is_tight = fit_margin < minimum_margin + 5.0
                opportunities.append(
                    PlacementOpportunity(
                        gap_id=gap.gap_id,
                        mode=mode,
                        target_x=target_x,
                        fit_margin=fit_margin,
                        left_clearance=left_clearance,
                        right_clearance=right_clearance,
                        left_boundary_type=gap.left_boundary_type,
                        right_boundary_type=gap.right_boundary_type,
                        distance_to_preferred=distance_to_preferred,
                        is_tight=is_tight,
                        confidence=gap.confidence,
                    )
                )
        return opportunities

    def score_opportunities(
        self, task: Task, opportunities: List[PlacementOpportunity]
    ) -> List[ScoredPlacementOpportunity]:
        scored: List[ScoredPlacementOpportunity] = []
        minimum_margin = config.PLACEMENT_SIDE_CLEARANCE

        for opportunity in opportunities:
            if opportunity.fit_margin < minimum_margin:
                scored.append(
                    ScoredPlacementOpportunity(
                        opportunity=opportunity,
                        score=0.0,
                        rejected=True,
                        reason="fit margin below minimum clearance",
                    )
                )
                continue

            score = 0.0
            reasons: List[str] = []

            margin_bonus = min(opportunity.fit_margin, 40.0) * 0.6
            score += margin_bonus
            reasons.append(f"margin {opportunity.fit_margin:.1f} mm")

            free_side_clearance = max(opportunity.left_clearance, opportunity.right_clearance)
            clearance_bonus = min(free_side_clearance, 40.0) * 0.3
            score += clearance_bonus
            reasons.append(f"free clearance {free_side_clearance:.1f} mm")

            support_reason = self._score_support_from_boundaries(opportunity)
            score += support_reason["bonus"]
            if support_reason["reason"]:
                reasons.append(support_reason["reason"])

            if opportunity.mode == "center":
                score -= 5.0
                reasons.append("center placement penalty")

            if opportunity.is_tight:
                score -= 6.0
                reasons.append("tight fit penalty")

            distance_penalty = min(opportunity.distance_to_preferred / 8.0, 12.0)
            score -= distance_penalty
            if opportunity.distance_to_preferred > 0:
                reasons.append(f"distance penalty {opportunity.distance_to_preferred:.1f} mm")

            confidence_bonus = max(0.0, min(opportunity.confidence, 1.0)) * 4.0
            score += confidence_bonus
            reasons.append(f"gap confidence {opportunity.confidence:.2f}")

            scored.append(
                ScoredPlacementOpportunity(
                    opportunity=opportunity,
                    score=round(score, 2),
                    rejected=False,
                    reason=", ".join(reasons),
                )
            )

        return scored

    def plan(
        self, task: Task, shelf: ShelfObservation, preferred_x: Optional[float]
    ) -> PlacementDecision:
        opportunities = self.generate_opportunities(task, shelf, preferred_x)
        scored = self.score_opportunities(task, opportunities)
        self._log_candidates(task, scored)

        feasible = [candidate for candidate in scored if not candidate.rejected]
        if not feasible:
            reason = "no feasible placement opportunities"
            print(f"[PLAN] Selected none for {task.title}: {reason}")
            return PlacementDecision(
                selected=None,
                scored_candidates=scored,
                approach_pose=None,
                final_pose=None,
                reason=reason,
            )

        selected = max(feasible, key=lambda candidate: candidate.score)
        final_pose = self._compute_final_pose(task, shelf, selected.opportunity)
        approach_pose = self._compute_approach_pose(task, final_pose)
        reason = (
            f"selected gap={selected.opportunity.gap_id} mode={selected.opportunity.mode} "
            f"because {selected.reason}"
        )
        print(
            f"[PLAN] Selected gap={selected.opportunity.gap_id} "
            f"mode={selected.opportunity.mode}: {selected.reason}"
        )
        return PlacementDecision(
            selected=selected.opportunity,
            scored_candidates=scored,
            approach_pose=approach_pose,
            final_pose=final_pose,
            reason=reason,
        )

    def _candidate_target_positions(self, gap: ShelfGap, thickness: float) -> List[tuple[str, float]]:
        right_limit = gap.start_x + max(0.0, gap.width - thickness)
        center_x = gap.start_x + max(0.0, (gap.width - thickness) / 2.0)
        return [
            ("lean_left", gap.start_x),
            ("center", center_x),
            ("lean_right", right_limit),
        ]

    def _score_support_from_boundaries(self, opportunity: PlacementOpportunity) -> dict:
        left_type = opportunity.left_boundary_type
        right_type = opportunity.right_boundary_type

        if opportunity.mode == "lean_left":
            if left_type in {"book", "side_panel"} and right_type == "open":
                return {"bonus": 8.0, "reason": "visual left support with open right side"}
            if left_type in {"book", "side_panel"}:
                return {"bonus": 4.0, "reason": "visual left support"}
            if left_type == "unknown":
                return {"bonus": 0.0, "reason": "left support unknown"}
            return {"bonus": -3.0, "reason": "no confirmed left support"}

        if opportunity.mode == "lean_right":
            if right_type in {"book", "side_panel"} and left_type == "open":
                return {"bonus": 8.0, "reason": "visual right support with open left side"}
            if right_type in {"book", "side_panel"}:
                return {"bonus": 4.0, "reason": "visual right support"}
            if right_type == "unknown":
                return {"bonus": 0.0, "reason": "right support unknown"}
            return {"bonus": -3.0, "reason": "no confirmed right support"}

        if left_type == "unknown" or right_type == "unknown":
            return {"bonus": 0.0, "reason": "center support unknown"}
        return {"bonus": 0.0, "reason": "center relies on geometry only"}

    def _compute_final_pose(
        self, task: Task, shelf: ShelfObservation, opportunity: PlacementOpportunity
    ) -> Pose:
        final_z = shelf.bottom + min(
            config.PLACEMENT_BOTTOM_CLEARANCE,
            max(4.0, (shelf.height - config.BOOK_VERT_HEIGHT) / 2.0),
        )
        return Pose(
            x=opportunity.target_x,
            y=shelf.depth + config.TIP_DEPTH,
            z=final_z,
        )

    def _compute_approach_pose(self, task: Task, final_pose: Pose) -> Pose:
        direction = 1 if task.zone.endswith("left") else -1
        return Pose(
            x=final_pose.x - direction * config.PLACEMENT_SIDE_CLEARANCE,
            y=final_pose.y - config.PLACEMENT_REAR_CLEARANCE,
            z=final_pose.z + 2.0,
        )

    def _log_candidates(self, task: Task, scored: List[ScoredPlacementOpportunity]) -> None:
        print(f"[PLAN] Placement candidates for {task.title}:")
        for candidate in scored:
            opportunity = candidate.opportunity
            rejected_text = "True" if candidate.rejected else "False"
            print(
                "  "
                f"gap={opportunity.gap_id} mode={opportunity.mode:<10} "
                f"score={candidate.score:>5.2f} rejected={rejected_text:<5} "
                f"reason={candidate.reason}"
            )
