import json
import os


DATA_DIR = os.path.join(os.getenv("APPDATA", ""), "Jarvis")
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR)
    except Exception as e:
        print(f"Error creating DATA_DIR: {e}")

CHATS_FILE = os.path.join(DATA_DIR, "jarvis_chats.json")
PROFILE_FILE = os.path.join(DATA_DIR, "jarvis_profile.json")


def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf8") as f:
            return json.load(f)
    return {}


def save_json(file, data):
    with open(file, "w", encoding="utf8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def update_profile(profile, message):
    keywords = [
        "programovani",
        "programov\u00e1n\u00ed",
        "python",
        "unity",
        "blender",
        "trading",
        "akcie",
        "investuji",
        "hra",
        "ai",
    ]
    lower = message.lower()
    for word in keywords:
        if word in lower:
            fact = f"uzivatel se zajima o {word}"
            if fact not in profile:
                profile.append(fact)
    return profile
