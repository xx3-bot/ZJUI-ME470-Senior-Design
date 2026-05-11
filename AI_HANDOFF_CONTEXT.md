# AI Handoff Context - ME470 Book Reshelving Project

Last updated: 2026-05-11 (Asia/Shanghai)

## 1. Project Overview

This is an ME470 robotic arm project for **autonomous book reshelving**.

Primary goal of the software framework:
- Serve as the central **decision + integration framework**.
- Coordinate perception, motion, and task planning.
- Execute a full loop: scan return bin -> create tasks -> pick book -> find shelf zone gap -> place book -> repeat.

Team context from user:
- User is focused on **robot hardware + ROS2** integration side.
- Current ROS2 progress has moved past zero as of 2026-04-30: user has confirmed PWM command sending works on the physical arm, and serial monitoring receives ESP32/controller feedback such as command echoes and `@GroupDone!`.

## 2. Current Status and Confirmed Direction

### 2026-05-11 grip/place test mode v1

Current-stage integration has a minimal `Grip and place test` mode for checking
the simplest useful chain before full Auto is ready.

Entry points:
- Menu option `6. Grip and place test`
- CLI:
  `python3 主程序代码/main.py --grip-place-test --dry-run --wait-trigger none`

Behavior:
- Captures/logs only the `-90 deg` reference view and the `0 deg` bin/OCR view.
- Does not run the `+90 deg` view.
- Does not interpret ABCD shelf sections.
- Logs OCR results if available, but does not use OCR pick coordinates for
  motion yet.
- Generates a fresh `target_sequence` with fixed v1 coordinates:
  - `pick = (220, 0, 115)`
  - `left place = (-25, 250, 124.25)`
  - `center place = (0, 250, 124.25)`
  - `right place = (25, 250, 124.25)`
- Writes outputs under `sim_output/grip_place_test/<timestamp>/`, including
  `left.png`, `center.png`, `grip_place_test_snapshot.json`,
  `grip_place_test_report.md`, `control_trajectory.csv`,
  `hardware_command_sequence.txt`, and `TARGET_SEQUENCE_SUMMARY.md`.

Verification on 2026-05-11:
- `main.py` and `grip_place_test.py` compile.
- Dry-run checks for `left`, `center`, and `right` slots all generated valid
  target sequences.
- Codex-side camera capture still fails due to macOS camera permissions, so
  the snapshot reports `partial`; this is expected in Codex and should be
  re-tested from the user's Terminal where camera access is granted.

### 2026-05-11 post-grasp extract-and-lift update

The target-sequence post-grasp motion has changed from pure vertical lifting to
extracting the book while lifting.

Current target-sequence policy:
- `pick_lift` now means post-grasp extract-and-lift.
- The generator retracts XY toward the arm origin by up to `50 mm`, but never
  below `170 mm` horizontal radius.
- The generator lifts to `pick.z + 65 mm`.
- For the clean test pick `pick=(220, 0, 115)`, this produces
  `pick_lift=(170, 0, 180)`.
- If the resulting `pick_lift` radius is still greater than `240 mm`, the older
  extra `transport_retract` step can still be inserted; otherwise the sequence
  goes directly from `pick_lift` to the shelf-side base-only transfer.

Verification on 2026-05-11:
- A temporary feasibility check for `place=(-25,250,124.25)`,
  `(0,250,124.25)`, and `(25,250,124.25)` passed MuJoCo IK.
- The formal command
  `python3 主程序代码/main.py --run-target-sequence --dry-run --wait-trigger none --pick 220 0 115 --place 0 250 124.25`
  generated `pick_lift=(170,0,180)` and 10 PWM commands.
- `--grip-place-test` dry-runs for left and right fixed slots also passed IK;
  camera capture remained partial in Codex due to macOS camera permission.

### 2026-05-01 control/planning boundary for agents

Do not misclassify the current MuJoCo pick/place demo as a vision planner or
global placement optimizer. The agreed module boundary is:

- Vision/decision/planning modules are responsible for detecting the book,
  choosing the shelf/gap, and providing task target points such as the book
  grasp point and the shelf placement point.
- The control/MuJoCo demo module is responsible for receiving those target
  points, deriving generic intermediate motion waypoints, checking reachability
  through IK, and executing/visualizing a normal `grip & place` sequence.
- It is acceptable that today's default target points are hardcoded or passed
  through CLI flags. They are stand-ins for future vision/decision outputs, not
  the core control algorithm.
- The reusable control policy is the waypoint rule sequence:
  `pick_approach -> pick -> CLOSE -> pick_lift -> transport_retract ->
  place_transfer -> place_approach -> place_final -> OPEN -> place_retreat`.
- Do not move book/gap optimization logic into `controller.py`. Future work
  should replace the coordinate provider while preserving the `PickPlacePlan`
  contract.
- A lightweight IK candidate cost structure now exists for future joint-posture
  tuning, but all cost weights are currently `0.0`, so it does not change the
  present demo behavior. Tune `IK_COST_WEIGHTS` in `主程序代码/config.py` later if
  the arm should avoid specific large joint angles or near-limit poses.
- Definition-level hardware commands are present in the simulation backend logs:
  `move_to` records contain vendor-format commands for servos `#000-#003`, and
  `gripper_command` records now map `OPEN -> {#005P1400T1000!}` and
  `CLOSE -> {#005P1700T1000!}`. A future ROS2 bridge can consume these command
  strings or regenerate them from the same IK/config values.
- Hardware angle mapping convention: software/MuJoCo/IK `0 deg` maps to the
  physical servo neutral `150 deg` / `P1500`. If a joint is "reversed", flip the
  software sign; the hardware command then mirrors around `P1500`, not around
  physical `0 deg`.
- MuJoCo joint1 zero convention was corrected on 2026-05-03: physical joint1
  upright/default equals software/MuJoCo-facing `0 deg` and servo `P1500`.
  This must be handled only at the human-facing output / hardware conversion
  layer. Do not change the MuJoCo XML geometry or numeric IK coordinates to
  enforce this convention; the raw MuJoCo model still uses its internal
  shoulder angle convention.

