Security

Security v Jarvisovi znamena lokalni kontrolu, minimalizaci rizika desktop akci, ochranu secrets, auditovatelnost a srozumitelna potvrzeni. Projekt ma silny zaklad v tom, ze je lokalni, ale lokalni desktop agent je sam o sobe citliva schopnost.

Hranice

Projekt nesmi pridavat cloudove sluzby, online API ani nove externi modelove providery. Secrets se neukladaji do repozitare a .env zustava lokalni. Desktop agent ma byt dostupny pouze na 127.0.0.1. Souborove operace maji respektovat workspace nebo explicitne povolene cesty.

Rizika

Hlavni rizika jsou nechtene klikani, psani do spatneho okna, otevreni spatne aplikace, prace se soubory, posilani citlivych dat do modelu, stahovani modelu bez souhlasu a nejasne chyby, ktere vedou uzivatele k nebezpecnym workaroundum. Vision muze spatne detekovat prvek a planner muze navrhnout chybnou akci.

Navrh ochrany

Jarvis potrebuje permission model. Bezpecne akce jsou napr. otevreni bezne aplikace nebo webu. Citlive akce jsou psani textu, klikani, hotkeys, souborove zapisy a spousteni prikazu. Zakazane akce jsou mazani mimo povolene oblasti, zadavani hesel, financni potvrzeni a skryte spousteni neznamych programu. Citlive akce musi mit potvrzeni podle kontextu.

Implementace

Kazdy tool ma mit metadata rizika. Executor ma pred rizikovym krokem zastavit a vyzadat potvrzeni. Audit log ma zaznamenat cil, plan, kroky, vysledek a chyby. Chybove zpravy nesmi obsahovat secrets. Pokud lokalni zavislost chybi, Jarvis ma rict, co chybi, ne zkouset nebezpecnou alternativu.

Mereni kvality

Kvalita security se meri poctem rizikovych akci bez potvrzeni, poctem auditovanych ukolu, absenci secrets v logu, omezenim endpointu na localhost a poctem testu permission modelu.