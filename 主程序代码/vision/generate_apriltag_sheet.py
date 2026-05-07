"""生成 AprilTag 图片，方便打印贴到 bin/shelf。

用法：
    python -m vision.generate_apriltag_sheet

会在 vision/apriltag_images/ 下生成：
- tag_00_30mm.png  / tag_01_30mm.png  / tag_02_30mm.png   (shelf 用，3 个)
- tag_10_30mm.png / tag_11_30mm.png                       (bin 用，2 个)
- INSTRUCTIONS.txt 打印 + 贴标说明

打印时：把这 5 张 PNG 放到 Word/Google Docs / 直接 PDF 打印。
关键：**100% 实际尺寸打印**，打印完用尺量 tag 边长应等于 30mm（误差 ±0.5mm 内）。
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

import config


# 打印参数
PRINT_DPI: int = 300                 # 打印精度（普通激光打印够用）
TAG_SIZE_MM: float = 30.0
TAG_QUIET_ZONE_RATIO: float = 0.25   # tag 周围留白宽度 = tag 大小 × 0.25
DICT_NAME_TO_CONST = {
    "DICT_4X4_50":  cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_5X5_50":  cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_6X6_50":  cv2.aruco.DICT_6X6_50,
}

# 要生成的 tag 列表：(id, size_mm, label)
TAGS_TO_GENERATE = [
    (0,  TAG_SIZE_MM, "shelf-left-foot"),
    (1,  TAG_SIZE_MM, "shelf-mid-foot"),
    (2,  TAG_SIZE_MM, "shelf-right-foot"),
    (10, TAG_SIZE_MM, "bin-left"),
    (11, TAG_SIZE_MM, "bin-right"),
]


def mm_to_px(size_mm: float, dpi: int = PRINT_DPI) -> int:
    """物理 mm → 打印像素（按 dpi 算）。"""
    inches = size_mm / 25.4
    return int(round(inches * dpi))


def generate_tag_image(tag_id: int, size_mm: float, dict_name: str) -> np.ndarray:
    """生成单个 tag 图，包含周围留白（quiet zone）。

    Returns: BGR uint8 image. 留白白色，tag 黑白。
    """
    dict_const = DICT_NAME_TO_CONST.get(dict_name, cv2.aruco.DICT_4X4_50)
    aruco_dict = cv2.aruco.getPredefinedDictionary(dict_const)

    tag_px = mm_to_px(size_mm)
    quiet_px = int(round(tag_px * TAG_QUIET_ZONE_RATIO))
    total_px = tag_px + quiet_px * 2

    # 生成 tag（cv2 输出灰度图）
    tag_gray = cv2.aruco.generateImageMarker(aruco_dict, tag_id, tag_px)

    # 加白色周围
    canvas = np.full((total_px, total_px), 255, dtype=np.uint8)
    canvas[quiet_px:quiet_px + tag_px, quiet_px:quiet_px + tag_px] = tag_gray

    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "apriltag_images"
    out_dir.mkdir(parents=True, exist_ok=True)

    dict_name = getattr(config, "APRILTAG_DICT_NAME", "DICT_4X4_50")
    print(f"[GEN] using dictionary: {dict_name}")
    print(f"[GEN] tag size: {TAG_SIZE_MM} mm @ {PRINT_DPI} dpi")
    print(f"[GEN] output dir: {out_dir}")

    for tag_id, size_mm, label in TAGS_TO_GENERATE:
        img = generate_tag_image(tag_id, size_mm, dict_name)
        filename = f"tag_{tag_id:02d}_{int(size_mm)}mm.png"
        out_path = out_dir / filename
        cv2.imwrite(str(out_path), img)
        print(f"[GEN] saved {filename} ({label})")

    instructions = f"""# AprilTag Print + Stick Instructions

Generated tags (DICT_4X4_50, {int(TAG_SIZE_MM)}mm physical size, {PRINT_DPI} dpi):

| File                  | ID | Where to stick                |
|-----------------------|----|-------------------------------|
| tag_00_30mm.png       | 0  | SHELF, left foot, front face  |
| tag_01_30mm.png       | 1  | SHELF, middle foot, front face|
| tag_02_30mm.png       | 2  | SHELF, right foot, front face |
| tag_10_30mm.png       | 10 | BIN,  front-bottom strip, LEFT  |
| tag_11_30mm.png       | 11 | BIN,  front-bottom strip, RIGHT |

## Print steps

1. Open each PNG in Word / Preview / Photoshop / browser.
2. Print at **100% actual size** (do NOT check "fit to page" / "scale to fit").
3. Use **laser printer + matte sticker paper** (avoid inkjet/glossy).
4. After printing, measure with calipers: tag black edge should be **{int(TAG_SIZE_MM)} mm**.
   Tolerance: ±0.5 mm. If off >1mm, re-check print scale settings.

## Stick steps

1. Cut each tag with the white quiet zone left intact (don't trim into the
   white border — AprilTag detection needs at least one tag-cell of white margin).
2. Peel sticker, stick onto **flat clean surface** at the location above.
3. Tag must face the C920e camera; tilt < 30 deg relative to camera axis.
4. After sticking all 5, measure with ruler:
   - Each tag center's offset from the bin/shelf reference point
   - Update `BIN_MODEL["tags"][...]["offset_mm"]` and `SHELF_MODEL["tags"][...]["offset_mm"]`
     in `config.py` with the measured values (replace the TODO placeholders).
"""
    (out_dir / "INSTRUCTIONS.txt").write_text(instructions, encoding="utf-8")
    print(f"[GEN] saved INSTRUCTIONS.txt")
    print()
    print(f"[GEN] Done. {len(TAGS_TO_GENERATE)} tags + instructions in {out_dir}")


if __name__ == "__main__":
    main()
