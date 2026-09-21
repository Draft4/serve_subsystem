import math

from tennis_serve_common.core import (
    RobotSample, clamp_with_tolerance,
    court_to_legacy_model_y, legacy_target_to_court,
    localization_to_court_xy, observation_received_monotonic,
    target_yaw_from_court_delta, validate_absolute_target,
)
from tennis_serve_supervisor.gates import GateConfig, LauncherSample, evaluate_gates


class Target:
    center_x_m = 5.485
    center_y_m = 16.77
    width_m = 1.0
    depth_m = 1.0
    net_height_min_m = 1.7
    net_height_max_m = 2.1


def test_legacy_target_is_converted_once_and_new_target_is_valid():
    assert legacy_target_to_court(0.0, 7.0) == (5.485, 16.77)
    assert legacy_target_to_court(-5.485, 11.885) == (0.0, 11.885)
    validate_absolute_target(Target())


def test_left_corner_robot_localization_is_already_in_court_frame():
    assert localization_to_court_xy(0.0, 0.0) == (0.0, 0.0)
    assert localization_to_court_xy(5.485, 1.0) == (5.485, 1.0)
    assert localization_to_court_xy(10.97, 2.0) == (10.97, 2.0)
    robot_x, robot_y = localization_to_court_xy(5.485, 0.0)
    assert target_yaw_from_court_delta(5.485 - robot_x, 16.77 - robot_y) == 0.0


def test_non_finite_localization_age_is_rejected():
    try:
        observation_received_monotonic(10.0, math.nan)
    except ValueError:
        pass
    else:
        raise AssertionError("NaN observation age must be rejected")


def test_live_court_y_is_flipped_only_at_the_frozen_model_boundary():
    assert court_to_legacy_model_y(0.0) == 23.77
    assert court_to_legacy_model_y(11.885) == 11.885
    assert court_to_legacy_model_y(16.77) == 7.0
    assert court_to_legacy_model_y(23.77) == 0.0


def test_screenshot_target_is_valid_in_court_origin_v2():
    """Regression for the 2026-09-18 operator screenshot."""
    target = type("ScreenshotTarget", (), {
        "center_x_m": 5.485,
        "center_y_m": 16.07,
        "width_m": 1.0,
        "depth_m": 0.8,
        "net_height_min_m": 1.75,
        "net_height_max_m": 2.05,
    })()
    validate_absolute_target(target)
    assert math.isclose(court_to_legacy_model_y(16.47), 7.3)
    assert math.isclose(court_to_legacy_model_y(15.67), 8.1)


def test_robot_yaw_is_zero_forward_and_counter_clockwise_positive():
    assert math.isclose(target_yaw_from_court_delta(0.0, 1.0), 0.0)
    assert math.isclose(target_yaw_from_court_delta(-1.0, 0.0), math.pi / 2.0)
    assert math.isclose(target_yaw_from_court_delta(1.0, 0.0), -math.pi / 2.0)
    assert math.isclose(abs(target_yaw_from_court_delta(0.0, -1.0)), math.pi)


def test_small_localization_boundary_noise_is_clamped():
    assert clamp_with_tolerance(-0.1, 0.0, 10.97, 0.5, "x") == 0.0
    assert clamp_with_tolerance(-0.2, 0.0, 6.4, 0.5, "y") == 0.0
    try:
        clamp_with_tolerance(-0.6, 0.0, 6.4, 0.5, "y")
    except ValueError:
        pass
    else:
        raise AssertionError("large coordinate errors must still be rejected")


def test_relaxed_gates_pass_only_with_fresh_matching_feedback():
    now = 100.0
    robot = RobotSample(5.485, 1.0, math.pi / 2, 0.02, 0.01, 0.01, True, now)
    launcher = LauncherSample(
        True, True, True, 2090, 1810, 21.5,
        False, "", False, False, now,
    )
    result = evaluate_gates(
        now, robot, launcher, math.pi / 2, 2000, 1800, 20.0, GateConfig())
    assert result.ready
    stale = evaluate_gates(
        now + 0.81, robot, launcher, math.pi / 2, 2000, 1800, 20.0, GateConfig())
    assert not stale.ready
    assert not stale.robot_fresh
    assert not stale.launcher_fresh


def test_position_drift_blocks_feed():
    now = 5.0
    robot = RobotSample(6.1, 1.0, 0.0, 0.0, 0.0, 0.0, True, now)
    launcher = LauncherSample(
        True, True, True, 2000, 1800, 20.0,
        False, "", False, False, now,
    )
    result = evaluate_gates(
        now, robot, launcher, 0.0, 2000, 1800, 20.0, GateConfig(),
        planned_robot_x_m=5.485, planned_robot_y_m=1.0)
    assert not result.ready
    assert not result.position_ready
    assert result.detail == "ROBOT_POSITION_CHANGED"


def test_each_gate_boundary_can_block_feed():
    now = 5.0
    robot = RobotSample(5.0, 1.0, math.radians(6.0), 0.0, 0.0, 0.0, True, now)
    launcher = LauncherSample(
        True, True, True, 2000, 1800, 20.0,
        False, "", False, False, now,
    )
    result = evaluate_gates(now, robot, launcher, 0.0, 2000, 1800, 20.0, GateConfig())
    assert not result.ready
    assert not result.yaw_ready
