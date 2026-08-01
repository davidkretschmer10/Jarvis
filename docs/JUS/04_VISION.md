Vision

Vision system dava Jarvisovi schopnost rozumet obrazovce. Aktualni kod obsahuje vision_engine.py, screenshot_manager.py, ui_detector.py, tesseract_validator.py, debug_visualizer.py, parsery, schemas, overlay renderer a prompt builder. Vision pouziva lokalni screenshoty, OCR/Tesseract a lokalni Ollama vision model. Vision nesmi pouzivat cloudove API.

Ucel

Vision se pouziva pro popis obrazovky, detekci UI prvku, chytre klikani, opravu selhanych agentnich kroku a kontext tam, kde prime desktopove nastroje nestaci. Neni to primarni cesta pro otevreni webu nebo aplikace. Planner uz obsahuje pravidlo, ze vision/UI kroky jsou posledni moznost.

Architektura

ScreenshotManager porizuje obrazovku a uklada soubor. VisionEngine posila obrazek lokalnimu Ollama /api/generate endpointu s obrazkem v base64 a promptem. TesseractValidator kontroluje OCR dostupnost. UIDetector a parsery prevadi OCR/vision vystup na strukturovane UI elementy. Executor pri selhani umi zachytit obrazovku, detekovat prvky a nechat lokalni LLM navrhnout opravnou akci.

UX

Vision musi byt uzivateli prezentovano jako "divam se na obrazovku" nebo "zkousim najit prvek". Pokud OCR nebo vision model chybi, Jarvis ma jasne rict, ze vision neni dostupny a jaky komponent chybi. Pri vision akci nesmi Jarvis slepe klikat na nejisty prvek bez kontroly.

Implementace

Kazdy vision vystup musi byt validovan. Strukturovane schema UI prvku ma obsahovat typ, text, souradnice a rozmer. Latence vision volani je vyssi, proto musi bezet mimo GUI thread a musi mit timeout. Screenshoty jsou lokalni runtime artefakty a nemaji se pridavat do repozitare.

Mereni kvality

Kvalita se meri uspesnosti detekce prvku, presnosti souradnic, latenci popisu obrazovky, poctem VisionError chyb, poctem uspesnych oprav po selhani a poctem pripadu, kdy vision navrhlo nebezpecnou nebo chybnou akci.

Budouci rozsireni

Prioritou je lepsi diagnostika Tesseractu, testovaci screenshot dataset, vizualni debug overlay, confidence score pro UI prvky a pravidla pro potvrzeni pred kliknutim na nizko-konfidencni prvek.