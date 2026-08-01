# Jarvis Voice System Analysis

## Current Architecture

The original voice stack is concentrated in `interfaces/voice.py` and is called directly from `interfaces/gui_controller.py`.

Current flow:

1. GUI button calls `GuiController.start_recording()`.
2. `interfaces.voice.start_recording()` opens a `sounddevice.InputStream`.
3. Audio blocks are normalized, lightly gated, and stored in a global `audio_buffer`.
4. `stop_recording()` stops the stream.
5. `speech_to_text()` waits until recording stops, writes `Voice/user_voice_*.wav`, then calls `faster_whisper.WhisperModel("small", device="cpu", compute_type="int8")`.
6. GUI sends the final text to the existing chat/agent routing.
7. AI response streams from Ollama.
8. Sentence-like chunks are sent to `interfaces.voice.speak()`.
9. `speak()` enqueues text and `_play_text()` starts Piper as a subprocess for each queued item.

Wake word flow:

1. GUI wake checkbox starts a daemon thread.
2. `interfaces.voice.wake_listener()` uses `speech_recognition`.
3. Audio is sent to Google recognition with `language="cs-CZ"`.
4. If recognized text contains `jarvis`, the GUI starts recording.

Voice-related files:

- `interfaces/voice.py`: recording, preprocessing, Whisper STT, Piper TTS, wake word.
- `interfaces/gui_controller.py`: voice state, threading, AI response streaming, wake toggle.
- `interfaces/gui/chat_widget.py`: voice buttons, wake checkbox, read-answer checkbox, waveform hookup.
- `interfaces/gui/voice_widget.py`: waveform widget and continuous voice chat buttons.
- `requirements.txt`: `faster-whisper`, `piper-tts`, `sounddevice`, `soundfile`, `noisereduce`, `librosa`, `SpeechRecognition`.

## Weaknesses

- Voice logic is monolithic and global; recorder state, STT state, TTS queue, and wake listener share one file.
- Wake word is not offline because it depends on Google SpeechRecognition.
- Wake word listener cannot be stopped cleanly once started.
- STT uses `small` on CPU only, so recognition quality and latency are limited on RTX-class hardware.
- There is no proper realtime transcription loop; transcription runs only after the whole recording is finished.
- TTS starts a Piper subprocess per utterance and blocks on `sd.wait()`.
- There is no speech interruption support; user speech cannot stop ongoing playback.
- GUI and voice threads communicate through direct calls and globals instead of explicit thread-safe queues/callbacks.
- `voice_conversation_loop()` duplicates the chat-response streaming logic from `send_voice()`.
- Recording and transcription are tightly coupled to files, adding disk latency.

## Bottlenecks And Latency Issues

- Whisper model is loaded lazily but fixed to CPU int8.
- Whole-recording transcription prevents partial updates.
- Noise reduction is applied to the entire recording before transcription, which can add noticeable delay.
- Piper subprocess startup per sentence increases response-to-audio latency.
- Wake word recognition with cloud STT is slower than a dedicated keyword detector.
- `speech_to_text()` busy-waits with `time.sleep(0.1)` while recording is active.

## Threading Risks

- Global mutable state in `interfaces/voice.py` is not protected by locks.
- Wake listener daemon threads can stack if the checkbox is toggled repeatedly.
- TTS playback is serialized through a queue, but there is no `stop()` or cancellation event.
- GUI-triggered operations rely on daemon threads with limited lifecycle management.

## Upgrade Notes

The requested logical package name was `voice/`. This project already contained a Windows folder named `Voice` for recordings. Because Windows treats `Voice` and `voice` as the same folder, the upgraded package is stored in that existing `Voice/` directory and code imports it as `Voice.*`.

## Upgrade Opportunities

- Split voice into dedicated modules: audio capture, VAD, STT, TTS, wake word, realtime orchestration, config.
- Use `large-v3-turbo` or `large-v3` with CUDA when available and CPU fallback when not.
- Add WebRTC VAD for frame-level speech detection with an RMS fallback.
- Add offline Porcupine wake word support with configurable sensitivity.
- Add a realtime pipeline that handles wake detection, recording, transcription, AI streaming, sentence-based TTS, and interruption.
- Keep compatibility wrappers so existing GUI methods continue to work.
- Add JSON configuration in `settings/voice_config.json`.
- Add tests that validate module construction and control flow without requiring real microphone/audio hardware.
