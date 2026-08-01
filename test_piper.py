from Voice.utils.config import load_voice_config
from Voice.tts.piper_engine import PiperEngine
import time

print("Loading config...")
config = load_voice_config()

print("Initializing PiperEngine...")
start_init = time.time()
engine = PiperEngine(config)
print(f"Init took {time.time() - start_init:.2f}s")

print("Synthesizing and playing test sentence...")
text = "Ahoj, já jsem Jarvis. Můj hlasový modul byl úspěšně vylepšen."
engine.speak(text)

print("Waiting for generation and playback...")
time.sleep(5)
engine.shutdown()
print("Done.")
