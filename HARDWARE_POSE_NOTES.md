# Hardware Pose Notes

Last updated: 2026-04-30

This document records observed physical arm poses and their known serial/ROS2 command evidence.

## Pose A: startup straight pose

User description:
- Triggered/observed after startup.
- All joints are visually straight/extended.
- All reported/understood angles are `150.0`.

Observed serial monitor line:

```text
{G0001#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}
```

Parsed PWM targets:

| Servo ID | PWM | Time ms | Note |
| --- | ---: | ---: | --- |
| 000 | 1500 | 1500 | startup straight pose |
| 001 | 2000 | 1500 | startup straight pose |
| 002 | 2000 | 1500 | startup straight pose |
| 003 | 0850 | 1500 | startup straight pose |
| 004 | 1500 | 1500 | startup straight pose |
| 005 | 1500 | 1500 | startup straight pose / gripper neutral |

Observed completion feedback:

```text
@GroupDone!
```

Interpretation:
- `@GroupDone!` is received from the controller after the command/action completes.
- Do not treat `@GroupDone!` as part of the command to send unless a specific ROS2 wrapper requires it.

## Pose B: default Z-shaped pose

User description:
- This is the arm's default position.
- The arm visually forms a Z-like shape.

Current command evidence:
- Exact PWM command for this default Z-shaped pose has not yet been captured in this document.
- Need to capture the serial monitor line corresponding to this pose, or record the PWM table from the ROS2/app command that produces it.

TODO:
- Capture the command/echo line for the default Z-shaped pose.
- Record servo `000-005` PWM values and timing.
- Confirm whether this pose is the same as an app-level "home/default" action group or a separate startup/idle behavior.

## Related Control Notes

Known stop command:

```text
$DST!
```

Known single-servo command format:

```text
#005P1500T1000!
```

Known grouped command format:

```text
{G0001#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}
```

## Joint Calibration Notes

### Direction calibration update: 2026-05-03

Manual raw-ASCII calibration commands were tested against MuJoCo positive
joint motion. These rows are historical direction probes made with the old
`10 PWM/deg` assumption; keep them as sign evidence only, not as the current
angle-to-PWM scale.

| MuJoCo joint test | Tested command | Physical result | Mapping decision |
| --- | --- | --- | --- |
| joint1 +30 deg | `{#000P1500T1500!#001P1800T1500!#002P1500T1500!#003P1500T1500!}` | joint1 moved negative | invert `#001` mapping |
| joint2 +30 deg | `{#000P1500T1500!#001P1500T1500!#002P1200T1500!#003P1500T1500!}` | joint2 moved negative | do not invert `#002` mapping |
| joint3 +30 deg | `{#000P1500T1500!#001P1500T1500!#002P1500T1500!#003P1200T1500!}` | joint3 matched MuJoCo positive | keep `#003` inverted |

Current software-to-hardware direction convention for `measured_grasp`:

| MuJoCo joint | Servo ID | Software +30 deg should command now |
| --- | --- | --- |
| joint1 / shoulder | 001 | `P1278` after joint1 calibration offset |
| joint2 / elbow | 002 | `P1722` |
| joint3 / wrist pitch | 003 | `P1278` |

### joint0 / servo000: base pan / turret

User observation:
- `joint0` is the base pan / turret joint.
- Right rotation limit corresponds to PWM `500`.
- Left rotation limit corresponds to PWM `2500`.
- Later MuJoCo comparison confirmed that positive `base_yaw` should increase
  PWM above `P1500`. A test pose with `base_yaw = +0.504 rad` was mirrored when
  commanded as `#000P1286`; matching MuJoCo required `#000P1714`.

Direction convention from observation:

| Joint | Servo ID | Right limit PWM | Left limit PWM | Notes |
| --- | --- | ---: | ---: | --- |
| joint0 | 000 | 500 | 2500 | PWM increases from right toward left |

Suggested working rule until more testing:
- Treat `1500` as approximately center.
- Do not command the full `500-2500` span in autonomous motion until conservative safety margins are chosen.

### joint1 / servo001

Previous serial observation:
- During a joint1 test, the serial monitor repeatedly showed command echo:
  - `#001P0500T2000!`
- The monitor also repeatedly showed stop/ack feedback:
  - `#001PDST!#OK!`
  - sometimes split as `#001PDST!` then `#OK!`
- User initially did not observe obvious physical movement from that text alone.

Confirmed user observation:
- `joint1` is physically structure-limited.
- Backward limit is approximately PWM `2400`.
- Forward limit is approximately PWM `550`.
- This is the only joint currently noted as physically structure-limited.

Direction convention from observation:

| Joint | Servo ID | Forward limit PWM | Backward limit PWM | Notes |
| --- | --- | ---: | ---: | --- |
| joint1 | 001 | ~550 | 2400 | PWM increases from forward toward backward; structure-limited |

Interpretation:
- The controller/remote path is receiving or echoing the joint1 target command.
- The repeated `#001PDST!#OK!` suggests the control source may be sending a stop-on-release command after each command/button event.
- Do not use the full nominal `500-2500` span for joint1; use a margin within `~550-2400` for autonomous motion.

### joint5 / servo005: gripper

User observation:
- `joint5` is the gripper open/close joint.
- Gripper open corresponds to PWM `500`.
- Gripper closed corresponds to PWM `2500`.

