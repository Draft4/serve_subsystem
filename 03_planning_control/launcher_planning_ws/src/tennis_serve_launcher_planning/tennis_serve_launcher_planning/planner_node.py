from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from tennisbot_interfaces.msg import RobotState
from tennis_serve_interfaces.msg import PlannedShot
from tennis_serve_interfaces.srv import GetModelInfo, PlanAim, PlanShot

from tennis_serve_common.core import (
    INTERFACE_VERSION, RobotSample, localization_to_court_xy,
    observation_received_monotonic,
)
from .model_service import ModelError, ModelService


class ServePlannerNode(Node):
    def __init__(self) -> None:
        super().__init__("serve_planner_node")
        self.declare_parameter("robot_state_topic", "/localization/robot_state")
        self.declare_parameter("localization_timeout_s", 1.0)
        self.declare_parameter("machine_boundary_tolerance_m", 1.0)
        model_dir = Path(get_package_share_directory(
            "tennis_serve_launcher_planning")) / "data" / "fire_ball"
        self.declare_parameter(
            "model_path", str(model_dir / "model_snapshot.json")
        )
        self.timeout_s = float(self.get_parameter("localization_timeout_s").value)
        self.model = ModelService(
            str(self.get_parameter("model_path").value),
            float(self.get_parameter("machine_boundary_tolerance_m").value),
        )
        self.robot = None
        self._group = ReentrantCallbackGroup()
        self._aim_client = self.create_client(
            PlanAim, "/tennis/serve/plan_aim", callback_group=self._group)
        self.create_subscription(
            RobotState,
            str(self.get_parameter("robot_state_topic").value),
            self._robot_callback,
            qos_profile_sensor_data, callback_group=self._group,
        )
        self.create_service(
            PlanShot, "/tennis/serve/plan_shot", self._plan, callback_group=self._group)
        self.create_service(
            GetModelInfo, "/tennis/serve/model_info", self._model_info,
            callback_group=self._group)

    def _robot_callback(self, message: RobotState) -> None:
        if len(message.state) < 6:
            return
        try:
            court_x_m, court_y_m = localization_to_court_xy(
                message.state[0], message.state[1])
            received_s = observation_received_monotonic(
                time.monotonic(), message.observation_age_s)
        except ValueError:
            return
        self.robot = RobotSample(
            x_m=court_x_m,
            y_m=court_y_m,
            yaw_rad=float(message.state[2]),
            vx_mps=float(message.state[3]),
            vy_mps=float(message.state[4]),
            yaw_rate_radps=float(message.state[5]),
            valid=bool(message.valid),
            received_monotonic_s=received_s,
        )

    def _model_info(self, _request, response):
        try:
            metadata = self.model.metadata()
            response.ready = True
            response.code = "READY"
            response.message = "model ready"
            response.model_version = metadata["model_version"]
            response.model_sha256 = metadata["model_sha256"]
            response.metadata_json = json.dumps(
                metadata, ensure_ascii=False, separators=(",", ":")
            )
        except ModelError as exc:
            response.ready = False
            response.code = "MODEL_NOT_READY"
            response.message = str(exc)
        return response

    def _plan(self, request, response):
        if not request.request_id:
            response.ok = False
            response.code = "INVALID_REQUEST"
            response.message = "request_id is required"
            return response
        robot = self.robot
        if (
            robot is None
            or not robot.valid
            or time.monotonic() - robot.received_monotonic_s > self.timeout_s
        ):
            response.ok = False
            response.code = "LOCALIZATION_NOT_READY"
            response.message = "robot state is missing, invalid or stale"
            return response
        try:
            if not self._aim_client.wait_for_service(timeout_sec=0.5):
                raise ModelError("serve aim service is unavailable")
            aim_request = PlanAim.Request()
            aim_request.request_id = request.request_id
            aim_request.target = request.target
            aim_request.robot_x_m = robot.x_m
            aim_request.robot_y_m = robot.y_m
            done = threading.Event()
            future = self._aim_client.call_async(aim_request)
            future.add_done_callback(lambda _future: done.set())
            if not done.wait(1.0):
                raise ModelError("serve aim service timed out")
            aim = future.result()
            if not aim.ok:
                raise ModelError(f"{aim.code}: {aim.message}")
            result = self.model.plan(
                request.request_id, request.step_id, request.target, robot
            )
            shot = self._shot_message(request, result, aim.target_yaw_rad)
            response.ok = True
            response.code = "READY"
            response.message = "shot planned from live localization"
            response.shot = shot
        except (ModelError, ValueError) as exc:
            response.ok = False
            response.code = "PLAN_REJECTED"
            response.message = str(exc)
        return response

    def _shot_message(self, request, result, target_yaw_rad):
        shot = PlannedShot()
        shot.header.stamp = self.get_clock().now().to_msg()
        shot.header.frame_id = "court"
        shot.interface_version = INTERFACE_VERSION
        shot.request_id = request.request_id
        shot.step_id = request.step_id
        shot.target = request.target
        shot.target_yaw_rad = target_yaw_rad
        for name in (
            "robot_x_m",
            "robot_y_m",
            "robot_yaw_rad",
            "upper_target_rpm",
            "lower_target_rpm",
            "pitch_target_deg",
            "success_probability",
            "confidence",
            "landing_median_m",
            "landing_p05_m",
            "landing_p95_m",
            "net_height_median_m",
            "net_height_p05_m",
            "net_height_p95_m",
            "model_version",
            "model_sha256",
        ):
            setattr(shot, name, result[name])
        return shot

def main(args=None) -> None:
    rclpy.init(args=args)
    node = ServePlannerNode()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
