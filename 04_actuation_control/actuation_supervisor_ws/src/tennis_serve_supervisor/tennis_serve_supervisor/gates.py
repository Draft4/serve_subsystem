"""Execution gate rules for one tennis serve shot."""

from __future__ import annotations

import math
from dataclasses import dataclass

from tennis_serve_common.core import RobotSample, wrap_angle_rad

@dataclass(frozen=True)
class LauncherSample:
    online: bool
    rpm_valid: bool
    pitch_valid: bool
    upper_rpm: int
    lower_rpm: int
    pitch_deg: float
    feed_feedback_supported: bool
    last_feed_command_id: str
    feed_result_valid: bool
    feed_succeeded: bool
    received_monotonic_s: float


@dataclass(frozen=True)
class GateConfig:
    localization_timeout_s: float = 0.8
    launcher_state_timeout_s: float = 0.8
    yaw_tolerance_deg: float = 5.0
    linear_speed_limit_mps: float = 0.20
    angular_speed_limit_radps: float = 0.10
    rpm_tolerance_ratio: float = 0.15
    pitch_tolerance_deg: float = 3.0
    position_tolerance_m: float = 0.50


@dataclass(frozen=True)
class GateResult:
    ready: bool
    robot_fresh: bool
    launcher_fresh: bool
    yaw_ready: bool
    stopped: bool
    rpm_ready: bool
    pitch_ready: bool
    position_ready: bool
    yaw_error_deg: float
    upper_error_ratio: float
    lower_error_ratio: float
    pitch_error_deg: float
    position_error_m: float
    detail: str


def evaluate_gates(now_s: float, robot: RobotSample | None, launcher: LauncherSample | None,
                   target_yaw_rad: float, upper_target_rpm: int, lower_target_rpm: int,
                   pitch_target_deg: float, config: GateConfig,
                   planned_robot_x_m: float | None = None,
                   planned_robot_y_m: float | None = None) -> GateResult:
    robot_fresh = bool(robot and robot.valid and now_s - robot.received_monotonic_s <= config.localization_timeout_s)
    launcher_fresh = bool(
        launcher and launcher.online and launcher.rpm_valid and launcher.pitch_valid
        and now_s - launcher.received_monotonic_s <= config.launcher_state_timeout_s
    )
    yaw_error = math.inf
    stopped = yaw_ready = False
    position_ready = planned_robot_x_m is None or planned_robot_y_m is None
    position_error = 0.0 if position_ready else math.inf
    if robot_fresh and robot:
        yaw_error = abs(math.degrees(wrap_angle_rad(robot.yaw_rad - target_yaw_rad)))
        yaw_ready = yaw_error <= config.yaw_tolerance_deg
        stopped = (
            math.hypot(robot.vx_mps, robot.vy_mps) <= config.linear_speed_limit_mps
            and abs(robot.yaw_rate_radps) <= config.angular_speed_limit_radps
        )
        if planned_robot_x_m is not None and planned_robot_y_m is not None:
            position_error = math.hypot(
                robot.x_m - float(planned_robot_x_m),
                robot.y_m - float(planned_robot_y_m),
            )
            position_ready = position_error <= config.position_tolerance_m
    upper_error = lower_error = math.inf
    pitch_error = math.inf
    rpm_ready = pitch_ready = False
    if launcher_fresh and launcher:
        upper_error = abs(launcher.upper_rpm - upper_target_rpm) / max(abs(upper_target_rpm), 1)
        lower_error = abs(launcher.lower_rpm - lower_target_rpm) / max(abs(lower_target_rpm), 1)
        pitch_error = abs(launcher.pitch_deg - pitch_target_deg)
        rpm_ready = upper_error <= config.rpm_tolerance_ratio and lower_error <= config.rpm_tolerance_ratio
        pitch_ready = pitch_error <= config.pitch_tolerance_deg
    ready = (
        robot_fresh and launcher_fresh and yaw_ready and stopped
        and rpm_ready and pitch_ready and position_ready
    )
    failed = []
    for ok, name in (
        (robot_fresh, "ROBOT_STATE_STALE"), (launcher_fresh, "LAUNCHER_STATE_STALE"),
        (yaw_ready, "YAW_NOT_READY"), (stopped, "ROBOT_MOVING"),
        (position_ready, "ROBOT_POSITION_CHANGED"),
        (rpm_ready, "RPM_NOT_READY"), (pitch_ready, "PITCH_NOT_READY"),
    ):
        if not ok:
            failed.append(name)
    return GateResult(
        ready, robot_fresh, launcher_fresh, yaw_ready, stopped, rpm_ready, pitch_ready,
        position_ready, yaw_error, upper_error, lower_error, pitch_error, position_error,
        "OK" if ready else ",".join(failed),
    )

