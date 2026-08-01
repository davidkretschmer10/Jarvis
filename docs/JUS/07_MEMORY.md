Memory

Memory system umoznuje Jarvisovi pamatovat si chaty, volbu modelu a jednoduche profilove fakty. Aktualni implementace je v core/memory.py a uklada JSON soubory do %APPDATA%/Jarvis. Pamet je lokalni a nesmi byt synchronizovana do cloudu.

Ucel

Pamet ma zlepsovat kontinuitu. Jarvis ma vedet, v jakem chatu uzivatel je, jake jsou posledni zpravy a ktere profilove fakty mohou zlepsit odpoved. Pamet nesmi byt skryta magie. Uzivatel musi mit moznost ji videt, upravit a smazat.

Architektura

CHATS_FILE a PROFILE_FILE jsou hlavni uloziste. load_json a save_json provadi cteni a zapis. GuiController nacita chaty, migruje starsi format listu na dict s modelem, vytvari vychozi chat a uklada zmeny. update_profile dnes pridava jednoduche fakty na zaklade klicovych slov.

UX

Memory panel dnes ukazuje souhrn poctu profilu, chatu a aktualni chat. Cilovy UX ma umoznit plnou spravu: seznam faktu, editaci, mazani, vysvetleni zdroje faktu a export/import. Jarvis musi pri pouziti pameti jednat prirozene a nevyvolavat pocit sledovani.

Implementace

Pamet musi byt verzovana schematem, aby bylo mozne bezpečně migrovat format. Kazdy zapis musi byt atomicky nebo aspon odolny proti poskozeni JSON. Profilove fakty musi mit text, zdroj, datum pridani a volitelne datum aktualizace. Citlive informace se nemaji pridavat automaticky bez explicitniho souhlasu.

Mereni kvality

Kvalita se meri poctem uspesnych migraci, absenci poskozenych JSON souboru, presnosti profilovych faktu, poctem smazatelnych polozek a schopnosti uzivatele pochopit, proc Jarvis neco vi.