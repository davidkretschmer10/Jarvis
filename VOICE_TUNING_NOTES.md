# Jarvis Voice Tuning Notes

This guide explains the new cinematic AI voice upgrade based on Piper TTS (`cs_CZ-jirka-medium.onnx`).

## What Was Changed
1. **Model Preloading:** The Piper engine no longer spawns a new Python process for every sentence. It loads the `cs_CZ-jirka-medium.onnx` model directly into memory using the Python bindings (`piper-tts`). This dramatically reduces the initialization latency per sentence.
2. **Cinematic Post-Processing:** We added an audio post-processing pipeline using `librosa` and `scipy.signal` to alter the generated audio in memory. 
    - **Pitch Shifting**: The voice is shifted down a few semitones for a deeper, more resonant feel.
    - **EQ Boost**: We applied an IIR peak filter at around 120Hz to give the voice a cinematic bass punch.
3. **Pacing and Flow:** The engine now supports customizable sentence pauses (`tts_sentence_pause`) to make the speech sound more natural rather than rushing from one sentence to the next.
4. **Volume Control:** We added a `tts_volume` multiplier to avoid clipping while maintaining a loud presence.

## Latency Impact
- **Preloading vs Subprocess**: Moving from subprocess to memory execution saves around **150-300ms** per sentence. 
- **Pitch Shifting Overhead**: Using `librosa` for high-quality pitch shifting adds approximately **10-40ms** of processing time per chunk (depending on chunk length and system load).
- **EQ Overhead**: The `scipy` IIR filter is highly optimized and adds < **2ms** latency.
- **Overall:** The TTS should still start generating and playing audio within ~100-250ms of receiving text, maintaining a real-time interactive feel.

## How to Tune the Voice
All settings are controlled in `settings/voice_config.json`.

* **`tts_rate` (Speed):** 
  - `1.0`: Default Piper speed.
  - `0.90 - 0.95`: Slower, more deliberate, and cinematic.
  - `1.1 - 1.2`: Faster, snappier responses.
* **`tts_pitch` (Tone):** 
  - `0`: Default pitch.
  - `-2 to -3`: Deeper, older, more "Jarvis/Vader" tone.
  - `+1 to +2`: Lighter, more energetic.
* **`tts_sentence_pause` (Pacing):**
  - `0.0`: Immediate, robotic burst mode.
  - `0.1 - 0.25`: Natural pauses between complete thoughts, allowing the user to process or interrupt.
* **`tts_ai_style` (EQ):**
  - `true`: Applies the cinematic 120Hz bass boost for a movie-like trailer voice presence.
  - `false`: Flat EQ, true to the original Jirka recordings.

### Recommended Profiles

**Cinematic Jarvis (Current Default):**
```json
"tts_rate": 0.92,
"tts_pitch": -2,
"tts_sentence_pause": 0.12,
"tts_ai_style": true
```

**Fast/Informational Assistant:**
```json
"tts_rate": 1.05,
"tts_pitch": 0,
"tts_sentence_pause": 0.05,
"tts_ai_style": false
```

**Deep / Imposing AI:**
```json
"tts_rate": 0.85,
"tts_pitch": -4,
"tts_sentence_pause": 0.3,
"tts_ai_style": true
```
