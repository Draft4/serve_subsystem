"""Manual ROS integration fixture. Never install or launch in production."""

from __future__ import annotations

import math

import rclpy
from rclpy.node import Node
from tennisbot_interfaces.msg import RobotState
from tennis_serve_interfaces.msg import (
    ChassisAimCommand, FeedCommand, LauncherSetpoint, LauncherState,
)


class ManualFakeIoNode(Node):
    """Mimics only the external ROS contract for bench tests without a ball."""

    def __init__(self) -> None:
        super().__init__("manual_fake_tennis_io")
        self.declare_parameter("publish_robot_state", False)
        self.publish_robot_state = bool(self.get_parameter("publish_robot_state").value)
        self.yaw = 0.0
        self.upper_rpm = 0
        self.lower_rpm = 0
        self.pitch_deg = 0.0
        self.enabled = False
        self.sequence = 0
        self.feed_ids = set()
        self.robot_pub = (self.create_publisher(
            RobotState, "/localization/robot_state", 10)
            if self.publish_robot_state else None)
        self.launcher_pub = self.create_publisher(
            LauncherState, "/tennis/launcher/state", 10)
        self.create_subscription(
            ChassisAimCommand, "/tennis/chassis/aim_command", self._aim, 10)
        self.create_subscription(
            LauncherSetpoint, "/tennis/launcher/setpoint", self._setpoint, 10)
        self.create_subscription(
            FeedCommand, "/tennis/launcher/feed_command", self._feed, 10)
        self.create_timer(0.05, self._publish)
        self.get_logger().warning(
            "TEST FIXTURE ONLY: no CAN/F407 output; do not install in production")

    def _aim(self, message: ChassisAimCommand) -> None:
        if message.active:
            self.yaw = float(message.target_yaw_rad)

    def _setpoint(self, message: LauncherSetpoint) -> None:
        self.enabled = bool(message.enabled)
        self.upper_rpm = int(message.upper_target_rpm) if self.enabled else 0
        self.lower_rpm = int(message.lower_target_rpm) if self.enabled else 0
        self.pitch_deg = float(message.pitch_target_deg) if self.enabled else 0.0

    def _feed(self, message: FeedCommand) -> None:
        if message.command_id in self.feed_ids:
            self.get_logger().error("DUPLICATE FEED ID: %s", message.command_id)
            return
        self.feed_ids.add(message.command_id)
        self.get_logger().info("feed trigger %s (timed/unconfirmed)", message.command_id)

    def _publish(self) -> None:
        stamp = self.get_clock().now().to_msg()
        robot = RobotState()
        robot.header.stamp = stamp
        robot.header.frame_id = "court"
        robot.state = [0.0, 0.5, self.yaw, 0.0, 0.0, 0.0, 0.0, 0.0]
        robot.valid = True
        if self.robot_pub is not None:
            self.robot_pub.publish(robot)

        launcher = LauncherState()
        launcher.header.stamp = stamp
        launcher.interface_version = 1
        self.sequence += 1
        launcher.sequence = self.sequence
        launcher.online = True
        launcher.rpm_valid = True
        launcher.pitch_valid = True
        launcher.upper_actual_rpm = self.upper_rpm
        launcher.lower_actual_rpm = self.lower_rpm
        launcher.pitch_actual_deg = self.pitch_deg
        launcher.feed_feedback_supported = False
        launcher.detail = "MANUAL_TEST_FIXTURE"
        self.launcher_pub.publish(launcher)


def main() -> None:
    rclpy.init()
    node = ManualFakeIoNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
