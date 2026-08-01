from __future__ import annotations
from typing import Any


class RoutingResult:
    def __init__(
        self,
        task_type: str,
        recommended_model: str,
        confidence: float,
        reason: str,
        is_fallback: bool = False,
        original_model: str | None = None
    ):
        self.task_type = task_type
        self.recommended_model = recommended_model
        self.confidence = confidence
        self.reason = reason
        self.is_fallback = is_fallback
        self.original_model = original_model

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "recommended_model": self.recommended_model,
            "confidence": self.confidence,
            "reason": self.reason,
            "is_fallback": self.is_fallback,
            "original_model": self.original_model
        }
