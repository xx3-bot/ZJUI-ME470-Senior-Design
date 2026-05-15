# Auto Demo Result

Run status: dry_run_complete
Mode: auto_demo
Books planned: 4
Books needing attention: 0
Dry run: True

## What The Robot Plans To Do
1. Move **羊皮卷** from +Y/right-side of the bin to demo shelf slot 1 at X=0 mm. Confidence 0.96.
2. Move **人性的弱点** from -Y/left-side of the bin to demo shelf slot 2 at X=15 mm. Confidence 0.58.
3. Move **鬼谷子** from +Y/right-side of the bin to demo shelf slot 3 at X=30 mm. Confidence 0.96.
4. Move **墨菲定律** from -Y/left-side of the bin to demo shelf slot 4 at X=45 mm. Confidence 0.99.

## Needs Human Attention
None.

## Technical Files
- Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260512_234204
- Combined command file: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260512_234204/loop_hardware_command_sequence.txt
- Combined command count: 45

## World Model Summary
- Detected bin books: ['羊皮卷', '人性的弱点', '鬼谷子', '墨菲定律']
- Planned shelf positions: ['羊皮卷 -> demo shelf slot 1', '人性的弱点 -> demo shelf slot 2', '鬼谷子 -> demo shelf slot 3', '墨菲定律 -> demo shelf slot 4']
- Occupied demo shelf slots: ['demo shelf slot 1 (羊皮卷)', 'demo shelf slot 2 (人性的弱点)', 'demo shelf slot 3 (鬼谷子)', 'demo shelf slot 4 (墨菲定律)']

## Notes
- Vision provides bin pick candidates through vision.lateral_pose_provider.
- The temporary shelf placement provider starts at --place and shifts along +X.
- WorldModel records detected books, planned placements, and occupied demo shelf positions.
- target_sequence.py remains the only hardware command-generation path.
- Intermediate per-book home commands are omitted; final book keeps measured home.