### 2026-05-07 decision/vision shelf-slicing next step

User wants the earlier "slicing" idea preserved as a future decision-system
direction. This is a joint task for the decision teammate and the vision
teammate, not a control-chain rewrite.

The intended architecture:
- Vision should convert shelf perception into local, structured shelf slices:
  zone -> shelf layer -> gap -> candidate local windows / support regions.
- Decision should score these slices and derive placement opportunities from
  them.
- Control should continue receiving target points or a `PickPlacePlan`-shaped
  output and should not own shelf segmentation, gap optimization, or slice
  generation.

Current teammate decision code already implements a lightweight version of this
idea by splitting each `ShelfGap` into three fixed opportunities:
`lean_left`, `center`, and `lean_right`. This is useful and should be kept, but
it is not the complete slicing feature yet.

The fuller slicing feature should allow larger gaps or partially occupied shelf
regions to produce multiple candidate windows, for example:
```text
gap width = 120 mm
book thickness = 20 mm
candidate slices at start_x, start_x + step, ..., right_limit
each slice carries width, support side, clearance, confidence, occupancy risk,
and whether placement would require squeezing or disturbing existing books
```

Recommended division of work:
- Vision teammate:
  - estimate shelf boundaries, book-edge positions, occupied intervals, open
    intervals, support-side labels (`book`, `side_panel`, `open`, `unknown`),
    and confidence for each local slice;
  - output camera-relative slice/gap data through `perception_adapter.py`.
- Decision teammate:
  - extend `PlacementOpportunityPlanner` from fixed left/center/right choices
    to scoring multiple slice-derived opportunities;
  - keep the output explainable with candidate scores, rejection reasons, and
    selected placement rationale;
  - map the selected slice/opportunity to a final shelf placement point.
- Control/hardware side:
  - keep the existing waypoint execution policy, IK checks, MuJoCo viewer,
    PWM/serial command generation, and ROS2 motion adapter boundary intact.

Acceptance target for this feature:
- A mock shelf with several occupied/open intervals can produce multiple
  slices.
- Logs show why one slice/opportunity was chosen over the others.
- If all slices are too tight or risky, the task becomes `BLOCKED` with a clear
  reason instead of falling through to unsafe placement.
- The selected result can still feed the existing control path without changing
  the hardware-driving code.

### 2026-05-08 shelf-level simulation boundary

Do not treat the second/upper shelf layer in the mock decision data as the main
hardware simulation target. Upper/second-level shelf observations such as
`B_left` / `B_right` are currently test data for scanning, task routing, and
decision robustness. They are useful for software checks, but they are not the
primary physical demo path.

Current main motion/hardware validation path should remain the lower-shelf
fixed pick/place flow through the verified target-sequence / command-file path:
```text
python3 主程序代码/main.py --sim-mode
python3 sim_output/send_hardware_sequence.py --commands sim_output/hardware_command_sequence.txt --dry-run
python3 sim_output/send_hardware_sequence.py --commands sim_output/hardware_command_sequence.txt --port /dev/ttyUSB0 --baud 115200 --fixed-step-delay 2.5
```

The full mock controller run without `--sim-mode` may create tasks for upper
test zones and may attempt unreachable or non-demo targets. Use it to validate
decision logging and software branching only. Do not use its second-layer mock
targets as evidence that the physical arm should execute upper-shelf placement.

Important correction: do not add a direct `motion_adapter -> per-pose hardware
IK` bridge for this demo path. The verified hardware path is the generated raw
ASCII command sequence, especially `sim_output/hardware_command_sequence.txt`,
and the target-sequence pipeline in `主程序代码/target_sequence.py`. The vendor
analytical IK helper in `sim_output/ik_helper.py` is useful for reachability
checks and logs, but it must not silently replace the calibrated
target-sequence/MuJoCo-angle-to-PWM chain.

Formal runtime should generate the trajectory from the current pick/place
targets for that run. Historical CSV trajectories and IK probe grids are
offline simulation artifacts only; in `Integrated Algorithm` they are kept under
`sim/examples/` and `sim/diagnostics/`, not in the top-level runtime path. They
must never be used as implicit inputs to hardware execution.

`Integrated Algorithm/RUN_MODES.md` now documents the hard separation:
`--run-target-sequence` is the formal hardware-generation path, while
`--sim-mode`, `--viewer`, and `--target-viewer` are simulation/debug paths only.
`main.py` rejects mixed hardware/simulation flags instead of guessing.
When `main.py` is run with no CLI arguments, it opens an interactive terminal
menu with modes 1-5 for hardware send, hardware dry-run, sim mode, target
viewer, and startup scan. Pressing Enter at the menu defaults to dry-run; pressing Enter at
parameter prompts keeps the current default values.
The legacy 11-hyperparameter controller prompt also accepts blank input now and
loads `config.DEFAULT_RUNTIME_PARAMS`, so the outer menu and the older
controller setup layer share the same default behavior.

Startup scan v1 is implemented as an independent workflow, not full Auto:
`--startup-scan` sends base-only `-90 / 0 / +90` scan commands, captures
`left.png`, `center.png`, and `right.png`, returns home/straight, and writes
`sim_output/startup_scan/<timestamp>/startup_scan_snapshot.json`. Shelf section
interpretation is preserved as `pending_or_partial` until the vision/planning
handoff for A/B/C/D is completed.

Target-sequence transport retract update: `transport_retract` is now conditional
instead of always inserted. If the pick point horizontal radius is `<= 240 mm`,
the generator keeps the post-grasp `pick_lift` pose as the transport start and
does not add a duplicate/retracted waypoint. If the radius is `> 240 mm`, it
retracts toward the origin but clamps the resulting radius to at least `170 mm`.
This avoids creating near-base points such as `[148, 0, 160]` for
`pick = (218, 0, 115)`, which failed the MuJoCo horizontal-end-link IK check.

