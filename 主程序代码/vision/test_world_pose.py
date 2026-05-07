"""离线测试：把图像文件喂进视觉 pipeline，输出世界系 (x, y, z) mm。

用法（在 主程序代码/ 目录下）：

    # 跑 vision/test_images/ 下所有图，title 取 KNOWN_BOOK_TITLES[0]
    python -m vision.test_world_pose

    # 跑指定单张图
    python -m vision.test_world_pose --image vision/test_images/IMG_8010.jpeg

    # 指定其他 title
    python -m vision.test_world_pose --title "其它书名"

⚠️ 用 iPhone 照片测试时，相机内参（fx/fy/cx/cy）和外参（CAMERA_TRANSLATION_MM）
都仍是 C920e 的占位值，所以输出的 world (x, y, z) 数值**不是物理真值**。
本工具的目的是验证：
1. pipeline 能在真实图像上端到端跑通
2. 输出量级合理（不是 NaN、None 或荒谬数字）
3. 不同图给出不同 pose（书的位置/距离不同，pose 应不同）
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
from PIL import Image, ImageOps

import config

from .world_pose_provider import get_pick_world_pose_from_frame


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def _load_image_with_exif(image_path: Path) -> Optional[np.ndarray]:
    """PIL 读图 + EXIF 旋转 → BGR ndarray。iPhone 横屏拍的图必须这样读。"""
    try:
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            rgb = np.array(img.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception as exc:
        print(f"  ! PIL 读图失败 ({exc})，回退 cv2.imread")
        return cv2.imread(str(image_path))


def _process_one(image_path: Path, title: str) -> None:
    print("\n" + "=" * 64)
    print(f"[{image_path.name}]  title={title!r}")
    frame = _load_image_with_exif(image_path)
    if frame is None:
        print("  X 读图失败")
        return
    h, w = frame.shape[:2]
    print(f"  loaded shape: {h}x{w} (HxW)")

    pose = get_pick_world_pose_from_frame(frame, title)
    if pose is None:
        print("  X pose=None  (OCR 未命中目标或 pipeline 失败)")
        return
    print(
        f"  OK world_pose = ({pose[0]:+8.1f}, {pose[1]:+8.1f}, {pose[2]:+8.1f}) mm"
    )


def _list_images(image_dir: Path) -> List[Path]:
    if not image_dir.is_dir():
        return []
    return sorted(p for p in image_dir.iterdir() if p.suffix.lower() in _IMAGE_EXTS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", type=Path, help="single image path; overrides --image-dir"
    )
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "test_images",
        help="directory of images to process (default: vision/test_images/)",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="target title (default: config.KNOWN_BOOK_TITLES[0])",
    )
    args = parser.parse_args()

    title = args.title or (
        config.KNOWN_BOOK_TITLES[0] if config.KNOWN_BOOK_TITLES else ""
    )
    if not title:
        print("错误：title 为空且 config.KNOWN_BOOK_TITLES 也是空")
        return

    print("=== test_world_pose ===")
    print(
        f"camera intrinsics: fx={config.RGB_INTRINSICS_FX_PX} "
        f"fy={config.RGB_INTRINSICS_FY_PX} "
        f"cx={config.RGB_INTRINSICS_CX_PX} "
        f"cy={config.RGB_INTRINSICS_CY_PX}"
    )
    print(
        f"camera extrinsics: t={config.CAMERA_TRANSLATION_MM} "
        f"orientation={config.CAMERA_ORIENTATION_MODE}"
    )
    book_spine_h = config.KNOWN_BOOK_DIMENSIONS_MM.get(title, {}).get("spine_height")
    print(f"book spine_height: {book_spine_h} mm")
    print(f"OCR_TO_REAL_HEIGHT_RATIO: {config.OCR_TO_REAL_HEIGHT_RATIO}")

    if args.image is not None:
        _process_one(args.image, title)
        return

    images = _list_images(args.image_dir)
    if not images:
        print(f"\n[NOTE] {args.image_dir} 下没有图")
        return
    print(f"\nProcessing {len(images)} images from {args.image_dir}")
    for image_path in images:
        try:
            _process_one(image_path, title)
        except Exception as exc:
            print(f"  X 处理出错: {exc}")


if __name__ == "__main__":
    main()
