# WINDOWS TOOLS & LOW-LEVEL OPERATIONS AUDIT
**Datum auditu:** 2026-09-09  
**Fáze:** JARVIS FÁZE 9 – Deterministic Windows Tools & Real Verification Kernel  
**Autorita:** Jarvis Safety & Verification Architecture  

---

## 1. Souhrn současného stavu

Při komplexním auditu zdrojového kódu projektu Jarvis bylo identifikováno celkem **24 konkrétních nízkoúrovňových Windows operací** napříč moduly `core/agent.py`, `core/services/application_resolver.py`, `core/verification.py`, `tools/pc_control.py`, `tools/file_manager.py` a `vision/`.

### Klíčová zjištění podle 7 požadovaných otázek:

1. **Které operace používají ToolRegistry:**
   - Souborové operace čtení/zápisu textu (`read_text_file`, `write_text_file`, `list_dir`) v `tools/file_manager.py`.
   - Vstupní desktopové operace (`open_app`, `write_text`, `click`, `press_key`, `hotkey`, `screenshot`, `read_screen`, `smart_click`, `smart_write`, `smart_checkbox`, `close_window`, `confirm_dialog`, `cancel_dialog`, `open_search_result`, `refresh_apps`) v `tools/pc_control.py`.
   - **Chybí v ToolRegistry:** `create_file`, `delete_file`, `copy_file`, `move_file`, `create_directory`, `delete_directory`, `process_exists`, `get_process_info`, `terminate_process`, `window_exists`, `double_click`, `open_path`, `open_url`.

2. **Které používají Executor:**
   - Všechny požadavky vstupující přes `JarvisRuntime.run_task()` jsou směrovány do `Executor`u (`core/executor.py`).
   - Přímé HTTP volání endpointu `/command` v `core/agent.py` **nevyužívá Executor** (zpracovává nízkoúrovňové akce přímo).

3. **Které procházejí SecurityPolicy:**
   - Všechny akce prováděné `Executor`em (kroky plánu) povinně procházejí branou `SecurityPolicy.evaluate()` v `core/executor.py` před jakýmkoliv voláním nástroje.
   - Low-level endpoint `/command open_path` v `core/agent.py` prochází `SecurityPolicy.evaluate()`.
   - Ostatní low-level akce v `/command` (`write`, `click`, `press`, `website`, `open`) mají základní lokální auth `_verify_local_auth()`, ale neprocházejí centrální `SecurityPolicy` v `agent.py`.

4. **Které mají skutečnou deterministickou verifikaci:**
   - `open_app`: `ApplicationVerifier` kontroluje procesní tabulku (`tasklist`) a viditelná okna (`EnumWindows`).
   - `write_file` / `delete_file`: `FileVerifier` kontroluje existenci a velikost/obsah (ale samotné tooly `delete_file` v registry nebyly!).
   - `create_directory` / `delete_directory`: `DirectoryVerifier` kontroluje existenci složky na disku.
   - `open_website`: `BrowserVerifier` kontroluje procesy prohlížečů (`chrome.exe`, `msedge.exe`, `firefox.exe`, `brave.exe`).
   - `click` / `write_text` / `press_key`: `UIInteractionVerifier` vrací korektně `UNKNOWN` (pokud není detekována vision delta).

5. **Které pouze vracejí `ok=True` (bez verifikace v samotném toolu):**
   - `tools/pc_control.py` – většina nástrojů zabalí odpověď `_post_agent` do `{"ok": True, "result": ...}` bezprostředně po síťovém volání bez ověření skutečného dopadu na OS. Spoléhají se až na následný krok v Executoru.
   - `tools/file_manager.py`: `WriteTextFileTool` zapíše soubor a vrátí `{"ok": True, "result": f"Wrote {path}"}`.
   - `core/agent.py`: `write_text` volá `pyautogui.write()` a slepě vrátí `"Text napsan"`.
   - `core/agent.py`: `click` volá `pyautogui.click()` a vrátí `"Kliknuto"`.
   - `core/agent.py`: `open_website` volá `webbrowser.open()` a vrátí `"Web otevren"`.
   - `core/agent.py`: `press_key` volá `pyautogui.press()` a vrátí `"Klavesa stisknuta"`.
   - `tools/pc_control.py`: `CloseWindowTool` pošle `Alt+F4` a vrátí `{"ok": True}` bez ověření zániku okna!

6. **Které mohou představovat bypass:**
   - `/command` v `core/agent.py` s akcí `open` volá `open_program(value)` bez `SecurityPolicy.evaluate()`. Pokud útočník nebo skript zavolá `/command {"action": "open", "value": "powershell"}`, může spustit aplikaci bez high-level autorizace.
   - Cesty v `tools/file_manager.py` používají `_resolve_under_root(ctx, rel_path)`. Pokud uživatel zadá absolutní cestu např. `C:\Users\...\Desktop\doc.txt`, tool selže s chybou `Path escapes workspace`, i když jde o legitimní uživatelský požadavek.
   - V `core/security_policy.py`: cesta nebyla plně kanonikalizována před vyhodnocením scope (nerozvíjely se `%TEMP%`, `%APPDATA%`, tilda `~`).

