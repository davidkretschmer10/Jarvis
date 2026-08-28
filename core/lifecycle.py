# -*- coding: utf-8 -*-
from __future__ import annotations

from enum import Enum
import threading
import time
from typing import Any, Dict, List, Optional, Set
import uuid
import weakref


class RequestStatus(str, Enum):
    CREATED = "CREATED"
    ROUTING = "ROUTING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    WAITING_FOR_USER = "WAITING_FOR_USER"


class InvalidStateTransitionError(Exception):
    """Raised when an illegal transition is requested on a RequestContext."""

    def __init__(self, from_status: RequestStatus, to_status: RequestStatus, request_id: str = ""):
        self.from_status = from_status
        self.to_status = to_status
        self.request_id = request_id
        super().__init__(
            f"Invalid state transition from '{from_status.value}' to '{to_status.value}' for request '{request_id}'."
        )


VALID_TRANSITIONS: Dict[RequestStatus, Set[RequestStatus]] = {
    RequestStatus.CREATED: {
        RequestStatus.ROUTING,
        RequestStatus.PLANNING,
        RequestStatus.EXECUTING,
        RequestStatus.COMPLETED,
        RequestStatus.CANCELLED,
        RequestStatus.FAILED,
    },
    RequestStatus.ROUTING: {
        RequestStatus.PLANNING,
        RequestStatus.EXECUTING,
        RequestStatus.WAITING_FOR_USER,
        RequestStatus.COMPLETED,
        RequestStatus.FAILED,
        RequestStatus.CANCELLED,
    },
    RequestStatus.PLANNING: {
        RequestStatus.EXECUTING,
        RequestStatus.COMPLETED,
        RequestStatus.FAILED,
        RequestStatus.CANCELLED,
    },
    RequestStatus.EXECUTING: {
        RequestStatus.VERIFYING,
        RequestStatus.WAITING_FOR_USER,
        RequestStatus.COMPLETED,
        RequestStatus.FAILED,
        RequestStatus.CANCELLED,
    },
    RequestStatus.VERIFYING: {
        RequestStatus.COMPLETED,
        RequestStatus.FAILED,
        RequestStatus.CANCELLED,
    },
    RequestStatus.WAITING_FOR_USER: {
        RequestStatus.EXECUTING,
        RequestStatus.COMPLETED,
        RequestStatus.CANCELLED,
        RequestStatus.FAILED,
    },
    RequestStatus.COMPLETED: set(),
    RequestStatus.FAILED: set(),
    RequestStatus.CANCELLED: set(),
}


