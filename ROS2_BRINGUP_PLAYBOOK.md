# ROS2 Bring-up Playbook for KM1 Arm (Detailed, Step-by-Step)

Last updated: 2026-04-30 (Asia/Shanghai)
Audience: user with hardware focus, starting from zero ROS2 arm control validation
Goal: move from “unknown status” to “ROS2 can reliably command the arm” and then integrate with existing control framework

---

## Living Document Policy

This file is both:
1. A step-by-step ROS2 bring-up playbook.
2. A persistent progress log and AI handoff memory for future sessions.

Important reading rule:
- This document is maintained as a time-ordered iteration log, not a fully
  rewritten specification.
- Earlier sections may contain old coordinates, old assumptions, or older
  visual-tuning decisions that have since been replaced.
- Prefer the newest dated/update entries when they conflict with older notes.
- Stable handoff/API contracts should still be checked in the dedicated README
  or spec files referenced by the latest entry.

When new evidence is found, update this file directly instead of relying on chat history.
Future AI assistants should treat this file as the main source of truth for hardware bring-up status,
but should still ask for the latest physical gate status before suggesting risky hardware actions.

Update rules:
- Record exact dates when a gate changes status.
- Record exact serial device names, baud rates, commands, and observed behavior.
- Distinguish confirmed facts from assumptions.
- Do not mark a gate passed unless the pass criteria in this document were actually observed.
- Keep failed attempts; they are useful debugging evidence.
- Prefer adding short dated entries over rewriting history.

Current high-level status as of 2026-04-28:
- Arm hardware is in factory/original state.
- ESP32 has factory firmware.
- Observed factory behavior: power-on beep and arm returns to default pose.
- User has not yet modified firmware or confirmed external serial control.
- Primary next gate: identify serial device and verify vendor/raw serial command control before ROS2.
- Current hardware serial/ROS2 gates are still not passed.

Current IK/profile policy as of 2026-04-30:
- Default IK profile for this workspace's simulation/control validation path is `measured_grasp`.
- Do not use `esp32_factory` as the default target-planning, reachability, viewer-precheck, or command-generation baseline in this project workspace.
- Keep `esp32_factory`, `stm32_openmv`, and `measured_physical` only as explicit comparison/debug profiles.
- `measured_grasp` commands are still not hardware-proven. Before sending any generated PWM/pose commands to the physical arm, verify servo zero, direction, scale, range, serial behavior, and stop path.

Critical warning as of 2026-04-29:
- There is a known inconsistency between:
  1. ESP32 factory firmware kinematics parameters,
  2. user-measured physical link lengths,
  3. MuJoCo visualization geometry,
  4. future custom IK target definition.
- Do not treat MuJoCo visual reachability as hardware reachability.
- Do not treat `measured_physical` / `measured_grasp` commands as safe hardware commands yet.
- The older `esp32_factory` baseline was superseded for this workspace on 2026-04-30 because the current arm is not the original factory aluminum-frame geometry.
- This mismatch is important enough that future AI sessions must explicitly account for it before making placement or ROS2-control recommendations.

---

## Progress Log

Use this section as the rolling work log.

Entry template:
```text
Date/time:
Environment:
Hardware state:
Serial device:
Baud/settings:
Commands tested:
Observed behavior:
Gate status:
Next action:
Notes / assumptions:
```

### 2026-04-28 - Initial Known State

Environment:
- Not yet confirmed.

Hardware state:
- KM1 arm is in factory/original state.
- ESP32 is running factory firmware.
- On power-up, buzzer sounds and arm returns to default position.

Serial device:
- Not yet identified.

Baud/settings:
- Assumption from vendor resources: likely `115200`, `8N1`.
- Not yet verified on the actual arm.

Commands tested:
- None yet.

Observed behavior:
- Factory boot behavior only.

Gate status:
- Gate 1 Vendor baseline: not passed.
- Gate 2 Raw protocol baseline: not passed.
- Gate 3 ROS2 parity: not started.
- Gate 4 Motion adapter integration: not started.
- Gate 5 Framework run: not started.

Next action:
- Connect USB data cable.
- Identify OS serial device.
- Verify safe power and stop path.
- Test raw/vendor command path before writing any ROS2 code.

Notes / assumptions:
- Do not flash new firmware yet.
- First preferred strategy is to keep factory firmware and build a ROS2 serial bridge.
- Superseded on 2026-04-30: the active project IK baseline is now `measured_grasp`, not ESP32 factory kinematics.

### 2026-04-29 - Vendor Kinematics Profile Decision

Superseded by the 2026-04-30 IK policy above. Keep this entry as historical evidence only; do not use its `esp32_factory` recommendation as the current default.

Environment:
- Local workspace: `/Users/xinruixiong/Desktop/ME470`
- MuJoCo Python package is installed (`mujoco 3.6.0` observed locally).

Hardware state:
- Physical arm is the ESP32 factory version.
- Physical arm uses bus servos, but the true angular range is not yet verified.
- STM32 resources belong to a different vendor/controller variant and should not be used as the main baseline for this arm.

Confirmed vendor kinematics evidence:
- ESP32 factory source contains `setup_kinematics(100, 105, 75, 180, &kinematics)`.
  - Source: `项目资源（厂商）/4.源代码程序/机械臂控制器出厂源码/ESP代码v1.1.mix`
  - Active profile: `L0=100 mm`, `L1=105 mm`, `L2=75 mm`, `L3=180 mm`
- STM32/OpenMV sources contain another profile:
  - `L0=100 mm`, `L1=105 mm`, `L2=88 mm`, `L3=155 mm`
  - Treat this as reference only for another hardware/controller version.

Simulation/code artifacts created:
- `sim/km1_arm.xml`
  - MuJoCo KM1-like arm model updated to ESP32 factory link lengths.
- `sim/km1_workspace_sim.py`
  - MuJoCo workspace sampler and numeric IK helper.
- `sim/vendor_km1_kinematics.py`
  - Python port of vendor analytical IK and PWM command generation.
  - Historical note: default active profile was `esp32_factory` at this point; current default is `measured_grasp`.
- `sim/README.md`
  - Documents usage and profile decision.

Important rule for future AI sessions:
- Superseded on 2026-04-30: use `measured_grasp` for current workspace analysis, IK feasibility checks, viewer prechecks, and project-specific command generation.
- Keep `esp32_factory`, `stm32_openmv`, and `measured_physical` only for explicit comparison/debugging.
- If profiles disagree, trust `measured_grasp` for the current project planning path unless the user explicitly requests a comparison run.
- Do not assume bus-servo physical angle limits yet. The range may be wider than `0-180 deg` or represented differently. Verify on hardware before enforcing a hard angle limit.

Observed analysis result:
- A test target `(0, 300, 180) mm` is reachable under `stm32_openmv` but not under `esp32_factory` using vendor IK.
- Therefore MuJoCo numeric IK alone is not enough; current placement range should be checked with `sim/vendor_km1_kinematics.py` using `measured_grasp`.
- A temporary `0-180 deg` bus-servo assumption was considered, but user clarified the true servo range has not been tested and may be wider. The simulation no longer enforces that limit by default.

Useful commands:
```bash
python3 sim/vendor_km1_kinematics.py 0 300 180 --profile measured_grasp
python3 sim/vendor_km1_kinematics.py --scan-grid --profile measured_grasp --x-range=-160:160 --y-range=80:420 --z-range=20:420 --step-mm 20
```

Reachable ESP32 factory IK spot checks observed by user:
```text
target (0, 180, 120) mm -> ok, alpha=-53 deg, pwm=(1500,1367,1601,0675)
target (0, 220, 120) mm -> ok, alpha=-46 deg, pwm=(1500,1324,1654,0823)
target (50, 180, 120) mm -> ok, alpha=-52 deg, pwm=(1385,1355,1599,0692)
target (0, 160, 80) mm -> ok, alpha=-70 deg, pwm=(1500,1295,1603,0622)
```

Interpretation:
- Early feasible forward working region appears around `y=160-250 mm`, `z=80-150 mm`, with modest lateral offset at least to `x=50 mm`.
- Some feasible low/near points push servo 3 PWM close to the lower bound, for example `0622`, so final placement planning should reserve margin from PWM/joint limits.
- Previously tested target `(0, 300, 180) mm` remains not feasible under `esp32_factory` vendor IK.

Shelf placement simulation note:
- MuJoCo scene currently has two shelf platforms at approximately `z=50 mm` and `z=350 mm`.
- With a held-book center target around lower shelf height, lower-left/lower-right checks passed:
  - `(-60, 180, 95) mm`, `alpha=-45 deg`, PWM `(1636,1542,2107,1064)`
  - `(60, 180, 95) mm`, `alpha=-45 deg`, PWM `(1363,1542,2107,1064)`
- Upper-left/upper-right at current upper shelf height failed:
  - `(-60, 180, 395) mm` -> no valid alpha
  - `(60, 180, 395) mm` -> no valid alpha
- A local scan around `x=-60..60`, `y=140..240`, `z=40..260`, `alpha=-45:-25` found max feasible `z≈180 mm`.
- A broader ESP32 factory IK scan around `x=-160..160`, `y=0..500`, `z=0..360` without extra alpha constraints also found max feasible `z≈180 mm`.
- Current conclusion: a second platform 300 mm above the lower platform is too high for ESP32 factory kinematics if the final book placement must be close to horizontal.
- Visual MuJoCo motion may appear to leave unused upper space, but the vendor ESP32 analytical IK is the stricter source for current hardware planning.

Deeper lower-shelf three-point trajectory:
- Created `sim/lower_shelf_deep_trajectory.csv`.
- Intended to test lower shelf left/center/right while pushing the book deeper into the shelf.
- Placement-oriented targets, all passing `esp32_factory` with `alpha=-45:-25`:
  - `(-80, 240, 95) mm` -> PWM `(1636,1242,1695,0953)`
  - `(0, 240, 95) mm` -> PWM `(1500,1323,1838,1014)`
  - `(80, 240, 95) mm` -> PWM `(1363,1242,1695,0953)`
- Viewer command on macOS:
```bash
mjpython sim/km1_trajectory_viewer.py --trajectory sim/lower_shelf_deep_trajectory.csv --alpha-range=-45:-25 --loop
```

Gate status:
- Simulation/IK evidence improved, but hardware gates are unchanged.
- Gate 1 Vendor baseline: not passed.
- Gate 2 Raw protocol baseline: not passed.
- Gate 3 ROS2 parity: not started.

Next action:
- Use ESP32 factory IK grid results to propose conservative bin/shelf candidate zones.
- Still verify actual serial control on the real ESP32 arm before trusting generated commands on hardware.

### 2026-04-29 - Current Simulation Progress and Difficulties

Current progress:
- A usable MuJoCo visualization path exists for the KM1-like arm.
- The viewer can show a simplified held book between the gripper fingers.
- The scene includes two shelf platforms:
  - lower platform around `z=50 mm`
  - upper platform around `z=350 mm`
- macOS viewer must be launched with `mjpython`, not `python3`.
- A deeper lower-shelf trajectory exists:
  - `sim/lower_shelf_deep_trajectory.csv`
  - run with:
```bash
mjpython sim/km1_trajectory_viewer.py --trajectory sim/lower_shelf_deep_trajectory.csv --alpha-range=-45:-25 --loop
```

Current active lower-shelf placement candidates:
```text
left:   (-80, 240, 95) mm
center: (  0, 240, 95) mm
right:  ( 80, 240, 95) mm
```

These pass ESP32 factory IK with placement angle constraint `alpha=-45:-25`.

Current important constraints:
- Use ESP32 factory kinematics, not STM32/OpenMV kinematics.
- Physical servo angle range is unknown; do not prematurely constrain it to `0-180 deg`.
- For placement, do not accept arbitrary reachable poses. Require an `Alpha` window so the held book is close to horizontal.
- Current placement-oriented working targets are lower-shelf only.

Current difficulties / risks:
- The visual MuJoCo model is useful for intuition but is not yet a calibrated digital twin.
- MuJoCo numeric IK can make the arm appear to have more usable space than the ESP32 vendor IK allows.
- The current upper shelf height around `z=350 mm` is not feasible under ESP32 factory IK.
- Broad ESP32 IK scans suggest max feasible target `z≈180 mm`, even without extra placement alpha constraints.
- Therefore a second shelf 300 mm above the lower shelf is likely unrealistic for this arm unless hardware tests prove a different control mode can safely use more range.
- Some previous feasible points pushed servo PWM close to limits; use margin and avoid planning near physical extremes.
- Actual serial control has not been verified yet, so all generated commands remain simulation/planning artifacts, not hardware-proven commands.

Near-term recommendation:
- Continue using the three deeper lower-shelf points as the first simulated placement test set.
- Before changing shelf design, perform raw serial tests on hardware:
  1. confirm serial device
  2. send stop command
  3. send a known safe single-servo command
  4. test one conservative multi-servo/IK command
  5. verify whether servo feedback can be read
- Do not rely on upper-shelf trajectories until the real arm proves it can safely reach those heights.

Additional simulation update:
- User observed in the MuJoCo viewer that early joints were not extending aggressively enough and the final link/book looked too slanted downward.
- Cause identified: the viewer's numeric IK was originally position-only; it did not constrain final link orientation.
- Update made:
  - `sim/km1_trajectory_viewer.py` now constrains the end-link local x-axis to stay close to horizontal/radial by default.
  - Use `--free-end-link` to recover the old position-only behavior.
  - `sim/lower_shelf_aggressive_trajectory.csv` created for deeper targets around `y=300 mm`.