Standard Auto flow design is documented in
`Integrated Algorithm/AUTO_STANDARD_FLOW.md`. This is a design/team-alignment
document only; the full Auto flow is not implemented yet.

### Confirmed strategy
Do **not** rewrite the whole system.
Keep high-level logic and replace adapters first.

- Keep mostly unchanged:
  - `controller.py`
  - `decision/task_planner.py`
  - `world_model.py`
- Integrate via adapter layers:
  - `motion_adapter.py` (highest priority)
  - `perception_adapter.py` (later)
- Minor future updates:
  - `config.py` / `main.py` for ROS2 parameterization (replace terminal input when ready).

### Immediate priority (critical)
Before full integration, first prove MVP:
1. ROS2 can command arm motion.
2. Motion completion status can be observed reliably.
3. A minimal `move_to(...) -> bool` returns true only on actual completion.

### Practical recommendation already agreed
Use vendor original software/driver as baseline first:
1. Run vendor sample successfully.
2. Verify communication + enable + motion + stop.
3. Replicate same behavior with a ROS2 minimal node.
4. Then connect to this framework via `motion_adapter.py`.

## 3. Main Codebase Architecture (Read from `/Users/xinruixiong/Desktop/ME470/主程序代码`)

### 3.1 Entry and control core
- `main.py`
  - Entry point.
  - Calls `RobotControlSystem().run()`.

- `controller.py`
  - Main state-machine orchestrator.
  - Runtime flow:
    1. Load 11 hyperparameters.
    2. Global bin scan.
    3. Create pending tasks from recognized titles.
    4. Select next task.
    5. Localize target book.
    6. Pick book.
    7. Return to pick-ready pose.
    8. Scan shelf vertically and find target zone.
    9. Choose gap and place book.
    10. Tilt check interaction.
    11. Mark task done and return home.
    12. Loop until all tasks complete.

### 3.2 Configuration
- `config.py`
  - Stores runtime hyperparameters and constants.
  - Parses 11 user-input parameters:
    - `ARM_LENGTH`
    - `SCAN_ARC`
    - `OFFSET_X`
    - `OFFSET_Y`
    - `GRIP_ORIENTATION`
    - `TIP_GAP`
    - `TIP_DEPTH`
    - `SAMPLE_RATE_MS`
    - `BOOK_VERT_HEIGHT`
    - `SHELF_H_MIN`
    - `SHELF_H_MAX`
  - Computes `INITIAL_GRIP_POS` based on offsets + orientation.

### 3.3 Shared models
- `models.py`: `Pose`, `BookObservation`, `ShelfGap`, `ShelfObservation`, `BookCatalogEntry`, `Task`.

### 3.4 Coordinate transforms
- `coordinate_transformer.py`
  - `get_camera_pose(gripper_pose)`
  - `camera_to_world(camera_pose, rel_x, rel_y, rel_z)`
  - `calculate_arc_points(...)`
  - `calculate_vertical_scan_points(...)`

### 3.5 Planning and database mock
- `decision/db_manager.py`
  - In-memory catalog + task list.
  - Maps title -> zone + thickness.
  - Creates/marks tasks.

- `decision/task_planner.py`
  - Chooses next pending task.
  - Computes pick pose from observation.
  - Chooses feasible shelf gap.
  - Computes approach/final place poses.

### 3.6 World model
- `world_model.py`
  - Maintains latest observed books and shelves.
  - Tracks zone placement base (`zone_slot_bases`).

### 3.7 Adapter layer (integration seam)
- `motion_adapter.py`
  - Current behavior: forwards to mock interface.
  - Contract:
    - `move_to(current_pose, target_pose) -> bool`
    - `gripper_command(command) -> bool`

- `perception_adapter.py`
  - Current behavior: forwards to mock interface.
  - Contract:
    - `scan_bin_books(camera_pose) -> list[dict]`
    - `locate_book(title, camera_pose) -> dict | None`
    - `scan_shelves(camera_pose) -> list[dict]`

### 3.8 Mock backend
- `interfaces.py`
  - Mock vision and mock motion/gripper execution.

### 3.9 Interface spec document
- `CONTROL_INTERFACE_SPEC.md`
  - Team-facing contract.
  - Key rules:
    - Units: mm
    - Perception outputs are camera-relative coordinates.
    - Control converts to world frame.
    - Motion receives world-frame gripper poses.

## 4. Vendor Resources: What Is Provided

Read target directory: `/Users/xinruixiong/Desktop/ME470/项目资源（厂商）`

High-level inventory (approx):
- ~430 files total
- ~268 text-like files (`py/c/h/ino/txt/ini/htm/mix/...`)
- ~162 binary-like files (`pdf/exe/mp4/zip/step/tflite/...`)

### 4.1 Tutorials / manuals / command reference
- `1.教程手册/视觉指令表.docx` (text extracted)
  - Contains visual mode command strings:
    - `#StartLed!`
    - `#StopLed!`
    - `#RunStop!`
    - `#ColorSort!`
    - `#ColorStack!`
    - `#FaceTrack!`
    - `#ColorTrack!`
    - `#ApriltagSort!`
    - `#ApriltagStack!`
    - `#ApriltagNumSort!`

### 4.2 OpenMV vision source code
- Main package:
  - `4.源代码程序/KM1机械臂Openmv视觉模块代码 V3.1/*.py`
- Includes task modules:
  - `colorSort.py`, `colorPalletizer.py`, `colorTrace.py`
  - `apriltagSort.py`, `apriltagPalletizer.py`, `apriltagNumSort.py`
  - `faceTrack.py`, `kinematics.py`, `main.py`
- Communication characteristics observed:
  - Uses `UART(3,115200)`
  - Sends/receives ASCII command strings
  - Sends servo command format like `{#000P1500T1000!...}`

### 4.3 STM32 factory controller source (critical for protocol)
- Path (large project):
  - `6.拓展资料/.../STM32程序代码 V1.0 (3)/...`
