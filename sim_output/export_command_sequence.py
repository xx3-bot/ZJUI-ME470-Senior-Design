"""Export the latest simulated command sequence as vendor serial commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_LOG_PATH = Path(__file__).resolve().parent / "sim_output.log"
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent / "hardware_command_sequence.txt"
DEFAULT_HOME_COMMAND = "{#000P1500T1500!#001P2000T1500!#002P2000T1500!#003P0850T1500!#004P1500T1500!#005P1500T1500!}"


def _load_records(log_path: Path) -> list[dict]:
    records: list[dict] = []
    if not log_path.exists():
        return records
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _latest_session_id(records: list[dict]) -> str | None:
    for record in reversed(records):
        session_id = record.get("session_id")
        if session_id:
            return session_id
    return None


def export_commands(
    log_path: Path,
    output_path: Path,
    session_id: str | None = None,
    append_home: bool = True,
) -> list[str]:
    """Write command strings from one log session to a plain text file."""
    records = _load_records(log_path)
    selected_session_id = session_id or _latest_session_id(records)
    if selected_session_id is None:
        raise SystemExit(f"No session records found in {log_path}")

    commands: list[str] = []
    for record in records:
        if record.get("session_id") != selected_session_id:
            continue
        call_type = record.get("call_type")
        if call_type not in {"move_to", "gripper_command"}:
            continue
        output = record.get("output") or {}
        if call_type == "move_to" and not output.get("reachable"):
            continue
        if call_type == "gripper_command" and not output.get("result"):
            continue
        command = output.get("command")
        if command:
            commands.append(command)

    if append_home and (not commands or commands[-1] != DEFAULT_HOME_COMMAND):
        commands.append(DEFAULT_HOME_COMMAND)

    if not commands:
        raise SystemExit(f"No exportable commands found for session {selected_session_id}")

    output_path.write_text("\n".join(commands) + "\n", encoding="utf-8")
    return commands


def main() -> None:
    parser = argparse.ArgumentParser(description="Export vendor serial commands from sim_output.log.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--session-id", help="Optional session id. Defaults to the latest session.")
    parser.add_argument(
        "--no-append-home",
        action="store_true",
        help="Do not append the documented raw PWM startup-straight/home command after the exported sequence.",
    )
    args = parser.parse_args()

    commands = export_commands(args.log, args.out, args.session_id, append_home=not args.no_append_home)
    print(f"Exported {len(commands)} commands to {args.out}")
    for index, command in enumerate(commands, start=1):
        print(f"{index:02d}: {command}")


if __name__ == "__main__":
    main()
