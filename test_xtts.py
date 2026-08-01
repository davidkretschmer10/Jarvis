import time
import torch
from TTS.api import TTS

print("CUDA available:", torch.cuda.is_available())

print("Loading XTTS model...")
start_load = time.time()

tts = TTS(
    model_name="tts_models/multilingual/multi-dataset/xtts_v2",
    gpu=True
)

load_time = time.time() - start_load
print(f"Model loading took {load_time:.2f} seconds")

print("Generating speech...")
start_gen = time.time()

tts.tts_to_file(
    text="Ahoj Davide. Já jsem Jarvis.",
    file_path="output.wav",
    speaker="Craig",
    language="cs"
)

gen_time = time.time() - start_gen
print(f"Audio generation took {gen_time:.2f} seconds")

print("Hotovo - output.wav created")
