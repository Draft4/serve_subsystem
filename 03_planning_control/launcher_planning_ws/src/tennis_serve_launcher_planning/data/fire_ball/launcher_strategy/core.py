"""Numerical runtime for the frozen launcher strategy model.

This module deliberately depends only on NumPy.  Training and workbook parsing
remain outside the delivery runtime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import product
from typing import Any

import numpy as np


EPSILON = 1e-12


class StrategyError(ValueError):
    """A requested target cannot be searched safely."""


@dataclass(frozen=True, order=True)
class MachineSetting:
    upper_rpm: int
    lower_rpm: int
    angle_deg: float


@dataclass(frozen=True)
class TargetGeometry:
    target_center_x: float
    target_center_y: float
    horizontal_heading_deg: float
    net_distance: float
    landing_min: float
    landing_max: float
    target_landing: float
    target_a: float
    target_b: float


@dataclass(frozen=True)
class CandidateResult:
    upper_rpm: int
    lower_rpm: int
    vertical_servo_angle_deg: float
    predicted_a: float
    predicted_b: float
    landing_median_m: float
    landing_p05_m: float
    landing_p95_m: float
    net_height_median_m: float
    net_height_p05_m: float
    net_height_p95_m: float
    success_probability: float
    confidence: str
    nearest_training_distance: float


class FrozenTrajectoryModel:
    """Gaussian-process model reconstructed from a release JSON snapshot."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        required = {
            "invariant", "xMean", "xScale", "yMean", "yScale", "xTrain",
            "xRaw", "alpha", "cholesky", "lengthScale", "noiseVariance",
            "nearestDistanceLimit", "shotCovariance", "upperValues", "lowerValues",
            "angleValues", "netDistanceRange", "standardNormalSamples",
            "trainingSummary",
        }
        missing = sorted(required.difference(snapshot))
        if missing:
            raise StrategyError(f"模型快照缺少字段：{', '.join(missing)}")
        self.invariant = bool(snapshot["invariant"])
        self.x_mean = np.asarray(snapshot["xMean"], dtype=float)
        self.x_scale = np.asarray(snapshot["xScale"], dtype=float)
        self.y_mean = np.asarray(snapshot["yMean"], dtype=float)
        self.y_scale = np.asarray(snapshot["yScale"], dtype=float)
        self.x_train = np.asarray(snapshot["xTrain"], dtype=float)
        self.x_raw = np.asarray(snapshot["xRaw"], dtype=float)
        self.alpha = np.asarray(snapshot["alpha"], dtype=float)
        self.cholesky = np.asarray(snapshot["cholesky"], dtype=float)
        self.length_scale = float(snapshot["lengthScale"])
        self.noise_variance = float(snapshot["noiseVariance"])
        self.nearest_distance_limit = float(snapshot["nearestDistanceLimit"])
        self.shot_covariance = np.asarray(snapshot["shotCovariance"], dtype=float)
        self.upper_values = tuple(int(value) for value in snapshot["upperValues"])
        self.lower_values = tuple(int(value) for value in snapshot["lowerValues"])
        self.angle_values = tuple(float(value) for value in snapshot["angleValues"])
        self.net_distance_range = tuple(float(value) for value in snapshot["netDistanceRange"])
        self.standard_normal_samples = np.asarray(
            snapshot["standardNormalSamples"], dtype=float
        )
        self._training_summary = dict(snapshot["trainingSummary"])
        self._observed_feature_keys = {
            tuple(np.round(row, 9)) for row in self.x_raw
        }
        self._context_cache: dict[tuple[float, float], tuple[Any, ...]] = {}
        self.last_context_cache_hit = False
        arrays = (
            self.x_mean, self.x_scale, self.y_mean, self.y_scale, self.x_train,
            self.x_raw, self.alpha, self.cholesky, self.shot_covariance,
            self.standard_normal_samples,
        )
        if (
            not all(np.isfinite(array).all() for array in arrays)
            or self.x_train.ndim != 2
            or self.x_train.shape != self.x_raw.shape
            or self.alpha.shape != (self.x_train.shape[0], 2)
            or self.cholesky.shape != (self.x_train.shape[0], self.x_train.shape[0])
            or self.standard_normal_samples.ndim != 2
            or self.standard_normal_samples.shape[1] != 2
            or self.shot_covariance.shape != (2, 2)
            or self.length_scale <= 0
            or self.nearest_distance_limit <= 0
        ):
            raise StrategyError("模型快照维度或数值无效")

    def candidate_settings(self) -> tuple[MachineSetting, ...]:
        return tuple(
            MachineSetting(upper, lower, angle)
            for upper, lower, angle in product(
                self.upper_values, self.lower_values, self.angle_values
            )
        )

    def _raw_features(
        self, setting: MachineSetting, net_distance_m: float
    ) -> np.ndarray:
        base = [
            (setting.upper_rpm + setting.lower_rpm) / 2.0,
            setting.upper_rpm - setting.lower_rpm,
            setting.angle_deg,
        ]
        if not self.invariant:
            base.append(net_distance_m)
        return np.asarray(base, dtype=float)

    def features_for(
        self, settings: tuple[MachineSetting, ...], net_distance_m: float
    ) -> np.ndarray:
        return np.asarray(
            [self._raw_features(setting, net_distance_m) for setting in settings],
            dtype=float,
        )

    def domain_distances(self, raw_features: np.ndarray) -> np.ndarray:
        normalized = (raw_features - self.x_mean) / self.x_scale
        differences = normalized[:, None, :] - self.x_train[None, :, :]
        return np.sqrt(np.sum(differences**2, axis=2)).min(axis=1)

    def predict(self, raw_features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        normalized = (raw_features - self.x_mean) / self.x_scale
        differences = normalized[:, None, :] - self.x_train[None, :, :]
        distance = np.sqrt(np.sum(differences**2, axis=2))
        scaled = math.sqrt(3.0) * distance / self.length_scale
        cross_kernel = (1.0 + scaled) * np.exp(-scaled)
        mean_normalized = cross_kernel @ self.alpha
        solved = np.linalg.solve(self.cholesky, cross_kernel.T)
        latent_variance = np.maximum(0.0, 1.0 - np.sum(solved**2, axis=0))
        mean = mean_normalized * self.y_scale + self.y_mean
        variances = latent_variance[:, None] * (self.y_scale**2)
        return mean, variances

    def confidence(self, raw_feature: np.ndarray, distance: float) -> str:
        if tuple(np.round(raw_feature, 9)) in self._observed_feature_keys or distance <= 1e-4:
            return "observed"
        if distance <= self.nearest_distance_limit * 0.5:
            return "high"
        if distance <= self.nearest_distance_limit:
            return "medium"
        return "extrapolated"

    def training_summary(self) -> dict[str, Any]:
        return dict(self._training_summary)

    def prepared_context(
        self, net_distance_m: float, distance_limit: float
    ) -> tuple[tuple[MachineSetting, ...], np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        key = (round(net_distance_m, 9), round(distance_limit, 9))
        cached = self._context_cache.get(key)
        if cached is not None:
            self.last_context_cache_hit = True
            return cached
        self.last_context_cache_hit = False
        all_settings = self.candidate_settings()
        all_features = self.features_for(all_settings, net_distance_m)
        all_distances = self.domain_distances(all_features)
        in_domain = all_distances <= distance_limit + EPSILON
        settings = tuple(
            setting for setting, keep in zip(all_settings, in_domain) if keep
        )
        features = all_features[in_domain]
        distances = all_distances[in_domain]
        means, variances = self.predict(features) if len(settings) else (
            np.empty((0, 2)), np.empty((0, 2))
        )
        covariance = self.shot_covariance[None, :, :] + np.eye(2)[None, :, :] * variances[:, None, :]
        covariance = (covariance + np.swapaxes(covariance, 1, 2)) / 2.0
        covariance += np.eye(2)[None, :, :] * 1e-12
        factors = np.linalg.cholesky(covariance) if len(settings) else np.empty((0, 2, 2))
        prepared = (settings, features, distances, means, variances, factors)
        self._context_cache[key] = prepared
        return prepared


def _target_coefficients(z0: float, net_distance: float, landing: float, height: float) -> tuple[float, float]:
    denominator = net_distance * landing * (landing - net_distance)
    if abs(denominator) <= EPSILON:
        raise StrategyError("目标轨迹几何条件退化")
    delta = height - z0
    return (
        (delta * landing**2 + z0 * net_distance**2) / denominator,
        (-z0 * net_distance - landing * delta) / denominator,
    )


def _ray_rectangle_interval(
    origin_x: float, origin_y: float, direction_x: float, direction_y: float,
    x_min: float, x_max: float, y_min: float, y_max: float,
) -> tuple[float, float]:
    near, far = -math.inf, math.inf
    for origin, direction, minimum, maximum in (
        (origin_x, direction_x, x_min, x_max),
        (origin_y, direction_y, y_min, y_max),
    ):
        if abs(direction) <= EPSILON:
            if origin < minimum or origin > maximum:
                raise StrategyError("机器中心射线没有穿过落点区域")
            continue
        first = (minimum - origin) / direction
        second = (maximum - origin) / direction
        if first > second:
            first, second = second, first
        near = max(near, first)
        far = min(far, second)
    if far <= max(near, 0.0):
        raise StrategyError("机器中心射线没有穿过落点区域")
    return max(near, 0.0), far


def build_target_geometry(
    machine_x: float, machine_y: float, x_min: float, x_max: float,
    y_min: float, y_max: float, net_height_m: float, launcher_height_m: float,
    net_y: float,
) -> TargetGeometry:
    center_x = (x_min + x_max) / 2.0
    center_y = (y_min + y_max) / 2.0
    delta_x = center_x - machine_x
    delta_y = center_y - machine_y
    distance = math.hypot(delta_x, delta_y)
    if distance <= EPSILON:
        raise StrategyError("发球机位置不能与目标区域中心重合")
    direction_x, direction_y = delta_x / distance, delta_y / distance
    if abs(direction_y) <= EPSILON:
        raise StrategyError("机器朝向与球网平行，无法过网")
    net_distance = (net_y - machine_y) / direction_y
    if net_distance <= EPSILON:
        raise StrategyError("球网不在机器正前方")
    interval = _ray_rectangle_interval(
        machine_x, machine_y, direction_x, direction_y, x_min, x_max, y_min, y_max
    )
    landing_min = max(interval[0], net_distance + 1e-6)
    landing_max = interval[1]
    if landing_max <= landing_min:
        raise StrategyError("落点区域没有位于球网之后的部分")
    target_landing = (landing_min + landing_max) / 2.0
    target_a, target_b = _target_coefficients(
        launcher_height_m, net_distance, target_landing, net_height_m
    )
    if target_b >= 0:
        raise StrategyError("目标条件得到非下凹轨迹")
    return TargetGeometry(
        center_x, center_y, math.degrees(math.atan2(delta_y, delta_x)), net_distance,
        landing_min, landing_max, target_landing, target_a, target_b,
    )


def _safe_quantiles(values: np.ndarray) -> tuple[float, float, float]:
    valid = values[np.isfinite(values)]
    if len(valid) == 0:
        return math.nan, math.nan, math.nan
    result = np.quantile(valid, [0.05, 0.5, 0.95])
    return float(result[0]), float(result[1]), float(result[2])


def search_parameters(
    model: FrozenTrajectoryModel,
    geometry: TargetGeometry,
    *,
    launcher_height_m: float,
    physical_net_height_m: float,
    safety_margin_m: float,
    net_height_min_m: float,
    net_height_max_m: float,
    top_k: int,
    coarse_samples: int,
    shortlist_size: int,
    allow_extrapolation: bool = False,
    extrapolation_distance_multiplier: float = 2.0,
) -> tuple[CandidateResult, ...]:
    """Two-stage deterministic search matching the frozen strategy release."""
    if net_height_max_m <= net_height_min_m:
        raise StrategyError("过网高度最高值必须大于最低值")
    minimum_height = physical_net_height_m + safety_margin_m
    if net_height_min_m < minimum_height:
        raise StrategyError("目标过网高度低于安全余量")
    if not model.invariant and not allow_extrapolation:
        lower_context, upper_context = model.net_distance_range
        if not lower_context - 1e-9 <= geometry.net_distance <= upper_context + 1e-9:
            raise StrategyError("当前球网距离超出训练范围")

    distance_limit = model.nearest_distance_limit * (
        max(1.0, float(extrapolation_distance_multiplier))
        if allow_extrapolation else 1.0)
    settings, features, distances, means, variances, covariance_factors = model.prepared_context(
        geometry.net_distance, distance_limit
    )
    if not settings:
        return ()
    sample_total = len(model.standard_normal_samples)
    coarse_count = min(coarse_samples, sample_total)
    if coarse_count < 50:
        raise StrategyError("固定标准正态样本不足50组")
    landing_scale = max((geometry.landing_max - geometry.landing_min) / 2.0, 0.25)
    height_scale = max((net_height_max_m - net_height_min_m) / 2.0, 0.05)

    def target_errors(mean_values: np.ndarray) -> np.ndarray:
        parameter_a, parameter_b = mean_values[:, 0], mean_values[:, 1]
        discriminants = parameter_a**2 - 4.0 * parameter_b * launcher_height_m
        valid = (parameter_b < -EPSILON) & (discriminants >= 0)
        landing = np.full(len(mean_values), np.nan)
        landing[valid] = (
            -parameter_a[valid] - np.sqrt(discriminants[valid])
        ) / (2.0 * parameter_b[valid])
        valid &= landing > geometry.net_distance
        height = (
            launcher_height_m
            + parameter_a * geometry.net_distance
            + parameter_b * geometry.net_distance**2
        )
        landing_error = np.maximum(
            np.maximum(geometry.landing_min - landing, landing - geometry.landing_max), 0.0
        )
        height_error = np.maximum(
            np.maximum(net_height_min_m - height, height - net_height_max_m), 0.0
        )
        errors = (landing_error / landing_scale) ** 2 + (height_error / height_scale) ** 2
        errors[~valid] = math.inf
        return errors

    def batch_metrics(
        mean_values: np.ndarray, factors: np.ndarray, count: int
    ) -> tuple[np.ndarray, np.ndarray]:
        samples = mean_values[:, None, :] + np.einsum(
            "sk,njk->nsj", model.standard_normal_samples[:count], factors
        )
        parameter_a, parameter_b = samples[:, :, 0], samples[:, :, 1]
        discriminants = parameter_a**2 - 4.0 * parameter_b * launcher_height_m
        valid = (parameter_b < -EPSILON) & (discriminants >= 0)
        landing = np.full(parameter_a.shape, np.nan)
        landing[valid] = (
            -parameter_a[valid] - np.sqrt(discriminants[valid])
        ) / (2.0 * parameter_b[valid])
        valid &= landing > geometry.net_distance
        height = (
            launcher_height_m
            + parameter_a * geometry.net_distance
            + parameter_b * geometry.net_distance**2
        )
        success = (
            valid
            & (landing >= geometry.landing_min)
            & (landing <= geometry.landing_max)
            & (height >= net_height_min_m)
            & (height <= net_height_max_m)
            & (height >= minimum_height)
        )
        return np.mean(success, axis=1), np.count_nonzero(valid, axis=1)

    def detailed_metrics(index: int) -> tuple[float, int, tuple[float, float, float], tuple[float, float, float]]:
        samples = means[index] + model.standard_normal_samples @ covariance_factors[index].T
        parameter_a, parameter_b = samples[:, 0], samples[:, 1]
        discriminants = parameter_a**2 - 4.0 * parameter_b * launcher_height_m
        valid = (parameter_b < -EPSILON) & (discriminants >= 0)
        landing = np.full(sample_total, np.nan)
        landing[valid] = (
            -parameter_a[valid] - np.sqrt(discriminants[valid])
        ) / (2.0 * parameter_b[valid])
        valid &= landing > geometry.net_distance
        height = (
            launcher_height_m
            + parameter_a * geometry.net_distance
            + parameter_b * geometry.net_distance**2
        )
        success = (
            valid
            & (landing >= geometry.landing_min)
            & (landing <= geometry.landing_max)
            & (height >= net_height_min_m)
            & (height <= net_height_max_m)
            & (height >= minimum_height)
        )
        return (
            float(np.mean(success)),
            int(np.count_nonzero(valid)),
            _safe_quantiles(landing[valid]),
            _safe_quantiles(height[valid]),
        )

    errors = target_errors(means)
    total_rpm = np.asarray(
        [setting.upper_rpm + setting.lower_rpm for setting in settings], dtype=float
    )
    indices = np.arange(len(settings))
    coarse_probability, _ = batch_metrics(means, covariance_factors, coarse_count)
    coarse_order = np.lexsort((indices, total_rpm, errors, -coarse_probability))
    shortlist = coarse_order[:max(top_k, shortlist_size)]
    fine_probability, fine_valid = batch_metrics(
        means[shortlist], covariance_factors[shortlist], sample_total
    )
    valid_shortlist = shortlist[fine_valid > 0]
    if not len(valid_shortlist):
        return ()
    final_order = valid_shortlist[np.lexsort((
        valid_shortlist,
        total_rpm[valid_shortlist],
        errors[valid_shortlist],
        -fine_probability[fine_valid > 0],
    ))]

    selected: list[CandidateResult] = []
    for index in final_order[:top_k]:
        probability, valid_count, landing_q, height_q = detailed_metrics(int(index))
        if not valid_count:
            continue
        setting, feature, distance, mean_ab = (
            settings[index], features[index], distances[index], means[index]
        )
        selected.append(CandidateResult(
            upper_rpm=setting.upper_rpm,
            lower_rpm=setting.lower_rpm,
            vertical_servo_angle_deg=setting.angle_deg,
            predicted_a=float(mean_ab[0]),
            predicted_b=float(mean_ab[1]),
            landing_p05_m=landing_q[0], landing_median_m=landing_q[1], landing_p95_m=landing_q[2],
            net_height_p05_m=height_q[0], net_height_median_m=height_q[1], net_height_p95_m=height_q[2],
            success_probability=probability,
            confidence=model.confidence(feature, distance),
            nearest_training_distance=distance,
        ))
    return tuple(selected)