7. **Které jsou legacy compatibility paths:**
   - `/command` HTTP endpoint v `core/agent.py` pro starší HTTP klienty a staré unit testy (`test_phase2.py`, `test_phase2_6.py`, `test_phase2_7.py`, `test_router.py`).
   - `_post_agent` v `tools/pc_control.py`, který zprostředkovává volání mezi tool vrstvou a Flask serverem v `core/agent.py`.
   - `os.startfile` fallback v `application_resolver.py` a `core/agent.py`, pokud selže `subprocess.Popen` nebo jde o ne-spustitelný soubor/zástupce `.lnk`.

---

## 2. Kompletní tabulka operací

| Operation | File | Tool / Funkce | Security | Verification | Risk | Problem |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `subprocess.Popen([target_path])` | `core/agent.py` (124) | `launch_path()` | Pouze v Executoru; v `/command` částečná | `ApplicationVerifier` (v Executoru) | `LOW` až `HIGH` | V `/command` spouští bez SecurityPolicy, pokud přišlo přes `open` |
| `subprocess.Popen([target_path])` | `core/services/application_resolver.py` (711) | `launch_path()` | Řešeno v nadřazené vrstvě | `ApplicationVerifier` (v Executoru) | `LOW` | Nemá přímou návaznost na verifikaci PID, vrací raw dict |
| `os.startfile(path)` | `core/agent.py` (109, 119, 128, 313) | `launch_path()`, `/command open_path` | Brána v `/command open_path`; v `launch_path` ne | Žádná v agent.py | `HIGH` | Slepé spuštění souborů bez garance vytvoření procesu |
| `os.startfile(path)` | `core/services/application_resolver.py` (694, 706, 720, 726) | `launch_path()` | Řešeno v Executoru | `ApplicationVerifier` | `LOW` | Fallback pro neexistující zástupce `.lnk` nebo nemockované startfile |
| `webbrowser.open(url)` | `core/agent.py` (169) | `open_website()` | Pouze v Executoru | `BrowserVerifier` (v Executoru) | `LOW` | Nevaliduje URL protokol (může teoreticky přijmout `file://` nebo nebezpečné schéma) |
| `pyautogui.write(text)` | `core/agent.py` (150) | `write_text()` | V Executoru | `UNKNOWN` (UIInteractionVerifier) | `LOW` / `MEDIUM` | Vrací `"Text napsan"` bez ověření fokusu nebo cílového pole |
| `pyautogui.click(x, y)` | `core/agent.py` (161, 164) | `click()` | V Executoru | `UNKNOWN` (UIInteractionVerifier) | `LOW` / `MEDIUM` | Žádné ověření, zda klik dopadl do aktivního okna |
| `pyautogui.hotkey(*keys)` | `core/agent.py` (187) | `press_key()` (hotkey) | V Executoru | `UNKNOWN` | `LOW` / `HIGH` | Zkratky jako Alt+F4 zavírají okna, bez kontroly předchozího stavu |
| `pyautogui.press(key)` | `core/agent.py` (193) | `press_key()` | V Executoru | `UNKNOWN` | `LOW` | Slepé odeslání klávesy do OS |
| `pyautogui.screenshot()` | `core/agent.py` (206, 217) | `take_screenshot()`, `read_screen()` | V Executoru (`SAFE`) | `PassThrough` / `SCREEN` | `SAFE` | Zapisuje do disku bez strukturovaného modelu `Observation` |
| `pytesseract.image_to_string()` | `core/agent.py` (223) | `read_screen()` | V Executoru (`SAFE`) | `PassThrough` | `SAFE` | Může selhat, pokud Tesseract chybí |
| `open(path, "r")` | `tools/file_manager.py` (51) | `ReadTextFileTool` (`read_text_file`) | V Executoru (`SAFE`) | `PassThrough` | `SAFE` | Vynucuje `_resolve_under_root` – odmítá platné absolutní cesty uživatele |
| `open(path, "w")` | `tools/file_manager.py` (102) | `WriteTextFileTool` (`write_text_file`) | V Executoru (`MEDIUM`) | `FileVerifier` | `MEDIUM` | Přepisuje soubor bez hash/size verifikace v samotném toolu |
| `os.makedirs()` | `tools/file_manager.py` (101) | `WriteTextFileTool` | V Executoru | `DirectoryVerifier` | `MEDIUM` | Vytváří rodičovské složky bez explicitního oprávnění pro adresář |
| `os.listdir()` | `tools/file_manager.py` (136) | `ListDirTool` (`list_dir`) | V Executoru (`SAFE`) | `PassThrough` | `SAFE` | Pouze workspace scope |
| `subprocess.run(["tasklist", ...])` | `core/verification.py` (73) | `_get_running_processes_windows()` | Jen čtení | Čtení pro verifikaci | `SAFE` | Spolehlivé deterministické čtení procesů |
| `ctypes.windll.user32.EnumWindows` | `core/verification.py` (117) | `_get_visible_window_titles_windows()` | Jen čtení | Čtení pro verifikaci | `SAFE` | Spolehlivé čtení oken přes Win32 API bez vedlejších účinků |
| `subprocess.run(["taskkill", ...])` | `tests/stress/launch_stress.py` (142) | Test cleanup | Pouze v testech | Test assertions | `HIGH` | Není implementován jako tool v `tools/` |
| `winreg.OpenKey` / `QueryValueEx` | `core/services/application_resolver.py` (248) | `scan_registry_app_paths()` | Jen čtení | Interní scan aplikací | `SAFE` | Deterministické prohledání App Paths v registrech |
| `win32com.client.Dispatch("WScript.Shell")` | `core/services/application_resolver.py` (659) | `resolve_shortcut()` | Jen čtení | Interní rezoluce zástupců | `SAFE` | COM rozhraní pro čtení `.lnk` |
| `powershell -NoProfile -Command ...` | `core/services/application_resolver.py` (668) | `resolve_shortcut()` | V resolveru | Fallback pro `.lnk` | `LOW` | Spouští PowerShell subprocess, pokud selže `win32com` |
| `requests.post("/command")` | `tools/pc_control.py` (15) | `_post_agent()` | V Executoru | Delegováno na agenta | `LOW` | Meziprocesová komunikace přes HTTP, vrací `ok=True` i při selhání OS |
| `os.remove` | `tests/` | Test fixtures | N/A | N/A | `SAFE` | V produkčních toolech chyběl dedikovaný `delete_file` tool |
| `shutil.copy` / `shutil.move` | `tests/stress/chaos_test.py` | Chaos testování | N/A | N/A | `SAFE` | V produkčních toolech chyběl dedikovaný `copy_file`/`move_file` tool |

