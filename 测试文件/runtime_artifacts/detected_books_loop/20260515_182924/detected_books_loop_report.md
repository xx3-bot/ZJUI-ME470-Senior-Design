# Auto Demo Result

Run status: prepared_with_skips
Mode: auto_demo
Books planned: 2
Books needing attention: 1
Dry run: False

## What The Robot Plans To Do
1. Move **羊皮卷** from near the bin center to shelf B slice 0 (lean_left) at X=20 mm. Book is nearly vertical. Confidence 1.00.
2. Move **人性的弱点** from -Y/left-side of the bin to shelf A slice 4 (lean_right) at X=-20 mm. Book is nearly vertical. Confidence 0.92.

## Needs Human Attention
- 墨菲定律: target_sequence failed: MuJoCo IK failed for target [311.7, 77.83763236815967, 115.0]

## Technical Files
- Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260515_182924
- Combined command file: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260515_182924/loop_hardware_command_sequence.txt
- Combined command count: 25
- Visual plan overlay: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260515_182924/bin_plan_overlay.png
- Visual plan overlay: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260515_182924/shelf_plan_overlay.png

## World Model Summary
- Detected bin books: ['羊皮卷', '人性的弱点', '墨菲定律']
- Planned shelf positions: ['羊皮卷 -> demo shelf slot 1', '人性的弱点 -> demo shelf slot 2', '墨菲定律 -> demo shelf slot 3']
- Occupied demo shelf slots: ['demo shelf slot 1 (羊皮卷)', 'demo shelf slot 2 (人性的弱点)']

## Notes
- Vision provides bin pick candidates through vision.lateral_pose_provider.
- A-route shelf logic: startup scan initializes shelf slots; execution updates WorldModel occupancy.
- WorldModel records detected books, planned placements, and occupied demo shelf positions.
- target_sequence.py remains the only hardware command-generation path.
- Intermediate per-book home commands are omitted; final book keeps measured home.
