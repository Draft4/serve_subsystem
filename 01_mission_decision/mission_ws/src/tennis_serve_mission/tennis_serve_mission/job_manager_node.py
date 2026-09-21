from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import uuid
from collections import deque
from copy import deepcopy

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from tennisbot_interfaces.msg import RobotState
from tennis_serve_interfaces.action import ExecuteShot
from tennis_serve_interfaces.msg import LauncherState, ServeSystemStatus
from tennis_serve_interfaces.srv import (
    CreateJob, GetJob, GetModelInfo, JobCommand, JobHeartbeat, PlanShot, SetLauncherHold,
)

from tennis_serve_common.core import (
    INTERFACE_VERSION, localization_to_court_xy,
    observation_received_monotonic,
)


TERMINAL_STATES = {"COMPLETED", "REJECTED", "FAILED", "CANCELLED"}
ACTIVE_STATES = {"VALIDATING", "READY", "RUNNING", "PAUSED"}
RETRYABLE_PRE_FEED_CODES = {
    "AIM_TIMEOUT", "LAUNCHER_READY_TIMEOUT", "ROBOT_POSITION_CHANGED",
    "PLANNER_UNAVAILABLE", "PLAN_RETRY_FAILED", "LOCALIZATION_NOT_READY",
    "LAUNCHER_HOLD_UNAVAILABLE", "EXECUTE_SHOT_UNAVAILABLE",
}


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _target_dict(target) -> dict:
    return {
        "center_x_m": target.center_x_m,
        "center_y_m": target.center_y_m,
        "width_m": target.width_m,
        "depth_m": target.depth_m,
        "net_height_min_m": target.net_height_min_m,
        "net_height_max_m": target.net_height_max_m,
    }


def _shot_dict(shot) -> dict:
    return {
        "step_id": shot.step_id,
        "target": _target_dict(shot.target),
        "robot_x_m": shot.robot_x_m,
        "robot_y_m": shot.robot_y_m,
        "robot_yaw_rad": shot.robot_yaw_rad,
        "target_yaw_rad": shot.target_yaw_rad,
        "target_heading_deg": math.degrees(shot.target_yaw_rad),
        "turn_deg": math.degrees(math.atan2(
            math.sin(shot.target_yaw_rad - shot.robot_yaw_rad),
            math.cos(shot.target_yaw_rad - shot.robot_yaw_rad))),
        "upper_target_rpm": shot.upper_target_rpm,
        "lower_target_rpm": shot.lower_target_rpm,
        "pitch_target_deg": shot.pitch_target_deg,
        "success_probability": shot.success_probability,
        "confidence": shot.confidence,
        "landing_median_m": shot.landing_median_m,
        "landing_p05_m": shot.landing_p05_m,
        "landing_p95_m": shot.landing_p95_m,
        "net_height_median_m": shot.net_height_median_m,
        "net_height_p05_m": shot.net_height_p05_m,
        "net_height_p95_m": shot.net_height_p95_m,
        "model_version": shot.model_version,
        "model_sha256": shot.model_sha256,
    }