- Aggressive lower-shelf targets, all passing ESP32 factory IK with `alpha=-35:-25`:
```text
left:   (-50, 300, 105) mm
center: (  0, 300, 105) mm
right:  ( 50, 300, 105) mm
```
- Verified MuJoCo horizontal-end-link IK errors for this trajectory are small:
  - position error about `0.1 mm`
  - end-link axis error about `0.039`
- Viewer command on macOS:
```bash
mjpython sim/km1_trajectory_viewer.py --trajectory sim/lower_shelf_aggressive_trajectory.csv --alpha-range=-35:-25 --loop
```

Pick-and-place mock cycle added:
- User requested a side return-bin object at roughly 90 degrees from the arm's initial forward direction.
- Added a simple side return-bin hint and upright standing book in `sim/km1_arm.xml`.
- The side return-bin book was first rotated `90 deg` about world Z so the thin side faced the arm. It was then rotated another `180 deg` after the user observed that the spine was facing away from the arm, and later rotated `180 deg` again about the book's own vertical Z axis to correct the visible spine/cover orientation. Current intent: thin/spine side faces the gripper during pickup.
- The side return-bin support base was reduced to half thickness to reduce visual interference near pickup.
- Moved the side return-bin/book farther from the base, first from about `(140, 80)` mm to about `(200, 90)` mm, then to `(230, 100)` mm, then `(260, 110)` mm, and currently to about `(280, 100)` mm in the XY plane.
- The current side pickup point is `(280, 100, 120)` with `horizontal_end_link=1`. This was chosen because the user wants pickup to happen with the end link close to horizontal, like reversing the shelf-placement motion. This point passes both `esp32_factory` vendor IK and MuJoCo horizontal-end-link IK.
- Added CSV state columns to trajectory viewer:
```text
held_book_visible
return_book_visible
placed_book_visible
horizontal_end_link
```
- `horizontal_end_link` is optional and overrides the viewer-wide orientation mode for that waypoint. In `sim/pick_and_place_trajectory.csv`, side pickup and shelf placement/release rows now use `horizontal_end_link=1` so the end link is leveled before gripping/releasing the book.
- Added a free-joint placed-book body. After the release waypoint, `placed_book_visible=1` shows a book whose pose is copied from the gripper-held book at release, then shifted only in world Z so the book's lowest point touches the lower shelf surface. This means final book orientation now depends on the actual release pose instead of a fixed upright/static placeholder.
- Added `sim/pick_and_place_trajectory.csv` to simulate:
  1. start/ready
  2. move to side return-bin book
  3. pick/lift
  4. approach lower shelf
  5. insert/place book
  6. release
  7. retreat
- Non-GUI verification passed:
  - all trajectory targets pass `esp32_factory` vendor IK precheck
  - MuJoCo position IK solves all waypoints with about `0.2-3.0 mm` error after moving the pickup book farther out
- Current viewer command on macOS:
```bash
mjpython sim/km1_trajectory_viewer.py --trajectory sim/pick_and_place_trajectory.csv --free-end-link --loop
```
- Note: `--free-end-link` is still used globally, but pickup and placement rows use `horizontal_end_link=1`, so per-waypoint orientation constraints are available and used for gripping/release.
- `--loop` is included so the mock pick-and-place cycle repeats continuously in the viewer.

Joint teaching viewer added:
- Added `sim/km1_joint_teach_viewer.py`.
- Run on macOS:
```bash
mjpython sim/km1_joint_teach_viewer.py
```
- It uses MuJoCo's right-side `Control` sliders for the five arm position actuators.
- Keyboard shortcuts:
  - `P`: print current joint angles and end-effector pose.
  - `S`: append current pose to `sim/joint_teach_poses.csv`.
  - `R`: reset actuator controls to zero.
- This tool is for manually teaching difficult poses when natural-language trajectory edits become ambiguous.

Joint constraints and book-grip correction:
- User observed that overly loose simulation constraints caused physically implausible poses and floor/shelf penetration.
- Updated MuJoCo joint ranges to be more conservative for visualization:
```text
shoulder_pitch: -60..0 deg
elbow_pitch:    -120..60 deg
wrist_pitch:    -110..110 deg
```
- Important sign note: in the current MuJoCo convention, positive `shoulder_pitch` tips the arm downward. The `0 deg` upper limit is intentional because the previous `+35 deg`, `+10 deg`, and `+5 deg` limits allowed too much shoulder-down posture after pickup.
- User observed that joint 2/elbow rotated too much during the pick-and-place mock. The elbow positive limit was reduced from `135 deg` to `60 deg`; smaller limits such as `25-45 deg` can still solve the free pick-and-place path but break the horizontal lower-shelf placement test.
- User clarified that the gripper should hold the book at the spine/edge rather than the book center.
- Updated held-book geometry in `sim/km1_arm.xml`:
  - added `held_book_spine`
  - initially shifted `held_book_cover` and `held_book_pages` forward from `ee_site`
  - temporarily flipped the held/placed book local geometry to the left side of `ee_site`, then reverted it after the user clarified only the pre-pick book state should be corrected
  - `ee_site` remains the grasp/control point at the spine/edge grip location
- Current verification:
  - `sim/lower_shelf_aggressive_trajectory.csv` still passes with horizontal end-link constraint.
  - `sim/pick_and_place_trajectory.csv` still passes with `--free-end-link`.
  - `sim/lower_shelf_deep_trajectory.csv` should be treated as position-only/reference with `--free-end-link`; it may fail under strict horizontal end-link constraint after the joint-range tightening.

### 2026-04-30 - MuJoCo Manual-Tuning Joint Ranges Reopened

Context:
- User wanted to manually tune poses in the MuJoCo viewer and asked to try the ESP32-factory-style constraints again.
- This is a visualization/manual-teaching change only; it is not a hardware safety claim.

Updated `sim/km1_arm.xml` visual joint ranges:
```text
base_yaw:        -135..135 deg
shoulder_pitch:  -120..120 deg
elbow_pitch:     -135..135 deg
wrist_pitch:     -120..120 deg
wrist_roll:      -135..135 deg
```

Related viewer behavior:
- `sim/km1_trajectory_viewer.py` now keeps the MuJoCo window open after a non-looping trajectory stops.
- Right-side `Control` sliders remain active from the final pose.
- Keyboard selection is enabled after stop:
  - `0`: base yaw
  - `1`: shoulder pitch
  - `2`: elbow pitch
  - `3`: wrist pitch
  - `4`: wrist roll
  - `5`: reserved for gripper; current XML has no gripper actuator yet
- Arrow keys adjust the selected joint:
  - left/right: `-1/+1 deg`
  - down/up: `-5/+5 deg`

Warning:
- Physical servo range, zero, direction, scale, and collision margins are still unverified.
- Do not send poses discovered under these broad MuJoCo ranges to hardware until raw serial and servo-feedback gates are passed.

### 2026-04-30 - Pick/Place Demo Release Target Moved From Manual Pose

Context:
- User manually adjusted the MuJoCo final placement posture and clarified the desired behavior: "shoot the arrow first, then draw the target."
- Interpretation: use the manually adjusted end-effector location as the new release target, while still letting the viewer solve IK and keep the end link horizontal at release.

Manual posture observed from MuJoCo sliders:
```text
base_yaw:        0 rad
shoulder_pitch: -1.04 rad
elbow_pitch:     1.95 rad
wrist_pitch:    -0.901 rad
wrist_roll:      0 rad
```

Forward-kinematics estimate from that posture:
```text
q_deg ~= [0.0, -59.6, 111.7, -51.6, 0.0]
ee ~= (231.15, 0.0, 124.25) mm
ee local x-axis ~= (1.0, 0.0, -0.009), nearly horizontal
```

Initial `PICK_PLACE_ONLY_MODE` release target from manual pose:
```text
FIXED_PLACE_APPROACH_POSE = (231.15, 40.0, 104.25)
FIXED_PLACE_FINAL_POSE    = (231.15, 60.0, 124.25)
```

Important:
- The final/release CSV rows still set `horizontal_end_link=1`.
- For horizontal placement rows, `sim/km1_trajectory_viewer.py` now straightens `wrist_roll` to `0 deg` before release so the held book is not rolled sideways.
- The viewer is not locking to the exact manually adjusted joint angles; it uses the manual pose only to place the target around the correct end-effector location.
- If exact joint replay is needed later, add an explicit joint-waypoint mode instead of overloading Cartesian target rows.

Follow-up adjustment:
- User wanted the release target pushed slightly deeper into the shelf and the return book moved slightly closer to the arm.
- Defaults updated:
```text
FIXED_PICK_POSE          = (300.0, 100.0, 150.0)
FIXED_PLACE_APPROACH_POSE = (231.15, 40.0, 104.25)
FIXED_PLACE_FINAL_POSE    = (231.15, 60.0, 124.25)
```
- `sim/km1_arm.xml` side return-bin/book visual moved from approximately `x=0.34 m` to `x=0.30 m`.
- Verification:
```text
pick target [300,100,120] -> MuJoCo IK ok, error ~= 2.9 mm
place approach [231.15,40,104.25] -> ok
place final [231.15,60,124.25] -> ok
wrist_roll remains 0 deg on placement rows
```

Second follow-up adjustment:
- User wanted the final book placement pushed another `0.75` book-width deeper into the shelf.
- In the current MuJoCo book geometry, the cover width is approximately `90 mm`, so `0.75 * 90 mm = 67.5 mm`.
- Final shelf-depth `y` was moved from `60.0 mm` to `127.5 mm`; approach `y` moved to `107.5 mm`.
- User also clarified that the arm's grasp point must be exactly the book xyz used when executing the code.
- Viewer update: `sim/km1_trajectory_viewer.py` now moves the return-book visual from the first trajectory row where `return_book_visible=1`, so `--book-xy/--book-z` changes both the arm's pickup target and the displayed return-book position.
- Follow-up fix: the return-book xyz is now defined as the book-spine/left-edge grasp marker, not the book center. The return-book body is offset from that marker by about `45 mm` in `+x` and `22 mm` in `+z`, so the gripper approaches the spine/left side instead of penetrating the book body.
- Pickup rows now also set `horizontal_end_link=1`, matching the placement orientation convention and keeping the gripper level at the spine.
- Current defaults:
```text
FIXED_PICK_POSE           = (300.0, 100.0, 150.0)
FIXED_PLACE_APPROACH_POSE = (231.15, 107.5, 104.25)
FIXED_PLACE_FINAL_POSE    = (231.15, 127.5, 124.25)
```
- Verification:
```text
pick target [300,100,120] -> MuJoCo IK ok, error ~= 2.9 mm
place approach [231.15,107.5,104.25] -> ok
place final [231.15,127.5,124.25] -> ok
wrist_roll remains 0 deg on placement rows
return book grasp marker ~= (0.300, 0.100, 0.120) m
return book center visual ~= (0.345, 0.100, 0.142) m
```

Third follow-up adjustment:
- User manually tuned a better book pickup posture because the default IK solution made joint 1/shoulder posture undesirable.
- Manual pickup posture from MuJoCo sliders:
```text
base_yaw:        0.504 rad
shoulder_pitch: -0.935 rad
elbow_pitch:     1.71 rad
wrist_pitch:    -0.812 rad
wrist_roll:      0 rad
```
- Forward kinematics from that posture:
```text
q_deg ~= [28.88, -53.57, 97.98, -46.52, 0.0]
ee ~= (218.0, 120.23, 131.69) mm
```
- Defaults updated so the book-spine grasp marker is at that manually tuned end-effector location:
```text
FIXED_PICK_POSE           = (218.0, 120.23, 131.69)
FIXED_PLACE_APPROACH_POSE = (231.15, 107.5, 104.25)
FIXED_PLACE_FINAL_POSE    = (231.15, 127.5, 124.25)
FIXED_PLACE_RETREAT_POSE  = (218.0, 90.0, 150.0)
```
- `sim/km1_trajectory_viewer.py` uses this pickup posture as the preferred IK seed for rows where `return_book_visible=1`.
- Verification:
```text
pick target [218.0,120.23,131.69] -> MuJoCo IK ok, error ~= 0.0 mm
pickup q_deg -> [28.88, -53.57, 97.98, -46.52, 0.0]
return book grasp marker ~= (0.218, 0.120, 0.132) m
return book center visual ~= (0.263, 0.120, 0.154) m
wrist_roll remains 0 deg
```

Fourth follow-up adjustment:
- User noticed the trajectory entered manual control immediately after release, so the post-release return/retreat motion was visually missing.
- Added `MOVE_TO_PLACE_RETREAT` after gripper `OPEN`.
- The placed book remains visible on the shelf while the arm retreats.
- Manual control now begins after the retreat waypoint, not immediately at the release contact point.
- Current generated CSV has 6 rows:
```text
1. pickup before grasp: return book visible
2. pickup after grasp: held book visible
3. place approach
4. place final before release
5. place final after release: placed book visible
6. post-release retreat: placed book remains visible
```
- Verification:
```text
place retreat [218.0,90.0,150.0] -> MuJoCo IK ok, error ~= 0.1 mm
wrist_roll remains 0 deg on all 6 rows
```

