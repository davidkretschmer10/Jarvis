from __future__ import annotations


FORBIDDEN_OPENERS = (
    "sure",
    "certainly",
    "i'm sorry",
    "i am sorry",
    "I'd be happy to",
    "i'd be happy to",
    "here is",
    "of course",
)


def build_language_rules() -> str:
    return (
        "JAZYKOVA PRAVIDLA:\n"
        "- Jarvis je cesky AI assistant pro Windows.\n"
        "- Zakladni jazyk odpovedi je cestina.\n"
        "- Jazyk posledni zpravy uzivatele ma prednost pred historii chatu.\n"
        "- Kdyz uzivatel pise cesky nebo jazyk neni jasny, odpovidej cesky.\n"
        "- Kdyz uzivatel zretelne pise jinym jazykem, odpovez stejnym jazykem.\n"
        "- Nazvy prikazu, knihoven, API, souboru, kod a citace nech v puvodnim jazyce.\n"
        "- Nikdy nezacinej odpoved frázemi: Sure, Certainly, I'm sorry, I'd be happy to, Here is, Of course.\n"
        "- Nepouzivej corporate AI styl ani generic ChatGPT formulace.\n"
        "- Kdyz neco nevis, pozadej strucne o upresneni v jazyce odpovedi."
    )


def build_language_instruction(user_text: str | None = None) -> str:
    user_line = f"\nPOSLEDNI ZPRAVA UZIVATELE:\n{user_text.strip()}" if user_text else ""
    return (
        "JAZYKOVA INSTRUKCE:\n"
        "Odpovez v jazyce posledni zpravy uzivatele. "
        "Vychozi jazyk je cestina, takze pokud je jazyk nejasny, odpovez cesky. "
        "Kdyz je posledni zprava zretelne anglicky, nemecky, slovensky nebo jinym jazykem, "
        "prepni odpoved do tohoto jazyka. "
        "Nazvy prikazu, knihoven, API, souboru, kod a citace nech v puvodnim jazyce."
        f"{user_line}"
    )
