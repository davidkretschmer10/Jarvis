from __future__ import annotations

import logging
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

import numpy as np
import soundfile as sf

from Voice.config import VoiceConfig
from Voice.microphone import RecordingResult


LOGGER = logging.getLogger(__name__)
PartialCallback = Callable[[str], None]


@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration: float
    model: str


class WhisperEngine:
    def __init__(self, config: VoiceConfig):
        self.config = config
        self._model = None
        self._model_name = config.stt_model
        self._device = "cpu"
        self._compute_type = "int8"

    def _select_device(self) -> tuple[str, str]:
        requested = self.config.whisper_device
        if requested and requested != "auto":
            return requested, self.config.whisper_compute_type
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                return "cuda", self.config.whisper_compute_type or "float16"
        except Exception as exc:
            LOGGER.info("CUDA check unavailable, using CPU: %s", exc)
        return "cpu", "int8"

    def load(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        device, compute_type = self._select_device()
        candidates = [self.config.stt_model]
        if self.config.stt_fallback_model not in candidates:
            candidates.append(self.config.stt_fallback_model)

        last_error: Optional[Exception] = None
        for model_name in candidates:
            try:
                LOGGER.info("Loading Whisper model=%s device=%s compute=%s", model_name, device, compute_type)
                self._model = WhisperModel(model_name, device=device, compute_type=compute_type)
                self._model_name = model_name
                self._device = device
                self._compute_type = compute_type
                return
            except Exception as exc:
                LOGGER.warning("Could not load Whisper model %s on %s: %s", model_name, device, exc)
                last_error = exc
                device, compute_type = "cpu", "int8"
        raise RuntimeError(f"Could not load any Whisper model: {last_error}")

    def set_model(self, model_name: str) -> None:
        if model_name and model_name != self._model_name:
            self.config.stt_model = model_name
            self._model_name = model_name
            self._model = None

    def transcribe_audio(
        self,
        audio: np.ndarray,
        sample_rate: int,
        partial_callback: Optional[PartialCallback] = None,
    ) -> TranscriptionResult:
        start = time.perf_counter()
        audio = np.asarray(audio, dtype="float32").flatten()
        if len(audio) == 0:
            return TranscriptionResult("", self.config.language, 0.0, self._model_name)

        self.load()
        assert self._model is not None

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            sf.write(tmp_path, audio, sample_rate)
            language = self.config.language or None
            segments, info = self._model.transcribe(
                tmp_path,
                language=language,
                beam_size=5,
                vad_filter=self.config.vad_enabled,
                vad_parameters={"min_silence_duration_ms": int(self.config.silence_timeout * 500)},
                condition_on_previous_text=False,
            )
            parts: list[str] = []
            for segment in segments:
                text = segment.text.strip()
                if text:
                    parts.append(text)
                    if partial_callback:
                        partial_callback(" ".join(parts))
            detected = getattr(info, "language", self.config.language)
            duration = time.perf_counter() - start
            LOGGER.info("Whisper latency %.3fs model=%s language=%s", duration, self._model_name, detected)
            return TranscriptionResult(" ".join(parts).strip(), detected, duration, self._model_name)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def transcribe_recording(self, recording: RecordingResult, partial_callback: Optional[PartialCallback] = None) -> TranscriptionResult:
        return self.transcribe_audio(recording.audio, recording.sample_rate, partial_callback)

    def transcribe_chunks(
        self,
        chunks: Iterable[np.ndarray],
        sample_rate: int,
        partial_callback: Optional[PartialCallback] = None,
    ) -> TranscriptionResult:
        arrays = [np.asarray(chunk, dtype="float32").flatten() for chunk in chunks]
        if not arrays:
            return TranscriptionResult("", self.config.language, 0.0, self._model_name)
        return self.transcribe_audio(np.concatenate(arrays), sample_rate, partial_callback)
