"""Global configuration and runtime hyperparameters for the control system."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from pick_place_plan import (
    DEFAULT_PICK_APPROACH_CLEARANCE_MM,
    DEFAULT_POST_GRASP_LIFT_MM,
    PickPlacePlan,
    from_tuples,
)


# ---------------------------------------------------------------------------
# Vision module configuration（视觉与机械运动模块对接相关）
# ---------------------------------------------------------------------------
USE_MOCK_VISION: bool = True
USE_VISION_FOR_PICK: bool = False
VISION_SHADOW_MODE: bool = False
FAKE_VISION_PICK_POSE: Tuple[float, float, float] | None = None

RGB_CAMERA_INDEX: int = 0
RGB_FRAME_WIDTH: int = 1280
RGB_FRAME_HEIGHT: int = 720

# C920e 1280x720 棋盘格标定结果（reprojection RMS = 0.299 px, 2026-05-05）
RGB_INTRINSICS_FX_PX: float = 962.98
RGB_INTRINSICS_FY_PX: float = 964.73
RGB_INTRINSICS_CX_PX: float = 609.01
RGB_INTRINSICS_CY_PX: float = 358.15

# 相机外参（占位值，装机后实测替换）
CAMERA_TRANSLATION_MM: Tuple[float, float, float] = (0.0, -400.0, 200.0)
CAMERA_ORIENTATION_MODE: str = "ARM_FACING"

# 已知书目 + 物理尺寸 + OCR 标题文字段物理高度（用于深度反推）
KNOWN_BOOK_TITLES: List[str] = [
    "习近平新时代中国特色社会主义思想概论",
    "羊皮卷",
]
KNOWN_BOOK_DIMENSIONS_MM: Dict[str, Dict[str, float]] = {
    "习近平新时代中国特色社会主义思想概论": {
        "spine_height":          227.0,
        "cover_width":           150.0,
        "thickness":              25.0,
        "ocr_visible_height_mm": 110.0,
    },
    "羊皮卷": {
        "spine_height":          210.0,
        "cover_width":           150.0,
        "thickness":               7.0,
        "ocr_visible_height_mm":  33.0,
    },
}
# 全局 fallback：仅给没填 ocr_visible_height_mm 的书用
OCR_TO_REAL_HEIGHT_RATIO: float = 0.485

# ---------------------------------------------------------------------------
# AprilTag / 启动校准（一键启动用，bin/shelf 随便摆都能自动定位）
# ---------------------------------------------------------------------------
# 所有 "TODO: 实测" 标记的常量都是占位值，机械同学装好后用尺测量实际值再改。

APRILTAG_DICT_NAME: str = "DICT_4X4_50"

# 抓握高度（机械同学硬编码）
GRIPPER_PICK_HEIGHT_MM: float = 100.0
# 爪子最大张开宽度 + 安全裕量（决定 slot 评分阈值）
GRIPPER_OPEN_WIDTH_MM: float = 60.0      # TODO: 实测后填入
GRIPPER_SAFETY_MARGIN_MM: float = 10.0

# 启动校准时机械臂转到这两个角度，分别看 bin / shelf
JOINT0_BIN_SCAN_DEG: float = 0.0         # TODO: 实测后填入
JOINT0_SHELF_SCAN_DEG: float = 30.0      # TODO: 实测后填入


# ---------------------------------------------------------------------------
# 相机相对机械臂底座的固定外参（装机一次性测量）
# ---------------------------------------------------------------------------
# 相机镜头中心相对机械臂底座 yaw 关节几何中心的偏移 (mm)
# joint 0 = 0° 时为基准位置；运行时随 joint 0 旋转
# TODO: 装机后实测填入
CAMERA_MOUNT_OFFSET_MM: Tuple[float, float, float] = (0.0, 50.0, 30.0)
# 相机光轴相对水平面的上仰角（度），仰起为正
# TODO: 实测填入
CAMERA_MOUNT_PITCH_DEG: float = 20.0


# ---------------------------------------------------------------------------
# BIN（还书框）几何模型
# ---------------------------------------------------------------------------
# bin 几何参考点（坐标原点）：bin 物体上某个固定点（建议 bin 前面板左下角）
# 所有 offset 都相对这个点。实测时只测 offset，参考点本身不需要世界坐标——
# 启动时 AprilTag 把这个参考点定位到世界系。
#
# bin 不分 slot：书可能在 bin 内任意位置，OCR 找。这里只描述 bin 内"可能出现书的区域"。
BIN_MODEL: Dict = {
    # 2 个 30mm AprilTag，贴在 bin 前面板下横条左/右两端
    "tags": {
        # tag_id: { "size_mm": 边长, "offset_mm": tag 中心相对 bin 参考点的 (x, y, z) 偏移 }
        10: {"size_mm": 30.0, "offset_mm": (50.0, 0.0, 0.0)},    # TODO: 实测，左 tag
        11: {"size_mm": 30.0, "offset_mm": (210.0, 0.0, 0.0)},   # TODO: 实测，右 tag
    },
    # bin 内书可能出现的"前面平面"几何（书脊面所在平面）
    # 该平面的中心相对 bin 参考点的偏移
    "pickable_plane_center_offset_mm": (130.0, 30.0, 80.0),  # TODO: 实测
    # 该平面的法向（默认朝 +z 即朝相机方向）
    "pickable_plane_normal":           (0.0, 0.0, 1.0),
    # 平面尺寸：书脊横向铺开范围 + 高度
    "pickable_area_width_mm":  260.0,   # TODO: 实测
    "pickable_area_height_mm": 200.0,   # TODO: 实测
}


# ---------------------------------------------------------------------------
# SHELF（书架）几何模型
# ---------------------------------------------------------------------------
# 几何参考点：建议书架前面板左下角，所有 offset 相对它。
SHELF_MODEL: Dict = {
    # 3 个 30mm AprilTag，贴在书架底部三脚正面
    "tags": {
        0: {"size_mm": 30.0, "offset_mm": (50.0,   0.0, 0.0)},  # TODO: 实测，左脚
        1: {"size_mm": 30.0, "offset_mm": (200.0,  0.0, 0.0)},  # TODO: 实测，中脚
        2: {"size_mm": 30.0, "offset_mm": (350.0,  0.0, 0.0)},  # TODO: 实测，右脚
    },
    # 4 个 zone 的几何
    # center_offset_mm: zone 中心（用于书脊高度参考）相对 shelf 参考点的偏移
    # width_mm:         zone 内能放书的横向宽度（slot 切片用）
    # height_mm:        zone 单层高度（书的活动空间）
    # slot_count:       placement 评分时把 zone 切成几个 slot
    # grasp_z_mm:       该 zone 抓握/放置时机械臂末端 z 高度（队友硬编码）
    "zones": {
        # TODO: 4 个 zone 的所有数值实测
        "A": {"center_offset_mm": (100.0, 350.0, 0.0), "width_mm": 180.0, "height_mm": 220.0, "slot_count": 8, "grasp_z_mm": 100.0},
        "B": {"center_offset_mm": (300.0, 350.0, 0.0), "width_mm": 180.0, "height_mm": 220.0, "slot_count": 8, "grasp_z_mm": 100.0},
        "C": {"center_offset_mm": (100.0, 100.0, 0.0), "width_mm": 180.0, "height_mm": 220.0, "slot_count": 8, "grasp_z_mm": 100.0},
        "D": {"center_offset_mm": (300.0, 100.0, 0.0), "width_mm": 180.0, "height_mm": 220.0, "slot_count": 8, "grasp_z_mm": 100.0},
    },
    # zone 平面的法向（默认 +z 朝相机）
    "zone_plane_normal": (0.0, 0.0, 1.0),
}


# OCR / YOLO
YOLO_MODEL_PATH: str = "yolov8n.pt"
YOLO_BOOK_CLASS_ID: int = 73
YOLO_MIN_CONF: float = 0.4
OCR_LANG: str = "ch"
OCR_MIN_SCORE: float = 0.4
OCR_MIN_FONT_THICKNESS: float = 6.0
OCR_FUZZY_MATCH_CUTOFF: float = 0.4
OCR_MAX_INPUT_SIDE: int = 1600
OCR_DET_MODEL_NAME: str = "PP-OCRv5_mobile_det"
OCR_REC_MODEL_NAME: str = "PP-OCRv5_mobile_rec"


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

    视觉对接路径：
    - USE_VISION_FOR_PICK=True：调用 vision.world_pose_provider.get_pick_world_pose()
      用真实/注入的视觉 pose 替换 FIXED_PICK_POSE。识别失败回退到固定值。
    - VISION_SHADOW_MODE=True：影子模式——求一次但不替换，仅用于日志验证通路。
    """
    pick_pose = FIXED_PICK_POSE

    if USE_VISION_FOR_PICK or VISION_SHADOW_MODE:
        from vision.world_pose_provider import get_pick_world_pose

        title = KNOWN_BOOK_TITLES[0] if KNOWN_BOOK_TITLES else ""
        world = get_pick_world_pose(title)
        if world is not None:
            print(
                f"[VISION->PLAN] vision_pick=({world[0]:.1f}, {world[1]:.1f}, {world[2]:.1f}) "
                f"title={title!r}"
            )
            if USE_VISION_FOR_PICK:
                pick_pose = world
            else:
                print("[VISION->PLAN] SHADOW_MODE: keeping FIXED_PICK_POSE")
        else:
            print(
                f"[VISION->PLAN] vision_pick=None title={title!r} "
                "→ falling back to FIXED_PICK_POSE"
            )

    derived_pick_approach = (
        pick_pose[0],
        pick_pose[1],
        pick_pose[2] + FIXED_PICK_APPROACH_CLEARANCE_MM,
    )
    derived_pick_lift = (
        pick_pose[0],
        pick_pose[1],
        pick_pose[2] + FIXED_POST_GRASP_LIFT_MM,
    )

    return from_tuples(
        pick_approach=(
            FIXED_PICK_APPROACH_POSE
            if pick_pose == FIXED_PICK_POSE
            else derived_pick_approach
        ),
        pick_lift=(
            FIXED_PICK_LIFT_POSE
            if pick_pose == FIXED_PICK_POSE
            else derived_pick_lift
        ),
        pick=pick_pose,
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
