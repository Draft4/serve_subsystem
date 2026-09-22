from __future__ import annotations

import json
import math
import socket
import threading
import time

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy,
    qos_profile_sensor_data,
)
from std_msgs.msg import Bool
from tennisbot_interfaces.msg import RobotState
from tennisbot_launcher.msg import LauncherWheelState
from tennis_serve_interfaces.msg import CourtTarget, LauncherState, ServeSystemStatus, TrainingStep
from tennis_serve_interfaces.srv import (
    CreateJob, GetJob, GetModelInfo, JobCommand, PlanShot,
    ResetEmergencyStop,
)

from tennis_serve_common.core import (
    legacy_target_to_court, localization_to_court_xy,
    observation_received_monotonic,
)


SERVICE_VERSION = "0.7.0"
COORDINATE_SYSTEM = "court_origin_v2"
LEGACY_COORDINATE_SYSTEM = "court_centered_v1"


class BridgeError(RuntimeError):
    pass


class ServeBridgeNode(Node):
    """UDP boundary only: all planning and execution are delegated to ROS."""

    def __init__(self) -> None:
        super().__init__("serve_bridge_node")
        defaults = {
            "host": "0.0.0.0", "port": 8765,
            "robot_state_topic": "/localization/robot_state",
            "launcher_state_topic": "/tennis/launcher/state",
            "launcher_wheel_state_topic": "/launcher/wheels/state",
            "serve_status_topic": "/tennis/serve_status",
            "emergency_stop_topic": "/tennis/emergency_stop",
            "localization_timeout_s": 1.0, "launcher_state_timeout_s": 1.0,
            "serve_status_timeout_s": 1.0,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)
        self.host = str(self.get_parameter("host").value)
        self.port = int(self.get_parameter("port").value)
        self.localization_timeout_s = float(self.get_parameter("localization_timeout_s").value)
        self.launcher_timeout_s = float(self.get_parameter("launcher_state_timeout_s").value)
        self.serve_status_timeout_s = float(
            self.get_parameter("serve_status_timeout_s").value)
        self.started_monotonic = time.monotonic()
        self._group = ReentrantCallbackGroup()
        self._lock = threading.RLock()
        self._robot = None
        self._robot_at = 0.0
        self._launcher = None
        self._launcher_at = 0.0
        self._backend_armed = False
        self._serve_status = None
        self._serve_status_at = 0.0
        self._emergency_stop = False
        self._model_cache = None

        self._plan = self.create_client(
            PlanShot, "/tennis/serve/plan_shot", callback_group=self._group)
        self._model = self.create_client(
            GetModelInfo, "/tennis/serve/model_info", callback_group=self._group)
        self._create = self.create_client(
            CreateJob, "/tennis/serve/create_job", callback_group=self._group)
        self._get = self.create_client(
            GetJob, "/tennis/serve/get_job", callback_group=self._group)
        self._command = self.create_client(
            JobCommand, "/tennis/serve/job_command", callback_group=self._group)
        self._reset_estop = self.create_client(
            ResetEmergencyStop, "/tennis/serve/reset_emergency_stop",
            callback_group=self._group)
        self.create_subscription(
            RobotState, str(self.get_parameter("robot_state_topic").value),
            self._on_robot, qos_profile_sensor_data, callback_group=self._group)
        self.create_subscription(
            LauncherState, str(self.get_parameter("launcher_state_topic").value),
            self._on_launcher, qos_profile_sensor_data, callback_group=self._group)
        self.create_subscription(
            LauncherWheelState,
            str(self.get_parameter("launcher_wheel_state_topic").value),
            self._on_wheel_state, qos_profile_sensor_data, callback_group=self._group)
        self.create_subscription(
            ServeSystemStatus, str(self.get_parameter("serve_status_topic").value),
            self._on_status, 10, callback_group=self._group)
        estop_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.create_subscription(
            Bool, str(self.get_parameter("emergency_stop_topic").value),
            self._on_estop, estop_qos, callback_group=self._group)
        self._udp_socket = None
        self._udp_thread = None
        self._udp_running = False
        self.get_logger().info(
            f"UDP coordinate protocol: {COORDINATE_SYSTEM} "
            f"(legacy {LEGACY_COORDINATE_SYSTEM} accepted)")

    def _on_robot(self, message) -> None:
        if len(message.state) < 6:
            return
        try:
            received_s = observation_received_monotonic(
                time.monotonic(), message.observation_age_s)
            localization_to_court_xy(message.state[0], message.state[1])
        except ValueError:
            return
        with self._lock:
            self._robot = message
            self._robot_at = received_s

    def _on_launcher(self, message) -> None:
        if message.interface_version != 1:
            return
        with self._lock:
            self._launcher = message
            self._launcher_at = time.monotonic()

    def _on_wheel_state(self, message: LauncherWheelState) -> None:
        with self._lock:
            self._backend_armed = bool(message.armed)

    def _on_status(self, message) -> None:
        with self._lock:
            self._serve_status = message
            self._serve_status_at = time.monotonic()

    def _on_estop(self, message: Bool) -> None:
        if message.data:
            with self._lock:
                self._emergency_stop = True

    def _call(self, client, request, timeout_s: float = 5.0):
        if not client.wait_for_service(timeout_sec=min(timeout_s, 2.0)):
            raise BridgeError("ROS service is unavailable")
        event = threading.Event()
        future = client.call_async(request)
        future.add_done_callback(lambda _future: event.set())
        if not event.wait(timeout_s):
            raise BridgeError("ROS service timed out")
        if future.exception():
            raise BridgeError(str(future.exception()))
        return future.result()

    def _model_info(self):
        model = self._call(self._model, GetModelInfo.Request(), 3.0)
        with self._lock:
            self._model_cache = model
        return model

    @staticmethod
    def _object(value, field: str) -> dict:
        if not isinstance(value, dict):
            raise BridgeError(f"{field} must be an object")
        return value

    @staticmethod
    def _finite(value, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise BridgeError(f"{field} must be a finite number")
        return float(value)

    @staticmethod
    def _coordinate_system(body: dict) -> str:
        value = body.get("coordinate_system", COORDINATE_SYSTEM)
        if value not in {COORDINATE_SYSTEM, LEGACY_COORDINATE_SYSTEM}:
            raise BridgeError("coordinate_system must be court_origin_v2")
        return str(value)

    def _target(self, raw: dict, coordinate_system: str) -> CourtTarget:
        raw = self._object(raw, "target")
        target = CourtTarget()
        try:
            source_x = self._finite(raw["center_x_m"], "target.center_x_m")
            source_y = self._finite(raw["center_y_m"], "target.center_y_m")
            if coordinate_system == LEGACY_COORDINATE_SYSTEM:
                target.center_x_m, target.center_y_m = legacy_target_to_court(
                    source_x, source_y)
            else:
                target.center_x_m = source_x
                target.center_y_m = source_y
            target.width_m = self._finite(raw["width_m"], "target.width_m")
            target.depth_m = self._finite(raw["depth_m"], "target.depth_m")
            target.net_height_min_m = self._finite(raw["net_height_min_m"], "target.net_height_min_m")
            target.net_height_max_m = self._finite(raw["net_height_max_m"], "target.net_height_max_m")
        except KeyError as exc:
            raise BridgeError(f"missing target field {exc.args[0]}") from exc
        return target

    @staticmethod
    def _job_detail(raw: str) -> dict:
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise BridgeError("job manager returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise BridgeError("job manager returned a non-object JSON value")
        return value

    @staticmethod
    def _summary(status) -> dict | None:
        if not status or not status.job_id:
            return None
        remaining = status.time_to_next_shot_s if status.time_to_next_shot_s > 0 else None
        return {
            "job_id": status.job_id, "name": status.job_name, "state": status.job_state,
            "phase": status.phase, "revision": int(status.revision),
            "completed_balls": int(status.completed_shots),
            "total_balls": int(status.total_shots),
            "current_ball_index": int(status.current_shot),
            "current_step_index": int(status.current_step),
            "current_cycle": int(status.current_cycle), "remaining_s": remaining,
            "code": status.code, "message": status.message,
            "feed_triggered": bool(status.feed_triggered),
            "feed_confirmed": bool(status.feed_confirmed),
            "triggered_unconfirmed_balls": int(status.triggered_unconfirmed_shots),
        }

    def _status_payload(self) -> dict:
        now = time.monotonic()
        with self._lock:
            robot, robot_at = self._robot, self._robot_at
            launcher, launcher_at = self._launcher, self._launcher_at
            backend_armed = self._backend_armed
            serve_status, serve_status_at = self._serve_status, self._serve_status_at
            emergency_stop = self._emergency_stop
            model = self._model_cache
        model_message = model.message if model else "request model information first"
        robot_age = now - robot_at if robot_at else None
        launcher_age = now - launcher_at if launcher_at else None
        status_age = now - serve_status_at if serve_status_at else None
        status_fresh = bool(
            serve_status and status_age is not None
            and status_age <= self.serve_status_timeout_s)
        if not status_fresh:
            serve_status = None
        robot_values = list(robot.state[:6]) if robot and len(robot.state) >= 6 else [None] * 6
        if robot_values[0] is not None:
            try:
                robot_values[0], robot_values[1] = localization_to_court_xy(
                    robot_values[0], robot_values[1])
            except ValueError:
                robot_values = [None] * 6
        localization_ready = bool(
            robot and robot.valid and robot_values[0] is not None
            and robot_age is not None and robot_age <= self.localization_timeout_s)
        launcher_online = bool(
            launcher and launcher.online and launcher_age is not None and launcher_age <= self.launcher_timeout_s)
        launcher_ready = bool(
            launcher_online and launcher.rpm_valid)
        model_ready = bool(model and model.ready)
        return {
            "ok": True, "service_version": SERVICE_VERSION, "mode": "training",
            "coordinate_system": COORDINATE_SYSTEM,
            "uptime_s": now - self.started_monotonic,
            "model_ready": model_ready,
            "model_version": model.model_version if model_ready else "",
            "model_sha256": model.model_sha256 if model_ready else "",
            "execution_allowed": bool(
                model_ready and localization_ready and launcher_ready
                and not emergency_stop),
            "f407_connected": launcher_online, "armed": backend_armed,
            "emergency_stop": emergency_stop,
            "serve_status_fresh": status_fresh,
            "serve_status_age_s": status_age,
            "current_task": (
                serve_status.job_state if serve_status and serve_status.job_id
                else ("idle" if status_fresh else "unavailable")),
            "message": model_message, "runtime_mode": "hardware", "hardware_output": True,
            "training_commands_allowed": bool(
                model_ready and localization_ready and launcher_ready
                and not emergency_stop),
            "backend_connected": launcher_online, "backend_armed": backend_armed,
            "localization_ready": localization_ready,
            "robot_state": {
                "valid": bool(robot.valid) if robot else False,
                "x_m": robot_values[0], "y_m": robot_values[1], "yaw_rad": robot_values[2],
                "yaw_deg": math.degrees(robot_values[2]) if robot_values[2] is not None else None,
                "vx_mps": robot_values[3], "vy_mps": robot_values[4],
                "yaw_rate_radps": robot_values[5], "age_s": robot_age,
                "pose_source": "localization",
            },
            "launcher_state": {
                "online": bool(launcher.online) if launcher else False,
                "rpm_valid": bool(launcher.rpm_valid) if launcher else False,
                "pitch_valid": bool(launcher.pitch_valid) if launcher else False,
                "upper_actual_rpm": launcher.upper_actual_rpm if launcher else None,
                "lower_actual_rpm": launcher.lower_actual_rpm if launcher else None,
                "pitch_actual_deg": launcher.pitch_actual_deg if launcher else None,
                "detail": launcher.detail if launcher else "NO_LAUNCHER_STATE",
                "ready": launcher_ready,
                "age_s": launcher_age,
            },
            "target_state": ({
                "target_yaw_rad": serve_status.target_yaw_rad,
                "upper_target_rpm": serve_status.upper_target_rpm,
                "lower_target_rpm": serve_status.lower_target_rpm,
                "pitch_target_deg": serve_status.pitch_target_deg,
            } if serve_status else None),
            "gates": ({
                "robot_state_fresh": serve_status.robot_state_fresh,
                "launcher_state_fresh": serve_status.launcher_state_fresh,
                "yaw_ready": serve_status.yaw_ready, "speed_ready": serve_status.speed_ready,
                "rpm_ready": serve_status.rpm_ready, "pitch_ready": serve_status.pitch_ready,
                "stable_ready": serve_status.stable_ready, "detail": serve_status.gate_detail,
            } if serve_status else None),
            "feed_confirmed": bool(serve_status.feed_confirmed) if serve_status else False,
            "job": self._summary(serve_status),
        }

    def _preview(self, body: dict) -> dict:
        request = PlanShot.Request()
        request.request_id = "udp-preview"
        request.step_id = "preview"
        request.target = self._target(body["target"], self._coordinate_system(body))
        result = self._call(self._plan, request, 5.0)
        if not result.ok:
            return {"ok": False, "decision": "reject", "code": result.code,
                    "message": result.message, "plan": None, "prediction": None}
        shot = result.shot
        return {"ok": True, "decision": "execute", "code": result.code,
                "message": result.message,
                "plan": {"target_heading_deg": math.degrees(shot.target_yaw_rad),
                         "turn_deg": math.degrees(math.atan2(
                             math.sin(shot.target_yaw_rad - shot.robot_yaw_rad),
                             math.cos(shot.target_yaw_rad - shot.robot_yaw_rad))),
                         "upper_rpm": int(shot.upper_target_rpm),
                         "lower_rpm": int(shot.lower_target_rpm),
                         "pitch_deg": shot.pitch_target_deg},
                "prediction": {"success_probability": shot.success_probability,
                               "confidence": shot.confidence,
                               "landing_median_m": shot.landing_median_m,
                               "landing_p05_m": shot.landing_p05_m,
                               "landing_p95_m": shot.landing_p95_m,
                               "net_height_median_m": shot.net_height_median_m,
                               "net_height_p05_m": shot.net_height_p05_m,
                               "net_height_p95_m": shot.net_height_p95_m}}

    def _create_job(self, body: dict) -> dict:
        request = CreateJob.Request()
        request.request_id = "udp-job"
        request.client_id = "udp"
        request.name = str(body.get("name", ""))
        request.mode = str(body.get("mode", "fixed"))
        request.cycles = int(body.get("cycles", 1))
        request.cycle_rest_s = float(body.get("cycle_rest_s", 0.0))
        request.countdown_s = float(body.get("countdown_s", 0.0))
        request.stop_wheels_during_rest = bool(body.get("stop_wheels_during_rest", False))
        coordinate_system = self._coordinate_system(body)
        for raw in body.get("steps", []):
            step = TrainingStep()
            step.step_id = str(raw.get("step_id", ""))
            step.target = self._target(raw["target"], coordinate_system)
            step.repeat = int(raw.get("repeat", 1))
            step.interval_s = float(raw.get("interval_s", 1.0))
            request.steps.append(step)
        result = self._call(self._create, request, 15.0)
        return self._job_detail(result.job_json) if result.job_json else {
            "ok": bool(result.accepted), "code": result.code, "message": result.message}

    def _get_job(self, job_id: str) -> dict:
        request = GetJob.Request()
        request.job_id = job_id
        result = self._call(self._get, request, 3.0)
        return self._job_detail(result.job_json) if result.job_json else {
            "ok": bool(result.found), "code": result.code, "message": result.message}

    def _job_command(self, job_id: str, body: dict) -> dict:
        request = JobCommand.Request()
        request.job_id = job_id
        request.command_id = "udp-command"
        request.client_id = "udp"
        request.action = str(body.get("action", ""))
        result = self._call(self._command, request, 5.0)
        detail = self._job_detail(result.job_json) if result.job_json else {}
        return {"accepted": bool(result.accepted), "code": result.code,
                "message": result.message, "job": detail.get("summary")}

    def _reset(self) -> dict:
        request = ResetEmergencyStop.Request()
        request.command_id = "udp-reset"
        result = self._call(self._reset_estop, request, 3.0)
        if result.accepted:
            with self._lock:
                self._emergency_stop = False
        return {"ok": bool(result.accepted), "code": result.code, "message": result.message}

    def _handle_udp(self, request: dict) -> dict:
        op = request.get("op")
        data = request.get("data", {})
        if op == "status":
            return self._status_payload()
        if op == "model":
            model = self._model_info()
            return {"ok": bool(model.ready), "code": model.code, "message": model.message,
                    "model_version": model.model_version}
        if op == "preview":
            return self._preview(data)
        if op == "create_job":
            return self._create_job(data)
        if op == "get_job":
            return self._get_job(str(request.get("job_id", "")))
        if op == "job_command":
            return self._job_command(str(request.get("job_id", "")), data)
        if op == "reset_estop":
            return self._reset()
        return {"ok": False, "message": "unknown operation"}

    def _udp_loop(self) -> None:
        while self._udp_running:
            try:
                raw, address = self._udp_socket.recvfrom(65535)
            except OSError:
                break
            try:
                response = self._handle_udp(json.loads(raw.decode("utf-8")))
            except Exception as exc:
                response = {"ok": False, "message": str(exc)}
            try:
                self._udp_socket.sendto(json.dumps(response, ensure_ascii=False,
                                                    separators=(",", ":")).encode("utf-8"), address)
            except OSError:
                break

    def start_udp(self) -> None:
        self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_socket.bind((self.host, self.port))
        self._udp_running = True
        self._udp_thread = threading.Thread(target=self._udp_loop, name="serve-udp", daemon=True)
        self._udp_thread.start()

    def stop_udp(self) -> None:
        self._udp_running = False
        if self._udp_socket:
            self._udp_socket.close()
        if self._udp_thread:
            self._udp_thread.join(timeout=1.0)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ServeBridgeNode()
    node.start_udp()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.stop_udp()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
