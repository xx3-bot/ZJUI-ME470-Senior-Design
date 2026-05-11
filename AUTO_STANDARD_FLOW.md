# Auto Standard Flow

This document freezes the intended standard automatic run flow for the
integrated system. It is a design and team-alignment document only. The full
Auto flow described here is not implemented yet.

## Goal

The final standard run should use the existing program framework instead of a
separate new program. The controller remains the automation coordinator, while
the verified target-sequence path remains the hardware execution layer.

High-level flow:

```text
start program
-> three-view startup scan
-> initialize bin and shelf world model
-> plan the whole return queue
-> precheck feasible tasks with target_sequence dry-run
-> show result and wait for operator Enter
-> execute pick/place loop
-> update world model after each successful placement
-> report skipped/failed books at the end
```

## Reuse Existing Framework

Keep these pieces and upgrade them gradually:

- `controller.py`: keep it as the task-state and Auto-run coordinator.
- `perception_adapter.py`: keep it as the only control-side entry point for
  vision results.
- `decision/placement_opportunity_planner.py`: keep the scoring idea and evolve
  it from gap-level candidates into section/slice-level placement decisions.
- `world_model.py`: keep the module, but expand it into the runtime source of
  truth for bin books, shelf sections, slices, occupancy, placement decisions,
  and failures.
- `target_sequence.py`: keep it as the reliable pick/place trajectory, MuJoCo
  IK, PWM, command-generation, and hardware-send path.

Do not replace the verified hardware path with a direct
`motion_adapter -> per-pose IK` bridge.

## Startup Scan

Auto mode should begin with three fixed camera/arm views:

```text
left view   joint0/yaw = -90 deg
center view joint0/yaw =   0 deg
right view  joint0/yaw = +90 deg
```

A configuration table should state which shelf sections are expected in each
view. The vision module should not need to infer the whole shelf layout from
scratch. Instead, each view provides a coarse prior, and vision refines:

- bin book detections and rough pick information,
- section horizontal coordinates,
- section/slice free or occupied state,
- gap widths and boundary support,
- confidence values.

Depth is fixed by configuration in the first Auto version. Data structures
should still leave room for future depth correction from vision or AprilTag
calibration.

## Shelf Sections And Slices

Use two separate concepts:

```text
section: A / B / C / D
slice/gap/candidate: positions inside one section
```

`A`, `B`, `C`, and `D` are the large shelf sections. Left/right concepts belong
inside a section as boundary or slice information. The decision planner's
`lean_left`, `center`, and `lean_right` modes are placement modes inside a
candidate slice; they are not section names.

The desired model shape is:

```text
ShelfSection
- section_id: A/B/C/D
- expected_view: left/center/right
- nominal_x_range
- measured_x_range
- default_depth
- measured_depth optional
- confidence
- slices/gaps

ShelfSlice
- slice_id
- x_start / x_end / width
- state: free / occupied / unknown
- left_boundary_type
- right_boundary_type
- confidence
- placed_book_title optional
```

After a successful placement, the corresponding slice must become occupied in
the world model. Later planning must not treat that slice as free just because
it was free during the startup scan.

## Planning And Failure Policy

Auto mode should plan the whole queue before moving hardware. The queue should
be scored by the decision system using:

- detected bin books,
- target section from the catalog,
- shelf slice availability,
- book thickness,
- placement support and confidence,
- IK/command-generation feasibility,
- previous failures.

Hard failures block a specific book:

- target book missing,
- target section missing,
- no feasible slice/gap,
- MuJoCo IK failure,
- hardware command generation failure.

Low confidence should be reported as a warning in the first version, not a hard
failure.

If two or more books fail precheck, Auto mode should warn before execution,
print the failed entries and reasons, and request operator confirmation or task
position adjustment. If exactly one book fails, Auto mode should skip that book,
execute the feasible ones after confirmation, and report the skipped book at the
end for manual intervention.

## Execution Gate

Auto mode must not immediately move hardware after planning. It should first
print a run summary:

- planned book order,
- pick pose for each feasible book,
- target section and slice,
- place pose,
- command-generation status,
- failed/skipped entries and reasons.

If the plan has no blocking condition according to the failure policy, enter a
wait state:

```text
Press Enter to start hardware execution...
```

Only after Enter should the controller send hardware commands.

## Execution Loop

During execution, each feasible book should be handled as:

```text
select planned task
-> generate current pick/place target sequence
-> send hardware command sequence
-> on success, remove book from bin model
-> mark shelf slice occupied
-> update section/gap/slice state
-> continue with next task
```

The world model must be updated after each successful placement. The robot
should not continue to use the startup shelf model as if nothing changed.

If execution fails for one book, record the reason and continue or stop based on
the operator-facing policy chosen for that run. The first Auto implementation
should prefer conservative stopping or skipping over trying unverified recovery
motion.

## Suggested Migration Phases

1. Document the standard flow and keep current manual paths unchanged.
2. Add an Auto menu entry that prints the intended flow and uses mock scan
   results without moving hardware.
3. Add section/slice models beside the existing `ShelfObservation` and
   `ShelfGap`; do not delete old models yet.
4. Teach the world model to initialize sections/slices from three-view scan
   results and update occupancy after placement.
5. Teach the decision planner to score section/slice candidates.
6. Add full-queue dry-run precheck through `target_sequence.py`.
7. Add the operator Enter gate.
8. Only then allow Auto mode to send hardware commands.

Manual hardware, dry-run, sim, and target-viewer modes should remain available
throughout this migration.
