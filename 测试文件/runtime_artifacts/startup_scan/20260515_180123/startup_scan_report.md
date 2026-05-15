# Startup Scan Result

Status: complete
Timestamp: 2026-05-15T18:01:23
Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/startup_scan/20260515_180123

## Captured Views
- Left view: base -90 deg, shelf/world context.
- Center view: base 0 deg, bin/books.

## Detected Books
1. 墨菲定律 (confidence=0.999, pick=(309.5, 60.4, 115.0) mm, source=vision_pending)
2. 羊皮卷 (confidence=0.999, pick=(309.5, 1.0, 115.0) mm, source=vision_pending)
3. 人性的弱点 (confidence=0.979, pick=(309.5, -59.4, 115.0) mm, source=vision_pending)

## World Snapshot
- Book entities linked to OCR: 3
- Pick candidates: 3
- Shelf placement candidates: 10
- Initialized shelf world slots: 10
- Bin grid depth estimate: arm X=319.5 mm (camera depth=229.3 mm); overlay=/Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/startup_scan/20260515_180123/center_bin_grid_overlay.png

## Task Queue
1. 羊皮卷: pick candidate ready; shelf slot=right:0, hint=lean_left, support=left_wall; not sent to hardware.
2. 人性的弱点: pick candidate ready; shelf slot=left:4, hint=lean_right, support=right_wall; not sent to hardware.
3. 墨菲定律: pick candidate ready; shelf slot=right:4, hint=lean_right, support=right_wall; not sent to hardware.

## Planned Catalog Tasks
1. 墨菲定律 -> zone=C_right thickness=18.0 mm
2. 羊皮卷 -> zone=A_right thickness=7.0 mm
3. 人性的弱点 -> zone=B_right thickness=28.0 mm

## Unknown Titles
None.

## Run Notes
- No blocking issues recorded.
- This is a demo/user-facing summary, not an external library-system update.
- Startup scan initializes the world snapshot; it does not execute pick/place hardware.
