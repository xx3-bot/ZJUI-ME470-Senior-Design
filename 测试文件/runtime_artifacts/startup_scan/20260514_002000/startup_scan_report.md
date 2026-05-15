# Startup Scan Result

Status: complete
Timestamp: 2026-05-14T00:20:02
Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/startup_scan/20260514_002000

## Captured Views
- Left view: base -90 deg, shelf/world context.
- Center view: base 0 deg, bin/books.

## Detected Books
1. 羊皮卷 (confidence=0.998, pick=(320.0, 21.3, 115.0) mm, source=vision_pending)
2. 鬼谷子 (confidence=0.787, pick=(320.0, -8.1, 115.0) mm, source=vision_pending)
3. 墨菲定律 (confidence=0.999, pick=(320.0, -36.8, 115.0) mm, source=vision_pending)
4. 人性的弱点 (confidence=0.984, pick=(320.0, -66.6, 115.0) mm, source=vision_pending)

## World Snapshot
- Book entities linked to OCR: 4
- Pick candidates: 4
- Shelf placement candidates: 10
- Bin grid depth estimate: arm X=321.7 mm (camera depth=231.5 mm); overlay=/Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/startup_scan/20260514_002000/center_bin_grid_overlay.png

## Task Queue
1. 羊皮卷: pick candidate ready; shelf hint=lean_right, support=right_wall; not sent to hardware.
2. 人性的弱点: pick candidate ready; shelf hint=lean_left, support=left_wall; not sent to hardware.
3. 鬼谷子: pick candidate ready; shelf hint=lean_left, support=left_wall; not sent to hardware.
4. 墨菲定律: pick candidate ready; shelf hint=lean_right, support=right_wall; not sent to hardware.

## Planned Catalog Tasks
1. 羊皮卷 -> zone=A_right thickness=7.0 mm
2. 鬼谷子 -> zone=C_left thickness=24.0 mm
3. 墨菲定律 -> zone=C_right thickness=18.0 mm
4. 人性的弱点 -> zone=B_right thickness=28.0 mm

## Unknown Titles
None.

## Run Notes
- No blocking issues recorded.
- This is a demo/user-facing summary, not an external library-system update.
- Startup scan initializes the world snapshot; it does not execute pick/place hardware.
