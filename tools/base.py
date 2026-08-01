from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


JSON = Dict[str, Any]


@dataclass(frozen=True)
class ToolContext:
    """
    Shared runtime context passed to tools.
    Keep this small and stable; add fields only when necessary.
    """

    dry_run: bool = False
    agent_base_url: str = "http://127.0.0.1:5000"
    workspace_root: Optional[str] = None


class Tool(Protocol):
    name: str
    description: str
    input_schema: JSON  # lightweight JSON-schema-ish dict

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        ...