class RequestContext:
    """
    Centralized, thread-safe context and state machine representing a single
    user request lifecycle throughout Jarvis.
    """

    _instances: weakref.WeakSet[RequestContext] = weakref.WeakSet()

    def __init__(
        self,
        request_id: Optional[str] = None,
        goal: str = "",
        source: str = "unknown",
    ) -> None:
        self._lock = threading.RLock()
        self.request_id: str = request_id or uuid.uuid4().hex[:8]
        self.goal: str = goal
        self.source: str = source
        self.status: RequestStatus = RequestStatus.CREATED
        self.created_at: float = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.current_step: int = 0
        self.total_steps: int = 0
        self.cancellation_requested: bool = False
        self.waiting_for_user: bool = False
        self.result: Optional[Any] = None
        self.error: Optional[str] = None

        RequestContext._instances.add(self)

    @classmethod
    def get_active_count(cls) -> int:
        return len(cls._instances)

    # --------------------------------------------------------------------------
    # Backward Compatibility Properties
    # --------------------------------------------------------------------------
    @property
    def completed(self) -> bool:
        with self._lock:
            return self.status == RequestStatus.COMPLETED

    @completed.setter
    def completed(self, value: bool) -> None:
        with self._lock:
            if value and self.status != RequestStatus.COMPLETED:
                self.transition_to(RequestStatus.COMPLETED)
            elif not value and self.status == RequestStatus.COMPLETED:
                self.status = RequestStatus.CREATED

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self.status == RequestStatus.CANCELLED or self.cancellation_requested

    @cancelled.setter
    def cancelled(self, value: bool) -> None:
        with self._lock:
            if value and self.status != RequestStatus.CANCELLED:
                self.cancellation_requested = True
                self.transition_to(RequestStatus.CANCELLED)
            elif not value and self.status == RequestStatus.CANCELLED:
                self.cancellation_requested = False
                self.status = RequestStatus.CREATED

    @property
    def failed(self) -> bool:
        with self._lock:
            return self.status == RequestStatus.FAILED

    @failed.setter
    def failed(self, value: bool) -> None:
        with self._lock:
            if value and self.status != RequestStatus.FAILED:
                self.transition_to(RequestStatus.FAILED)
            elif not value and self.status == RequestStatus.FAILED:
                self.status = RequestStatus.CREATED

    @property
    def start_time(self) -> float:
        return self.created_at

    @start_time.setter
    def start_time(self, value: float) -> None:
        self.created_at = value

    @property
    def duration(self) -> float:
        with self._lock:
            end = self.completed_at or time.time()
            return max(0.0, end - self.created_at)

    @property
    def is_terminal(self) -> bool:
        with self._lock:
            return self.status in (
                RequestStatus.COMPLETED,
                RequestStatus.FAILED,
                RequestStatus.CANCELLED,
            )

    # --------------------------------------------------------------------------
    # State Transition
    # --------------------------------------------------------------------------
    def transition_to(
        self,
        target_status: RequestStatus,
        error: Optional[str] = None,
        result: Optional[Any] = None,
        event_bus: Any = None,
        **extra: Any,
    ) -> None:
        with self._lock:
            if self.status == target_status:
                if error is not None:
                    self.error = error
                if result is not None:
                    self.result = result
                return

            allowed = VALID_TRANSITIONS.get(self.status, set())
            if target_status not in allowed:
                raise InvalidStateTransitionError(
                    from_status=self.status,
                    to_status=target_status,
                    request_id=self.request_id,
                )

            prev_status = self.status
            self.status = target_status

            if target_status in (RequestStatus.ROUTING, RequestStatus.EXECUTING) and self.started_at is None:
                self.started_at = time.time()

            if target_status == RequestStatus.WAITING_FOR_USER:
                self.waiting_for_user = True
            elif prev_status == RequestStatus.WAITING_FOR_USER and target_status == RequestStatus.EXECUTING:
                self.waiting_for_user = False

            if error is not None:
                self.error = error
            if result is not None:
                self.result = result

            if target_status in (RequestStatus.COMPLETED, RequestStatus.FAILED, RequestStatus.CANCELLED):
                self.completed_at = time.time()
                if target_status == RequestStatus.CANCELLED:
                    self.cancellation_requested = True

            # Emit corresponding lifecycle event
            self._emit_lifecycle_event(prev_status, target_status, event_bus, **extra)

    def cancel(self, reason: Optional[str] = None, event_bus: Any = None) -> None:
        with self._lock:
            self.cancellation_requested = True
            if not self.is_terminal:
                self.transition_to(
                    RequestStatus.CANCELLED,
                    error=reason or "Request was cancelled by user",
                    event_bus=event_bus,
                )

    def _emit_lifecycle_event(
        self,
        prev_status: RequestStatus,
        new_status: RequestStatus,
        event_bus: Any = None,
        **extra: Any,
    ) -> None:
        if event_bus is None:
            return

        payload = {
            "request_id": self.request_id,
            "goal": self.goal,
            "source": self.source,
            "prev_status": prev_status.value,
            "status": new_status.value,
            "timestamp": time.time(),
            "duration": self.duration,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
        }
        if self.error:
            payload["error"] = self.error
        if self.result is not None:
            payload["result"] = self.result
        payload.update(extra)

        event_map = {
            RequestStatus.ROUTING: "routing_started",
            RequestStatus.PLANNING: "planning_started",
            RequestStatus.EXECUTING: "request_resumed" if prev_status == RequestStatus.WAITING_FOR_USER else "execution_started",
            RequestStatus.VERIFYING: "verification_started",
            RequestStatus.WAITING_FOR_USER: "request_waiting_for_user",
            RequestStatus.COMPLETED: "request_completed",
            RequestStatus.FAILED: "request_failed",
            RequestStatus.CANCELLED: "request_cancelled",
        }

        specific_event = event_map.get(new_status)
        if specific_event:
            try:
                event_bus.emit(specific_event, payload)
            except Exception as e:
                print(f"[LIFECYCLE] Error emitting {specific_event}: {e}")

        try:
            event_bus.emit("request_status_changed", payload)
        except Exception as e:
            print(f"[LIFECYCLE] Error emitting request_status_changed: {e}")

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "request_id": self.request_id,
                "goal": self.goal,
                "source": self.source,
                "status": self.status.value,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "duration": self.duration,
                "current_step": self.current_step,
                "total_steps": self.total_steps,
                "cancellation_requested": self.cancellation_requested,
                "waiting_for_user": self.waiting_for_user,
                "error": self.error,
            }


