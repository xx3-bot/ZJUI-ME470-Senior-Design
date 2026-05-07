"""JSON Lines logger for sim_output operations."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class SimLogger:
    """Thread-safe JSON Lines logger for simulation operations."""

    def __init__(self, log_path: Path | str) -> None:
        """Initialize logger with output file path."""
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # Session ID for grouping related operations
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def log_move_to(
        self,
        current_pose: tuple[float, float, float],
        target_pose: tuple[float, float, float],
        reachable: bool,
        reason: str | None = None,
        joint_angles: tuple[float, ...] | None = None,
        servo_pwm: tuple[int, ...] | None = None,
        command: str | None = None,
        book_position: tuple[float, float, float] | None = None,
        error_code: int | None = None,
        selection_cost: float | None = None,
        cost_breakdown: dict[str, float] | None = None,
    ) -> None:
        """Log a move_to operation."""
        record = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "session_id": self.session_id,
            "call_type": "move_to",
            "input": {
                "current_pose": current_pose,
                "target_pose": target_pose,
            },
            "book_position": {
                "x": book_position[0],
                "y": book_position[1],
                "z": book_position[2],
            }
            if book_position is not None
            else None,
            "output": {
                "reachable": reachable,
                "reason": reason,
                "joint_angles_deg": joint_angles,
                "servo_pwm": servo_pwm,
                "command": command,
                "error_code": error_code,
                "selection_cost": selection_cost,
                "cost_breakdown": cost_breakdown,
            },
        }
        self._write_record(record)

    def log_gripper_command(
        self,
        command: str,
        result: bool,
        message: str | None = None,
        servo_id: int | None = None,
        servo_pwm: int | None = None,
        command_string: str | None = None,
    ) -> None:
        """Log a gripper_command operation."""
        record = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "session_id": self.session_id,
            "call_type": "gripper_command",
            "input": {
                "command": command,
            },
            "output": {
                "result": result,
                "message": message,
                "servo_id": servo_id,
                "servo_pwm": servo_pwm,
                "command": command_string,
            },
        }
        self._write_record(record)

    def log_event(self, event_type: str, details: Dict[str, Any] | None = None) -> None:
        """Log a generic event such as configuration or session metadata."""
        record = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "session_id": self.session_id,
            "call_type": event_type,
            "details": details,
        }
        self._write_record(record)

    def _write_record(self, record: Dict[str, Any]) -> None:
        """Write a single JSON record to the log file (thread-safe)."""
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def get_session_id(self) -> str:
        """Get the current session ID."""
        return self.session_id
