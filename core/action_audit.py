"""Central Action Audit Logger for Jarvis.

Records every high-level action decision, execution, verification, and error
with deterministic secret redaction to AppData storage.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


# Sensitive patterns for secret redaction
SENSITIVE_KEY_PATTERN = re.compile(
    r"(pass(word)?|token|secret|api[_-]?key|auth(orization)?|cookie|bearer|private[_-]?key)",
    re.IGNORECASE,
)


def redact_secrets(data: Any) -> Any:
    """Recursively redact sensitive keys and values from data structures."""
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if isinstance(k, str) and SENSITIVE_KEY_PATTERN.search(k):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_secrets(v)
        return redacted
    elif isinstance(data, list):
        return [redact_secrets(item) for item in data]
    elif isinstance(data, str):
        # Check if string contains token=xxx or password=xxx patterns
        if SENSITIVE_KEY_PATTERN.search(data) and ("=" in data or ":" in data):
            # Mask out assignment values
            return re.sub(
                r"((?:password|token|secret|api[_-]?key|bearer)\s*[:=]\s*)([^\s,;]+)",
                r"\1[REDACTED]",
                data,
                flags=re.IGNORECASE,
            )
        return data
    return data


@dataclass
class ActionAuditRecord:
    """Structured record of an action authorization and execution lifecycle."""
    timestamp: float
    request_id: str
    step_id: Optional[int]
    source: Optional[str]
    tool: str
    capability: str
    risk: str
    decision: str
    confirmation_status: Optional[str] = None
    execution_status: Optional[str] = None
    verification_status: Optional[str] = None
    resource: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        raw = asdict(self)
        return redact_secrets(raw)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class ActionAuditLogger:
    """Thread-safe append-only logger storing action audits in AppData."""

    def __init__(self, log_path: Optional[Path] = None, max_bytes: int = 10 * 1024 * 1024) -> None:
        self.max_bytes = max_bytes
        self._lock = threading.RLock()

        if log_path is not None:
            self.log_path = Path(log_path)
        else:
            appdata_dir = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
            if appdata_dir:
                base_dir = Path(appdata_dir) / "Jarvis" / "audit"
            else:
                base_dir = Path.home() / ".jarvis" / "audit"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.log_path = base_dir / "action_audit.jsonl"

        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def log(
        self,
        request_id: str,
        step_id: Optional[int],
        source: Optional[str],
        tool: str,
        capability: str,
        risk: str,
        decision: str,
        confirmation_status: Optional[str] = None,
        execution_status: Optional[str] = None,
        verification_status: Optional[str] = None,
        resource: Optional[str] = None,
        error: Optional[str] = None,
    ) -> ActionAuditRecord:
        """Create and atomically persist an ActionAuditRecord."""
        record = ActionAuditRecord(
            timestamp=time.time(),
            request_id=request_id or "unknown",
            step_id=step_id,
            source=source or "unknown",
            tool=tool or "unknown",
            capability=str(capability),
            risk=str(risk),
            decision=str(decision),
            confirmation_status=confirmation_status,
            execution_status=execution_status,
            verification_status=verification_status,
            resource=resource,
            error=str(error) if error else None,
        )

        self._persist_record(record)
        return record

    def _persist_record(self, record: ActionAuditRecord) -> None:
        """Thread-safe append to JSONL file with rotation protection."""
        with self._lock:
            try:
                # Rotate if file exceeds max_bytes
                if self.log_path.exists() and self.log_path.stat().st_size > self.max_bytes:
                    rotated = self.log_path.with_name(f"{self.log_path.stem}_{int(time.time())}.jsonl")
                    self.log_path.rename(rotated)

                line = record.to_json() + "\n"
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception:
                # Audit logging must not crash execution path
                pass


# Global default instance
_default_logger: Optional[ActionAuditLogger] = None
_logger_lock = threading.Lock()


def get_audit_logger() -> ActionAuditLogger:
    global _default_logger
    with _logger_lock:
        if _default_logger is None:
            _default_logger = ActionAuditLogger()
        return _default_logger
