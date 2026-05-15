# Auto Demo Result

Run status: failed
Mode: auto_demo
Books planned: 0
Books needing attention: 3
Dry run: False

## What The Robot Plans To Do
No known catalog books were ready for robot handling.

## Needs Human Attention
- 羊皮卷: target_sequence failed: MuJoCo IK failed for target [320.9, 5.990098756231914, 115.0]
- 人性的弱点: target_sequence failed: MuJoCo IK failed for target [320.9, -70.00025466610263, 115.0]
- 墨菲定律: target_sequence failed: MuJoCo IK failed for target [320.9, 81.0706175500426, 115.0]
- no feasible target sequences were generated

## Technical Files
- Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260515_181015
- Combined command file: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260515_181015/loop_hardware_command_sequence.txt
- Combined command count: 0

## World Model Summary
- Detected bin books: ['羊皮卷', '人性的弱点', '墨菲定律']
- Planned shelf positions: ['羊皮卷 -> demo shelf slot 1', '人性的弱点 -> demo shelf slot 2', '墨菲定律 -> demo shelf slot 3']
- Occupied demo shelf slots: []

## Notes
- Vision provides bin pick candidates through vision.lateral_pose_provider.
- A-route shelf logic: startup scan initializes shelf slots; execution updates WorldModel occupancy.
- WorldModel records detected books, planned placements, and occupied demo shelf positions.
- target_sequence.py remains the only hardware command-generation path.
- Intermediate per-book home commands are omitted; final book keeps measured home.