Direction convention from observation:

| Joint | Servo ID | Open PWM | Closed PWM | Notes |
| --- | --- | ---: | ---: | --- |
| joint5 | 005 | 500 | 2500 | PWM increases from open toward closed |

Suggested working rule until object-specific grip tests:
- Use conservative intermediate grip values for books before commanding full `2500`.
- Record the smallest PWM that reliably holds a book without crushing or overloading the gripper.

### joint4 / servo004: wrist roll

User observation:
- `joint4` is the gripper wrist rotation joint.
- Left rotation limit corresponds to PWM `500`.
- Right rotation limit corresponds to PWM `2500`.

Direction convention from observation:

| Joint | Servo ID | Left limit PWM | Right limit PWM | Notes |
| --- | --- | ---: | ---: | --- |
| joint4 | 004 | 500 | 2500 | PWM increases from left toward right |

Suggested working rule until more testing:
- Treat `1500` as approximately centered wrist roll.
- Avoid full-span wrist roll while holding a book until cable clearance and gripper collision margins are checked.

### joint3 / servo003

User observation:
- Forward limit corresponds to PWM `2500`.
- Backward limit corresponds to PWM `500`.

Direction convention from observation:

| Joint | Servo ID | Backward limit PWM | Forward limit PWM | Notes |
| --- | --- | ---: | ---: | --- |
| joint3 | 003 | 500 | 2500 | PWM increases from backward toward forward |

Suggested working rule until more testing:
- Use conservative margins around the physical end stops before autonomous motion.
- Confirm how this joint maps to MuJoCo/vendor wrist-pitch sign before converting IK output directly.

### joint2 / servo002

User observation:
- Forward limit corresponds to PWM `2500`.
- Backward limit corresponds to PWM `500`.
- Later calibration note:
  - When `joint2` makes `link1` and `link2` completely straight/flat, PWM is
    approximately `1500`, matching MuJoCo `joint2 = 0`.
  - Sending `#002P2400T2000!` produces a physical angle much larger than
    `90 deg`.
  - Sending `#002P2100T2000!` produces a physical angle close to `90 deg`.
  - Therefore the earlier simple assumption `PWM = physical_degrees * 10` is
    not valid for `joint2` direct angle conversion.
  - Later protocol confirmation superseded the rough local estimate: command
    range `P500..P2500` spans `270 deg`, so the current project scale is
    `1000/135 = 7.4074 PWM/deg`.

Direction convention from observation:

| Joint | Servo ID | Backward limit PWM | Forward limit PWM | Notes |
| --- | --- | ---: | ---: | --- |
| joint2 | 002 | 500 | 2500 | PWM increases from backward toward forward |

Suggested working rule until more testing:
- Use conservative margins around the physical end stops before autonomous motion.
- Confirm how this joint maps to MuJoCo/vendor elbow sign before converting IK output directly.

## Confirmed Joint Range Summary

| Joint | Servo ID | Low/negative-side PWM | High/positive-side PWM | User-observed direction |
| --- | --- | ---: | ---: | --- |
| joint0 | 000 | 500 | 2500 | right -> left as PWM increases |
| joint1 | 001 | ~550 | 2400 | forward -> backward as PWM increases; structure-limited |
| joint2 | 002 | 500 | 2500 | backward -> forward as PWM increases |
| joint3 | 003 | 500 | 2500 | backward -> forward as PWM increases |
| joint4 | 004 | 500 | 2500 | left -> right as PWM increases |
| joint5 | 005 | 500 | 2500 | open -> closed as PWM increases |

## 2026-05-03 Calibration Incident and Current PWM Export Rule

Issue:
- A previous generated final pose used `#001P0600` because it was inferred from
  MuJoCo's old visual shoulder value of about `-1.57 rad` for upright. This was
  wrong for hardware. The real joint1 upright/default reference is servo
  `150 deg` / `P1500`.

Current rule:
- Treat software/MuJoCo-facing joint zero as hardware `P1500`.
- For joint1, this rule applies at the reporting/PWM conversion layer only:
  physical upright/default should be treated as calibrated joint1 `0 deg` /
  `P1500`, while MuJoCo's internal IK may still use shoulder `-90 deg` for the
  same visual pose.
- Current code applies `calibrated_joint1 = internal_joint1 + 90 deg` before
  converting joint1 to PWM. Example: internal `-90 deg` becomes calibrated
  `0 deg`, then maps to `P1500`.
- Confirmed servo protocol scale: command range `P500..P2500` spans `270 deg`.
  With `P1500` as the centered/default command, this maps to `-135..+135 deg`.
  The project now uses `1000/135 = 7.4074 PWM/deg`.
- Do not modify MuJoCo XML geometry just to make raw joint1 zero upright; that
  broke the viewer trajectory and horizontal end-link behavior.
- Mirror reversed joints around `P1500`, not around physical zero.
- Current direction mapping after manual one-joint tests:
  - joint0/servo000: normal, software `+30 deg -> #000P1722`.
  - joint1/servo001: inverted, calibrated software `+30 deg -> #001P1278`.
  - joint2/servo002: normal, software `+30 deg -> #002P1722`.
  - joint3/servo003: inverted, software `+30 deg -> #003P1278`.
- Final straight/home pose must use the measured direct raw command:
  `{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}`.
