#!/usr/bin/env python3
"""Send an exported KM1 command sequence over serial, one command at a time."""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path


DEFAULT_COMMAND_FILE = Path(__file__).resolve().parent / "hardware_command_sequence.txt"
MAIN_CODE_DIR = Path(__file__).resolve().parent.parent / "主程序代码"
TIME_TOKEN_RE = re.compile(r"T(\d{1,5})!")


def _load_commands(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"Command file not found: {path}")
    commands = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in commands if line and not line.startswith("#")]


def _open_serial(port: str, baud: int, timeout: float):
    try:
        if str(MAIN_CODE_DIR) not in sys.path:
            sys.path.insert(0, str(MAIN_CODE_DIR))
        from hardware_port import resolve_hardware_port
        import serial  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "pyserial is required for hardware serial output.\n"
            "Install it with: python3 -m pip install pyserial"
        ) from exc

    port = resolve_hardware_port(port)
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.timeout = timeout
    ser.dtr = False
    ser.rts = False
    ser.dsrdtr = False
    ser.open()
    ser.setDTR(False)
    ser.setRTS(False)
    return ser


def _read_until_feedback(ser, expected: str, timeout_s: float) -> str:
    deadline = time.monotonic() + timeout_s
    chunks: list[bytes] = []
    expected_bytes = expected.encode("ascii")
    while time.monotonic() < deadline:
        data = ser.read(256)
        if not data:
            continue
        chunks.append(data)
        joined = b"".join(chunks)
        print("RX raw:", data)
        try:
            print("RX txt:", data.decode(errors="replace"), end="")
        except Exception:
            pass
        if expected and expected_bytes in joined:
            return joined.decode(errors="replace")
    return b"".join(chunks).decode(errors="replace")


def _drain_until_quiet(ser, quiet_window_s: float, max_wait_s: float) -> None:
    """Read startup chatter until the controller has been quiet for a moment."""
    if quiet_window_s <= 0 or max_wait_s <= 0:
        return

    print(
        f"Waiting for controller quiet: {quiet_window_s:.2f}s quiet "
        f"within {max_wait_s:.2f}s max..."
    )
    deadline = time.monotonic() + max_wait_s
    quiet_deadline = time.monotonic() + quiet_window_s
    saw_data = False
    while time.monotonic() < deadline:
        data = ser.read(256)
        if data:
            saw_data = True
            quiet_deadline = time.monotonic() + quiet_window_s
            print("RX startup raw:", data)
            try:
                print("RX startup txt:", data.decode(errors="replace"), end="")
            except Exception:
                pass
            continue
        if time.monotonic() >= quiet_deadline:
            break
    if saw_data:
        print("\nController startup chatter drained.")
    else:
        print("No startup chatter observed.")


def _command_duration_s(command: str) -> float:
    times_ms = [int(match.group(1)) for match in TIME_TOKEN_RE.finditer(command)]
    if not times_ms:
        return 0.0
    return max(times_ms) / 1000.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send hardware_command_sequence.txt to the KM1 controller."
    )
    parser.add_argument("--commands", type=Path, default=DEFAULT_COMMAND_FILE)
    parser.add_argument("--port", default="auto")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--read-timeout", type=float, default=0.1)
    parser.add_argument("--startup-delay", type=float, default=2.0)
    parser.add_argument(
        "--startup-quiet-window",
        type=float,
        default=1.0,
        help="After opening serial, wait until no startup feedback arrives for this many seconds.",
    )
    parser.add_argument(
        "--max-startup-wait",
        type=float,
        default=8.0,
        help="Maximum seconds to wait for controller startup chatter to become quiet.",
    )
    parser.add_argument("--command-timeout", type=float, default=5.0)
    parser.add_argument(
        "--expected-feedback",
        default="",
        help="Optional required feedback string. Raw PWM commands often echo only, so default is no required token.",
    )
    parser.add_argument(
        "--feedback-read-window",
        type=float,
        default=0.5,
        help="Seconds to read and print feedback after each command when --expected-feedback is not set.",
    )
    parser.add_argument(
        "--settle-margin",
        type=float,
        default=0.7,
        help="Extra seconds to wait after the command's T duration before sending the next command.",
    )
    parser.add_argument(
        "--fixed-step-delay",
        type=float,
        default=None,
        help="If set, wait this many seconds after every command instead of using T duration + margin.",
    )
    parser.add_argument(
        "--line-ending",
        choices=["none", "lf", "crlf"],
        default="none",
        help="Bytes appended after each command. Current smoke test default is raw command only.",
    )
    parser.add_argument(
        "--post-sequence-hold",
        type=float,
        default=0.0,
        help="Seconds to keep the serial port open after the final command for debugging reset/override behavior.",
    )
    parser.add_argument(
        "--hold-open",
        action="store_true",
        help="After the final command, keep the serial port open until Ctrl+C without sending stop/home/default commands.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands without opening serial.",
    )
    args = parser.parse_args()

    commands = _load_commands(args.commands)
    newline = {"none": b"", "lf": b"\n", "crlf": b"\r\n"}[args.line_ending]

    print(f"Loaded {len(commands)} commands from {args.commands}")
    if args.dry_run:
        for index, command in enumerate(commands, start=1):
            print(f"{index:02d}: {command}")
        return

    ser = _open_serial(args.port, args.baud, args.read_timeout)
    try:
        time.sleep(args.startup_delay)
        print(f"Opened {args.port} @ {args.baud}")
        _drain_until_quiet(ser, args.startup_quiet_window, args.max_startup_wait)
        ser.reset_input_buffer()

        for index, command in enumerate(commands, start=1):
            print(f"\nTX {index:02d}/{len(commands)}: {command}")
            ser.write(command.encode("ascii") + newline)
            ser.flush()
            feedback_timeout = args.command_timeout if args.expected_feedback else args.feedback_read_window
            feedback = _read_until_feedback(ser, args.expected_feedback, feedback_timeout)
            if args.expected_feedback and args.expected_feedback not in feedback:
                raise SystemExit(
                    f"Timed out waiting for {args.expected_feedback!r} after command {index}."
                )
            delay = (
                args.fixed_step_delay
                if args.fixed_step_delay is not None
                else _command_duration_s(command) + args.settle_margin
            )
            if delay > 0:
                print(f"Waiting {delay:.2f}s before next command...")
                time.sleep(delay)
        if args.post_sequence_hold > 0:
            print(f"\nHolding serial open for {args.post_sequence_hold:.2f}s after final command...")
            _read_until_feedback(ser, "", args.post_sequence_hold)
        if args.hold_open:
            print("\nHolding serial open. No stop/home/default command will be sent. Press Ctrl+C to exit.")
            try:
                while True:
                    _read_until_feedback(ser, "", 1.0)
            except KeyboardInterrupt:
                print("\nInterrupted by user; closing serial without sending extra commands.")
        print("\nSequence completed.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
