"""L1 离线测试：用静态图验证 SpineDetector pipeline。

用法（在 主程序代码/ 目录下）：
    python -m vision.test_offline

它会：
1. 读 vision/test_images/ 下所有 jpg/jpeg/png/bmp
2. 对每张图跑 SpineDetector + bin_scanner.detect_books_in_frame
3. 把命中结果 dict 打印到终端
4. 把可视化叠加图存到 vision/captures/<原文件名>_annotated.jpg
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import cv2
import numpy as np
from PIL import Image, ImageOps

from .bin_scanner import _hit_to_book_dict
from .ocr import SpineOCR
from .spine_detector import SpineDetector
from .visual_overlay import draw_hits


def _load_image_with_exif(image_path: Path) -> np.ndarray | None:
    """用 PIL 读图并应用 EXIF orientation，再转回 BGR ndarray。

    iPhone 横屏拍出的 JPEG 把方向写在 EXIF orientation tag 里，cv2.imread 不认；
    不旋转就会把竖直摆放的书读成侧躺。
    """
    try:
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            rgb = np.array(img.convert("RGB"))
    except Exception as exc:
        print(f"  ! PIL 读图失败 ({exc})；回退 cv2.imread")
        frame = cv2.imread(str(image_path))
        return frame
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def _module_dir() -> Path:
    return Path(__file__).resolve().parent


def _list_test_images(test_dir: Path) -> List[Path]:
    if not test_dir.is_dir():
        return []
    return sorted(
        p for p in test_dir.iterdir() if p.suffix.lower() in _IMAGE_EXTS
    )


def _process_one(image_path: Path, captures_dir: Path) -> None:
    print("\n" + "=" * 60)
    print(f"[L1] {image_path.name}")
    frame = _load_image_with_exif(image_path)
    if frame is None:
        print("  ! 无法读图，跳过")
        return
    print(f"  loaded shape={frame.shape}")

    # 先 dump 一份原始 OCR 输出，方便诊断 hits=0 是 OCR 没看到字
    # 还是看到了字但被方向/匹配过滤掉
    raw_polys = SpineOCR.instance().recognize_polygons(frame)
    print(f"  raw OCR polygons = {len(raw_polys)}")
    for i, p in enumerate(raw_polys):
        cx, cy = p.center
        corners = ", ".join(f"({pt[0]:.0f},{pt[1]:.0f})" for pt in p.polygon)
        print(
            f"    [{i}] text={p.text!r} score={p.score:.2f} "
            f"vertical={p.is_vertical_text} center=({cx:.0f},{cy:.0f})"
        )
        print(f"        corners=[{corners}]")

    hits = SpineDetector.instance().detect(frame)
    print(f"  hits = {len(hits)}")
    h, w = frame.shape[:2]
    for i, hit in enumerate(hits):
        print(
            f"  [{i}] title={hit.matched_title!r} bbox={hit.bbox} "
            f"tilt={hit.tilt_deg:+.1f} deg score={hit.ocr_score:.2f}"
        )
        print(f"    dict[{i}] = {_hit_to_book_dict(hit, (w, h))}")

    annotated = draw_hits(frame, hits)
    captures_dir.mkdir(parents=True, exist_ok=True)
    out_path = captures_dir / f"{image_path.stem}_annotated.jpg"
    cv2.imwrite(str(out_path), annotated)
    print(f"  saved -> {out_path}")


def main() -> None:
    base = _module_dir()
    test_dir = base / "test_images"
    captures_dir = base / "captures"
    images = _list_test_images(test_dir)
    if not images:
        print(f"[L1] {test_dir} 下没有图，先放几张 jpg/png 进去再跑。")
        return
    for image_path in images:
        try:
            _process_one(image_path, captures_dir)
        except Exception as exc:
            print(f"[L1] 处理 {image_path.name} 出错: {exc}")


if __name__ == "__main__":
    main()
