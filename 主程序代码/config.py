"""Global configuration and runtime hyperparameters for the control system."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from pick_place_plan import (
    DEFAULT_PICK_APPROACH_CLEARANCE_MM,
    DEFAULT_POST_GRASP_LIFT_MM,
    PickPlacePlan,
    from_tuples,
)


ARM_LENGTH = 0.0
SCAN_ARC = 0.0
OFFSET_X = 0.0
OFFSET_Y = 0.0
GRIP_ORIENTATION = ""
TIP_GAP = 0.0
TIP_DEPTH = 0.0
SAMPLE_RATE_MS = 0
BOOK_VERT_HEIGHT = 0.0
SHELF_H_MIN = 0.0
SHELF_H_MAX = 0.0

INITIAL_GRIP_POS = (0.0, 0.0, 0.0)
SIM_MODE = False
VISUALIZER = False

# Fixed runtime hyperparameters for non-interactive simulation runs.
DEFAULT_RUNTIME_PARAMS = {
    "ARM_LENGTH": 240.0,
    "SCAN_ARC": 30.0,
    "OFFSET_X": 0.0,
    "OFFSET_Y": 0.0,
    "GRIP_ORIENTATION": "UP",
    "TIP_GAP": 20.0,
    "TIP_DEPTH": 25.0,
    "SAMPLE_RATE_MS": 100,
    "BOOK_VERT_HEIGHT": 80.0,
    "SHELF_H_MIN": 100.0,
    "SHELF_H_MAX": 260.0,
}


def load_default_hyperparameters() -> None:
    """Load hardcoded runtime hyperparameters for simulation mode."""
    global ARM_LENGTH, SCAN_ARC, OFFSET_X, OFFSET_Y, GRIP_ORIENTATION
    global TIP_GAP, TIP_DEPTH, SAMPLE_RATE_MS, BOOK_VERT_HEIGHT, SHELF_H_MIN, SHELF_H_MAX
    global INITIAL_GRIP_POS

    ARM_LENGTH = DEFAULT_RUNTIME_PARAMS["ARM_LENGTH"]
    SCAN_ARC = DEFAULT_RUNTIME_PARAMS["SCAN_ARC"]
    OFFSET_X = DEFAULT_RUNTIME_PARAMS["OFFSET_X"]
    OFFSET_Y = DEFAULT_RUNTIME_PARAMS["OFFSET_Y"]
    GRIP_ORIENTATION = DEFAULT_RUNTIME_PARAMS["GRIP_ORIENTATION"]
    TIP_GAP = DEFAULT_RUNTIME_PARAMS["TIP_GAP"]
    TIP_DEPTH = DEFAULT_RUNTIME_PARAMS["TIP_DEPTH"]
    SAMPLE_RATE_MS = DEFAULT_RUNTIME_PARAMS["SAMPLE_RATE_MS"]
    BOOK_VERT_HEIGHT = DEFAULT_RUNTIME_PARAMS["BOOK_VERT_HEIGHT"]
    SHELF_H_MIN = DEFAULT_RUNTIME_PARAMS["SHELF_H_MIN"]
    SHELF_H_MAX = DEFAULT_RUNTIME_PARAMS["SHELF_H_MAX"]
    INITIAL_GRIP_POS = compute_initial_grip_pose()
SIM_OUTPUT_LOG_PATH = str(Path(__file__).resolve().parent.parent / "sim_output" / "sim_output.log")
RETURN_BOOK_X = 218.0
RETURN_BOOK_Y = 120.23
RETURN_BOOK_Z = 100.0

# Minimal motion flow switches
PICK_PLACE_ONLY_MODE = True

# Fixed poses for minimal pick-and-place validation (mm)
FIXED_PICK_POSE = (218.0, 120.23, 100.0)
FIXED_PICK_APPROACH_CLEARANCE_MM = DEFAULT_PICK_APPROACH_CLEARANCE_MM
FIXED_POST_GRASP_LIFT_MM = DEFAULT_POST_GRASP_LIFT_MM
FIXED_PICK_APPROACH_POSE = (
    FIXED_PICK_POSE[0],
    FIXED_PICK_POSE[1],
    FIXED_PICK_POSE[2] + FIXED_PICK_APPROACH_CLEARANCE_MM,
)
FIXED_PICK_LIFT_POSE = (
    FIXED_PICK_POSE[0],
    FIXED_PICK_POSE[1],
    FIXED_PICK_POSE[2] + FIXED_POST_GRASP_LIFT_MM,
)
FIXED_PLACE_TRANSFER_POSE = (-40.0, 220.0, 150.0)
FIXED_PLACE_APPROACH_POSE = (-40.0, 260.0, 150.0)
FIXED_PLACE_FINAL_POSE = (-40.0, 260.0, 124.25)
FIXED_PLACE_RETREAT_POSE = (-40.0, 220.0, 150.0)

# IK environment for current practical simulation path.
# Valid profile names come from sim/vendor_km1_kinematics.py.
# Project rule: do not use esp32_factory in this workspace.
IK_PROFILE_NAME = "measured_grasp"
IK_ALPHA_MIN_DEG = -45.0
IK_ALPHA_MAX_DEG = -25.0
IK_FALLBACK_ALPHA_MIN_DEG = -90.0
IK_FALLBACK_ALPHA_MAX_DEG = 0.0
IK_COST_WEIGHTS = {
    "joint_limit": 0.0,
    "preferred_posture": 0.0,
    "motion_smoothness": 0.0,
    "alpha": 0.0,
}
IK_PREFERRED_JOINT_ANGLES_DEG = (0.0, 0.0, 0.0, 0.0)
IK_JOINT_LIMITS_DEG = (
    (-100.0, 100.0),
    # joint1 / servo001 practical range: physical ~60..240 deg.
    # With physical 150 deg treated as software 0 deg, this is -90..+90.
    (-90.0, 90.0),
    (-100.0, 100.0),
    (-100.0, 100.0),
)
IK_PREFERRED_ALPHA_DEG = -35.0
GRIPPER_SERVO_ID = 5
GRIPPER_OPEN_PWM = 1400
GRIPPER_CLOSE_PWM = 1700
GRIPPER_COMMAND_TIME_MS = 1000

BOOK_SCAN_STEPS = 10
SHELF_SCAN_STEP_MM = 60.0
SHELF_RESCAN_LIMIT = 2
BOOK_RESCAN_LIMIT = 2
PLACEMENT_SIDE_CLEARANCE = 12.0
PLACEMENT_REAR_CLEARANCE = 25.0
PLACEMENT_BOTTOM_CLEARANCE = 10.0
TILT_THRESHOLD_DEG = 8.0


def parse_hyperparameters(input_str: str) -> bool:
    """Parse the 11 runtime hyperparameters entered from the terminal."""
    global ARM_LENGTH, SCAN_ARC, OFFSET_X, OFFSET_Y, GRIP_ORIENTATION
    global TIP_GAP, TIP_DEPTH, SAMPLE_RATE_MS, BOOK_VERT_HEIGHT, SHELF_H_MIN, SHELF_H_MAX
    global INITIAL_GRIP_POS

    params = input_str.strip().split()
    if len(params) != 11:
        print(f"[CONFIG] Expected 11 hyperparameters, received {len(params)}.")
        return False

    try:
        arm_length = float(params[0])
        scan_arc = float(params[1])
        offset_x = float(params[2])
        offset_y = float(params[3])
        grip_orientation = params[4].upper()
        tip_gap = float(params[5])
        tip_depth = float(params[6])
        sample_rate_ms = int(params[7])
        book_vert_height = float(params[8])
        shelf_h_min = float(params[9])
        shelf_h_max = float(params[10])
    except ValueError:
        print("[CONFIG] Hyperparameters contain invalid numeric values.")
        return False

    if grip_orientation not in {"UP", "DOWN", "LEFT", "RIGHT"}:
        print("[CONFIG] Gripper orientation must be one of: UP, DOWN, LEFT, RIGHT.")
        return False

    if arm_length <= 0 or scan_arc <= 0 or tip_gap <= 0 or tip_depth <= 0:
        print("[CONFIG] ARM_LENGTH, SCAN_ARC, TIP_GAP and TIP_DEPTH must be positive.")
        return False

    if sample_rate_ms <= 0:
        print("[CONFIG] SAMPLE_RATE_MS must be positive.")
        return False

    if shelf_h_min >= shelf_h_max:
        print("[CONFIG] SHELF_H_MIN must be lower than SHELF_H_MAX.")
        return False

    ARM_LENGTH = arm_length
    SCAN_ARC = scan_arc
    OFFSET_X = offset_x
    OFFSET_Y = offset_y
    GRIP_ORIENTATION = grip_orientation
    TIP_GAP = tip_gap
    TIP_DEPTH = tip_depth
    SAMPLE_RATE_MS = sample_rate_ms
    BOOK_VERT_HEIGHT = book_vert_height
    SHELF_H_MIN = shelf_h_min
    SHELF_H_MAX = shelf_h_max
    INITIAL_GRIP_POS = compute_initial_grip_pose()

    print("[CONFIG] Hyperparameters loaded successfully.")
    print(f"[CONFIG] Initial gripper pose = {INITIAL_GRIP_POS}")
    return True


def compute_initial_grip_pose() -> Tuple[float, float, float]:
    """Infer the initial gripper pose when the camera center is used as the world reference."""
    orientation_offsets = {
        "UP": (OFFSET_X, OFFSET_Y),
        "DOWN": (OFFSET_X, -OFFSET_Y),
        "LEFT": (-OFFSET_X, OFFSET_Y),
        "RIGHT": (OFFSET_X, OFFSET_Y),
    }
    dx, dy = orientation_offsets.get(GRIP_ORIENTATION, (0.0, 0.0))
    return (dx, dy, 0.0)


def describe_runtime() -> Dict[str, object]:
    """Return the current runtime hyperparameters for debug logging."""
    return {
        "ARM_LENGTH": ARM_LENGTH,
        "SCAN_ARC": SCAN_ARC,
        "OFFSET_X": OFFSET_X,
        "OFFSET_Y": OFFSET_Y,
        "TIP_GAP": TIP_GAP,
        "TIP_DEPTH": TIP_DEPTH,
        "SAMPLE_RATE_MS": SAMPLE_RATE_MS,
        "BOOK_VERT_HEIGHT": BOOK_VERT_HEIGHT,
        "SHELF_H_MIN": SHELF_H_MIN,
        "SHELF_H_MAX": SHELF_H_MAX,
        "SIM_MODE": SIM_MODE,
        "SIM_VIEWER": VISUALIZER,
        "SIM_OUTPUT_LOG_PATH": SIM_OUTPUT_LOG_PATH,
        "RETURN_BOOK_X": RETURN_BOOK_X,
        "RETURN_BOOK_Y": RETURN_BOOK_Y,
        "RETURN_BOOK_Z": RETURN_BOOK_Z,
        "FIXED_PICK_POSE": FIXED_PICK_POSE,
        "FIXED_PICK_APPROACH_POSE": FIXED_PICK_APPROACH_POSE,
        "FIXED_PICK_APPROACH_CLEARANCE_MM": FIXED_PICK_APPROACH_CLEARANCE_MM,
        "FIXED_PICK_LIFT_POSE": FIXED_PICK_LIFT_POSE,
        "FIXED_POST_GRASP_LIFT_MM": FIXED_POST_GRASP_LIFT_MM,
        "FIXED_PLACE_TRANSFER_POSE": FIXED_PLACE_TRANSFER_POSE,
        "FIXED_PLACE_APPROACH_POSE": FIXED_PLACE_APPROACH_POSE,
        "FIXED_PLACE_FINAL_POSE": FIXED_PLACE_FINAL_POSE,
        "FIXED_PLACE_RETREAT_POSE": FIXED_PLACE_RETREAT_POSE,
        "IK_COST_WEIGHTS": IK_COST_WEIGHTS,
        "IK_PREFERRED_JOINT_ANGLES_DEG": IK_PREFERRED_JOINT_ANGLES_DEG,
        "IK_JOINT_LIMITS_DEG": IK_JOINT_LIMITS_DEG,
        "IK_PREFERRED_ALPHA_DEG": IK_PREFERRED_ALPHA_DEG,
        "GRIPPER_SERVO_ID": GRIPPER_SERVO_ID,
        "GRIPPER_OPEN_PWM": GRIPPER_OPEN_PWM,
        "GRIPPER_CLOSE_PWM": GRIPPER_CLOSE_PWM,
        "GRIPPER_COMMAND_TIME_MS": GRIPPER_COMMAND_TIME_MS,
    }


def get_pick_place_plan() -> PickPlacePlan:
    """Return the current minimal-flow pick/place plan.

    Future perception/planning code should produce this same shape:
    - `pick_approach`: pre-grasp waypoint above the book-spine marker
    - `pick`: book-spine/left-edge grasp marker in world millimeters
    - `pick_lift`: post-grasp vertical lift waypoint
    - `place_transfer`: shelf-side high transfer waypoint before lowering
    - `place_approach`: pre-release approach waypoint
    - `place_final`: release waypoint
    - `place_retreat`: post-release retreat waypoint
    """
    return from_tuples(
        pick_approach=FIXED_PICK_APPROACH_POSE,
        pick_lift=FIXED_PICK_LIFT_POSE,
        pick=FIXED_PICK_POSE,
        place_transfer=FIXED_PLACE_TRANSFER_POSE,
        place_approach=FIXED_PLACE_APPROACH_POSE,
        place_final=FIXED_PLACE_FINAL_POSE,
        place_retreat=FIXED_PLACE_RETREAT_POSE,
    )


def configure_sim_mode(
    sim_mode: bool,
    book_x: float | None = None,
    book_y: float | None = None,
    book_z: float | None = None,
    log_path: str | None = None,
    viewer: bool = False,
    pick_approach: tuple[float, float, float] | None = None,
    pick_approach_clearance: float | None = None,
    pick_lift: tuple[float, float, float] | None = None,
    post_grasp_lift: float | None = None,
    place_transfer: tuple[float, float, float] | None = None,
    place_approach: tuple[float, float, float] | None = None,
    place_final: tuple[float, float, float] | None = None,
    place_retreat: tuple[float, float, float] | None = None,
) -> None:
    """Configure simulation mode and optional book position overrides."""
    global SIM_MODE, VISUALIZER, RETURN_BOOK_X, RETURN_BOOK_Y, RETURN_BOOK_Z
    global SIM_OUTPUT_LOG_PATH, FIXED_PICK_POSE, FIXED_PICK_APPROACH_POSE, FIXED_PICK_LIFT_POSE
    global FIXED_PICK_APPROACH_CLEARANCE_MM, FIXED_POST_GRASP_LIFT_MM
    global FIXED_PLACE_TRANSFER_POSE, FIXED_PLACE_APPROACH_POSE, FIXED_PLACE_FINAL_POSE
    global FIXED_PLACE_RETREAT_POSE

    SIM_MODE = sim_mode
    VISUALIZER = viewer
    book_changed = False
    if book_x is not None:
        RETURN_BOOK_X = book_x
        book_changed = True
    if book_y is not None:
        RETURN_BOOK_Y = book_y
        book_changed = True
    if book_z is not None:
        RETURN_BOOK_Z = book_z
        book_changed = True
    if book_changed:
        FIXED_PICK_POSE = (RETURN_BOOK_X, RETURN_BOOK_Y, RETURN_BOOK_Z)
    if pick_approach_clearance is not None:
        FIXED_PICK_APPROACH_CLEARANCE_MM = pick_approach_clearance
    if pick_approach is not None:
        FIXED_PICK_APPROACH_POSE = pick_approach
    elif book_changed or pick_approach_clearance is not None:
        FIXED_PICK_APPROACH_POSE = (
            FIXED_PICK_POSE[0],
            FIXED_PICK_POSE[1],
            FIXED_PICK_POSE[2] + FIXED_PICK_APPROACH_CLEARANCE_MM,
        )
    if post_grasp_lift is not None:
        FIXED_POST_GRASP_LIFT_MM = post_grasp_lift
    pick_lift_changed = False
    if pick_lift is not None:
        FIXED_PICK_LIFT_POSE = pick_lift
        pick_lift_changed = True
    elif book_changed or post_grasp_lift is not None:
        FIXED_PICK_LIFT_POSE = (
            FIXED_PICK_POSE[0],
            FIXED_PICK_POSE[1],
            FIXED_PICK_POSE[2] + FIXED_POST_GRASP_LIFT_MM,
        )
        pick_lift_changed = True
    if place_approach is not None:
        FIXED_PLACE_APPROACH_POSE = place_approach
    placement_anchor_changed = False
    if place_final is not None:
        FIXED_PLACE_FINAL_POSE = place_final
        placement_anchor_changed = True
    if place_retreat is not None:
        FIXED_PLACE_RETREAT_POSE = place_retreat
        placement_anchor_changed = True
    if place_transfer is not None:
        FIXED_PLACE_TRANSFER_POSE = place_transfer
    elif pick_lift_changed or placement_anchor_changed:
        FIXED_PLACE_TRANSFER_POSE = (
            FIXED_PLACE_FINAL_POSE[0],
            FIXED_PLACE_RETREAT_POSE[1],
            FIXED_PICK_LIFT_POSE[2],
        )
    if log_path is not None:
        SIM_OUTPUT_LOG_PATH = log_path