Viewer playback fix:
- User observed that after grasp/release the arm looked stuck or like it placed the book in place.
- Cause: duplicate-position state changes used the full `steps_per_segment=80`, so "before/after grasp" and "before/after release" held at the same pose too long.
- `sim/km1_trajectory_viewer.py` now uses short holds for repeated poses and full interpolation only for real motion segments.
- Verified current waypoint joint deltas:
```text
pickup before -> pickup after: 0 deg hold
pickup -> approach: ~10.9 deg motion
approach -> final: ~10.3 deg motion
release before -> release after: 0 deg hold
release -> retreat: ~28.4 deg motion
```

Fifth follow-up adjustment:
- User observed that the arm should rotate the base/yaw nearly 90 degrees after pickup before reaching the bookshelf.
- Problem found: previous placement target `x≈231,y≈127` was still in the side/diagonal direction near the pickup side, so base yaw barely changed.
- Corrected shelf placement target to the front/left bookshelf region:
```text
FIXED_PICK_POSE           = (218.0, 120.23, 131.69)
FIXED_PLACE_APPROACH_POSE = (-40.0, 240.0, 104.25)
FIXED_PLACE_FINAL_POSE    = (-40.0, 260.0, 124.25)
FIXED_PLACE_RETREAT_POSE  = (-40.0, 220.0, 150.0)
```
- Verification:
```text
pickup base_yaw ~= 28.9 deg
place approach base_yaw ~= 99.5 deg
place final base_yaw ~= 98.7 deg
retreat base_yaw ~= 100.3 deg
pickup -> approach joint delta ~= 70.6 deg
all placement/retreat targets solve with horizontal end link and wrist_roll=0
```

Sixth follow-up adjustment:
- User asked to reduce base/yaw rotation by about `10 deg`.
- Placement x was moved from `-80 mm` to `-40 mm` while preserving shelf depth `y`.
- This reduces shelf-side base yaw from about `108 deg` to about `99 deg`.

Current run command:
```bash
python3 主程序代码/main.py --viewer
```

Equivalent explicit command:
```bash
python3 主程序代码/main.py --viewer \
  --book-xy 218.0 120.23 --book-z 100.0 \
  --pick-approach-clearance 100.0 \
  --post-grasp-lift 50.0 \
  --place-transfer -40.0 220.0 150.0 \
  --place-approach -40.0 240.0 104.25 \
  --place-final -40.0 260.0 124.25 \
  --place-retreat -40.0 220.0 150.0
```

Current viewer behavior:
- Main program writes `sim_output/control_trajectory.csv`.
- Viewer is launched with `mjpython` by `主程序代码/visualization.py`.
- After the non-looping trajectory stops, the MuJoCo window remains open for manual joint tuning.
- Keyboard controls after stop:
  - `0..4` select arm joints
  - `5` is reserved for gripper/no current actuator
  - left/right: `-1/+1 deg`
  - down/up: `-5/+5 deg`

General integration note:
- Added `主程序代码/pick_place_plan.py` with a `PickPlacePlan` dataclass.
- `controller.py` now reads the minimal flow through `config.get_pick_place_plan()` instead of directly constructing poses from scattered fixed constants.
- Current CLI/default values are only one provider for this plan.
- Future vision/planning code should provide the same seven fields:
```text
pick_approach  # pre-grasp point above pick, same XY by default, world mm
pick           # book-spine/left-edge grasp marker, world mm
pick_lift      # post-grasp lift above pick, same XY by default, world mm
place_transfer # shelf-side high transfer before lowering, world mm
place_approach # pre-release approach, world mm
place_final    # horizontal release point, world mm
place_retreat  # post-release retreat, world mm
```
- Detailed contract added to `主程序代码/CONTROL_INTERFACE_SPEC.md`.

Viewer playback start fix:
- `sim/km1_trajectory_viewer.py` now records the MuJoCo model's initial qpos immediately after loading the XML.
- Animation starts from that initial arm state and interpolates to `pick_approach`, then descends to the book-spine pickup target.
- The first CSV row is now the overhead pre-grasp waypoint; it is no longer treated as the viewer's starting arm pose.

Pickup approach update:
- `PickPlacePlan` now includes `pick_approach` before `pick`, and `pick_lift` after grasp.
- Default `pick_approach` is derived as `(pick.x, pick.y, pick.z + 100 mm)`.
- Default `pick_lift` is derived as `(pick.x, pick.y, pick.z + 50 mm)`.
- CLI supports `--pick-approach-clearance MM` or full `--pick-approach X Y Z`.
- The return-book visual anchor uses the last visible return-book waypoint before grasp, so the book stays at the real pickup point while the gripper starts above it.

Pickup height adjustment:
- User clarified that the return book should sit almost on the floor.
- Default pickup/book-spine marker is now `(218.0, 120.23, 100.0)`, matching 50% height on the measured 200 mm tall book.
- With the current `100 mm` clearance, `pick_approach` is now `(218.0, 120.23, 200.0)`.
- The return-book visual offset is kept simple and stable; the book center is aligned to the grasp point in Z.

Post-place center-up update:
- After `place_retreat`, MuJoCo viewer appends a joint-space return-to-center pose.
- MuJoCo internal center-up target remains
  `[base_yaw, shoulder_pitch, elbow_pitch, wrist_pitch, wrist_roll] = [0, -90, 0, 0, 0] deg`.
- Human-facing/hardware-calibrated reporting may treat this as joint1
  physical upright/default `0 deg`, but that conversion must not alter MuJoCo
  internal IK geometry.
- Manual joint control starts after this vertical arm pose, with the placed book remaining visible on the shelf.

Book dimension update:
- User measured the book as `200 x 140 x 10 mm`.
- MuJoCo book geometry now uses this as `height x spine-to-pages width x thickness`.
- Return-book, held-book, and placed-book geoms were updated together.
- Return-book center offset from the spine grasp marker is now `(70, 0, 0) mm`, so the default `pick.z=100 mm` sits at 50% book height.

### 2026-04-29 - Physical Link Measurements Added

User measured the current physical prototype:
```text
L0: 103 mm
  height from ground to the first pitch joint above the base yaw platform
L1: 105 mm
  first arm segment
L2: 86.35 mm
  second arm segment
L3: about 100 mm
  next/end-effector-side segment length measured on the prototype
```

Code updates:
- `sim/km1_arm.xml` now uses the measured physical dimensions for visualization:
  - shoulder joint height approximately `103 mm`
  - upper arm `105 mm`
  - forearm `86.35 mm`
  - wrist/end-effector-side link `100 mm`
- `sim/vendor_km1_kinematics.py` now includes a `measured_physical` profile:
  - `L0=103`, `L1=105`, `L2=86.35`, `L3=100`

Important interpretation:
- The ESP32 factory firmware source still appears to use internal kinematics parameters:
  - `L0=100`, `L1=105`, `L2=75`, `L3=180`
- Therefore there may be a mismatch between:
  1. physical/measured geometry
  2. factory firmware IK parameters
  3. MuJoCo visualization geometry
- For hardware command generation while the ESP32 firmware remains factory/unmodified, continue using `esp32_factory`.
- For visual/mechanical intuition, use the updated MuJoCo model and/or `measured_physical`.
- This mismatch must be resolved by real serial tests before trusting precise placement coordinates.

Example comparison at target `(0, 240, 95) mm`, `alpha=-45:-25`:
```text
esp32_factory     -> ok, alpha=-45, PWM=(1500,1323,1838,1014)
measured_physical -> ok, alpha=-45, PWM=(1500,1113,1788,1174)
```

Risk:
- Same target can produce significantly different servo commands depending on which parameter set is used.
- This strengthens the need for closed-loop feedback or empirical calibration once hardware serial control is available.

### 2026-04-29 - XYZ Target Definition Updated

User clarified the intended target convention:
- `XYZ` should represent a landmark/control point of the held object.
- For the book-reshelving task, choosing the lower gripper grasp position is reasonable.

Implication:
- The effective tool length for our own measured-object IK should be closer to `L3≈125 mm`, not just the visible/measured wrist-side segment length `L3≈100 mm`.

Code updates:
- `sim/vendor_km1_kinematics.py` now includes `measured_grasp`:
```text
L0=103 mm
L1=105 mm
L2=86.35 mm
L3=125 mm
```
- `sim/km1_arm.xml` now places `ee_site` at the held-object/gripper grasp control point:
```text
wrist pitch body -> wrist roll body: 100 mm
wrist roll body -> ee_site: 25 mm
effective wrist-pitch-to-XYZ length: 125 mm
```

Important interpretation:
- `esp32_factory` remains the baseline for unmodified firmware command prediction.
- `measured_grasp` is the better profile for our future custom IK where `XYZ` means held-book control point.
- MuJoCo visualization now uses the held-object control point for target tracking.
- A discrepancy remains: the measured analytic profiles and MuJoCo numeric IK do not yet share perfectly identical angle conventions. This is acceptable for visualization but must be resolved before using custom IK on hardware.

Concrete inconsistency observed:
- For aggressive lower-shelf visualization targets around `(0, 300, 105) mm`:
  - `esp32_factory` with `alpha=-35:-25` reports reachable.
  - MuJoCo numeric IK with the updated `ee_site` also reaches the target visually with small error.
  - `measured_physical` and `measured_grasp` analytic profiles can reject the same target under the same alpha window.
- Therefore the current profiles are not interchangeable.

Likely causes:
- Vendor `esp32_factory` parameters may be effective/demo-tuned parameters, not pure physical CAD dimensions.
- The measured `L3` depends on target definition: wrist endpoint vs held-object grasp point.
- MuJoCo joint sign/zero conventions are not yet fully matched to vendor servo angle conventions.
- `Alpha` meaning in vendor IK and visual end-link orientation in MuJoCo are related but not yet proven identical.

Do not ignore:
- A point being reachable in the viewer does not prove it is valid for ESP32 `$KMS`.
- A point being valid in `esp32_factory` does not prove the measured physical geometry model is calibrated.
- A PWM command generated from `measured_grasp` should not be sent to hardware until servo zero, direction, scale, and feedback are verified.

Required future calibration before custom IK on hardware:
1. Confirm actual serial command path on ESP32.
2. Confirm whether `$KMS:x,y,z,time!` is supported by the current firmware.
3. Confirm servo index mapping for servo0-5.
4. Confirm each main joint's zero pose and positive direction.
5. Confirm angle/PWM or bus-servo command scale.
6. Compare commanded targets against observed/feedback joint positions.
7. Only then decide whether to replace or supplement factory IK with `measured_grasp` custom IK.

### 2026-04-30 - PWM Command Path Confirmed and Teaching Tool Added

Environment:
- Local workspace: `/Users/xinruixiong/Desktop/ME470`

Hardware / ROS2 state:
- User reported that the basic ROS2 arm connection attempt is complete enough to send PWM commands.
- User confirmed that sent PWM commands are effective on the physical arm.
- User later clarified that the main ROS2 command shape is an action-group-style wrapper:
  - `{G0001#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}@GroupDone!`
- Exact ROS2 package/node path was not found in this workspace during this session, so the teaching helper was added as a standalone serial/PWM tool rather than integrated into a ROS2 package.

High-priority reusable commands:
- Stop all current motion:
  - `$DST!`
  - In firmware internals this forwards as `#255PDST!`.
  - This stops motion and holds at the controller's tracked current position; it is not torque-off/unload.
- Stop one servo:
  - `$DST:<index>!`, for example `$DST:3!`
  - In firmware internals this forwards as `#003PDST!`.
- Return/home/neutral pose:
  - Use an explicit known-good pose command rather than assuming a hidden home command.
  - Current user-provided ROS2-format candidate/known return pose:
    - `{G0001#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}@GroupDone!`
  - If a home action group has been stored on the controller, `$DGS:0!` calls action group `G0000`.
  - STM32 source comments mention `$DJR!` as "all servo reset", but the reviewed parser did not show an implemented `$DJR!` branch; do not depend on it until verified on hardware.

New artifact:
- `tools/km1_pwm_teach.py`
  - Interactive keyboard-driven PWM teaching helper.
  - Sends vendor-format multi-servo commands like `{#000P1500T0200!#001P1500T0200!...}`.
  - Also supports the observed ROS2/action-group wrapper via `--group-wrapper`, producing `{G0001#000P...}@GroupDone!`.
  - Records commanded PWM poses to CSV.
  - Default output: `teach_pwm_poses.csv`.
  - Includes `$DST!` stop command on key `x`.
  - Does not assume servo feedback; it records commanded PWM state, not measured physical joint feedback.

Recommended dry-run command:
```bash
python3 tools/km1_pwm_teach.py --dry-run
```

Example hardware command:
```bash
python3 tools/km1_pwm_teach.py --port /dev/ttyUSB0 --baud 115200 --output teach_pwm_poses.csv
```

Example using the observed ROS2/action-group command wrapper:
```bash
python3 tools/km1_pwm_teach.py --port /dev/ttyUSB0 --baud 115200 --group-wrapper --group-id 1 --output teach_pwm_poses.csv
```

Keyboard controls:
```text
0-5      select servo
[ / ]    decrease / increase selected servo by small step
{ / }    decrease / increase selected servo by large step
Enter    send current 6-servo PWM pose
g        increment group id, if --group-wrapper is enabled
l        toggle live-send after each adjustment
s        save current pose to CSV
x        send stop command ($DST!)
p        print current command
q        quit
```

Important interpretation:
- This is a practical remote teaching / point-recording tool.
- It is not yet true hand-guided teaching because servo unload/torque-off and read-current-position are still not confirmed.
- `@GroupDone!` is useful as a command completion/ack signal for the current ROS2 path, but it does not by itself prove physical motion completion or provide servo position feedback.
- For true hand-guided teaching, still verify:
  1. whether the servo bus exposes torque enable/disable or unload,
  2. whether current position can be read,
  3. whether the arm can safely re-enable holding at the read-back position.

