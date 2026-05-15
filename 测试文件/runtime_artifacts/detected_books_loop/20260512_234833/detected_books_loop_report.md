# Auto Demo Result

Run status: prepared
Mode: auto_demo
Books planned: 1
Books needing attention: 0
Dry run: False

## What The Robot Plans To Do
1. Move **羊皮卷** from +Y/right-side of the bin to demo shelf slot 1 at X=0 mm. Confidence 1.00.

## Needs Human Attention
None.

## Technical Files
- Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260512_234833
- Combined command file: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260512_234833/loop_hardware_command_sequence.txt
- Combined command count: 12

## World Model Summary
- Detected bin books: ['羊皮卷']
- Planned shelf positions: ['羊皮卷 -> demo shelf slot 1']
- Occupied demo shelf slots: ['demo shelf slot 1 (羊皮卷)']

## Notes
- Vision provides bin pick candidates through vision.lateral_pose_provider.
- The temporary shelf placement provider starts at --place and shifts along +X.
- WorldModel records detected books, planned placements, and occupied demo shelf positions.
- target_sequence.py remains the only hardware command-generation path.
- Intermediate per-book home commands are omitted; final book keeps measured home.
