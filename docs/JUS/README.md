Jarvis Ultimate Specification

Jarvis Ultimate Specification, zkratkou JUS, je hlavni technicka dokumentace projektu Jarvis. Tato slozka je zdroj pravdy pro dalsi vyvoj lokalniho Windows asistenta inspirovaneho Jarvisem z Iron Mana. Dokumentace popisuje skutecny stav projektu, cilovy stav, priority, architekturu, UX, implementacni pravidla, mereni kvality a backlog prace. Pokud je rozpor mezi kodem, starsimi poznamkami a JUS, ma JUS prednost, ale musi byt pri kazde zmene upraven tak, aby znovu odpovidal realite kodu.

Projekt Jarvis je lokalni desktopovy AI asistent pro Windows. Bezi nad Pythonem, PySide6 GUI, lokalnim Ollama backendem, hlasovym vstupem pres faster-whisper, hlasovym vystupem pres Piper, wake word engine pres Porcupine, desktopovou automatizaci pres lokalni Flask agenta a pomocne vision/OCR moduly. Projekt musi zustat 100 % lokalni. Do odvolani se nepridavaji nove cloudove sluzby, online API ani nove AI modely jako Gemini, OpenAI nebo Claude. Existujici Ollama integrace je lokalni runtime vrstva a neni povazovana za cloudovou sluzbu.
Zavazne vyvojove pravidlo

Po kazde implementaci nove funkce, opravy, refaktoringu nebo viditelne zmeny chovani musi byt aktualizovana dokumentace v docs/JUS. Povinna aktualizace vzdy zahrnuje CHANGELOG.md, PROGRESS.md a podle dopadu take prislusne tematicke dokumenty. Pokud zmena meni architekturu, aktualizuje se 14_ARCHITECTURE.md. Pokud meni UX, aktualizuje se 03_UX.md. Pokud meni hlas, aktualizuje se 01_VOICE_SYSTEM.md. Pokud meni GUI, aktualizuje se 02_GUI.md. Pokud behem prace vznikne zjevne zlepseni, riziko nebo chybejici cast, prida se do BACKLOG.md.

Pred kazdou implementaci se provadi analyza soucasneho stavu. Vyvoj musi porovnat realny kod s JUS dokumentaci, najit chybejici nebo zastarale casti a rozhodnout, zda navrhovana zmena prinasi lepsi uzivatelsky zazitek. Pokud odpoved na otazku "Prinese tato zmena lepsi zazitek uzivateli?" neni ano, zmena se nema implementovat. Toto pravidlo chrani projekt pred nahodnym rozsirovanim a drzi smer k nejlepsimu lokalnimu desktop asistentovi pro Windows.
Priorita projektu

Prioritni poradi je UX, Voice, GUI, Desktop Automation, Vision, Planner, Memory, Performance, Plugin System a AI modely. Toto poradi neznamena, ze nizsi oblasti nejsou dulezite. Znamena, ze pri konfliktu rozhodnuti ma prednost to, co zlepsi ovladatelnost, spolehlivost a prirozenost asistenta pro uzivatele. Jarvis nema byt sbirka demo funkci; ma byt spolehlivy, rychly a prijemny spolecnik pro realnou praci na Windows.
Struktura dokumentace

MASTER_ROADMAP.md definuje dlouhodoby smer a faze. CHANGELOG.md zaznamenava kazdou zmenu. PROGRESS.md drzi procentualni stav projektu. BACKLOG.md obsahuje strukturovane polozky s prioritou, duvodem, odhadem a zavislostmi. Dokumenty 01 az 15 popisuji konkretni oblasti systemu: hlas, GUI, UX, vision, planner, automatizaci, pamet, desktop control, plugin system, security, settings, personality, performance, architekturu a testovani.
Aktualni realita projektu

Projekt obsahuje hlavni vstup app/main.py, GUI vrstvu v interfaces/gui, controller v interfaces/gui_controller.py, lokalni AI engine v ai/engine.py, model manager v ai/model_manager.py, hlasovou pipeline v Voice, planovaci a exekucni vrstvu v core, nastroje v tools, vision moduly v vision, testy v tests a archivovanou Discord vetev v archive/discord_legacy. Runtime data chatu a profilu se ukladaji do %APPDATA%/Jarvis. Projekt ma jednotkove testy pres unittest, PyInstaller konfiguraci, opravny skript prostredi a batch soubory pro start.
Definice kvality

Kvalita Jarvise se meri podle toho, zda uzivatel dokaze rychle rict nebo napsat cil, videt co Jarvis dela, prerusit nebo opravit akci, dostat srozumitelnou odpoved a zustat v kontrole nad svym pocitacem. Technicka kvalita se meri testy, stabilitou lokalnich sluzeb, latenci hlasoveho cyklu, uspesnosti intent routingu, jasnosti stavovych hlasek, omezenim rizikovych akci, citelnosti architektury a aktualnosti dokumentace.