Vendor-material correction after deeper inspection:
- Do not use PWM/group commands as inputs for true hand-guided teaching. They command target positions and hold the servos there.
- Vendor manual states the physical KM1 uses bus servos and that data feedback supports reading servo position angle, voltage, and temperature.
- The manual points to `总线舵机学习资料` for detailed bus-servo commands, but that standalone document was not found in this workspace.
- Factory ESP32/STM32 source inspected in this workspace exposes high-level PWM-compatible serial parsing, not a documented torque-off/read-position teaching API.
- `$DST!` and `#xxxPDST!` stop current motion at the controller's internally tracked current PWM value. They are not torque-off/unload commands.
- The vendor "同步示教器" example is external-potentiometer teaching: it reads `A0-A5`, maps ADC values to PWM, and sends servo commands. It is not hand-guided teaching by moving the robot arm itself.
- True hand-guided teaching remains a separate bus-servo protocol task: find/obtain the missing bus-servo command table, or probe the raw servo bus for unload/torque-enable plus read-current-position support.

Useful `6.拓展资料` source findings:
- `6.拓展资料/拓展场景/出厂源码` has several controller/application variants: ESP32, STM32, Arduino, and `前抓侧放机械臂程序`.
- These sources are useful for command examples and action-group mining, but they did not reveal a new high-level torque-off/read-position command.
- OpenMV kinematics code sends generated IK commands as four-servo grouped PWM strings:
  - `{#000P...T...!#001P...T...!#002P...T...!#003P...T...!}`
- OpenMV task code uses gripper command examples:
  - old full-open `{#005P1000T1000!}` in several vendor scripts,
  - `{#005P1700T1000!}` as close/grip in several scripts.
- For the current physical demo, do not use the old full-open endpoint for
  normal release. Use `{#005P1400T1000!}` so servo005 does not keep loading at
  the mechanical end stop.
- OpenMV task code also calls action sequences such as `$DGT:1-5,1!`, `$ACTGO!`, `$ACT12!`, and `$ACTBACK!`.
- `前抓侧放机械臂程序/动作组/config.ini` contains vendor PWM/time action tables. Mine this file for conservative seed poses, but verify every pose on the modified physical arm before using it in ROS2.

Gate status update:
- Raw/PWM command effectiveness is now user-confirmed.
- ROS2 path is at least partially confirmed for PWM sending, but completion feedback semantics are still unresolved.
- Next useful replay/control gate: record 3-5 conservative known-good PWM poses with `tools/km1_pwm_teach.py`, then decide whether to wrap this workflow into the ROS2 serial node.
- Next true-teaching gate: obtain or reverse-engineer bus-servo unload/read-position commands before writing a hand-guided teaching script.

### 2026-04-30 - Serial Listen Confirmed and First Joint Range Table Recorded

Environment:
- User is testing from Ubuntu 22 with serial device `/dev/ttyUSB0`.
- Serial baud remains `115200`.

Observed serial receive behavior:
- After starting the listener, the controller/ESP32 output included grouped command echoes and completion feedback.
- Example observed startup/straight command echo:
```text
{G0001#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}
@GroupDone!
```
- Interpretation remains:
  - The grouped command is the motion command/echo.
  - `@GroupDone!` is received completion feedback, not part of the command to send unless a specific wrapper explicitly requires it.

Hardware pose notes:
- Detailed notes are stored in `HARDWARE_POSE_NOTES.md`.
- Startup straight pose:
  - User reports all joints visually straight/extended.
  - User reports all understood angles are `150.0`.
  - PWM targets observed in the command echo are `000=1500`, `001=2000`, `002=2000`, `003=0850`, `004=1500`, `005=1500`.
- Default Z-shaped pose:
  - User reports this is the default pose shape.
  - Exact PWM command still needs to be captured.

First confirmed physical joint ranges:

| Joint | Servo ID | Low-side PWM | High-side PWM | Direction / role |
| --- | --- | ---: | ---: | --- |
| joint0 | 000 | 500 | 2500 | base pan, right -> left as PWM increases |
| joint1 | 001 | ~550 | 2400 | forward -> backward as PWM increases; structure-limited |
| joint2 | 002 | 500 | 2500 | backward -> forward as PWM increases |
| joint3 | 003 | 500 | 2500 | backward -> forward as PWM increases |
| joint4 | 004 | 500 | 2500 | wrist roll, left -> right as PWM increases |
| joint5 | 005 | 500 | 2500 | gripper, open -> closed as PWM increases |

Progress interpretation:
- This is a real calibration milestone: servo index mapping, rough physical range, and sign/direction are now known for all six channels.
- The next safe engineering step is no longer blind serial probing; it is to build a conservative PWM safety table and replay a small set of known-good poses.
- The remaining blocker for true hand-guided teaching is unchanged: high-level PWM/group commands do not unload servos or read physical joint position. That still requires bus-servo torque/readback protocol evidence.

Recommended immediate next actions:
1. Choose conservative software limits inside the measured physical limits, for example avoid the outer `50-100` PWM near each end stop and use a larger margin for `joint1`.
2. Capture the exact PWM command for the default Z-shaped pose.
3. Record 3-5 named, slow, known-good poses: straight/startup, Z-default, safe pick-ready, safe carry, safe gripper-open/closed tests.
4. Compare `measured_grasp` IK-generated PWM outputs against this measured table before sending them to hardware.
5. Keep investigating raw bus-servo unload/read-current-position only after the replay path is reliable.

### 2026-04-30 - IK Profile Hard Rule Update (Structure Mismatch Clarified)

Critical clarification from user:
- Do not use `esp32_factory` as the default IK profile for this project anymore.
- Reason: current robot does not use the vendor's original aluminum frame dimensions; only servos are reused.

Execution rule (effective immediately):
- For this workspace's simulation/control validation path, default IK profile must be `measured_grasp` (or future calibrated project-specific profile), not `esp32_factory`.
- Treat `esp32_factory` as vendor reference only; do not use it for primary target planning or acceptance decisions.

### 2026-05-03 - ESP32 Source Finding: Stored Startup Action May Be Replaying `G0001`

User observation:
- A repeated `G0001`-style command appears to interrupt the first command in the intended action flow.

Vendor resources inspected:
- Main factory ESP32 Mixly project:
  - `项目资源（厂商）/4.源代码程序/机械臂控制器出厂源码/ESP代码v1.1.mix`
- Extension/reference ESP32 project:
  - `项目资源（厂商）/6.拓展资料/拓展场景/出厂源码/滑轨抓取放下程序/ESP32/ESP32程序/ESP代码.mix`

Source conclusions:
- The ESP32 firmware stores action groups in W25Q64 flash.
- Angle-bracket input stores data:
  - `<G0001#...>` stores action group `1`.
  - The firmware replaces `<...>` with `{...}` before writing the action group.
- Runtime command input executes stored groups:
  - `$DGS:1!` executes stored group `1` once.
  - `$DGT:start-end,count!` executes a range of groups and eventually emits `@GroupDone!`.
- A persistent startup command exists as `eeprom_info.pre_cmd`.
  - `setup_start()` parses this startup command if valid.
  - `setup_servo()` also parses it if valid and it starts with `$`.
  - Therefore a saved startup command such as `$DGS:1!` can cause group `1` / `G0001` to run automatically at boot, possibly more than once in this firmware layout.
- The same `save_action()` path supports clearing the startup command:
```text
<$!>
```
Expected feedback:
```text
@CLEAR PRE_CMD OK!
```

Recommended diagnosis before reflashing:
1. Send `$DST!` to stop current motion.
2. Send `<$!>` over the same serial path.
3. Confirm `@CLEAR PRE_CMD OK!`.
4. Power-cycle the board while monitoring serial output.
5. If `G0001` disappears, the issue was saved startup `pre_cmd`, and reflashing is not required for this problem.
6. If `G0001` persists, isolate other input sources: Bluetooth/app, OpenMV, PS2/control logic, and ROS2 sender.

Firmware modification path if still needed:
- Use `ESP代码v1.1.mix` as the primary factory source for the current arm unless proven otherwise.
- To make ROS2 own the arm cleanly, remove or guard the startup `parse_cmd(eeprom_info.pre_cmd)` calls in:
  - `setup_start()`
  - `setup_servo()`
- For a ROS2-only firmware build, consider disabling sensor/PS2 autonomous injection in `loop()`:
  - keep `loop_uart()`,
  - keep `loop_action()`,
  - keep `loop_servo()`,
  - disable or guard `loop_Function()` and `PS2_controll()` unless those inputs are intentionally used.
- Reflashing alone may not erase W25Q64 action groups or `pre_cmd`; clear stored startup behavior explicitly.

---

## 0. How to Use This Document

This playbook is intentionally detailed and non-minimal.
Work strictly in order. Do not skip validation gates.

Each step includes:
- `Action`: what to do
- `Expected`: what you should see
- `Pass`: explicit pass criteria
- `If Fail`: what to check next

If a step fails, stop and resolve before moving forward.

---

## 1. Mission and Scope Clarification

### 1.1 Primary mission right now
- Prove the arm can be controlled from your computer deterministically.
- Then prove the same control path from ROS2.
- Then connect ROS2 motion to your project `motion_adapter.py`.

### 1.2 What is not required yet
- Full perception integration
- Full task planner integration
- Mechanical optimization
- Final production safety certification

---

## 2. Known Assets You Already Have

### 2.1 Main project integration seam
- Existing control framework path:
  - `/Users/xinruixiong/Desktop/ME470/主程序代码`
- Key file for first integration:
  - `/Users/xinruixiong/Desktop/ME470/主程序代码/motion_adapter.py`

### 2.2 Vendor resources (already inspected)
- Vendor resource root:
  - `/Users/xinruixiong/Desktop/ME470/项目资源（厂商）`
- Useful files:
  - Visual command table: `1.教程手册/视觉指令表.docx`
  - OpenMV main: `4.源代码程序/KM1机械臂Openmv视觉模块代码 V3.1/main.py`
  - STM32 protocol parser: `6.拓展资料/.../User/Components/y_usart/y_usart.c`
  - Command logic: `6.拓展资料/.../User/Components/y_global/y_global.c`
  - Host presets: `5.软件工具/5.串口助手/sscom51.ini`

### 2.3 Protocol signals found
- Baud usually `115200`
- ASCII framed commands:
  - `$...!` (command mode)
  - `#...!` (single servo)
  - `{...}` (multi-servo)
  - `<...>` (save/action-group mode)
- Common commands:
  - `$DST!` stop all
  - `$DGT:start-end,count!` run action groups
  - `$KMS:x,y,z,time!` kinematics motion
  - `#005P1700T1000!` gripper-like servo action (example)

---

## 3. Phase A - Hardware + Electrical Baseline

## 3.1 Physical connection baseline

### Step A1: Confirm wiring topology
- Action:
  1. Identify controller board model (ESP32 variant / STM32 controller board).
  2. Identify actuator power source and voltage rating.
  3. Confirm USB data cable is data-capable (not charge-only).
- Expected:
  - You can clearly state: board model, power path, and cable type.
- Pass:
  - All three are known and documented.
- If Fail:
  - Replace cable first, then verify board label and power specs from vendor docs/hardware labels.

### Step A2: Safe power-on sequence
- Action:
  1. Ensure emergency stop / manual power cut is reachable.
  2. Start with low-risk pose / unloaded condition.
  3. Power board and actuator supply in the vendor-recommended order.
- Expected:
  - Board powers up stably, no reset loop, no obvious overcurrent symptoms.
- Pass:
  - Board remains powered for >60s with stable indicators.
- If Fail:
  - Check PSU current capacity, common ground, connector polarity, and shorts.

### Step A3: Mechanical safety baseline
- Action:
  1. Clear workspace around arm.
  2. Limit first test to very small movement.
- Expected:
  - No collisions in first command test window.
- Pass:
  - Safe test envelope established.
- If Fail:
  - Reposition arm physically and reduce motion command amplitude/time.

---

## 4. Phase B - OS Serial Device Baseline

## 4.1 Device detection

### Step B1: Connect USB and detect serial node
- Action:
  1. Connect USB data cable from board to PC.
  2. Check serial devices (Linux typical `/dev/ttyUSB*` or `/dev/ttyACM*`).
- Expected:
  - New serial device appears after plugging board.
- Pass:
  - You can identify one concrete device path.
- If Fail:
  - Install CH340/USB-UART driver, try another USB port/cable, inspect dmesg/system logs.

### Step B2: Permissions
- Action:
  1. Ensure your user has serial permission (often `dialout` on Linux).
  2. Re-login if group membership changed.
- Expected:
  - No permission error when opening serial device.
- Pass:
  - Serial tool can open the port.
- If Fail:
  - Fix user groups/permissions and retry.

### Step B3: Record serial baseline
- Action:
  1. Record in a notes file:
     - device path
     - baud
     - data bits/parity/stop bits
     - board firmware version if known
- Expected:
  - Single source of truth for serial config.
- Pass:
  - Config is written down and reused consistently.
- If Fail:
  - Pause and document before continuing.

---

## 5. Phase C - Vendor Host Baseline (Must Pass Before ROS2)

## 5.1 Install and launch vendor tooling

