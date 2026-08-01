from __future__ import annotations


def build_screen_description_prompt(extra_instruction: str | None = None) -> str:
    prompt = (
        "Jsi vision modul asistenta Jarvis pro Windows.\n"
        "Analyzuj screenshot obrazovky a popis ho cesky, vecne a strukturovane.\n"
        "Zamer se na:\n"
        "- jaka aplikace nebo web je pravdepodobne otevreny,\n"
        "- hlavni viditelne UI prvky,\n"
        "- viditelny text,\n"
        "- aktivni nebo dulezite ovladaci prvky,\n"
        "- co by mohl uzivatel nebo agent udelat jako dalsi krok.\n"
        "Nevymyslej si obsah, ktery na obrazovce neni videt."
    )

    if extra_instruction:
        prompt += f"\n\nDodatecna instrukce:\n{extra_instruction.strip()}"

    return prompt


def build_observation_prompt(goal: str | None = None) -> str:
    prompt = (
        "Jsi observation vrstva autonomniho PC agenta Jarvis.\n"
        "Z obrazovky vytvor pozorovani vhodne pro dalsi planovani akce.\n"
        "Vrat cesky popis aktualniho stavu obrazovky, viditelnych cilu, moznych tlacitek, "
        "vstupnich poli a prekazek. Pokud neni neco jiste, napis to jako nejistotu."
    )

    if goal:
        prompt += f"\n\nAktualni cil agenta:\n{goal.strip()}"

    return prompt


def build_ui_detection_prompt(extra_instruction: str | None = None) -> str:
    prompt = (
        "Jsi UI detection modul asistenta Jarvis pro Windows.\n"
        "Analyzuj screenshot a vrat POUZE validni JSON objekt bez markdownu, bez komentaru a bez vysvetleni.\n"
        "Detekuj interaktivni UI elementy pripravene pro budouci autonomni ovladani PC.\n"
        "Podporovane typy elementu jsou presne: button, input, dropdown, menu_item, checkbox, tab, popup.\n"
        "Souradnice jsou v pixelech vuci levemu hornimu rohu screenshotu.\n"
        "Kazdy element musi mit bounding box cele klikatelne/viditelne oblasti.\n"
        "Nevymyslej elementy, ktere nejsou videt. Kdyz si nejsi jisty, sniz confidence.\n\n"
        "Vrat JSON v tomto formatu:\n"
        "{\n"
        '  "screen_type": "browser",\n'
        '  "elements": [\n'
        "    {\n"
        '      "id": "btn_login",\n'
        '      "type": "button",\n'
        '      "text": "Login",\n'
        '      "x": 441,\n'
        '      "y": 220,\n'
        '      "width": 120,\n'
        '      "height": 40,\n'
        '      "confidence": 0.93\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    if extra_instruction:
        prompt += f"\n\nDodatecna instrukce:\n{extra_instruction.strip()}"

    return prompt
