# Auto Demo Result

Run status: sent
Mode: auto_demo
Books planned: 2
Books needing attention: 0
Dry run: False

## What The Robot Plans To Do
1. Move **羊皮卷** from -Y/left-side of the bin to shelf A slice 4 (lean_right) at X=-8 mm. Book is nearly vertical. Confidence 1.00.
2. Move **墨菲定律** from +Y/right-side of the bin to shelf A slice 0 (lean_left) at X=-73 mm. Book is nearly vertical. Confidence 1.00.

## Needs Human Attention
None.

## Technical Files
- Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260514_233036
- Combined command file: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260514_233036/loop_hardware_command_sequence.txt
- Combined command count: 25

## World Model Summary
- Detected bin books: ['羊皮卷', '墨菲定律']
- Planned shelf positions: ['羊皮卷 -> demo shelf slot 1', '墨菲定律 -> demo shelf slot 2']
- Occupied demo shelf slots: ['demo shelf slot 1 (羊皮卷)', 'demo shelf slot 2 (墨菲定律)']

## Notes
- Vision provides bin pick candidates through vision.lateral_pose_provider.
- A-route shelf logic: startup scan initializes shelf slots; execution updates WorldModel occupancy.
- WorldModel records detected books, planned placements, and occupied demo shelf positions.
- target_sequence.py remains the only hardware command-generation path.
- Intermediate per-book home commands are omitted; final book keeps measured home.
