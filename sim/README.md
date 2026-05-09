# KM1-like MuJoCo Workspace Simulator

This folder contains a first-pass MuJoCo model and analysis script for the ME470 book-reshelving arm.
The top-level scripts are tools; historical CSV trajectories and IK probes live under
`examples/` and `diagnostics/` so they cannot be mistaken for the formal runtime path.

The model is intentionally a configurable engineering approximation, not a calibrated KM1 digital twin yet.
Use it to answer early layout and control questions:

- Where can the gripper tip reach?
- What shelf/bin regions are likely feasible?
- Which target poses fail inverse kinematics?
- Which joint limits are hit near the workspace boundary?
- What constraints should the later ROS2 motion layer enforce?

## Files

- `km1_arm.xml`: simple 5-DOF KM1-like serial arm with base yaw, shoulder, elbow, wrist pitch, and wrist roll.
- `km1_workspace_sim.py`: workspace sampler, position-only IK solver, optional viewer.
- `vendor_km1_kinematics.py`: vendor-derived analytical IK and PWM command generator.
- `km1_trajectory_viewer.py`: MuJoCo trajectory viewer for a CSV list of target points.
- `examples/sample_trajectory.csv`: a small ESP32-feasible sample path.
- `examples/lower_shelf_deep_trajectory.csv`: three lower-shelf placement test points pushed deeper into the shelf.
- `examples/lower_shelf_aggressive_trajectory.csv`: a more aggressive lower-shelf path with targets around `y=300 mm`.
- `examples/pick_and_place_trajectory.csv`: historical side return-bin pick/place playback.
- `sim/diagnostics/workspace_samples.csv`: generated point cloud of reachable gripper tip positions.
- `diagnostics/vendor_ik_grid.csv`: optional generated target grid with IK success/failure.

## Run

From the repository root:

Generate the current hardware ASCII sequence from a target grasp point and a
target placement point without opening the MuJoCo viewer:

```bash
python3 主程序代码/main.py \
  --run-target-sequence \
  --pick 218.0 120.23 115.0 \
  --place -40.0 260.0 124.25 \
  --dry-run
```

This path uses the same MuJoCo/IK solving logic for trajectory calculation, but
does not launch a visualization window. The visual viewer remains a debugging
tool only.

For real hardware execution, the target-sequence path now waits for a start
trigger by default. During testing, use `--wait-trigger space` and press Space
or Enter after the command preview is ready. The future physical button should
replace this trigger source, not the motion-generation path.

The generated arm commands use per-servo dynamic `Txxxx` timing for small PWM
deltas to reduce jitter; base-only, gripper, and measured home commands stay
fixed.

Open the MuJoCo debug viewer directly from a target grasp point and placement
point:

```bash
python3 主程序代码/main.py \
  --target-viewer \
  --pick 220.0 0.0 115.0 \
  --place 0.0 260.0 124.25
```

This writes `sim_output/control_trajectory.csv` from the same generic
target-sequence waypoint policy, then opens `sim/km1_trajectory_viewer.py`.
On macOS the viewer is launched through `mjpython`.

For the current target-sequence hardware chain, the post-grasp transport lift is
`45 mm` above the input pick point. With the clean axis-aligned test
`pick=(220, 0, 115)` and `place=(0, 260, 124.25)`, the lift/transfer/approach
height is therefore `160 mm`.

After that lift, target-sequence runs add a `transport_retract` waypoint that
moves the held book `70 mm` horizontally toward the arm origin at the same Z
before the base-only shelf turn. For the clean axis test this point is
`(150, 0, 160)`.

Run the main pick/place demo and open the MuJoCo window:

```bash
python3 主程序代码/main.py --viewer --book-xy 218.0 120.23 --book-z 100.0
```

Tune the pickup and placement waypoints from the command line:

```bash
python3 主程序代码/main.py --viewer \
  --book-xy 218.0 120.23 --book-z 100.0 \
  --pick-approach-clearance 100.0 \
  --post-grasp-lift 50.0 \
  --place-transfer -40.0 220.0 150.0 \
  --place-approach -40.0 260.0 150.0 \
  --place-final -40.0 260.0 124.25 \
  --place-retreat -40.0 220.0 150.0
```

In the current `PICK_PLACE_ONLY_MODE`, `--book-xy/--book-z` directly set the pickup waypoint shown in MuJoCo.
Before descending to that pickup point, the arm now moves to a pre-grasp waypoint above the book with the same X/Y and a higher Z. The default clearance is `100 mm`, and it can be tuned with `--pick-approach-clearance` or replaced with `--pick-approach X Y Z`.
The return-book visual is also moved from that pickup waypoint. The waypoint is the book-spine/left-edge grasp marker, not the book center; the book body is offset away from the arm so the gripper approaches the spine instead of penetrating the pages.
The simulated book size is `200 x 140 x 10 mm` (`height x spine-to-pages width x thickness`).
The default pickup height is `100 mm`, the 50% height of the measured book.
After grasping, the default trajectory lifts the held book `50 mm`, then moves to a shelf-side high transfer waypoint, pushes the book inward at the high Z, and only then lowers to the release point.
The current default pickup posture is seeded from the manually tuned grasp pose using MuJoCo internal joint angles: `[28.88, -53.57, 97.98, -46.52, 0] deg`.
The placement approach/final rows use the horizontal end-link constraint so the held book is shown close to level at release.
For horizontal placement rows, the viewer also straightens `wrist_roll` to `0 deg` so the book is not rolled sideways before release.
The trajectory viewer now plays one step at a time. Press `Space` to move from the current pose to the next waypoint; after that segment finishes, the viewer pauses until `Space` is pressed again.
After release, the arm moves to a retreat waypoint with the book left placed on the shelf, then the final `Space` step returns the arm to the MuJoCo internal center-up pose `[0, -90, 0, 0, 0] deg`. For hardware calibration, this physical joint1 upright pose should be reported/converted as joint1 `0 deg` / `P1500`; do not change the MuJoCo XML geometry for that convention.
After the final step stops, the MuJoCo right-side `Control` panel stays active so teammates can manually adjust the arm joints from that center-up pose.
Keyboard joint control is also enabled after the trajectory stops:

- `0`: select `base_yaw`
- `1`: select `shoulder_pitch`
- `2`: select `elbow_pitch`
- `3`: select `wrist_pitch`
- `4`: select `wrist_roll`
- `5`: reserved for gripper; the current MuJoCo XML has no gripper actuator yet
- `Left/Right`: adjust selected joint by `-1/+1 deg`
- `Down/Up`: adjust selected joint by `-5/+5 deg`

Future perception/planning integration should feed the same seven-waypoint plan
that the CLI currently overrides: `pick_approach`, `pick`, `pick_lift`,
`place_transfer`, `place_approach`, `place_final`, and `place_retreat`. See `主程序代码/CONTROL_INTERFACE_SPEC.md`
for the contract.

```bash
python3 sim/km1_workspace_sim.py
```

Test one candidate target pose, in millimeters:

```bash
python3 sim/km1_workspace_sim.py --target-mm 0 300 180
```

Run the vendor-derived analytical IK directly:

```bash
python3 sim/vendor_km1_kinematics.py 0 300 180 --profile measured_grasp
```

For shelf placement, constrain the gripper/end-link angle so the held book is closer to horizontal:

```bash
python3 sim/vendor_km1_kinematics.py 0 180 120 --alpha-range=-45:-25
```

Scan a candidate book/shelf region:

```bash
python3 sim/km1_workspace_sim.py --ik-grid --x-range -200:200 --y-range 150:430 --z-range 40:520 --grid-step-mm 40
```

Scan with the vendor ESP32 IK and a placement-oriented end-link angle constraint:

```bash
python3 sim/vendor_km1_kinematics.py --scan-grid --profile measured_grasp --x-range=-160:160 --y-range=80:420 --z-range=20:420 --step-mm 20 --alpha-range=-45:-25
```

Open the interactive viewer:

```bash
python3 sim/km1_workspace_sim.py --viewer --target-mm 0 300 180
```

On macOS, MuJoCo's viewer must be launched with `mjpython` instead of `python3`:

