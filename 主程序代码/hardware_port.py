"""Serial port discovery helpers for the KM1 arm controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


AUTO_PORT = "auto"

_USB_SERIAL_HINTS = (
    "ch340",
    "ch341",
    "wch",
    "cp210",
    "silicon labs",
    "usb serial",
    "usb2.0-serial",
    "uart",
    "ft232",
    "ftdi",
    "esp32",
)

_AVOID_HINTS = (
    "bluetooth",
    "debug-console",
    "wireless",
    "iphone",
    "ipad",
)


@dataclass(frozen=True)
class SerialPortCandidate:
    device: str
    description: str
    manufacturer: str
    hwid: str
    score: int


def _list_ports() -> list[SerialPortCandidate]:
    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "pyserial is required for automatic hardware port detection. "
            "Install it in this environment first."
        ) from exc

    candidates: list[SerialPortCandidate] = []
    for port in list_ports.comports():
        description = port.description or ""
        manufacturer = port.manufacturer or ""
        hwid = port.hwid or ""
        searchable = " ".join((port.device, description, manufacturer, hwid)).lower()
        score = 0
        if "/dev/cu." in port.device:
            score += 3
        if "/dev/ttyusb" in port.device.lower() or "/dev/ttyacm" in port.device.lower():
            score += 3
        if any(hint in searchable for hint in _USB_SERIAL_HINTS):
            score += 8
        if "usb" in searchable:
            score += 2
        if any(hint in searchable for hint in _AVOID_HINTS):
            score -= 20
        candidates.append(
            SerialPortCandidate(
                device=port.device,
                description=description,
                manufacturer=manufacturer,
                hwid=hwid,
                score=score,
            )
        )
    return sorted(candidates, key=lambda item: (-item.score, item.device))


def format_candidates(candidates: Iterable[SerialPortCandidate]) -> str:
    lines = []
    for candidate in candidates:
        lines.append(
            f"- {candidate.device} | score={candidate.score} | "
            f"{candidate.description} | {candidate.manufacturer} | {candidate.hwid}"
        )
    return "\n".join(lines) if lines else "- <none>"


def resolve_hardware_port(port: str) -> str:
    """Resolve 'auto' into the best available serial device path."""
    if port and port != AUTO_PORT:
        return port

    candidates = _list_ports()
    usable = [candidate for candidate in candidates if candidate.score > 0]
    if not usable:
        raise RuntimeError(
            "No likely KM1 arm serial port was found.\n"
            "Detected serial ports:\n"
            f"{format_candidates(candidates)}\n"
            "Connect the controller board, then retry or pass --hardware-port /dev/..."
        )

    selected = usable[0]
    print("[PORT] Auto-detected hardware serial port:")
    print(
        f"[PORT] {selected.device} | {selected.description} | "
        f"{selected.manufacturer} | {selected.hwid}"
    )
    if len(usable) > 1:
        print("[PORT] Other serial candidates:")
        print(format_candidates(usable[1:]))
    return selected.device