### Step C1: Install vendor dependencies
- Action:
  1. Install CH340 driver if needed.
  2. Open vendor host software (`Yeahbot V2.0.5.exe`) on compatible machine.
- Expected:
  - Software launches and sees serial port.
- Pass:
  - Port selectable and connectable.
- If Fail:
  - Validate driver and OS compatibility; fallback to serial assistant for protocol-level test.

### Step C2: Connect to board from host app
- Action:
  1. Set serial port and baud to baseline (likely 115200).
  2. Connect and verify no immediate disconnect/reset.
- Expected:
  - Stable connected session.
- Pass:
  - Connected for >2 minutes without random disconnect.
- If Fail:
  - Check cable noise, power stability, incorrect baud, USB autosuspend.

## 5.2 Run vendor known-good actions

### Step C3: Trigger known action group
- Action:
  1. Use action preset/config (`机械臂Km1动作组.ini` / `抓取下放.ini`) or vendor GUI actions.
  2. Run one safe motion sequence.
- Expected:
  - Arm moves as expected and stops.
- Pass:
  - At least one repeatable motion success.
- If Fail:
  - Verify servo bus power and protocol mode; try simpler single-servo action.

### Step C4: Verify stop behavior
- Action:
  1. Trigger stop in host app or equivalent command path.
- Expected:
  - Motion stops quickly and predictably.
- Pass:
  - Stop command works every trial.
- If Fail:
  - Do not proceed to ROS2 until stop path is reliable.

---

## 6. Phase D - Raw Protocol Validation (No ROS2 Yet)

## 6.1 Serial assistant command-level testing

### Step D1: Open serial assistant with baseline settings
- Action:
  1. Use serial tool (e.g. `sscom` profile references from `sscom51.ini`).
  2. Set 115200, 8N1, correct line ending behavior.
- Expected:
  - Tool opens port and can send ASCII strings.
- Pass:
  - Manual command send is possible.
- If Fail:
  - Resolve port lock (close other apps), verify settings.

### Step D2: Send low-risk command first
- Action:
  1. Send a stop command: `$DST!`
- Expected:
  - Device acknowledges and/or motion bus stop behavior is observed.
- Pass:
  - Command accepted without destabilizing system.
- If Fail:
  - Check framing (`!` terminator), encoding, active protocol mode.

### Step D3: Send one deterministic motion command
- Action:
  1. Send a small single-servo command example:
     - `#005P1700T1000!` (example only; adjust safe range)
- Expected:
  - Servo responds predictably.
- Pass:
  - Same command gives same behavior repeatedly.
- If Fail:
  - Clamp PWM range, inspect servo mapping/index, test alternative known-good command from vendor presets.

### Step D4: Optional kinematics command check
- Action:
  1. Test `$KMS:x,y,z,time!` with safe coordinates if supported by current firmware profile.
- Expected:
  - Kinematics path executes or returns clear failure response.
- Pass:
  - You can classify firmware as KMS-supported or not-supported.
- If Fail:
  - Not a blocker if single-servo/multi-servo command path works.

## 6.2 Capture baseline command log

### Step D5: Record 5-command validation set
- Action:
  1. Save exact strings and observed result:
     - stop
     - one single-servo move
     - one multi-servo move
     - one action-group call (if used)
     - one status/ack query (`$GETA!` if available)
- Expected:
  - Reusable protocol smoke set exists.
- Pass:
  - Same set can be replayed and pass twice.
- If Fail:
  - Tighten power and timing assumptions, reduce test complexity.

---

## 7. Phase E - ROS2 Serial Bridge MVP

## 7.1 Package and node skeleton

### Step E1: Create ROS2 package for serial driver
- Action:
  1. Create package (Python or C++).
  2. Define one node as sole serial owner, e.g. `km1_serial_driver`.
- Expected:
  - Node runs and can open serial port at startup.
- Pass:
  - No serial open errors; process stable.
- If Fail:
  - Check permissions and port conflicts.

### Step E2: Add minimal API surface
- Action:
  1. Add service (or topic) to send raw command text.
  2. Add response structure: `ok`, `raw_reply`, `error`.
- Expected:
  - You can request send from ROS2 CLI.
- Pass:
  - CLI invocation returns structured response.
- If Fail:
  - Validate service registration and callback threading.

## 7.2 Replay vendor validation set through ROS2

### Step E3: Replay D5 commands via ROS2
- Action:
  1. Send the same 5 baseline commands from ROS2 service.
- Expected:
  - Behavior matches serial assistant baseline.
- Pass:
  - Functional parity achieved.
- If Fail:
  - Compare byte-level framing and timing between tools.

### Step E4: Add timeout/retry policy
- Action:
  1. Add per-command timeout.
  2. Add bounded retry where safe (not for potentially unsafe move replay).
- Expected:
  - Node does not hang on bad/partial responses.
- Pass:
  - Timeout path tested intentionally.
- If Fail:
  - Add watchdog and explicit error state transitions.

---

## 8. Phase F - ROS2 Motion API Layer

## 8.1 Define high-level interfaces

### Step F1: Movement API
- Action:
  1. Create action/service `MoveToPose` with fields:
     - target pose (x,y,z)
     - time_ms
     - optional mode/profile
- Expected:
  - Upper layer no longer sends raw strings.
- Pass:
  - Move command can be triggered with structured request.
- If Fail:
  - Keep raw service alive while iterating.

### Step F2: Gripper API
- Action:
  1. Create `GripperCommand` (`OPEN` / `CLOSE`).
- Expected:
  - Gripper can be triggered independently.
- Pass:
  - OPEN and CLOSE both validated.
- If Fail:
  - Map to known good servo command directly first.

### Step F3: Stop API
- Action:
  1. Create explicit `StopAll` mapping to `$DST!` (or equivalent).
- Expected:
  - Emergency stop path available from ROS2.
- Pass:
  - Stop test passes repeatedly.
- If Fail:
  - Block further integration until fixed.

## 8.2 Completion criteria semantics

### Step F4: Define when command is “success”
- Action:
  1. Success condition must include positive ack or deterministic completion condition.
  2. Never return success immediately after write-only send.
- Expected:
  - `success` means real completion, not just TX success.
- Pass:
  - Simulated delayed/failed cases produce `fail/timeout` correctly.
- If Fail:
  - Refactor state machine before integration.

---

## 9. Phase G - Integrate with Existing Project Framework

## 9.1 motion adapter integration first

### Step G1: Replace mock motion internals only
- Action:
  1. Keep function signatures in `/主程序代码/motion_adapter.py` unchanged.
  2. Replace internals to call ROS2 motion API.
- Expected:
  - Upstream `controller.py` remains untouched.
- Pass:
  - Existing flow starts and reaches motion calls without interface break.
- If Fail:
  - Check adapter return types and blocking behavior.

### Step G2: Preserve bool contract
- Action:
  1. `move_to(...)` and `gripper_command(...)` return `True` only on real completion.
- Expected:
  - State machine transitions remain correct.
- Pass:
  - Failures propagate as `False` and trigger existing fallback logic.
- If Fail:
  - Add robust exception/timeout mapping in adapter.

## 9.2 End-to-end run with mock perception

### Step G3: Keep perception mocked
- Action:
  1. Run controller with existing `perception_adapter` mock path.
- Expected:
  - Decision framework issues real motion against ROS2 bridge.
- Pass:
  - One complete task cycle succeeds with real movement.
- If Fail:
  - Inspect motion response latency vs controller expectations.

---

## 10. Phase H - Perception Integration (Later)

### Step H1: Introduce perception bridge
- Action:
  1. Replace internals of `perception_adapter.py` with ROS2 topic/service input.
- Expected:
  - Output format remains exactly what controller expects.
- Pass:
  - No controller code changes needed.
- If Fail:
  - Add adapter normalization layer for schema alignment.

### Step H2: Coordinate and units validation
- Action:
  1. Ensure all units and frames are explicit.
  2. Your current project assumes mm; ROS often defaults to meters.
- Expected:
  - No hidden unit mismatch.
- Pass:
  - Spot-check transforms with known landmarks.
- If Fail:
  - Add explicit conversion boundaries in adapter layer.

---

## 11. Failure Trees (Quick Diagnosis)

## 11.1 USB connected but no serial port
- Possible causes:
  - charge-only cable
  - missing driver
  - damaged USB bridge
- Checks:
  - swap cable/port
  - inspect system USB logs
  - test on another machine

## 11.2 Serial opens but commands do nothing
- Possible causes:
  - wrong baud / framing
  - wrong command mode or missing terminator
  - firmware variant mismatch
- Checks:
  - verify exact `!`, `{}`, `$` format
  - compare with vendor known-good commands

## 11.3 Moves in vendor app but not in ROS2
- Possible causes:
  - ROS2 message framing differs
  - timing/flush behavior differs
  - line endings or encoding differences
- Checks:
  - byte-level compare TX payloads
  - add serial sniffer/logging

## 11.4 Can move but cannot stop reliably
- Possible causes:
  - stop command not routed to active channel
  - command queue race
- Checks:
  - enforce single serial writer
  - prioritize stop command path

## 11.5 Controller loop hangs
- Possible causes:
  - adapter blocks forever waiting response
  - no timeout handling
- Checks:
  - enforce hard timeout and return `False`

---

## 12. Acceptance Gates (Mandatory)

Gate 1: Vendor baseline
- Host software can run and stop at least one known motion sequence.

Gate 2: Raw protocol baseline
- Manual serial command set passes twice (same behavior each run).

Gate 3: ROS2 parity
- ROS2 bridge replays same command set with same observable outcomes.

Gate 4: Motion adapter integration
- `motion_adapter.py` backed by ROS2, bool semantics correct.

Gate 5: Framework run
- Existing control loop runs with real motion + mock perception.

Do not proceed to next gate until current gate passes.

---

## 13. Suggested Work Log Template (Use Daily)

For each session, record:
1. Date/time
2. Hardware setup changes
3. Firmware/board identity
4. Serial settings
5. Commands tested
6. Observed behavior
7. Pass/Fail gate status
8. Next blocking issue

This prevents repeated blind debugging.

---

## 14. Immediate Next 24-Hour Plan

1. Complete Phases A-B (hardware + serial OS baseline).
2. Complete Phase C (vendor host baseline motion + stop).
3. Complete Phase D (manual protocol test set and logs).
4. Start Phase E (`km1_serial_driver` ROS2 MVP send/receive).

Stop after each phase and confirm gate status before continuing.

---

## 15. Important Notes for Future AI Sessions

When assisting this project, always:
1. Ask for the latest gate status first.
2. Assume integration is blocked until evidence is provided (logs/videos/command traces).
3. Prefer reproducing vendor-known-good behavior before proposing refactors.
4. Keep adapter signatures stable in `主程序代码`.
5. Prioritize deterministic stop and timeout behavior over feature expansion.

---

## 16. Time-Ordered Simulation Iteration Log

### 2026-04-30 - Current MuJoCo Pick/Place Viewer State

This section is the newest simulation handoff note as of 2026-04-30. If older
sections above show different pickup heights, book dimensions, placement points,
or clearances, treat those as historical tuning notes.

Current run command:
```bash
python3 主程序代码/main.py --viewer
```

Current default pick/place plan:
```text
pick_approach   = (218.0, 120.23, 200.0)
pick             = (218.0, 120.23, 100.0)
pick_lift        = (218.0, 120.23, 150.0)
place_transfer   = (-40.0, 220.0, 150.0)
place_approach   = (-40.0, 240.0, 104.25)
place_final      = (-40.0, 260.0, 124.25)
place_retreat    = (-40.0, 220.0, 150.0)
```

Current book model:
```text
size = 200 x 140 x 10 mm
meaning = height x spine-to-pages width x thickness
pick.z = 100 mm, the 50% height of the book
pick_approach clearance = 100 mm above pick
post-grasp lift = 50 mm above pick
```

Current viewer behavior:
- Starts from the MuJoCo model initial joint state.
- Moves to `pick_approach`, then descends vertically to `pick`.
- Closes gripper at `pick`.
- Lifts the held book to `pick_lift` before rotating toward the shelf.
- Moves to `place_transfer`, a shelf-side high transfer point.
- Moves to shelf placement, releases, and retreats.
- After `place_retreat`, appends a joint-space center-up pose:
```text
[base_yaw, shoulder_pitch, elbow_pitch, wrist_pitch, wrist_roll]
= [0, -90, 0, 0, 0] deg
```
- Physical/hardware-calibrated reporting may display this joint1 upright pose
  as `0 deg`, but the MuJoCo internal value stays `-90 deg`.
- Viewer playback is now step-gated: press `Space` to run each waypoint segment.
  Manual MuJoCo control starts after the final center-up segment finishes.

Verification note:
- MuJoCo XML loads successfully.
- MuJoCo numeric IK solves all current viewer waypoints, including
  `pick_approach=(218.0, 120.23, 200.0)`.
- The sim backend now treats the 200 mm pick-approach point as reachable by
  using a relaxed transition alpha sweep after the stricter placement-style
  alpha checks fail.

Current canonical handoff/spec files:
```text
sim/README.md
sim_output/README.md
主程序代码/CONTROL_INTERFACE_SPEC.md
主程序代码/pick_place_plan.py
```

### 2026-04-30 - Stage Milestone and Cleanup

Current milestone:
- The main program now supports a complete MuJoCo-visible pick/place demo for
  teammate tuning.
