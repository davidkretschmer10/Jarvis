Architecture

Jarvis je modularni lokalni desktop aplikace v Pythonu. Architektura je rozdelena na vstupni aplikacni vrstvu, GUI, controller, AI engine, hlas, planner/executor, tools, desktop agent, vision, memory, services a testy. Hlavni pravidlo architektury je: lokalni, vysvetlitelne, testovatelne a rizikove akce pod kontrolou.

Vrstvy

app/main.py startuje lokalni runtime: Ollama, Jarvis Agent a GUI. interfaces/gui obsahuje PySide6 komponenty. interfaces/gui_controller.py je orchestrace mezi UI, event busem, AI, hlasem, pameti a agentem. ai/engine.py komunikuje s lokalnim Ollama endpointem, drzi request context, streaming a model status. core obsahuje agenta, planner, executor, state, memory, task memory a intent routing. tools obsahuje registrovatelne nastroje. Voice obsahuje hlasovy stack. vision obsahuje screenshot, OCR a vision analysis. tests overuji routing, voice, planner, tools a dalsi casti.

Tok udalosti

Uzivatel posle zpravu pres chat nebo hlas. Controller ulozi zpravu do aktualniho chatu, klasifikuje intent a rozhodne mezi chat odpovedi a agentnim pozadavkem. Chat pozadavek jde do AI engine. Agentni pozadavek jde pres routing/planner do executor nebo autonomous agent. Executor spousti tools a emituje task progress. Vysledek se ulozi do pameti a vrati do GUI i event busu.

Stav

Runtime stav je dnes rozdelen mezi controller atributy, JarvisState, TaskMemory, thread-local RequestContext, chat JSON a profile JSON. Cilova architektura ma stav sjednotit natolik, aby GUI, hlas a executor sdilely jednoznacne request/task ID a stavovy enum.

Lokalne omezene integrace

Ollama je lokalni AI backend. Flask agent je lokalni desktop bridge. Tesseract a Piper jsou lokalni komponenty. Cloudove providery se nepridavaji. services/api_clients.py existuje jako obecna slozka, ale dalsi vyvoj musi respektovat pravidlo 100% lokalnosti.

Architektonicke priority

Prednost ma jednoduchost pred preabstrahovanim. Nove moduly maji vznikat jen tam, kde snizuji slozitost nebo izolují riziko. Planner, tools a GUI nesmi sdilet nahodne globalni stavy bez jasneho duvodu. Kazda zmena architektury musi aktualizovat tento dokument.