# Jarvis Voice Upgrade Guide

## Architecture

The upgraded voice system lives under the existing `Voice/` directory. The requested logical package is `voice/`, but this Windows project already had a `Voice` recordings folder; Windows treats those names as the same directory, so imports use `Voice.*` to match the real filesystem casing.

- `Voice/audio/audio_capture.py`: queue-based microphone capture, silence stop, volume callbacks.
- `Voice/audio/vad.py`: WebRTC VAD with RMS fallback.
- `Voice/stt/whisper_engine.py`: faster-whisper wrapper with CUDA auto-detection and CPU fallback.
- `Voice/tts/piper_engine.py`: queue-based Piper TTS, sentence splitting, interruption.
- `Voice/tts/audio_player.py`: interruptible `sounddevice` playback.
- `Voice/wakeword/porcupine_engine.py`: Porcupine wake word listener for `jarvis`.
- `Voice/pipeline/realtime_pipeline.py`: wake -> record -> transcribe -> AI stream -> sentence TTS orchestration.
- `Voice/utils/config.py`: JSON config loader/saver.

The old `interfaces/voice.py` API is preserved as a compatibility layer, so existing GUI code can still call `start_recording`, `stop_recording`, `speech_to_text`, `speak`, and `wake_listener`.

## Installation

Install or update dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

New dependencies:

- `pvporcupine` for offline wake word detection.
- `webrtcvad` for low-latency speech activity detection.

## CUDA Setup

`voice/stt/whisper_engine.py` tries CUDA automatically through `ctranslate2`. With an RTX 3080/3090, keep this in `settings/voice_config.json`:

```json
{
  "whisper_model": "large-v3-turbo",
  "whisper_device": "auto",
  "whisper_compute_type": "float16"
}
```

If CUDA is not available, Jarvis falls back to CPU int8. For lower memory use, change `whisper_model` to `small` or `medium`.

## Wake Word Setup

Wake word uses Porcupine with keyword `jarvis`.

Porcupine may require a Picovoice access key depending on the installed version. Set either:

```powershell
$env:PICOVOICE_ACCESS_KEY="your_key"
```

or add it to `settings/voice_config.json`:

```json
{
  "porcupine_access_key": "your_key"
}
```

Tune sensitivity with:

```json
{
  "wake_word_sensitivity": 0.65
}
```

Higher values detect more easily but can false-trigger more often.

## Microphone And Speaker Config

Use `null` for system defaults:

```json
{
  "microphone_device": null,
  "speaker_device": null
}
```

If the wrong device is used, list devices with:

```powershell
.\.venv\Scripts\python.exe -c "import sounddevice as sd; print(sd.query_devices())"
```

Then put the device index into `settings/voice_config.json`.

## Latency Optimization

Recommended low-latency defaults:

```json
{
  "chunk_ms": 30,
  "silence_timeout": 1.1,
  "partial_transcription_seconds": 1.5,
  "vad_aggressiveness": 2,
  "tts_voice": "cs_CZ-jirka-medium.onnx"
}
```

For a faster assistant:

- Use `large-v3-turbo` on CUDA.
- Reduce `silence_timeout` to `0.8`.
- Keep `chunk_ms` at `20` or `30`.
- Use the local Piper voice already included in the project.

## Troubleshooting

- No wake word: install `pvporcupine`, set `PICOVOICE_ACCESS_KEY` if required, and check the microphone device.
- No transcription: verify `faster-whisper` works and the selected model can be downloaded or is cached.
- Slow transcription: check CUDA availability and reduce the Whisper model size.
- No TTS: confirm `cs_CZ-jirka-medium.onnx` exists in the project root and `piper-tts` is installed.
- GUI freezes: voice work should run on background threads; check logs for a worker crash.

## Running

Start Jarvis as before:

```powershell
.\.venv\Scripts\python.exe -m app.main
```

The existing GUI buttons continue to work:

- Hold `Voice`, speak, release, then click `Send voice`.
- Toggle `Wake Word (Jarvis)` for background wake detection.
- Toggle `Cist odpoved` for spoken streamed answers.
