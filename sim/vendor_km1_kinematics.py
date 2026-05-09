"""Vendor-derived inverse kinematics for the KM1 arm.

The formulas in this file are ported from the vendor OpenMV/STM32/ESP32
resources in `项目资源（厂商）`.

Inputs are millimeters and degrees. Output PWM values match the vendor
`#000P1500T1000!` command convention.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import math
from pathlib import Path


@dataclass(frozen=True)
class KM1Profile:
    name: str
    l0_mm: float
    l1_mm: float
    l2_mm: float
    l3_mm: float
    theta5_min_deg: float
    theta5_max_deg: float
    theta3_abs_limit_deg: float
    alpha_start_deg: int
    alpha_stop_deg: int
    invert_servo2_in_group_command: bool
    invert_servo3_in_group_command: bool
    servo_relative_limit_deg: float | None


ACTIVE_PROFILE_NAME = "measured_grasp"
HARDWARE_NEUTRAL_DEG = 150.0
# Vendor servo protocol: command range P500..P2500 spans 270 degrees. With
# P1500 as the centered/default pose, the mechanical range is +/-135 degrees.
PWM_PER_HARDWARE_DEG = 1000.0 / 135.0
JOINT1_INTERNAL_TO_HARDWARE_OFFSET_DEG = 90.0


PROFILES = {
    "esp32_factory": KM1Profile(
        name="esp32_factory",
        l0_mm=100.0,
        l1_mm=105.0,
        l2_mm=75.0,
        l3_mm=180.0,
        theta5_min_deg=-30.0,
        theta5_max_deg=210.0,
        theta3_abs_limit_deg=120.0,
        alpha_start_deg=-30,
        alpha_stop_deg=-135,
        invert_servo2_in_group_command=False,
        invert_servo3_in_group_command=False,
        servo_relative_limit_deg=None,
    ),
    "stm32_openmv": KM1Profile(
        name="stm32_openmv",
        l0_mm=100.0,
        l1_mm=105.0,
        l2_mm=88.0,
        l3_mm=155.0,
        theta5_min_deg=0.0,
        theta5_max_deg=180.0,
        theta3_abs_limit_deg=90.0,
        alpha_start_deg=0,
        alpha_stop_deg=-135,
        invert_servo2_in_group_command=False,
        invert_servo3_in_group_command=True,
        servo_relative_limit_deg=None,
    ),
    "measured_physical": KM1Profile(
        name="measured_physical",
        l0_mm=103.0,
        l1_mm=105.0,
        l2_mm=86.35,
        l3_mm=100.0,
        theta5_min_deg=-30.0,
        theta5_max_deg=210.0,
        theta3_abs_limit_deg=120.0,
        alpha_start_deg=-30,
        alpha_stop_deg=-135,
        invert_servo2_in_group_command=False,
        invert_servo3_in_group_command=False,
        servo_relative_limit_deg=None,
    ),
    "measured_grasp": KM1Profile(
        name="measured_grasp",
        l0_mm=103.0,
        l1_mm=105.0,
        l2_mm=86.35,
        l3_mm=125.0,
        theta5_min_deg=-30.0,
        theta5_max_deg=210.0,
        theta3_abs_limit_deg=120.0,
        alpha_start_deg=-30,
        alpha_stop_deg=-135,
        invert_servo2_in_group_command=False,
        invert_servo3_in_group_command=True,
        servo_relative_limit_deg=None,
    ),
}


@dataclass(frozen=True)
class IKResult:
    ok: bool
    error_code: int
    alpha_deg: float | None = None
    servo_angles_deg: tuple[float, float, float, float] | None = None
    servo_pwm: tuple[int, int, int, int] | None = None
    command: str | None = None


ERROR_MEANINGS = {
    0: "ok",
    1: "z below lower model bound",
    2: "target beyond l1+l2 reach after gripper offset",
    3: "elbow acos input outside [-1, 1]",
    4: "theta4 outside vendor limit",
    5: "shoulder acos input outside [-1, 1]",
    6: "theta5 outside vendor limit",
    7: "theta3 outside vendor limit",
    8: "no valid alpha found",
    9: "servo relative angle outside 0-180 bus-servo limit",
}


def pwm_from_angle(angle_deg: float, sign: int) -> int:
    """Map software-relative joint angle to KM1 PWM/angle command value.

    Project hardware convention:
    - software/IK angle 0 deg means the servo's physical 150 deg neutral pose
    - protocol value P1500 therefore represents software 0 deg
    - a +1 software degree change is 1000/135 PWM units after applying joint sign
    - if a joint is "reversed", change the sign here. That mirrors the hardware
      target around 150 deg/P1500, e.g. software +30 deg becomes about P1278
      instead of P1722. Do not mirror hardware commands around physical 0 deg.

    Vendor servo protocol uses P500..P2500 over 270 degrees. With P1500 as the
    center/default pose, +/-135 degrees corresponds to +/-1000 PWM, so the scale
    is 1000/135 PWM per mechanical degree.
    """
    return int(round(1500.0 + sign * PWM_PER_HARDWARE_DEG * angle_deg))


def calibrated_joint1_angle_deg(internal_angle_deg: float) -> float:
    """Convert IK-internal shoulder angle to the physical joint1 zero convention.

    The MuJoCo/vendor IK geometry keeps the vertical/upright shoulder posture at
    about -90 deg internally. The physical hardware convention treats that same
    upright/default posture as joint1 0 deg / P1500. Apply this offset only when
    reporting calibrated joint1 or converting to hardware PWM; do not feed it
    back into IK solving.
    """
    return internal_angle_deg + JOINT1_INTERNAL_TO_HARDWARE_OFFSET_DEG


def analyze_pose(
    x_mm: float,
    y_mm: float,
    z_mm: float,
    alpha_deg: float,
    profile: KM1Profile,
    time_ms: int = 1500,
) -> IKResult:
    if x_mm == 0:
        theta6 = 0.0
    elif y_mm == 0 and x_mm > 0:
        theta6 = 90.0
    elif y_mm == 0 and x_mm < 0:
        theta6 = -90.0
    else:
        theta6 = math.degrees(math.atan2(x_mm, y_mm))

    radial_y = math.sqrt(x_mm * x_mm + y_mm * y_mm)
    alpha_rad = math.radians(alpha_deg)
    wrist_y = radial_y - profile.l3_mm * math.cos(alpha_rad)
    wrist_z = z_mm - profile.l0_mm - profile.l3_mm * math.sin(alpha_rad)

    if wrist_z < -profile.l0_mm:
        return IKResult(False, 1)
    wrist_dist = math.sqrt(wrist_y * wrist_y + wrist_z * wrist_z)
    if wrist_dist > profile.l1_mm + profile.l2_mm:
        return IKResult(False, 2)
    if wrist_dist <= 1e-9:
        return IKResult(False, 5)

    ccc_input = wrist_y / wrist_dist
    if ccc_input > 1.0 or ccc_input < -1.0:
        return IKResult(False, 5)
    ccc = math.acos(ccc_input)

    bbb = (
        wrist_y * wrist_y
        + wrist_z * wrist_z
        + profile.l1_mm * profile.l1_mm
        - profile.l2_mm * profile.l2_mm
    ) / (2 * profile.l1_mm * wrist_dist)
    if bbb > 1.0 or bbb < -1.0:
        return IKResult(False, 5)

    zf_flag = -1.0 if wrist_z < 0 else 1.0
    theta5 = math.degrees(ccc * zf_flag + math.acos(bbb))
    if theta5 > profile.theta5_max_deg or theta5 < profile.theta5_min_deg:
        return IKResult(False, 6)

    aaa = -(
        wrist_y * wrist_y
        + wrist_z * wrist_z
        - profile.l1_mm * profile.l1_mm
        - profile.l2_mm * profile.l2_mm
    ) / (2 * profile.l1_mm * profile.l2_mm)
    if aaa > 1.0 or aaa < -1.0:
        return IKResult(False, 3)

    theta4 = 180.0 - math.degrees(math.acos(aaa))
    if theta4 > 135.0 or theta4 < -135.0:
        return IKResult(False, 4)

    theta3 = alpha_deg - theta5 + theta4
    if theta3 > profile.theta3_abs_limit_deg or theta3 < -profile.theta3_abs_limit_deg:
        return IKResult(False, 7)

    theta6 = max(-135.0, min(135.0, theta6))
    servo_angles = (theta6, theta5 - 90.0, theta4, theta3)
    if profile.servo_relative_limit_deg is not None and any(
        abs(angle) > profile.servo_relative_limit_deg for angle in servo_angles
    ):
        return IKResult(False, 9)

    servo_pwm = (
        pwm_from_angle(servo_angles[0], 1),
        pwm_from_angle(calibrated_joint1_angle_deg(servo_angles[1]), -1),
        pwm_from_angle(servo_angles[2], -1 if profile.invert_servo2_in_group_command else 1),
        pwm_from_angle(servo_angles[3], -1 if profile.invert_servo3_in_group_command else 1),
    )
    command = (
        "{"
        f"#000P{servo_pwm[0]:04d}T{time_ms:04d}!"
        f"#001P{servo_pwm[1]:04d}T{time_ms:04d}!"
        f"#002P{servo_pwm[2]:04d}T{time_ms:04d}!"
        f"#003P{servo_pwm[3]:04d}T{time_ms:04d}!"
        "}"
    )
    return IKResult(True, 0, alpha_deg, servo_angles, servo_pwm, command)


def solve_pose(
    x_mm: float,
    y_mm: float,
    z_mm: float,
    profile: KM1Profile = PROFILES[ACTIVE_PROFILE_NAME],
    time_ms: int = 1500,
    alpha_min_deg: float | None = None,
    alpha_max_deg: float | None = None,
) -> IKResult:
    step = -1 if profile.alpha_stop_deg <= profile.alpha_start_deg else 1
    best: IKResult | None = None
    for alpha in range(profile.alpha_start_deg, profile.alpha_stop_deg + step, step):
        if alpha_min_deg is not None and alpha < alpha_min_deg:
            continue
        if alpha_max_deg is not None and alpha > alpha_max_deg:
            continue
        result = analyze_pose(x_mm, y_mm, z_mm, alpha, profile, time_ms)
        if result.ok:
            best = result
    if best is None:
        return IKResult(False, 8)
    return best


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run vendor-derived KM1 IK.")
    parser.add_argument("x", type=float, nargs="?")
    parser.add_argument("y", type=float, nargs="?")
    parser.add_argument("z", type=float, nargs="?")
    parser.add_argument("--profile", choices=sorted(PROFILES), default=ACTIVE_PROFILE_NAME)
    parser.add_argument("--time-ms", type=int, default=1500)
    parser.add_argument(
        "--alpha-range",
        help="Optional gripper angle constraint in degrees, for example -45:-25 for shelf placement.",
    )
    parser.add_argument("--scan-grid", action="store_true")
    parser.add_argument("--x-range", default="-220:220")
    parser.add_argument("--y-range", default="80:460")
    parser.add_argument("--z-range", default="20:520")
    parser.add_argument("--step-mm", type=float, default=20.0)
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).resolve().parent / "diagnostics" / "vendor_ik_grid.csv",
    )
    args = parser.parse_args()

    profile = PROFILES[args.profile]
    alpha_min, alpha_max = parse_alpha_range(args.alpha_range)
    if args.scan_grid:
        scan_grid(profile, args, alpha_min, alpha_max)
        return

    if args.x is None or args.y is None or args.z is None:
        parser.error("x y z are required unless --scan-grid is used")

    result = solve_pose(args.x, args.y, args.z, profile, args.time_ms, alpha_min, alpha_max)
    print(f"profile: {profile.name}")
    print(f"target_mm: ({args.x:.1f}, {args.y:.1f}, {args.z:.1f})")
    print(f"ok: {result.ok}")
    print(f"error: {result.error_code} ({ERROR_MEANINGS[result.error_code]})")
    if result.ok:
        print(f"alpha_deg: {result.alpha_deg}")
        print(f"servo_angles_deg: {[round(v, 2) for v in result.servo_angles_deg or ()]}")
        print(f"servo_pwm: {result.servo_pwm}")
        print(f"command: {result.command}")


def parse_range(text: str) -> tuple[float, float]:
    left, right = text.split(":", 1)
    return float(left), float(right)


def parse_alpha_range(text: str | None) -> tuple[float | None, float | None]:
    if text is None:
        return None, None
    left, right = text.split(":", 1)
    low = float(left)
    high = float(right)
    return min(low, high), max(low, high)


def scan_grid(profile: KM1Profile, args, alpha_min: float | None, alpha_max: float | None) -> None:
    x0, x1 = parse_range(args.x_range)
    y0, y1 = parse_range(args.y_range)
    z0, z1 = parse_range(args.z_range)

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    ok_count = 0
    with args.csv.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "x_mm",
                "y_mm",
                "z_mm",
                "ok",
                "error_code",
                "alpha_deg",
                "servo0_pwm",
                "servo1_pwm",
                "servo2_pwm",
                "servo3_pwm",
                "command",
            ]
        )
        x = x0
        while x <= x1 + 1e-9:
            y = y0
            while y <= y1 + 1e-9:
                z = z0
                while z <= z1 + 1e-9:
                    result = solve_pose(x, y, z, profile, args.time_ms, alpha_min, alpha_max)
                    total += 1
                    ok_count += int(result.ok)
                    pwm = result.servo_pwm or ("", "", "", "")
                    writer.writerow(
                        [
                            x,
                            y,
                            z,
                            int(result.ok),
                            result.error_code,
                            result.alpha_deg if result.alpha_deg is not None else "",
                            *pwm,
                            result.command or "",
                        ]
                    )
                    z += args.step_mm
                y += args.step_mm
            x += args.step_mm

    print(f"profile: {profile.name}")
    print(f"grid success: {ok_count}/{total} ({ok_count / max(total, 1):.1%})")
    print(f"wrote: {args.csv}")


if __name__ == "__main__":
    main()
