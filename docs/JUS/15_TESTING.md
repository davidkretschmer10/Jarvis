Testing

Testovani chrani Jarvise pred regresi v routingu, hlasu, planneru, desktop automation, pameti, GUI controlleru a tool registru. Projekt pouziva standardni unittest a obsahuje testy ve slozce tests, vcetne stress podslozky.

Aktualni pokryti

Existuji testy pro web routing, wakeword, voice pipeline, TTS, tool registry, router, planner/executor flow, PC control, Ollama connection, language prompt, intents, GUI controller, file manager, autonomous agent, app scan a agent command execution. Stress testy pokryvaji router, planner, performance monitor, launch stress a chaos test.

Ucel

Testy maji overit, ze lokalni asistent zustava spolehlivy pri realnych uzivatelskych scenarich. Jednotkove testy kontroluji funkce a kontrakty. Integracni testy maji kontrolovat tok od vstupu po vystup. Stress testy maji odhalit zpomaleni, race conditions a nestabilitu.

Prioritni scenare

Nejdulezitejsi testy jsou: klasifikace beznych ceskych prikazu, otevreni aplikace bez LLM, otevreni webu primou URL, odmítnuti vision kroků pro webovy request, hlasova pipeline bez skutecneho mikrofonu pres mock, TTS interrupt, executor stop pri chybe, confirmation required, memory load/save a GUI controller signaly.

Implementace

Testy nemaji vyzadovat cloud ani online API. Lokalne zavisle komponenty se mockuji, pokud by test byl krehky. Testy nesmi zapisovat mimo povolene testovaci lokace. Pro GUI se maji pouzit controller-level testy a pozdeji UI smoke testy. Pro performance se maji zaznamenavat metriky, ale nevytvaret nestabilni prahy bez rezervy.

Mereni kvality

Kvalita testovani se meri poctem kritickych workflow pokrytych testem, rychlosti test suite, stabilitou na Windows, schopnosti reprodukovat chybu a vazbou na backlog. Pri kazde zmene funkce musi byt vyhodnoceno, zda je potreba pridat nebo upravit test.