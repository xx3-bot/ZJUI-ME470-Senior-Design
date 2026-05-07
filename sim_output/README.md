# sim_output

`sim_output` is the simulated motion backend and log sink for the ME470
book-reshelving control program. It lets teammates run the current main program
without hardware, inspect every motion request, and open the MuJoCo viewer.

## Current Goal

The current short-term goal is a minimal, reusable pick/place pipeline:

1. receive or configure a book-spine grasp point,
2. receive or configure shelf placement points,
3. run the existing controller,
4. log every motion/gripper call,
5. visualize the full trajectory in MuJoCo.

This is intentionally shaped so a future vision/planning algorithm can provide
coordinates instead of a human typing them on the command line.

Boundary for future agents/teammates:

- This module is not the vision system and not the shelf/gap optimizer.
- Vision/decision code should provide the book grasp target and shelf placement
  target(s).
- The control demo receives those targets, derives the generic intermediate
  waypoints, checks IK reachability, logs the motion requests, and visualizes a
  normal `grip & place` sequence.
- Hardcoded defaults and CLI coordinates are acceptable temporary stand-ins for
  future vision/decision outputs. The reusable part is the motion policy and
  `PickPlacePlan` interface, not the specific numeric defaults.

## Quick Run

From the repository root:

Generate a hardware sequence from target coordinates without opening the
MuJoCo viewer:

```bash
python3 主程序代码/main.py \
  --run-target-sequence \
  --pick 218.0 120.23 115.0 \
  --place -40.0 260.0 124.25 \
  --dry-run
```

This writes:

```text
sim_output/control_trajectory.csv
sim_output/hardware_command_sequence.txt
sim_output/TARGET_SEQUENCE_SUMMARY.md
```

To inspect the same target-sequence policy in MuJoCo without generating or
sending hardware commands, use:

```bash
python3 主程序代码/main.py \
  --target-viewer \
  --pick 220.0 0.0 115.0 \
  --place 0.0 260.0 124.25
```

This writes `sim_output/control_trajectory.csv` and opens the step-by-step
viewer. Press `Space` to advance one waypoint at a time.

The target-sequence path uses MuJoCo/IK calculation logic without launching the
visualization window. The viewer is only for debugging/tuning. If the runtime
Python environment does not have `mujoco` and `numpy`, the command stops before
opening serial:

```bash
python3 -m pip install mujoco numpy pyserial
```

After checking the dry-run command preview, send the generated sequence on
Ubuntu. In real hardware mode the program waits in standby after command
generation; press `Space` or `Enter` to start the full sequence:

```bash
python3 主程序代码/main.py \
  --run-target-sequence \
  --pick 218.0 120.23 115.0 \
  --place -40.0 260.0 124.25 \
  --wait-trigger space \
  --hardware-port /dev/ttyUSB0 \
  --hardware-baud 115200
```

Use `--wait-trigger none` only for bench/debug runs where automatic immediate
execution is intentional. `--wait-trigger button` is reserved for the future
physical start button / ROS2 trigger wiring.

The target-sequence generator now assigns per-servo `Txxxx` timing from adjacent
PWM deltas to reduce small-angle jitter:

```text
delta < 20 PWM    -> T0400
delta < 120 PWM   -> T0800
otherwise         -> T1500
```

The first arm command, base-only turn, gripper commands, and measured home
command remain special cases. The generated `TARGET_SEQUENCE_SUMMARY.md`
includes a PWM delta / timing audit table for manual review.

Current target-sequence post-grasp lift is `45 mm` above the input pick point.
This lowered the previous `60 mm` transport height by `15 mm` to reduce the
chance of the held book reaching the second shelf in the updated two-layer
shelf scene. This does not change the default pick/place coordinates; it only
changes the derived `pick_lift`, `transport_retract`,
`place_transfer_base_only`, `place_approach`, and `place_retreat` Z values for
target-driven runs.

After `pick_lift`, target-sequence runs now add a `transport_retract` waypoint.
It keeps the same transport Z and moves the held book `70 mm` horizontally
toward the arm origin before the base-only shelf turn. This is a generic load
reduction policy, not a hardcoded coordinate.

If your shell has Fusion360 Python variables set on macOS, clear them first:

```bash
env -u PYTHONHOME -u PYTHONPATH python3 主程序代码/main.py --run-target-sequence --pick 218.0 120.23 115.0 --place -40.0 260.0 124.25 --dry-run
```