---

## 3. Identifikované mezery a doporučení k implementaci

1. **Sjednocení Windows Tools pod jednotnou strukturu:**
   - Zavést autoritativní sadu deterministických nástrojů v `tools/windows_tools.py` (nebo rozšířit `tools/file_manager.py` a `tools/pc_control.py` s plnou registrací v `ToolRegistry`):
     - `launch_application` (alias `open_app`)
     - `open_url` (alias `open_website`)
     - `open_path`
     - `create_file`, `read_file` (alias `read_text_file`), `write_file` (alias `write_text_file`), `copy_file`, `move_file`, `delete_file`
     - `create_directory`, `delete_directory`
     - `process_exists`, `get_process_info`, `terminate_process`
     - `window_exists`, `close_window`
     - `click`, `double_click`, `type_text` (alias `write_text`), `press_key`
     - `screenshot` (vracející strukturovaný `Observation` typu `SCREEN`)
2. **Kanonická normalizace cest:**
   - Zavést `canonical_windows_path(path_str, workspace_root=None)`:
     - Rozvinutí `%ENV_VARS%` (`os.path.expandvars`)
     - Rozvinutí `~` (`os.path.expanduser`)
     - Vyřešení relativních cest vůči workspace nebo cwd
     - Kanonické vyřešení symlinků a `..` (`Path.resolve()`)
     - Normalizace velikosti písmen na Windows pro deterministické porovnávání.
   - Propojit kanonickou cestu do `SecurityPolicy.evaluate()` a všech file nástrojů (žádné porovnávání před normalizací!).
3. **Rozšíření Verifier Registry:**
   - Přidat `ProcessVerifier` (ověřování PID, spuštění procesu a zániku po `terminate_process`).
   - Přidat `WindowVerifier` (ověřování existence a zániku okna po `close_window`).
   - Rozšířit `FileVerifier` o verifikaci `copy_file` (zdroj + cíl existují, velikost sedí) a `move_file` (zdroj neexistuje, cíl existuje).
4. **Idempotence & Inteligentní Retry:**
   - Před opakovaným pokusem u destruktivních akcí (`delete_file`, `terminate_process`, `launch_application`) nejdříve provést observaci aktuálního stavu. Pokud již cíl zanikl (u delete) nebo proces běží (u launch), neprovádět slepý re-run, ale rovnou vyhodnotit jako `VERIFIED`.
5. **Zachování 100% zpětné kompatibility:**
   - Všechny stávající názvy nástrojů (`open_app`, `write_text_file`, `read_text_file`, `open_website`, `click`, atd.) zůstávají plně funkční jako aliasy nebo přímé implementace.
   - Všechny stávající testy (272 testů) musí zůstat zelené.
