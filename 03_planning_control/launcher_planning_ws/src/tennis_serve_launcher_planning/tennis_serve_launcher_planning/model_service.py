"""Frozen launcher model access.  This module has no ROS or hardware dependency."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import sys
import threading
from pathlib import Path

from tennis_serve_common.core import (
    court_to_legacy_model_y, target_bounds,
    validate_absolute_target, validate_with_tolerance,
)


class ModelError(RuntimeError):
    pass


class ModelService:
    def __init__(self, model_path: str,
                 machine_boundary_tolerance_m: float = 1.0) -> None:
        self.model_path = Path(model_path).expanduser().resolve()
        self.machine_boundary_tolerance_m = float(machine_boundary_tolerance_m)
        self._lock = threading.Lock()
        self._metadata = None
        strategy_root = str(self.model_path.parent)
        if strategy_root not in sys.path:
            sys.path.insert(0, strategy_root)
        self._recommend = importlib.import_module("launcher_strategy").recommend_serve

    def metadata(self) -> dict:
        if self._metadata is not None:
            return dict(self._metadata)
        try:
            model_bytes = self.model_path.read_bytes()
            snapshot = json.loads(model_bytes.decode("utf-8"))
            digest = hashlib.sha256(model_bytes).hexdigest()
            self._metadata = {
                "model_version": str(snapshot["model_version"]),
                "model_sha256": digest,
                "source_workbook_sha256": str(snapshot["metadata"]["source_sha256"]),
                "strategy_config": dict(snapshot["strategy_config"]),
                "training_summary": dict(snapshot["model"]["trainingSummary"]),
            }
        except ModelError:
            raise
        except Exception as exc:
            raise ModelError("cannot load model delivery: {}".format(exc)) from exc
        return dict(self._metadata)

    def plan(self, request_id: str, step_id: str, target, robot) -> dict:
        validate_absolute_target(target)
        metadata = self.metadata()
        x_min, x_max, y_min, y_max = target_bounds(target)
        config = metadata["strategy_config"]
        court_width = float(config["court_width_m"])
        court_length = float(config["court_length_m"])
        machine_y_max = court_length - float(config["machine_y_min_m"])
        try:
            model_machine_x = validate_with_tolerance(
                robot.x_m, 0.0, court_width,
                self.machine_boundary_tolerance_m, "robot.x_m")
            court_machine_y = validate_with_tolerance(
                robot.y_m, 0.0, machine_y_max,
                self.machine_boundary_tolerance_m, "robot.y_m")
        except ValueError as exc:
            raise ModelError(str(exc)) from exc

        # RobotState is already in court_origin_v2 at the ROS input boundary.
        # The frozen model shares that X axis but puts Y=0 at the opponent
        # baseline, so only Y flips here.
        model_machine_y = court_to_legacy_model_y(court_machine_y, court_length)
        model_target_y_min = court_to_legacy_model_y(y_max, court_length)
        model_target_y_max = court_to_legacy_model_y(y_min, court_length)
        with self._lock:
            result = self._recommend(
                request_id=request_id,
                machine_x_m=model_machine_x,
                machine_y_m=model_machine_y,
                landing_x_min_m=x_min,
                landing_x_max_m=x_max,
                landing_y_min_m=model_target_y_min,
                landing_y_max_m=model_target_y_max,
                net_height_min_m=target.net_height_min_m,
                net_height_max_m=target.net_height_max_m,
                model_path=self.model_path,
            )
        if result.get("ok") is not True or result.get("decision") != "execute":
            raise ModelError("{}: {}".format(result.get("code", "REJECTED"), result.get("message", "model rejected")))
        candidate = result["recommended"]
        for key in (
            "upper_rpm", "lower_rpm", "vertical_servo_angle_deg", "success_probability",
            "landing_median_m", "landing_p05_m", "landing_p95_m",
            "net_height_median_m", "net_height_p05_m", "net_height_p95_m",
        ):
            if not isinstance(candidate.get(key), (int, float)) or not math.isfinite(candidate[key]):
                raise ModelError("invalid model field {}".format(key))
        return {
            "request_id": request_id, "step_id": step_id,
            "robot_x_m": robot.x_m, "robot_y_m": robot.y_m, "robot_yaw_rad": robot.yaw_rad,
            "upper_target_rpm": int(candidate["upper_rpm"]),
            "lower_target_rpm": int(candidate["lower_rpm"]),
            "pitch_target_deg": float(candidate["vertical_servo_angle_deg"]),
            "success_probability": float(candidate["success_probability"]),
            "confidence": str(candidate.get("confidence", "unknown")),
            "landing_median_m": float(candidate["landing_median_m"]),
            "landing_p05_m": float(candidate["landing_p05_m"]),
            "landing_p95_m": float(candidate["landing_p95_m"]),
            "net_height_median_m": float(candidate["net_height_median_m"]),
            "net_height_p05_m": float(candidate["net_height_p05_m"]),
            "net_height_p95_m": float(candidate["net_height_p95_m"]),
            "model_version": metadata["model_version"], "model_sha256": metadata["model_sha256"],
            "raw": result,
        }
