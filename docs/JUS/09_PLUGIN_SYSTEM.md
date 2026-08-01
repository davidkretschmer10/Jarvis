Plugin System

Plugin system je cilova schopnost projektu, ale aktualne neni hlavnim vyvojovym fokusem. Projekt uz ma tools.registry.ToolRegistry, coz je prirozeny zaklad pro budouci pluginy. Plny plugin system se ma budovat az po stabilizaci UX, hlasu, GUI, desktop automation a security.

Ucel

Pluginy maji umoznit lokalni rozsirovani Jarvise bez zasahu do jadra. Plugin muze pridat tool, GUI panel, nastaveni, prompt fragment, testy nebo lokalni integraci. Plugin nesmi automaticky pridavat cloudove sluzby ani online API bez explicitniho rozhodnuti projektu, ktere je aktualne zakazane.

Navrh

Minimalni plugin by mel mit manifest s nazvem, verzí, popisem, autorem, seznamem toolu, pozadavky, permission deklaraci a test entrypointem. Loader by mel nacist pouze pluginy z lokalni povolene slozky. Kazdy tool z pluginu musi projit stejnou validaci jako vestavene tooly: jmeno, popis, input schema a bezpecnostni metadata.

UX

Uzivatel musi videt, ktere pluginy jsou aktivni, co umi, jake maji opravneni a jak je vypnout. Pluginy se nesmi schovavat jako neviditelne zmeny chovani. Pokud plugin prida rizikovou schopnost, musi byt oznacena a potvrzovana.

Implementace

Plugin system nesmi zhorsit start aplikace ani stabilitu. Loader musi izolovat chyby pluginu tak, aby nerozbil Jarvise. Dokumentace kazdeho pluginu musi byt soucasti JUS nebo navazujici plugin dokumentace. Testy musi pokryt registraci a zakladni spusteni plugin toolu.

Mereni kvality

Kvalita se meri poctem pluginu, ktere se nactou bez chyby, schopnosti vypnout plugin, absenci kolizi jmen toolu, jasnosti permission modelu a testovatelnosti.