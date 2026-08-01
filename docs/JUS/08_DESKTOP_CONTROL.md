Desktop Control

Desktop control je schopnost Jarvise ovladat Windows. Projekt obsahuje lokalniho agenta v core/agent.py, tooly v tools, PC control helpers a komunikaci pres lokalni HTTP endpoint http://127.0.0.1:5000/command. Tato oblast musi byt bezpecna, predvidatelna a auditovatelna.

Ucel

Desktop control umoznuje otevrit aplikace, weby, psat text, klikat, stisknout klavesy, udelat screenshot a cist obrazovku. Hodnota spociva v tom, ze uzivatel muze rict cil a Jarvis provede mechanickou cast prace.

Architektura

app/main.py startuje lokalniho agenta jako subprocess. ai.engine.send_agent_command posila JSON s action a value. AutonomousAgent.execute mapuje synonymni akce na jednotne action hodnoty. Tool vrstva muze volat desktopove funkce pres registry. Vision a OCR se pouzivaji pro screen context a opravne scenare.

UX

Desktop akce musi mit jasnou signalizaci. Pred zacatkem ma Jarvis rict, co bude delat. Behem akce ma task progress ukazovat krok. Po dokonceni ma vratit vysledek. Pri riziku musi vyzadat potvrzeni. Pri selhani musi rict, co se nepovedlo a zda potrebuje pomoc.

Bezpecnost

Desktop control nesmi byt vystaven mimo lokalni stroj. Endpoint ma bezet pouze lokálně. Budouci permission model musi rozlisovat bezpecne akce, citlive akce a zakazane akce. Operace jako mazani souboru, zadavani hesel, potvrzovani plateb nebo zmeny systemove konfigurace musi byt chranene.

Mereni kvality

Kvalita se meri uspesnosti otevreni aplikaci, spravnosti mapovani nazvu, latenci agent volani, poctem nechtenych akci, poctem potvrzeni a stabilitou agent procesu.