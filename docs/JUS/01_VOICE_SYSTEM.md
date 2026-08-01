Voice System

Hlasovy system je jedna z nejdulezitejsich casti Jarvise. Jeho ucelem je umoznit uzivateli ovladat asistenta prirozene, bez neustaleho psani, a dostavat odpovedi hlasem v lokalnim prostredi. Aktualni implementace stoji na modulech ve slozce Voice: audio capture, VAD, wake word engine, STT pres faster-whisper, TTS pres Piper a orchestrace v Voice/pipeline/realtime_pipeline.py. Starsi integracni vrstva je dostupna pres interfaces/voice.py, kterou pouziva GuiController.

Architektura

Hlasovy tok ma byt Wake -> Recording -> Transcribing -> Thinking -> Speaking -> Ready. RealtimeVoicePipeline drzi AudioCapture, WhisperEngine, PiperEngine a PorcupineWakeWordEngine. Pipeline prijima callbacky pro status, uzivatelsky text, partial text, AI chunk, AI done, volume a error. Tento design je spravny, protoze oddeluje audio mechaniku od GUI a AI odpovedi. Controller a GUI maji poslouchat udalosti, ne duplikovat audio logiku.

UX

Uzivatel musi vzdy videt a slyset, v jakem stavu Jarvis je. Pri wake word detekci ma GUI okamzite prejit do aktivniho hlasoveho stavu. Pri nahravani ma byt videt hlasitost. Pri transkripci ma byt videt rozpoznany text. Pri odpovedi ma byt mozne TTS prerusit. Hlasovy rezim nesmi blokovat chat ani desktopove ovladani bez jasne indikace.

Scenare

Zakladni scenar je "Jarvis" -> uzivatel rekne prikaz -> Jarvis prepis zobrazi -> provede nebo odpovi -> precte vysledek. Manualni scenar je klik na mikrofon -> nahravani -> stop -> transkripce -> odpoved. Chybovy scenar je chybejici mikrofon, chybejici Piper model, chybejici wake word konfigurace, prilis tiche audio nebo prazdna transkripce. V kazdem pripade musi Jarvis vratit srozumitelnou lokalni chybu.

Implementace

Hlasova implementace musi zustat 100 % lokalni. STT pouziva lokani faster-whisper modely a TTS pouziva lokalni Piper model cs_CZ-jirka-medium.onnx. Pridani cloudoveho STT/TTS je zakazane. Pipeline musi podporovat preruseni pres cancel event, stop audio capture a interrupt TTS. Vsechny dlouhe operace musi bezet mimo GUI thread.

Mereni kvality

Kvalita se meri latenci od konce reci po zacatek odpovedi, presnosti transkripce cestiny, uspesnosti wake word, poctem prazdnych transkripci, stabilitou audio zarizeni, schopnosti prerusit TTS a jasnosti stavovych hlasek. Cilem je, aby bezny kratky hlasovy dotaz pusobil okamzite a predvidatelne.

Budouci rozsireni

Prioritni rozsireni jsou sjednoceny stavovy model, hlasove potvrzovani rizikovych desktop akci, lepsi detekce konce reci, uzivatelske nastaveni rychlosti a hlasitosti TTS, diagnostika mikrofonu a automaticke recovery pri chybe audio backendu.