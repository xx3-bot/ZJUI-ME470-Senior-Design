# Grip and Place Test Result

Status: partial
Timestamp: 2026-05-13T15:52:46
Output directory: /Users/xinruixiong/Desktop/ME470/Integrated Algorithm/sim_output/grip_place_test/20260513_155246

## Fixed Test Inputs
- Pick used for target_sequence: (220.0, 0.0, 115.0)
- Place slot: center
- Place used for target_sequence: (0.0, 250.0, 115.0)

## Vision Observation
No book OCR result was available.

## Selected Book
- None. The test still generated the fixed pick/place sequence.

## Target Sequence
- Failed: MuJoCo IK failed for target [145.0, 0.0, 160.0]

## Run Notes
- target_sequence failed: MuJoCo IK failed for target [145.0, 0.0, 160.0]
- left capture failed
- center capture failed
- bin detection failed
- target sequence generation failed
- v1 logs OCR pick_point but does not use it to drive the arm.
- v1 does not run +90 deg scan or ABCD shelf interpretation.
