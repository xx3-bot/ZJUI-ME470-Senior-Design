# Auto Demo Result

Run status: sent
Mode: auto_demo
Books planned: 2
Books needing attention: 0
Dry run: False

## What The Robot Plans To Do
1. Move **鬼谷子** from +Y/right-side of the bin to demo shelf slot 1 at X=0 mm. Book is nearly vertical. Confidence 0.95.
2. Move **墨菲定律** from +Y/right-side of the bin to demo shelf slot 2 at X=15 mm. Book is nearly vertical. Confidence 0.99.

## Needs Human Attention
None.

## Technical Files
- Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260514_005856
- Combined command file: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260514_005856/loop_hardware_command_sequence.txt
- Combined command count: 27

## World Model Summary
- Detected bin books: ['鬼谷子', '墨菲定律']
- Planned shelf positions: ['鬼谷子 -> demo shelf slot 1', '墨菲定律 -> demo shelf slot 2']
- Occupied demo shelf slots: ['demo shelf slot 1 (鬼谷子)', 'demo shelf slot 2 (墨菲定律)']

## Notes
- Vision provides bin pick candidates through vision.lateral_pose_provider.
- The temporary shelf placement provider starts at --place and shifts along +X.
- WorldModel records detected books, planned placements, and occupied demo shelf positions.
- target_sequence.py remains the only hardware command-generation path.
- Intermediate per-book home commands are omitted; final book keeps measured home.
