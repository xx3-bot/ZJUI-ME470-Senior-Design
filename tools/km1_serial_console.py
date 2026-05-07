#!/usr/bin/env python3
"""Minimal screen-like serial console for the KM1 controller.

Type a complete command line such as:
  {#000P1500T1000!#001P2000T1000!}

The tool sends exactly that command plus the selected line ending, while a
background reader prints any controller feedback.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interactive KM1 serial console.")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port path")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument(
        "--line-ending",
        choices=["none", "lf", "cr", "crlf"],
        default="none",
        help="Line ending appended after each entered command",
    )
    parser.add_argument(
        "--reset-on-open",
        action="store_true",
        help="Allow DTR/RTS reset behavior on open. Default keeps DTR/RTS low.",
    )
    parser.add_argument(
        "--raw-rx",
        action="store_true",
        help="Print received bytes with repr() instead of decoded text.",
    )
    return parser


def rx_loop(ser, stop_event: threading.Event, raw_rx: bool) -> None:  # type: ignore[no-untyped-def]
    while not stop_event.is_set():
        try:
            data = ser.read(256)
        except Exception as exc:  # pragma: no cover - hardware path
            print(f"\n[rx error] {exc}", file=sys.stderr)
            stop_event.set()
            return
        if not data:
            continue
        if raw_rx:
            print(f"\n[rx] {data!r}", flush=True)
        else:
            text = data.decode("utf-8", errors="replace")
            print(text, end="", flush=True)


def main() -> int:
    args = build_parser().parse_args()
    try:
        import serial  # type: ignore
    except ImportError:
        print("pyserial is required: python3 -m pip install pyserial", file=sys.stderr)
        return 2

    ending = {
        "none": b"",
        "lf": b"\n",
        "cr": b"\r",
        "crlf": b"\r\n",
    }[args.line_ending]

    ser = serial.Serial()
    ser.port = args.port
    ser.baudrate = args.baud
    ser.timeout = 0.05
    ser.write_timeout = 1
    if not args.reset_on_open:
        ser.dtr = False
        ser.rts = False
    ser.open()

    # Give the bridge a moment to settle, then clear only stale host-side input.
    time.sleep(0.2)
    ser.reset_input_buffer()

    stop_event = threading.Event()
    reader = threading.Thread(target=rx_loop, args=(ser, stop_event, args.raw_rx), daemon=True)
    reader.start()

    print(f"Opened {args.port} @ {args.baud}. Type q/quit/exit to close.")
    print("Enter complete commands exactly as the vendor serial assistant accepts them.")
    print("Example: {#000P1500T1000!#001P2000T1000!#002P2000T1000!#003P0850T1000!#004P1500T1000!#005P1500T1000!}")

    try:
        while not stop_event.is_set():
            try:
                line = input("km1> ")
            except EOFError:
                break
            cmd = line.strip()
            if cmd.lower() in {"q", "quit", "exit"}:
                break
            if not cmd:
                continue
            payload = cmd.encode("ascii") + ending
            ser.write(payload)
            ser.flush()
            print(f"[tx] {cmd}")
    except KeyboardInterrupt:
        print()
    finally:
        stop_event.set()
        time.sleep(0.1)
        ser.close()
        print("closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