- Key files reviewed:
  - `User/main.c`
  - `User/app_uart.c`
  - `User/Components/y_usart/y_usart.c`
  - `User/Components/y_global/y_global.c`
- Protocol mode parser (from `uart_data_parse`):
  - `$...!` -> command mode
  - `#...!` -> single-servo command
  - `{...}` -> multi-servo command
  - `<...>` -> action-group save mode
- Commands found in parsing logic:
  - `$DST!` (stop all)
  - `$DST:<index>!` (stop one)
  - `$DGS:<group>!`
  - `$DGT:start-end,count!`
  - `$GETA!`
  - `$SMODE...!`
  - `$KMS:x,y,z,time!` (kinematics move)
  - `$BEEP!`

### 4.4 Arduino / ESP32 / glove / teaching examples
- `4.源代码程序/同步示教器代码/*` (`.ino`)
- `4.源代码程序/仿生手套代码/*` (`.ino`)
- `*.mix` files (Mixly XML projects, readable as text)
- Provide practical serial command examples and PWM action sequence examples.

### 4.5 Host tools and configs
- Windows tools and support:
  - CH340 driver installer
  - Vendor host app (`Yeahbot V2.0.5.exe`)
  - serial assistant (`sscom5.13.1.exe` + `sscom51.ini` presets)
  - OpenMV IDE installer
- `.ini` files include action groups and servo trajectories (PWM/time tables).

### 4.6 Additional assets
- Video tutorials (`mp4`), CAD (`STEP`), PDFs, model files (`.tflite`), zip bundles.
- Useful for onboarding and validation, but not directly consumed by ROS2 code.

## 5. Known Protocol / Integration Signals Already Extracted

Practical signals useful for ROS2 bridge design:
1. Frequent baud rate: `115200`.
2. ASCII command protocol with explicit delimiters (`!`, `}`, `>`).
3. Servo command examples:
   - `#005P1700T1000!`
   - `{#000P1500T1000!#001P1500T1000!}`
4. Stop command exists and should be part of safety path:
   - `$DST!` stops all servos' current motion through the high-level controller path.
   - `$DST:<index>!` stops one servo's current motion.
   - Controller internals forward these as `#255PDST!` or `#xxxPDST!`.
   - Important: this is motion stop/hold-at-current-tracked-position, not torque-off/unload.
5. Kinematics command support in firmware parser:
   - `$KMS:x,y,z,time!`.
6. Return/home command notes:
   - Current reliable return-to-pose path should use an explicit servo pose command, not an assumed hidden home command.
   - User-provided ROS2-format candidate/known pose command:
     - `{G0001#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}@GroupDone!`
   - Vendor action group 0 can be called with `$DGS:0!` if that action group has been stored on the controller.
   - STM32 source comments mention `$DJR!` as "all servo reset", but the reviewed parser did not show an implemented `$DJR!` branch; do not rely on `$DJR!` until hardware verifies it.

## 6. User Current Mission (Hardware + ROS2)

As of 2026-04-30 user state:
- Works on hardware and ROS2 integration.
- User has completed a basic ROS2 arm connection attempt.
- User confirmed that sending PWM commands is effective on the physical arm.
- User confirmed serial monitoring can receive ESP32/controller output from `/dev/ttyUSB0` at `115200`.
- Observed controller feedback includes grouped command echoes and `@GroupDone!`.
- Completion feedback / motion-done semantics are still not confirmed.
- IK profile constraint update: do not use `esp32_factory` as default for this project, because the current arm does not use the vendor original aluminum frame dimensions (only servos are reused).
- Primary simulation/control validation should use `measured_grasp` (or a future project-calibrated profile).

Primary near-term objective:
- For replay/control: record conservative known-good PWM poses, then use those poses to shape the first motion adapter / ROS2 motion layer.
- For true hand-guided teaching: do not treat PWM/group commands as sufficient, because they command and hold target positions.

New practical tool:
- `tools/km1_pwm_teach.py`
  - Standalone interactive PWM teaching helper.
  - Sends vendor-format multi-servo commands like `{#000P1500T0200!#001P1500T0200!...}`.
  - Records commanded PWM poses to CSV, default `teach_pwm_poses.csv`.
  - Has `$DST!` stop command on key `x`.
  - This is remote teaching / point recording, not true hand-guided teaching, because servo unload and read-current-position are still unverified.

### 2026-04-30 hardware pose and joint-range calibration
- New persistent hardware notes file:
  - `HARDWARE_POSE_NOTES.md`
- Startup straight pose was observed as:
  - `{G0001#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}`
  - Completion feedback observed separately as `@GroupDone!`.
- Earlier notes called the startup/reset command a "startup straight pose", but
  user later observed that the physical pose can appear skewed. Treat it only
  as an observed reset/serial-control test command, not as a calibrated
  geometric home pose.
- Default Z-shaped pose exists but its exact PWM command still needs to be captured.
- Confirmed first-pass physical PWM ranges and directions:
  - `joint0 / servo000`: base pan, right `500`, left `2500`.
  - `joint1 / servo001`: forward approximately `550`, backward `2400`; physically structure-limited.
  - `joint2 / servo002`: backward `500`, forward `2500`.
  - `joint3 / servo003`: backward `500`, forward `2500`.
  - `joint4 / servo004`: gripper wrist roll, left `500`, right `2500`.
  - `joint5 / servo005`: gripper, open `500`, closed `2500`.
- Practical implication:
  - We now have the first usable `servo id -> joint -> direction -> physical PWM range` table.
  - This is enough to start building a conservative PWM safety layer and to compare `measured_grasp` IK outputs against hardware limits.
  - It is not yet enough to send arbitrary IK paths safely; zero offsets, angle-to-PWM mapping, conservative margins, and repeatable pose tests still need validation.

### 2026-04-30 vendor-material check for true hand-guided teaching
- User clarified the desired teaching mode is:
  1. disable/unload all servos,
  2. manually move the physical arm,
  3. read current servo/joint positions,
  4. re-enable holding at the current pose and record it.