class ServeJobManagerNode(Node):
    """Owns the single in-memory job and delegates each shot to ExecuteShot."""

    def __init__(self) -> None:
        super().__init__("serve_job_manager_node")
        self.declare_parameter("heartbeat_timeout_s", 10.0)
        self.declare_parameter("max_pre_feed_retries", 2)
        self.declare_parameter("max_job_steps", 500)
        self.declare_parameter("max_job_cycles", 999)
        self.declare_parameter("max_step_repeat", 1000)
        self.declare_parameter("min_shot_interval_s", 0.2)
        self.declare_parameter("max_shot_interval_s", 3600.0)
        self.declare_parameter("max_total_shots", 10000)
        self.declare_parameter("max_countdown_s", 600.0)
        self.declare_parameter("max_cycle_rest_s", 3600.0)
        self.declare_parameter("status_topic", "/tennis/serve_status")
        self.declare_parameter("robot_state_topic", "/localization/robot_state")
        self.declare_parameter("launcher_state_topic", "/tennis/launcher/state")
        self.declare_parameter("localization_timeout_s", 1.0)
        self.declare_parameter("launcher_state_timeout_s", 1.0)
        self.declare_parameter("yaw_tolerance_deg", 5.0)
        self.declare_parameter("linear_speed_limit_mps", 0.20)
        self.declare_parameter("angular_speed_limit_radps", 0.10)
        self.declare_parameter("rpm_tolerance_ratio", 0.15)
        self.declare_parameter("pitch_tolerance_deg", 3.0)
        self.heartbeat_timeout_s = float(self.get_parameter("heartbeat_timeout_s").value)
        self.max_pre_feed_retries = int(
            self.get_parameter("max_pre_feed_retries").value)
        self.max_job_steps = int(self.get_parameter("max_job_steps").value)
        self.max_job_cycles = int(self.get_parameter("max_job_cycles").value)
        self.max_step_repeat = int(self.get_parameter("max_step_repeat").value)
        self.min_shot_interval_s = float(
            self.get_parameter("min_shot_interval_s").value)
        self.max_shot_interval_s = float(
            self.get_parameter("max_shot_interval_s").value)
        self.max_total_shots = int(self.get_parameter("max_total_shots").value)
        self.max_countdown_s = float(self.get_parameter("max_countdown_s").value)
        self.max_cycle_rest_s = float(
            self.get_parameter("max_cycle_rest_s").value)
        self.localization_timeout_s = float(self.get_parameter("localization_timeout_s").value)
        self.launcher_timeout_s = float(
            self.get_parameter("launcher_state_timeout_s").value)
        self.yaw_tolerance_deg = float(self.get_parameter("yaw_tolerance_deg").value)
        self.linear_speed_limit_mps = float(
            self.get_parameter("linear_speed_limit_mps").value)
        self.angular_speed_limit_radps = float(
            self.get_parameter("angular_speed_limit_radps").value)
        self.rpm_tolerance_ratio = float(
            self.get_parameter("rpm_tolerance_ratio").value)
        self.pitch_tolerance_deg = float(
            self.get_parameter("pitch_tolerance_deg").value)
        self._group = ReentrantCallbackGroup()
        self._lock = threading.RLock()
        self._job = None
        self._events = deque(maxlen=200)
        self._request_cache = {}
        self._command_cache = {}
        self._worker = None
        self._active_goal_handle = None
        self._robot = None
        self._robot_at = 0.0
        self._launcher = None
        self._launcher_at = 0.0
        self._hold_call_lock = threading.Lock()
        self._hold_generation = 0
        self._hold_renew_failed = False

        self._plan_client = self.create_client(
            PlanShot, "/tennis/serve/plan_shot", callback_group=self._group)
        self._shot_client = ActionClient(
            self, ExecuteShot, "/tennis/serve/execute_shot", callback_group=self._group)
        self._model_client = self.create_client(
            GetModelInfo, "/tennis/serve/model_info", callback_group=self._group)
        self._hold_client = self.create_client(
            SetLauncherHold, "/tennis/serve/set_launcher_hold", callback_group=self._group)
        self.create_service(CreateJob, "/tennis/serve/create_job", self._create_job,
                            callback_group=self._group)
        self.create_service(GetJob, "/tennis/serve/get_job", self._get_job,
                            callback_group=self._group)
        self.create_service(JobCommand, "/tennis/serve/job_command", self._job_command,
                            callback_group=self._group)
        self.create_service(JobHeartbeat, "/tennis/serve/job_heartbeat", self._heartbeat,
                            callback_group=self._group)
        self._status_pub = self.create_publisher(
            ServeSystemStatus, str(self.get_parameter("status_topic").value), 10)
        self.create_subscription(
            RobotState, str(self.get_parameter("robot_state_topic").value),
            self._on_robot, qos_profile_sensor_data, callback_group=self._group)
        self.create_subscription(
            LauncherState, str(self.get_parameter("launcher_state_topic").value),
            self._on_launcher, qos_profile_sensor_data, callback_group=self._group)
        self.create_timer(0.1, self._publish_status, callback_group=self._group)
        self.create_timer(0.25, self._check_heartbeat, callback_group=self._group)
        self.create_timer(0.25, self._maintain_launcher_hold, callback_group=self._group)

    def _on_robot(self, message) -> None:
        if len(message.state) >= 6:
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
        if message.interface_version != INTERFACE_VERSION:
            return
        with self._lock:
            self._launcher = message
            self._launcher_at = time.monotonic()

    def _event(self, level: str, code: str, message: str) -> None:
        with self._lock:
            sequence = (self._events[-1]["sequence"] + 1) if self._events else 1
            self._events.append({
                "sequence": sequence, "time": time.time(), "level": level,
                "code": code, "message": message,
            })
            if self._job:
                self._job["revision"] += 1

    def _job_json(self) -> str:
        with self._lock:
            if not self._job:
                return "{}"
            deadline = self._job.get("next_deadline_monotonic", 0.0)
            value = deepcopy({
                key: item for key, item in self._job.items()
                if key not in {"schedule", "planned_messages", "last_heartbeat_monotonic",
                               "next_deadline_monotonic"}
            })
            value["summary"] = {
                "job_id": value["job_id"], "name": value["name"],
                "state": value["state"], "phase": value["phase"],
                "revision": value["revision"],
                "completed_balls": value["completed_balls"],
                "total_balls": value["total_balls"],
                "current_ball_index": value["current_shot"],
                "current_step_index": value["current_step"],
                "current_cycle": value["current_cycle"],
                "remaining_s": max(0.0, deadline - time.monotonic()) if deadline else None,
                "code": value["code"], "message": value["message"],
                "feed_triggered": value["feed_triggered"],
                "feed_confirmed": value["feed_confirmed"],
                "triggered_unconfirmed_balls": value["triggered_unconfirmed_balls"],
            }
            value["events"] = list(self._events)
            return _canonical(value)

    def _wait_future(self, future, timeout_s: float):
        done = threading.Event()
        future.add_done_callback(lambda _future: done.set())
        if not done.wait(timeout_s):
            raise TimeoutError("ROS request timed out")
        error = future.exception()
        if error:
            raise error
        return future.result()

    def _request_launcher_hold(self, job_id: str, enabled: bool, reason: str,
                               timeout_s: float = 1.0, expected_generation=None,
                               skip_if_busy: bool = False):
        acquired = self._hold_call_lock.acquire(blocking=not skip_if_busy)
        if not acquired:
            return True, "RENEWAL_IN_FLIGHT", "another hold request is already in flight"
        try:
            if (expected_generation is not None
                    and expected_generation != self._hold_generation):
                return True, "STALE_RENEWAL_SKIPPED", "a newer hold decision superseded this renewal"
            if not self._hold_client.wait_for_service(timeout_sec=min(timeout_s, 0.5)):
                return False, "LAUNCHER_HOLD_UNAVAILABLE", "launcher hold service is unavailable"
            request = SetLauncherHold.Request()
            request.job_id = job_id
            request.command_id = ("hold-" if enabled else "stop-") + uuid.uuid4().hex
            request.enabled = enabled
            request.reason = reason
            try:
                result = self._wait_future(self._hold_client.call_async(request), timeout_s)
            except Exception as exc:
                return False, "LAUNCHER_HOLD_ERROR", str(exc)
            return bool(result.accepted), result.code, result.message
        finally:
            self._hold_call_lock.release()

    def _enable_launcher_hold_locked(self, reason: str):
        self._hold_generation += 1
        ok, code, message = self._request_launcher_hold(
            self._job["job_id"], True, reason, timeout_s=1.0)
        if ok:
            self._hold_renew_failed = False
        return ok, code, message

    def _stop_launcher_locked(self, reason: str) -> None:
        if not self._job:
            return
        self._hold_generation += 1
        ok, code, message = self._request_launcher_hold(
            self._job["job_id"], False, reason, timeout_s=1.0)
        self._hold_renew_failed = False
        if not ok:
            self._event(
                "error", "LAUNCHER_STOP_UNCONFIRMED",
                f"{reason}: {code}: {message}; hold lease will be allowed to expire")

    def _maintain_launcher_hold(self) -> None:
        with self._lock:
            if not self._job or self._job["state"] != "RUNNING":
                return
            if (self._job["program"].get("stop_wheels_during_rest")
                    and self._job["phase"] in {"INTERVAL", "CYCLE_REST"}):
                return
            job_id = self._job["job_id"]
            generation = self._hold_generation
        ok, code, message = self._request_launcher_hold(
            job_id, True, "LEASE_RENEW", timeout_s=0.75,
            expected_generation=generation, skip_if_busy=True)
        if code in {"STALE_RENEWAL_SKIPPED", "RENEWAL_IN_FLIGHT"}:
            return
        with self._lock:
            still_running = bool(
                self._job and self._job["job_id"] == job_id
                and self._job["state"] == "RUNNING"
                and self._hold_generation == generation)
            if not still_running:
                return
            if ok:
                self._hold_renew_failed = False
            elif not self._hold_renew_failed:
                self._hold_renew_failed = True
                self._event(
                    "warning", "LAUNCHER_HOLD_RENEW_FAILED",
                    f"{code}: {message}; launcher will stop when its hold lease expires")

    def _validate_request(self, request) -> None:
        if not request.request_id or not request.client_id:
            raise ValueError("request_id and client_id are required")
        if request.mode not in {"fixed", "sequence"}:
            raise ValueError("mode must be fixed or sequence")
        if not 1 <= len(request.steps) <= self.max_job_steps:
            raise ValueError(
                f"steps must contain 1 to {self.max_job_steps} entries")
        if request.mode == "fixed" and len(request.steps) != 1:
            raise ValueError("fixed mode requires exactly one step")
        if not 1 <= request.cycles <= self.max_job_cycles:
            raise ValueError(f"cycles must be in 1..{self.max_job_cycles}")
        if not 0.0 <= request.cycle_rest_s <= self.max_cycle_rest_s:
            raise ValueError(
                f"cycle_rest_s must be in 0..{self.max_cycle_rest_s:g}")
        if not 0.0 <= request.countdown_s <= self.max_countdown_s:
            raise ValueError(
                f"countdown_s must be in 0..{self.max_countdown_s:g}")
        total = 0
        for step in request.steps:
            if not 1 <= step.repeat <= self.max_step_repeat:
                raise ValueError(
                    f"step repeat must be in 1..{self.max_step_repeat}")
            if not self.min_shot_interval_s <= step.interval_s <= self.max_shot_interval_s:
                raise ValueError(
                    "step interval_s must be in "
                    f"{self.min_shot_interval_s:g}..{self.max_shot_interval_s:g}")
            total += step.repeat
        if total * request.cycles > self.max_total_shots:
            raise ValueError(
                f"total shot count exceeds {self.max_total_shots}")

    def _create_job(self, request, response):
        payload = {
            "client_id": request.client_id, "name": request.name, "mode": request.mode,
            "cycles": request.cycles, "cycle_rest_s": request.cycle_rest_s,
            "countdown_s": request.countdown_s,
            "stop_wheels_during_rest": request.stop_wheels_during_rest,
            "steps": [{"step_id": s.step_id, "target": _target_dict(s.target),
                       "repeat": s.repeat, "interval_s": s.interval_s} for s in request.steps],
        }
        fingerprint = _digest(payload)
        with self._lock:
            cached = self._request_cache.get(request.request_id)
            if cached:
                if cached[0] != fingerprint:
                    response.code = "IDEMPOTENCY_CONFLICT"
                    response.message = "request_id was already used with different content"
                    return response
                response.accepted, response.code, response.message, response.job_id, response.job_json = cached[1]
                return response
            if self._job and self._job["state"] in ACTIVE_STATES:
                response.code = "ACTIVE_JOB_EXISTS"
                response.message = "finish or cancel the current job first"
                return response
        try:
            self._validate_request(request)
        except ValueError as exc:
            response.code = "INVALID_JOB"
            response.message = str(exc)
            return response

        job_id = "job-" + uuid.uuid4().hex
        with self._lock:
            self._events.clear()
            self._job = {
                "request_id": request.request_id, "job_id": job_id,
                "client_id": request.client_id, "name": request.name or "未命名训练",
                "mode": request.mode, "state": "VALIDATING", "phase": "VALIDATING",
                "code": "VALIDATING", "message": "compiling all shots from live localization",
                "runtime_mode": "hardware", "hardware_output": True,
                "revision": 1, "completed_balls": 0, "triggered_unconfirmed_balls": 0,
                "current_shot": 0, "current_step": 0, "current_cycle": 0,
                "total_balls": sum(s.repeat for s in request.steps) * request.cycles,
                "feed_confirmed": False, "feed_triggered": False,
                "model_version": "", "model_sha256": "", "compiled_steps": [],
                "program": payload, "schedule": [], "planned_messages": [],
                "last_heartbeat_monotonic": time.monotonic(), "next_deadline_monotonic": 0.0,
                "estimated_min_duration_s": float(request.countdown_s),
            }
        self._event("info", "VALIDATING", "开始按实时定位编译训练任务")

        try:
            model_sha = None
            model_version = None
            plans_by_step = []
            planned_messages = []
            for index, step in enumerate(request.steps):
                if not self._plan_client.wait_for_service(timeout_sec=2.0):
                    raise RuntimeError("planner service is unavailable")
                plan_request = PlanShot.Request()
                plan_request.request_id = f"{request.request_id}:{index}"
                plan_request.step_id = step.step_id or f"step-{index + 1}"
                plan_request.target = step.target
                result = self._wait_future(self._plan_client.call_async(plan_request), 5.0)
                if not result.ok:
                    raise RuntimeError(f"{result.code}: {result.message}")
                shot = result.shot
                if model_sha is not None and shot.model_sha256 != model_sha:
                    raise RuntimeError("model changed while compiling the job")
                model_sha, model_version = shot.model_sha256, shot.model_version
                plans_by_step.append(_shot_dict(shot))
                planned_messages.append(shot)

            schedule = []
            for cycle in range(request.cycles):
                for step_index, step in enumerate(request.steps):
                    for repetition in range(step.repeat):
                        schedule.append({
                            "cycle": cycle + 1, "step": step_index + 1,
                            "repetition": repetition + 1, "interval_s": float(step.interval_s),
                            "plan_index": step_index,
                        })
            estimate = float(request.countdown_s) + len(schedule)
            for schedule_index, entry in enumerate(schedule[:-1]):
                following = schedule[schedule_index + 1]
                estimate += (float(request.cycle_rest_s)
                             if following["cycle"] != entry["cycle"]
                             else float(entry["interval_s"]))

            compiled = []
            for index, step in enumerate(request.steps):
                item = dict(plans_by_step[index])
                item.update({"repeat": step.repeat, "interval_s": step.interval_s})
                compiled.append(item)
            with self._lock:
                self._job.update({
                    "state": "READY", "phase": "READY", "code": "READY",
                    "message": "job compiled; waiting for start",
                    "model_version": model_version, "model_sha256": model_sha,
                    "compiled_steps": compiled, "schedule": schedule,
                    "planned_messages": planned_messages,
                    "estimated_min_duration_s": estimate,
                })
            self._event("info", "READY", "任务编译完成，等待开始")
            response.accepted = True
            response.code = "READY"
            response.message = "job compiled from live localization"
            response.job_id = job_id
            response.job_json = self._job_json()
        except Exception as exc:  # service boundary: return an explicit rejection
            with self._lock:
                self._job.update({"state": "REJECTED", "phase": "REJECTED",
                                  "code": "COMPILE_REJECTED", "message": str(exc)})
            self._event("error", "COMPILE_REJECTED", str(exc))
            response.code = "COMPILE_REJECTED"
            response.message = str(exc)
            response.job_id = job_id
            response.job_json = self._job_json()
        cache_value = (response.accepted, response.code, response.message,
                       response.job_id, response.job_json)
        if response.accepted:
            with self._lock:
                self._request_cache[request.request_id] = (fingerprint, cache_value)
        return response

    def _get_job(self, request, response):
        with self._lock:
            found = bool(self._job and self._job["job_id"] == request.job_id)
        response.found = found
        response.code = "OK" if found else "JOB_NOT_FOUND"
        response.message = "job found" if found else "job is not available in this process"
        response.job_json = self._job_json() if found else "{}"
        return response

    def _job_command(self, request, response):
        fingerprint = _digest({"job_id": request.job_id, "client_id": request.client_id,
                               "action": request.action})
        with self._lock:
            cached = self._command_cache.get(request.command_id)
            if cached:
                if cached[0] != fingerprint:
                    response.code = "IDEMPOTENCY_CONFLICT"
                    response.message = "command_id was already used with different content"
                    return response
                response.accepted, response.code, response.message, response.job_json = cached[1]
                return response
            job = self._job
            if not job or job["job_id"] != request.job_id:
                response.code = "JOB_NOT_FOUND"; response.message = "job not found"
                return response
            if request.action != "cancel" and request.client_id != job["client_id"]:
                response.code = "NOT_OWNER"; response.message = "only the owner may control this job"
                return response

            accepted, code, message = self._apply_command_locked(request.action)
            response.accepted, response.code, response.message = accepted, code, message
            response.job_json = self._job_json()
            self._command_cache[request.command_id] = (
                fingerprint, (accepted, code, message, response.job_json))
        return response

    def _apply_command_locked(self, action: str):
        state = self._job["state"]
        if action == "start" and state == "READY":
            ok, code, message = self._preflight_locked()
            if not ok:
                return False, code, message
            ok, code, message = self._enable_launcher_hold_locked("JOB_START")
            if not ok:
                return False, code, message
            self._job.update({"state": "RUNNING", "phase": "COUNTDOWN",
                              "code": "RUNNING", "message": "training started",
                              "last_heartbeat_monotonic": time.monotonic()})
            self._event("info", "RUNNING", "训练开始")
            self._start_worker_locked()
            return True, "RUNNING", "training started"
        if action == "pause" and state == "RUNNING":
            self._pause_locked("PAUSED_BY_USER", "用户请求暂停")
            return True, "PAUSED", "pause requested"
        if action == "resume" and state == "PAUSED":
            ok, code, message = self._preflight_locked()
            if not ok:
                return False, code, message
            ok, code, message = self._enable_launcher_hold_locked("JOB_RESUME")
            if not ok:
                return False, code, message
            self._job.update({"state": "RUNNING", "phase": "RESUMING",
                              "code": "RUNNING", "message": "training resumed",
                              "last_heartbeat_monotonic": time.monotonic()})
            self._event("info", "RESUMED", "训练继续")
            self._start_worker_locked()
            return True, "RUNNING", "training resumed"
        if action == "cancel" and state not in TERMINAL_STATES:
            self._job.update({"state": "CANCELLED", "phase": "CANCELLED",
                              "code": "CANCELLED", "message": "training cancelled"})
            goal = self._active_goal_handle
            if goal:
                goal.cancel_goal_async()
            self._event("warning", "CANCELLED", "训练已停止")
            self._stop_launcher_locked("JOB_CANCELLED")
            return True, "CANCELLED", "training cancelled"
        return False, "INVALID_TRANSITION", f"cannot {action} while state is {state}"

    def _preflight_locked(self):
        robot_ready = bool(
            self._robot and self._robot.valid and self._robot_at
            and time.monotonic() - self._robot_at <= self.localization_timeout_s)
        if not robot_ready:
            return False, "LOCALIZATION_NOT_READY", "live localization is missing, invalid or stale"
        launcher_ready = bool(
            self._launcher and self._launcher.online
            and self._launcher.rpm_valid and self._launcher.pitch_valid
            and self._launcher_at
            and time.monotonic() - self._launcher_at <= self.launcher_timeout_s)
        if not launcher_ready:
            detail = self._launcher.detail if self._launcher else "no launcher state"
            return False, "LAUNCHER_NOT_READY", detail
        try:
            if not self._model_client.wait_for_service(timeout_sec=1.0):
                return False, "MODEL_NOT_READY", "model service is unavailable"
            model = self._wait_future(
                self._model_client.call_async(GetModelInfo.Request()), 3.0)
        except Exception as exc:
            return False, "MODEL_NOT_READY", str(exc)
        if not model.ready:
            return False, "MODEL_NOT_READY", model.message
        if model.model_sha256 != self._job["model_sha256"]:
            return False, "MODEL_CHANGED", "model SHA changed after job compilation"
        return True, "OK", "preflight passed"

    def _heartbeat(self, request, response):
        with self._lock:
            job = self._job
            if not job or job["job_id"] != request.job_id:
                response.code = "JOB_NOT_FOUND"; response.message = "job not found"
            elif request.client_id != job["client_id"]:
                response.code = "NOT_OWNER"; response.message = "heartbeat client is not the owner"
            else:
                job["last_heartbeat_monotonic"] = time.monotonic()
                response.accepted = True; response.code = "OK"; response.message = "heartbeat accepted"
            response.job_json = self._job_json() if job else "{}"
        return response

    def _check_heartbeat(self) -> None:
        with self._lock:
            if not self._job or self._job["state"] != "RUNNING":
                return
            if time.monotonic() - self._job["last_heartbeat_monotonic"] > self.heartbeat_timeout_s:
                self._pause_locked("HEARTBEAT_TIMEOUT", "Windows 心跳超时，已请求安全暂停")

    def _pause_locked(self, code: str, message: str) -> None:
        self._job.update({"state": "PAUSED", "phase": "PAUSING",
                          "code": code, "message": message})
        goal = self._active_goal_handle
        if goal:
            goal.cancel_goal_async()
        self._event("warning", code, message)
        self._stop_launcher_locked(code)

    def _start_worker_locked(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._run_job, name="serve-job", daemon=True)
        self._worker.start()

    def _wait_while_running(self, seconds: float, phase: str) -> bool:
        deadline = time.monotonic() + max(0.0, seconds)
        with self._lock:
            if self._job:
                self._job["phase"] = phase
                self._job["next_deadline_monotonic"] = deadline
        while time.monotonic() < deadline:
            with self._lock:
                if not self._job or self._job["state"] != "RUNNING":
                    return False
            time.sleep(min(0.05, deadline - time.monotonic()))
        return True

    def _send_shot(self, index: int):
        with self._lock:
            job = self._job
            entry = job["schedule"][index]
            template = job["planned_messages"][entry["plan_index"]]
            goal = ExecuteShot.Goal()
            goal.job_id = job["job_id"]
            goal.shot_id = f"{job['job_id']}-shot-{index + 1}"
            job.update({"current_shot": index + 1, "current_step": entry["step"],
                        "current_cycle": entry["cycle"], "phase": "WAITING_STATE",
                        "feed_triggered": False, "feed_confirmed": False})

        failed = ExecuteShot.Result()
        if not self._plan_client.wait_for_service(timeout_sec=2.0):
            failed.code = "PLANNER_UNAVAILABLE"
            failed.message = "planner service is unavailable before shot"
            return failed
        plan_request = PlanShot.Request()
        plan_request.request_id = f"{goal.shot_id}:plan:{uuid.uuid4().hex}"
        plan_request.step_id = template.step_id
        plan_request.target = template.target
        try:
            plan_result = self._wait_future(
                self._plan_client.call_async(plan_request), 5.0)
        except Exception as exc:
            failed.code = "PLAN_RETRY_FAILED"
            failed.message = str(exc)
            return failed
        if not plan_result.ok:
            failed.code = plan_result.code or "PLAN_REJECTED"
            failed.message = plan_result.message
            return failed
        with self._lock:
            expected_model_sha = self._job["model_sha256"] if self._job else ""
        if plan_result.shot.model_sha256 != expected_model_sha:
            failed.code = "MODEL_CHANGED"
            failed.message = "model SHA changed while the job was running"
            return failed
        goal.shot = plan_result.shot
        with self._lock:
            if not self._job or self._job["state"] != "RUNNING":
                failed.code = "CANCELLED"
                failed.message = "job stopped while replanning the shot"
                return failed

        # Renew immediately before sending the action goal.  The periodic renewal
        # normally keeps the lease alive during countdown/rest, but this explicit
        # renewal closes the timing window between the last timer callback and the
        # controller's goal callback (especially after a long countdown).
        ok, code, message = self._request_launcher_hold(
            goal.job_id, True, "SHOT_START", timeout_s=1.0)
        if not ok:
            failed.code = "LAUNCHER_HOLD_UNAVAILABLE"
            failed.message = f"{code}: {message}"
            return failed
        if not self._shot_client.wait_for_server(timeout_sec=3.0):
            failed.code = "EXECUTE_SHOT_UNAVAILABLE"
            failed.message = "ExecuteShot action server is unavailable"
            return failed

        def feedback_callback(feedback_message):
            feedback = feedback_message.feedback
            with self._lock:
                if not self._job:
                    return
                self._job["phase"] = feedback.phase
                self._job["gate_feedback"] = {
                    "yaw_error_deg": feedback.yaw_error_deg,
                    "upper_rpm_error_ratio": feedback.upper_rpm_error_ratio,
                    "lower_rpm_error_ratio": feedback.lower_rpm_error_ratio,
                    "pitch_error_deg": feedback.pitch_error_deg,
                    "stable_ready": feedback.gates_ready,
                    "detail": feedback.detail,
                }
                if feedback.phase in {"FEED_TRIGGERED", "FEED_DWELL"}:
                    self._job["feed_triggered"] = True

        goal_future = self._shot_client.send_goal_async(goal, feedback_callback=feedback_callback)
        handle = self._wait_future(goal_future, 5.0)
        if not handle.accepted:
            raise RuntimeError(
                "ExecuteShot goal was rejected; inspect serve_controller_node logs "
                "for GOAL_REJECTED_* to identify emergency stop, an active goal, "
                "or launcher-hold ownership/lease state")
        with self._lock:
            self._active_goal_handle = handle
        try:
            wrapped = self._wait_future(handle.get_result_async(), 70.0)
            return wrapped.result
        finally:
            with self._lock:
                self._active_goal_handle = None

    def _run_job(self) -> None:
        try:
            with self._lock:
                job = self._job
                start_index = int(job["completed_balls"])
                countdown = float(job["program"]["countdown_s"]) if start_index == 0 else 0.0
            if countdown and not self._wait_while_running(countdown, "COUNTDOWN"):
                return
            index = start_index
            while True:
                with self._lock:
                    if not self._job or self._job["state"] != "RUNNING":
                        return
                    if index >= len(self._job["schedule"]):
                        self._job.update({"state": "COMPLETED", "phase": "COMPLETED",
                                          "code": "COMPLETED", "message": "training completed",
                                          "next_deadline_monotonic": 0.0})
                        self._event("info", "COMPLETED", "训练完成")
                        self._stop_launcher_locked("JOB_COMPLETED")
                        return
                    current_entry = self._job["schedule"][index]
                retry = 0
                while True:
                    result = self._send_shot(index)
                    if (result.success or result.feed_triggered
                            or result.code not in RETRYABLE_PRE_FEED_CODES
                            or retry >= self.max_pre_feed_retries):
                        break
                    retry += 1
                    self._event(
                        "warning", "SHOT_RETRY",
                        f"第 {index + 1} 球拨球前失败，重新规划后重试 "
                        f"({retry}/{self.max_pre_feed_retries}): "
                        f"{result.code}: {result.message}")
                    if not self._wait_while_running(0.25, "REPLANNING"):
                        return
                with self._lock:
                    if self._job["state"] in {"PAUSED", "CANCELLED"} and not result.feed_triggered:
                        if self._job["state"] == "PAUSED":
                            self._job["phase"] = "PAUSED"
                        return
                    if not result.success:
                        self._job["feed_triggered"] = bool(result.feed_triggered)
                        self._job["feed_confirmed"] = bool(result.feed_confirmed)
                        if result.feed_triggered and not result.feed_confirmed:
                            self._job["triggered_unconfirmed_balls"] += 1
                        if result.code == "CANCELLED" and self._job["state"] == "PAUSED":
                            self._job["phase"] = "PAUSED"
                            return
                        self._job.update({"state": "FAILED", "phase": "FAILED",
                                          "code": result.code, "message": result.message})
                        self._event("error", result.code, result.message)
                        self._stop_launcher_locked(result.code or "SHOT_FAILED")
                        return
                    self._job["completed_balls"] = index + 1
                    self._job["feed_triggered"] = result.feed_triggered
                    self._job["feed_confirmed"] = result.feed_confirmed
                    if result.feed_triggered and not result.feed_confirmed:
                        self._job["triggered_unconfirmed_balls"] += 1
                    self._event("info", result.code, result.message)
                    if self._job["state"] == "PAUSED":
                        self._job["phase"] = "PAUSED"
                        return
                    next_index = index + 1
                    if next_index >= len(self._job["schedule"]):
                        index = next_index
                        continue
                    next_entry = self._job["schedule"][next_index]
                    if next_entry["cycle"] != current_entry["cycle"]:
                        delay = float(self._job["program"]["cycle_rest_s"])
                        phase = "CYCLE_REST"
                    else:
                        delay = float(current_entry["interval_s"])
                        phase = "INTERVAL"
                    stop_during_rest = bool(
                        self._job["program"].get("stop_wheels_during_rest"))
                    if stop_during_rest:
                        self._job["phase"] = phase
                        self._stop_launcher_locked("REST_WHEELS_STOPPED")
                if not self._wait_while_running(delay, phase):
                    return
                index = next_index
        except Exception as exc:
            with self._lock:
                if self._job and self._job["state"] not in TERMINAL_STATES:
                    self._job.update({"state": "FAILED", "phase": "FAILED",
                                      "code": "EXECUTION_ERROR", "message": str(exc)})
                    self._event("error", "EXECUTION_ERROR", str(exc))
                    self._stop_launcher_locked("EXECUTION_ERROR")

    def _publish_status(self) -> None:
        now = time.monotonic()
        message = ServeSystemStatus()
        message.header.stamp = self.get_clock().now().to_msg()
        message.interface_version = INTERFACE_VERSION
        with self._lock:
            job = self._job
            if job:
                message.job_id = job["job_id"]; message.job_name = job["name"]
                message.job_state = job["state"]; message.phase = job["phase"]
                message.revision = job["revision"]
                message.completed_shots = job["completed_balls"]
                message.triggered_unconfirmed_shots = job["triggered_unconfirmed_balls"]
                message.total_shots = job["total_balls"]
                message.current_shot = job["current_shot"]
                message.current_step = job["current_step"]
                message.current_cycle = job["current_cycle"]
                message.feed_confirmed = bool(job["feed_confirmed"])
                message.feed_triggered = bool(job["feed_triggered"])
                message.code = job["code"]; message.message = job["message"]
                deadline = job.get("next_deadline_monotonic", 0.0)
                message.time_to_next_shot_s = max(0.0, deadline - now) if deadline else 0.0
                index = min(max(job["current_shot"] - 1, 0), len(job["schedule"]) - 1)
                if job["schedule"]:
                    shot = job["planned_messages"][job["schedule"][index]["plan_index"]]
                    message.target_yaw_rad = shot.target_yaw_rad
                    message.upper_target_rpm = shot.upper_target_rpm
                    message.lower_target_rpm = shot.lower_target_rpm
                    message.pitch_target_deg = shot.pitch_target_deg
                gate = job.get("gate_feedback", {})
                message.yaw_error_deg = float(gate.get("yaw_error_deg", 0.0))
                message.upper_rpm_error_ratio = float(gate.get("upper_rpm_error_ratio", 0.0))
                message.lower_rpm_error_ratio = float(gate.get("lower_rpm_error_ratio", 0.0))
                message.pitch_error_deg = float(gate.get("pitch_error_deg", 0.0))
                message.stable_ready = bool(gate.get("stable_ready", False))
                message.gate_detail = str(gate.get("detail", ""))
            else:
                message.job_state = "IDLE"; message.phase = "IDLE"
                message.code = "IDLE"; message.message = "no job in memory"
            robot = self._robot
            message.robot_age_s = now - self._robot_at if self._robot_at else 1e9
            if robot and len(robot.state) >= 6:
                message.robot_valid = bool(robot.valid)
                try:
                    message.robot_x_m, message.robot_y_m = localization_to_court_xy(
                        robot.state[0], robot.state[1])
                except ValueError:
                    message.robot_valid = False
                message.robot_yaw_rad = robot.state[2]
                message.robot_vx_mps, message.robot_vy_mps, message.robot_yaw_rate_radps = robot.state[3:6]
            launcher = self._launcher
            message.launcher_age_s = now - self._launcher_at if self._launcher_at else 1e9
            if launcher:
                message.launcher_online = bool(launcher.online)
                message.launcher_rpm_valid = bool(launcher.rpm_valid)
                message.launcher_pitch_valid = bool(launcher.pitch_valid)
                message.upper_actual_rpm = launcher.upper_actual_rpm
                message.lower_actual_rpm = launcher.lower_actual_rpm
                message.pitch_actual_deg = launcher.pitch_actual_deg
            message.robot_state_fresh = bool(
                message.robot_valid
                and message.robot_age_s <= self.localization_timeout_s)
            message.launcher_state_fresh = bool(
                message.launcher_online
                and message.launcher_age_s <= self.launcher_timeout_s)
            message.yaw_ready = bool(
                abs(message.yaw_error_deg) <= self.yaw_tolerance_deg)
            speed = math.hypot(message.robot_vx_mps, message.robot_vy_mps)
            message.speed_ready = bool(
                speed <= self.linear_speed_limit_mps
                and abs(message.robot_yaw_rate_radps)
                <= self.angular_speed_limit_radps)
            message.rpm_ready = bool(
                message.launcher_rpm_valid
                and message.upper_rpm_error_ratio <= self.rpm_tolerance_ratio
                and message.lower_rpm_error_ratio <= self.rpm_tolerance_ratio)
            message.pitch_ready = bool(
                message.launcher_pitch_valid
                and message.pitch_error_deg <= self.pitch_tolerance_deg)
        self._status_pub.publish(message)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ServeJobManagerNode()
    executor = MultiThreadedExecutor(num_threads=6)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
