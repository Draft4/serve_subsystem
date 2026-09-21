"""Pure domain rules shared by ROS nodes and unit tests."""

from __future__ import annotations

import math
from dataclasses import dataclass

COURT_WIDTH_M = 10.97
COURT_LENGTH_M = 23.77
COURT_NET_Y_M = 11.885
INTERFACE_VERSION = 1


def wrap_angle_rad(value: float) -> float:
    return (value + math.pi) % (2.0 * math.pi) - math.pi


def observation_received_monotonic(now_s: float, observation_age_s: float) -> float:
    """Return a safe monotonic receive time for a localization observation."""
    age_s = float(observation_age_s)
    if not math.isfinite(age_s):
        raise ValueError("observation_age_s must be finite")
    return float(now_s) - max(age_s, 0.0)


def target_yaw_from_court_delta(delta_x_m: float, delta_y_m: float) -> float:
    """RobotState yaw: court-forward (+Y) is zero; counter-clockwise is positive."""
    return wrap_angle_rad(math.atan2(-float(delta_x_m), float(delta_y_m)))


def centered_to_court_x(centered_x_m: float) -> float:
    """Convert baseline-centred localization X to the left-corner court frame."""
    return centered_x_m + COURT_WIDTH_M / 2.0


def localization_to_court_xy(left_corner_x_m: float, forward_y_m: float) -> tuple[float, float]:
    """Convert RobotState position into the common court_origin_v2 frame.

    RobotState already uses the serving-side left corner as its origin. Its +X
    points right while facing the net and +Y points forward, which is exactly
    the court_origin_v2 convention.
    """
    x_m = float(left_corner_x_m)
    y_m = float(forward_y_m)
    if not math.isfinite(x_m) or not math.isfinite(y_m):
        raise ValueError("localization position must be finite")
    return x_m, y_m


def legacy_target_to_court(centered_x_m: float, legacy_y_m: float) -> tuple[float, float]:
    """Convert protocol v1 target coordinates into the court-origin frame."""
    return centered_to_court_x(centered_x_m), COURT_LENGTH_M - legacy_y_m


def court_to_legacy_model_y(court_y_m: float, court_length_m: float = COURT_LENGTH_M) -> float:
    """Flip only Y when crossing from the live court frame into the frozen model."""
    return float(court_length_m) - float(court_y_m)


def clamp_with_tolerance(value: float, minimum: float, maximum: float,
                         tolerance: float, field: str) -> float:
    """Clamp small localization overshoot while rejecting a genuinely invalid pose."""
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    epsilon = 1e-9
    if value < minimum - tolerance - epsilon or value > maximum + tolerance + epsilon:
        raise ValueError(
            f"{field}={value:.3f} is outside [{minimum:.3f}, {maximum:.3f}] "
            f"with {tolerance:.3f} m tolerance")
    return min(max(value, minimum), maximum)


def validate_with_tolerance(value: float, minimum: float, maximum: float,
                            tolerance: float, field: str) -> float:
    """Validate a value against an expanded range without changing its geometry."""
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    epsilon = 1e-9
    if value < minimum - tolerance - epsilon or value > maximum + tolerance + epsilon:
        raise ValueError(
            f"{field}={value:.3f} is outside [{minimum:.3f}, {maximum:.3f}] "
            f"with {tolerance:.3f} m tolerance")
    return value


def target_bounds(target) -> tuple[float, float, float, float]:
    return (
        target.center_x_m - target.width_m / 2.0,
        target.center_x_m + target.width_m / 2.0,
        target.center_y_m - target.depth_m / 2.0,
        target.center_y_m + target.depth_m / 2.0,
    )


def validate_absolute_target(target) -> None:
    values = (
        target.center_x_m, target.center_y_m, target.width_m, target.depth_m,
        target.net_height_min_m, target.net_height_max_m,
    )
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("target contains a non-finite value")
    x_min, x_max, y_min, y_max = target_bounds(target)
    if target.width_m <= 0.0 or target.depth_m <= 0.0:
        raise ValueError("target dimensions must be positive")
    if (x_min < 0.0 or x_max > COURT_WIDTH_M
            or y_min < COURT_NET_Y_M or y_max > COURT_LENGTH_M):
        raise ValueError(
            "target rectangle must be fully inside the opponent court: "
            "center=({:.3f}, {:.3f}), size=({:.3f}, {:.3f}), "
            "bounds=x[{:.3f}, {:.3f}] y[{:.3f}, {:.3f}], "
            "allowed=x[0.000, {:.3f}] y[{:.3f}, {:.3f}]".format(
                float(target.center_x_m), float(target.center_y_m),
                float(target.width_m), float(target.depth_m),
                x_min, x_max, y_min, y_max,
                COURT_WIDTH_M, COURT_NET_Y_M, COURT_LENGTH_M,
            )
        )
    if not 0.0 < target.net_height_min_m < target.net_height_max_m <= 3.6:
        raise ValueError("net-height range is invalid")


@dataclass(frozen=True)
class RobotSample:
    x_m: float
    y_m: float
    yaw_rad: float
    vx_mps: float
    vy_mps: float
    yaw_rate_radps: float
    valid: bool
    received_monotonic_s: float

