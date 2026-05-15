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
7. Auto demo / detected-books loop
```

After choosing a number, press Enter at any prompt to use the current default
value. Passing CLI arguments directly still works and skips the menu.

The legacy controller still supports its original 11-hyperparameter prompt. If
that prompt appears, pressing Enter now loads `config.DEFAULT_RUNTIME_PARAMS`
instead of rejecting the empty input.

The generated target sequence now treats `pick_lift` as a post-grasp
extract-and-lift pose, not a pure vertical lift. It retracts the held book
toward the arm origin by up to `200 mm`, never below `125 mm` horizontal radius,
and lifts to `pick.z + 95 mm`. An additional `transport_retract` waypoint is
inserted only if the post-grasp extract pose still has radius `> 240 mm`.

The pick approach is now a low insert-style approach instead of a high
top-down descent. For a typical `pick=(250,0,115)`, the sequence now inserts a
`pick_insert_ready` pose at approximately `(175,0,160)` before the final low
approach. This lets the arm complete the obvious downward posture change at a
smaller X, away from the book top, then move through `(210,0,115)` toward
`(250,0,115)` so the claw reaches forward around the target book.

Current placement decision hint: `left_wall`. Before releasing the book, the
generated command sequence adds a servo004-only wrist-roll command that tilts
the held book left by `15 deg`, then opens the gripper. This is the first
simple decision-to-control hint for leaning a book against a left wall/support.
After opening the gripper, the sequence now adds `place_backoff`: a `50 mm`
horizontal retreat toward the robot origin at the same placement height before
lifting away.

Current gripper command constants in `target_sequence.py`:
- pre-open before low insert into pick: `{#005P1445T1000!}`
- close: `{#005P1700T1000!}`
- narrow open/release at shelf: `{#005P1625T1000!}`. This opens only `75 PWM`
  from the closed grasp so the claw does not sweep into neighboring books.
  The measured home command still returns servo005 to `P1500` after retreat.

The intended future standard Auto flow is documented in
`AUTO_STANDARD_FLOW.md`. That document is for design/team alignment only; the
full Auto flow is not implemented yet.

## Current Auto Demo Shell

As of 2026-05-15, `--auto-demo` is the main integrated software shell for
hardware trials. It is still a demo path, but it now has the intended Auto
shape:

```text
startup scan
-> bin/shelf vision snapshot
-> world-model-backed task plan
-> target_sequence command generation
-> operator confirmation trigger
-> hardware sender
```

Normal real-hardware command:

```bash
python3 主程序代码/main.py \
  --auto-demo \
  --camera-index 0 \
  --hardware-port auto \
  --hardware-baud 115200 \
  --fixed-step-delay 2.5 \
  --startup-scan-settle-seconds 4 \
  --wait-trigger space
```

Important current behavior:

- Startup scan should capture the center/bin view and the left shelf/world view.
- Auto demo reuses `startup_scan_snapshot.json` bin pick candidates. It should
  not rescan the bin again before target-sequence generation.
- If the detected pick X is near or above the workspace edge, expect IK failure;
  move the bin/book closer or add a future software guard.
- Shelf slots are still provisional. A 2026-05-15 run showed that the current
  shelf detector can misclassify a bin/books view as shelf slots. Do not treat
  autonomous shelf placement as complete until CAD/pose validation is added.
- Shared test images and runtime artifacts for remote teammates are under
  `测试文件/`.

## Detected Books Loop

This is the current strongest semi-automatic demo path. It uses one live camera
frame, detects all visible known books, orders them by
`config.KNOWN_BOOK_TITLES`, generates one `target_sequence` per book, and writes
a merged command file.

The standard current demo shell is:

```bash
python3 主程序代码/main.py \
  --auto-demo \
  --place 0 250 140 \
  --loop-place-step-mm 15 \
  --camera-index auto \
  --dry-run
```

If the Mac/iPhone Continuity camera is known to be OpenCV index 1, use:

```bash
python3 主程序代码/main.py \
  --auto-demo \
  --place 0 250 140 \
  --loop-place-step-mm 15 \
  --camera-index 1 \
  --dry-run
```

Immediate next validation:

```bash
python3 主程序代码/main.py \
  --auto-demo \
  --place 0 250 140 \
  --loop-place-step-mm 15 \
  --dry-run \
  --wait-trigger none
```

Check the printed plan before any hardware run:
- detected titles match the physical books,
- pick poses currently look like `(320, vision_y, 115)` after the 2026-05-14
  real camera/arm setup correction,
- place poses step as `(0,250,140)`, `(15,250,140)`, `(30,250,140)`,
- skipped/failed books are clearly reported,
- OCR text that does not match `KNOWN_BOOK_TITLES` is reported for manual
  handling, but never drives robot motion.

Then remove `--dry-run` only for a one-book hardware test first.

`--auto-demo` uses the same hardware-generation core as
`--run-detected-books-loop`, but labels the run as the current Auto-shaped demo:
vision candidates are recorded into `WorldModel`, a temporary fixed shelf
placement provider chooses each place point, `target_sequence.py` prechecks each
book, and the program prints an execution plan before the hardware sender step.
When `--max-loop-books` is omitted, every known book detected in the camera
frame is planned. Use `--max-loop-books 1` for the first hardware pass.

Dry-run first:

```bash
python3 主程序代码/main.py \
  --run-detected-books-loop \
  --place 0 250 140 \
  --loop-place-step-mm 15 \
  --dry-run
```

Hardware send after checking the printed candidates and generated command file:

```bash
python3 主程序代码/main.py \
  --run-detected-books-loop \
  --place 0 250 140 \
  --loop-place-step-mm 15 \
  --hardware-port auto \
  --hardware-baud 115200 \
  --fixed-step-delay 2.5
```

Useful test cap:

```bash
python3 主程序代码/main.py \
  --run-detected-books-loop \
  --place 0 250 140 \
  --max-loop-books 3 \
  --dry-run
```

Output goes to `sim_output/detected_books_loop/<timestamp>/`:
- `book_XX_control_trajectory.csv`
- `book_XX_hardware_command_sequence.txt`
- `book_XX_TARGET_SEQUENCE_SUMMARY.md`
- `loop_hardware_command_sequence.txt`
- `detected_books_loop_snapshot.json`
- `detected_books_loop_report.md`

This path is independent from `--startup-scan`, `--grip-place-test`,
`--run-target-sequence`, `--target-viewer`, and simulation modes. It still does
not perform full shelf/ABCD interpretation or vision-selected shelf slots.
The fixed shelf placement provider is intentionally temporary and should later
be replaced by section/slice decisions without changing `target_sequence.py`.

## Startup Scan

Use this to initialize the current two-view world snapshot without running a
pick/place task:

```bash
python3 主程序代码/main.py --startup-scan --dry-run --wait-trigger none
```

For hardware testing, remove `--dry-run` after checking the command preview and
serial port. The workflow sends base-only scan commands for physical `left-90 / 0` degrees,
captures `left.png` and `center.png`, then sends the documented home/straight
command. The left frame is processed by the shelf scanner; the center frame is
processed by the OCR/entity bin scanner and lateral pick provider. Each run
writes a timestamped snapshot under `sim_output/startup_scan/`, including a
`task_queue` for review. It does not send pick/place hardware commands.

This path is independent from `--run-target-sequence`, `--target-viewer`, and
`--sim-mode`.

## Grip and Place Test

Use this current-stage test before the full Auto workflow is ready. It only
activates the physical `left-90 deg` reference view and the `0 deg` bin/OCR view, then
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
- `left place = (-25, 250, 115)`
- `center place = (0, 250, 115)`
- `right place = (25, 250, 115)`

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
