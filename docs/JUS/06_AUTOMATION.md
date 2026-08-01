Automation

Automation vrstva provadi realne akce. Zahrnuje tool registry, executor, desktop agenta, praci se soubory, otevreni aplikaci a webu, psani textu, klikani, klavesy, screenshoty a OCR. Je to oblast s vysokou hodnotou i vysokym rizikem, proto musi byt navrzena konzervativne.

Architektura

Automation zacina klasifikaci intentu v core/intents, pokracuje pres fast command router nebo planner, pouziva run.build_registry() pro nastroje a Executor.run_plan() pro spusteni. Nektere jednodussi akce obsluhuje AutonomousAgent, ktery ma deterministicke planovani a fallback na LLM plan. Desktopove prikazy jsou posilany lokalnimu Flask agentovi pres send_agent_command.

Navrh

Automatizace ma preferovat prime systemove akce. Otevrit aplikaci znamena pouzit open tool nebo lokalni agent, ne klikat na Start menu pres vision. Otevrit web znamena sestavit URL a otevrit ji, ne psat do prohlizece pres klavesy. Vision klikani je posledni moznost.

UX scenare

Bezny scenar je otevreni aplikace, webu nebo provedeni klavesove zkratky. Nejasny scenar je prikaz s vice kandidaty, kde Jarvis ukaze moznosti a pocka. Rizikovy scenar je zapis, klik nebo souborova akce s moznosti skody, kde Jarvis musi vyzadat potvrzeni podle permission modelu.

Implementace

Kazdy tool musi mit jmeno, popis a input schema. Registry odmita nevalidni nebo duplicitni tooly. Executor uklada vystupy do JarvisState, podporuje templaty a stopne plan pri chybe. Automaticka oprava musi byt omezena na registrovane tooly a nikdy nesmi obchazet potvrzeni.

Mereni kvality

Kvalita automatizace se meri uspesnosti ukolu, poctem chybnych otevreni aplikace, poctem nejasnych prikazu, prumernym poctem kroku, prumernou dobou dokonceni, poctem vyzadanych potvrzeni a poctem neuspesnych oprav.