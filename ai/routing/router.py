from __future__ import annotations

class RoutingResult:
    def __init__(self, model: str):
        self.recommended_model = model
        self.original_model = model
        self.is_fallback = False

def route_task(prompt: str, chat_model: str | None = None) -> RoutingResult:
    return RoutingResult("llama3")
    
def get_installed_models() -> list[str]:
    return ["llama3"]
    
def start_background_pull_vision() -> None:
    pass
