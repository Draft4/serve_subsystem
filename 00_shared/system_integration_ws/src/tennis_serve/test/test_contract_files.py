from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
INTERFACES = ROOT / "00_shared/interfaces_ws/src/tennis_serve_interfaces"
INTEGRATION = ROOT / "00_shared/system_integration_ws/src/tennis_serve"
SUPERVISOR = ROOT / "04_actuation_control/actuation_supervisor_ws/src/tennis_serve_supervisor"
MISSION = ROOT / "01_mission_decision/mission_ws/src/tennis_serve_mission"
OPERATOR = ROOT / "01_mission_decision/operator_ws/src/tennis_serve_operator"


def test_no_can_or_virtual_f407_production_module():
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in ROOT.glob("**/src/*/*.py")
    )
    assert "SimulatedF407" not in sources
    assert "TENNIS_TRAINING_BACKEND" not in sources
    assert "python-can" not in sources


def test_feed_contract_has_unique_command_id_and_no_bool_pulse():
    interface_root = INTERFACES
    feed = (interface_root / "msg" / "FeedCommand.msg").read_text(encoding="utf-8")
    assert "string command_id" in feed
    assert "uint8 action" in feed
    assert "builtin_interfaces/Time valid_until" in feed
    assert "std_msgs/Bool" not in feed


def test_relaxed_thresholds_are_configuration():
    config = (SUPERVISOR / "config" / "supervisor.yaml").read_text(encoding="utf-8")
    for expected in (
        "yaw_tolerance_deg: 5.0", "linear_speed_limit_mps: 0.20",
        "rpm_tolerance_ratio: 0.15",
        "stable_hold_s: 0.20", "feed_dwell_s: 1.0",
        "feed_confirmation_mode: feedback", "feed_confirmation_timeout_s: 8.5",
        "launcher_hold_lease_s: 2.5", "position_tolerance_m: 0.50",
    ):
        assert expected in config


def test_launcher_hold_service_is_generated_with_acknowledged_contract():
    interface_root = INTERFACES
    service = (interface_root / "srv" / "SetLauncherHold.srv").read_text(encoding="utf-8")
    for expected in (
        "string job_id", "string command_id", "bool enabled", "string reason",
        "bool accepted", "string code", "string message",
    ):
        assert expected in service
    cmake = (interface_root / "CMakeLists.txt").read_text(encoding="utf-8")
    assert '"srv/SetLauncherHold.srv"' in cmake


def test_emergency_stop_has_an_acknowledged_reset_contract():
    interface_root = INTERFACES
    service = (interface_root / "srv" / "ResetEmergencyStop.srv").read_text(
        encoding="utf-8")
    assert "string command_id" in service
    assert "bool accepted" in service
    assert '"srv/ResetEmergencyStop.srv"' in (
        interface_root / "CMakeLists.txt").read_text(encoding="utf-8")


def test_controller_holds_successful_shots_and_stops_failed_shots():
    controller = (SUPERVISOR / "tennis_serve_supervisor" / "controller_node.py").read_text(encoding="utf-8")
    assert "self.create_timer(0.05, self._refresh_launcher_setpoint" in controller
    assert "if not completed_successfully:" in controller
    assert "self._publish_launcher_stop(goal.job_id, goal.shot_id" in controller
    assert "self.feed_pub.publish(command)" in controller


def test_job_manager_renews_only_running_jobs_and_stops_terminal_jobs():
    manager = (MISSION / "tennis_serve_mission" / "job_manager_node.py").read_text(encoding="utf-8")
    assert 'self._job["state"] != "RUNNING"' in manager
    assert 'goal.job_id, True, "SHOT_START"' in manager
    assert manager.index('goal.job_id, True, "SHOT_START"') < manager.index(
        "self._shot_client.send_goal_async(goal")
    for reason in (
        "JOB_CANCELLED", "JOB_COMPLETED", "HEARTBEAT_TIMEOUT", "EXECUTION_ERROR",
    ):
        assert reason in manager
    assert "plan_request.request_id" in manager
    assert "max_pre_feed_retries" in manager
    assert "REST_WHEELS_STOPPED" in manager


def test_controller_logs_each_action_goal_rejection_reason():
    controller = (SUPERVISOR / "tennis_serve_supervisor" / "controller_node.py").read_text(encoding="utf-8")
    for code in (
        "GOAL_REJECTED_EMERGENCY_STOP", "GOAL_REJECTED_ACTIVE_GOAL",
        "GOAL_REJECTED_HOLD_DISABLED", "GOAL_REJECTED_HOLD_OWNER",
        "GOAL_REJECTED_HOLD_EXPIRED",
    ):
        assert code in controller


def test_feedback_mode_fails_closed_when_feed_is_not_confirmed():
    controller = (SUPERVISOR / "tennis_serve_supervisor" / "controller_node.py").read_text(encoding="utf-8")
    assert 'result.code = "FEED_CONFIRMATION_TIMEOUT"' in controller
    assert 'if self.feed_mode == "feedback" and not confirmed:' in controller


def test_main_launch_does_not_duplicate_systemd_launcher_adapter():
    launch = (INTEGRATION / "launch" / "tennis_serve.launch.py").read_text(encoding="utf-8")
    assert 'serve_launcher_adapter_node' not in launch


def test_start_preflight_requires_fresh_valid_rpm_feedback():
    manager = (MISSION / "tennis_serve_mission" / "job_manager_node.py").read_text(encoding="utf-8")
    assert 'return False, "LAUNCHER_NOT_READY", detail' in manager
    assert "and self._launcher.rpm_valid" in manager
    assert "pitch_tolerance_deg" not in manager


def test_http_execution_allowed_requires_rpm_validity():
    bridge = (OPERATOR / "tennis_serve_operator" / "bridge_node.py").read_text(encoding="utf-8")
    assert "launcher_online and launcher.rpm_valid" in bridge


def test_http_status_bridges_the_real_launcher_arm_state():
    bridge = (OPERATOR / "tennis_serve_operator" / "bridge_node.py").read_text(encoding="utf-8")
    assert "from tennisbot_launcher.msg import LauncherWheelState" in bridge
    assert '"backend_armed": backend_armed' in bridge