Open the existing MuJoCo debug viewer:

```bash
python3 主程序代码/main.py --viewer
```

This runs the current default minimal pick/place demo and opens MuJoCo.

Equivalent explicit command:

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

For log-only mode without opening MuJoCo:

```bash
python3 主程序代码/main.py --sim-mode
```

## Coordinate Contract

All coordinates are world-frame gripper target points in `mm`, relative to the
arm base/yaw joint coordinate system used by the current MuJoCo model.

The minimal flow uses one `PickPlacePlan`:

```text
pick_approach   = (x, y, z)
pick             = (x, y, z)
pick_lift        = (x, y, z)
transport_retract = (x, y, z)
place_transfer   = (x, y, z)
place_approach   = (x, y, z)
place_final      = (x, y, z)
place_retreat    = (x, y, z)
```

Important semantics:

- `pick_approach` is directly above `pick`: same X/Y, higher Z. The default
  clearance is `100 mm`, and it can be overridden with
  `--pick-approach-clearance` or a full `--pick-approach X Y Z`.
- `pick` is the book-spine / left-edge grasp marker, not the book center.
- The return-book visual in MuJoCo is offset from `pick` so the book body sits
  away from the gripper and the gripper approaches the spine side.
- The current MuJoCo book dimensions are `200 x 140 x 10 mm`:
  height x spine-to-pages width x thickness.
- The default `pick.z=100 mm` is the midpoint of the measured 200 mm book
  height.
- `pick_lift` raises the gripped book before the arm rotates toward the shelf.
  The current target-sequence lift is `45 mm`.
- `transport_retract` moves the held book `70 mm` toward the arm origin at the
  same transport Z before the base-only shelf turn. This reduces yaw/shoulder
  torque while carrying the book.
- `place_transfer` moves the held book to a shelf-side high waypoint.
- `place_approach` should push the held book inward at a high Z before the
  final downward placement move.
- `place_final` is the release target. Placement rows use a horizontal end-link
  constraint.
- `wrist_roll` is straightened to `0 deg` on horizontal pick/place rows so the
  book is not rolled sideways.
- `place_retreat` moves the gripper clear after release. Manual MuJoCo control
  starts after this retreat waypoint.

Current defaults:

```text
pick_approach   = (218.0, 120.23, 200.0)
pick             = (218.0, 120.23, 100.0)
pick_lift        = (218.0, 120.23, 150.0)
place_transfer   = (-40.0, 220.0, 150.0)
place_approach   = (-40.0, 260.0, 150.0)
place_final      = (-40.0, 260.0, 124.25)
place_retreat    = (-40.0, 220.0, 150.0)
```

## Future Vision/Planning Integration

The future vision/planning module should produce the same seven fields as the CLI
currently provides:

```python
from pick_place_plan import PickPlacePlan
from models import Pose

plan = PickPlacePlan(
    pick_approach=Pose(x_pick, y_pick, z_pick + clearance_mm),
    pick=Pose(x_pick, y_pick, z_pick),
    pick_lift=Pose(x_pick, y_pick, z_pick + lift_mm),
    place_transfer=Pose(x_transfer, y_transfer, z_transfer),
    place_approach=Pose(x_app, y_app, z_app),
    place_final=Pose(x_final, y_final, z_final),
    place_retreat=Pose(x_retreat, y_retreat, z_retreat),
)
```

Recommended division of responsibility:

- Vision detects the book and outputs `pick` as the spine/left-edge grasp point.
- Pick planning outputs `pick_approach` and `pick_lift`, usually by copying
  `pick.x/pick.y` and adjusting Z for pre-grasp descent and post-grasp lift.
- Shelf/gap planning outputs `place_transfer`, `place_approach`, `place_final`, and
  `place_retreat`.
- The controller should keep reading the plan through
  `config.get_pick_place_plan()` or a future provider with the same return
  shape.
- Avoid changing `controller.py` state sequencing unless the plan contract
  itself changes.

Detailed interface notes are in:

```text
主程序代码/CONTROL_INTERFACE_SPEC.md
主程序代码/pick_place_plan.py
```

## Logs

The default log path is:

```text
sim_output/sim_output.log
```

Each line is a JSON record. Motion records include:

