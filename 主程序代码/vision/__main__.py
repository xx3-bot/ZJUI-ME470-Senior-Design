"""L2 实时相机验证：python -m vision

打开 iPhone 相机（config.RGB_CAMERA_INDEX）。三条线程：
- _FrameReader：循环读相机，把缓冲一直抽干，存最新一帧
- _AsyncSpineDetector：拿 worker 自取最新帧跑 OCR，结果回写
- 主线程：取最新帧 + 最新 hits → 画 → cv2.imshow

按键：
- SPACE：保存当前帧的原图 + 可视化图到 vision/captures/
- q：退出
"""

from __future__ import annotations

import os

# 限制 Paddle/MKL 占核，给主线程和 reader 留出 CPU。必须在 import paddle 前设置。
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")

import threading
import time
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from .bin_scanner import _hit_to_book_dict
from .camera import CameraError, RGBCamera
from .spine_detector import SpineDetector, SpineHit
from .visual_overlay import draw_hits


def _captures_dir() -> Path:
    p = Path(__file__).resolve().parent / "captures"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_frame(raw: np.ndarray, annotated: np.ndarray, hits: List[SpineHit]) -> None:
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = _captures_dir()
    raw_path = out_dir / f"live_{ts}_raw.jpg"
    ann_path = out_dir / f"live_{ts}_annotated.jpg"
    cv2.imwrite(str(raw_path), raw)
    cv2.imwrite(str(ann_path), annotated)
    print(f"[L2] saved -> {raw_path.name}, {ann_path.name}")
    if hits:
        h, w = raw.shape[:2]
        for i, hit in enumerate(hits):
            print(f"  dict[{i}] = {_hit_to_book_dict(hit, (w, h))}")


class _FrameReader(threading.Thread):
    """循环读相机，把内部 buffer 抽干，只保留最新一帧。

    macOS AVFoundation backend 会缓冲 3-4 帧，主线程一旦慢一拍就拿到旧帧，
    视觉效果就是"卡顿 + 跳帧"。这个线程不停 read 把缓冲冲掉。
    """

    def __init__(self, cam: RGBCamera) -> None:
        super().__init__(daemon=True)
        self._cam = cam
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._stop = False
        self._error: Optional[str] = None

    def latest(self) -> Optional[np.ndarray]:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self) -> None:
        self._stop = True

    @property
    def error(self) -> Optional[str]:
        return self._error

    def run(self) -> None:
        while not self._stop:
            try:
                frame = self._cam.read_frame()
            except CameraError as exc:
                self._error = str(exc)
                return
            with self._lock:
                self._frame = frame


class _AsyncSpineDetector(threading.Thread):
    """后台线程跑 OCR；主线程通过 submit/get_hits 通信，不会被阻塞。"""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._detector = SpineDetector.instance()
        self._lock = threading.Lock()
        self._pending_frame: Optional[np.ndarray] = None
        self._latest_hits: List[SpineHit] = []
        self._busy = False
        self._stop = False
        self._wake = threading.Event()

    def submit(self, frame: np.ndarray) -> None:
        """主线程调用：丢一帧给 worker 跑 OCR。worker 忙就直接丢弃。"""
        with self._lock:
            if self._busy:
                return
            self._pending_frame = frame.copy()
            self._busy = True
        self._wake.set()

    def get_hits(self) -> List[SpineHit]:
        with self._lock:
            return list(self._latest_hits)

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def run(self) -> None:
        while not self._stop:
            self._wake.wait(timeout=0.5)
            self._wake.clear()
            with self._lock:
                frame = self._pending_frame
                self._pending_frame = None
            if frame is None:
                with self._lock:
                    self._busy = False
                continue
            try:
                hits = self._detector.detect(frame)
            except Exception as exc:
                print(f"[L2 worker] detect failed: {exc}")
                hits = []
            with self._lock:
                self._latest_hits = hits
                self._busy = False


def main() -> None:
    cam = RGBCamera.instance()
    try:
        cam.open()
    except CameraError as exc:
        print(f"[L2] 相机打不开: {exc}")
        return

    reader = _FrameReader(cam)
    reader.start()
    worker = _AsyncSpineDetector()
    worker.start()

    print("[L2] 按 SPACE 保存当前帧；按 q 退出。")

    try:
        while True:
            if reader.error:
                print(f"[L2] 读帧失败: {reader.error}")
                break
            frame = reader.latest()
            if frame is None:
                time.sleep(0.01)
                continue

            worker.submit(frame)
            hits = worker.get_hits()
            annotated = draw_hits(frame, hits)
            cv2.imshow("vision live (SPACE=save, q=quit)", annotated)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == 32:  # SPACE
                _save_frame(frame, annotated, hits)
    finally:
        reader.stop()
        worker.stop()
        cam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