- The observed ROS2 command shape, e.g. `{G0001#000P1500T1500!...}@GroupDone!`, is a position/hold command path and cannot by itself unload the arm.
- Vendor manual says the KM1 uses bus servos and claims data feedback supports reading servo position angle, voltage, and temperature.
- The same manual says bus-servo details are in `总线舵机学习资料`, but that standalone file was not found in the current workspace.
- Reviewed factory ESP32/STM32 source shows the exposed high-level command parser handles PWM-like commands, `$DST!`, `$DST:x!`, action groups, and kinematics. No high-level torque-off/unload or read-current-position command was found.
- Important correction: `$DST!` / `#xxxPDST!` means stop current motion at the controller's internally tracked current PWM value. It is not evidence of servo torque-off/unload.
- ESP32 factory code uses Arduino `Servo` objects on GPIO pins and `writeMicroseconds()`. STM32 factory code uses TIM7 to synthesize PWM pulses. Those firmware paths do not expose physical encoder/position readback through the current high-level serial protocol.
- The original "同步示教器" code reads external potentiometers (`A0-A5`) and maps them to servo PWM commands. It is not hand-guided teaching by moving the robot arm itself.
- Next evidence gate for true teaching: obtain the missing `总线舵机学习资料` or identify/test the raw bus-servo protocol directly on the servo bus, specifically looking for unload/torque-enable and read-current-position commands.

### 2026-04-30 `6.拓展资料` follow-up
- `6.拓展资料/拓展场景/出厂源码` contains multiple useful source sets:
  - `滑轨抓取放下程序/ESP32`
  - `滑轨抓取放下程序/STM32`
  - `滑轨抓取放下程序/ard`
  - `前抓侧放机械臂程序`
- These are useful for:
  - confirming the same high-level ASCII command protocol,
  - borrowing known-good OpenMV serial command examples,
  - mining action-group PWM tables for safe return / pick / place seed poses.
- `前抓侧放机械臂程序/Openmv程序/kinematics.py` sends four-servo IK commands in the form `{#000P...T...!#001P...T...!#002P...T...!#003P...T...!}`.
- OpenMV task scripts use gripper commands such as old full-open
  `{#005P1000T1000!}` and close `{#005P1700T1000!}`. For this project's current
  physical demo, use the safer release command `{#005P1400T1000!}` so the
  gripper does not push into its mechanical end stop.
- Some OpenMV scripts call saved action groups such as `$DGT:1-5,1!`, `$ACTGO!`, `$ACT12!`, and `$ACTBACK!`; these are action sequencing hooks, not servo feedback/unload.
- `前抓侧放机械臂程序/动作组/config.ini` includes many vendor action-group PWM/time tables. This is a good source for conservative pose candidates, but each pose must still be verified on this project's modified physical structure.
- No additional torque-off/unload or read-current-position command was found in the reviewed `6.拓展资料` source sweep.

### 2026-05-03 ESP32 firmware / `G0001` interference finding
- User observed a repeated `G0001`-style command interrupting the first command in the intended motion flow.
- Vendor ESP32 Mixly projects were decoded for inspection:
  - `项目资源（厂商）/4.源代码程序/机械臂控制器出厂源码/ESP代码v1.1.mix`
  - `项目资源（厂商）/6.拓展资料/拓展场景/出厂源码/滑轨抓取放下程序/ESP32/ESP32程序/ESP代码.mix`
- The main factory candidate for the current arm is `ESP代码v1.1.mix`; the `6.拓展资料` ESP32 project is a scene/extension variant and should be treated as reference unless hardware behavior matches it exactly.
- Source evidence:
  - Firmware stores action groups in W25Q64 flash by group number.
  - `<G0001#...>` stores action group `1`; it is converted to `{G0001#...}` internally and saved at `group_num * ACTION_SIZE`.
  - `$DGS:1!` executes saved action group `1` once.
  - `$DGT:start-end,count!` executes action groups as a sequence and later emits `@GroupDone!`.
  - A persistent startup command `pre_cmd` exists in W25Q64-backed `eeprom_info`.
  - `setup_start()` and `setup_servo()` both parse `eeprom_info.pre_cmd` if it is valid, so a saved startup command can run at boot and may even be parsed twice in this firmware layout.
  - `save_action()` supports clearing startup command via angle-bracket storage mode: sending `<$!>` should clear `pre_cmd` and return `@CLEAR PRE_CMD OK!`.
- Practical diagnosis:
  - Before reflashing, test whether the board has a stored startup command by sending `<$!>`, then power-cycle and monitor whether `G0001` still appears.
  - If clearing `pre_cmd` removes the repeated `G0001`, firmware replacement is not required for this issue.
  - If `G0001` still appears, likely sources are another serial endpoint (Bluetooth/app/OpenMV/Serial1/Serial2), PS2/control logic, or a ROS2-side sender.
- Firmware modification option if needed:
  - In `ESP代码v1.1.mix` / generated Arduino code, remove or guard the startup `parse_cmd(eeprom_info.pre_cmd)` calls in `setup_start()` and `setup_servo()`.
  - For a ROS2-only firmware build, consider disabling `loop_Function()` and `PS2_controll()` in `loop()` so sensors/PS2 cannot inject action groups while ROS2 owns motion.
  - Keep `loop_uart()`, `loop_action()`, and `loop_servo()` unless intentionally replacing the serial protocol.

### 2026-05-03 SSCOM-style raw ASCII command path confirmed
- User tested a terminal-style serial console and confirmed that raw ASCII
  `{#...}` commands execute correctly on the physical arm.
- This matches the vendor SSCOM serial assistant configuration:
  - baud `115200`,
  - send mode `ASC`,
  - no HEX,
  - no automatic terminal newline append.
- Local helper:
  - `tools/km1_serial_console.py`
  - Default line ending changed to `none` to match SSCOM more closely.
