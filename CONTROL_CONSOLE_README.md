# ME470 Control Console

Local-development desktop console for the current Integrated Algorithm codebase.

## Start

Install the UI dependency once:

```bash
.venv/bin/python -m pip install -r requirements-control-console.txt
```

Launch from the project root:

```bash
.venv/bin/python control_console.py
```

If Qt fails to load the macOS `cocoa` platform plugin, use the browser fallback:

```bash
.venv/bin/python web_control_console.py
```

Then open:

```text
http://127.0.0.1:8765
```

The console imports `主程序代码` directly. After changing the main algorithm,
restart the console to load the new code. No packaging step is needed during
active development.

## Current V1 Behavior

- Dashboard shows project paths, latest output files, camera status, and serial candidates.
- Camera can scan one frame through the current vision pipeline and reload latest overlays.
- Decision shows the latest detected-books loop report and task table.
- Path / Commands can generate a target-sequence dry-run and inspect latest commands/summary.
- Parameters displays important values from `config.py` and `target_sequence.py`.
- Hardware execution remains disabled in the UI for V1; use the existing CLI for real sending.

## Notes

If macOS denies camera access from the terminal, grant Camera permission to the
terminal app used to launch the console, then restart the console.
