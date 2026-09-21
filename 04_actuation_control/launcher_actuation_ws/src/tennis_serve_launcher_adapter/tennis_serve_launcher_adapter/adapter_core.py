"""Pure mapping and feed-result rules for the launcher hardware adapter."""

from __future__ import annotations

from dataclasses import dataclass


def map_targets(
    upper_rpm: int,
    lower_rpm: int,
    upper_motor: int,
    motor1_sign: int,
    motor2_sign: int,
) -> tuple[int, int]:
    if upper_motor not in (1, 2):
        raise ValueError("upper_motor must be 1 or 2")
    if motor1_sign not in (-1, 1) or motor2_sign not in (-1, 1):
        raise ValueError("motor signs must be -1 or 1")
    if upper_rpm < 0 or lower_rpm < 0:
        raise ValueError("strategy RPM values must be non-negative")
    motor1 = upper_rpm if upper_motor == 1 else lower_rpm
    motor2 = lower_rpm if upper_motor == 1 else upper_rpm
    return motor1_sign * motor1, motor2_sign * motor2


def map_feedback(
    motor1_rpm: float,
    motor2_rpm: float,
    upper_motor: int,
) -> tuple[int, int]:
    if upper_motor not in (1, 2):
        raise ValueError("upper_motor must be 1 or 2")
    motor1 = round(abs(motor1_rpm))
    motor2 = round(abs(motor2_rpm))
    return (motor1, motor2) if upper_motor == 1 else (motor2, motor1)


def feedback_directions_match(
    motor1_rpm: float,
    motor2_rpm: float,
    motor1_target_rpm: int,
    motor2_target_rpm: int,
    minimum_check_rpm: float = 100.0,
) -> bool:
    """Reject a reversed wheel once both target and feedback are measurable."""
    for measured, target in (
        (motor1_rpm, motor1_target_rpm),
        (motor2_rpm, motor2_target_rpm),
    ):
        if abs(target) < minimum_check_rpm or abs(measured) < minimum_check_rpm:
            continue
        if measured * target <= 0:
            return False
    return True


@dataclass
class FeedResultTracker:
    timeout_s: float
    command_id: str = ""
    baseline_count: int = 0
    started_s: float = 0.0
    saw_progress: bool = False
    result_valid: bool = False
    succeeded: bool = False
    detail: str = "IDLE"

    def start(self, command_id: str, completed_count: int, now_s: float) -> None:
        self.command_id = command_id
        self.baseline_count = completed_count
        self.started_s = now_s
        self.saw_progress = False
        self.result_valid = False
        self.succeeded = False
        self.detail = "FEED_REQUESTED"

    def update(
        self,
        completed_count: int,
        state: int,
        result: int,
        error: str,
        now_s: float,
    ) -> None:
        if not self.command_id or self.result_valid:
            return
        if completed_count > self.baseline_count:
            self.result_valid = True
            self.succeeded = True
            self.detail = "FEED_COMPLETE"
            return
        if error:
            self.result_valid = True
            self.detail = "FEED_ADAPTER_ERROR:" + error
            return
        if state in (1, 3, 4, 11) or result in (2, 4, 5, 15):
            self.saw_progress = True
            self.detail = "FEED_IN_PROGRESS"
        if self.saw_progress and (
            state in (7, 10) or result in (8, 9, 10, 11, 13, 14)
        ):
            self.result_valid = True
            self.detail = f"FEED_FAILED_STATE_{state}_RESULT_{result}"
            return
        if now_s - self.started_s >= self.timeout_s:
            self.result_valid = True
            self.detail = f"FEED_TIMEOUT_STATE_{state}_RESULT_{result}"

    def tick(self, now_s: float) -> None:
        """Advance the deadline even if feeder-state messages stop arriving."""
        if (self.command_id and not self.result_valid
                and now_s - self.started_s >= self.timeout_s):
            self.result_valid = True
            self.succeeded = False
            self.detail = "FEED_TIMEOUT_NO_RESULT"
