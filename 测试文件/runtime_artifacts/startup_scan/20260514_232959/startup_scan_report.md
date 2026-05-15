# Startup Scan Result

Status: complete
Timestamp: 2026-05-14T23:30:02
Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/startup_scan/20260514_232959

## Captured Views
- Left view: base -90 deg, shelf/world context.
- Center view: base 0 deg, bin/books.

## Detected Books
1. 墨菲定律 (confidence=0.999, pick=(293.1, 42.1, 115.0) mm, source=vision_pending)
2. 羊皮卷 (confidence=0.999, pick=(293.1, -65.5, 115.0) mm, source=vision_pending)

## World Snapshot
- Book entities linked to OCR: 2
- Pick candidates: 2
- Shelf placement candidates: 5
- Initialized shelf world slots: 5
- Bin grid depth estimate: arm X=303.1 mm (camera depth=212.9 mm); overlay=/Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/startup_scan/20260514_232959/center_bin_grid_overlay.png

## Task Queue
1. 羊皮卷: pick candidate ready; shelf slot=left:4, hint=lean_right, support=right_wall; not sent to hardware.
2. 墨菲定律: pick candidate ready; shelf slot=left:0, hint=lean_left, support=left_wall; not sent to hardware.

## Planned Catalog Tasks
1. 墨菲定律 -> zone=C_right thickness=18.0 mm
2. 羊皮卷 -> zone=A_right thickness=7.0 mm

## Unknown Titles
None.

## Run Notes
- No blocking issues recorded.
- This is a demo/user-facing summary, not an external library-system update.
- Startup scan initializes the world snapshot; it does not execute pick/place hardware.
