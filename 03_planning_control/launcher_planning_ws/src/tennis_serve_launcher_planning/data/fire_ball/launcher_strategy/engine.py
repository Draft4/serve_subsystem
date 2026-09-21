"""Control-facing engine that loads one immutable strategy release."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .core import FrozenTrajectoryModel, StrategyError, build_target_geometry, search_parameters
from .protocol import (
    HEIGHT_UNSAFE,
    INTERNAL_ERROR,
    MODEL_LOAD_FAILED,
    NO_SAFE_CANDIDATE,
    TARGET_OUT_OF_RANGE,
    ProtocolError,
    RecommendationRequest,
    error_response,
)


class ModelLoadError(RuntimeError):
    """The model release file cannot be trusted or loaded."""


class StrategyEngine:
    """Persistent engine for local controller integration."""

    def __init__(self, model_path: str | Path) -> None:
        self.model_path = Path(model_path).expanduser().resolve()
        try:
            raw = self.model_path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("schema_version") != 1:
                raise ModelLoadError("模型发布文件 schema_version 无效")
            self.model_version = str(payload["model_version"])
            self.model_sha256 = hashlib.sha256(raw).hexdigest()
            self.config = dict(payload["strategy_config"])
            self.model = FrozenTrajectoryModel(dict(payload["model"]))
            self._validate_release_config()
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError, StrategyError) as error:
            if isinstance(error, ModelLoadError):
                raise
            raise ModelLoadError(f"无法加载策略模型：{error}") from error

    def _validate_release_config(self) -> None:
        required = {
            "court_width_m", "net_y_m", "machine_y_min_m", "court_length_m",
            "launcher_height_m", "physical_net_height_m", "safety_margin_m",
            "net_height_max_m", "top_k", "samples", "coarse_samples",
            "shortlist_size", "allow_extrapolation",
        }
        missing = sorted(required.difference(self.config))
        if missing:
            raise ModelLoadError(f"模型发布配置缺少字段：{', '.join(missing)}")
        if int(self.config["samples"]) != len(self.model.standard_normal_samples):
            raise ModelLoadError("固定采样数与模型快照不一致")
        if int(self.config["coarse_samples"]) < 50 or int(self.config["shortlist_size"]) < int(self.config["top_k"]):
            raise ModelLoadError("两阶段搜索配置无效")

    def health_response(self, request_id: str) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "ok": True,
            "code": "OK",
            "status": "ready",
            "decision": "reject",
            "model_version": self.model_version,
            "model_sha256": self.model_sha256,
        }

    def _validate_target(self, request: RecommendationRequest) -> None:
        cfg = self.config
        court_width = float(cfg["court_width_m"])
        net_y = float(cfg["net_y_m"])
        machine_y_min = float(cfg["machine_y_min_m"])
        court_length = float(cfg["court_length_m"])
        machine_margin = float(cfg.get("machine_boundary_margin_m", 0.0))
        if not (
            -machine_margin - 1e-9 <= request.machine_x_m <= court_width + machine_margin + 1e-9
            and machine_y_min - machine_margin - 1e-9
            <= request.machine_y_m <= court_length + machine_margin + 1e-9
        ):
            raise ProtocolError(TARGET_OUT_OF_RANGE, "机器坐标超出允许范围", request.request_id)
        if not (
            0.0 <= request.landing_x_min_m < request.landing_x_max_m <= court_width
            and 0.0 <= request.landing_y_min_m < request.landing_y_max_m <= net_y
        ):
            raise ProtocolError(TARGET_OUT_OF_RANGE, "落点矩形必须完整位于对侧场地", request.request_id)
        minimum_height = float(cfg["physical_net_height_m"]) + float(cfg["safety_margin_m"])
        if request.net_height_min_m < minimum_height:
            raise ProtocolError(HEIGHT_UNSAFE, f"过网高度最低值不得低于 {minimum_height:.3f} m", request.request_id)
        if not request.net_height_min_m < request.net_height_max_m <= float(cfg["net_height_max_m"]):
            raise ProtocolError(HEIGHT_UNSAFE, "过网高度范围无效或超过当前策略上限", request.request_id)

    @staticmethod
    def _candidate_payload(candidate: Any) -> dict[str, Any]:
        payload = asdict(candidate)
        return {
            "upper_rpm": payload["upper_rpm"],
            "lower_rpm": payload["lower_rpm"],
            "vertical_servo_angle_deg": payload["vertical_servo_angle_deg"],
            "predicted_a": payload["predicted_a"],
            "predicted_b": payload["predicted_b"],
            "landing_median_m": payload["landing_median_m"],
            "landing_p05_m": payload["landing_p05_m"],
            "landing_p95_m": payload["landing_p95_m"],
            "net_height_median_m": payload["net_height_median_m"],
            "net_height_p05_m": payload["net_height_p05_m"],
            "net_height_p95_m": payload["net_height_p95_m"],
            "success_probability": payload["success_probability"],
            "confidence": payload["confidence"],
            "nearest_training_distance": payload["nearest_training_distance"],
        }

    def recommend(self, request: RecommendationRequest) -> dict[str, Any]:
        self._validate_target(request)
        cfg = self.config
        target_midpoint = (request.net_height_min_m + request.net_height_max_m) / 2.0
        try:
            geometry = build_target_geometry(
                request.machine_x_m, request.machine_y_m,
                request.landing_x_min_m, request.landing_x_max_m,
                request.landing_y_min_m, request.landing_y_max_m,
                target_midpoint, float(cfg["launcher_height_m"]), float(cfg["net_y_m"]),
            )
            candidates = search_parameters(
                self.model, geometry,
                launcher_height_m=float(cfg["launcher_height_m"]),
                physical_net_height_m=float(cfg["physical_net_height_m"]),
                safety_margin_m=float(cfg["safety_margin_m"]),
                net_height_min_m=request.net_height_min_m,
                net_height_max_m=request.net_height_max_m,
                top_k=int(cfg["top_k"]),
                coarse_samples=int(cfg["coarse_samples"]),
                shortlist_size=int(cfg["shortlist_size"]),
                allow_extrapolation=bool(cfg["allow_extrapolation"]),
                extrapolation_distance_multiplier=float(
                    cfg.get("extrapolation_distance_multiplier", 2.0)),
            )
        except StrategyError as error:
            code = TARGET_OUT_OF_RANGE if "球网距离" in str(error) else NO_SAFE_CANDIDATE
            return error_response(
                request_id=request.request_id, code=code, message=str(error),
                model_version=self.model_version, model_sha256=self.model_sha256,
            )
        if not candidates:
            return error_response(
                request_id=request.request_id, code=NO_SAFE_CANDIDATE,
                message="数据邻域内没有可执行的候选参数",
                model_version=self.model_version, model_sha256=self.model_sha256,
            )
        alternatives = [self._candidate_payload(candidate) for candidate in candidates]
        recommended = {
            **alternatives[0],
            "horizontal_heading_deg": geometry.horizontal_heading_deg,
        }
        decision = "execute"
        return {
            "request_id": request.request_id,
            "ok": True,
            "code": "OK",
            "status": "success",
            "decision": decision,
            "recommended": recommended,
            "alternatives": alternatives,
            "geometry": {
                "target_center_x_m": geometry.target_center_x,
                "target_center_y_m": geometry.target_center_y,
                "horizontal_heading_deg": geometry.horizontal_heading_deg,
                "net_distance_m": geometry.net_distance,
                "landing_min_m": geometry.landing_min,
                "landing_max_m": geometry.landing_max,
                "target_landing_m": geometry.target_landing,
                "target_a": geometry.target_a,
                "target_b": geometry.target_b,
            },
            "model_version": self.model_version,
            "model_sha256": self.model_sha256,
            "diagnostics": {
                "prediction_cache_hit": self.model.last_context_cache_hit,
                "training_summary": self.model.training_summary(),
            },
        }

    def handle(self, parsed_request: RecommendationRequest | str, request_id: str) -> dict[str, Any]:
        if parsed_request == "health":
            return self.health_response(request_id)
        try:
            return self.recommend(parsed_request)
        except ProtocolError as error:
            return error_response(
                request_id=error.request_id or request_id,
                code=error.code,
                message=str(error),
                model_version=self.model_version,
                model_sha256=self.model_sha256,
            )

    def unexpected_error(self, request_id: str | None, error: Exception) -> dict[str, Any]:
        return error_response(
            request_id=request_id, code=INTERNAL_ERROR, message=f"策略服务内部错误：{error}",
            model_version=self.model_version, model_sha256=self.model_sha256,
        )
