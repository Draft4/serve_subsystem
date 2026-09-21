"""Simple in-process Python API for the frozen launcher strategy."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

from .engine import StrategyEngine
from .protocol import ProtocolError, error_response, parse_request


class RecommendationRejected(RuntimeError):
    """Raised when a caller asks for parameters but the strategy rejects the target."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.code = str(response.get("code", "INTERNAL_ERROR"))
        message = str(response.get("message", "发球策略未返回可执行参数"))
        super().__init__(f"{self.code}: {message}")


_ENGINE_LOCK = threading.RLock()
_ENGINES: dict[Path, StrategyEngine] = {}


def _default_model_path() -> Path:
    package_dir = Path(__file__).resolve().parent
    candidates = (
        package_dir.parent / "model_snapshot.json",
        package_dir.parent / "control_delivery" / "model_snapshot.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "未找到 model_snapshot.json；请保持模型文件与 launcher_strategy 文件夹位于同一目录"
    )


def _engine(model_path: str | Path | None) -> StrategyEngine:
    resolved = (
        Path(model_path).expanduser().resolve()
        if model_path is not None
        else _default_model_path().resolve()
    )
    with _ENGINE_LOCK:
        engine = _ENGINES.get(resolved)
        if engine is None:
            engine = StrategyEngine(resolved)
            _ENGINES[resolved] = engine
        return engine


def recommend_serve(
    *,
    machine_x_m: float,
    machine_y_m: float,
    landing_x_min_m: float,
    landing_x_max_m: float,
    landing_y_min_m: float,
    landing_y_max_m: float,
    net_height_min_m: float,
    net_height_max_m: float,
    request_id: str | None = None,
    model_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return a complete strategy response for one requested landing region.

    All positions and heights use metres.  The returned command is executable only
    when ``response["decision"] == "execute"``.
    """
    actual_request_id = request_id or f"python-{uuid.uuid4().hex}"
    engine = _engine(model_path)
    payload = {
        "request_id": actual_request_id,
        "action": "recommend",
        "machine": {"x_m": machine_x_m, "y_m": machine_y_m},
        "target": {
            "landing": {
                "x_min_m": landing_x_min_m,
                "x_max_m": landing_x_max_m,
                "y_min_m": landing_y_min_m,
                "y_max_m": landing_y_max_m,
            },
            "net_height": {"min_m": net_height_min_m, "max_m": net_height_max_m},
        },
    }
    try:
        parsed = parse_request(payload)
        return engine.handle(parsed, actual_request_id)
    except ProtocolError as error:
        return error_response(
            request_id=error.request_id or actual_request_id,
            code=error.code,
            message=str(error),
            model_version=engine.model_version,
            model_sha256=engine.model_sha256,
        )
    except Exception as error:  # Keep the controller-facing function fail-safe.
        return engine.unexpected_error(actual_request_id, error)


def get_serve_parameters(**kwargs: Any) -> dict[str, Any]:
    """Return only the preferred executable command, or raise on rejection."""
    response = recommend_serve(**kwargs)
    if response.get("decision") != "execute" or "recommended" not in response:
        raise RecommendationRejected(response)
    return dict(response["recommended"])

