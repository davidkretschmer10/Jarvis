from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time

from agent_loop.step_result import ActionResult, ObservationResult


class FailureType(str, Enum):
    NONE = "none"
    ACTION_FAILED = "action_failed"
    OBSERVATION_FAILED = "observation_failed"
    EVALUATION_FAILED = "evaluation_failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 5.0
    backoff_factor: float = 2.0


class RetryManager:
    def __init__(self, policy: RetryPolicy | None = None) -> None:
        self.policy = policy or RetryPolicy()

    def classify(
        self,
        action_result: ActionResult | None = None,
        observation_result: ObservationResult | None = None,
        evaluation_passed: bool | None = None,
        timed_out: bool = False,
        cancelled: bool = False,
    ) -> FailureType:
        if cancelled:
            return FailureType.CANCELLED
        if timed_out:
            return FailureType.TIMEOUT
        if action_result is not None and not action_result.ok:
            return FailureType.ACTION_FAILED
        if observation_result is not None and not observation_result.ok:
            return FailureType.OBSERVATION_FAILED
        if evaluation_passed is False:
            return FailureType.EVALUATION_FAILED
        return FailureType.NONE

    def should_retry(self, failure_type: FailureType, retry_count: int) -> bool:
        if failure_type in {FailureType.NONE, FailureType.CANCELLED, FailureType.TIMEOUT}:
            return False
        return retry_count < self.policy.max_retries

    def delay_seconds(self, retry_count: int) -> float:
        delay = self.policy.base_delay_seconds * (self.policy.backoff_factor ** max(0, retry_count))
        return min(self.policy.max_delay_seconds, delay)

    def sleep_before_retry(self, retry_count: int) -> None:
        time.sleep(self.delay_seconds(retry_count))

    def has_timed_out(self, started_at: float, timeout_seconds: float) -> bool:
        return (time.monotonic() - started_at) >= timeout_seconds
