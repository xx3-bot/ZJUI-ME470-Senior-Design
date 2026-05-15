# Startup Scan Result

Status: complete
Timestamp: 2026-05-14T00:54:19
Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/startup_scan/20260514_005418

## Captured Views
- Left view: base -90 deg, shelf/world context.
- Center view: base 0 deg, bin/books.

## Detected Books
1. 鬼谷子 (confidence=0.994, pick=(315.4, 74.0, 115.0) mm, source=vision_pending)
2. 墨菲定律 (confidence=0.996, pick=(315.4, 9.5, 115.0) mm, source=vision_pending)

## World Snapshot
- Book entities linked to OCR: 2
- Pick candidates: 2
- Shelf placement candidates: 10
- Bin grid depth estimate: arm X=315.4 mm (camera depth=225.2 mm); overlay=/Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/startup_scan/20260514_005418/center_bin_grid_overlay.png

## Task Queue
1. 鬼谷子: pick candidate ready; shelf hint=lean_right, support=right_wall; not sent to hardware.
2. 墨菲定律: pick candidate ready; shelf hint=lean_left, support=left_wall; not sent to hardware.

## Planned Catalog Tasks
1. 鬼谷子 -> zone=C_left thickness=24.0 mm
2. 墨菲定律 -> zone=C_right thickness=18.0 mm

## Unknown Titles
None.

## Run Notes
- No blocking issues recorded.
- This is a demo/user-facing summary, not an external library-system update.
- Startup scan initializes the world snapshot; it does not execute pick/place hardware.
