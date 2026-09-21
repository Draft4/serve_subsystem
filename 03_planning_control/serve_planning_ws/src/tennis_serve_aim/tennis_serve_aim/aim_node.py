"""Plan the heading for a serve from the robot's current position."""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from tennis_serve_interfaces.srv import PlanAim

from tennis_serve_common.core import (
    localization_to_court_xy,
    target_yaw_from_court_delta,
    validate_absolute_target,
)


class ServeAimNode(Node):
    def __init__(self) -> None:
        super().__init__("serve_aim_node")
        self.create_service(PlanAim, "/tennis/serve/plan_aim", self._plan)

    def _plan(self, request, response):
        try:
            validate_absolute_target(request.target)
            x_m, y_m = localization_to_court_xy(
                request.robot_x_m, request.robot_y_m)
            response.target_yaw_rad = target_yaw_from_court_delta(
                request.target.center_x_m - x_m,
                request.target.center_y_m - y_m,
            )
            response.ok = True
            response.code = "READY"
            response.message = "serve heading planned"
        except ValueError as exc:
            response.code = "PLAN_REJECTED"
            response.message = str(exc)
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ServeAimNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
