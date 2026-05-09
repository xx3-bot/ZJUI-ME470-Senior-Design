# ME470 Lab Notebook - Team 34

Project: A Vision-Integrated Robot for Autonomous Book Classification and Reshelving in Library Environments  
Team: Zehao Bao, Zhenxiong Tang, Zhecheng Lou, Xinrui Xiong  

## 1. Project Objective

The project aims to build a robotic system that can identify returned books, determine their target shelf zones, pick up a book from a return-bin area, find a suitable shelf gap, and place the book back into the shelf. The final system is intended to integrate perception, decision-making, motion planning, and hardware execution.

The intended full workflow is:

1. Scan the return-bin region and identify book titles.
2. Query the book database to determine the target shelf zone.
3. Localize the selected book and generate a grasp point.
4. Detect shelf occupancy and available gaps.
5. Select a safe placement opportunity using clearance and confidence rules.
6. Generate a pick-and-place motion sequence.
7. Command the physical robotic arm through ROS2 or a serial bridge.
8. Verify task completion and repeat until all pending books are handled.

## 2. Team Role Summary

Xinrui Xiong worked mainly on mechanical/hardware adjustment, robotic arm control, hardware-software integration, prototype testing, ROS2/serial bring-up, and command-level validation.

Zhecheng Lou worked mainly on mechanical design, gripper structure optimization, three-claw gripper redesign, mounting hardware, and assembly support.

Zehao Bao worked mainly on barcode/book-title recognition, shelf occupancy perception, book-spine detection, visual localization, and the vision-to-world-pose pipeline.

Zhenxiong Tang worked mainly on database design, decision subsystem design, main program implementation, task flow, adapter interface definitions, and decision-control integration.

## 3. Chronological Lab Log

### 2026-04-03 - Initial System Direction and Mechanical Risk Identification

Objective:

Establish the project direction, divide responsibilities, identify the main early design risks, and decide the next mechanical and software integration steps.

Work performed:

- Defined the project as a vision-integrated robotic system for autonomous book classification and library reshelving.
- Identified the initial hardware problem: the existing two-claw gripper could not guarantee stable grasping, especially for books or objects that are thin, slippery, or irregularly positioned.
- Proposed adding a small paddle or additional contact structure to improve the gripping interface.
- Completed base structure design and robotic arm modification planning with modular interfaces for sensors.
- Completed feasibility analysis and RFA.
- Purchased main mechanical components needed for prototype assembly.
- Started planning camera mounting and sensor integration.

Technical observations:

- Reliable grasping is a major mechanical constraint because a book can slip during arm acceleration or rotation.
- Camera-robot calibration was recognized early as a key integration risk. The system needs a stable relationship between the camera frame and robot base frame.
- Motion planning, perception, and hardware control must be connected through consistent coordinate definitions.

Results:

- The project scope and main architecture were agreed upon.
- The first mechanical improvement direction was selected: move from a basic two-claw design toward a more stable gripping mechanism.
- Hardware purchasing and assembly preparation were mostly complete.

Problems and risks:

- The two-claw gripper was not reliable enough.
- Camera-to-robot transform calibration was not yet solved.
- The software pipeline from vision to decision to hardware had not yet been tested end to end.

Next steps:

- Design a new three-claw or paddle-assisted gripper.
- Design and integrate a fixed camera mount.
- Set up the Orbbec Astra Pro depth stream.
- Begin implementation of book/barcode recognition.
- Continue database and decision subsystem development.

### 2026-04-10 - System Architecture and Perception-Planning Strategy

Objective:

Clarify the system architecture and refine the core technical strategy for dynamic shelf placement.

Work performed:

- Completed the overall architecture design covering perception, planning, and manipulation.
- Finalized the robotic arm structure concept with a three-finger gripper.
- Selected and verified key hardware components such as RGB-D camera and actuators.
- Designed the perception pipeline for book identification and shelf gap detection.
- Implemented the initial database interface for retrieving target shelf information.
- Prepared the system for full hardware-software integration.

Technical observations:

- The main problem was reframed from only grasping to reliable placement in a dynamic, partially occupied bookshelf.
- Unlike simple pick-and-place with predefined target points, this task requires real-time perception of shelf occupancy and gap size.
- The team proposed a perception-planning framework that uses RGB-D data to detect gaps, estimate physical dimensions, and apply safety-margin-based fit evaluation.

Results:

- The system-level design became clearer: perception identifies books and gaps, the decision module selects placement opportunities, and the manipulation module executes the motion.
- The database and decision interfaces started to become concrete software components instead of only conceptual blocks.

Problems and risks:

- Gap detection can be affected by viewing angle and depth noise.
- Camera-arm calibration errors directly affect placement accuracy.
- Real-time synchronization between perception, task planning, and motion control remained unresolved.

Next steps:

- Finish shelf occupancy perception and slot selection logic.
- Test visual servo control.
- Calibrate the camera-to-arm transformation.
- Begin initial end-to-end placement experiments.

### 2026-04-17 - Prototype Assembly, Decision Code, and Workspace Constraints

