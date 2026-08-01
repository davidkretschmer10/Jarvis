Planner

Planner prevadi uzivatelsky cil na vykonatelny plan. V projektu existuji dve vrstvy: rychle deterministicke a intent routovaci cesty pro bezne prikazy a obecnejsi Planner v core/planner.py, ktery generuje JSON kroky nad registrovanymi tooly. Executor potom kroky spousti a aktualizuje stav.

Ucel

Planner ma chranit uzivatele pred chaotickym jednanim asistenta. Misto jedne velke neurcite odpovedi vytvari male kroky s popisem. Kazdy krok musi pouzit znamy tool a mit validni input. Planner nesmi vymyslet neexistujici nastroje ani pouzivat vision, kdyz existuje prima cesta.

Architektura

ToolRegistry popisuje dostupne nastroje. Planner.build_prompt vlozi seznam toolu, pravidla, priklady a cil. Planner.plan se pokusi vystup vyparsovat jako JSON pole, validuje prazdne plany a pro webove pozadavky odmita UI/Vision kroky. Executor bere kroky, renderuje templaty ze sdileneho stavu, spousti tool a uklada vysledky.

UX

Plan ma byt viditelny v task progress panelu. Uzivatel ma videt popis kroku, aktualni stav a vysledek. Pri nejasnosti musi Jarvis pozadat o upresneni. Pri selhani musi vysvetlit, ktery krok selhal a zda se pokusi o opravu.

Implementace

Planner musi vystupovat pouze ve strukturovanem JSON formatu. Validace musi byt prisna, protoze spatny plan muze zpusobit spatnou desktop akci. Deterministicke prikazy maji prednost pred LLM planem, pokud jasne pokryji cil. Planner nesmi pridavat nove modely ani cloudove sluzby.

Mereni kvality

Kvalita planneru se meri procentem validnich planu, procentem dokoncenych ukolu, poctem oprav po selhani, poctem dotazu na uzivatele pri nizke jistote a poctem pripadu, kdy planner zvolil prime nastroje misto vision klikani.