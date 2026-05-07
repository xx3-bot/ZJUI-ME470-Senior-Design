"""iPhone Continuity Camera 封装。

通过 cv2.VideoCapture(config.RGB_CAMERA_INDEX) 打开 iPhone 相机，
对外提供 read_frame() 返回 BGR ndarray。
保持单例懒加载，避免多次打开/释放设备。
"""

from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

import config


class CameraError(RuntimeError):
    """相机打开失败或读帧失败时抛出。"""


class RGBCamera:
    """iPhone 相机的简单封装。"""

    _instance: Optional["RGBCamera"] = None

    def __init__(self, camera_index: int, width: int, height: int) -> None:
        self._camera_index = camera_index
        self._width = width
        self._height = height
        self._cap: Optional[cv2.VideoCapture] = None

    @classmethod
    def instance(cls) -> "RGBCamera":
        if cls._instance is None:
            cls._instance = cls(
                camera_index=config.RGB_CAMERA_INDEX,
                width=config.RGB_FRAME_WIDTH,
                height=config.RGB_FRAME_HEIGHT,
            )
        return cls._instance

    def open(self) -> None:
        if self._cap is not None and self._cap.isOpened():
            return
        cap = cv2.VideoCapture(self._camera_index)
        if not cap.isOpened():
            raise CameraError(f"无法打开摄像头 index={self._camera_index}")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap = cap

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
