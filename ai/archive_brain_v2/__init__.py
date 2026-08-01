from __future__ import annotations

from ai.routing.router import route_task, get_installed_models
from ai.routing.routing_result import RoutingResult
from ai.routing.model_registry import MODEL_SPECIALTIES
from ai.routing.fallback_manager import FALLBACK_MAP

__all__ = [
    "route_task",
    "get_installed_models",
    "RoutingResult",
    "MODEL_SPECIALTIES",
    "FALLBACK_MAP",
]
