import os
import re
import unicodedata


EXECUTABLE_SKIP_DIRS = {
    "$recycle.bin",
    "appdata",
    "cache",
    "common files",
    "crashdumps",
    "drivers",
    "installer",
    "microsoft",
    "packages",
    "temp",
    "temporary internet files",
    "windows defender",
    "windows kits",
    "windowsapps",
}


def normalize_name(value):
    value = str(value).lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    replacements = {
        "epick": "epic",
        "epic game": "epic games",
        "vscode": "visual studio code",
        "vs code": "visual studio code",
        "chrom": "chrome",
    }
    value = " ".join(value.split())
    for source, target in replacements.items():
        value = re.sub(rf"\b{re.escape(source)}\b", target, value)
    return " ".join(value.split())


def get_start_menu_paths():
    paths = []
    appdata = os.getenv("APPDATA")
    if appdata:
        paths.append(os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs"))
    paths.append(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs")
    return paths


def _add_app(apps, name, path):
    if path:
        name_lower = name.lower()
        path_lower = path.lower()
        exe_name = os.path.basename(path_lower)
        ignored_keywords = ["epicwebhelper", "updater", "crash reporter", "crashreporter", "crash_reporter", "helper"]
        if any(kw in name_lower for kw in ignored_keywords) or any(kw in exe_name for kw in ignored_keywords):
            return

    norm = normalize_name(name)
    if norm and path and norm not in apps:
        apps[norm] = path


def _scan_shortcuts(apps, base):
    if not base or not os.path.isdir(base):
        return
    for root, dirs, files in os.walk(base):
        for file in files:
            lower = file.lower()
            if lower.endswith(".lnk") or lower.endswith(".url") or lower.endswith(".exe"):
                name = os.path.splitext(file)[0]
                _add_app(apps, name, os.path.join(root, file))


def scan_apps():
    apps = {}
    for base in get_start_menu_paths():
        _scan_shortcuts(apps, base)
    return apps


def _should_skip_dir(path):
    parts = {part.lower() for part in path.split(os.sep)}
    return any(part in EXECUTABLE_SKIP_DIRS for part in parts)


def _scan_executables(apps, base, max_depth=5):
    if not base or not os.path.isdir(base):
        return

    base = os.path.abspath(base)
    base_depth = base.count(os.sep)
    for root, dirs, files in os.walk(base):
        if root.count(os.sep) - base_depth >= max_depth:
            dirs[:] = []
        dirs[:] = [d for d in dirs if not _should_skip_dir(os.path.join(root, d))]

        if _should_skip_dir(root):
            continue

        for file in files:
            if file.lower().endswith(".exe"):
                name = os.path.splitext(file)[0]
                _add_app(apps, name, os.path.join(root, file))


def scan_all_apps():
    apps = {}

    desktop_paths = [
        os.path.join(os.path.expanduser("~"), "Desktop"),
        r"C:\Users\Public\Desktop",
    ]
    for desktop in desktop_paths:
        _scan_shortcuts(apps, desktop)

    for base in get_start_menu_paths():
        _scan_shortcuts(apps, base)

    executable_roots = [
        os.getenv("ProgramFiles"),
        os.getenv("ProgramFiles(x86)"),
        os.getenv("LOCALAPPDATA"),
    ]
    for base in executable_roots:
        _scan_executables(apps, base)

    print("SCANNED APPS:", len(apps))
    return apps
