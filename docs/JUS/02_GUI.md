GUI

GUI je hlavni pracovni plocha Jarvise. Aktualni aplikace pouziva PySide6 a je organizovana kolem JarvisMainWindow, GuiController, samostatnych widgetu pro chat, hlas, nastaveni, modely, pamet, nastroje, bocni seznam chatu a pravy informacni panel. GUI nesmi byt pouze dekorace. Ma byt ridici centrum, kde uzivatel vidi konverzaci, stav lokalnich sluzeb, prubeh ukolu, hlasovy rezim a kontrolu nad pameti.

Architektura

Vstup do GUI jde pres app/gui.py a interfaces/gui_app.py. Hlavni okno je v interfaces/gui/windows/main_window.py, zatimco interfaces/gui/main_window.py slouzi jako export kompatibility. Controller v interfaces/gui_controller.py propojuje GUI, event bus, AI engine, memory, voice a agenta. Signalovy model PySide6 je spravne zvolen, protoze umoznuje oddelit background vlakna od UI threadu.

Navrh

Soucasny layout obsahuje hlavni surface, levy sliding chat panel, pravy info panel, top navigation, chat page, voice page, settings page, models page, memory page a tools page. Voice page je specialni, protoze pri prechodu na hlas skryva okraje a meni layout na immersive rezim. Toto je dobry smer pro Jarvis identitu, ale musi zustat ergonomicky: navigace musi byt dostupna, texty citelne a stav asistenta jednoznacny.

UX scenare

Uzivatel otevre Jarvise a vidi chat v ready stavu. Muze zalozit novy chat, zmenit model, napsat dotaz, prepnout na hlas, zobrazit task progress nebo zkontrolovat stav Ollama a Vision. Kdyz agent vykonava ukol, pravy panel ma ukazovat kroky a stav. Kdyz je potreba potvrzeni, GUI musi jasne ukazat volby a nespolihat pouze na text v chatu.

Implementacni pravidla

GUI zmeny musi pouzivat existujici komponenty a styl v interfaces/gui. Nove panely nemaji duplikovat controller logiku. Dlouhe operace nesmi blokovat UI thread. Vsechny uzivatelske texty musi byt korektne cesky a bez rozbiteho encodingu. Stavove texty maji byt centralizovane a mapovane na vizualni stav logo/orb/navigation.

Mereni kvality

Kvalita GUI se meri stabilitou startu, citelnosti pri minimalni velikosti okna, rychlosti odezvy pri streamovani odpovedi, absenci zamrzani, prehlednosti task progress, korektnosti ceskych textu a schopnosti uzivatele pochopit stav bez cteni logu.

Budouci rozsireni

Prioritou je doplnit skutecne funkcni Memory panel, diagnosticky Settings panel, permission dialogy pro desktop akce, sjednocene notifikace chyb, audit ukolu a detailni stav lokalnich zavislosti.