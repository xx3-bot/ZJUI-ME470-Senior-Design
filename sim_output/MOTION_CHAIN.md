# Current Verified Motion Chain

Last updated: 2026-05-03.

This file records the currently verified sim-to-hardware motion chain for the
book pick-and-place demo. The user tested the latest PWM conversion on hardware
and reported that the physical motion is basically consistent with the MuJoCo
viewer.

## Current Conversion

MuJoCo displayed angles are in degrees:

```text
#000 = 1500 + base_yaw * 1000/135
#001 = 1500 - (shoulder_pitch + 90) * 1000/135
#002 = 1500 + elbow_pitch * 1000/135
#003 = 1500 - wrist_pitch * 1000/135
#004 = 1500 + wrist_roll * 1000/135
```

Important details:

- `P500..P2500` spans `270 deg`, so the scale is `1000/135 = 7.4074 PWM/deg`.
- `#000/base_yaw` is normal: positive MuJoCo `base_yaw` increases PWM.
- `#001/shoulder_pitch` uses the MuJoCo internal-to-hardware offset first:
  `calibrated_joint1 = shoulder_pitch + 90 deg`, then inverted PWM mapping.
- `#002/elbow_pitch` is normal.
- `#003/wrist_pitch` is inverted.
- `#004/wrist_roll` is currently held at `P1500`.
- The final home/straight command is a measured hardware command, not generated
  from the MuJoCo formula.
- The grasp point is now `z=115 mm`, raised 15 mm from the earlier `100 mm`;
  the pick-approach point is directly above it at `z=215 mm`.
- After grasping, the lift/transport height is `175 mm`: the arm keeps that
  height through shelf turn/push approach, then lowers only at the place step.
- The shelf-turn transition is a base-only motion. MuJoCo changes only
  `base_yaw`; joint1-joint4 hold the lift pose, and the hardware command sends
  only `#000P2243T2500!` so joint1-joint5 are not re-commanded during the turn.

## Waypoints and Commands

| Step | Meaning | MuJoCo angles deg `[base, shoulder, elbow, wrist_pitch, wrist_roll]` | Raw ASCII command |
| ---: | --- | --- | --- |
| 00 | Viewer start/upright reference | `[0.000, -90.000, 0.000, 0.000, 0.000]` | `{#000P1500T1500!#001P1500T1500!#002P1500T1500!#003P1500T1500!#004P1500T1500!}` |
| 01 | Pick approach above raised grasp point | `[28.877, -68.715, 62.672, 3.760, 0.000]` | `{#000P1714T1500!#001P1342T1500!#002P1964T1500!#003P1472T1500!#004P1500T1500!}` |
| 02 | Lower to raised grasp point | `[28.877, -50.738, 98.859, -45.861, 0.000]` | `{#000P1714T1500!#001P1209T1500!#002P2232T1500!#003P1840T1500!#004P1500T1500!}` |
| 03 | Close gripper | same as step 02 | `{#005P1700T1000!}` |
| 04 | Lift after grasp to 175 mm | `[28.877, -66.055, 85.578, -21.730, 0.000]` | `{#000P1714T1500!#001P1323T1500!#002P2134T1500!#003P1661T1500!#004P1500T1500!}` |
| 05 | Base-only turn toward shelf at 175 mm | `[100.305, -66.055, 85.578, -21.731, 0.000]` | `{#000P2243T2500!}` |
| 06 | Push into shelf at 175 mm | `[98.746, -58.573, 73.744, -17.426, 0.000]` | `{#000P2231T1500!#001P1267T1500!#002P2046T1500!#003P1629T1500!#004P1500T1500!}` |
| 07 | Lower to place | `[98.746, -48.521, 85.845, -35.037, 0.000]` | `{#000P2231T1500!#001P1193T1500!#002P2136T1500!#003P1760T1500!#004P1500T1500!}` |
| 08 | Open gripper/release book | same as step 07 | `{#005P1400T1000!}` |
| 09 | Retreat from shelf at 175 mm | `[100.305, -78.932, 103.523, -26.793, 0.000]` | `{#000P2243T1500!#001P1418T1500!#002P2267T1500!#003P1698T1500!#004P1500T1500!}` |
| 10 | Measured hardware home/straight | measured hardware pose | `{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}` |

## Run Command

From the integrated folder on Ubuntu:

```bash
cd ~/Desktop/Integrated\ Algorithm
python3 sim_output/send_hardware_sequence.py \
  --commands sim_output/hardware_command_sequence.txt \
  --port /dev/ttyUSB0 \
  --baud 115200 \
  --fixed-step-delay 2.5
```

Send raw ASCII commands only. Do not wrap direct PWM commands with `G0001`, and
do not append `@GroupDone!`.

Gripper note: use `#005P1400` for release/open during the demo. Do not drive the
gripper fully to the old `P1000` open endpoint during normal release, because
the servo can hit the mechanical end stop and keep loading.