```bash
mjpython sim/km1_workspace_sim.py --viewer --target-mm 0 180 120
```

Play a trajectory in the MuJoCo viewer:

```bash
python3 sim/km1_trajectory_viewer.py
```

On macOS:

```bash
mjpython sim/km1_trajectory_viewer.py
```

Open the joint teaching viewer. Use the MuJoCo viewer's right-side `Control` sliders to move each joint:

```bash
mjpython sim/km1_joint_teach_viewer.py
```

Keyboard shortcuts in the teaching viewer:

- `P`: print current joint angles and end-effector pose.
- `S`: append the current pose to `sim/joint_teach_poses.csv`.
- `R`: reset actuator controls to zero.

Play a custom trajectory:

```bash
python3 sim/km1_trajectory_viewer.py --trajectory sim/examples/sample_trajectory.csv --loop
```

On macOS:

```bash
mjpython sim/km1_trajectory_viewer.py --trajectory sim/examples/sample_trajectory.csv --loop
```

Play the deeper lower-shelf three-point test:

```bash
mjpython sim/km1_trajectory_viewer.py --trajectory sim/examples/lower_shelf_deep_trajectory.csv --alpha-range=-45:-25 --free-end-link --loop
```

This older deeper trajectory is useful for position-only motion checks. For shelf placement with a near-horizontal final link, prefer the aggressive trajectory below.

Play the more aggressive lower-shelf test. The viewer constrains the final link to stay close to horizontal by default:

```bash
mjpython sim/km1_trajectory_viewer.py --trajectory sim/examples/lower_shelf_aggressive_trajectory.csv --alpha-range=-35:-25 --loop
```

To see the old position-only behavior:

```bash
mjpython sim/km1_trajectory_viewer.py --trajectory sim/examples/lower_shelf_aggressive_trajectory.csv --alpha-range=-35:-25 --free-end-link --loop
```

Play the first pick-and-place mock cycle. A standing book is placed farther out at the side return-bin position near the arm's 90-degree direction:

```bash
mjpython sim/km1_trajectory_viewer.py --trajectory sim/examples/pick_and_place_trajectory.csv --free-end-link --loop
```

The pick-and-place mock still uses `--free-end-link` globally, but pickup and placement waypoints override this with `horizontal_end_link=1` where the end link should be leveled.
The return-bin book is rotated about the world Z axis so its thin/spine side faces the arm for easier gripping. Its support base is half height to reduce visual interference near pickup, and the horizontal pickup point is currently about `(280, 100, 120) mm`.
Only the pre-pick return-bin book orientation is adjusted for the desired pickup edge; once the book is held, the gripper-held book geometry keeps the original grasp-relative pose.
After release, the placed-book visual copies the gripper-held book pose at the release waypoint, then shifts only in world Z so the book's lowest point touches the lower shelf surface instead of disappearing.
Current shelf visual dimensions: each shelf board is `10 mm` thick, the first
board spans `30..40 mm` above the floor, and the second shelf surface is
`240 mm` above the first shelf surface (`280 mm` above the floor). The placed
book visual is aligned to the lower shelf top at `z=40 mm`.
The current MuJoCo joint ranges are broadened to approximate the ESP32 factory analytical IK limits, so manual teaching can explore the original-style motion envelope.

Trajectory CSV format:

```csv
x_mm,y_mm,z_mm,held_book_visible,return_book_visible,placed_book_visible,horizontal_end_link,base_only_from_previous
0,180,120,0,1,0,0,0
280,100,120,1,0,0,1,0
0,300,105,0,0,1,1,0
```

The optional `horizontal_end_link` column overrides the viewer-wide orientation mode for a waypoint. Use `1` on side pickup and shelf placement/release rows where the end link should be close to horizontal.

The optional `base_only_from_previous` column marks a waypoint where only
`base_yaw` should change; joint1-joint4 are held from the previous waypoint.
Use this for shelf-turn transitions that should avoid wrist/link posture
changes while the base rotates.

## Coordinate Convention

The script reports positions in millimeters to match the current main control code.

- `x`: left/right from the arm base
- `y`: forward from the arm base
- `z`: height above the floor/base plane