Objective:

Move from architecture planning toward actual prototype testing and decision-driven manipulation.

Work performed:

- Completed full code construction of the planning and decision system, including book database and complete task chain.
- Verified the decision/task chain through virtual data simulation.
- Defined standardized interfaces between perception and decision modules.
- Completed physical prototype assembly using aluminum frame structure, six serial bus servos, and ESP32 control board.
- Built the experimental scenario and performed basic functional tests.
- Verified that the current hardware could perform required experimental operations without exceeding design load capacity.
- Completed preliminary perception model training for book identification and gap detection.
- Verified the Astra Pro depth stream.

Technical observations:

- The software challenge was precise decision-driven robotic manipulation. The system must map camera coordinates to arm coordinates, calculate target points, and fine-tune dynamically using perception feedback.
- The hardware challenge was gripper stability during dynamic motion. Books may slip under rapid arm motion if contact friction and contact area are insufficient.
- The third-claw mounting height needed to be optimized so that the book center of gravity remains stable after extraction.
- Workspace constraints became more important: the team needed MuJoCo or another simulator to check joint limits and avoid bookshelf collisions.

Results:

- A physical prototype and experimental setup were available for integration testing.
- The decision subsystem and database were implemented and verified with mock/virtual data.
- Perception training and depth stream validation made the vision side ready for deeper integration.

Problems and risks:

- Visual perception and motion control were not yet precisely coordinated.
- Hand-eye calibration remained a key source of placement error.
- Emergency handling for unexpected book tilt had not been developed or verified.
- Physical-environment joint debugging between perception and decision modules was not yet complete.
- Workspace and collision limits still needed simulation-based validation.

Next steps:

- Complete software-hardware integration between perception, planning, and manipulation.
- Deploy and test the visual servo module.
- Improve gap detection robustness and hand-eye calibration.
- Develop exception handling for book tilt or failed placement.
- Continue gripper redesign and dynamic holding tests.

### 2026-04-24 - Subsystem Interface Definition and Integration Preparation

Objective:

Prepare the project for end-to-end integration by refining control code, perception logic, and adapter interfaces.

Work performed:

- Debugged the robotic arm control program.
- Set up integration environment and subsystem interfaces.
- Continued third-claw CAD redesign based on the existing gripper model.
- Refined vision logic for book and spine text identification.
- Modified and refined the main program code.
- Configured system response-time behavior.
- Defined adapter interface specifications, especially `perception_adapter.py` and `motion_adapter.py`.

Technical observations:

- The project needed stable adapter boundaries so that perception, decision, and control modules could be developed independently.
- Spine text recognition required logic tuning to avoid false grouping and improve title identification.
- Control code needed to translate high-level decisions into concrete robotic actions.

Results:

- Subsystem integration environment and interface specifications were established.
- Robotic arm control program entered active debugging.
- Vision algorithm logic was refined for book/spine identification.
- Adapter interface specifications were delivered to the team.

Problems and risks:

- End-to-end joint debugging across perception, planning, and manipulation was still pending.
- Third-claw CAD design was still in progress.
- Recognition accuracy under different lighting and viewing angles still required more testing.

Next steps:

- Complete perception adapter integration.
- Estimate book position from vision output.
- Complete subsystem integration.
- Begin end-to-end debugging across perception, planning, and manipulation.

### 2026-04-28 - ROS2 and Hardware Bring-Up Baseline

Objective:

Establish the starting status of the physical arm and define safe gates before ROS2 control.

Work performed:

- Recorded that the KM1 robotic arm was still in factory/original state.
- Confirmed ESP32 factory firmware was still present.
- Observed factory boot behavior: power-on beep and arm returning to a default pose.
- Defined a staged bring-up plan:
  1. Confirm hardware/electrical baseline.
  2. Detect serial device.
  3. Verify vendor or raw serial control before ROS2.
  4. Build a ROS2 serial bridge only after raw command control works.

Technical observations:

- At this stage, external serial control was not confirmed.
- Baud rate was assumed likely to be `115200`, but still needed validation.
- Flashing firmware was intentionally avoided because factory behavior provided a known-good baseline.

Results:

- The team established a safe hardware bring-up policy.
- The immediate priority became raw command verification rather than writing large ROS2 code first.

Problems and risks:

- Serial device was not yet identified.
- Vendor/raw command control was not yet confirmed.
- ROS2 parity was not started.

Next steps:

- Connect USB data cable.
- Identify the OS serial device.
- Verify stop behavior.
- Test a low-risk serial command.
- Record command responses and motion behavior.

### 2026-04-29 - Vendor Kinematics, MuJoCo Simulation, and Shelf Feasibility

Objective:

Build a simulation and kinematics baseline for the KM1-like arm and determine which shelf targets are feasible.

Work performed:

- Inspected vendor ESP32 factory source and found kinematics parameters.
- Built or updated a MuJoCo KM1-like arm model.
- Added a MuJoCo workspace sampler and numeric IK helper.
- Ported vendor analytical IK and PWM command generation into Python.
- Created several IK grid and trajectory test files.
- Tested lower-shelf placement candidates.
- Built a simple pick-and-place visualization with a held book model and shelf platforms.

