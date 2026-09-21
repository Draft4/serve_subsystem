from __future__ import annotations

import hmac
import json
import math
import os
import threading
import time
import uuid

import rclpy
import uvicorn
from fastapi import Body, Depends, FastAPI, Header, HTTPException
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
    CreateJob, GetJob, GetModelInfo, JobCommand, JobHeartbeat, PlanShot,
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
    """HTTP boundary only: all planning and execution are delegated to ROS."""

    def __init__(self) -> None:
        super().__init__("serve_bridge_node")
        defaults = {
            "host": "0.0.0.0", "port": 8765, "api_token": "",
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
        self.api_token = os.environ.get(
            "TENNIS_API_TOKEN", str(self.get_parameter("api_token").value)).strip()
        if not self.api_token:
            raise RuntimeError("set TENNIS_API_TOKEN or serve_bridge_node.api_token")
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
        self._heartbeat = self.create_client(
            JobHeartbeat, "/tennis/serve/job_heartbeat", callback_group=self._group)
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
        self.app = self._build_app()
        self._server = None
        self._http_thread = None
        self.get_logger().info(
            f"HTTP coordinate protocol: {COORDINATE_SYSTEM} "
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
        return self._call(self._model, GetModelInfo.Request(), 3.0)

    @staticmethod
    def _object(value, field: str) -> dict:
        if not isinstance(value, dict):
            raise HTTPException(status_code=422, detail=f"{field} must be an object")
        return value

    @staticmethod
    def _finite(value, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise HTTPException(status_code=422, detail=f"{field} must be a finite number")
        return float(value)

    @staticmethod
    def _coordinate_system(body: dict) -> str:
        value = body.get("coordinate_system", COORDINATE_SYSTEM)
        if value not in {COORDINATE_SYSTEM, LEGACY_COORDINATE_SYSTEM}:
            raise HTTPException(
                status_code=422,
                detail=("coordinate_system must be court_origin_v2 "
                        "(court_centered_v1 is accepted only for legacy clients)"),
            )
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
            raise HTTPException(status_code=422, detail=f"missing target field {exc.args[0]}") from exc
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
        try:
            model = self._model_info()
        except BridgeError as exc:
            model = None
            model_message = str(exc)
        else:
            model_message = model.message
        with self._lock:
            robot, robot_at = self._robot, self._robot_at
            launcher, launcher_at = self._launcher, self._launcher_at
            backend_armed = self._backend_armed
            serve_status, serve_status_at = self._serve_status, self._serve_status_at
            emergency_stop = self._emergency_stop
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

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="Tennis Serve ROS Bridge", version=SERVICE_VERSION)

        def authorize(authorization: str = Header(default="")) -> None:
            expected = "Bearer " + self.api_token
            if not hmac.compare_digest(authorization, expected):
                raise HTTPException(status_code=401, detail="invalid bearer token")

        @app.get("/api/v1/health")
        def health():
            try:
                model = self._model_info()
                ready, version, digest, message = (
                    bool(model.ready), model.model_version, model.model_sha256, model.message)
            except BridgeError as exc:
                ready, version, digest, message = False, "", "", str(exc)
            return {"ok": True, "service": "tennis-serve-ros", "service_version": SERVICE_VERSION,
                    "mode": "training", "model_ready": ready, "model_version": version,
                    "model_sha256": digest, "message": message}

        @app.get("/api/v1/status", dependencies=[Depends(authorize)])
        def status():
            return self._status_payload()

        @app.get("/api/v1/model", dependencies=[Depends(authorize)])
        def model_info():
            try:
                result = self._model_info()
            except BridgeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            metadata = json.loads(result.metadata_json) if result.metadata_json else {}
            return {"ok": bool(result.ready), "code": result.code, "message": result.message,
                    "model_version": result.model_version, "model_sha256": result.model_sha256,
                    **metadata}

        def preview_impl(body: dict):
            coordinate_system = self._coordinate_system(body)
            request_id = str(body.get("request_id", ""))
            if not request_id:
                raise HTTPException(status_code=422, detail="request_id is required")
            request = PlanShot.Request()
            request.request_id = request_id
            request.step_id = "preview"
            request.target = self._target(body.get("target"), coordinate_system)
            try:
                result = self._call(self._plan, request, 5.0)
                model = self._model_info()
            except BridgeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            if not result.ok:
                return {"request_id": request_id, "ok": False, "decision": "reject",
                        "code": result.code, "message": result.message,
                        "coordinate_system": coordinate_system, "pose_source": "localization",
                        "execution_allowed": False, "model_version": model.model_version,
                        "model_sha256": model.model_sha256, "plan": None, "prediction": None,
                        "evidence": {"court_request": body}}
            shot = result.shot
            turn = math.degrees(math.atan2(
                math.sin(shot.target_yaw_rad - shot.robot_yaw_rad),
                math.cos(shot.target_yaw_rad - shot.robot_yaw_rad)))
            return {
                "request_id": request_id, "ok": True, "decision": "execute",
                "code": result.code, "message": result.message,
                "coordinate_system": coordinate_system, "pose_source": "localization",
                "execution_allowed": False, "model_version": shot.model_version,
                "model_sha256": shot.model_sha256,
                "plan": {"target_heading_deg": math.degrees(shot.target_yaw_rad),
                         "turn_deg": turn, "upper_rpm": int(shot.upper_target_rpm),
                         "lower_rpm": int(shot.lower_target_rpm),
                         "pitch_deg": shot.pitch_target_deg},
                "prediction": {"success_probability": shot.success_probability,
                               "confidence": shot.confidence,
                               "landing_median_m": shot.landing_median_m,
                               "landing_p05_m": shot.landing_p05_m,
                               "landing_p95_m": shot.landing_p95_m,
                               "net_height_median_m": shot.net_height_median_m,
                               "net_height_p05_m": shot.net_height_p05_m,
                               "net_height_p95_m": shot.net_height_p95_m},
                "evidence": {"court_request": body,
                             "robot_pose": {"x_m": shot.robot_x_m, "y_m": shot.robot_y_m,
                                            "yaw_rad": shot.robot_yaw_rad}},
            }

        @app.post("/api/v1/plan-preview", dependencies=[Depends(authorize)])
        def plan_preview(body: dict = Body(...)):
            return preview_impl(self._object(body, "body"))

        @app.post("/api/v1/recommend", dependencies=[Depends(authorize)])
        def recommend(body: dict = Body(...)):
            return preview_impl(self._object(body, "body"))

        @app.post("/api/v1/jobs", dependencies=[Depends(authorize)])
        def create_job(body: dict = Body(...)):
            body = self._object(body, "body")
            coordinate_system = self._coordinate_system(body)
            request = CreateJob.Request()
            request.request_id = str(body.get("request_id", ""))
            request.client_id = str(body.get("client_id", ""))
            request.name = str(body.get("name", ""))
            request.mode = str(body.get("mode", ""))
            try:
                request.cycles = int(body.get("cycles", 0))
                request.cycle_rest_s = self._finite(body.get("cycle_rest_s"), "cycle_rest_s")
                request.countdown_s = self._finite(body.get("countdown_s"), "countdown_s")
            except (TypeError, ValueError, OverflowError) as exc:
                raise HTTPException(status_code=422, detail="invalid training numeric field") from exc
            request.stop_wheels_during_rest = bool(body.get("stop_wheels_during_rest", False))
            raw_steps = body.get("steps")
            if not isinstance(raw_steps, list):
                raise HTTPException(status_code=422, detail="steps must be an array")
            for raw_step in raw_steps:
                raw_step = self._object(raw_step, "step")
                step = TrainingStep()
                step.step_id = str(raw_step.get("step_id", ""))
                step.target = self._target(raw_step.get("target"), coordinate_system)
                try:
                    step.repeat = int(raw_step.get("repeat", 0))
                    step.interval_s = self._finite(raw_step.get("interval_s"), "step.interval_s")
                except (TypeError, ValueError, OverflowError) as exc:
                    raise HTTPException(status_code=422, detail="invalid step numeric field") from exc
                request.steps.append(step)
            try:
                result = self._call(self._create, request, 15.0)
            except BridgeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            detail = self._job_detail(result.job_json) if result.job_json else {}
            if not result.accepted:
                raise HTTPException(status_code=409 if result.code == "ACTIVE_JOB_EXISTS" else 422,
                                    detail={"code": result.code, "message": result.message,
                                            "job": detail})
            return detail

        @app.get("/api/v1/jobs/{job_id}", dependencies=[Depends(authorize)])
        def get_job(job_id: str):
            request = GetJob.Request(); request.job_id = job_id
            try:
                result = self._call(self._get, request, 3.0)
            except BridgeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            if not result.found:
                raise HTTPException(status_code=404, detail=result.message)
            return self._job_detail(result.job_json)

        @app.post("/api/v1/jobs/{job_id}/command", dependencies=[Depends(authorize)])
        def job_command(job_id: str, body: dict = Body(...)):
            body = self._object(body, "body")
            request = JobCommand.Request(); request.job_id = job_id
            request.command_id = str(body.get("command_id", ""))
            request.client_id = str(body.get("client_id", ""))
            request.action = str(body.get("action", ""))
            try:
                result = self._call(self._command, request, 5.0)
            except BridgeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            detail = self._job_detail(result.job_json) if result.job_json else {}
            if not result.accepted:
                status_code = 404 if result.code == "JOB_NOT_FOUND" else (
                    403 if result.code == "NOT_OWNER" else 409)
                raise HTTPException(status_code=status_code,
                                    detail={"code": result.code, "message": result.message})
            return {"command_id": request.command_id, "accepted": result.accepted,
                    "code": result.code, "message": result.message,
                    "job": detail.get("summary")}

        @app.post("/api/v1/jobs/{job_id}/heartbeat", dependencies=[Depends(authorize)])
        def job_heartbeat(job_id: str, body: dict = Body(...)):
            body = self._object(body, "body")
            request = JobHeartbeat.Request(); request.job_id = job_id
            request.client_id = str(body.get("client_id", ""))
            try:
                result = self._call(self._heartbeat, request, 3.0)
            except BridgeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            return {"ok": result.accepted, "code": result.code, "message": result.message}

        @app.post("/api/v1/emergency-stop/reset", dependencies=[Depends(authorize)])
        def reset_emergency_stop(body: dict = Body(default={})):
            body = self._object(body, "body")
            request = ResetEmergencyStop.Request()
            request.command_id = str(
                body.get("command_id") or "estop-reset-" + uuid.uuid4().hex)
            try:
                result = self._call(self._reset_estop, request, 3.0)
            except BridgeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            if result.accepted:
                with self._lock:
                    self._emergency_stop = False
            else:
                raise HTTPException(
                    status_code=409,
                    detail={"code": result.code, "message": result.message})
            return {"ok": True, "code": result.code, "message": result.message}

        return app

    def start_http(self) -> None:
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info")
        self._server = uvicorn.Server(config)
        self._http_thread = threading.Thread(
            target=self._server.run, name="serve-http", daemon=True)
        self._http_thread.start()

    def stop_http(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._http_thread:
            self._http_thread.join(timeout=3.0)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ServeBridgeNode()
    node.start_http()
    executor = MultiThreadedExecutor(num_threads=8)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.stop_http()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
