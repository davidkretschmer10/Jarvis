Settings

Settings jsou misto, kde uzivatel ridi lokalniho Jarvise. Nastaveni musi byt srozumitelne, vratitelne a bezpecne. Aktualni projekt ma config/settings.py, ai/model_manager.py, interfaces/gui/settings_widget.py, interfaces/gui/models_widget.py a hlasovou konfiguraci ve Voice/utils/config.py.

Ucel

Settings maji umoznit spravu lokalnich sluzeb, modelu, hlasu, wake word, TTS, pameti, permission pravidel, vzhledu a diagnostiky. Nastaveni nesmi byt jen technicka forma config souboru; ma uzivateli vysvetlit dopad voleb.

Architektura

Model settings se ukladaji a nacitaji pres ai.model_manager. GUI controller uklada model volbu per chat. Hlasova konfigurace je oddelena ve Voice config. Chybi jednotne schema nastaveni napric projektem, ktere by definovalo defaulty, validaci a migrace.

UX

Uzivatel ma videt stav Ollama, aktivni model, stahovani modelu, chybu, stav OCR, stav hlasu a wake word. Nastaveni rizikovych schopnosti musi byt jasne oznacena. Diagnostika ma byt prvni vec, kterou uzivatel pouzije pri problemu.

Implementace

Nastaveni musi byt lokalni JSON nebo podobny citelny format v %APPDATA%/Jarvis. Kazde nastaveni ma mit default, typ, validaci a popis. Zmeny nastaveni nesmi vyzadovat restart, pokud to neni technicky nutne. Pokud restart nutny je, GUI to musi rict.

Mereni kvality

Kvalita se meri poctem nastaveni dostupnych z GUI, poctem validovanych hodnot, absenci rozbitych config souboru, jasnosti diagnostiky a schopnosti obnovit defaulty.