The current XML uses meters internally because MuJoCo uses SI units.

## Current Visual Joint Limits

The MuJoCo viewer currently uses ESP32-factory-style visual joint limits:

- `base_yaw`: `-135..135 deg`
- `shoulder_pitch`: `-120..120 deg`
- `elbow_pitch`: `-135..135 deg`
- `wrist_pitch`: `-120..120 deg`
- `wrist_roll`: `-135..135 deg`

These limits are for visualization/manual teaching only. The real arm's safe range still needs hardware verification before any command is sent to the physical robot.

## Vendor Parameters Found So Far

Two parameter profiles were found in the vendor resources:

- `esp32_factory`: `L0=100 mm`, `L1=105 mm`, `L2=75 mm`, `L3=180 mm`.
  This appears in `4.源代码程序/机械臂控制器出厂源码/ESP代码v1.1.mix` as `setup_kinematics(100, 105, 75, 180, ...)`.
- `stm32_openmv`: `L0=100 mm`, `L1=105 mm`, `L2=88 mm`, `L3=155 mm`.
  This appears in STM32 `main.c` and several OpenMV `kinematics.py` files.
- `measured_physical`: `L0=103 mm`, `L1=105 mm`, `L2=86.35 mm`, `L3≈100 mm`.
  This is based on direct user measurement of the current physical prototype.
- `measured_grasp`: `L0=103 mm`, `L1=105 mm`, `L2=86.35 mm`, `L3≈125 mm`.
  This treats `XYZ` as the landmark/control point of the held object at the gripper's lower grasp position.

`measured_grasp` is the active baseline for this workspace's current simulation/control validation path.
The `esp32_factory` profile is kept as vendor-reference history only; do not use it as the default for target planning, IK acceptance, or viewer prechecks.
The `stm32_openmv` profile is only a reference for the vendor's other arm/controller variant and should not be used for placement-range decisions unless the hardware changes.
The MuJoCo geometry currently follows the measured physical dimensions for visualization.
The MuJoCo `ee_site` is placed at the held-object/gripper grasp control point, about `125 mm` from the wrist pitch joint.
The held-book geometry is offset so the gripper holds the book near its spine/edge instead of at the book center.
The command-generation default is also `measured_grasp` for this project code path. Do not send generated commands to hardware until servo zero, direction, scale, and safety gates are verified.

Current project rule:

- Use `measured_grasp` for workspace analysis, IK feasibility, simulation backend reachability, viewer vendor precheck, and future project-specific command generation.
- Use `measured_physical` only for explicit mechanical-geometry comparison/debugging.
- Keep `esp32_factory` only as vendor-reference history.
- Keep `stm32_openmv` only for comparison/debugging.
- If profiles disagree, trust `measured_grasp` for this workspace's current planning/acceptance path unless the user explicitly requests a comparison run.
- The current physical bus-servo angular range is not yet verified.
  Do not assume a `0-180 deg` hard limit until hardware tests confirm it; the IK helper does not enforce this as a default limit.

## What To Calibrate Later

Replace the approximate values in `km1_arm.xml` once measured or confirmed:

- Link lengths
- Joint axes and sign conventions
- Joint angle limits
- Gripper tip offset
- Base height
- Servo-to-joint mapping
- Self-collision and table/shelf collision geometry

Until those are calibrated, treat the output as a layout and algorithm-design guide, not final hardware truth.

## Constraints To Carry Into ROS2

Early constraints that should eventually exist in the ROS2 motion API:

- Reject targets outside joint limits.
- Verify the physical bus-servo range before enforcing angle limits in ROS2.
- Keep conservative joint limits in simulation; unconstrained numeric IK can produce visually impossible floor/shelf penetration.
- Reject targets with IK error above tolerance.
- Avoid returning success unless motion completion is observed.
- Clamp or reject targets below table height.
- Reserve a collision margin around shelf boards, bin walls, and books.
- Prefer approach poses before final pick/place poses.
- For shelf placement, require the final gripper/book angle to stay within a placement-specific `Alpha` window instead of accepting any reachable pose.
