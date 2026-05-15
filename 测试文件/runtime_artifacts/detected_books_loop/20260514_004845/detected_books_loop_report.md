# Auto Demo Result

Run status: sent
Mode: auto_demo
Books planned: 1
Books needing attention: 0
Dry run: False

## What The Robot Plans To Do
1. Move **羊皮卷** from +Y/right-side of the bin to demo shelf slot 1 at X=0 mm. Book is nearly vertical. Confidence 0.52.

## Needs Human Attention
None.

## Technical Files
- Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260514_004845
- Combined command file: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260514_004845/loop_hardware_command_sequence.txt
- Combined command count: 14

## World Model Summary
- Detected bin books: ['羊皮卷', '人性的弱点', '鬼谷子', '墨菲定律']
- Planned shelf positions: ['羊皮卷 -> demo shelf slot 1', '人性的弱点 -> demo shelf slot 2', '鬼谷子 -> demo shelf slot 3', '墨菲定律 -> demo shelf slot 4']
- Occupied demo shelf slots: ['demo shelf slot 1 (羊皮卷)']

## Notes
- Vision provides bin pick candidates through vision.lateral_pose_provider.
- The temporary shelf placement provider starts at --place and shifts along +X.
- WorldModel records detected books, planned placements, and occupied demo shelf positions.
- target_sequence.py remains the only hardware command-generation path.
- Intermediate per-book home commands are omitted; final book keeps measured home.
