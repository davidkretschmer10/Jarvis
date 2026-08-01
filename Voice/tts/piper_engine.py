from __future__ import annotations

import logging
import queue
import re
import threading
import time
from typing import Iterable, Optional

import numpy as np

try:
    from piper.voice import PiperVoice
except ImportError:
    PiperVoice = None

from Voice.audio.audio_capture import normalize_audio
from Voice.tts.audio_player import AudioPlayer
from Voice.utils.config import VoiceConfig

LOGGER = logging.getLogger(__name__)

SENTENCE_RE = re.compile(r"([^.!?\n]+[.!?\n]+)")
DEFAULT_MAX_TTS_CHARS = 180


def split_sentences(buffer: str, max_chars: int = DEFAULT_MAX_TTS_CHARS) -> tuple[list[str], str]:
    sentences: list[str] = []
    consumed = 0
    for match in SENTENCE_RE.finditer(buffer):
        text = match.group(1).strip()
        if text:
            sentences.extend(split_for_tts(text, max_chars=max_chars))
        consumed = match.end()
    return sentences, buffer[consumed:]


def split_for_tts(text: str, max_chars: int = DEFAULT_MAX_TTS_CHARS) -> list[str]:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    chunks: list[str] = []
    current = ""
    tokens = re.split(r"(\s+|[,;:]\s*)", cleaned)
    for token in tokens:
        if not token:
            continue
        candidate = f"{current}{token}" if current else token.lstrip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current.strip():
            chunks.append(current.strip())
        current = token.lstrip()
    if current.strip():
        chunks.append(current.strip())
    return chunks


class PiperEngine:
    """Queue-based Piper TTS with sentence playback, memory preloading, and cinematic post-processing."""

    def __init__(self, config: VoiceConfig):
        self.config = config
        self.player = AudioPlayer(config.speaker_device)
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._stop_event = threading.Event()
        
        # Preload model into memory to avoid subprocess overhead
        self.voice = None
        if PiperVoice is not None:
            LOGGER.info("Preloading Piper model: %s", self.config.tts_voice)
            try:
                self.voice = PiperVoice.load(self.config.tts_voice)
            except Exception as exc:
                LOGGER.error("Failed to preload Piper model: %s", exc)
        else:
            LOGGER.error("piper-tts is not installed. Synthesis will fail.")

        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def speak(self, text: str) -> None:
        text = self._normalize_text(text)
        if text:
            for chunk in split_for_tts(
                text,
                max_chars=getattr(self.config, "tts_max_chunk_chars", DEFAULT_MAX_TTS_CHARS),
            ):
                self._queue.put(chunk)

    def speak_stream(self, chunks: Iterable[str]) -> str:
        buffer = ""
        full = ""
        for chunk in chunks:
            if self._stop_event.is_set():
                break
            full += chunk
            buffer += chunk
            sentences, buffer = split_sentences(
                buffer,
                max_chars=getattr(self.config, "tts_max_chunk_chars", DEFAULT_MAX_TTS_CHARS),
            )
            for sentence in sentences:
                self.speak(sentence)
        if buffer.strip():
            self.speak(buffer.strip())
        return full

    def interrupt(self) -> None:
        self._stop_event.set()
        self.player.stop()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        self._stop_event.clear()

    def shutdown(self) -> None:
        self._queue.put(None)

    def synthesize(self, text: str) -> np.ndarray:
        text = self._normalize_text(text)
        if not text or not self.voice:
            return np.array([], dtype="float32")

        start_time = time.perf_counter()
        
        # Direct memory synthesis
        audio_chunks = []
        try:
            from piper.config import SynthesisConfig
            syn_config = SynthesisConfig(length_scale=self.config.tts_rate)
            for chunk in self.voice.synthesize(text, syn_config=syn_config):
                audio_chunks.append(chunk.audio_float_array)
        except Exception as exc:
            LOGGER.warning("Piper generation failed: %s", exc)
            return np.array([], dtype="float32")
            
        if not audio_chunks:
            return np.array([], dtype="float32")
            
        audio = np.concatenate(audio_chunks)
        gen_time = (time.perf_counter() - start_time) * 1000
        LOGGER.debug("TTS Gen latency: %.2f ms | Queue size: %d", gen_time, self._queue.qsize())
        
        return self._post_process_audio(audio)

    def _post_process_audio(self, audio: np.ndarray) -> np.ndarray:
        """Apply cinematic EQ, compression, and optional pitch shifting."""
        if not len(audio):
            return audio
            
        # Optional: Pitch shifting using librosa if configured
        if self.config.tts_pitch != 0:
            try:
                import librosa
                audio = librosa.effects.pitch_shift(
                    audio, 
                    sr=self.voice.config.sample_rate if self.voice else 22050, 
                    n_steps=self.config.tts_pitch, 
                    bins_per_octave=12
                )
            except Exception as exc:
                LOGGER.debug("Pitch shift failed/skipped: %s", exc)

        if getattr(self.config, "tts_ai_style", False):
            # Cinematic EQ: Low frequency boost (bass)
            try:
                import scipy.signal as signal
                sr = self.voice.config.sample_rate if self.voice else 22050
                b, a = signal.iirpeak(120 / (sr / 2), 1.5)
                bass_boost = signal.lfilter(b, a, audio)
                audio = audio + bass_boost * 0.3
            except Exception as exc:
                LOGGER.debug("EQ failed/skipped: %s", exc)

        return normalize_audio(audio, peak=0.85)

    def _worker_loop(self) -> None:
        while True:
            text = self._queue.get()
            try:
                if text is None:
                    return
                if self._stop_event.is_set():
                    continue
                    
                audio = self.synthesize(text)
                
                if len(audio) and not self._stop_event.is_set():
                    # Play the synthesized sentence
                    sample_rate = self.voice.config.sample_rate if self.voice else 22050
                    self.player.play(audio, sample_rate, getattr(self.config, "tts_volume", 1.0))
                    
                    # Sentence Pause (Cinematic pacing)
                    pause = getattr(self.config, "tts_sentence_pause", 0.0)
                    if pause > 0 and not self._stop_event.is_set() and not self._queue.empty():
                        time.sleep(pause)
                        
            except Exception as exc:
                LOGGER.warning("TTS playback loop failed: %s", exc)
            finally:
                self._queue.task_done()

    def _normalize_text(self, text: str) -> str:
        replacements = {
            "AI": "A I",
            "CPU": "C P U",
            "GPU": "G P U",
            "URL": "U R L",
            "PC": "P C",
        }
        out = str(text)
        for source, target in replacements.items():
            out = out.replace(source, target)
        return out.strip()
