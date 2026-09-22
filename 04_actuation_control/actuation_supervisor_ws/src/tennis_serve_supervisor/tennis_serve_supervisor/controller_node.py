from __future__ import annotations

import math
import threading
import time
import uuid

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from std_msgs.msg import Bool
from tennisbot_interfaces.msg import RobotState
from tennis_serve_interfaces.action import ExecuteShot
from tennis_serve_interfaces.msg import ChassisAimCommand, FeedCommand, LauncherSetpoint, LauncherState
from tennis_serve_interfaces.srv import ResetEmergencyStop, SetLauncherHold

from tennis_serve_common.core import (
    INTERFACE_VERSION, RobotSample, localization_to_court_xy,
    observation_received_monotonic,
)
from .gates import GateConfig, LauncherSample, evaluate_gates


class ServeControllerNode(Node):
    def __init__(self) -> None:
        super().__init__("serve_controller_node")
        defaults = {
            "robot_state_topic": "/localization/robot_state",
            "launcher_state_topic": "/tennis/launcher/state",
            "chassis_aim_topic": "/tennis/chassis/aim_command",
            "launcher_setpoint_topic": "/tennis/launcher/setpoint",
            "feed_command_topic": "/tennis/launcher/feed_command",
            "emergency_stop_topic": "/tennis/emergency_stop",
            "localization_timeout_s": 0.8, "launcher_state_timeout_s": 0.8,
            "yaw_tolerance_deg": 5.0, "linear_speed_limit_mps": 0.20,
            "angular_speed_limit_radps": 0.10, "rpm_tolerance_ratio": 0.15,
            "position_tolerance_m": 0.50,
            "position_mismatch_timeout_s": 0.5,
            "stable_hold_s": 0.20,
            "aim_timeout_s": 30.0, "launcher_ready_timeout_s": 20.0,
            "feed_dwell_s": 1.0,
            "command_validity_s": 1.0, "launcher_hold_lease_s": 2.5,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)
        self.gate_config = GateConfig(**{
            name: float(self.get_parameter(name).value) for name in (
                "localization_timeout_s", "launcher_state_timeout_s", "yaw_tolerance_deg",
                "linear_speed_limit_mps", "angular_speed_limit_radps", "rpm_tolerance_ratio",
                "position_tolerance_m",
            )
        })
        self.stable_hold_s = float(self.get_parameter("stable_hold_s").value)
        self.position_mismatch_timeout_s = float(
            self.get_parameter("position_mismatch_timeout_s").value)
        self.aim_timeout_s = float(self.get_parameter("aim_timeout_s").value)
        self.launcher_timeout_s = float(self.get_parameter("launcher_ready_timeout_s").value)
        self.feed_dwell_s = float(self.get_parameter("feed_dwell_s").value)
        if self.feed_dwell_s <= 0.0:
            raise ValueError("feed timing parameters must be positive")
        self.validity_s = float(self.get_parameter("command_validity_s").value)
        self.hold_lease_s = float(self.get_parameter("launcher_hold_lease_s").value)
        if self.hold_lease_s <= self.validity_s:
            raise ValueError("launcher_hold_lease_s must exceed command_validity_s")
        self.robot = None
        self.launcher = None
        self.emergency_stop = False
        self._active_goal = False
        self._feed_committed = False
        self._goal_lock = threading.Lock()
        self._hold_lock = threading.RLock()
        self._hold_enabled = False
        self._hold_job_id = ""
        self._hold_deadline = 0.0
        self._hold_target = None
        self._launcher_stopped = True
        self._group = ReentrantCallbackGroup()
        command_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST, depth=1,
        )
        estop_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST, depth=1,
        )
        self.aim_pub = self.create_publisher(
            ChassisAimCommand, str(self.get_parameter("chassis_aim_topic").value), command_qos)
        self.setpoint_pub = self.create_publisher(
            LauncherSetpoint, str(self.get_parameter("launcher_setpoint_topic").value), command_qos)
        self.feed_pub = self.create_publisher(
            FeedCommand, str(self.get_parameter("feed_command_topic").value), command_qos)
        self.create_subscription(
            RobotState, str(self.get_parameter("robot_state_topic").value),
            self._robot_callback, qos_profile_sensor_data, callback_group=self._group)
        self.create_subscription(
            LauncherState, str(self.get_parameter("launcher_state_topic").value),
            self._launcher_callback, qos_profile_sensor_data, callback_group=self._group)
        self.create_subscription(
            Bool, str(self.get_parameter("emergency_stop_topic").value),
            self._estop_callback, estop_qos, callback_group=self._group)
        self.create_service(
            SetLauncherHold, "/tennis/serve/set_launcher_hold", self._set_launcher_hold,
            callback_group=self._group)
        self.create_service(
            ResetEmergencyStop, "/tennis/serve/reset_emergency_stop", self._reset_estop,
            callback_group=self._group)
        self.create_timer(0.1, self._refresh_launcher_setpoint, callback_group=self._group)
        self.action_server = ActionServer(
            self, ExecuteShot, "/tennis/serve/execute_shot",
            execute_callback=self._execute,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=self._group,
        )

    def _robot_callback(self, message: RobotState) -> None:
        if len(message.state) >= 6:
            try:
                court_x_m, court_y_m = localization_to_court_xy(
                    message.state[0], message.state[1])
                received_s = observation_received_monotonic(
                    time.monotonic(), message.observation_age_s)
            except ValueError:
                return
            self.robot = RobotSample(
                court_x_m, court_y_m,
                *(float(message.state[index]) for index in range(2, 6)),
                valid=bool(message.valid),
                received_monotonic_s=received_s)

    def _launcher_callback(self, message: LauncherState) -> None:
        if message.interface_version != INTERFACE_VERSION:
            return
        self.launcher = LauncherSample(
            online=message.online, rpm_valid=message.rpm_valid,
            upper_rpm=message.upper_actual_rpm, lower_rpm=message.lower_actual_rpm,
            received_monotonic_s=time.monotonic())

    def _estop_callback(self, message: Bool) -> None:
        if message.data:
            self.emergency_stop = True
            self._publish_chassis_stop("", "")
            self._publish_launcher_stop("", "", "EMERGENCY_STOP")

    def _reset_estop(self, request, response):
        if not request.command_id:
            response.code = "INVALID_REQUEST"
            response.message = "command_id is required"
            return response
        with self._goal_lock:
            if self._active_goal:
                response.code = "RESET_NOT_READY"
                response.message = "cannot reset emergency stop while a shot is active"
                return response
        now = time.monotonic()
        robot = self.robot
        launcher = self.launcher
        robot_ready = bool(
            robot and robot.valid
            and now - robot.received_monotonic_s <= self.gate_config.localization_timeout_s
            and math.hypot(robot.vx_mps, robot.vy_mps) <= self.gate_config.linear_speed_limit_mps
            and abs(robot.yaw_rate_radps) <= self.gate_config.angular_speed_limit_radps)
        launcher_ready = bool(
            launcher and launcher.online
            and now - launcher.received_monotonic_s <= self.gate_config.launcher_state_timeout_s)
        if not robot_ready or not launcher_ready:
            response.code = "RESET_NOT_READY"
            response.message = "fresh stopped robot and online launcher state are required"
            return response
        self.emergency_stop = False
        response.accepted = True
        response.code = "RESET"
        response.message = "emergency stop latch reset"
        return response

    def _set_launcher_hold(self, request, response):
        if not request.command_id:
            response.code = "INVALID_REQUEST"
            response.message = "command_id is required"
            return response
        if request.enabled and not request.job_id:
            response.code = "INVALID_REQUEST"
            response.message = "job_id is required when enabling launcher hold"
            return response
        now = time.monotonic()
        if request.enabled:
            with self._hold_lock:
                stale_target = bool(
                    self._hold_target is not None
                    and (self._hold_deadline <= now
                         or (self._hold_job_id and self._hold_job_id != request.job_id)))
                stale_job_id = self._hold_job_id
                stale_shot_id = (
                    self._hold_target["shot_id"] if self._hold_target is not None else "")
            if stale_target:
                self._publish_launcher_stop(
                    stale_job_id, stale_shot_id, "STALE_HOLD_REPLACED")
            with self._hold_lock:
                if self.emergency_stop:
                    response.code = "EMERGENCY_STOP"
                    response.message = "emergency stop is latched"
                    return response
                if (self._hold_enabled and self._hold_deadline > now
                        and self._hold_job_id and self._hold_job_id != request.job_id):
                    response.code = "HOLD_OWNED_BY_OTHER_JOB"
                    response.message = "launcher hold belongs to another active job"
                    return response
                self._hold_enabled = True
                self._hold_job_id = request.job_id
                self._hold_deadline = now + self.hold_lease_s
            response.accepted = True
            response.code = "HOLD_ENABLED"
            response.message = "launcher hold lease renewed"
            return response
        self._publish_launcher_stop(request.job_id, "", request.reason or "HOLD_DISABLED")
        response.accepted = True
        response.code = "HOLD_DISABLED"
        response.message = "launcher hold disabled"
        return response

    def _goal_callback(self, request) -> GoalResponse:
        with self._goal_lock:
            if self.emergency_stop:
                self.get_logger().error(
                    f"GOAL_REJECTED_EMERGENCY_STOP job_id={request.job_id} "
                    f"shot_id={request.shot_id}: emergency stop is latched")
                return GoalResponse.REJECT
            if self._active_goal:
                self.get_logger().warning(
                    f"GOAL_REJECTED_ACTIVE_GOAL job_id={request.job_id} "
                    f"shot_id={request.shot_id}: another ExecuteShot goal is still active")
                return GoalResponse.REJECT
            with self._hold_lock:
                now = time.monotonic()
                if not self._hold_enabled:
                    self.get_logger().warning(
                        f"GOAL_REJECTED_HOLD_DISABLED job_id={request.job_id} "
                        f"shot_id={request.shot_id}")
                    return GoalResponse.REJECT
                if self._hold_job_id != request.job_id:
                    self.get_logger().warning(
                        f"GOAL_REJECTED_HOLD_OWNER job_id={request.job_id} "
                        f"shot_id={request.shot_id} hold_job_id={self._hold_job_id}")
                    return GoalResponse.REJECT
                if now > self._hold_deadline:
                    self.get_logger().warning(
                        f"GOAL_REJECTED_HOLD_EXPIRED job_id={request.job_id} "
                        f"shot_id={request.shot_id} "
                        f"expired_by_s={now - self._hold_deadline:.3f}")
                    return GoalResponse.REJECT
            self._active_goal = True
            self._feed_committed = False
            return GoalResponse.ACCEPT

    def _cancel_callback(self, _goal) -> CancelResponse:
        with self._goal_lock:
            return CancelResponse.REJECT if self._feed_committed else CancelResponse.ACCEPT

    def _deadline(self):
        return (self.get_clock().now() + Duration(seconds=self.validity_s)).to_msg()

    def _publish_aim_target(self, job_id: str, shot_id: str, shot) -> None:
        stamp = self.get_clock().now().to_msg()
        command_id = "target-" + shot_id
        aim = ChassisAimCommand()
        aim.header.stamp = stamp; aim.header.frame_id = "court"
        aim.interface_version = INTERFACE_VERSION; aim.job_id = job_id; aim.shot_id = shot_id
        aim.command_id = command_id; aim.target_yaw_rad = shot.target_yaw_rad
        aim.active = True; aim.valid_until = self._deadline()
        self.aim_pub.publish(aim)

    def _set_launcher_target(self, job_id: str, shot_id: str, shot) -> bool:
        with self._hold_lock:
            if (not self._hold_enabled or self._hold_job_id != job_id
                    or time.monotonic() > self._hold_deadline):
                return False
            self._hold_target = {
                "job_id": job_id,
                "shot_id": shot_id,
                "command_id": "target-" + shot_id,
                "upper_target_rpm": int(shot.upper_target_rpm),
                "lower_target_rpm": int(shot.lower_target_rpm),
                "pitch_target_deg": float(shot.pitch_target_deg),
            }
            self._launcher_stopped = False
        self._refresh_launcher_setpoint()
        return True

    def _refresh_launcher_setpoint(self) -> None:
        expired = False
        expired_job_id = ""
        expired_shot_id = ""
        with self._hold_lock:
            if not self._hold_enabled or self._hold_target is None:
                return
            if time.monotonic() > self._hold_deadline:
                expired = True
                expired_job_id = self._hold_job_id
                expired_shot_id = self._hold_target["shot_id"]
            else:
                target = dict(self._hold_target)
                stamp = self.get_clock().now().to_msg()
                setpoint = LauncherSetpoint()
                setpoint.header.stamp = stamp; setpoint.interface_version = INTERFACE_VERSION
                setpoint.job_id = target["job_id"]
                setpoint.shot_id = target["shot_id"]
                setpoint.command_id = target["command_id"]
                setpoint.upper_target_rpm = target["upper_target_rpm"]
                setpoint.lower_target_rpm = target["lower_target_rpm"]
                setpoint.pitch_target_deg = target["pitch_target_deg"]
                setpoint.enabled = True; setpoint.valid_until = self._deadline()
                self.setpoint_pub.publish(setpoint)
        if expired:
            self._publish_launcher_stop(
                expired_job_id, expired_shot_id, "HOLD_LEASE_EXPIRED")

    def _publish_chassis_stop(self, job_id: str, shot_id: str) -> None:
        stamp = self.get_clock().now().to_msg()
        aim = ChassisAimCommand()
        aim.header.stamp = stamp; aim.header.frame_id = "court"
        aim.interface_version = INTERFACE_VERSION; aim.job_id = job_id; aim.shot_id = shot_id
        aim.command_id = "stop-" + uuid.uuid4().hex; aim.active = False
        aim.valid_until = stamp
        self.aim_pub.publish(aim)

    def _publish_launcher_stop(self, job_id: str, shot_id: str, reason: str) -> None:
        with self._hold_lock:
            should_publish = not self._launcher_stopped
            self._hold_enabled = False
            self._hold_job_id = ""
            self._hold_deadline = 0.0
            self._hold_target = None
            self._launcher_stopped = True
            if should_publish:
                stamp = self.get_clock().now().to_msg()
                stop = LauncherSetpoint()
                stop.header.stamp = stamp; stop.interface_version = INTERFACE_VERSION
                stop.job_id = job_id; stop.shot_id = shot_id
                stop.command_id = "stop-" + uuid.uuid4().hex
                stop.enabled = False; stop.valid_until = stamp
                self.setpoint_pub.publish(stop)
                self.get_logger().info(f"launcher hold stopped: {reason}")

    def _feedback(self, phase: str, gate=None):
        value = ExecuteShot.Feedback()
        value.phase = phase
        if gate:
            value.yaw_error_deg = gate.yaw_error_deg if math.isfinite(gate.yaw_error_deg) else 999.0
            value.upper_rpm_error_ratio = gate.upper_error_ratio if math.isfinite(gate.upper_error_ratio) else 999.0
            value.lower_rpm_error_ratio = gate.lower_error_ratio if math.isfinite(gate.lower_error_ratio) else 999.0
            value.gates_ready = gate.ready; value.detail = gate.detail
        return value

    def _execute(self, goal_handle):
        goal = goal_handle.request
        shot = goal.shot
        result = ExecuteShot.Result()
        started = time.monotonic(); launcher_wait_started = None
        stable_since = None; position_mismatch_since = None
        feed_id = "feed-" + uuid.uuid4().hex
        feed_published = False
        completed_successfully = False
        try:
            if not self._set_launcher_target(goal.job_id, goal.shot_id, shot):
                result.code = "LAUNCHER_HOLD_DISABLED"
                result.message = "launcher hold lease is missing, expired or owned by another job"
                goal_handle.abort()
                return result
            while True:
                now = time.monotonic()
                gate = evaluate_gates(
                    now, self.robot, self.launcher, shot.target_yaw_rad,
                    shot.upper_target_rpm, shot.lower_target_rpm,
                    self.gate_config, shot.robot_x_m, shot.robot_y_m)
                phase = "AIMING" if not (
                    gate.robot_fresh and gate.yaw_ready and gate.stopped
                    and gate.position_ready) else "WAITING_LAUNCHER"
                if phase == "WAITING_LAUNCHER" and launcher_wait_started is None:
                    launcher_wait_started = now
                goal_handle.publish_feedback(self._feedback(phase, gate))
                if self.emergency_stop:
                    result.code = "EMERGENCY_STOP"; result.message = "emergency stop is latched"
                    goal_handle.abort(); return result
                if goal_handle.is_cancel_requested:
                    result.code = "CANCELLED"; result.message = "shot cancelled before feed"
                    goal_handle.canceled(); return result
                with self._hold_lock:
                    hold_ready = (self._hold_enabled and self._hold_job_id == goal.job_id
                                  and now <= self._hold_deadline)
                if not hold_ready:
                    result.code = "LAUNCHER_HOLD_DISABLED"
                    result.message = "launcher hold was disabled or its lease expired"
                    goal_handle.abort(); return result
                if gate.robot_fresh and not gate.position_ready:
                    position_mismatch_since = position_mismatch_since or now
                    if now - position_mismatch_since >= self.position_mismatch_timeout_s:
                        result.code = "ROBOT_POSITION_CHANGED"
                        result.message = (
                            f"robot moved {gate.position_error_m:.3f} m from the planned pose; "
                            f"limit is {self.gate_config.position_tolerance_m:.3f} m")
                        goal_handle.abort(); return result
                else:
                    position_mismatch_since = None
                self._publish_aim_target(goal.job_id, goal.shot_id, shot)
                if gate.ready:
                    stable_since = stable_since or now
                    if now - stable_since >= self.stable_hold_s:
                        break
                else:
                    stable_since = None
                timed_out = (
                    phase == "AIMING" and now - started > self.aim_timeout_s
                ) or (
                    phase == "WAITING_LAUNCHER" and launcher_wait_started is not None
                    and now - launcher_wait_started > self.launcher_timeout_s
                )
                if timed_out:
                    result.code = "AIM_TIMEOUT" if phase == "AIMING" else "LAUNCHER_READY_TIMEOUT"
                    result.message = gate.detail
                    goal_handle.abort(); return result
                time.sleep(0.1)

            goal_handle.publish_feedback(self._feedback("READY_TO_FEED", gate))
            command = FeedCommand()
            command.header.stamp = self.get_clock().now().to_msg()
            command.interface_version = INTERFACE_VERSION; command.job_id = goal.job_id
            command.shot_id = goal.shot_id; command.command_id = feed_id
            command.action = FeedCommand.ACTION_FIRE
            command.valid_until = self._deadline()
            with self._goal_lock:
                self._feed_committed = True
            self.feed_pub.publish(command)
            feed_published = True
            goal_handle.publish_feedback(self._feedback("FEED_TRIGGERED", gate))
            goal_handle.publish_feedback(self._feedback("FEED_DWELL", gate))
            time.sleep(self.feed_dwell_s)
            result.success = True; result.feed_triggered = True; result.feed_confirmed = False
            result.code = "SHOT_TRIGGERED_UNCONFIRMED"
            result.message = "feed dwell elapsed without hardware confirmation"
            completed_successfully = True
            goal_handle.succeed()
            return result
        finally:
            self._publish_chassis_stop(goal.job_id, goal.shot_id)
            if not completed_successfully:
                self._publish_launcher_stop(goal.job_id, goal.shot_id, result.code or "SHOT_FAILED")
            with self._goal_lock:
                self._active_goal = False
                self._feed_committed = False
            if feed_published:
                self.get_logger().info(
                    f"feed command {feed_id} was published exactly once")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ServeControllerNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
