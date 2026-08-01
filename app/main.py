import subprocess
import time
import requests
import sys
import multiprocessing


# =========================
# START OLLAMA
# =========================

def start_ollama():

    try:
        requests.get("http://localhost:11434", timeout=5)
        print("Ollama already running")
        return
    except:
        pass

    print("Starting Ollama...")

    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    time.sleep(5)


# =========================
# START AGENT
# =========================

def start_agent():

    print("Starting Jarvis Agent...")

    subprocess.Popen(
        [sys.executable, "-m", "core.agent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    time.sleep(2)


# =========================
# MAIN
# =========================

def main():

    print("Starting Jarvis system")

    start_ollama()

    start_agent()

    print("Starting Jarvis GUI...")

    import app.gui

    print("Jarvis started")


# =========================
# ENTRY
# =========================

if __name__ == "__main__":

    multiprocessing.freeze_support()

    if len(sys.argv) > 1:

        if sys.argv[1] == "agent":

            from core import agent
            agent.app.run(port=5000, use_reloader=False)
            sys.exit()

    main()