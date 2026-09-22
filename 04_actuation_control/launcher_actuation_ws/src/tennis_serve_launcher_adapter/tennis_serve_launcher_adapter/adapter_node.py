"""Adapter between tennis_serve strategy topics and launcher hardware topics."""

from __future__ import annotations

import math
import time
from collections import deque

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from tennis_serve_interfaces.msg import FeedCommand, LauncherSetpoint, LauncherState
from tennisbot_launcher.msg import (
    LauncherFeederCommand,
    LauncherFeederState,
    LauncherPitchCommand,
    LauncherWheelCommand,
    LauncherWheelState,
)

from .adapter_core import (
    FeedResultTracker,
    feedback_directions_match,
    map_feedback,
    map_targets,
)


INTERFACE_VERSION = 1
FEEDER_FAULT_STATE = 7


class ServeLauncherAdapterNode(Node):
    def __init__(self) -> None:
        super().__init__("serve_launcher_adapter_node")
        defaults = {
            "setpoint_topic": "/tennis/launcher/setpoint",
            "feed_command_topic": "/tennis/launcher/feed_command",
            "state_topic": "/tennis/launcher/state",
            "wheel_command_topic": "/launcher/wheels/command",
            "wheel_state_topic": "/launcher/wheels/state",
            "pitch_command_topic": "/launcher/pitch/command",
            "feeder_command_topic": "/launcher/feeder/command",
            "feeder_state_topic": "/launcher/feeder/state",
            "upper_motor": 1,
            "motor1_sign": 1,
            "motor2_sign": -1,
            "max_rpm": 7857,
            "min_pitch_deg": 0.0,
            "max_pitch_deg": 90.0,
            "wheel_command_timeout_ms": 1000,
            "setpoint_receive_timeout_s": 1.2,
            "pitch_move_time_ms": 1000,
            "enforce_feedback_direction": True,
            "direction_check_min_rpm": 100.0,
            "hardware_state_timeout_s": 1.0,
            "feed_result_timeout_s": 8.0,
            "command_rate_hz": 10.0,
            "state_rate_hz": 25.0,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

        self.upper_motor = int(self.get_parameter("upper_motor").value)
        self.motor1_sign = int(self.get_parameter("motor1_sign").value)
        self.motor2_sign = int(self.get_parameter("motor2_sign").value)
        self.max_rpm = int(self.get_parameter("max_rpm").value)
        self.min_pitch_deg = float(self.get_parameter("min_pitch_deg").value)
        self.max_pitch_deg = float(self.get_parameter("max_pitch_deg").value)
        self.wheel_timeout_ms = int(
            self.get_parameter("wheel_command_timeout_ms").value)
        self.setpoint_receive_timeout_s = float(
            self.get_parameter("setpoint_receive_timeout_s").value)
        self.pitch_move_ms = int(self.get_parameter("pitch_move_time_ms").value)
        self.enforce_feedback_direction = bool(
            self.get_parameter("enforce_feedback_direction").value)
        self.direction_check_min_rpm = float(
            self.get_parameter("direction_check_min_rpm").value)
        self.state_timeout_s = float(
            self.get_parameter("hardware_state_timeout_s").value)
        self.feed_tracker = FeedResultTracker(
            float(self.get_parameter("feed_result_timeout_s").value))
        map_targets(0, 0, self.upper_motor, self.motor1_sign, self.motor2_sign)
        if (self.max_rpm <= 0 or self.wheel_timeout_ms < 100
                or self.setpoint_receive_timeout_s <= 0.0
                or not self.min_pitch_deg < self.max_pitch_deg):
            raise ValueError("invalid launcher adapter limits")
        if self.direction_check_min_rpm < 0.0:
            raise ValueError("direction_check_min_rpm must be non-negative")
        self._validate_hardware_interfaces()
        self.get_logger().info(
            "pitch feedback is disabled; using commanded pitch without a feedback gate")

        self.wheel_pub = self.create_publisher(
            LauncherWheelCommand,
            str(self.get_parameter("wheel_command_topic").value), 10)
        self.pitch_pub = self.create_publisher(
            LauncherPitchCommand,
            str(self.get_parameter("pitch_command_topic").value), 10)
        self.feeder_pub = self.create_publisher(
            LauncherFeederCommand,
            str(self.get_parameter("feeder_command_topic").value), 10)
        self.state_pub = self.create_publisher(
            LauncherState, str(self.get_parameter("state_topic").value),
            qos_profile_sensor_data)

        self.create_subscription(
            LauncherSetpoint,
            str(self.get_parameter("setpoint_topic").value),
            self._setpoint_callback, 10)
        self.create_subscription(
            FeedCommand,
            str(self.get_parameter("feed_command_topic").value),
            self._feed_callback, 10)
        self.create_subscription(
            LauncherWheelState,
            str(self.get_parameter("wheel_state_topic").value),
            self._wheel_callback, qos_profile_sensor_data)
        self.create_subscription(
            LauncherFeederState,
            str(self.get_parameter("feeder_state_topic").value),
            self._feeder_callback, qos_profile_sensor_data)

        self.setpoint = None
        self.setpoint_deadline_ns = 0
        self.setpoint_monotonic_deadline_s = 0.0
        self.last_target_key = None
        self.pitch_target_deg = 0.0
        self.wheel_state = None
        self.feeder_state = None
        self.wheel_received_s = 0.0
        self.feeder_received_s = 0.0
        self.sequence = 0
        self.stop_sent = True
        self.seen_feed_ids = set()
        self.seen_feed_order = deque()

        command_rate = float(self.get_parameter("command_rate_hz").value)
        state_rate = float(self.get_parameter("state_rate_hz").value)
        if command_rate <= 0.0 or state_rate <= 0.0:
            raise ValueError("adapter rates must be positive")
        self.create_timer(1.0 / command_rate, self._publish_command)
        self.create_timer(1.0 / state_rate, self._publish_state)

    @staticmethod
    def _time_ns(value) -> int:
        return int(value.sec) * 1_000_000_000 + int(value.nanosec)

    @staticmethod
    def _require_fields(message_type, fields) -> None:
        available = set(message_type.get_fields_and_field_types())
        missing = sorted(set(fields) - available)
        if missing:
            raise RuntimeError(
                f"{message_type.__name__} is incompatible; missing fields: "
                + ", ".join(missing))

    def _validate_hardware_interfaces(self) -> None:
        self._require_fields(
            LauncherWheelCommand,
            {"header", "enable", "left_rpm", "right_rpm", "timeout_ms"})
        self._require_fields(
            LauncherWheelState,
            {"feedback_valid", "measured_left_rpm", "measured_right_rpm",
             "left_fault_valid", "right_fault_valid", "left_fault",
             "right_fault", "error"})
        self._require_fields(
            LauncherPitchCommand,
            {"header", "position_degrees", "move_time_ms"})
        self._require_fields(LauncherFeederCommand, {"header", "command"})
        self._require_fields(
            LauncherFeederState,
            {"valid", "completed_count", "state", "result", "error"})
        if not hasattr(LauncherFeederCommand, "FEED"):
            raise RuntimeError("LauncherFeederCommand is incompatible; FEED is missing")

    def _setpoint_callback(self, message: LauncherSetpoint) -> None:
        if message.interface_version != INTERFACE_VERSION:
            self.get_logger().error(
                f"ignored launcher setpoint with version {message.interface_version}")
            return
        if (message.upper_target_rpm < 0 or message.lower_target_rpm < 0
                or message.upper_target_rpm > self.max_rpm
                or message.lower_target_rpm > self.max_rpm
                or not math.isfinite(message.pitch_target_deg)
                or not self.min_pitch_deg <= message.pitch_target_deg <= self.max_pitch_deg):
            self.get_logger().error(
                f"ignored invalid launcher setpoint {message.command_id}")
            return
        self.setpoint = message
        self.setpoint_deadline_ns = self._time_ns(message.valid_until)
        stamp_ns = self._time_ns(message.header.stamp)
        declared_lifetime_s = max(
            0.0, (self.setpoint_deadline_ns - stamp_ns) / 1_000_000_000.0)
        self.setpoint_monotonic_deadline_s = time.monotonic() + min(
            declared_lifetime_s, self.setpoint_receive_timeout_s)
        key = (
            message.command_id,
            int(message.upper_target_rpm),
            int(message.lower_target_rpm),
            round(float(message.pitch_target_deg), 4),
            bool(message.enabled),
        )
        if message.enabled and key != self.last_target_key:
            pitch = LauncherPitchCommand()
            pitch.header.stamp = self.get_clock().now().to_msg()
            pitch.position_degrees = float(message.pitch_target_deg)
            pitch.move_time_ms = self.pitch_move_ms
            self.pitch_pub.publish(pitch)
            self.pitch_target_deg = float(message.pitch_target_deg)
        self.last_target_key = key

    def _reject_feed(self, message: FeedCommand, detail: str, now_s: float) -> None:
        completed = (
            int(self.feeder_state.completed_count)
            if self.feeder_state is not None else 0)
        self.feed_tracker.start(message.command_id, completed, now_s)
        self.feed_tracker.result_valid = True
        self.feed_tracker.succeeded = False
        self.feed_tracker.detail = detail

    def _feed_callback(self, message: FeedCommand) -> None:
        if (message.interface_version != INTERFACE_VERSION
                or message.action != FeedCommand.ACTION_FIRE
                or not message.command_id):
            return
        if message.command_id in self.seen_feed_ids:
            return
        self.seen_feed_ids.add(message.command_id)
        self.seen_feed_order.append(message.command_id)
        while len(self.seen_feed_order) > 128:
            self.seen_feed_ids.discard(self.seen_feed_order.popleft())

        now_s = time.monotonic()
        valid_until_ns = self._time_ns(message.valid_until)
        if valid_until_ns <= 0 or self.get_clock().now().nanoseconds > valid_until_ns:
            self._reject_feed(message, "FEED_REJECTED_COMMAND_EXPIRED", now_s)
            return
        if (not self._setpoint_active() or self.setpoint is None
                or self.setpoint.job_id != message.job_id
                or self.setpoint.shot_id != message.shot_id):
            self._reject_feed(message, "FEED_REJECTED_NO_MATCHING_SETPOINT", now_s)
            return
        # The current feeder hardware does not provide a usable state
        # feedback channel.  The command is therefore forwarded and the
        # supervisor uses a timed dwell instead of waiting for confirmation.
        completed_count = (
            int(self.feeder_state.completed_count)
            if self.feeder_state is not None else 0)
        self.feed_tracker.start(message.command_id, completed_count, now_s)
        command = LauncherFeederCommand()
        command.header.stamp = self.get_clock().now().to_msg()
        command.command = LauncherFeederCommand.FEED
        self.feeder_pub.publish(command)

    def _wheel_callback(self, message: LauncherWheelState) -> None:
        self.wheel_state = message
        self.wheel_received_s = time.monotonic()

    def _feeder_callback(self, message: LauncherFeederState) -> None:
        self.feeder_state = message
        self.feeder_received_s = time.monotonic()
        self.feed_tracker.update(
            int(message.completed_count), int(message.state),
            int(message.result), message.error, time.monotonic())

    def _setpoint_active(self) -> bool:
        if self.setpoint is None or not self.setpoint.enabled:
            return False
        return (
            self.setpoint_deadline_ns > 0
            and self.get_clock().now().nanoseconds <= self.setpoint_deadline_ns
            and time.monotonic() <= self.setpoint_monotonic_deadline_s
        )

    def _publish_command(self) -> None:
        active = self._setpoint_active()
        if not active:
            if not self.stop_sent:
                command = LauncherWheelCommand()
                command.header.stamp = self.get_clock().now().to_msg()
                command.enable = False
                command.timeout_ms = self.wheel_timeout_ms
                self.wheel_pub.publish(command)
                self.stop_sent = True
            return
        left, right = map_targets(
            int(self.setpoint.upper_target_rpm),
            int(self.setpoint.lower_target_rpm),
            self.upper_motor, self.motor1_sign, self.motor2_sign)
        command = LauncherWheelCommand()
        command.header.stamp = self.get_clock().now().to_msg()
        command.enable = True
        command.left_rpm = left
        command.right_rpm = right
        command.timeout_ms = self.wheel_timeout_ms
        self.wheel_pub.publish(command)
        self.stop_sent = False

    def _publish_state(self) -> None:
        now = time.monotonic()
        self.feed_tracker.tick(now)
        wheel_fresh = (
            self.wheel_state is not None
            and now - self.wheel_received_s <= self.state_timeout_s)
        feeder_fresh = (
            self.feeder_state is not None
            and now - self.feeder_received_s <= self.state_timeout_s)

        wheel_valid = bool(wheel_fresh and self.wheel_state.feedback_valid)
        direction_valid = True
        if (wheel_valid and self.enforce_feedback_direction
                and self._setpoint_active()):
            motor1_target, motor2_target = map_targets(
                int(self.setpoint.upper_target_rpm),
                int(self.setpoint.lower_target_rpm),
                self.upper_motor, self.motor1_sign, self.motor2_sign)
            direction_valid = feedback_directions_match(
                float(self.wheel_state.measured_left_rpm),
                float(self.wheel_state.measured_right_rpm),
                motor1_target, motor2_target, self.direction_check_min_rpm)
            wheel_valid = wheel_valid and direction_valid

        using_commanded_pitch = self._setpoint_active()
        feeder_valid = bool(
            feeder_fresh and self.feeder_state.valid
            and self.feeder_state.state != FEEDER_FAULT_STATE
            and not self.feeder_state.error)

        upper_rpm = lower_rpm = 0
        if wheel_valid:
            upper_rpm, lower_rpm = map_feedback(
                self.wheel_state.measured_left_rpm,
                self.wheel_state.measured_right_rpm,
                self.upper_motor)

        state = LauncherState()
        state.header.stamp = self.get_clock().now().to_msg()
        state.interface_version = INTERFACE_VERSION
        self.sequence += 1
        state.sequence = self.sequence
        state.online = wheel_fresh
        state.rpm_valid = wheel_valid
        state.pitch_valid = using_commanded_pitch
        state.upper_actual_rpm = upper_rpm
        state.lower_actual_rpm = lower_rpm
        if using_commanded_pitch:
            state.pitch_actual_deg = self.pitch_target_deg
        else:
            state.pitch_actual_deg = 0.0
        state.feed_feedback_supported = True
        state.last_feed_command_id = self.feed_tracker.command_id
        state.feed_result_valid = self.feed_tracker.result_valid
        state.feed_succeeded = self.feed_tracker.succeeded
        details = []
        if not wheel_fresh:
            details.append("WHEEL_STATE_STALE")
        elif not wheel_valid:
            details.append(
                "WHEEL_DIRECTION_MISMATCH"
                if not direction_valid else "WHEEL_STATE_INVALID")
        if using_commanded_pitch:
            details.append("PITCH_COMMAND_ASSUMED")
        if not feeder_fresh:
            details.append("FEEDER_STATE_STALE")
        elif not feeder_valid:
            details.append(
                "FEEDER_STATE_INVALID"
                f"_STATE_{int(self.feeder_state.state)}"
                f"_RESULT_{int(self.feeder_state.result)}")
        if self.feed_tracker.command_id:
            details.append(self.feed_tracker.detail)
        state.detail = "OK" if not details else ",".join(details)
        self.state_pub.publish(state)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ServeLauncherAdapterNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
