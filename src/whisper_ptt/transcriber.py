"""Whisper transcription wrapper (faster-whisper / CTranslate2, CPU int8)."""

from __future__ import annotations

import logging

import numpy as np

from .config import Config

log = logging.getLogger("whisper_ptt.transcriber")


class Transcriber:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._model = None

    def load(self) -> None:
        from faster_whisper import WhisperModel  # lazy: heavy import

        # resolve_model() raises ModelNotFound when offline and the model is not
        # bundled — the caller (boot) surfaces that instead of a silent fetch.
        source, is_local = self.cfg.resolve_model()
        if is_local:
            log.info("loading local model: %s (compute_type=%s, cpu_threads=%s)",
                     source, self.cfg.compute_type, self.cfg.cpu_threads)
        else:
            log.warning("model %r not found locally; DOWNLOADING from HuggingFace "
                        "(allow_download=true)", source)
        self._model = WhisperModel(
            source,
            device="cpu",
            compute_type=self.cfg.compute_type,
            cpu_threads=self.cfg.cpu_threads,
        )

    def warm_start(self) -> None:
        """Run one dummy transcribe so the first real dictation is warm.

        Uses a faint non-silent tone with VAD DISABLED. Warming on pure silence
        with vad_filter on is a no-op: VAD strips the audio to nothing and the
        decoder kernels never actually execute, so the first real dictation
        still pays the full cold-start cost.
        """
        if self._model is None:
            return
        n = self.cfg.sample_rate // 2  # 0.5s
        t = np.arange(n, dtype=np.float32) / float(self.cfg.sample_rate)
        warm = (0.01 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32)
        try:
            segments, _info = self._model.transcribe(
                warm,
                language=self.cfg.language,
                beam_size=self.cfg.beam_size,
                vad_filter=False,
            )
            for _ in segments:  # force the lazy generator so decode really runs
                pass
            log.info("warm_start done")
        except Exception:  # noqa: BLE001 — warm-up must never crash startup
            log.exception("warm_start failed (non-fatal)")

    def transcribe(self, audio: np.ndarray) -> str:
        if self._model is None:
            raise RuntimeError("model not loaded; call load() first")
        audio = np.ascontiguousarray(audio, dtype=np.float32)

        vad_params = (
            {"min_silence_duration_ms": self.cfg.min_silence_duration_ms}
            if self.cfg.vad_filter else None
        )
        segments, _info = self._model.transcribe(
            audio,
            language=self.cfg.language,
            beam_size=self.cfg.beam_size,
            vad_filter=self.cfg.vad_filter,
            vad_parameters=vad_params,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text