# ------------------------------------------------------------------------------
# Thread-local & Context Management Functions
# ------------------------------------------------------------------------------
_thread_local = threading.local()


def get_current_request() -> RequestContext:
    if not hasattr(_thread_local, "context") or _thread_local.context is None:
        _thread_local.context = RequestContext()
    return _thread_local.context


def get_current_request_or_none() -> Optional[RequestContext]:
    if hasattr(_thread_local, "context"):
        return _thread_local.context
    return None


def set_current_request(ctx: RequestContext) -> None:
    _thread_local.context = ctx


def reset_current_request(goal: str = "", source: str = "unknown") -> RequestContext:
    old_ctx = get_current_request_or_none()
    if old_ctx and not old_ctx.is_terminal:
        print(
            f"[REQUEST]\nPrevious request still active\n\nRequest ID:\n{old_ctx.request_id}\n\nAction:\ncancel previous request\n"
        )
        old_ctx.cancel(reason="New request superseded previous one")

    new_ctx = RequestContext(goal=goal, source=source)
    _thread_local.context = new_ctx
    print(f"[REQUEST]\nNew request started\n\nRequest ID:\n{new_ctx.request_id}\n")
    return new_ctx


def complete_current_request(result: Optional[Any] = None, event_bus: Any = None) -> None:
    req = get_current_request()
    if not req.is_terminal:
        req.transition_to(RequestStatus.COMPLETED, result=result, event_bus=event_bus)
        duration = req.duration
        print(f"[REQUEST]\nCompleted\n\nRequest ID:\n{req.request_id}\n\nDuration:\n{duration:.2f}s\n")
        try:
            from core.intents.fast_command_router import update_request_stat

            update_request_stat("completed")
        except Exception:
            pass


def cancel_current_request(reason: Optional[str] = None, event_bus: Any = None) -> None:
    req = get_current_request()
    if not req.is_terminal:
        req.cancel(reason=reason, event_bus=event_bus)
        duration = req.duration
        print(f"[REQUEST]\nCancelled\n\nRequest ID:\n{req.request_id}\n\nDuration:\n{duration:.2f}s\n")
        try:
            from core.intents.fast_command_router import update_request_stat

            update_request_stat("cancelled")
        except Exception:
            pass


def fail_current_request(error: Optional[str] = None, event_bus: Any = None) -> None:
    req = get_current_request()
    if not req.is_terminal:
        req.transition_to(RequestStatus.FAILED, error=error, event_bus=event_bus)
        duration = req.duration
        print(f"[REQUEST]\nFailed\n\nRequest ID:\n{req.request_id}\n\nDuration:\n{duration:.2f}s\n")
        try:
            from core.intents.fast_command_router import update_request_stat

            update_request_stat("failed")
        except Exception:
            pass


def check_request_context_block() -> bool:
    req = get_current_request()
    if req.is_terminal:
        reason = req.status.value.lower()
        print(
            f"[ENGINE]\nAI generation skipped\n\nReason:\nrequest already {reason}\n\nRequest state:\ncompleted={req.completed}\ncancelled={req.cancelled}\nfailed={req.failed}\n"
        )
        return True
    return False
