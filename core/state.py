from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


JSON = Dict[str, Any]


@dataclass
class JarvisState:
    """
    Shared state for a single agent run.

    Why it exists:
    - Multi-step tasks need memory between steps (outputs, filenames, extracted data).
    - Tools can write small structured results into `data` and reference them later.

    Expected usage:
    - Executor passes the same `state` instance to every tool.
    - After each step, executor updates:
        - state.last_output
        - state.tool_results (per-step history)
        - state.files (created/used files)
        - state.data (arbitrary structured data)
    """

    files: List[str] = field(default_factory=list)
    last_output: str = ""
    data: JSON = field(default_factory=dict)
    tool_results: List[JSON] = field(default_factory=list)

    def snapshot(self) -> JSON:
        """Small debug-friendly snapshot (avoid huge dumps)."""
        return {
            "files": list(self.files)[:10],
            "last_output": (self.last_output[:200] + "...") if len(self.last_output) > 200 else self.last_output,
            "data_keys": sorted(list(self.data.keys()))[:30],
            "tool_results_count": len(self.tool_results),
        }