- `timestamp`
- `session_id`
- `call_type`
- `input.current_pose`
- `input.target_pose`
- `book_position`
- `output.reachable`
- `output.reason`
- `output.joint_angles`
- `output.servo_pwm`
- `output.command`
- `output.error_code`
- `output.selection_cost`
- `output.cost_breakdown`

The simulation backend checks reachability with the current project IK profile:

```text
measured_grasp
```

The backend also has a lightweight IK candidate cost hook for future
joint-posture tuning. The current weights are all `0.0`, so the present demo is
not restricted by this cost and should keep the same behavior. The logged
`selection_cost` and `cost_breakdown` fields are there so future tuning can
compare candidate choices when weights are enabled.

Gripper records also carry a hardware-command definition. The gripper is servo
`005` in the ROS2/vendor command path:

```text
OPEN  -> {#005P1400T1000!}
CLOSE -> {#005P1700T1000!}
```

So a ROS2 bridge can translate the log/event stream as:

```text
move_to         -> output.command for servos #000-#003
gripper_command -> output.command for servo #005
```

Historical note: `export_command_sequence.py` can still export command strings
from old `sim_output.log` records, but it is not the source of truth for the
current verified hardware chain. It does not own the latest target-driven
MuJoCo angle mapping or the `base_only_from_previous` transfer behavior.
Prefer `main.py --run-target-sequence` for current hardware runs.

For old log-based smoke tests only, export one complete command sequence from
the latest simulated session:

```bash
python3 sim_output/export_command_sequence.py
```

This writes:

```text
sim_output/hardware_command_sequence.txt
```

The file contains only vendor command strings, one per line, so it can be used
as the source for a serial sender test. Send one line at a time and wait for the
controller completion response before sending the next line.

On Ubuntu 22, after the arm appears as `/dev/ttyUSB0` and permissions are set,
the smoke-test sender can send that file automatically:

```bash
python3 sim_output/send_hardware_sequence.py --port /dev/ttyUSB0 --baud 115200
```

To first trigger only the observed startup/reset pose, send the one-line reset
file:

```bash
python3 sim_output/send_hardware_sequence.py --commands sim_output/reset_startup_pose.txt --port /dev/ttyUSB0 --baud 115200 --fixed-step-delay 2.5
```

`reset_startup_pose.txt` is an observed reset/serial-control test command, not
a calibrated geometric home pose. The physical arm may look skewed there until
servo zero/direction definitions are calibrated.

The `G0001` prefix is not a neutral wrapper for arbitrary pose tests. Hardware
observation suggests it may trigger or restore a recorded factory
initialization/homing action group. Keep it as a reverse-engineering clue, but
prefer raw PWM commands such as `{#000P...!#001P...!}` when testing direct servo
targets.

Confirmed SSCOM-style raw ASCII path:

- Use plain ASCII `{#...}` command strings.
- Do not prepend `G0001`.
- Do not append `@GroupDone!`; that is feedback, not command text.
- Do not append a newline for the confirmed terminal-style path.
- The helper for one-command-at-a-time testing is:

```bash
python3 tools/km1_serial_console.py --port /dev/ttyUSB0 --baud 115200
```

Then type a full raw command, for example:

```text
{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}
```

Known non-blocking firmware message:

```text
LTR381 I2C错误3
```

This is an LTR381 sensor warning and did not prevent servo motion during the
confirmed raw ASCII test.

joint1/servo001 hardware limit note:

- `HARDWARE_POSE_NOTES.md` records joint1 as structure-limited to roughly
  PWM `550..2400`.
- Using the project convention that real `150 deg` equals software `0 deg`,
  the current practical IK working range is physical `60..240 deg`, which maps
  to software `-90..+90 deg`.
- The current IK helper now rejects candidates outside the configured
  `IK_JOINT_LIMITS_DEG`; joint1 is configured to `(-90.0, 90.0) deg`.
- Other IK joints are conservatively capped only where their old range exceeded
  `+/-100 deg`; current limits are `(-100,100)`, `(-90,90)`,
  `(-100,100)`, `(-100,100)` for the four IK-generated servo joints.

Servo mapping note:

- Software/MuJoCo/IK joint angle `0 deg` maps to physical servo `150 deg`, which
  is command value `P1500`.
- Command generation now uses the vendor servo range confirmed by the user:
  `P500..P2500` spans `270 deg`. With `P1500` as software/hardware zero, this
  means `P500..P2500 = -135..+135 deg` and
  `PWM = 1500 + sign * software_deg * (1000/135)`.
