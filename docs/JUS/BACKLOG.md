Backlog

Backlog obsahuje praci, ktera byla identifikovana pri analyzach, implementacich nebo dokumentacnich aktualizacich. Kazda polozka musi mit ID, prioritu, popis, duvod, odhad pracnosti a zavislosti. Priority pouzivaji P0 pro kriticke blokery, P1 pro vysoky dopad na UX nebo spolehlivost, P2 pro dulezite zlepseni a P3 pro pozdejsi rozsirovani.

JUS-001

Priorita: P1

Popis: Sjednotit cestinu a encoding ve vsech GUI a agentnich textech. V aktualnim kodu jsou videt rozbite retezce v nekterych PySide6 panelech a controller hlaskach.

Duvod: Rozbite znaky primo poskozuji UX, duveru v asistenta a citelnost stavovych hlasek. Hlasovy a desktopovy asistent musi komunikovat prirozene cesky.

Odhad pracnosti: M

Zavislosti: Audit souboru interfaces, core, ai.prompts, Voice a test s ceskymi znaky ve Windows konzoli i GUI.

JUS-002

Priorita: P1

Popis: Zavest jednotny stavovy model Jarvise napric chatem, hlasem, agentem, GUI panelem a task progress widgetem.

Duvod: Uzivatel musi vzdy vedet, zda Jarvis posloucha, nahrava, prepisuje, premysli, vykonava akci, ceka na potvrzeni, mluvi, dokoncil nebo selhal.

Odhad pracnosti: L

Zavislosti: interfaces/gui_controller.py, Voice/pipeline/realtime_pipeline.py, interfaces/gui/windows/main_window.py, TaskProgressWidget.

JUS-003

Priorita: P1

Popis: Navrhnout permission model pro desktopove akce: bezpecne akce bez potvrzeni, citlive akce s potvrzenim, zakazane akce s vysvetlenim.

Duvod: Desktop agent muze ovlivnit realny pocitac. Bez jasnych hranic roste riziko nechteneho klikani, psani nebo spousteni prikazu.

Odhad pracnosti: L

Zavislosti: Tool registry, executor, GUI potvrzovaci dialog, audit log.

JUS-004

Priorita: P2

Popis: Dodelat Memory panel tak, aby uzivatel mohl zobrazit, upravit, exportovat a smazat profilove fakty a historii.

Duvod: Lokalni pamet je hodnota projektu jen tehdy, kdyz je kontrolovatelna a vysvetlitelna.

Odhad pracnosti: M

Zavislosti: core/memory.py, interfaces/gui/windows/main_window.py, storage schema.

JUS-005

Priorita: P2

Popis: Pridat diagnostickou obrazovku pro lokalni zavislosti: Ollama, modely, Tesseract, mikrofon, audio vystup, Piper model, Porcupine key/config a zapis do %APPDATA%.

Duvod: Jarvis ma mnoho lokalnich komponent. Uzivatel potrebuje rychle zjistit, proc nefunguje hlas, vision nebo model.

Odhad pracnosti: L

Zavislosti: Settings GUI, model manager, tesseract validator, voice config.

JUS-006

Priorita: P2

Popis: Rozsirit end-to-end testy pro nejdulezitejsi scenare: napsat chat dotaz, spustit hlasovy dotaz, otevrit aplikaci, otevrit web, pouzit OCR fallback, zrusit ukol.

Duvod: Jednotkove testy existuji, ale cilovy produkt potrebuje overeni realnych workflow.

Odhad pracnosti: L

Zavislosti: Stabilni testovatelne rozhrani pro GUI/controller a mocky lokalnich sluzeb.

JUS-007

Priorita: P3

Popis: Definovat lokalni plugin manifest a minimalni plugin loader pro budouci rozsireni toolu a GUI panelu.

Duvod: Plugin system je cilova oblast, ale nema predbehnout stabilizaci UX, voice a desktop automation.

Odhad pracnosti: XL

Zavislosti: Bezpecnostni model, tool registry kontrakt, settings schema, test harness.