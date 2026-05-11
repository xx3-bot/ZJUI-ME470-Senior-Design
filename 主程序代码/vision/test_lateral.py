"""离线测试 lateral_pose_provider。

输出 arm-frame 横向坐标 Y（mm），以及完整 pick_pose (X, Y, Z)，
喂给机械同学手动复现抓书测试。

用法（在 主程序代码/ 目录下，先 conda activate ece445）：

    # 测试单张图，title 取 KNOWN_BOOK_TITLES[0]
    python -m vision.test_lateral --image vision/test_images/foo.jpg

    # 指定 title
    python -m vision.test_lateral --image vision/test_images/foo.jpg --title "羊皮卷"

    # 同时给真实横向 Y（书放在 bin 中心 = arm-Y 0），自动算误差
    python -m vision.test_lateral --image vision/test_images/foo.jpg --truth-y 0.0

    # 跑整个目录
    python -m vision.test_lateral --image-dir vision/test_images/

输出可视化图存 vision/captures/lateral_<时间戳>_<原文件名>.jpg：
- 红框 = OCR bbox
- 黄点 + 黄竖线 = bbox 中心（用来算横向 Y 的像素列）
- 文字 = arm_y_mm
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
from PIL import Image, ImageOps

import config

from .lateral_pose_provider import get_book_arm_y_mm, get_book_pick_pose
from .spine_detector import SpineDetector


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def _load_image_with_exif(image_path: Path) -> Optional[np.ndarray]:
    """PIL + EXIF 矫正 → BGR ndarray。iPhone 横屏图必须这样读。"""
    try:
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            rgb = np.array(img.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception as exc:
        print(f"  ! PIL 读图失败 ({exc})，回退 cv2.imread")
        return cv2.imread(str(image_path))


def _annotate_and_save(
    frame: np.ndarray, title: str, arm_y_mm: Optional[float], out_path: Path,
) -> None:
    """在原图上画 bbox + 中心点 + arm_y 数值，存到 out_path."""
    annotated = frame.copy()
    hits = SpineDetector.instance().detect(frame)
    matching = [h for h in hits if h.matched_title == title]
    if matching:
        hit = max(matching, key=lambda h: h.ocr_score)
        x1, y1, x2, y2 = hit.bbox
        cu = int((x1 + x2) / 2)
        cv = int((y1 + y2) / 2)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.circle(annotated, (cu, cv), 8, (0, 255, 255), -1)
        cv2.line(annotated, (cu, 0), (cu, annotated.shape[0]), (0, 255, 255), 1)
        text = (
            f"{title}  arm_y={arm_y_mm:+.1f}mm"
            if arm_y_mm is not None else f"{title}  arm_y=?"
        )
        cv2.putText(
            annotated, text, (max(10, x1), max(30, y1 - 12)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA,
        )
    else:
        cv2.putText(
            annotated, f"NO HIT for {title!r}", (20, 50),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2, cv2.LINE_AA,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), annotated)


def _process_one(
    image_path: Path, title: str, truth_y_mm: Optional[float], out_dir: Path,
) -> None:
    print("\n" + "=" * 70)
    print(f"[{image_path.name}]  title={title!r}")
    frame = _load_image_with_exif(image_path)
    if frame is None:
        print("  X 读图失败")
        return
    h, w = frame.shape[:2]
    print(f"  loaded shape: {h}x{w} (HxW)")

    arm_y = get_book_arm_y_mm(frame, title)
    pose = get_book_pick_pose(frame, title)  # 二次调用很轻；OCR 已在前一次跑过

    if arm_y is None:
        print("  → arm_y = None")
    elif truth_y_mm is not None:
        err = arm_y - truth_y_mm
        print(
            f"  → arm_y = {arm_y:+8.1f} mm  | truth = {truth_y_mm:+.1f} | "
            f"err = {err:+.1f} mm"
        )
    else:
        print(f"  → arm_y = {arm_y:+8.1f} mm")

    if pose is not None:
        print(
            f"  → pick_pose = ({pose[0]:+.1f}, {pose[1]:+.1f}, {pose[2]:+.1f}) mm "
            f"  [给机械同学直接喂这个]"
        )

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"lateral_{ts}_{image_path.stem}.jpg"
    _annotate_and_save(frame, title, arm_y, out_path)
    print(f"  annotated saved: {out_path.relative_to(out_dir.parent)}")


def _list_images(image_dir: Path) -> List[Path]:
    if not image_dir.is_dir():
        return []
    return sorted(p for p in image_dir.iterdir() if p.suffix.lower() in _IMAGE_EXTS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, help="单张图路径；优先于 --image-dir")
    parser.add_argument(
        "--image-dir", type=Path,
        default=Path(__file__).resolve().parent / "test_images",
        help="批量目录（默认 vision/test_images/）",
    )
    parser.add_argument(
        "--title", type=str, default=None,
        help="目标书名（默认取 config.KNOWN_BOOK_TITLES[0]）",
    )
    parser.add_argument(
        "--truth-y", type=float, default=None,
        help="（可选）真实横向 arm-Y mm，给了就自动算误差",
    )
    args = parser.parse_args()

    title = args.title or (
        config.KNOWN_BOOK_TITLES[0] if config.KNOWN_BOOK_TITLES else ""
    )
    if not title:
        print("错误：title 为空，且 config.KNOWN_BOOK_TITLES 也是空的")
        return

    out_dir = Path(__file__).resolve().parent / "captures"

    print("=== test_lateral ===")
    print(f"intrinsics: fx={config.RGB_INTRINSICS_FX_PX} cx={config.RGB_INTRINSICS_CX_PX}")
    print(f"CAMERA_POSITION_IN_ARM_MM    = {config.CAMERA_POSITION_IN_ARM_MM}")
    print(f"BIN_PICK_DEPTH_MM (arm X)    = {config.BIN_PICK_DEPTH_MM}")
    print(f"BIN_PICK_GRASP_HEIGHT_MM (Z) = {config.BIN_PICK_GRASP_HEIGHT_MM}")
    print(f"BIN_FIXED_DEPTH_MM (cam Z)   = {config.BIN_FIXED_DEPTH_MM}  [= pick_depth − cam_x]")
    print(f"CAMERA_Y_OFFSET_MM           = {config.CAMERA_Y_OFFSET_MM}")
    print(f"CAMERA_PIXEL_TO_ARM_Y_SIGN   = {config.CAMERA_PIXEL_TO_ARM_Y_SIGN}")
    print(f"target title                 = {title!r}")

    if args.image is not None:
        _process_one(args.image, title, args.truth_y, out_dir)
        return

    images = _list_images(args.image_dir)
    if not images:
        print(f"\n[NOTE] {args.image_dir} 下没有图")
        return
    print(f"\nProcessing {len(images)} images from {args.image_dir}")
    for image_path in images:
        try:
            _process_one(image_path, title, args.truth_y, out_dir)
        except Exception as exc:  # noqa: BLE001 — 离线测试，宁愿继续而不是中断
            print(f"  X 处理出错: {exc}")


if __name__ == "__main__":
    main()
