# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, Optional


class ObservationType(str, Enum):
    PROCESS = "PROCESS"
    WINDOW = "WINDOW"
    FILE = "FILE"
    DIRECTORY = "DIRECTORY"
    SCREEN = "SCREEN"
    OCR = "OCR"
    BROWSER = "BROWSER"
    TOOL_RESULT = "TOOL_RESULT"
    SYSTEM = "SYSTEM"


@dataclass
class Observation:
    """
    Represents an objective, factual observation of the physical system/environment state.
    Distinct from a tool's internal execution report.
    """

    source: str
    type: ObservationType
    data: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    evidence: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "type": self.type.value if isinstance(self.type, ObservationType) else str(self.type),
            "data": self.data,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }
