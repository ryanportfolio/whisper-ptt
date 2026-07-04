"""Microphone capture into an in-memory float32 buffer (sounddevice/PortAudio).

The InputStream stays open for the app's lifetime; start()/stop() just gate a
capturing flag and the ring buffer, so dictation begins with no device-open
latency.
"""

from __future__ import annotations

import logging
import threading
from collections import deque

import numpy as np
import sounddevice as sd

from .config import Config

log = logging.getLogger("whisper_ptt.audio")


class AudioCapture:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._capturing = False
        self._buf: deque[np.ndarray] = deque()
        self._buf_samples = 0  # running count, to cap without summing the deque
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self._last_rms = 0.0
        self._capture_sr = cfg.sample_rate  # actual device rate (set in open())
        self._max_samples = 0  # capture cap in samples (set in open())
        self._capped = False   # latched once the cap trips, to warn only once

    # ---- stream lifecycle -------------------------------------------------
    # Shared-mode host APIs deliver audio reliably and resample internally;
    # WDM-KS is exclusive/finicky and is the last resort. When no mic is
    # plugged in, only WDM-KS pins enumerate at all and they deliver nothing.
    _API_PREFERENCE = ("MME", "Windows WASAPI", "Windows DirectSound", "Windows WDM-KS")

    def _resolve_device(self) -> int | None:
        """config override -> PortAudio default -> first input by API preference."""
        if self.cfg.device_index is not None:
            return self.cfg.device_index

        try:
            default_in = sd.default.device[0]
        except Exception:  # noqa: BLE001
            default_in = -1
        if isinstance(default_in, int) and default_in >= 0:
            return default_in

        hostapis = sd.query_hostapis()
        devices = sd.query_devices()

        # Prefer a host API's own default input, in preference order.
        for want in self._API_PREFERENCE:
            for ha in hostapis:
                idx = ha.get("default_input_device", -1)
                if ha["name"] == want and isinstance(idx, int) and idx >= 0:
                    return idx

        # Else the first input-capable device, in preference order.
        for want in self._API_PREFERENCE:
            for i, d in enumerate(devices):
                if d["max_input_channels"] > 0 and hostapis[d["hostapi"]]["name"] == want:
                    log.info("no default input; using %s device %d (%s)", want, i, d["name"])
                    return i
        return None

    def open(self) -> None:
        device = self._resolve_device()
        if device is None:
            raise RuntimeError("no input audio device found")
        # Some devices (WDM-KS pins especially) reject a direct 16 kHz open.
        # Open at the device's native rate and resample to the model rate in
        # stop() so any working input device is usable.
        info = sd.query_devices(device)
        self._capture_sr = int(round(info["default_samplerate"])) or self.cfg.sample_rate
        cap_s = getattr(self.cfg, "max_capture_seconds", 0) or 0
        self._max_samples = int(cap_s * self._capture_sr) if cap_s > 0 else 0
        blocksize = int(self._capture_sr * 0.1)  # 100ms
        self._stream = sd.InputStream(
            samplerate=self._capture_sr,
            channels=1,
            dtype="float32",
            blocksize=blocksize,
            device=device,
            callback=self._callback,
        )
        self._stream.start()
        log.info("audio stream open: device=%s capture=%d Hz -> model=%d Hz mono",
                 device, self._capture_sr, self.cfg.sample_rate)

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, indata, frames, time_info, status):  # noqa: ANN001
        if status:
            log.debug("audio status: %s", status)
        if not self._capturing:
            return
        mono = indata.reshape(-1).copy()
        self._last_rms = float(np.sqrt(np.mean(mono * mono))) if mono.size else 0.0
        with self._lock:
            self._buf.append(mono)
            self._buf_samples += mono.size
            # Bound memory on an abandoned recording: once we hit the cap, stop
            # capturing (keeping the chronological start) so RAM can't grow to
            # OOM. A later stop() drains what was captured; the next start()
            # resets. Warn exactly once per recording.
            if self._max_samples and self._buf_samples >= self._max_samples:
                self._capturing = False
                if not self._capped:
                    self._capped = True
                    log.warning(
                        "capture hit %ds cap; auto-stopped to bound memory "
                        "(tap to transcribe/reset)",
                        self.cfg.max_capture_seconds,
                    )

    # ---- capture gate -----------------------------------------------------
    def start(self) -> None:
        with self._lock:
            self._buf.clear()
            self._buf_samples = 0
        self._capped = False
        self._capturing = True

    def stop(self) -> np.ndarray:
        self._capturing = False
        with self._lock:
            chunks = list(self._buf)
            self._buf.clear()
            self._buf_samples = 0
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(chunks).astype(np.float32)
        if self._capture_sr != self.cfg.sample_rate:
            audio = _resample(audio, self._capture_sr, self.cfg.sample_rate)
        return audio

    @property
    def rms(self) -> float:
        return self._last_rms


def _resample(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Resample mono float32 via PyAV (anti-aliased; already a dependency)."""
    import av
    from av.audio.resampler import AudioResampler

    if audio.size == 0:
        return audio
    frame = av.AudioFrame.from_ndarray(audio.reshape(1, -1), format="flt", layout="mono")
    frame.sample_rate = src_sr
    resampler = AudioResampler(format="flt", layout="mono", rate=dst_sr)
    out = resampler.resample(frame)
    out = out if isinstance(out, list) else [out]
    flush = resampler.resample(None)
    if flush:
        out += flush if isinstance(flush, list) else [flush]
    parts = [f.to_ndarray().reshape(-1) for f in out]
    return np.concatenate(parts).astype(np.float32) if parts else np.zeros(0, dtype=np.float32)


def list_input_devices() -> list[tuple[int, str]]:
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append((i, d["name"]))
    return out
