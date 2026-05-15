# Auto Demo Result

Run status: failed
Mode: auto_demo
Books planned: 0
Books needing attention: 2
Dry run: True

## What The Robot Plans To Do
No known catalog books were ready for robot handling.

## Needs Human Attention
- 鬼谷子: target_sequence failed: MuJoCo IK failed for target [334.7, 86.39710153417218, 115.0]
- 墨菲定律: target_sequence failed: MuJoCo IK failed for target [334.7, 14.976960425014044, 115.0]
- no feasible target sequences were generated

## Technical Files
- Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260514_005229
- Combined command file: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260514_005229/loop_hardware_command_sequence.txt
- Combined command count: 0

## World Model Summary
- Detected bin books: ['鬼谷子', '墨菲定律']
- Planned shelf positions: ['鬼谷子 -> demo shelf slot 1', '墨菲定律 -> demo shelf slot 2']
- Occupied demo shelf slots: []

## Notes
- Vision provides bin pick candidates through vision.lateral_pose_provider.
- The temporary shelf placement provider starts at --place and shifts along +X.
- WorldModel records detected books, planned placements, and occupied demo shelf positions.
- target_sequence.py remains the only hardware command-generation path.
- Intermediate per-book home commands are omitted; final book keeps measured home.
