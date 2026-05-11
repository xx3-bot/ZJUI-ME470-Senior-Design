"""C920e 内参标定工具：采集棋盘格图 + 跑 OpenCV calibrateCamera。

两个子命令：

    # 1) 采集 25 张棋盘格图。锁焦 + 实时角点检测 overlay。
    python -m vision.calibrate_intrinsics capture --num 25

    # 2) 标定。读全部图，跑 cv2.calibrateCamera 出 fx/fy/cx/cy + 畸变。
    python -m vision.calibrate_intrinsics solve --square-size-mm 25.0

棋盘格规格（默认与 calib.io PDF 一致）：
    9×6 内角点（即 10×7 个方格）
    25.0 mm 方格边长

输出：
    vision/calibration_images/  ← 采集到的 JPG
    vision/intrinsics_calibration.json  ← 标定结果
    控制台同时打印一段可直接粘进 config.py 的代码
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

import config


_DEFAULT_PATTERN = (9, 6)
_DEFAULT_SQUARE_MM = 25.0
_DEFAULT_DIR = Path(__file__).resolve().parent / "calibration_images"
_DEFAULT_JSON = Path(__file__).resolve().parent / "intrinsics_calibration.json"


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def _open_camera() -> cv2.VideoCapture:
    from .camera import probe_camera_indices

    camera_index = os.environ.get("ME470_RGB_CAMERA_INDEX", config.RGB_CAMERA_INDEX)
    if str(camera_index).lower() == "auto":
        candidates = probe_camera_indices()
        if not candidates:
            raise RuntimeError("无法自动检测到可读相机。检查 C920e 是否连接。")
        camera_index = candidates[0][0]
        print(f"[CAL] Auto-selected camera index {camera_index}")
    cap = cv2.VideoCapture(int(camera_index))
    if not cap.isOpened():
        raise RuntimeError(
            f"无法打开摄像头 index={camera_index}。检查 C920e 是否连接。"
        )
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.RGB_FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.RGB_FRAME_HEIGHT)
    return cap


def _lock_focus(cap: cv2.VideoCapture, focus_value: int) -> None:
    """锁定 C920e 自动对焦，避免标定中焦距漂动。"""
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
    cap.set(cv2.CAP_PROP_FOCUS, focus_value)
    af = cap.get(cv2.CAP_PROP_AUTOFOCUS)
    f = cap.get(cv2.CAP_PROP_FOCUS)
    print(f"[CAL] AUTOFOCUS={af}  FOCUS={f}（要求 0 / {focus_value}）")
    if af != 0:
        print("[CAL] 警告：macOS 上 CAP_PROP_AUTOFOCUS 偶发不生效；继续，但标定可能漂")


def _draw_chessboard_overlay(
    frame: np.ndarray, pattern: Tuple[int, int]
) -> Tuple[np.ndarray, bool]:
    """在画面上画棋盘格角点 overlay；返回（标注后帧, 是否检测到完整角点）。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCornersSB(
        gray, pattern, flags=cv2.CALIB_CB_NORMALIZE_IMAGE
    )
    annotated = frame.copy()
    if found:
        cv2.drawChessboardCorners(annotated, pattern, corners, found)
        cv2.putText(
            annotated, "OK - press SPACE to save",
            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 220, 0), 2
        )
    else:
        cv2.putText(
            annotated, "no chessboard - move/tilt board",
            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 220), 2
        )
    return annotated, found


