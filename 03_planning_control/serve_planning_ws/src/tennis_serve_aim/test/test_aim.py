import math

from tennis_serve_interfaces.srv import PlanAim
from tennis_serve_aim.aim_node import ServeAimNode


def _request():
    request = PlanAim.Request()
    request.request_id = "test"
    request.target.center_x_m = 5.485
    request.target.center_y_m = 16.77
    request.target.width_m = 1.0
    request.target.depth_m = 1.0
    request.target.net_height_min_m = 1.7
    request.target.net_height_max_m = 2.1
    request.robot_x_m = 5.485
    request.robot_y_m = 0.0
    return request


def test_heading_uses_current_robot_position():
    request = _request()
    response = ServeAimNode._plan(None, request, PlanAim.Response())
    assert response.ok
    assert response.target_yaw_rad == 0.0

    request.robot_x_m = 6.485
    response = ServeAimNode._plan(None, request, PlanAim.Response())
    assert response.ok
    assert math.isclose(response.target_yaw_rad, math.atan2(1.0, 16.77))


def test_invalid_target_is_rejected():
    request = _request()
    request.target.center_y_m = 1.0
    response = ServeAimNode._plan(None, request, PlanAim.Response())
    assert not response.ok
    assert response.code == "PLAN_REJECTED"
