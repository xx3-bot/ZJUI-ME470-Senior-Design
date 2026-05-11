# Run Modes

This folder has two separate execution paths.

Running `python3 主程序代码/main.py` with no arguments opens an interactive
terminal menu:

```text
1. Run hardware command sequence
2. Dry run hardware path
3. Simulation mode
4. Target viewer
5. Startup scan
6. Grip and place test
```

After choosing a number, press Enter at any prompt to use the current default
value. Passing CLI arguments directly still works and skips the menu.

The legacy controller still supports its original 11-hyperparameter prompt. If
that prompt appears, pressing Enter now loads `config.DEFAULT_RUNTIME_PARAMS`
instead of rejecting the empty input.

The generated target sequence may or may not include a `transport_retract`
waypoint. It is inserted only when the pick point is far enough from the arm
base: horizontal radius `> 240 mm`. When inserted, it retracts toward the origin
but never below `170 mm` radius. For closer picks, the sequence goes directly
from `pick_lift` to the shelf-side base transfer.

The intended future standard Auto flow is documented in
`AUTO_STANDARD_FLOW.md`. That document is for design/team alignment only; the
full Auto flow is not implemented yet.

## Startup Scan

Use this to collect the first three-view world-model input snapshot without
running a pick/place task:

```bash
python3 主程序代码/main.py --startup-scan --dry-run --wait-trigger none
```

For hardware testing, remove `--dry-run` after checking the command preview and
serial port. The workflow sends base-only scan commands for `-90 / 0 / +90`
degrees, captures `left.png`, `center.png`, and `right.png`, then sends the
documented home/straight command. Each run writes a timestamped snapshot under
`sim_output/startup_scan/`.

This path is independent from `--run-target-sequence`, `--target-viewer`, and
`--sim-mode`.

## Grip and Place Test

Use this current-stage test before the full Auto workflow is ready. It only
activates the `-90 deg` reference view and the `0 deg` bin/OCR view, then
generates a fixed-place target sequence:

```bash
python3 主程序代码/main.py \
  --grip-place-test \
  --dry-run \
  --wait-trigger none
```

Slot choices:

```bash
python3 主程序代码/main.py --grip-place-test --dry-run --wait-trigger none --grip-place-slot left
python3 主程序代码/main.py --grip-place-test --dry-run --wait-trigger none --grip-place-slot center
python3 主程序代码/main.py --grip-place-test --dry-run --wait-trigger none --grip-place-slot right
```

Fixed v1 coordinates:

- `pick = (220, 0, 115)`
- `left place = (-25, 250, 124.25)`
- `center place = (0, 250, 124.25)`
- `right place = (25, 250, 124.25)`

This mode logs OCR output if the camera works, but it does not use the OCR
pick point to drive the arm yet. It does not run the `+90 deg` scan and does
not interpret ABCD shelf sections. Each run writes a timestamped snapshot under
`sim_output/grip_place_test/`.

## Formal Hardware-Generation Path

Use this when the robot should generate a fresh trajectory from the current
pick/place targets and optionally send it to the arm:

```bash
python3 主程序代码/main.py \
  --run-target-sequence \
  --pick 218.0 120.23 115.0 \
  --place -40.0 260.0 124.25 \
  --dry-run
```

Remove `--dry-run` and pass the serial options only after checking the command
preview:

```bash
python3 主程序代码/main.py \
  --run-target-sequence \
  --pick 218.0 120.23 115.0 \
  --place -40.0 260.0 124.25 \
  --hardware-port /dev/ttyUSB0 \
  --hardware-baud 115200 \
  --fixed-step-delay 2.5
```

This path overwrites the latest runtime artifacts in `sim_output/`:

- `control_trajectory.csv`
- `hardware_command_sequence.txt`
- `TARGET_SEQUENCE_SUMMARY.md`

Do not combine `--run-target-sequence` with `--sim-mode`, `--viewer`,
`--target-viewer`, or simulation waypoint override flags.

## Simulation / Viewer Paths

Use these only for debugging, tuning, or visualization. They do not send
hardware commands:

```bash
python3 主程序代码/main.py --sim-mode
python3 主程序代码/main.py --viewer
python3 主程序代码/main.py --target-viewer --pick 218.0 120.23 115.0 --place -40.0 260.0 124.25
```

Historical CSV examples live in `sim/examples/`. IK probes and workspace grids
live in `sim/diagnostics/`. They are offline artifacts, not formal runtime
inputs.

## Raw Sender

`sim_output/send_hardware_sequence.py` only sends an already existing command
file. It does not plan or regenerate a trajectory. Use it only when deliberately
replaying a known command sequence.