Technical observations:

- Vendor ESP32 and STM32/OpenMV sources used different kinematics profiles.
- MuJoCo visual reachability was useful for intuition but could not be trusted as hardware reachability.
- ESP32 factory IK suggested lower-shelf placement was feasible, but the upper shelf around `z=350 mm` was not feasible under the factory profile.
- Placement should not accept arbitrary reachable positions; it needs an angle constraint so the held book remains close to horizontal.

Key simulated lower-shelf candidates:

```text
left:   (-80, 240, 95) mm
center: (  0, 240, 95) mm
right:  ( 80, 240, 95) mm
```

Later aggressive lower-shelf candidates:

```text
left:   (-50, 300, 105) mm
center: (  0, 300, 105) mm
right:  ( 50, 300, 105) mm
```

Results:

- A usable MuJoCo visualization path was created.
- The viewer could show the robot, held book, side return-bin book, and shelf platform.
- A mock pick-and-place cycle was added:
  1. Move to side return-bin book.
  2. Pick and lift.
  3. Approach lower shelf.
  4. Insert/place book.
  5. Release and retreat.
- A joint teaching viewer was added for manual pose tuning.

Problems and risks:

- The physical servo angle range was not yet verified.
- MuJoCo and vendor IK disagreed in some areas.
- The upper shelf appeared unrealistic for the arm under early IK assumptions.
- Generated commands were still simulation artifacts, not hardware-proven commands.

Next steps:

- Continue lower-shelf placement tests.
- Verify raw serial command path on hardware.
- Record real servo directions, limits, and neutral references.
- Avoid upper-shelf hardware claims until the real arm proves the reach.

### 2026-04-30 - MuJoCo Pick/Place Demo and Control Interface Cleanup

Objective:

Turn the simulation work into a reusable demo path and define a stable `PickPlacePlan` contract.

Work performed:

- Set the current demo command:

```bash
python3 主程序代码/main.py --viewer
```

- Defined the default pick/place plan:

```text
pick_approach   = (218.0, 120.23, 200.0)
pick            = (218.0, 120.23, 100.0)
pick_lift       = (218.0, 120.23, 150.0)
place_transfer  = (-40.0, 220.0, 150.0)
place_approach  = (-40.0, 240.0, 104.25)
place_final     = (-40.0, 260.0, 124.25)
place_retreat   = (-40.0, 220.0, 150.0)
```

- Updated the book model to measured dimensions:

```text
book size = 200 x 140 x 10 mm
meaning = height x spine-to-pages width x thickness
grasp point = spine/edge point at 50% book height
```

