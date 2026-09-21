from pathlib import Path
from types import SimpleNamespace

from tennis_serve_launcher_planning.model_service import ModelService


ROOT = Path(__file__).resolve().parents[1]


def _target(center_x_m):
    return SimpleNamespace(
        center_x_m=center_x_m,
        center_y_m=16.77,
        width_m=0.5,
        depth_m=0.5,
        net_height_min_m=1.1,
        net_height_max_m=2.0,
    )


def _model():
    return ModelService(
        str(ROOT / "data" / "fire_ball" / "model_snapshot.json"),
        str(ROOT / "data" / "fire_ball" / "manifest.json"),
        machine_boundary_tolerance_m=1.0,
    )


def test_baseline_robot_can_plan_lateral_targets_with_controlled_extrapolation():
    model = _model()
    robot = SimpleNamespace(x_m=5.485, y_m=0.0, yaw_rad=0.0)
    for target_x in (1.0, 3.0, 5.485, 8.0, 10.0):
        result = model.plan(f"baseline-{target_x}", "step", _target(target_x), robot)
        assert result["upper_target_rpm"] > 0
        assert result["lower_target_rpm"] > 0


def test_machine_position_keeps_real_geometry_with_one_metre_boundary_margin():
    model = _model()
    for robot_x, robot_y in ((-1.0, 0.0), (11.97, 0.0), (5.485, -1.0), (5.485, 7.4)):
        robot = SimpleNamespace(x_m=robot_x, y_m=robot_y, yaw_rad=0.0)
        result = model.plan(
            f"outside-{robot_x}-{robot_y}", "step", _target(5.485), robot)
        assert result["robot_x_m"] == robot_x
        assert result["robot_y_m"] == robot_y
