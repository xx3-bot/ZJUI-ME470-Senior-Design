# Auto Demo Result

Run status: prepared
Mode: auto_demo
Books planned: 1
Books needing attention: 1
Dry run: False

## What The Robot Plans To Do
1. Move **鬼谷子** from -Y/left-side of the bin to demo shelf slot 1 at X=0 mm. Confidence 0.64.

## Needs Human Attention
- OCR saw `陆明编者张辰伴编泽` but it is not in the known-book list; leave it for manual handling or add it to the catalog.

## Technical Files
- Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260513_011823
- Combined command file: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/detected_books_loop/20260513_011823/loop_hardware_command_sequence.txt
- Combined command count: 13

## World Model Summary
- Detected bin books: ['鬼谷子']
- Planned shelf positions: ['鬼谷子 -> demo shelf slot 1']
- Occupied demo shelf slots: ['demo shelf slot 1 (鬼谷子)']

## Notes
- Vision provides bin pick candidates through vision.lateral_pose_provider.
- The temporary shelf placement provider starts at --place and shifts along +X.
- WorldModel records detected books, planned placements, and occupied demo shelf positions.
- target_sequence.py remains the only hardware command-generation path.
- Intermediate per-book home commands are omitted; final book keeps measured home.
