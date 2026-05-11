"""Probe OpenCV camera indices and save one snapshot per readable camera.

Usage from 主程序代码/:
    ../.venv/bin/python -m vision.camera_probe

Optional:
    ME470_RGB_CAMERA_INDEX_ORDER=1,2,0 ../.venv/bin/python -m vision.camera_probe
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2

from .camera import _choose_camera_index, probe_camera_indices


def _output_dir() -> Path:
    path = Path(__file__).resolve().parent / "captures" / (
        "camera_probe_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_snapshot(index: int, output_dir: Path) -> Path | None:
    cap = cv2.VideoCapture(index)
    try:
        if not cap.isOpened():
            return None
        ok, frame = cap.read()
        if not ok or frame is None or frame.size == 0:
            return None
        path = output_dir / f"camera_index_{index}.jpg"
        if not cv2.imwrite(str(path), frame):
            return None
        return path
    finally:
        cap.release()


def main() -> None:
    candidates = probe_camera_indices()
    print("[CAMERA-PROBE] readable candidates:")
    if not candidates:
        print("  <none>")
        return
    selected = _choose_camera_index(candidates)
    for index, width, height in candidates:
        marker = " <-- selected" if index == selected else ""
        print(f"  index {index}: {width}x{height}{marker}")

    output_dir = _output_dir()
    print(f"[CAMERA-PROBE] saving snapshots to: {output_dir}")
    for index, _width, _height in candidates:
        path = _save_snapshot(index, output_dir)
        print(f"  index {index}: {path if path is not None else 'snapshot failed'}")


if __name__ == "__main__":
    main()
