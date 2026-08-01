# Jarvis Voice Modernization

## Summary

The voice subsystem is now a local, modular stack with one orchestration point:
`Voice.voice_manager.VoiceManager`.

On Windows the existing `Voice/` directory and the requested `voice/` directory
resolve to the same path on the case-insensitive filesystem. The implementation
therefore lives in `Voice/` and exposes a lowercase `voice` alias at runtime for
architectural compatibility.

## Changed Files

- `interfaces/voice.py` - compatibility facade now delegates to `VoiceManager`.
- `interfaces/gui_controller.py` - voice transcription is off the GUI thread,
  voice chat no longer blocks while responses are speaking, and streamed TTS is
  used for voice replies.
- `settings/voice_config.json` - migrated to a nested `voice` configuration.
- `Voice/__init__.py` - exports `VoiceManager` and registers the lowercase alias.

## New Files

- `Voice/config.py`
- `Voice/microphone.py`
- `Voice/vad.py`
- `Voice/whisper_engine.py`
- `Voice/interruption.py`
- `Voice/streaming.py`
- `Voice/tts_engine.py`
- `Voice/audio_output.py`
- `Voice/wake_word.py`
- `Voice/voice_manager.py`

## Dependencies

No cloud dependencies were added. The implementation uses the existing local
dependencies already listed in `requirements.txt`:

- `faster-whisper`
- `piper-tts`
- `sounddevice`
- `soundfile`
- `numpy`
- `scipy`
- `webrtcvad`
- `noisereduce` optional at runtime
- `librosa` optional for TTS pitch processing

## Architecture

`VoiceManager` owns the full local voice lifecycle:

- microphone capture
- VAD-based speech start/end detection
- optional local noise reduction
- Faster-Whisper transcription
- interruptible TTS queue
- streaming LLM text to TTS
- audio playback synchronization
- wake-word placeholder for a future local backend

The GUI only calls the compatibility facade in `interfaces.voice`; it no longer
owns voice internals.

## Configuration

Voice settings are under `voice` in `settings/voice_config.json`:

- `enabled`
- `stt_model`
- `tts_backend`
- `language`
- `sample_rate`
- `device`
- `input_device`
- `output_device`
- `vad_enabled`
- `streaming_enabled`
- `interrupt_enabled`
- `noise_reduction`
- `volume`
- `speed`

Legacy flat keys such as `whisper_model`, `tts_voice`, and `microphone_device`
are still accepted by the loader.

## Migration Notes

- Czech remains the default language.
- Piper is the default TTS backend.
- `ChatterboxTTS` and `FutureTTS` are backend placeholders behind the same
  `BaseTTS` interface.
- Wake word is isolated and disabled by default because the project must remain
  fully local and must not require API keys.
- Existing imports from `interfaces.voice` remain compatible.