- Correct direct-control format:
  - `{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}`
- Important direct-control rules:
  - Do not add `@GroupDone!` to transmitted commands.
  - Do not use `G0001` as a generic PWM wrapper.
  - Use plain ASCII `{#...}` for direct servo pose tests.
  - For raw PWM commands, command echo plus elapsed `Txxxx` timing is sufficient for first smoke tests; do not require `@GroupDone!` unless sending stored action-group commands.
- Observed board output `LTR381 I2C错误3` is a firmware-side LTR381 I2C sensor warning. It did not prevent servo motion and should not be treated as serial command failure.

Useful commands:
```bash
python3 tools/km1_pwm_teach.py --dry-run
python3 tools/km1_pwm_teach.py --port /dev/ttyUSB0 --baud 115200 --output teach_pwm_poses.csv
```

## 7. End-to-End Build Path (From ESP32 Data Cable to ROS2)

### Step A: physical and electrical baseline
1. Connect control board to PC via USB data cable.
2. Ensure actuator power is valid (do not rely on USB for loaded actuation).
3. Confirm board enumerates as serial device (`/dev/ttyUSB*` or `/dev/ttyACM*`).

### Step B: vendor software baseline
1. Install required driver/tooling (CH340 + vendor host app/serial assistant).
2. Run a known vendor action group.
3. Verify at least: move, stop, repeatability.

### Step C: raw protocol verification (no ROS2 yet)
1. Use serial tool at `115200 8N1`.
2. Send minimal safe commands (`$DST!`, a small single-servo move).
3. Validate observable response and behavior.

### Step D: ROS2 serial bridge MVP
1. Create or locate `km1_serial_driver` ROS2 node (single owner of serial port).
2. Implement:
   - send command
   - wait response / timeout
   - publish state/ack
3. Reproduce Step C commands via ROS2, verify parity with vendor tool.
4. Optional near-term bridge: wrap the command formatting/CSV output behavior from `tools/km1_pwm_teach.py` into a ROS2 service or action once the ROS2 package path is known.

### Step E: ROS2 motion API layer
1. Add higher-level ROS2 interfaces (service/action):
   - `MoveToPose`
   - `GripperCommand`
   - `Stop`
2. Completion rule: success only after ack/condition; timeout -> fail.

### Step F: connect to this project
1. Replace internals of `motion_adapter.py` to call ROS2 motion API.
2. Keep perception mock for first integration pass.
3. Run existing controller loop end-to-end (real motion + mock perception).

### Step G: perception and full-stack polish
1. Replace `perception_adapter.py` with ROS2 perception data path.
2. Move runtime params to ROS2 params/launch.
3. Add robust retries, logging, safety stop behavior.

## 8. Recommended ROS2 Architecture

Suggested modules:
1. `km1_serial_driver`
   - low-level serial + protocol parser/formatter
2. `km1_motion_server`
   - action/service abstraction for movement/gripper/stop
3. `km1_perception_bridge` (later)
   - OpenMV or other vision into ROS2 messages
4. Existing control framework
   - adapter callouts only, preserve decision/state machine logic

## 9. Risks / Known Gaps

1. PWM command effectiveness is user-confirmed, but exact ROS2 package/node path is not yet recorded in this workspace.
2. Completion criteria currently likely weak unless explicit feedback path is implemented.
3. Encoding inconsistencies in some vendor source files (UTF/GBK mixtures) may complicate direct reuse.
4. Several resources are Windows-first; Linux/macOS ROS2 setup may need replacements.
5. Existing project tilt-repair logic is not implemented.
6. True hand-guided teaching remains unconfirmed until torque/unload and read-current-position are verified on the servo bus.

## 10. Acceptance Gates (Do Not Skip)

Gate 1 (hardware baseline):
- Vendor host can execute and stop predefined motions reliably.

Gate 2 (protocol baseline):
- Manual serial command round-trip confirmed with deterministic behavior.

Gate 3 (ROS2 baseline):
- ROS2/PWM sending is partially user-confirmed; still record exact node/package path and repeatable command logs.

Gate 4 (framework integration):
- `motion_adapter.py` backed by ROS2 and returns boolean success correctly.

Gate 5 (system run):
- Existing controller runs full task loop with real motion and mock perception.

## 11. Immediate Next Actions (Most Practical)

1. Calibrate hardware servo definitions against the code/MuJoCo definitions.
   The current sequence can move the physical arm through the task, but several
   joints appear reversed or offset relative to the software model, especially
   near the wrist/end effector.
2. Reset to the known startup pose, then probe one servo at a time with small
   conservative PWM changes. Record each servo's physical role, positive
   direction, neutral PWM, safe range, and whether it matches the MuJoCo/IK sign.
3. Latest raw-ASCII direction calibration: historical `10 PWM/deg` probes
   showed `#001P1800` made joint1 move negative, `#002P1200` made joint2 move
   negative, and `#003P1200` matched MuJoCo joint3 positive. Treat those rows
   as sign evidence only. With the current `1000/135 PWM/deg` scale, positive
   software tests from zero are now joint0 `#000P1722`, joint1 `#001P1278`
   after the joint1 calibration offset, joint2 `#002P1722`, and joint3
   `#003P1278`.
4. Pay special attention to `servo004` wrist-roll handling. `move_to` currently exports raw targets for
   `#000-#003`; `#004` should not be assumed to match the viewer unless it is
   explicitly commanded or otherwise verified.
   When correcting a reversed joint, change the software sign in the mapping so
   the physical command mirrors around `150 deg` / `P1500`.
5. Do not treat `G0001` as a neutral raw PWM wrapper. User observed that sending
   `{G0001#000P1500T1500!...}` appears to trigger/restore a recorded
   initialization/homing action group and can interrupt desired motion. Keep it
   as a useful factory-action clue, but use raw `{#000P...!#001P...!}` commands
   for direct servo pose tests.