- Converted the demo from a single jump into a staged sequence:

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
```

- Cleaned up obsolete backup artifacts and stale test values.
- Added relaxed transition alpha sweep fallback for high transition points that failed strict placement-style alpha checks.

Technical observations:

- The high pick-approach point is physically reachable, but earlier IK settings falsely rejected it because the alpha search range was too narrow.
- The simulation backend must distinguish placement-style constrained IK from transition-waypoint IK.
- The current canonical interface became a seven-point `PickPlacePlan`.

Results:

- The main program supported a complete MuJoCo-visible pick/place demo.
- MuJoCo numeric IK solved all current viewer waypoints.
- The demo became useful for teammate tuning and future vision/decision integration.

Problems and risks:

- The viewer was still not a calibrated digital twin.
- Broad MuJoCo ranges could produce physically unrealistic poses.
- Hardware safety still depended on future servo calibration.

Next steps:

- Use `sim/README.md`, `sim_output/README.md`, and `CONTROL_INTERFACE_SPEC.md` as the current interface references.
- Preserve the `PickPlacePlan` contract when adding perception and decision outputs.
- Continue hardware serial validation.

### 2026-04-30 - PWM Command Path and First Hardware Range Evidence

Objective:

Confirm whether PWM commands can actually move the physical arm and record initial servo range evidence.

Work performed:

- Confirmed that the user could send PWM commands to the physical arm.
- Observed controller/ESP32 output containing grouped command echoes and completion feedback.
- Recorded the startup/straight command echo:

```text
{G0001#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}
@GroupDone!
```

- Identified important command types:

```text
stop all motion: $DST!
single-servo command example: #005P1500T1000!
grouped command example: {#000P...!#001P...!...}
```

- Added a PWM teaching/helper tool for interactive command testing and pose recording.
- Recorded the first confirmed physical joint range table.

Confirmed physical joint range summary:

| Joint | Servo ID | Observed low side | Observed high side | Direction / role |
| --- | ---: | ---: | ---: | --- |
| joint0 | 000 | 500 | 2500 | base pan, right to left as PWM increases |
| joint1 | 001 | approx. 550 | 2400 | forward to backward as PWM increases; structure-limited |
| joint2 | 002 | 500 | 2500 | backward to forward as PWM increases |
| joint3 | 003 | 500 | 2500 | backward to forward as PWM increases |
| joint4 | 004 | 500 | 2500 | wrist roll, left to right as PWM increases |
| joint5 | 005 | 500 | 2500 | gripper, open to closed as PWM increases |

Technical observations:

- `@GroupDone!` is feedback from the controller and should not be treated as text to append to ordinary raw commands.
- `$DST!` stops motion at the controller's tracked current position, but it is not a torque-off or servo-unload command.
- True hand-guided teaching was not available yet because torque-off and read-current-position commands were not confirmed.
- The old assumption that all hardware commands could be wrapped in `G0001` was risky because `G0001` appears related to stored action groups.

Results:

- PWM command effectiveness was confirmed on real hardware.
- Servo index mapping and rough direction/range evidence were available for all six channels.
- The next engineering step changed from blind probing to conservative pose replay and calibration.

Problems and risks:

- The default Z-shaped pose command was not yet captured.
- Completion feedback did not yet prove real physical motion completion.
- There was no confirmed servo position feedback.
- True bus-servo readback/unload protocol still needed vendor documentation or reverse engineering.

Next steps:

- Record 3-5 named safe poses.
- Compare IK-generated PWM outputs against measured physical pose tables.
- Avoid end stops by adding conservative margins.
- Use raw ASCII commands for direct testing instead of `G0001` wrappers.

### 2026-05-01 - Placement Order, Module Boundary, and Future IK Scoring

Objective:

Refine the placement policy and clarify responsibility boundaries between control, vision, and decision modules.

Work performed:

- Changed placement order based on observed desired behavior.
- The previous behavior effectively lowered first and then pushed inward.
- The revised behavior pushes inward while high, then lowers vertically, then opens the gripper.

Updated placement segment:

```text
place_transfer  = (-40.0, 220.0, 150.0)
place_approach  = (-40.0, 260.0, 150.0)
place_final     = (-40.0, 260.0, 124.25)
place_retreat   = (-40.0, 220.0, 150.0)
```

Reusable motion policy:

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

- Documented that the current hardcoded target points are temporary stand-ins for future vision/decision output.
- Clarified that the control/MuJoCo module should not own book detection, shelf segmentation, or global placement optimization.
- Added a minimal IK candidate cost structure for future tuning.

Technical observations:

- The control module should receive target points and derive intermediate waypoints.
- Vision and decision modules should produce book grasp points and shelf placement points.
- IK candidate cost weights were added but kept at `0.0`, so current behavior did not change.

Results:

- The control/vision/decision boundary became clearer.
- The motion sequence became more physically meaningful for shelf insertion.
- Future posture tuning can use cost weights instead of hardcoded one-off fixes.

Problems and risks:

- Cost scoring was present but not tuned.
- Vision and decision outputs still needed real coordinate integration.

Next steps:

- Preserve the `PickPlacePlan` contract.
- Connect future perception output through `perception_adapter.py`.
- Connect future hardware command execution through `motion_adapter.py`.

### 2026-05-01 - Vision Mock Injection Test Passed

Objective:

Verify that a vision-generated pick point can propagate through the planning and motion stack without requiring a real camera.

Work performed:

- Added configuration switches:

```python
USE_MOCK_VISION
USE_VISION_FOR_PICK
VISION_SHADOW_MODE
FAKE_VISION_PICK_POSE
```

- Added CLI flags:

```bash
--use-vision-for-pick
--vision-shadow-mode
--fake-vision-pose X Y Z
```

- Tested fake vision injection:

```bash
python3 主程序代码/main.py --sim-mode \
  --use-vision-for-pick --fake-vision-pose 150.0 100.0 80.0
```

Observed comparison:

| Item | Baseline | Fake vision injection |
| --- | --- | --- |
| pick | `(218.0, 120.23, 100.0)` | `(150.0, 100.0, 80.0)` |
| pick_approach | `(218.0, 120.23, 200.0)` | `(150.0, 100.0, 180.0)` |
| pick_lift | `(218.0, 120.23, 150.0)` | `(150.0, 100.0, 130.0)` |

Technical observations:

- The fake vision value changed the pick waypoint and automatically changed derived waypoints.
- Placement waypoints remained unchanged, as intended.
- Shadow mode correctly ran/logged vision without replacing the fixed pick pose.

Results:

- The vision-to-motion data path was verified end to end at the interface level.
- Remaining vision work became a calibration/real-input problem, not an adapter-contract problem.

Problems and risks:

- Real camera input, OCR robustness, and physical calibration were still not complete.

Next steps:

- Validate real image input.
- Calibrate camera intrinsics and extrinsics.
- Keep fallback behavior so demo does not crash when vision fails.

### 2026-05-02 - Hardware Sequence Sender and Feedback Timing

Objective:

Build a safer command-sending workflow for raw hardware sequence testing.

Work performed:

- Confirmed Ubuntu serial bring-up pattern:

```text
port = /dev/ttyUSB0
baud = 115200
DTR = False
RTS = False
open serial
sleep 2 seconds
read feedback with timeout
```

- Added a hardware smoke-test sender:

```bash
python3 sim_output/send_hardware_sequence.py --port /dev/ttyUSB0 --baud 115200
```

- Added a dry-run mode:

```bash
python3 sim_output/send_hardware_sequence.py --dry-run
```

- Updated sender timing after observing that the arm could move but some actions looked rushed or overlapped.
- Parsed the largest `Txxxx` duration in each command and waited that duration plus a settle margin.
- Changed feedback handling after observing raw PWM commands may echo but not emit `@GroupDone!`.

Technical observations:

- Raw `{#000...}` PWM commands should not require `@GroupDone!` after every line.
- Physical timing should rely on command duration plus settle margin.
- `@GroupDone!` should only be required for known saved action-group commands.
- Startup/action-group chatter can interfere with first commands, so sender startup quiet-window logic was added.

Results:

- The sender became safer for one-line-at-a-time command replay.
- The control path moved closer to a ROS2 bridge pattern, even though it was still a standalone smoke-test sender.

Problems and risks:

- Controller feedback could arrive before physical motion settled.
- Hidden startup action behavior could still interrupt the desired command sequence.

Next steps:

- Use raw ASCII commands without `G0001`.
- Add conservative fixed step delays when testing.
- Wait for quiet startup before sending the first command.

### 2026-05-02 - Hardware and Simulation Mismatch Identified

Objective:

Diagnose why the physical arm did not exactly match the MuJoCo motion.

Work performed:

- Ran generated command sequences on the physical arm.
- Observed that the real physical pose differed from the MuJoCo pose, especially near the last two links and end effector.
- Compared the generated command list against observed physical extra motions.

Technical observations:

- The exported command sequence starts directly with IK-generated PWM commands and does not include `G0001`.
- Extra physical upright/Z-like motions were likely caused by controller startup/action-group behavior or another active control source.
- The final visual center-up motion in the MuJoCo viewer was not automatically exported as a hardware command.
- The mismatch appeared more likely due to servo mapping/profile calibration than to the high-level task policy.

Results:

- The team identified hardware-simulation mismatch as a calibration issue.
- Servo direction, zero, scale, and offset calibration became the next priority.

Problems and risks:

- Raw PWM commands are direct servo targets. If the mapping is wrong, the whole task can look wrong even when the waypoint policy is reasonable.
- A final hardware home pose must be measured directly, not inferred from MuJoCo visual joint values.

Next steps:

- Probe one servo at a time.
- Record role, direction, neutral PWM, safe range, and sign relative to MuJoCo.
- Update the hardware-calibrated IK/profile instead of manually tuning coordinates around a wrong mapping.

### 2026-05-03 - Raw ASCII Serial Control and PWM Calibration

Objective:

Confirm the correct direct serial command style and calibrate hardware PWM mapping against MuJoCo/software joint definitions.

Work performed:

- Tested a terminal-style serial console and confirmed raw ASCII commands work.
- Confirmed the correct direct command style:

```text
{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}
```

- Confirmed not to append `@GroupDone!` to commands sent by project tools.
- Confirmed not to use `{G0001#...}` as a generic direct PWM wrapper.
- Performed one-joint calibration probes for joint directions.
- Updated PWM conversion scale after confirming command range:

```text
P500..P2500 spans 270 deg
P1500 is centered/default
scale = 1000 / 135 = 7.4074 PWM/deg
```

- Corrected joint mapping rules:

```text
joint0 / servo000: normal
joint1 / servo001: inverted, with joint1 calibration offset
joint2 / servo002: normal
joint3 / servo003: inverted
```

Technical observations:

- Software/MuJoCo/IK `0 deg` should map to hardware `P1500`.
- Reversed joints must be mirrored around `P1500`, not around physical `0 deg`.
- Physical joint1 upright/default should be treated as calibrated joint1 `0 deg` / `P1500`, while MuJoCo internal IK may still represent the same visual posture as shoulder `-90 deg`.
- Changing MuJoCo XML geometry to force raw joint1 zero upright caused trajectory failures, so the correction belongs in reporting/PWM conversion layers.

Updated command sequence after calibration included:

```text
{#000P1714T1500!#001P1342T1500!#002P1964T1500!#003P1472T1500!#004P1500T1500!}
{#000P1714T1500!#001P1209T1500!#002P2232T1500!#003P1840T1500!#004P1500T1500!}
{#005P1700T1000!}
...
{#005P1400T1000!}
...
{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}
```

Results:

- Raw ASCII command path was confirmed.
- Servo direction and scale mapping were significantly improved.
- The base yaw sign was corrected: positive MuJoCo base yaw must increase PWM.
- A dangerous old inferred final pose using `#001P0600` was invalidated.

Problems and risks:

- Per-joint calibration is still approximate.
- The final straight/home pose must use measured direct raw commands, not MuJoCo visual inference.
- Servo readback remains unavailable.

Next steps:

- Continue per-joint calibration with known angle check points.
- Use conservative command delays.
- Keep raw ASCII sequence sending as the current hardware smoke-test path.

### 2026-05-03 - Motion Stability Diagnostic

Objective:

Determine whether shaking/drop during transport was due to base rotation torque or the full transfer posture transition.

Work performed:

- Inserted/tested a pure base-turn segment after grasp and lift.
- During this segment, only joint0/base yaw changed while joint1-joint4 remained at the pick-lift PWM values.

Observation:

- The arm did not visibly shake or drop during the pure base turn.
- Visible height change appeared during the full `place_transfer` command, where shoulder, elbow, wrist, and base all changed.

Technical interpretation:

- The observed drop is more likely caused by planned posture transition and joint-space interpolation than by base yaw torque weakness alone.
- Separating transport into smaller stages should improve stability.

Next steps:

- Use a sequence structure:
  1. Lift.
  2. Retract toward the arm base.
  3. Turn base only.
  4. Adjust shelf-side reach/posture.
  5. Lower/place.

### 2026-05-04 - Target-Triggered Hardware Sequence Entry

Objective:

Create a cleaner runtime path where the caller only provides a pick point and place point, and the program generates intermediate waypoints and hardware commands.

Work performed:

- Added a target-driven hardware entry point in `主程序代码/main.py`.
- The caller provides:

```text
--pick X Y Z
--place X Y Z
```

- The program derives intermediate pick/place waypoints, computes MuJoCo IK without opening the viewer, writes the calibrated raw ASCII command sequence, and can call the serial sender automatically.

Dry-run command:

```bash
python3 主程序代码/main.py \
  --run-target-sequence \
  --pick 218.0 120.23 115.0 \
  --place -40.0 260.0 124.25 \
  --dry-run
```

Hardware command pattern:

```bash
python3 主程序代码/main.py \
  --run-target-sequence \
  --pick 218.0 120.23 115.0 \
  --place -40.0 260.0 124.25 \
  --hardware-port /dev/ttyUSB0 \
  --hardware-baud 115200
```

- Added a start trigger so real hardware runs wait after command generation and preview.
- Added dynamic per-servo timing based on PWM deltas:

```text
delta < 20 PWM  -> T0400
delta < 120 PWM -> T0800
otherwise       -> T1500
```

Technical observations:

- The MuJoCo viewer is not required for runtime execution; it is a tuning/debugging UI.
- Runtime still depends on MuJoCo Python calculation unless later replaced by a standalone IK module.
- The legacy log-based export path should not be used as the current verified hardware source.

Results:

- The project obtained a more realistic integration entry point:
  vision/decision can provide target points, and the control stack generates a hardware-ready sequence.

Problems and risks:

- The runtime path still depends on calibrated mapping and conservative serial testing.
- A physical start button was not yet integrated; Space/Enter is the software stand-in.

Next steps:

- Use `--run-target-sequence` for hardware ASCII generation/sending.
- Use dry-run preview before sending to hardware.
- Continue improving motion stability and calibration.

### 2026-05-04 - Offline Vision World-Pose Test

Objective:

Verify that the vision pipeline can produce world-coordinate book poses from real images, without requiring live camera capture.

Work performed:

- Added `get_pick_world_pose_from_frame(frame, title)`.
- Added `vision/test_world_pose.py`.
- Ran the offline image-to-world-pose pipeline on iPhone test images.

Results:

- 6 test images were processed.
- 5 images successfully returned world pose.
- OCR, depth estimation, back-projection, transform logic, and output formatting all ran end to end.
- Different input images produced different pose outputs, confirming that the pipeline responds to visual input rather than returning a constant value.

Technical observations:

- Initial depth estimates were physically incorrect because the configuration used approximate C920e values while the images were from an iPhone camera.
- The direction and structural behavior were correct, but physical accuracy required real camera calibration.

Problems and risks:

- Camera intrinsics and extrinsics were still placeholders.
- OCR failures remained possible.

Next steps:

- Calibrate the C920e intrinsics.
- Measure the real camera-to-robot transform.
- Continue real-image validation.

### 2026-05-05 - C920e Calibration and Depth Validation

Objective:

Replace estimated camera parameters with measured intrinsics and verify physical depth accuracy.

Work performed:

- Added `vision/calibrate_intrinsics.py` with capture and solve modes.
- Captured 25 chessboard images using a 9x6 inner-corner board with 25 mm squares.
- Solved camera calibration and saved `vision/intrinsics_calibration.json`.

Calibration result:

```text
images used:      25 / 25
image size:       1280 x 720
reprojection RMS: 0.299 px
fx, fy:           962.98, 964.73
cx, cy:           609.01, 358.15
distortion:       [0.039, -0.132, 0.001, 0.000, 0.005]
```

- Fixed a depth-estimation bug in `vision/intrinsics.py`.
- Measured the book-spine geometry for the target book:

```text
spine height = 227 mm
visible OCR title height = 110 mm
ratio = 110 / 227 = 0.485
```

- Validated depth with known distances:

| Actual distance | Pixel height | Estimated depth | Error |
| ---: | ---: | ---: | ---: |
| 250 mm | 440 | 241.4 mm | -3.60% |
| 300 mm | 357 | 297.5 mm | -0.83% |
| 600 mm | 181 | 586.8 mm | -2.20% |

Technical observations:

- Depth estimation error was below +/-4% for the long-title target book.
- This is much better than the approximate tolerance needed for the demo.
- Short-title books are less accurate because a small text height makes pixel noise more significant.

Additional work:

- Added per-book `ocr_visible_height_mm` instead of using one global OCR-to-real-height ratio.
- Added title-character filtering in spine clustering to avoid authors/publishers stretching the detected bounding box.
- Added support for multiple known titles, including:
  - `"习近平新时代中国特色社会主义思想概论"`
  - `"羊皮卷"`

Results:

- Vision depth estimation became physically meaningful for the C920e.
- Long-title book depth was accurate enough for demo-level use.
- The vision pipeline became more robust across different books.

Problems and risks:

- World-frame x/y/z still depend on camera extrinsics, which must be measured after mounting.
- Short-title books remain more sensitive to OCR pixel noise.
- Minimum camera working distance is about 30 cm because a tall book spine can be clipped when too close.

Next steps:

- Mount the camera.
- Measure camera offset and pitch relative to the robot base.
- Keep the book roughly 30-50 cm from the camera for the demo.

### 2026-05-06 - AprilTag Startup Calibration and Shelf Geometry Update

Objective:

Support one-button demo startup by localizing the bin and shelf from AprilTags instead of assuming fixed world coordinates.

Work performed:

- Designed an AprilTag-based startup calibration framework.
- Proposed tag layout:
  - Bin: two 30 mm AprilTags, IDs 10 and 11.
  - Shelf: three 30 mm AprilTags, IDs 0, 1, and 2.
- Added runtime state storage for object poses.
- Added AprilTag detection and `solvePnP` wrapper.
- Added object-localization startup flow.
- Added configuration fields for bin model, shelf model, camera mount offset, camera pitch, scan angles, and gripper safety margins.
- Updated MuJoCo shelf geometry:

```text
shelf board thickness = 10 mm
first shelf support top = z 40 mm
second shelf support top = z 280 mm
layer spacing = 240 mm
```

- Lowered post-grasp lift from previous value by 15 mm:

```text
POST_GRASP_LIFT_MM = 45.0
```

- Added a `transport_retract` waypoint before base-only shelf turn:

```text
transport_retract moves XY 70 mm toward the robot origin
```

Technical observations:

- AprilTags make the bin/shelf placement more flexible because their world poses can be estimated at runtime.
- Retracting the held book closer to the base before turning should reduce yaw and shoulder torque.
- Lower transport height reduces risk of touching the second shelf during transfer.

Results:

- The project gained a plan for startup calibration and runtime object localization.
- The target sequence became more stable by adding retract-before-turn behavior.
- The shelf visual model better matched a two-layer shelf mock-up.

Problems and risks:

- AprilTag smoke tests and printed tag sheet workflow were not fully completed.
- Some geometry parameters were still marked as TODO until measured on the physical setup.
- Camera extrinsic calibration was still required.

Next steps:

- Finish AprilTag smoke tests.
- Generate and print tag sheets.
- Measure camera mount offset and pitch.
- Integrate startup calibration into the main program.

### 2026-05-07 - Target Viewer and Shelf-Slicing Decision Direction

Objective:

Improve target-based debugging and preserve the future shelf-slicing architecture.

Work performed:

- Added a target viewer CLI:

```bash
python3 主程序代码/main.py \
  --target-viewer \
  --pick 220.0 0.0 115.0 \
  --place 0.0 260.0 124.25
```

- The command generates `sim_output/control_trajectory.csv` and opens the MuJoCo viewer for inspection.
- It does not generate or send hardware PWM commands.
- Documented the intended shelf-slicing architecture:
  - Vision converts shelf perception into structured slices.
  - Decision scores slice-derived opportunities.
  - Control continues receiving target points or `PickPlacePlan`-shaped output.

Technical observations:

- Existing teammate decision code already splits each `ShelfGap` into fixed opportunities: `lean_left`, `center`, and `lean_right`.
- A fuller slicing system should allow a wide gap or partially occupied shelf region to produce multiple candidate placement windows.
- Each candidate slice should carry width, support side, clearance, confidence, occupancy risk, and whether placement would disturb existing books.

Results:

- Target-based visualization became easier.
- The future architecture was clarified without changing the control chain.

Problems and risks:

- Full shelf slicing was not implemented yet.
- Real shelf perception still needs reliable occupied/open interval detection.

Next steps:

- Vision should output shelf boundaries, book edges, occupied intervals, open intervals, support-side labels, and confidence.
- Decision should score multiple candidate slices and give rejection reasons.
- Control should keep using the existing waypoint, IK, and command-generation path.

### 2026-05-08 - Current Demo Boundary and Integration Strategy

Objective:

Clarify what should count as the main hardware demo path and avoid over-claiming upper-shelf behavior.

Work performed:

- Defined that the main motion/hardware validation path should remain the lower-shelf fixed pick/place flow.
- Recorded that second/upper shelf mock observations are useful for scanning, task routing, and decision robustness, but not the main physical execution target.
- Confirmed the strategy:
  - Do not rewrite the whole system.
  - Keep high-level logic mostly unchanged.
  - Replace or connect adapter layers first.

Current main validation commands:

```bash
python3 主程序代码/main.py --sim-mode
python3 sim_output/send_hardware_sequence.py --commands sim_output/hardware_command_sequence.txt --dry-run
python3 sim_output/send_hardware_sequence.py --commands sim_output/hardware_command_sequence.txt --port /dev/ttyUSB0 --baud 115200 --fixed-step-delay 2.5
```

Technical observations:

- The upper/second shelf layer should not be used as evidence that the physical arm can execute upper-shelf placement.
- Full mock controller runs without `--sim-mode` may create upper-zone tasks and attempt unreachable or non-demo targets.
- Those runs are useful for software branching and decision logging, not for physical reachability claims.

Results:

- The project now has a clear demo boundary:
  - lower-shelf fixed pick/place is the main hardware validation path;
  - upper-shelf behavior is software/decision test data.
- Correction: do not use a direct `motion_adapter -> per-pose hardware IK`
  bridge for the current hardware demo. Hardware execution should use
  `sim_output/hardware_command_sequence.txt` or regenerate that sequence through
  `主程序代码/target_sequence.py`.

Problems and risks:

- Completion semantics for a robust `move_to(...) -> bool` still need careful hardware validation.
- Camera extrinsics and AprilTag integration still need physical measurement.
- Full end-to-end autonomous shelf placement is not yet fully demonstrated.

Next steps:

- Prove a minimal hardware MVP:
  1. ROS2 or serial bridge can command arm motion.
  2. Completion status can be observed reliably.
  3. `move_to(...) -> bool` returns true only after actual completion.
- Continue adapter-based integration through `motion_adapter.py` and `perception_adapter.py`.

## 4. Current System Status as of 2026-05-08

Hardware:

- Physical arm can receive and execute raw ASCII PWM commands.
- Serial port testing is based on `/dev/ttyUSB0` at `115200` baud on Ubuntu.
- Servo IDs and rough physical ranges are known.
- Direct raw `{#...}` command style is confirmed.
- `G0001` should not be used as a generic raw command wrapper.
- `@GroupDone!` is feedback, not a command suffix.

Simulation and control:

- MuJoCo viewer and target viewer exist.
- The control path can generate staged pick/place trajectories.
- Target-driven sequence generation exists from user-provided pick and place points.
- Hardware command sequence generation exists, but still requires conservative review before physical runs.
- Current main demo path is lower-shelf pick/place.

Vision:

- Mock injection into the motion path is verified.
- Offline image-to-world-pose pipeline works.
- C920e intrinsic calibration is complete.
- Depth estimation for the main long-title book is within about +/-4% in tested distances.
- Per-book OCR-visible height support exists.
- AprilTag startup calibration framework is partially implemented.

Decision:

- Database and task-chain logic exist.
- Shelf gap opportunity logic includes a lightweight left/center/right split.
- Future work should extend this into slice-based scoring with confidence, clearance, support side, and rejection reasons.

Integration:

- Main architectural decision is adapter-based integration.
- Vision/decision provide target points.
- Control derives intermediate waypoints and checks IK.
- Hardware adapter/ROS2 bridge should send calibrated raw commands and observe completion.

## 5. Known Limitations and Risks

1. The MuJoCo model is not a fully calibrated digital twin.
2. Physical servo readback and torque-off/unload commands are not confirmed.
3. Some hardware completion feedback may not equal true physical motion completion.
4. Upper shelf placement is not the main physical demo target.
5. Camera extrinsics still need physical measurement after mounting.
6. Short book titles produce noisier depth estimates than long titles.
7. Real shelf gap detection under varying angle, lighting, and depth noise still needs physical testing.
8. Emergency handling for book tilt or failed insertion is not fully implemented.
9. The physical gripper still needs final holding-performance validation under dynamic motion.

## 6. Immediate Next Work

Hardware and control:

- Record a small set of named safe poses.
- Continue per-joint calibration.
- Validate raw command sequences with conservative timing.
- Implement or wrap the final ROS2 serial bridge after raw serial behavior is stable.
- Define reliable completion criteria for `move_to(...) -> bool`.

Vision:

- Measure camera mount offset and pitch relative to the robot base.
- Finish AprilTag startup calibration testing.
- Integrate runtime bin/shelf pose into the world-pose provider.
- Test live camera performance and direction consistency.

Decision:

- Extend placement opportunities from fixed left/center/right to multiple scored shelf slices.
- Log candidate scores and rejection reasons.
- Return `BLOCKED` with a clear reason when no safe slice exists.

System demo:

- Focus the final hardware demo on lower-shelf fixed pick/place first.
- Use upper-shelf mock data for decision robustness, not hardware reach claims.
- Keep integration through `motion_adapter.py` and `perception_adapter.py`.