- The flow is no longer a single jump from pickup to placement. It is staged as:
```text
initial arm state
-> pick_approach
-> pick
-> close gripper
-> pick_lift
-> place_transfer
-> place_approach
-> place_final
-> open gripper
-> place_retreat
-> center-up joint pose
-> manual MuJoCo control
```
- The book model is based on measured dimensions `200 x 140 x 10 mm`.
- The grasp point is the spine/left-edge point at 50% book height.
- The current default plan is the source of truth for the demo:
```text
pick_approach   = (218.0, 120.23, 200.0)
pick             = (218.0, 120.23, 100.0)
pick_lift        = (218.0, 120.23, 150.0)
place_transfer   = (-40.0, 220.0, 150.0)
place_approach   = (-40.0, 240.0, 104.25)
place_final      = (-40.0, 260.0, 124.25)
place_retreat    = (-40.0, 220.0, 150.0)
```

Cleanup performed:
- Removed obsolete backup artifacts:
```text
sim/km1_arm_backup_0429.xml
sim/pick_and_place_trajectory_backup_0429.csv
```
- Removed stale `+35 mm` pre-grasp test value from `sim_output/sim_runner.py`.
- Updated `config.configure_sim_mode()` so derived `place_transfer` follows
  changed `pick_lift`, `place_final`, or `place_retreat` unless explicitly
  overridden.

Reachability cleanup:
- User physically checked the high pick-approach region and found the real arm
  has enough range.
- Root cause of the earlier false negative: `measured_grasp` vendor-style IK
  only searched its narrow negative alpha sweep, while the high transition point
  solves with a positive alpha around `+62 deg`.
- `sim_output/ik_helper.py` and `sim_output/backend.py` now add a relaxed
  transition alpha sweep fallback after strict placement-style alpha checks
  fail with `no valid alpha`.
- Current default sim run reports `MOVE_TO_PICK_APPROACH` as `True`.

### 2026-04-30 - ME470 Description/Handoff File Map

This repository now has several description-style files. They were written at
different stages, so do not read them as one fully synchronized document set.
Use the newest dated entries in this playbook first, then use the stable README
and interface files below for concrete commands and APIs.

Recommended reading order for the next teammate:
1. `ROS2_BRINGUP_PLAYBOOK.md`
   - Start at the top "Living Document Policy", then jump to the newest dated
     entries in `Time-Ordered Simulation Iteration Log`.
   - This is the time-ordered progress log. Older sections may mention
     coordinates, constraints, or failed attempts that are no longer current.
   - Conflict rule: newest dated entry wins.
2. `sim_output/README.md`
   - Current best handoff for the simulation/backend side.
   - Read this before connecting future vision output to the pick/place demo.
   - It documents the current seven-point `PickPlacePlan` contract:
     `pick_approach`, `pick`, `pick_lift`, `place_transfer`,
     `place_approach`, `place_final`, `place_retreat`.
3. `sim/README.md`
   - Current MuJoCo viewer usage notes.
   - Use this for running the viewer, understanding the book model, manual
     joint controls, and the generated trajectory CSV.
4. `主程序代码/CONTROL_INTERFACE_SPEC.md`
   - Stable interface note for teammates touching perception, planning, or the
     main program.
   - Future vision integration should replace the coordinate provider and feed
     a `PickPlacePlan`, not hardcode motion logic inside `controller.py`.
5. `AI_HANDOFF_CONTEXT.md`
   - Broad AI-to-AI handoff and architecture/status context.
   - Useful when a new assistant or teammate needs the project background, but
     it may include older snapshots. Verify current sim details against this
     playbook and the README/spec files above.
6. `HARDWARE_POSE_NOTES.md`
   - Physical hardware/PWM/pose evidence and notes.
   - Read this before sending commands to real hardware or comparing MuJoCo
     behavior against the physical arm.
7. `error log.md`
   - Historical debugging/error handoff.
   - Useful for understanding why earlier choices were made, but it should not
     be treated as the current source of truth unless a newer note confirms it.

Other file groups:
- `主程序代码/*.py`: active main-program code. Current demo entry point is
  `python3 主程序代码/main.py --viewer`.
- `sim/*.py` and `sim/km1_arm.xml`: MuJoCo model, viewer, vendor-style IK
  helpers, and old grid/probe scripts. For normal use, start with
  `sim/README.md`.
- `sim_output/*.py`: current simulation backend and IK reachability helpers.
  `sim_output/control_trajectory.csv` is generated output, not hand-authored
  source.
- `项目资源（厂商）/*`: vendor manuals, source dumps, videos, and CAD resources.
  Use as reference evidence when needed, not as the current project API.
- `项目主要汇报文件/*`, `组会课件/*`, and `Lecture and Guides/*`: report/class
  materials. They are not the current runtime handoff.
- `__pycache__`, `.DS_Store`, and `sim_output/*.log`: generated/runtime files.
  Ignore unless debugging a specific run.

Quick current run reminder:
```bash
python3 主程序代码/main.py --viewer
```

### 2026-05-01 - Placement Order Adjustment

User observation:
- Before final release, the previous default path effectively moved downward
  first and then pushed the held book deeper into the shelf.
- Real desired behavior is the opposite: push inward first while the book is
  still high, then lower the book, then open the gripper.

Updated default placement segment:
```text
place_transfer   = (-40.0, 220.0, 150.0)
place_approach   = (-40.0, 260.0, 150.0)
place_final      = (-40.0, 260.0, 124.25)
place_retreat    = (-40.0, 220.0, 150.0)
```

Current placement semantics:
```text
pick_lift
-> place_transfer   # shelf-side high transfer point
-> place_approach   # push inward at high Z
-> place_final      # lower vertically to release height
-> OPEN
-> place_retreat
```

Implementation note:
- `FIXED_PLACE_APPROACH_POSE` in `主程序代码/config.py` was changed from
  `(-40.0, 240.0, 104.25)` to `(-40.0, 260.0, 150.0)`.
- `sim/README.md`, `sim_output/README.md`, and
  `主程序代码/CONTROL_INTERFACE_SPEC.md` were updated so future vision/planning
  integration keeps the same push-then-lower placement order.

### 2026-05-01 - Control vs Vision/Decision Responsibility Boundary

Agreed interpretation:
- It is acceptable that current default target points are hardcoded or supplied
  through CLI flags. Those points represent future inputs from the
  vision/decision stack.
- The control/MuJoCo module is not responsible for detecting the book, choosing
  the best shelf gap, or optimizing the final placement target.
- The control/MuJoCo module is responsible for receiving a grasp point and
  placement target(s), deriving generic intermediate waypoints, checking
  reachability through IK, and executing/visualizing one normal `grip & place`
  task.

Current reusable motion policy:
```text
pick_approach
-> pick
-> CLOSE
-> pick_lift
-> place_transfer
-> place_approach
-> place_final
-> OPEN
-> place_retreat
```

Documentation updated:
- `AI_HANDOFF_CONTEXT.md` now explicitly warns future agents not to treat the
  demo as a vision planner or global optimizer.
- `主程序代码/CONTROL_INTERFACE_SPEC.md` now states that vision/decision provides
  the target points, while control derives intermediate motion waypoints and
  checks IK.
- `sim_output/README.md` now explains that hardcoded/CLI coordinates are only
  temporary stand-ins for future coordinate providers.

### 2026-05-01 - IK Candidate Cost Hook

A minimal optimization-control structure was added without changing current
behavior:
- `主程序代码/config.py` now contains `IK_COST_WEIGHTS`,
  `IK_PREFERRED_JOINT_ANGLES_DEG`, `IK_JOINT_LIMITS_DEG`, and
  `IK_PREFERRED_ALPHA_DEG`.
- All current weights are `0.0`, so the cost structure is inactive for motion
  selection and the present demo result should remain unchanged.
- `sim_output/ik_helper.py` can now score multiple IK alpha candidates with:
  `joint_limit`, `preferred_posture`, `motion_smoothness`, and `alpha`.
- Tie handling keeps the previous behavior when all costs are equal.
- `sim_output/logger.py` records `selection_cost` and `cost_breakdown` for
  future tuning.

Intended future use:
- If a joint angle looks too extreme or unsafe, increase a corresponding cost
  weight instead of hardcoding a one-off special case in the state machine.
- Keep this as candidate ranking, not full MPC/trajectory optimization, unless
  the project scope changes.

### 2026-05-01 - Definition-Level ROS2/Serial Command Coverage

Current command-definition status:
- `move_to` records already contain IK-derived vendor-format commands for
  servos `#000-#003`, for example `{#000P...T1500!#001P...}`.
- The gripper is servo `#005` in the ROS2/vendor command path.
- `gripper_command("OPEN")` now maps to `{#005P1400T1000!}`.
- `gripper_command("CLOSE")` now maps to `{#005P1700T1000!}`.

Meaning:
- `sim_output` is still not a ROS2 node and does not send hardware commands by
  itself.
- At the definition layer, the log/event stream now contains enough command
  strings for a future ROS2 bridge to publish/send:
```text
MOVE_TO          -> output.command for #000-#003
OPEN/CLOSE       -> output.command for #005
```

### 2026-05-01 - Before ROS2 Node: Command Recognition Smoke Test

Next integration step:
- Eventually define a ROS2 node/bridge that publishes or sends the command
  strings generated by the control pipeline.
- Before building the node, first test whether the connected arm controller can
  recognize one complete exported command sequence.

Implementation added:
- `sim_output/export_command_sequence.py` reads the latest `sim_output.log`
  session and exports all successful `move_to` and `gripper_command` records.
- Output path:
```text
sim_output/hardware_command_sequence.txt
```

Historical exported default sequence from the first recognition test. This is
obsolete after later hardware calibration; do not use it for the current demo:
```text
{#000P1047T1500!#001P0834T1500!#002P1568T1500!#003P2026T1500!}
{#000P1047T1500!#001P1162T1500!#002P1769T1500!#003P1107T1500!}
{#005P1700T1000!}
{#000P1047T1500!#001P1155T1500!#002P1570T1500!#003P0981T1500!}
{#000P1576T1500!#001P1168T1500!#002P1503T1500!#003P0835T1500!}
{#000P1564T1500!#001P1146T1500!#002P1614T1500!#003P1079T1500!}
{#000P1564T1500!#001P1111T1500!#002P1615T1500!#003P1062T1500!}
{#005P1400T1000!}
{#000P1576T1500!#001P1168T1500!#002P1503T1500!#003P0835T1500!}
```

Hardware caution:
- For first recognition test, send one line at a time and wait for controller
  feedback such as `@GroupDone!` or a timeout before sending the next line.
- Do not stream all lines blindly until completion feedback is confirmed.

### 2026-05-02 - Ubuntu Serial Sender Pattern Confirmed

User provided `ROS2—1.txt` with a confirmed Ubuntu 22 serial bringup pattern:
```text
port = /dev/ttyUSB0
baud = 115200
dtr = False
rts = False
open serial
sleep 2 s
read feedback with timeout
```

Added hardware smoke-test sender:
```bash
python3 sim_output/send_hardware_sequence.py --port /dev/ttyUSB0 --baud 115200
```

Dry-run check:
```bash
python3 sim_output/send_hardware_sequence.py --dry-run
```

Behavior:
- Loads `sim_output/hardware_command_sequence.txt`.
- Sends one vendor command line at a time.
- Waits for `@GroupDone!` by default before sending the next line.
- Also waits for the command's own `Txxxx` duration plus a `0.7 s` settle
  margin before sending the next command.
- If feedback arrives before physical motion visibly settles, use
  `--fixed-step-delay 2.5` or increase `--settle-margin`.
- Prints raw and decoded RX feedback.
- Exits on timeout instead of blindly streaming all commands.

This is still a smoke-test sender, not the final ROS2 node. The final node can
reuse the same open/write/read pattern and completion-feedback rule.

### 2026-05-02 - Hardware Sender Step Timing Adjustment

Hardware observation:
- Sending the whole sequence through the sender made the arm move, but some
  actions looked rushed, overlapped, or swallowed.
- Likely cause: controller feedback can arrive before physical servo motion has
  fully settled, especially for raw PWM commands with `T1500/T1000`.

Sender update:
- `sim_output/send_hardware_sequence.py` now parses the largest `Txxxx` token in
  each command and waits that duration plus `--settle-margin` before sending the
  next command.
- Default `--settle-margin` is `0.7 s`.
- A fixed delay can be forced for smoke tests:
```bash
python3 sim_output/send_hardware_sequence.py --port /dev/ttyUSB0 --baud 115200 --fixed-step-delay 2.5
```

### 2026-05-02 - Raw PWM Feedback Handling Correction

Hardware observation from Ubuntu screenshot:
- First raw PWM command echoed back.
- Controller then emitted a startup-group-like pose and `@GroupDone!`.
- Second raw PWM command echoed back but did not emit `@GroupDone!`, causing the
  sender to time out.

Conclusion:
- Do not require `@GroupDone!` for every raw `{#000...}` PWM command.
- Raw commands may only echo; physical timing should be handled by the command's
  `Txxxx` duration plus settle margin.
- Require `@GroupDone!` only for known group/action commands when explicitly
  requested.

Sender update:
- `sim_output/send_hardware_sequence.py` now defaults to no required feedback
  token.
- It reads/prints feedback for `--feedback-read-window 0.5` seconds, then waits
  `Txxxx + --settle-margin` before sending the next command.
- To force group feedback for a known group command:
```bash
python3 sim_output/send_hardware_sequence.py --commands sim_output/reset_startup_pose.txt --port /dev/ttyUSB0 --baud 115200 --expected-feedback '@GroupDone!'
```

