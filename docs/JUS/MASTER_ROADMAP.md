Master Roadmap

Tento roadmap dokument urcuje strategicky smer projektu Jarvis. Cilem neni vyrobit obycejny chatbot v okne, ale lokalniho Windows asistenta, ktery kombinuje rychly chat, hlasove ovladani, desktopovou automatizaci, vision kontext, pamet a profesionalni UX. Roadmap je rizena pravidlem, ze kazda zmena musi zlepsovat uzivatelsky zazitek nebo spolehlivost systemu.

Faze 1: Stabilni lokalni zaklad

Zakladni faze je z velke casti hotova. Projekt umi spustit GUI, komunikovat s lokalnim Ollama serverem, uchovavat chaty a profil v %APPDATA%/Jarvis, obsluhovat hlasovy vstup a vystup, registrovat nastroje a spoustet desktopove akce pres lokalni agent. Dalsi prace v teto fazi ma odstranit drsne hrany: sjednotit kody a texty s diakritikou, doplnit jasne chyby pro chybejici zavislosti, stabilizovat start lokalnich procesu a zlepsit viditelnost stavu v GUI.

Faze 2: UX jako hlavni produkt

Jarvis musi vzdy ukazovat, co dela, proc to dela a co potrebuje od uzivatele. GUI ma byt pracovni plocha asistenta, ne jen chat. Chat, hlas, nastaveni, modely, pamet, nastroje a prubeh ukolu musi byt sjednocene do jednoho citelneho mentalniho modelu. Prvni priorita je konzistentni stavovy system: Ready, Listening, Recording, Transcribing, Thinking, Acting, Speaking, Waiting for confirmation, Failed a Completed. Kazdy stav musi byt viditelny v GUI a pouzitelny pro hlasovy rezim.

Faze 3: Hlas jako prirozena cesta

Hlasovy system ma byt pro Jarvise klicovy. Aktualni stack obsahuje wake word, audio capture, VAD, faster-whisper STT a Piper TTS. Roadmap pro hlas vede ke stabilnimu hands-free rezimu: spolehlive probuzeni, nahravani do ticha, casne zobrazeni rozpoznaneho textu, rychla odpoved, preruseni mluveni a jasne potvrzovani rizikovych akci. Hlas se nema chovat jako doplnek ke chatu, ale jako rovnocenny vstupni kanal.

Faze 4: Desktop automation

Jarvis musi umet provadet bezne akce na Windows. Prioritou jsou prime nastroje pred vision klikaci automatizaci. Otevreni aplikace, webu, vyhledani, psani textu, klavesove zkratky a prace se soubory maji byt deterministicke, auditovatelne a potvrzovane tam, kde hrozi skoda. Vision a OCR jsou posledni moznost, kdy prime API nebo systemova akce nestaci.

Faze 5: Vision a kontext obrazovky

Vision vrstva ma dodat Jarvisovi schopnost chapat obrazovku. Aktualni system ma screenshot manager, UI detector, Tesseract validator, parsers, overlay renderer a lokalni Ollama vision engine. Cilem je, aby Jarvis umel popsat obrazovku, najit UI element, navrhnout opravu selhane akce a pracovat s vizualnim stavem bez nebezpecneho hadani. Vision musi byt merena uspesnosti detekce, latenci a poctem pripadu, kdy uzivatel musel zasahnout.

Faze 6: Planner a agentni spolehlivost

Planner ma prekladat cil na male overitelne kroky. Executor ma kazdy krok spustit pres registrovany tool, aktualizovat stav a v pripade chyby nabidnout opravu nebo si vyzadat pomoc. Stavajici Planner, Executor, TaskMemory, JarvisState a fast intent router tvori dobry zaklad. Dalsi cil je sjednotit deterministicke prikazy, LLM planner a obnovu po chybe do jedne citelne cesty pro uzivatele.

Faze 7: Pamet a personalizace

Pamet dnes uklada chaty, model volby a jednoduche profilove fakty. Dlouhodoby cil je pamet, ktera zlepsuje odpovedi, ale neprekvapuje uzivatele. Pamet musi byt lokalni, kontrolovatelna, smazatelna a vysvetlitelna. Uzivatel musi vedet, co si Jarvis pamatuje, proc to pouziva a jak to upravit.

Faze 8: Plugin system

Plugin system zatim neni plne realizovana produktova vrstva. Roadmap pocita s lokalnimi pluginy, ktere pridavaji tooly, GUI panely, nastaveni a testy bez zasahu do jadra. Do te doby se nema vynucovat slozita plugin architektura. Nejprve musi byt stabilni registr nastroju, bezpecnostni hranice a dokumentace kontraktu.

Faze 9: Baleny Windows produkt

Jarvis ma byt spustitelny pro uzivatele bez vyvojarskeho ritualu. Existuje PyInstaller spec a startovaci batch soubory. Cilova faze zahrnuje kontrolu zavislosti, opravu prostredi, start lokalnich sluzeb, diagnostiku, logy a jasny recovery postup. Instalace nesmi pridavat cloudove zavislosti ani tise stahovat neodsouhlasene modely.