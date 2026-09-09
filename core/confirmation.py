"""Structured Confirmation Engine for Jarvis.

Replaces ad-hoc boolean flags with cryptographically/uniquely identified,
time-limited, and context-bound confirmation requests.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from core.security_policy import ActionRisk, ToolCapability


class ConfirmationStatus(str, Enum):
    """Lifecycle states of a confirmation request."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"

    def __str__(self) -> str:
        return self.value


@dataclass
class ConfirmationRequest:
    """A strongly-typed, time-limited confirmation token bound to a specific step."""
    request_id: str
    step_id: int
    tool: str
    capability: ToolCapability
    risk: ActionRisk
    resource: Optional[str]
    summary: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default=0.0)
    status: ConfirmationStatus = ConfirmationStatus.PENDING

    def __post_init__(self):
        if self.expires_at <= 0.0:
            # Default TTL: 5 minutes (300 seconds)
            self.expires_at = self.created_at + 300.0

    @property
    def is_expired(self) -> bool:
        if self.status == ConfirmationStatus.EXPIRED:
            return True
        if time.time() >= self.expires_at:
            self.status = ConfirmationStatus.EXPIRED
            return True
        return False

    @property
    def is_valid_pending(self) -> bool:
        return self.status == ConfirmationStatus.PENDING and not self.is_expired

    @property
    def is_approved(self) -> bool:
        return self.status == ConfirmationStatus.APPROVED and not self.is_expired

    def approve(self) -> bool:
        if self.is_expired:
            self.status = ConfirmationStatus.EXPIRED
            return False
        if self.status != ConfirmationStatus.PENDING:
            return False
        self.status = ConfirmationStatus.APPROVED
        return True

    def deny(self) -> bool:
        if self.status == ConfirmationStatus.PENDING:
            self.status = ConfirmationStatus.DENIED
            return True
        return False

    def build_user_prompt(self) -> str:
        """Construct a user-friendly and specific confirmation message."""
        resource_text = f" Cíl: {self.resource}\n" if self.resource else ""
        return (
            f"Jarvis vyžaduje potvrzení pro následující akci:\n"
            f" Nástroj: {self.tool} ({self.capability.value})\n"
            f"{resource_text}"
            f" Úroveň rizika: {self.risk.name}\n"
            f" Detail: {self.summary}\n"
            f"Tato akce může být nevratná. Přejete si akci provést? [Ano / Ne]"
        )


class ConfirmationManager:
    """Thread-safe manager for tracking pending and resolved confirmations."""

    def __init__(self, default_ttl_seconds: float = 300.0) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self._lock = threading.RLock()
        # Key: (request_id, step_id, tool) -> ConfirmationRequest
        self._confirmations: Dict[Tuple[str, int, str], ConfirmationRequest] = {}

    def create_confirmation(
        self,
        request_id: str,
        step_id: int,
        tool: str,
        capability: ToolCapability,
        risk: ActionRisk,
        resource: Optional[str],
        summary: str,
        ttl_seconds: Optional[float] = None,
    ) -> ConfirmationRequest:
        """Create and register a new pending confirmation request."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        now = time.time()
        conf = ConfirmationRequest(
            request_id=request_id,
            step_id=step_id,
            tool=tool,
            capability=capability,
            risk=risk,
            resource=resource,
            summary=summary,
            created_at=now,
            expires_at=now + ttl,
            status=ConfirmationStatus.PENDING,
        )
        with self._lock:
            self._confirmations[(request_id, step_id, tool)] = conf
        return conf

    def get_pending(self, request_id: str, step_id: Optional[int] = None) -> List[ConfirmationRequest]:
        """Retrieve all currently valid pending confirmations for a request."""
        with self._lock:
            results: List[ConfirmationRequest] = []
            for (req_id, s_id, _), conf in self._confirmations.items():
                if req_id == request_id:
                    if step_id is not None and s_id != step_id:
                        continue
                    if conf.is_valid_pending:
                        results.append(conf)
                    elif conf.is_expired:
                        conf.status = ConfirmationStatus.EXPIRED
            return results

    def get_confirmation(self, request_id: str, step_id: int, tool: str) -> Optional[ConfirmationRequest]:
        """Look up a confirmation by exact identity."""
        with self._lock:
            conf = self._confirmations.get((request_id, step_id, tool))
            if conf and conf.is_expired:
                conf.status = ConfirmationStatus.EXPIRED
            return conf

    def approve(self, request_id: str, step_id: int, tool: str) -> bool:
        """Approve an exact confirmation. Fails if expired or mismatched."""
        with self._lock:
            conf = self.get_confirmation(request_id, step_id, tool)
            if not conf:
                return False
            return conf.approve()

    def deny(self, request_id: str, step_id: int, tool: str) -> bool:
        """Deny an exact confirmation."""
        with self._lock:
            conf = self.get_confirmation(request_id, step_id, tool)
            if not conf:
                return False
            return conf.deny()

    def invalidate_request(self, request_id: str) -> int:
        """Invalidate all pending confirmations for a cancelled request.

        Returns number of confirmations invalidated.
        """
        count = 0
        with self._lock:
            for (req_id, _, _), conf in list(self._confirmations.items()):
                if req_id == request_id and conf.status == ConfirmationStatus.PENDING:
                    conf.status = ConfirmationStatus.DENIED
                    count += 1
        return count

    def prune_expired(self) -> int:
        """Prune long expired entries to prevent unbounded memory growth."""
        now = time.time()
        count = 0
        with self._lock:
            keys_to_remove = [
                key for key, conf in self._confirmations.items()
                if now > (conf.expires_at + 3600.0)  # keep for 1h after expiry for auditing
            ]
            for key in keys_to_remove:
                del self._confirmations[key]
                count += 1
        return count
