# Startup Scan Result

Status: complete
Timestamp: 2026-05-13T23:52:38
Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/startup_scan/20260513_235235

## Captured Views
- Left view: base -90 deg, shelf/world context.
- Center view: base 0 deg, bin/books.

## Detected Books
1. 羊皮卷 (confidence=0.999, rel_x=-17.3 mm, pick=(-17.3, 260.0, 115.0) mm)
2. 鬼谷子 (confidence=0.816, rel_x=4.6 mm, pick=(4.6, 260.0, 115.0) mm)
3. 墨菲定律 (confidence=0.999, rel_x=25.6 mm, pick=(25.6, 260.0, 115.0) mm)
4. 人性的弱点 (confidence=0.975, rel_x=47.8 mm, pick=(47.8, 260.0, 115.0) mm)

## World Snapshot
- Book entities linked to OCR: 4
- Pick candidates: 4
- Shelf placement candidates: 10
- Bin grid depth estimate: arm X=262.2 mm (camera depth=172.0 mm)

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