- joint1/servo001 is also offset at the conversion boundary: MuJoCo/vendor IK
  keeps the old internal shoulder convention where upright is about `-90 deg`.
  Before converting joint1 to PWM, the exporter applies
  `calibrated_joint1 = internal_joint1 + 90 deg`. This offset must not be fed
  back into MuJoCo IK or path planning.
- This makes the neutral/default mapping explicit for joint1 through joint4;
  joint signs still need hardware calibration.
- If a joint is found to be "reversed", flip the software sign in the mapping.
  The resulting hardware command mirrors around `150 deg` / `P1500`, not around
  physical `0 deg`. Example: software `+30 deg` becomes about `P1278` for a
  reversed joint instead of about `P1722`.
- Current `measured_grasp` hardware mapping after one-joint raw-ASCII
  calibration:
  - joint0/servo000 is not inverted: software `+30 deg -> #000P1722`.
  - joint1/servo001 is inverted: calibrated software `+30 deg -> #001P1278`.
  - joint2/servo002 is not inverted: software `+30 deg -> #002P1722`.
  - joint3/servo003 is inverted: software `+30 deg -> #003P1278`.
  Reversed joints are mirrored around `P1500`.
- The latest complete verified chain is documented in
  `sim_output/MOTION_CHAIN.md` and exported in
  `sim_output/hardware_command_sequence.txt`.
- Gripper release/open is now `#005P1400`, not the old full-open `#005P1000`,
  to avoid pushing the gripper servo into its mechanical endpoint.
- The current grasp point is `z=115 mm`, with the pick-approach point directly
  above it at `z=215 mm`.
- After grasping, the current target-sequence trajectory lifts/transports the
  book at `160 mm` for the clean axis test where `pick.z = 115 mm`
  (`POST_GRASP_LIFT_MM = 45 mm`)
  through the shelf turn and push, then lowers only at the placement step.
- For the clean axis test `pick=(220, 0, 115)`, the new `transport_retract`
  point is `(150, 0, 160)` before the base-only turn.
- The shelf-turn transition is base-only: the hardware command sends only
  `{#000P2243T2500!}` so joint1-joint5 are not re-commanded during that turn.

For debugging controller override/reset behavior, keep the serial connection
open after the final command without sending any stop/home/default command:

```bash
python3 sim_output/send_hardware_sequence.py --commands sim_output/reset_startup_pose.txt --port /dev/ttyUSB0 --baud 115200 --hold-open
```

The sender does not append `$DST!`, a home pose, or any default pose by itself.
If the arm returns to a Z/default pose while `--hold-open` is active, that
behavior is coming from firmware or another active control source, not from the
sender's post-sequence logic.

Current sequence-consistency note:

- `hardware_command_sequence.txt` starts directly with the IK-generated
  `pick_approach` command. It does not contain the observed `G0001`
  initialization/homing command and does not contain an explicit Z-default pose.
- As of the latest hardware check, `#000/base_yaw` uses normal sign: positive
  MuJoCo base yaw maps above `P1500`. The first pick approach therefore uses
  `#000P1714`, not the old mirrored `#000P1286/#000P1047` style commands.
- If the real arm moves through upright/Z-default before the first
  `pick_approach`, that motion is coming from controller startup/action-group
  behavior or another active control source, not from the exported sim_out
  sequence.
- The MuJoCo viewer appends a visual center-up motion after the final
  `place_retreat`. The exporter appends the documented raw PWM startup-straight
  pose from `HARDWARE_POSE_NOTES.md`, so the hardware sequence pulls the gripper
  out and then returns to the known physical straight pose.
- The MuJoCo viewer now starts from the same internal center-up pose used at the
  end of playback: `[0, -90, 0, 0, 0] deg`. Hardware-calibrated reporting can
  treat that physical joint1 upright pose as joint1 `0 deg` / `P1500`.
- Therefore the current viewer and hardware export are closer at the beginning
  and end of the run, while the middle pick/place waypoints remain the
  IK-exported task sequence.

The sender waits for controller startup chatter to become quiet before sending
the first exported command. Tune this if the controller still injects a delayed
startup/action-group motion:

```bash
python3 sim_output/send_hardware_sequence.py --port /dev/ttyUSB0 --baud 115200 --startup-quiet-window 2.0 --max-startup-wait 12.0
```

The sender follows the current known-good serial pattern: `dtr=False`,
`rts=False`, startup delay, raw ASCII command write, and a short feedback read
window. Raw PWM commands often echo the command but do not return `@GroupDone!`,
so `@GroupDone!` is not required by default. It also waits after each command
before sending the next one: by default it parses the command's `Txxxx` duration
and adds a `0.7 s` settle margin. For example, `T1500` waits about `2.2 s`.

For commands that are known to produce group completion feedback, require it
explicitly:

```bash
python3 sim_output/send_hardware_sequence.py --commands sim_output/reset_startup_pose.txt --port /dev/ttyUSB0 --baud 115200 --expected-feedback '@GroupDone!'
```

If the arm still looks rushed, force a fixed delay:

```bash
python3 sim_output/send_hardware_sequence.py --port /dev/ttyUSB0 --baud 115200 --fixed-step-delay 2.5
```

Test without hardware first:

```bash
python3 sim_output/send_hardware_sequence.py --dry-run
```

If a target is unreachable under the placement alpha range, the backend can try
the configured fallback alpha range. If that still fails with "no valid alpha",
the backend uses a relaxed transition alpha sweep for simulation waypoints such
as high transfer/approach poses. The log records which fallback succeeded.

## Trajectory CSV

When `--viewer` is used, the controller writes:

```text
sim_output/control_trajectory.csv
```

Current rows:

```text
1. pick approach above book: return book visible
2. pickup before grasp: return book visible
3. pickup after grasp: held book visible
4. pick lift after grasp: held book visible
5. place transfer: shelf-side high waypoint
6. place approach
7. place final before release
8. place final after release: placed book visible
9. post-release retreat: placed book remains visible
```

Columns:

```csv
x_mm,y_mm,z_mm,held_book_visible,return_book_visible,placed_book_visible,horizontal_end_link,base_only_from_previous
```

`horizontal_end_link=1` tells the viewer to keep the end link level/radial and
straighten wrist roll.

`base_only_from_previous=1` tells the viewer to change only `base_yaw` and hold
joint1-joint4 from the previous waypoint. The current shelf-turn transition uses
this to avoid visible wrist/link sliding while the base rotates.

Repeated-position state changes, such as "same pickup pose before/after grasp"
and "same release pose before/after opening", are short holds in the viewer.
Actual motion segments still use the normal interpolation length, so the arm
visibly moves to approach/final/retreat instead of appearing stuck at the
grasp/release point.

Viewer playback starts from the MuJoCo model's initial joint state, then moves
to `pick_approach`, descends to `pick`, closes the gripper, and continues to
`pick_lift`, then `place_transfer`, before lowering toward the placement waypoints. The book visual is anchored to the
last return-book visible waypoint before the grasp, so the upper approach point
does not move the book upward. After the post-release retreat, the viewer
appends a joint-space visual center-up motion before manual control starts.
Hardware export does not infer this pose from MuJoCo angles; it uses the
documented physical straight-pose command instead:

```text
{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}
```

## MuJoCo Viewer Controls

The MuJoCo trajectory viewer advances one step at a time. Press `Space` to run
the next segment; when the segment reaches its waypoint, the viewer pauses until
`Space` is pressed again. After the final center-up segment stops, the MuJoCo
window stays open for manual joint tuning.

Keyboard controls after stop:

- `0`: base yaw
- `1`: shoulder pitch
- `2`: elbow pitch
- `3`: wrist pitch
- `4`: wrist roll
- `5`: reserved for gripper; current XML has no gripper actuator yet
- left/right: selected joint `-1/+1 deg`
- down/up: selected joint `-5/+5 deg`

The right-side MuJoCo `Control` sliders are also active.

## Current Limitations

- This is a visualization and software-integration backend, not a calibrated
  hardware digital twin.
- Broad ESP32-factory-style MuJoCo joint ranges are for manual teaching only.
- Physical servo range, zero, direction, scale, collisions, and stop behavior
  are not verified.
- Do not send MuJoCo-discovered poses to hardware until the raw serial and
  servo-feedback gates in `ROS2_BRINGUP_PLAYBOOK.md` are passed.
- As of 2026-05-02, the full sequence can command the physical arm, but the
  real pose does not yet match the MuJoCo pose. Several joints are suspected to
  have reversed or offset code-vs-physical definitions. Treat this as a
  hardware profile calibration issue first: probe each servo direction/neutral
  point before changing the pick/place policy.
