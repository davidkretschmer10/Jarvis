import os
import subprocess
import sys
import urllib.request

print("===================================")
print("        JARVIS SYSTEM SETUP")
print("===================================")

def run(cmd):
    subprocess.run(cmd, shell=True)

def download(url, name):
    print(f"Stahuji {name}...")
    urllib.request.urlretrieve(url, name)

# ------------------------
# Python knihovny
# ------------------------

print("\nInstaluji Python knihovny...")

run(f"{sys.executable} -m pip install --upgrade pip")
run(f"{sys.executable} -m pip install -r requirements.txt")

print("Python knihovny hotovo")

# ------------------------
# Tesseract OCR
# ------------------------

tesseract = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

if not os.path.exists(tesseract):

    url = "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.3.0.20221214.exe"

    download(url,"tesseract_installer.exe")

    print("Spouštím instalaci Tesseract")

    run("tesseract_installer.exe")

else:

    print("Tesseract už je nainstalovaný")

# ------------------------
# Ollama AI
# ------------------------

ollama = r"C:\Users\Public\ollama"

if not os.path.exists(ollama):

    url = "https://ollama.com/download/OllamaSetup.exe"

    download(url,"ollama_installer.exe")

    print("Spouštím instalaci Ollama")

    run("ollama_installer.exe")

else:

    print("Ollama už existuje")

# ------------------------
# Docker
# ------------------------

docker = r"C:\Program Files\Docker"

if not os.path.exists(docker):

    url = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"

    download(url,"docker_installer.exe")

    print("Spouštím instalaci Docker")

    run("docker_installer.exe")

else:

    print("Docker už existuje")

# ------------------------
# AI model
# ------------------------

print("\nStahuji AI model")

run("ollama pull llama3")

# ------------------------
# Spuštění serveru
# ------------------------

print("\nSpouštím Jarvis server")

run(f"{sys.executable} -m app.main")

# ------------------------
# Spuštění agenta
# ------------------------

print("\nSpouštím Jarvis agent")

run(f"{sys.executable} -m core.agent")

print("\n===================================")
print("       JARVIS SYSTEM READY")
print("===================================")