def _next_image_path(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(out_dir.glob("calib_*.jpg"))
    n = len(existing)
    return out_dir / f"calib_{n:03d}.jpg"


def cmd_capture(args: argparse.Namespace) -> None:
    pattern = tuple(int(x) for x in args.pattern.lower().split("x"))
    if len(pattern) != 2:
        raise SystemExit(f"--pattern 格式错误：{args.pattern}，应该形如 9x6")

    cap = _open_camera()
    _lock_focus(cap, args.focus)

    target_count = args.num
    saved = sum(1 for _ in args.output_dir.glob("calib_*.jpg")) if args.output_dir.is_dir() else 0
    print(f"[CAL] 已有 {saved} 张；目标 {target_count} 张")
    print("[CAL] 按 SPACE 保存当前帧；q 退出。绿框 = 角点检测到了，可以保存")

    try:
        while saved < target_count:
            ok, frame = cap.read()
            if not ok:
                print("[CAL] 读帧失败")
                break
            annotated, found = _draw_chessboard_overlay(frame, pattern)
            cv2.putText(
                annotated, f"saved {saved}/{target_count}",
                (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2
            )
            cv2.imshow("calibrate (SPACE=save, q=quit)", annotated)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == 32:  # SPACE
                if not found and not args.force:
                    print("[CAL] 这帧没找到完整角点，跳过（加 --force 强制保存）")
                    continue
                path = _next_image_path(args.output_dir)
                cv2.imwrite(str(path), frame)
                saved += 1
                print(f"[CAL] saved -> {path.name}  ({saved}/{target_count})")
    finally:
        cap.release()
        cv2.destroyAllWindows()
    print(f"[CAL] capture 完成，{saved} 张图在 {args.output_dir}")


# ---------------------------------------------------------------------------
# Solve
# ---------------------------------------------------------------------------


def _build_object_points(pattern: Tuple[int, int]) -> np.ndarray:
    cols, rows = pattern
    obj = np.zeros((cols * rows, 3), np.float32)
    obj[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    return obj


def _gather_corners(
    image_dir: Path, pattern: Tuple[int, int]
) -> Tuple[List[np.ndarray], List[np.ndarray], Tuple[int, int], List[Path]]:
    image_paths = sorted(image_dir.glob("*.jpg")) + sorted(image_dir.glob("*.jpeg"))
    if not image_paths:
        raise SystemExit(f"{image_dir} 下没有 .jpg/.jpeg")

    obj_pts_all: List[np.ndarray] = []
    img_pts_all: List[np.ndarray] = []
    used_paths: List[Path] = []
    image_size: Optional[Tuple[int, int]] = None
    obj = _build_object_points(pattern)

    for path in image_paths:
        frame = cv2.imread(str(path))
        if frame is None:
            print(f"[CAL] {path.name}: 读不出来，跳过")
            continue
        if image_size is None:
            image_size = (frame.shape[1], frame.shape[0])
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCornersSB(
            gray, pattern, flags=cv2.CALIB_CB_NORMALIZE_IMAGE
        )
        if not found:
            print(f"[CAL] {path.name}: 没找到角点，跳过")
            continue
        obj_pts_all.append(obj.copy())
        img_pts_all.append(corners)
        used_paths.append(path)

    print(f"[CAL] 用到 {len(used_paths)}/{len(image_paths)} 张图")
    if image_size is None:
        raise SystemExit("一张能用的图都没有，标定终止")
    return obj_pts_all, img_pts_all, image_size, used_paths


def cmd_solve(args: argparse.Namespace) -> None:
    pattern = tuple(int(x) for x in args.pattern.lower().split("x"))
    if len(pattern) != 2:
        raise SystemExit(f"--pattern 格式错误：{args.pattern}")

    obj_pts_unit, img_pts, image_size, used_paths = _gather_corners(args.input_dir, pattern)
    if len(obj_pts_unit) < 8:
        print(f"[CAL] 警告：只有 {len(obj_pts_unit)} 张可用，建议 >= 15 张")

    obj_pts = [pts * args.square_size_mm for pts in obj_pts_unit]

    print("[CAL] 跑 cv2.calibrateCamera ...")
    rms, K, dist, _, _ = cv2.calibrateCamera(
        obj_pts, img_pts, image_size, None, None,
        flags=0,
    )
    fx, fy = float(K[0, 0]), float(K[1, 1])
    cx, cy = float(K[0, 2]), float(K[1, 2])
    dist = dist.ravel().tolist()

    print()
    print(f"[CAL] images used     : {len(used_paths)}")
    print(f"[CAL] image size      : {image_size[0]} x {image_size[1]}")
    print(f"[CAL] reprojection RMS: {rms:.3f} px  (理想 < 0.5)")
    print(f"[CAL] fx, fy          : {fx:.2f}, {fy:.2f}")
    print(f"[CAL] cx, cy          : {cx:.2f}, {cy:.2f}")
    print(f"[CAL] distortion      : {[round(x, 4) for x in dist]}")

    fx_fy_ratio = abs(fx - fy) / max(fx, fy)
    if fx_fy_ratio > 0.02:
        print(f"[CAL] 警告：fx/fy 差异 {fx_fy_ratio*100:.1f}%（应 <1%），可能没锁焦")
    if rms > 0.5:
        print("[CAL] 警告：reprojection error 偏大；考虑重拍部分图，板要平、角度要多样")

    out = {
        "fx": fx,
        "fy": fy,
        "cx": cx,
        "cy": cy,
        "distortion": dist,
        "reprojection_error_px": float(rms),
        "image_count": len(used_paths),
        "pattern": list(pattern),
        "square_size_mm": float(args.square_size_mm),
        "calibrated_at": datetime.now().isoformat(timespec="seconds"),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\n[CAL] 写入 {args.output_json}")

    print()
    print(">>> 把下面 4 行粘到 config.py 替换原来的估算值：")
    print(f"RGB_INTRINSICS_FX_PX: float = {fx:.2f}")
    print(f"RGB_INTRINSICS_FY_PX: float = {fy:.2f}")
    print(f"RGB_INTRINSICS_CX_PX: float = {cx:.2f}")
    print(f"RGB_INTRINSICS_CY_PX: float = {cy:.2f}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="C920e 内参标定")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_cap = sub.add_parser("capture", help="实时拍棋盘格图")
    p_cap.add_argument("--num", type=int, default=25, help="目标张数（默认 25）")
    p_cap.add_argument("--output-dir", type=Path, default=_DEFAULT_DIR)
    p_cap.add_argument("--pattern", type=str, default="9x6", help="内角点 colsxrows，默认 9x6")
    p_cap.add_argument("--focus", type=int, default=50,
                       help="锁定的对焦值 (0-255)，30cm 工作距用 50 左右；越大焦距越远")
    p_cap.add_argument("--force", action="store_true",
                       help="即使没检测到角点也强制保存（一般不用）")

    p_solve = sub.add_parser("solve", help="跑 calibrateCamera")
    p_solve.add_argument("--input-dir", type=Path, default=_DEFAULT_DIR)
    p_solve.add_argument("--pattern", type=str, default="9x6")
    p_solve.add_argument("--square-size-mm", type=float, default=_DEFAULT_SQUARE_MM)
    p_solve.add_argument("--output-json", type=Path, default=_DEFAULT_JSON)

    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.cmd == "capture":
        cmd_capture(args)
    elif args.cmd == "solve":
        cmd_solve(args)


if __name__ == "__main__":
    main()
