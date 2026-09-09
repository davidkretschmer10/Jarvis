# DETERMINISTIC WINDOWS TOOLS & REAL VERIFICATION KERNEL
**Architektonický standard systému Jarvis (Fáze 9)**

---

## 1. Přehled architektury

Tento dokument popisuje deterministickou vrstvu pro ovládání operačního systému Windows, kanonickou normalizaci cest, autoritativní bezpečnostní bránu `SecurityPolicy`, exekuční smyčku a verifikační kernel.

Architektura striktně dodržuje princip **One True Runtime** a invariant **Execution Safety Kernel**:

```
                 USER / CLIENT
         (GUI / Voice / CLI / HTTP / Autonomous)
                      ↓
                JarvisRuntime
                      ↓
               RequestContext
                      ↓
             Authoritative Router
                      ↓
            Planner / Fast Command
                      ↓
                   Executor
                      ↓
     Canonical Path Normalization & Resolving
                      ↓
                SecurityPolicy
               ├── ALLOW
               ├── CONFIRM
               └── DENY (Terminal Failure)
                      ↓
           Deterministic Windows Tool
                      ↓
             Observe & Verify (Kernel)
               ├── VERIFIED
               ├── FAILED → Safe Replan / Repair
               ├── UNKNOWN (Never false success)
               └── NOT_APPLICABLE
                      ↓
                Action Audit
                      ↓
               RequestResult
```

---

## 2. Autoritativní deterministické nástroje (Windows Tools)

Každý nástroj deklaruje schopnost (`ToolCapability`), míru rizika (`ActionRisk`), timeout a validační schéma argumentů (`input_schema`). Všechny operace jsou deterministické a podporují idempotenci.

### Souborové operace (`tools/file_manager.py`)
- **`create_file`**: Vytvoří soubor s volitelným obsahem. Automaticky vytváří chybějící rodičovské složky.
- **`read_file`** (alias `read_text_file`): Přečte textový obsah souboru s limitem znaků.
- **`write_file`** (alias `write_text_file`): Zapíše obsah do souboru. Pokud soubor existuje a leží mimo dočasný adresář, vyžaduje potvrzení.
- **`copy_file`**: Zkopíruje soubor ze `source` do `destination`. Zachovává metadata.
- **`move_file`**: Přesune/přejmenuje soubor ze `source` do `destination`.
- **`delete_file`**: Smaže soubor. **Idempotentní**: pokud soubor již neexistuje, akce okamžitě uspěje s příznakem `already_deleted: True`.
- **`create_directory`**: Vytvoří adresář včetně rodičovských složek (`exist_ok=True`).
- **`delete_directory`**: Smaže adresář. **Idempotentní**: uspěje, pokud adresář již neexistuje.
- **`list_dir`**: Vypíše obsah složky.

### Procesy a správa oken (`tools/pc_control.py`)
- **`launch_application`** (alias `open_app`): Spustí aplikaci přes `ApplicationResolver` nebo přímý executable path.
- **`process_exists`**: Deterministicky ověří, zda proces běží podle jména nebo PID.
- **`get_process_info`**: Vrátí podrobné informace o běžících procesech (PID, Image Name, paměť).
- **`terminate_process`**: Ukončí proces podle PID nebo jména (`taskkill /F`). **Idempotentní**: pokud proces již neběží, uspěje s `already_terminated: True`.
- **`window_exists`**: Ověří existenci viditelného okna podle titulku přes Win32 API (`EnumWindows`).
- **`close_window`**: Zavře aktivní nebo cílové okno.

### Periferní a síťové operace (`tools/pc_control.py`)
- **`open_url`** (alias `open_website`): Validuje protokol (`http://`, `https://`) a otevře webový prohlížeč. Nikdy nespouští libovolné shell příkazy.
- **`open_path`**: Nízkoúrovňový chráněný start souboru podléhající přísné kontrole `SecurityPolicy`.
- **`click`**, **`double_click`**: Simulace kliknutí myší (s volitelnými souřadnicemi x, y).
- **`type_text`** (alias `write_text`): Simulace psaní textu přes klávesnici.
- **`press_key`**, **`hotkey`**: Simulace stisku kláves a klávesových zkratek.
- **`screenshot`**: Vytvoří snímek obrazovky a vrátí strukturovaný objekt `Observation(type=SCREEN)`.

---

## 3. Kanonická normalizace cest (`utils/path_utils.py`)

Bezpečnostní politika i souborové nástroje pracují **výhradně s kanonikalizovanými cestami**:

$$\text{raw input} \longrightarrow \text{expandvars} \longrightarrow \text{expanduser} \longrightarrow \text{resolve} \longrightarrow \text{canonical path} \longrightarrow \text{SecurityPolicy}$$

Pravidla normalizace:
1. **Rozvinutí proměnných prostředí**: `%APPDATA%`, `%TEMP%`, `%USERPROFILE%`, `%WINDIR%`, `%LOCALAPPDATA%`.
2. **Rozvinutí uživatelské tildy**: `~` se rozvine na domovský adresář uživatele.
3. **Relativní cesty**: Relativní cesty se vyhodnotí vůči `workspace_root` (nebo cwd).
4. **Řešení traversal útoků**: Výrazy typu `..\..\Windows\System32` jsou normalizovány přes `Path.resolve()` na reálnou cílovou cestu na disku.
5. **Normalizace velikosti písmen**: Na Windows jsou cesty porovnávány bez ohledu na velikost písmen.

