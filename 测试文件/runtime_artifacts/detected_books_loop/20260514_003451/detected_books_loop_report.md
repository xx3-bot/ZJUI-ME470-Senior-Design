# Auto Demo Result

Run status: failed
Mode: auto_demo
Books planned: 0
Books needing attention: 1
Dry run: False

## What The Robot Plans To Do
No known catalog books were ready for robot handling.

## Needs Human Attention
- 羊皮卷: target_sequence failed: MuJoCo IK failed for target [320.0, 81.76162335115866, 115.0]
- no feasible target sequences were generated

## Technical Files
- Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260514_003451
- Combined command file: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260514_003451/loop_hardware_command_sequence.txt
- Combined command count: 0

## World Model Summary
- Detected bin books: ['羊皮卷']
- Planned shelf positions: ['羊皮卷 -> demo shelf slot 1']
- Occupied demo shelf slots: []

## Notes
- Vision provides bin pick candidates through vision.lateral_pose_provider.
- The temporary shelf placement provider starts at --place and shifts along +X.
- WorldModel records detected books, planned placements, and occupied demo shelf positions.
- target_sequence.py remains the only hardware command-generation path.
- Intermediate per-book home commands are omitted; final book keeps measured home.
