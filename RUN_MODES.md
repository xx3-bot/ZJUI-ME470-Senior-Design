# Run Modes

This folder has two separate execution paths.

Running `python3 主程序代码/main.py` with no arguments opens an interactive
terminal menu:

```text
1. Run hardware command sequence
2. Dry run hardware path
3. Simulation mode
4. Target viewer
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