---

## 4. Bezpečnostní brána (`core/security_policy.py`)

Před spuštěním kteréhokoliv kroku provede `Executor` striktní kontrolu:

1. **Striktní hierarchie rizik**:
   $$\text{SAFE (0)} < \text{LOW (1)} < \text{MEDIUM (2)} < \text{HIGH (3)} < \text{CRITICAL (4)}$$
2. **Resource Scopes**:
   - `SYSTEM_PROTECTED`: `C:\Windows`, `System32`, `Program Files`, `ProgramData`, kořeny disků (`C:\`). Jakýkoliv zápis nebo mazání je striktně **`DENY`**. Čtení vyžaduje potvrzení.
   - `TEMPORARY`: `%TEMP%`, `%TMP%`. Vytváření, čtení, zápis i mazání jsou **`ALLOW`** (pro bezpečné testy a mezipaměť).
   - `USER_WORKSPACE`, `USER_DOCUMENTS`: Běžný uživatelský scope. Zápisy jsou povoleny, přepisy a mazání vyžadují potvrzení.
   - `APP_DATA`, `UNKNOWN`.
3. **Ochrana systémových procesů**:
   - Ukončení procesů jako `csrss.exe`, `lsass.exe`, `smss.exe`, `services.exe`, `wininit.exe`, `svchost.exe` je striktně **`DENY`**.
4. **Destruktivní příkazy v shellu**:
   - Vzory typu `rmdir /s /q c:`, `format`, `del /f /s`, `shutdown` jsou okamžitě **`DENY`**.

---

## 5. Verification Kernel (`core/verification.py`)

Základní pravidlo: **Tool execution success != Verification success**.

Samotný návrat `{"ok": True}` z nástroje nepotvrzuje, že se stav světa změnil. O výsledku rozhoduje nezávislý `StepVerifierRegistry`:

| Verifier | Pokrývané nástroje | Způsob deterministického ověření |
| :--- | :--- | :--- |
| **`FileVerifier`** | `create_file`, `write_file`, `delete_file`, `copy_file`, `move_file` | Kontrola existence na disku, ověření velikosti a obsahu. U `delete` ověření nepřítomnosti. U `copy` existence zdroje i cíle a shody velikostí. U `move` existence cíle a nepřítomnosti zdroje. |
| **`DirectoryVerifier`** | `create_directory`, `delete_directory` | Kontrola existence/nepřítomnosti složky na disku přes `os.path.isdir`. |
| **`ProcessVerifier`** | `process_exists`, `terminate_process`, `get_process_info` | Kontrola procesní tabulky (`tasklist`) a Win32 `OpenProcess` / PID exit kódu. U `terminate` ověření zániku procesu. |
| **`WindowVerifier`** | `window_exists`, `close_window` | Inspekce viditelných oken přes `ctypes.windll.user32.EnumWindows`. U `close` ověření zániku okna. |
| **`ApplicationVerifier`** | `launch_application`, `open_app` | Detekce vytvoření nového procesu nebo otevření nového okna. |
| **`BrowserVerifier`** | `open_url`, `open_website` | Detekce aktivního procesu prohlížeče (`chrome.exe`, `msedge.exe`, `firefox.exe`, `brave.exe`). |
| **`UIInteractionVerifier`** | `click`, `double_click`, `type_text`, `press_key` | Pokud není k dispozici ověřená OCR/Vision delta, stav je striktně **`UNKNOWN`** (nikdy falešné `VERIFIED`). |
| **`PassThroughVerifier`** | Read-only nástroje (`system_info`, `get_time`, `read_file`, atd.) | Vrací **`NOT_APPLICABLE`**. |

---

## 6. Idempotence a inteligentní pre-retry

Při selhání destruktivních operací (`delete_file`, `delete_directory`, `terminate_process`) Executor před provedením dalšího pokusu provede **pre-check stavu světa**:
- Pokud cílový soubor nebo proces již ve skutečnosti neexistuje (např. z důvodu timeoutu odpovědi sítě, ačkoliv OS akci provedl), akce je okamžitě označena jako `VERIFIED` a redundantní destruktivní volání je přeskočeno.

---

## 7. Bezpečná strategie testování Windows

Při testování v reálném prostředí Windows platí striktní pravidla:
- Testy souborů probíhají výhradně v `%TEMP%` v izolovaných složkách vytvořených přes `tempfile.mkdtemp()`.
- Testy procesů spouštějí výhradně neškodný vlastní subprocess (`sys.executable -c "import time; time.sleep(30)"`).
- Test cleanup probíhá v bloku `finally` / `tearDown`, takže žádné procesy nezůstávají viset na pozadí ani při selhání testu.
- Je striktně zakázáno modifikovat produkční systémové registry, mazat systémové soubory nebo volat `shutdown`.
