from __future__ import annotations

import logging
import queue
import re
import threading
import time
from abc import ABC, abstractmethod
from typing import Iterable, List, Optional, Tuple

import numpy as np

from Voice.audio_output import AudioOutput
from Voice.config import VoiceConfig
from Voice.microphone import normalize_audio


LOGGER = logging.getLogger(__name__)
SENTENCE_RE = re.compile(r"([^.!?\n]+[.!?\n]+)")
DEFAULT_MAX_TTS_CHARS = 180


def split_for_tts(text: str, max_chars: int = DEFAULT_MAX_TTS_CHARS) -> List[str]:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]
    chunks: List[str] = []
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


def split_sentences(buffer: str, max_chars: int = DEFAULT_MAX_TTS_CHARS) -> Tuple[List[str], str]:
    sentences: List[str] = []
    consumed = 0
    for match in SENTENCE_RE.finditer(buffer):
        text = match.group(1).strip()
        if text:
            sentences.extend(split_for_tts(text, max_chars))
        consumed = match.end()
    return sentences, buffer[consumed:]


class BaseTTS(ABC):
    """Abstract base class for local text-to-speech synthesis with async sentence queue."""

    def __init__(self, config: VoiceConfig, audio_output: Optional[AudioOutput] = None):
        self.config = config
        self.audio_output = audio_output or AudioOutput(config.speaker_device)
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="TTSWorker")
        self._worker.start()

    def speak(self, text: str) -> None:
        for chunk in split_for_tts(self.normalize_text(text), self.config.tts_max_chunk_chars):
            self._queue.put(chunk)

    def speak_stream(self, chunks: Iterable[str]) -> str:
        buffer = ""
        full = ""
        for chunk in chunks:
            if self._stop_event.is_set():
                break
            full += chunk
            buffer += chunk
            sentences, buffer = split_sentences(buffer, self.config.tts_max_chunk_chars)
            for sentence in sentences:
                self.speak(sentence)
        if buffer.strip() and not self._stop_event.is_set():
            self.speak(buffer.strip())
        return full

    def interrupt(self) -> None:
        self._stop_event.set()
        self.audio_output.stop()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        self._stop_event.clear()

    def shutdown(self, timeout: float = 2.0) -> None:
        self._queue.put(None)
        if self._worker.is_alive():
            self._worker.join(timeout=timeout)
        self.audio_output.shutdown(timeout=timeout)

    @abstractmethod
    def synthesize(self, text: str) -> Tuple[np.ndarray, int]:
        raise NotImplementedError

    def normalize_text(self, text: str) -> str:
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

    # Backwards compatibility alias
    def _normalize_text(self, text: str) -> str:
        return self.normalize_text(text)

    def _worker_loop(self) -> None:
        while True:
            try:
                text = self._queue.get()
            except Exception:
                break
            try:
                if text is None:
                    return
                if self._stop_event.is_set():
                    continue
                start = time.perf_counter()
                audio, sample_rate = self.synthesize(text)
                LOGGER.info("TTS latency %.3fs backend=%s", time.perf_counter() - start, self.__class__.__name__)
                if len(audio) and not self._stop_event.is_set():
                    self.audio_output.play(audio, sample_rate, self.config.volume)
                    pause = self.config.tts_sentence_pause
                    if pause > 0 and not self._stop_event.is_set() and not self._queue.empty():
                        time.sleep(pause)
            except Exception as exc:
                LOGGER.warning("TTS worker failed: %s", exc)
            finally:
                try:
                    self._queue.task_done()
                except ValueError:
                    pass


class PiperTTS(BaseTTS):
    """Local Piper neural TTS engine optimized for Czech speech."""

    def __init__(self, config: VoiceConfig, audio_output: Optional[AudioOutput] = None):
        self.voice = None
        super().__init__(config, audio_output)
        try:
            from piper.voice import PiperVoice

            LOGGER.info("Loading Piper voice: %s", config.piper_voice)
            self.voice = PiperVoice.load(config.piper_voice)
        except Exception as exc:
            LOGGER.warning("Piper unavailable: %s", exc)

    def synthesize(self, text: str) -> Tuple[np.ndarray, int]:
        if not self.voice or not text:
            return np.array([], dtype="float32"), 22050
        try:
            from piper.config import SynthesisConfig

            syn_config = SynthesisConfig(length_scale=self.config.speed)
            audio_chunks = [chunk.audio_float_array for chunk in self.voice.synthesize(text, syn_config=syn_config)]
        except Exception as exc:
            LOGGER.warning("Piper generation failed: %s", exc)
            return np.array([], dtype="float32"), getattr(self.voice.config, "sample_rate", 22050)
        if not audio_chunks:
            return np.array([], dtype="float32"), getattr(self.voice.config, "sample_rate", 22050)
        audio = np.concatenate(audio_chunks).astype("float32")
        audio = self._post_process_audio(audio)
        return audio, self.voice.config.sample_rate

    def _post_process_audio(self, audio: np.ndarray) -> np.ndarray:
        if not len(audio) or not self.voice:
            return audio
        sr = getattr(self.voice.config, "sample_rate", 22050)
        if self.config.pitch != 0:
            try:
                import librosa

                audio = librosa.effects.pitch_shift(audio, sr=sr, n_steps=self.config.pitch)
            except Exception as exc:
                LOGGER.debug("Pitch shift skipped: %s", exc)
        if self.config.tts_ai_style:
            try:
                import scipy.signal as signal

                b, a = signal.iirpeak(120 / (sr / 2), 1.5)
                audio = audio + signal.lfilter(b, a, audio) * 0.3
            except Exception as exc:
                LOGGER.debug("EQ skipped: %s", exc)
        return normalize_audio(np.asarray(audio, dtype="float32"), peak=0.85)


# Legacy alias
PiperEngine = PiperTTS


def create_tts(config: VoiceConfig, audio_output: Optional[AudioOutput] = None) -> BaseTTS:
    """TTS engine factory returning local offline PiperTTS."""
    return PiperTTS(config, audio_output)
