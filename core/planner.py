from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from tools.registry import ToolRegistry
from utils.json_utils import extract_first_json_array


JSON = Dict[str, Any]


@dataclass
class Planner:
    registry: ToolRegistry

    def build_prompt(self, goal: str) -> str:
        tools = self.registry.describe_for_planner()
        return f"""
Jsi autonomni agent. Tvym ukolem je prevest uzivateluv cil na vykonatelny plan.

Pouzij pouze tyto tooly (presne nazvy):
{tools}

Pravidla:
- Vystup musi byt POUZE JSON pole kroku.
- Kazdy krok ma tvar: {{"tool": "<tool_name>", "input": {{...}}, "description": "<strucny cesky popis kroku pro uzivatele>"}}
- Zadny text okolo, zadne vysvetleni.
- Plan delej po malych krocich.
- Nevis-li, nejdriv si vyzadej info tooly, napr. list_dir/read_text_file.
- Vždy dodržuj následující hierarchii a priority nástrojů:
  1. Priorita 1 (Přímé nástroje): Pro otevření aplikací, webů, souborů nebo spouštění příkazů použij přímo k tomu určené nástroje (např. open_app, open_website, atd.). Nepoužívej Vision ani screenshoty.
  2. Priorita 2 (Python automatizace/Vyhledávání): Použij přímé otevření URL s vyhledávacími parametry pro vyhledávání namísto GUI klikání.
  3. Priorita 3 (Smart UI / Vision): Nástroje jako smart_click, smart_write, smart_checkbox, confirm_dialog, atd. (využívající screenshot a OCR) používej zásadně jako POSLEDNÍ MOŽNOST (last resort), pokud neexistuje přímá cesta.
- Pokud uživatel požaduje otevření nebo vyhledání nějakého webu (např. Google, Seznam, YouTube nebo obecně vyhledávání na internetu), NESMÍŠ v plánu generovat kroky typu smart_write, smart_click, nebo stisky kláves (press_key enter) pro vyplňování polí. Místo toho použij přímo nástroj open_website s vygenerovanou URL.

Příklad výstupu pro cíl "otevři chrome a vyhledej seznam":
[
  {{"tool": "open_app", "input": {{"name": "chrome"}}, "description": "Otevřít prohlížeč Chrome"}},
  {{"tool": "open_website", "input": {{"url": "https://www.seznam.cz"}}, "description": "Otevřít web Seznam v prohlížeči"}}
]

Příklad výstupu pro cíl "vyhledej Nvidia":
[
  {{"tool": "open_website", "input": {{"url": "https://www.google.com/search?q=Nvidia"}}, "description": "Vyhledat Nvidia v prohlížeči"}}
]

Příklad výstupu pro cíl "vyhledej Jarvis AI na youtube":
[
  {{"tool": "open_website", "input": {{"url": "https://www.youtube.com/results?search_query=Jarvis+AI"}}, "description": "Vyhledat Jarvis AI na YouTube v prohlížeči"}}
]

STATE:
- Behem vykonavani existuje sdileny `state`, do ktereho si tooly ukladaji vysledky.
- V inputu dalsich kroku muzes pouzivat templaty:
  - {{state.last_output}}
  - {{state.files[0]}}
  - {{state.data.<key>}} napr. {{state.data.last_written_path}}

Cil:
{goal}
""".strip()

    def plan(self, goal: str) -> List[JSON]:
        from ai.engine import ask_ai
        
        goal_lower = goal.lower()
        import re
        import unicodedata

        def strip_accents(text: str) -> str:
            text_norm = unicodedata.normalize("NFD", text)
            return "".join(c for c in text_norm if unicodedata.category(c) != "Mn")

        goal_clean = strip_accents(goal_lower)
        
        web_keywords = ["seznam", "google", "youtube", "web", "internet", "vyhledej", "najdi na", "search", "open website", "otevri"]
        is_web_request = any(kw in goal_clean for kw in web_keywords)
        
        feedback = None
        steps: List[JSON] = []
        
        for attempt in range(3):
            prompt = self.build_prompt(goal)
            if feedback:
                prompt += f"\n\nPOZOR: Předchozí pokus o plán selhal. Chyba: {feedback}\nOprav se a vygeneruj nový plán bez těchto chyb."
                
            raw = ask_ai(prompt)
            arr = extract_first_json_array(raw) or []
            steps = []
            for item in arr:
                if isinstance(item, dict) and "tool" in item:
                    steps.append(item)
                    
            if not steps:
                feedback = "Plán je prázdný nebo neobsahuje platný JSON."
                continue
                
            # Validation logic
            if is_web_request:
                invalid_tools = {"smart_click", "smart_write", "press_key", "screenshot", "read_screen", "confirm_dialog", "cancel_dialog", "open_search_result"}
                found_invalid = [s.get("tool") for s in steps if s.get("tool") in invalid_tools]
                if found_invalid:
                    feedback = f"Plán pro otevření webu/vyhledávání nesmí obsahovat UI/Vision kroky (nalezeno: {', '.join(found_invalid)}). Použij přímé otevření URL pomocí nástroje 'open_website'."
                    print(f"[PLAN VALIDATION] Attempt {attempt+1} failed: {feedback}")
                    continue
                    
            # If valid, exit loop early
            break
            
        return steps

    def replan(self, goal: str, failed_step: JSON, error_msg: str, current_state: Any = None) -> List[JSON]:
        """Generates a new plan for the remaining goal after a step failure."""
        from ai.engine import ask_ai

        state_info = ""
        if current_state and hasattr(current_state, "snapshot"):
            state_info = f"\nAktuální stav paměti: {current_state.snapshot()}"

        replan_prompt = f"""
Jsi autonomní agent Jarvis. Původní plán pro dosáhnutí cíle selhal.
Tvoř nový plán pro dokončení zbývající části cíle z aktuálního stavu.

Původní cíl: {goal}
Selhaný krok: {failed_step}
Chybová zpráva: "{error_msg}"
{state_info}

Dostupné nástroje:
{self.registry.describe_for_planner()}

Požadavky:
- Vrať POUZE platné JSON pole nových kroků pro dokončení cíle.
- Pokud cíl nelze splnit, vrať prázdné pole [].
- Nepoužívej stejný chybný nástroj se stejným vstupem bez úpravy.
"""
        raw = ask_ai(replan_prompt)
        arr = extract_first_json_array(raw) or []
        new_steps: List[JSON] = []
        for item in arr:
            if isinstance(item, dict) and "tool" in item:
                new_steps.append(item)
        return new_steps

