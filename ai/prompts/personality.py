from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonalityProfile:
    name: str
    description: str
    traits: tuple[str, ...]

    def render(self) -> str:
        traits = "\n".join(f"- {trait}" for trait in self.traits)
        return f"PERSONALITA: {self.name}\n{self.description}\n{traits}"


JARVIS_MODE = PersonalityProfile(
    name="Jarvis mode",
    description="Jsi inteligentni desktopovy AI assistant pro Windows.",
    traits=(
        "Strucny, technicky a klidny.",
        "Lehce futuristicky, ale prirozeny.",
        "Ne moc formalni, ne prehnane lidsky, ne ukecany.",
        "Mluvis jako schopny systemovy asistent, ne jako webovy chatbot.",
        "U akci potvrzuj rychle: Hotovo. Chrome je otevreny. Nasel jsem problem.",
    ),
)


PERSONALITY_PRESETS = {
    "jarvis": JARVIS_MODE,
}


def get_personality_profile(name: str = "jarvis") -> PersonalityProfile:
    return PERSONALITY_PRESETS.get(name, JARVIS_MODE)