6. Final hardware straight/home export must use the measured pose in
   `HARDWARE_POSE_NOTES.md`:
   `{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}`.
   Do not infer this command from MuJoCo's visual center-up pose; the previous
   `#001P0600` inference was wrong for the physical arm and drove joint1 toward
   the ground.
7. Record exact ROS2 package/node path used for the successful PWM sending attempt.
8. Record real serial device, baud rate, and exact command strings used successfully.
9. Use `tools/km1_pwm_teach.py` to record 3-5 conservative known-good PWM poses.
10. Confirm whether `$DST!` reliably stops current motion on the current hardware path.
11. Investigate whether the bus servos expose unload/torque-off and read-current-position for future true hand-guided teaching.
12. Only after repeatable pose replay and servo-definition calibration, start `motion_adapter.py` ROS2 integration.

## 12. 2026-05-03 PWM/MuJoCo Calibration Incident Summary

Problem found:
- The exported hardware sequence initially used a final `#001P0600` "center-up"
  command inferred from the old MuJoCo visual pose. On real hardware this drove
  joint1 toward the ground, because physical upright/default for joint1 is
  servo `150 deg` / `P1500`, not a MuJoCo raw `-1.57 rad` shoulder value.
- Manual raw-ASCII tests also showed that the earlier joint direction assumption
  was incomplete: joint1 and joint2 behaved opposite of what the previous export
  expected, while joint3 matched the current inverted mapping.

Fixes applied:
- Final hardware straight/home command now comes from `HARDWARE_POSE_NOTES.md`
  measured values only:
  `{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}`.
- Current PWM direction mapping in `sim/vendor_km1_kinematics.py`:
  `#000` normal, `#001` inverted, `#002` normal, `#003` inverted.
- 2026-05-03 joint0/base_yaw correction: user confirmed `base_yaw = +0.504 rad`
  must command `#000P1714`, not `#000P1286`; therefore joint0 uses normal
  sign `+1` and positive base yaw maps above `P1500`.
- Important correction after a failed attempt: do not modify `sim/km1_arm.xml`
  just to make joint1 upright equal raw MuJoCo zero. That broke the existing
  numeric IK geometry and caused severe trajectory errors such as collision and
  loss of horizontal end-link behavior.
- Correct architecture: MuJoCo internal IK keeps its original joint convention;
  the "physical joint1 upright/default = 0 deg/P1500" rule is applied only when
  reporting calibrated angles to humans or converting software angles to
  hardware PWM.
- Current implementation in `sim/vendor_km1_kinematics.py`: joint1 uses
  `calibrated_joint1 = internal_joint1 + 90 deg` before PWM conversion, so
  internal upright `-90 deg` maps to calibrated `0 deg` and hardware `P1500`.
- Hardware scale corrected after user confirmed the servo protocol range:
  `P500..P2500` spans `270 deg`, so `P1500` is the center/default and
  `P500..P2500 = -135..+135 deg`. Current conversion uses
  `1000/135 = 7.4074 PWM/deg`.
- `sim_output/hardware_command_sequence.txt` and the `Integrated Algorithm`
  copy were regenerated with the corrected PWM chain.
- The full verified motion chain, including MuJoCo-displayed waypoint angles
  and the corresponding raw ASCII commands, is documented in
  `sim_output/MOTION_CHAIN.md` and copied to
  `Integrated Algorithm/sim_output/MOTION_CHAIN.md`.
- Latest trajectory adjustment: the grasp point is now `z=115 mm`, raised
  `15 mm` from the previous `100 mm`; the pick-approach point is directly above
  it at `z=215 mm`. After grasping, lift/transport height is `175 mm`. The
  shelf-turn transition is base-only: MuJoCo changes only joint0/base_yaw, and
  the hardware command sends only `{#000P2243T2500!}` so joint1-joint5 are not
  re-commanded during that turn.
- 2026-05-03 hardware diagnostic: user inserted/tested a pure base-turn segment
  from `pick_lift` by changing only joint0/servo000 while keeping joint1-4 at
  the `pick_lift` PWM values. Result: pure joint0 turn was stable with no
  visible shake/drop. The visible height variation appears when running the
  full `place_transfer` command, where joint1/joint2/joint3 also change.
  Interpretation: prioritize trajectory/IK waypoint shape and joint-space
  interpolation as the cause of the ~15 mm end-effector height change; do not
  treat joint1 torque insufficiency as the leading diagnosis unless it also
  drops during pure base rotation or while holding the final pose under load.

## 13. File Inventory Already Reviewed

### 13.1 `主程序代码` (core project)
- `main.py`
- `controller.py`
- `config.py`
- `models.py`
- `coordinate_transformer.py`
- `world_model.py`
- `motion_adapter.py`
- `perception_adapter.py`
- `interfaces.py`
- `decision/db_manager.py`
- `decision/task_planner.py`
- `CONTROL_INTERFACE_SPEC.md`
- `.vscode/settings.json`
- `.vscode/launch.json`
- `.vscode/c_cpp_properties.json`

### 13.2 `项目资源（厂商）` (representative critical files)
- `1.教程手册/视觉指令表.docx` (text extracted)
- `4.源代码程序/KM1机械臂Openmv视觉模块代码 V3.1/main.py`
- `4.源代码程序/KM1机械臂Openmv视觉模块代码 V3.1/kinematics.py`
- `4.源代码程序/同步示教器代码/Yteaching-Km1-pwm/uart1_send.ino`
- `tools/km1_pwm_teach.py`
- `4.源代码程序/仿生手套代码/Ygloves-Km1/loop_glove_R.ino`
- `5.软件工具/4.上位机软件/机械臂Km1动作组.ini`
- `5.软件工具/5.串口助手/sscom51.ini`
- `6.拓展资料/拓展场景/出厂源码/滑轨抓取放下程序/STM32/.../User/main.c`
- `6.拓展资料/拓展场景/出厂源码/滑轨抓取放下程序/STM32/.../User/app_uart.c`
- `6.拓展资料/拓展场景/出厂源码/滑轨抓取放下程序/STM32/.../User/Components/y_usart/y_usart.c`
- `6.拓展资料/拓展场景/出厂源码/滑轨抓取放下程序/STM32/.../User/Components/y_global/y_global.c`

