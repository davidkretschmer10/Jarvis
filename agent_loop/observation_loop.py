from __future__ import annotations

import logging
import asyncio
import threading
import time

from agent_loop.action_executor import ActionExecutor
from agent_loop.retry_manager import FailureType, RetryManager
from agent_loop.state_tracker import StateTracker, TaskState
from agent_loop.step_result import ActionResult, ObservationResult, StepResult
from agent_loop.task_context import ExpectedState, TaskContext
from vision.ui_detector import UIDetector


LOGGER = logging.getLogger(__name__)


class ObservationLoop:
    def __init__(
        self,
        action_executor: ActionExecutor | None = None,
        ui_detector: UIDetector | None = None,
        state_tracker: StateTracker | None = None,
        retry_manager: RetryManager | None = None,
    ) -> None:
        self.action_executor = action_executor or ActionExecutor()
        self.ui_detector = ui_detector or UIDetector()
        self.state_tracker = state_tracker or StateTracker()
        self.retry_manager = retry_manager or RetryManager()
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        LOGGER.info("Observation loop cancellation requested")
        self._cancel_event.set()

    def reset_cancellation(self) -> None:
        self._cancel_event.clear()

    def run(self, context: TaskContext, cancel_event: threading.Event | None = None) -> TaskState:
        self.reset_cancellation()
        external_cancel = cancel_event
        state = self.state_tracker.start(context)
        started_at = time.monotonic()
        LOGGER.info("Observation loop started: %s", context.goal)

        try:
            for action_index, action in enumerate(context.actions[: context.max_steps]):
                if self._is_cancelled(external_cancel):
                    self.state_tracker.set_status("cancelled")
                    LOGGER.info("Observation loop cancelled before step %s", action_index)
                    break
                if self.retry_manager.has_timed_out(started_at, context.timeout_seconds):
                    self.state_tracker.set_status("timeout")
                    LOGGER.warning("Observation loop timed out before step %s", action_index)
                    break

                while True:
                    retry_count = self.state_tracker._require_state().retry_count
                    LOGGER.info("Step %s action=%s retry=%s", action_index, action.type, retry_count)
                    action_result = self.action_executor.execute(action)

                    if context.settle_seconds:
                        time.sleep(context.settle_seconds)

                    observation_result = self._observe(context)
                    evaluation_passed = self._evaluate(context.expected_state, observation_result)
                    failure = self.retry_manager.classify(
                        action_result=action_result,
                        observation_result=observation_result,
                        evaluation_passed=evaluation_passed,
                        timed_out=self.retry_manager.has_timed_out(started_at, context.timeout_seconds),
                        cancelled=self._is_cancelled(external_cancel),
                    )

                    step_result = StepResult(
                        step_index=action_index,
                        action_result=action_result,
                        observation_result=observation_result,
                        evaluation_passed=evaluation_passed,
                        message=failure.value,
                        retry_count=retry_count,
                    )
                    self.state_tracker.record_step(step_result, min(len(context.actions), context.max_steps))

                    if failure == FailureType.NONE:
                        self.state_tracker.reset_retry()
                        if evaluation_passed:
                            self.state_tracker.set_status("completed")
                            LOGGER.info("Observation loop completed at step %s", action_index)
                            return self.state_tracker._require_state()
                        break

                    if not self.retry_manager.should_retry(failure, retry_count):
                        self.state_tracker.set_status(failure.value)
                        LOGGER.warning("Observation loop stopped: %s", failure.value)
                        return self.state_tracker._require_state()

                    next_retry = self.state_tracker.increment_retry()
                    LOGGER.info("Retrying step %s after failure=%s retry=%s", action_index, failure.value, next_retry)
                    if self._sleep_before_retry(retry_count, external_cancel):
                        self.state_tracker.set_status("cancelled")
                        return self.state_tracker._require_state()

            if state.status == "running":
                self.state_tracker.set_status("completed" if self._last_evaluation_passed() else "incomplete")
        finally:
            LOGGER.info("Observation loop finished with status=%s", self.state_tracker._require_state().status)

        return self.state_tracker._require_state()

    async def run_async(self, context: TaskContext, cancel_event: threading.Event | None = None) -> TaskState:
        return await asyncio.to_thread(self.run, context, cancel_event)

    def _observe(self, context: TaskContext) -> ObservationResult:
        started = time.perf_counter()
        try:
            ui = self.ui_detector.detect_screen(extra_instruction=context.observation_instruction)
            return ObservationResult(
                ok=True,
                ui=ui,
                screenshot_path=ui.image_path,
                elapsed_seconds=time.perf_counter() - started,
            )
        except Exception as exc:
            LOGGER.error("Screen observation failed: %s", exc)
            return ObservationResult(
                ok=False,
                error=str(exc),
                elapsed_seconds=time.perf_counter() - started,
            )

    def _evaluate(self, expected: ExpectedState, observation: ObservationResult) -> bool:
        if not observation.ok or observation.ui is None:
            return False

        ui = observation.ui
        if expected.screen_type and ui.screen_type.lower() != expected.screen_type.lower():
            return False
        if expected.min_elements and len(ui.elements) < expected.min_elements:
            return False

        all_text = " ".join(element.text for element in ui.elements).lower()
        for text in expected.required_text:
            if text.lower() not in all_text:
                return False

        available_types = {element.type for element in ui.elements}
        for element_type in expected.required_element_types:
            if element_type not in available_types:
                return False

        element_texts = [element.text.lower() for element in ui.elements]
        for expected_text in expected.required_element_texts:
            needle = expected_text.lower()
            if not any(needle in text for text in element_texts):
                return False

        return True

    def _last_evaluation_passed(self) -> bool:
        state = self.state_tracker._require_state()
        return bool(state.history and state.history[-1].evaluation_passed)

    def _is_cancelled(self, external_cancel: threading.Event | None) -> bool:
        return self._cancel_event.is_set() or bool(external_cancel and external_cancel.is_set())

    def _sleep_before_retry(self, retry_count: int, external_cancel: threading.Event | None) -> bool:
        delay = self.retry_manager.delay_seconds(retry_count)
        deadline = time.monotonic() + delay
        while time.monotonic() < deadline:
            if self._is_cancelled(external_cancel):
                return True
            time.sleep(min(0.1, deadline - time.monotonic()))
        return self._is_cancelled(external_cancel)