### 2026-05-04 - Target-Triggered Sequence Entry Added

Current integration step:
- Added a target-driven hardware entry point in `主程序代码/main.py`.
- The caller provides only:
  - `--pick X Y Z`: book-spine grasp point in mm.
  - `--place X Y Z`: final shelf placement point in mm.
- The program derives the intermediate pick/place waypoints, computes MuJoCo IK
  without opening the viewer, writes the calibrated raw ASCII command sequence,
  and can call the existing serial sender automatically.

Dry-run first:

```bash
python3 主程序代码/main.py \
  --run-target-sequence \
  --pick 218.0 120.23 115.0 \
  --place -40.0 260.0 124.25 \
  --dry-run
```

Hardware run on Ubuntu after reviewing the command preview:

```bash
python3 主程序代码/main.py \
  --run-target-sequence \
  --pick 218.0 120.23 115.0 \
  --place -40.0 260.0 124.25 \
  --hardware-port /dev/ttyUSB0 \
  --hardware-baud 115200
```

Generated files:
- `sim_output/control_trajectory.csv`
- `sim_output/hardware_command_sequence.txt`
- `sim_output/TARGET_SEQUENCE_SUMMARY.md`

Important:
- The MuJoCo viewer is not required for runtime execution. It is only a
  debugging/tuning UI.
- Runtime still needs the MuJoCo Python calculation dependency unless this is
  later replaced by a standalone IK module:
  `python3 -m pip install mujoco numpy pyserial`.
- `export_command_sequence.py` is legacy/log-based and should not be used as
  the current verified hardware source because it does not own the latest
  target-driven MuJoCo angle mapping or base-only transfer behavior.

### 2026-05-04 - Start Trigger and Small-Move Timing Update

Demo/start behavior:
- Real hardware target-sequence runs now wait after command generation and
  preview. During the current test stage, press Space or Enter to start.
- This is the software stand-in for the required large physical start button.
- Dry-run skips the trigger wait and never opens serial.

Current hardware command:

```bash
python3 主程序代码/main.py \
  --run-target-sequence \
  --pick 218.0 120.23 115.0 \
  --place -40.0 260.0 124.25 \
  --wait-trigger space \
  --hardware-port /dev/ttyUSB0 \
  --hardware-baud 115200
```

Dynamic timing:
- Ordinary arm commands now assign `Txxxx` per servo from adjacent PWM deltas:
  - `delta < 20 PWM` -> `T0400`
  - `delta < 120 PWM` -> `T0800`
  - otherwise -> `T1500`
- First arm command remains conservative at `T1500`.
- Base-only turn remains fixed `T2500`.
- Gripper close/open and measured home remain fixed.
- `TARGET_SEQUENCE_SUMMARY.md` includes a PWM delta / timing audit table.

### 2026-05-06 - MuJoCo Shelf Geometry Update

MuJoCo scene update:
- Shelf visual now has two layers.
- Shelf board thickness is `10 mm`.
- First shelf board spans `z=30..40 mm`, so first-layer placement support is
  `z=40 mm`.
- Layer height is `240 mm`, so the second shelf support surface is `z=280 mm`.
- `LOW_SHELF_TOP_Z_M` in `sim/km1_trajectory_viewer.py` is now `0.040` to snap
  the placed-book visual to the lower shelf top.
- This update only changes scene/visual shelf geometry and placed-book visual
  grounding. It does not change the default target coordinates or PWM mapping.

### 2026-05-02 - Single Reset/Startup Pose File

For safer hardware testing before the full sequence, added:
```text
sim_output/reset_startup_pose.txt
```

It contains an observed startup/reset test command from `HARDWARE_POSE_NOTES.md`:
```text
{G0001#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}
```

Ubuntu command:
```bash
python3 sim_output/send_hardware_sequence.py --commands sim_output/reset_startup_pose.txt --port /dev/ttyUSB0 --baud 115200 --fixed-step-delay 2.5
```

Note:
- This uses an explicit known observed pose command.
- User later observed that this pose can appear physically skewed. Do not treat
  it as a calibrated "arm straight up" or geometric home pose until servo
  zero/direction definitions are calibrated.
- Do not rely on `$DJR!` or other hidden reset commands until they are verified
  on this hardware path.

### 2026-05-02 - Hardware/Simulation Joint Definition Mismatch

Hardware observation:
- The current command sequence can drive the physical arm through the full
  grip-and-place flow.
- However, the real physical pose differs noticeably from the MuJoCo pose,
  especially around the last two links and end effector. The book is not held
  level in the same way as the simulation predicts.

Current diagnosis:
- The task policy and waypoint flow are not the primary suspected failure.
- Several joints likely have code-side definitions that are reversed or offset
  relative to the physical servo definitions.
- This is especially important for wrist/end-effector behavior. `servo003`
  direction/inversion and `servo004` wrist-roll handling should be checked
  before trusting hardware execution as a calibrated digital-twin match.
- Raw PWM commands such as `{#000P...#003P...}` are direct servo targets, so a
  large mismatch here should be treated first as a servo mapping/profile
  calibration problem, not as the controller secretly re-solving Cartesian IK.

Next calibration direction:
- Reset to the known startup pose.
- Probe one servo at a time with small, conservative PWM changes.
- Record for each servo: physical joint role, positive direction, neutral PWM,
  safe range, and whether the sign matches the MuJoCo/IK convention.
- After the table is measured, update or create a hardware-calibrated IK/profile
  instead of hand-tuning the existing pick/place waypoints around a wrong model.

### 2026-05-02 - `G0001` Command Behavior

Hardware/terminal observation:
- Sending the single command
  `{G0001#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}`
  produces an exact echo from the controller.
- User observed that this appears to trigger/restore the controller's recorded
  initialization or homing action group and can interrupt the desired motion.
- Therefore `G0001` should not be treated as a neutral raw PWM wrapper for
  arbitrary pose testing.

Working interpretation:
- `G0001` likely identifies a stored/vendor action group or initialization
  group, not just "send these six PWM values".
- Keep this command in the notes because it may be useful later for reverse
  engineering factory actions.
- For ordinary direct servo pose tests, prefer raw PWM command format without
  the `G0001` prefix, e.g. `{#000P...!#001P...!}`.

Terminal note:
- Bash/zsh may treat `!` as history expansion and print `event not found` if
  the command string is not quoted safely.
- Use single quotes around the complete command string, or disable history
  expansion with `set +H` in bash before typing protocol strings containing `!`.

### 2026-05-03 - sim_out vs Physical Extra Motions

Observed mismatch:
- MuJoCo/sim_out appears to go directly toward the book grasp waypoint, while
  the physical arm may first move upright, then into a Z/default pose, then move
  toward the book.
- At the end, the MuJoCo viewer shows a center-up motion, but the physical
  sequence may not return to that upright pose.

Code inspection:
- `sim_output/hardware_command_sequence.txt` starts directly with the exported
  IK `pick_approach` PWM command. It does not contain `G0001` and does not
  contain an explicit Z-default command.
- The sender does not append stop/home/default commands.
- `controller.py` calls `go_home()` after `place_retreat`, but in SIM_MODE this
  currently only acknowledges the command. It is not logged as a concrete
  `move_to`/PWM command, so `export_command_sequence.py` cannot export a final
  hardware home pose.
- `sim/km1_trajectory_viewer.py` independently appends a visual center-up
  joint-space motion after the CSV waypoints. This viewer-only final motion is
  not equivalent to a hardware command sequence entry.

Conclusion:
- Extra physical upright/Z motions before the first pick waypoint are not from
  the exported sim_out command list. They are most likely controller
  startup/action-group behavior or another active control source.
- Final viewer center-up is not currently represented in hardware export. Do
  not assume hardware will end upright until a calibrated hardware home command
  is defined and exported.

Sender update:
- `sim_output/send_hardware_sequence.py` now drains controller startup chatter
  and waits for a quiet window before sending the first command:
  `--startup-quiet-window` default `1.0 s`, `--max-startup-wait` default `8.0 s`.
  Increase these values if delayed startup/action-group feedback still appears.

### 2026-05-03 - Align Viewer Start and Hardware End

User decision:
- First make the simulation visualization match the observed physical run
  shape more closely instead of treating the physical Z-like startup pose as
  something to hide.
- The viewer should begin from the physical straight/upright posture, while
  preserving MuJoCo's internal geometry and IK convention.
- After book release, the hardware should also retreat from the shelf and then
  return upright/center-up, matching the viewer's final motion intent.

Implementation:
- Historical note: `sim/km1_trajectory_viewer.py` previously started playback
  from an observed physical Z-like posture by default:
  `[base, shoulder, elbow, wrist_pitch, wrist_roll] =
  [0.0, -67.5, 67.5, -87.75, 0.0] deg`.
- This start pose is converted from the observed raw PWM values
  `#000P1500 #001P2000 #002P2000 #003P0850 #004P1500`.
- Correction: the MuJoCo `shoulder_pitch` visual sign is opposite for this
  anchor. The first attempt used `+67.5 deg`, which drove the simulated arm into
  the floor; shoulder is now flipped to `-67.5 deg`.
- Follow-up correction: physical inspection indicated the elbow and wrist-pitch
  directions were also reversed for this startup anchor. The current viewer
  anchor was adjusted again after joint1/shoulder inspection.
- Correction of approach: do not derive this startup visualization anchor from
  raw PWM math until the hardware profile is calibrated. Use the observed
  geometry directly: lower link slants upward, middle link is nearly vertical,
  and the end link is horizontal.
- Current viewer startup anchor is the MuJoCo internal center-up pose
  `[0.0, -90.0, 0.0, 0.0, 0.0] deg`, matching the physical straight/upright
  start convention without changing the MuJoCo XML geometry.
- Use `--start-from-model-default` only for diagnostics if the XML default pose
  is needed.
- `sim_output/export_command_sequence.py` now appends the documented raw PWM
  startup-straight/home pose by default after the exported pick/place sequence:
  `{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}`.
- Use `--no-append-home` only for diagnostics when the final home command should
  be suppressed.

Current caution:
- The appended home command is raw PWM and avoids the `G0001` action-group
  prefix. Do not derive this final hardware pose from a MuJoCo visual center-up
  angle; use `HARDWARE_POSE_NOTES.md` or a newly measured hardware pose table.

### 2026-05-03 - joint1 IK Limit from Measured Hardware Range

Source of truth:
- `HARDWARE_POSE_NOTES.md` records `joint1 / servo001` as physically
  structure-limited:
  - forward limit approximately PWM `550`
  - backward limit approximately PWM `2400`
  - PWM increases from forward toward backward

User angle convention:
- Real servo angle `150 deg` is treated as software/IK `0 deg`.
- Therefore PWM/angle values are interpreted relative to `150 deg`.
- The notes record approximately PWM `550..2400`; the practical IK working
  range is set to physical `60..240 deg` for a symmetric range around `150 deg`.
- `60 deg -> -90 deg` software angle.
- `240 deg -> +90 deg` software angle.

Implementation:
- `主程序代码/config.py` now sets joint1/servo001 IK limits to
  `(-90.0, 90.0) deg`.
- Other IK joints are not forced to joint1's measured range. They keep their
  previous ranges unless a side exceeded `100 deg`; exceeded sides are capped to
  `+/-100 deg` for conservative autonomous motion. Current IK limits are:
  `joint0=(-100,100)`, `joint1=(-90,90)`, `joint2=(-100,100)`,
  `joint3=(-100,100)`.
- `sim_output/ik_helper.py` now treats `IK_JOINT_LIMITS_DEG` as hard candidate
  filters, not only as optional cost terms. With current zero cost weights, this
  preserves candidate ranking behavior while rejecting physically out-of-range
  joint solutions.

### 2026-05-03 - Explicit Software Angle to Hardware Servo Mapping

User clarification:
- For joint1 through joint4, software/MuJoCo/IK `0 deg` should correspond to
  the physical servo's default `150 deg` pose.
- In serial commands this means software `0 deg` maps to `P1500`.

Implementation:
- `sim/vendor_km1_kinematics.py` now maps software-relative joint angles using:
  `PWM = 1500 + sign * software_deg * (1000/135)`.
- This uses the confirmed vendor servo protocol range where `P500..P2500`
  spans `270 deg`, so `P1500` is centered/default and represents software
  `0 deg`.
- The new mapping is consistent with the measured `joint1 / servo001` range and
  the current practical IK limit:
  `PWM 600..2400` -> physical `60..240 deg` -> software `-90..+90 deg`.
- Correction: the earlier `#001P0600` final center-up command was an invalid
  inference from the MuJoCo visual pose. It drives joint1 toward the ground on
  the real arm and must not be used as the hardware straight/home pose.

Caution:
- Joint signs are still profile-dependent and must be calibrated per joint.
- This change makes the neutral offset explicit, but it does not by itself prove
  all joint directions match the physical arm.

### 2026-05-03 - Meaning of "Joint Reversed" in Hardware Mapping

Important convention:
- When user says a joint is "reversed", that means the software/MuJoCo/IK joint
  angle should use the opposite sign.
- Hardware command values must still be mirrored around the physical neutral
  `150 deg` / `P1500`, not around physical `0 deg`.

Correct mapping:
- Normal direction: `PWM = 1500 + software_deg * (1000/135)`.
- Reversed direction: `PWM = 1500 - software_deg * (1000/135)`.