Not semantically reviewed:
- Binary caches and non-text media (e.g., `__pycache__/*.pyc`, videos, most executable installers, PDF internals).

## 14. 2026-05-04 Target-Triggered Hardware Sequence Entry

Goal:
- The current v1 control integration is target-driven: a caller provides only
  a book-spine grasp point `pick xyz` and a final shelf placement point
  `place xyz`.
- The program derives the existing generic pick/place policy, computes IK for
  all waypoints, converts the result into calibrated raw ASCII PWM commands,
  and optionally sends the sequence to the hardware.
- The MuJoCo viewer is not part of runtime execution. It remains a debugging
  and tuning tool only. Runtime sequence generation uses MuJoCo/IK calculation
  logic without opening a visual window.

New entry point:

```bash
python3 主程序代码/main.py \
  --run-target-sequence \
  --pick 218.0 120.23 115.0 \
  --place -40.0 260.0 124.25 \
  --dry-run
```

Hardware execution after dry-run review:

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

Implementation notes:
- `主程序代码/target_sequence.py` owns the target-to-waypoints policy and the
  calibrated MuJoCo-angle-to-PWM conversion for this v1 path.
- `sim_output/send_hardware_sequence.py` remains the serial sender. Do not
  duplicate its serial behavior unless the hardware protocol changes.
- `export_command_sequence.py` is legacy/log-based and should not be used as
  the current verified hardware source because it does not own the latest
  target-driven MuJoCo mapping or `base_only_from_previous` behavior.
- If `mujoco`/`numpy` are missing, the target sequence command stops before
  serial is opened. Install with `python3 -m pip install mujoco numpy pyserial`
  in the Ubuntu runtime environment.

## 15. 2026-05-04 Start Trigger and Dynamic Per-Servo Timing

School/demo requirement:
- The complete flow should start from one large button with no human
  intervention during motion.
- Before the physical button is installed, the target-sequence entry uses
  `--wait-trigger space`: the program generates and previews the command file,
  then waits for Space or Enter before sending to hardware.
- `--dry-run` skips the trigger wait so command generation remains convenient.
- `--wait-trigger button` is reserved and currently exits with a clear message;
  future GPIO/ROS2 trigger wiring should plug in there without changing the
  motion-generation path.

Timing update:
- Ordinary arm commands now allow each servo in one ASCII line to have its own
  `Txxxx`.
- Per-servo timing is based on PWM delta from the previous arm pose:
  - `delta < 20 PWM` -> `T0400`
  - `delta < 120 PWM` -> `T0800`
  - otherwise -> `T1500`
- The first arm command remains `T1500` for all joints because startup pose is
  treated conservatively.
- Base-only transfer remains `{#000...T2500!}` and still does not re-command
  joint1-joint5.
- Gripper close/open and measured home commands remain fixed.
- `TARGET_SEQUENCE_SUMMARY.md` now includes a PWM delta / timing audit table.

## 16. 2026-05-06 MuJoCo Shelf Geometry Update

Scene-only shelf adjustment:
- The MuJoCo shelf now represents two layers with `240 mm` layer height.
- Each shelf board is `10 mm` thick.
- The first board spans `z=30..40 mm`; therefore books placed on the first
  layer sit at `z=40 mm`.
- The second shelf surface is `z=280 mm`.
- `sim/km1_trajectory_viewer.py` now uses `LOW_SHELF_TOP_Z_M = 0.040` when
  snapping the placed-book visual to the lower shelf.
- This is a visual/scene geometry adjustment; it does not change the default
  pick/place target coordinates or hardware PWM mapping by itself.

## 17. 2026-05-06 Post-Grasp Lift Lowered for Two-Layer Shelf Clearance

Target-driven motion policy update:
- `POST_GRASP_LIFT_MM` in `主程序代码/target_sequence.py` changed from
  `60.0` to `45.0`.
- For the clean axis test input `pick=(220, 0, 115)` and
  `place=(0, 260, 124.25)`, this changes transport/lift Z from `175 mm` to
  `160 mm`.
- The generated axis-test CSV is `sim_output/examples/control_trajectory_axis_test.csv`.
- This is a policy change for derived target-sequence waypoints, not a change
  to the default pick/place coordinates.
- Purpose: reduce the chance of the held book reaching/colliding with the
  second shelf after the shelf scene was updated to a two-layer 240 mm height.

## 18. 2026-05-06 Held-Book Transport Retract Waypoint

Target-driven motion policy update:
- `主程序代码/target_sequence.py` now inserts `transport_retract` immediately
  after `pick_lift`.
- `transport_retract` keeps the same transport Z and moves the held book
  `70 mm` horizontally toward the arm origin `(0, 0)` before the base-only
  shelf turn.
- If the pick XY radius is less than `70 mm`, the retract distance is clamped so
  the waypoint does not cross past the origin.
- For the clean axis test input `pick=(220, 0, 115)` and
  `place=(0, 260, 124.25)`, the generated point is
  `transport_retract=(150, 0, 160)`.
- This is a generic load-reduction rule intended to lower yaw/shoulder torque
  while carrying the book; the external interface remains just `pick xyz` and
  `place xyz`.

## 19. 2026-05-07 Target Viewer CLI

MuJoCo debug entry update:
- `主程序代码/main.py` now supports `--target-viewer --pick X Y Z --place X Y Z`.
- This writes `sim_output/control_trajectory.csv` from the current generic
  target-sequence waypoint policy and opens `sim/km1_trajectory_viewer.py`.
- It does not generate or send hardware PWM commands. Use
  `--run-target-sequence` for the hardware path.
- Example:
  `python3 主程序代码/main.py --target-viewer --pick 220 0 115 --place 0 260 124.25`.

---
This document is intended as persistent handoff context for future AI conversations.
