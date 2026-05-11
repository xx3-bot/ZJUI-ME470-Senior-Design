"""RGB camera wrapper.

通过 cv2.VideoCapture 打开 RGB 相机，对外提供 read_frame() 返回 BGR ndarray。
config.RGB_CAMERA_INDEX 可设为整数 index，或 "auto" 自动选择第一个可读相机。
保持单例懒加载，避免多次打开/释放设备。
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import cv2
import numpy as np

import config


class CameraError(RuntimeError):
    """相机打开失败或读帧失败时抛出。"""


class RGBCamera:
    """RGB 相机的简单封装。"""

    _instance: Optional["RGBCamera"] = None

    def __init__(self, camera_index: int | str, width: int, height: int) -> None:
        self._camera_index = camera_index
        self._width = width
        self._height = height
        self._cap: Optional[cv2.VideoCapture] = None
        self._resolved_camera_index: Optional[int] = None

    @classmethod
    def instance(cls) -> "RGBCamera":
        if cls._instance is None:
            camera_index = os.environ.get("ME470_RGB_CAMERA_INDEX", config.RGB_CAMERA_INDEX)
            cls._instance = cls(
                camera_index=camera_index,
                width=config.RGB_FRAME_WIDTH,
                height=config.RGB_FRAME_HEIGHT,
            )
        return cls._instance

    def open(self) -> None:
        if self._cap is not None and self._cap.isOpened():
            return
        index = self._resolve_camera_index()
        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            raise CameraError(f"无法打开摄像头 index={index}")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap = cap

    def _resolve_camera_index(self) -> int:
        if self._resolved_camera_index is not None:
            return self._resolved_camera_index
        if isinstance(self._camera_index, int):
            self._resolved_camera_index = self._camera_index
            return self._resolved_camera_index
        if str(self._camera_index).lower() != "auto":
            try:
                self._resolved_camera_index = int(self._camera_index)
                return self._resolved_camera_index
            except ValueError as exc:
                raise CameraError(
                    f"未知 RGB_CAMERA_INDEX={self._camera_index!r}，请使用整数或 'auto'"
                ) from exc

        candidates = probe_camera_indices()
        if not candidates:
            raise CameraError("未检测到可打开且可读帧的 RGB 相机")
        self._resolved_camera_index = _choose_camera_index(candidates)
        selected = next(
            (candidate for candidate in candidates if candidate[0] == self._resolved_camera_index),
            candidates[0],
        )
        print(
            f"[CAMERA] Auto-selected camera index {self._resolved_camera_index} "
            f"({selected[1]}x{selected[2]})"
        )
        if len(candidates) > 1:
            print(
                "[CAMERA] Readable camera candidates: "
                + ", ".join(f"{idx}({w}x{h})" for idx, w, h in candidates)
            )
        return self._resolved_camera_index

    def read_frame(self) -> np.ndarray:
        """读一帧 BGR 图像；失败时抛 CameraError。"""
        if self._cap is None or not self._cap.isOpened():
            self.open()
        assert self._cap is not None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise CameraError("从相机读取画面失败")
        return frame

    @property
    def frame_size(self) -> Tuple[int, int]:
        """实际协商出来的分辨率 (width, height)。"""
        if self._cap is None:
            self.open()
        assert self._cap is not None
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (w, h)

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


def probe_camera_indices(max_index: int = 5) -> list[tuple[int, int, int]]:
    """Return readable camera indices as (index, width, height)."""
    candidates: list[tuple[int, int, int]] = []
    for index in range(max_index + 1):
        cap = cv2.VideoCapture(index)
        try:
            if not cap.isOpened():
                continue
            ok, frame = cap.read()
            if not ok or frame is None or frame.size == 0:
                continue
            h, w = frame.shape[:2]
            candidates.append((index, int(w), int(h)))
        finally:
            cap.release()
    return candidates


def _preferred_index_order() -> list[int]:
    raw = os.environ.get("ME470_RGB_CAMERA_INDEX_ORDER", "")
    order: list[int] = []
    for part in raw.replace(";", ",").split(","):
        value = part.strip()
        if not value:
            continue
        try:
            order.append(int(value))
        except ValueError:
            print(f"[CAMERA] Ignoring invalid ME470_RGB_CAMERA_INDEX_ORDER item: {value!r}")
    return order


def _choose_camera_index(candidates: list[tuple[int, int, int]]) -> int:
    """Choose a camera index, allowing the lab setup to prefer external cameras.

    macOS/OpenCV does not reliably expose device names for AVFoundation indices.
    In this project the built-in/Continuity camera often appears as index 0,
    while the external USB camera may be 1 or 2. The env var lets us encode the
    physically verified order without hard-coding it for every machine.
    """
    available = {index for index, _w, _h in candidates}
    for index in _preferred_index_order():
        if index in available:
            return index
    return candidates[0][0]