Example:
- Software `+30 deg` normal -> `P1722`.
- Software `+30 deg` reversed -> `P1278`.
- Therefore the "opposite" hardware command is symmetric around `P1500`.

Code status:
- `sim/vendor_km1_kinematics.py:pwm_from_angle()` already implements this as
  `PWM = 1500 + sign * software_deg * (1000/135)`.
- To reverse a joint in command generation, change that joint's `sign`, not the
  neutral offset and not the physical zero reference.

### 2026-05-03 - joint1/joint2/joint3 Hardware Direction Correction

User hardware observation:
- Initial testing suggested joint2 and joint3 might both be reversed. A later
  one-joint-at-a-time raw-ASCII calibration refined this. The following tested
  commands used the old `10 PWM/deg` probe spacing, so keep them as direction
  evidence only:
  - `#001P1800` for MuJoCo joint1 `+30 deg` moved joint1 negative, so `#001`
    must be inverted.
  - `#002P1200` for MuJoCo joint2 `+30 deg` moved joint2 negative, so `#002`
    must not be inverted.
  - `#003P1200` for MuJoCo joint3 `+30 deg` matched MuJoCo positive, so `#003`
    remains inverted.
- The correction must use the `150 deg` / `P1500` neutral as the mirror point,
  not physical `0 deg`.

Implementation:
- `measured_grasp` now uses inverted hardware command generation for `#001`
  and `#003`; `#002` uses the normal sign.
- The command mapping remains:
  `PWM = 1500 + sign * software_deg * (1000/135)`.
- Therefore reversing a joint changes its sign and mirrors its PWM
  targets around `P1500`.

Example:
- Calibrated software joint1 `+30 deg -> #001P1278`.
- Software joint2 `+30 deg -> #002P1722`.
- Software joint3 `+30 deg -> #003P1278`.

### 2026-05-03 - joint0 / base_yaw Direction Correction

User hardware observation:
- A MuJoCo pose with `base_yaw = +0.504 rad` was first converted to
  `#000P1286`.
- The physical result was mirrored relative to MuJoCo.
- Matching MuJoCo required `#000P1714`.

Correction:
- `joint0 / servo000` is normal direction in the current software convention:
```text
base_yaw positive -> PWM above P1500
base_yaw +30 deg  -> #000P1722
```
- Do not invert `#000` in command generation.

Implementation:
- `sim/vendor_km1_kinematics.py` now maps `servo_angles[0]` with sign `+1`.
- Synced the same change into
  `Integrated Algorithm/sim/vendor_km1_kinematics.py`.

### 2026-05-03 - Joint1 Zero Convention Layering Correction

User calibration requirement:
- Physical joint1 upright/default pose is the servo default angle, physical
  `150 deg`, command `P1500`.
- Therefore human-facing calibrated joint1 zero and hardware PWM conversion
  should treat upright/default as `0 deg` / `P1500`.

Implementation:
- Do not change `sim/km1_arm.xml` geometry or MuJoCo numeric IK coordinates to
  force raw MuJoCo joint1 zero to be upright. A direct XML geometry change was
  tried and caused severe viewer trajectory errors: multiple waypoint
  collisions/penetrations and failure to keep the end link horizontal.
- Keep MuJoCo's internal center-up/vertical value as shoulder `-90 deg`.
- Apply the joint1 zero/upright convention only at the reporting and
  hardware-PWM conversion layers.
- Current code implementation: `sim/vendor_km1_kinematics.py` applies
  `calibrated_joint1 = internal_joint1 + 90 deg` immediately before converting
  joint1 to PWM. This makes internal `-90 deg` map to hardware `P1500`.

### 2026-05-03 - PWM Sequence Chain Updated After Calibration

Problem found:
- The old final hardware "center-up" command was incorrectly inferred from the
  MuJoCo visual pose and included `#001P0600`, which drove joint1 toward the
  ground on the real arm.
- The old direction assumption for the generated PWM chain did not match
  one-joint raw-ASCII hardware tests.
- A later attempt to fix joint1 zero by changing MuJoCo XML geometry broke the
  existing IK/trajectory behavior. That attempt was reverted. MuJoCo internal
  geometry should remain stable; only conversion/reporting layers should carry
  the joint1 zero offset.

Applied update:
- `sim/vendor_km1_kinematics.py` now maps `#000` normal, `#001` inverted,
  `#002` normal, and `#003` inverted around the neutral `P1500`.
- `#001` also applies the joint1 calibration offset before PWM conversion:
  `calibrated_joint1 = internal_joint1 + 90 deg`.
- User confirmed the servo command range is `P500..P2500` over `270 deg`.
  With `P1500` as the zero/default command, this means `P500..P2500` maps to
  `-135..+135 deg`, so conversion now uses `1000/135 = 7.4074 PWM/deg`.
- User then tested the corrected `#000/base_yaw` sign and confirmed that the
  latest hardware motion is basically consistent with MuJoCo. Positive MuJoCo
  base yaw must increase PWM; the first pick approach uses `#000P1714`, not the
  old mirrored `#000P1047/#000P1286` style command.
- Latest trajectory adjustment: the grasp point is raised from `z=100 mm` to
  `z=115 mm`, and the pick-approach point directly above it is now `z=215 mm`.
- After grasping, the transport height is `175 mm` through lift, shelf push,
  and retreat. The actual place step still lowers to the placement height.
- The shelf-turn transition is base-only. MuJoCo changes only joint0/base_yaw,
  and the hardware sequence sends only `{#000P2243T2500!}` so joint1-joint5 are
  not re-commanded during that turn.
- `sim_output/hardware_command_sequence.txt` was regenerated and synced into
  `Integrated Algorithm/sim_output/hardware_command_sequence.txt`.
- The full waypoint/angle/command chain is documented in
  `sim_output/MOTION_CHAIN.md`.
- The current run command should use raw ASCII sequence sending, no `G0001`,
  no appended `@GroupDone!`.
- Use a conservative delay while testing, e.g. `--fixed-step-delay 2.5`.

Current regenerated sequence:
```text
{#000P1714T1500!#001P1342T1500!#002P1964T1500!#003P1472T1500!#004P1500T1500!}
{#000P1714T1500!#001P1209T1500!#002P2232T1500!#003P1840T1500!#004P1500T1500!}
{#005P1700T1000!}
{#000P1714T1500!#001P1323T1500!#002P2134T1500!#003P1661T1500!#004P1500T1500!}
{#000P2243T2500!}
{#000P2231T1500!#001P1267T1500!#002P2046T1500!#003P1629T1500!#004P1500T1500!}
{#000P2231T1500!#001P1193T1500!#002P2136T1500!#003P1760T1500!#004P1500T1500!}
{#005P1400T1000!}
{#000P2243T1500!#001P1418T1500!#002P2267T1500!#003P1698T1500!#004P1500T1500!}
{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}
```

### 2026-05-03 - SSCOM-Style Raw ASCII Console Test Passed

User hardware result:
- User tested with the new terminal-style serial console and confirmed that
  raw ASCII commands work.
- The arm successfully executed direct raw PWM commands in the same style as
  the vendor SSCOM serial assistant.

Successful direct command style:
```text
{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}
```

Important correction:
- The correct direct-control path is plain ASCII `{#...}` commands.
- Do not append `@GroupDone!` to commands sent by our tools; `@GroupDone!` is
  controller feedback for action/group completion.
- Do not use `{G0001#...}` as a generic wrapper for direct PWM control.
  `G0001` is action-group-related and can confuse testing.

Vendor tool configuration evidence:
- `项目资源（厂商）/5.软件工具/5.串口助手/sscom51.ini` shows SSCOM uses:
  - baud `115200`
  - send format `ASC`
  - receive display not HEX
  - DTR enabled, RTS disabled in the Windows tool
  - terminal send does not automatically append a newline
- The local helper `tools/km1_serial_console.py` was adjusted to match this
  behavior more closely: default line ending is now `none`.

Observed non-blocking board message:
```text
LTR381 I2C错误3
```
- This is firmware output from the LTR381 I2C sensor initialization/write path.
- It does not indicate serial command failure and did not prevent servo motion.
- Treat it as a sensor/peripheral warning unless the project later needs the
  LTR381 sensor.

Current practical rule:
- For hardware pose tests and ROS2 bridge smoke tests, send one complete ASCII
  command line at a time using raw `{#...}` strings.
- Wait according to the largest `Txxxx` duration plus a settle margin.
- Only require `@GroupDone!` for saved action-group commands where that feedback
  is actually expected.

### 2026-05-03 - joint2 PWM Scale Correction

New user hardware finding:
- In reality, `joint2 / servo002` at `P1500` makes `link1` and `link2`
  completely straight/flat.
- This matches MuJoCo `joint2 = 0`.
- Sending `#002P2400T2000!` makes the physical joint rotate much more than
  `90 deg`.
- Sending `#002P2100T2000!` makes the physical joint close to a `90 deg` bend.

Important correction:
- The earlier explicit mapping `PWM = hardware_deg * 10`, with software zero
  at `P1500`, is not valid as a global joint-angle mapping.
- The later confirmed protocol scale supersedes the rough local estimate:
  `P500..P2500` spans `270 deg`, so `P1500` maps to `0 deg` and
  `1000/135 = 7.4074 PWM/deg`.
- The old rough joint2 observation was:
```text
P1500 -> 0 deg relative
P2100 -> about +90 deg relative
scale -> about 600 PWM / 90 deg = 6.7 PWM/deg
```
- Keep that as historical evidence that `10 PWM/deg` was wrong, not as the
  current exporter scale.

Action for future code:
- Do not keep a single global `10 PWM/deg` conversion for all joints.
- Move toward per-joint calibration:
  - neutral PWM,
  - sign,
  - PWM-per-degree slope,
  - min/max PWM,
  - known angle check points.
- Update command generation only after at least `joint1-joint3` have similar
  `P1500`, `P~90deg`, and end-stop observations.

### 2026-05-03 - Pure Base-Turn Diagnostic Before `place_transfer`

User hardware test:
- After grasp and `pick_lift`, user tested a pure base-turn waypoint that
  changed only `joint0 / servo000` toward the shelf direction while holding
  joint1-joint4 at the `pick_lift` PWM values.
- Result: the arm did not visibly shake or drop during the pure `joint0` turn.
- The visible height variation/drop appears when running the full
  `place_transfer` command.

Implication:
- Current `place_transfer` is not just a base rotation. It moves from
  `pick_lift = (218.0, 120.23, 150.0)` to
  `place_transfer = (-40.0, 220.0, 150.0)`, so the IK changes shoulder,
  elbow, and wrist as well as base yaw.
- Since pure base rotation is stable, the leading cause of the observed
  ~15 mm height change is the planned posture transition / joint-space
  interpolation between waypoints, not immediately joint1 torque weakness.
- Next improvement should separate the motion into:
  1. lift,
  2. pure base turn with the arm posture frozen,
  3. shelf-side reach/posture adjustment,
  4. lower/place.

### 2026-05-06 - Two-Layer Shelf Clearance and 45 mm Post-Grasp Lift

Current MuJoCo shelf visual:
- Lower shelf board top is `40 mm` above ground.
- Shelf board thickness is `10 mm`.
- Next shelf board top is `280 mm`, giving `240 mm` layer spacing between
  board tops.
- This geometry is visual/passive in MuJoCo and is meant to match the
  two-layer shelf mock-up better than the earlier single-board scene.

Current target-sequence policy:
- `主程序代码/target_sequence.py` now uses `POST_GRASP_LIFT_MM = 45.0`.
- This lowered the previous post-grasp transport height by `15 mm` to reduce
  the risk of the held book touching the second shelf during transfer.
- For the clean axis-aligned test input
  `pick=(220, 0, 115)` and `place=(0, 260, 124.25)`, the generated lift and
  transfer height is now `160 mm` instead of `175 mm`.
- The default/external pick and place target semantics did not change: the
  caller still provides only the book-spine grasp point and the final shelf
  placement point. Intermediate points remain generated by the generic policy.

### 2026-05-06 - Held-Book Retract Before Base-Only Shelf Turn

Current target-sequence policy:
- After `pick_lift`, the generated chain now inserts `transport_retract`.
- `transport_retract` keeps the held book at the same transport Z and moves XY
  `70 mm` toward the arm origin `(0, 0)`.
- If the pick point is already closer than `70 mm` to the origin, the retract is
  clamped so the waypoint does not cross the origin.
- For the clean axis-aligned test `pick=(220, 0, 115)` and
  `place=(0, 260, 124.25)`, this creates
  `transport_retract=(150, 0, 160)`.
- The following `place_transfer_base_only` still sends only the base/yaw servo,
  but now inherits the non-base joint posture from `transport_retract`.

Reason:
- Carrying the book closer to the base before rotating should reduce yaw and
  shoulder torque and make the shelf turn less shaky.
- This remains a generic rule derived from the input pick point; it is not a
  hardcoded special coordinate.

### 2026-05-07 - Target Viewer CLI

New MuJoCo debug command:
```bash
python3 主程序代码/main.py \
  --target-viewer \
  --pick 220.0 0.0 115.0 \
  --place 0.0 260.0 124.25
```

Behavior:
- Generates `sim_output/control_trajectory.csv` from the current
  target-sequence waypoint policy.
- Opens `sim/km1_trajectory_viewer.py` for step-by-step inspection.
- Does not generate or send hardware PWM commands.

Use this when the goal is "command + grasp point + place point" visualization.
Use `--run-target-sequence` when the goal is hardware ASCII generation/sending.
