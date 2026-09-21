"""Versioned JSON Lines protocol definitions for the control-facing service."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


INVALID_REQUEST = "INVALID_REQUEST"
TARGET_OUT_OF_RANGE = "TARGET_OUT_OF_RANGE"
HEIGHT_UNSAFE = "HEIGHT_UNSAFE"
NO_SAFE_CANDIDATE = "NO_SAFE_CANDIDATE"
MODEL_LOAD_FAILED = "MODEL_LOAD_FAILED"
INTERNAL_ERROR = "INTERNAL_ERROR"


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str, request_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id


@dataclass(frozen=True)
class RecommendationRequest:
    request_id: str
    machine_x_m: float
    machine_y_m: float
    landing_x_min_m: float
    landing_x_max_m: float
    landing_y_min_m: float
    landing_y_max_m: float
    net_height_min_m: float
    net_height_max_m: float


def _mapping(value: Any, name: str, request_id: str | None) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolError(INVALID_REQUEST, f"{name} 必须是对象", request_id)
    return value


def _number(value: Any, name: str, request_id: str | None) -> float:
    if isinstance(value, bool):
        raise ProtocolError(INVALID_REQUEST, f"{name} 必须是有限数值", request_id)
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ProtocolError(INVALID_REQUEST, f"{name} 必须是有限数值", request_id) from error
    if not math.isfinite(result):
        raise ProtocolError(INVALID_REQUEST, f"{name} 必须是有限数值", request_id)
    return result


def parse_request(payload: Any) -> RecommendationRequest | str:
    """Parse one request.  Returns ``"health"`` for the health action."""
    root = _mapping(payload, "请求", None)
    raw_request_id = root.get("request_id")
    request_id = raw_request_id if isinstance(raw_request_id, str) and raw_request_id else None
    if request_id is None:
        raise ProtocolError(INVALID_REQUEST, "request_id 必须是非空字符串")
    action = root.get("action")
    if action == "health":
        return "health"
    if action != "recommend":
        raise ProtocolError(INVALID_REQUEST, "action 必须为 recommend 或 health", request_id)
    machine = _mapping(root.get("machine"), "machine", request_id)
    target = _mapping(root.get("target"), "target", request_id)
    landing = _mapping(target.get("landing"), "target.landing", request_id)
    net_height = _mapping(target.get("net_height"), "target.net_height", request_id)
    return RecommendationRequest(
        request_id=request_id,
        machine_x_m=_number(machine.get("x_m"), "machine.x_m", request_id),
        machine_y_m=_number(machine.get("y_m"), "machine.y_m", request_id),
        landing_x_min_m=_number(landing.get("x_min_m"), "target.landing.x_min_m", request_id),
        landing_x_max_m=_number(landing.get("x_max_m"), "target.landing.x_max_m", request_id),
        landing_y_min_m=_number(landing.get("y_min_m"), "target.landing.y_min_m", request_id),
        landing_y_max_m=_number(landing.get("y_max_m"), "target.landing.y_max_m", request_id),
        net_height_min_m=_number(net_height.get("min_m"), "target.net_height.min_m", request_id),
        net_height_max_m=_number(net_height.get("max_m"), "target.net_height.max_m", request_id),
    )


def error_response(
    *, request_id: str | None, code: str, message: str,
    model_version: str | None = None, model_sha256: str | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "request_id": request_id,
        "ok": False,
        "code": code,
        "decision": "reject",
        "message": message,
    }
    if model_version is not None:
        response["model_version"] = model_version
    if model_sha256 is not None:
        response["model_sha256"] = model_sha256
    return response
