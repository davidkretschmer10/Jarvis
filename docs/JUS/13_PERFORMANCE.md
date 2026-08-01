Performance

Performance v Jarvisovi znamena rychly start, rychlou odezvu chatu, nizkou latenci hlasu, nezamrzajici GUI, efektivni lokalni HTTP spojeni a rozumne timeouty pro vision. Projekt je lokalni, takze vykon zavisi na Windows stroji, dostupnych modelech, CPU/GPU, audio zarizeni a OCR.

Aktualni stav

ai.engine pouziva requests.Session s keep-alive adapterem a retry logikou pro Ollama. GUI pouziva background vlakna pro status a AI praci. Voice pipeline pouziva vlastni vlakna a eventy. Vision ma timeout 120 sekund. Executor bezi krokove a uklada stav. To je dobry zaklad, ale chybi systematicke metriky a performance dashboard.

Prioritni metriky

Meri se start aplikace, health check Ollama, cas do prvniho tokenu, streaming rychlost, cas STT, cas TTS zacatku, wake word odezva, vision request latence, delka desktop akce a GUI frame responsiveness. Pro uzivatele je nejdulezitejsi subjektivni pocit, ze Jarvis reaguje hned a nezamrzl.

Implementace

Dlouhe operace musi bezet mimo GUI thread. HTTP klienti maji pouzivat reuse spojeni. Vision a model volani musi mit timeout a chybove hlasky. Logy performance maji byt citelne a nesmi obsahovat secrets. Automaticke stahovani modelu musi byt minimalni a explicitne viditelne.

UX

Kdyz akce trva, Jarvis musi ukazat, ze pracuje. Ticho a zamrzly interface jsou horsi nez pomalejsi, ale komunikovana akce. Pro hlas je kriticka latence mezi koncem reci a odpovedi; pokud je delsi, GUI musi ukazat transcribing/thinking.

Budouci rozsireni

Pridat lightweight metrics collector, diagnosticky performance panel, mereni per request ID, histogramy latenci a testy proti regresim. Optimalizace se maji delat podle namerenych dat, ne podle dojmu.