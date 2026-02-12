"""
Utility functions: logging setup, performance timing, audio encoding.
"""

import io
import time
import wave
import logging
import numpy as np
from contextlib import contextmanager


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the application logger."""
    logger = logging.getLogger("interview_helper")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


@contextmanager
def perf_timer(label: str, logger: logging.Logger | None = None):
    """Context manager that measures elapsed time in milliseconds.

    Usage:
        with perf_timer("stt_call", logger) as t:
            result = await some_api_call()
        elapsed_ms = t["elapsed_ms"]
    """
    result = {"elapsed_ms": 0.0}
    start = time.perf_counter()
    try:
        yield result
    finally:
        elapsed = (time.perf_counter() - start) * 1000
        result["elapsed_ms"] = round(elapsed, 2)
        if logger:
            logger.info(f"⏱  {label}: {result['elapsed_ms']:.1f} ms")


def encode_wav(
    audio_data: np.ndarray,
    sample_rate: int = 48000,
    target_rate: int = 16000,
) -> bytes:
    """Encode a numpy float32 audio array to WAV bytes for the Whisper API.

    Converts stereo to mono and downsamples to 16kHz (Whisper's native rate)
    for best transcription accuracy.

    Args:
        audio_data: Float32 numpy array, shape (frames,) or (frames, channels).
        sample_rate: Input sampling rate in Hz.
        target_rate: Target sampling rate for output (default 16000 for Whisper).

    Returns:
        WAV file content as bytes (16kHz, mono, 16-bit PCM).
    """
    # Convert stereo to mono if needed
    if audio_data.ndim == 2 and audio_data.shape[1] >= 2:
        mono = np.mean(audio_data, axis=1)
    else:
        mono = audio_data.flatten()

    # Downsample from sample_rate to target_rate
    if sample_rate != target_rate:
        # Simple decimation — works well for integer ratios
        ratio = sample_rate / target_rate  # e.g., 48000/16000 = 3
        num_target_samples = int(len(mono) / ratio)
        indices = (np.arange(num_target_samples) * ratio).astype(int)
        mono = mono[indices]

    # Convert float32 [-1, 1] to int16
    audio_int16 = np.clip(mono, -1.0, 1.0)
    audio_int16 = (audio_int16 * 32767).astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)          # Mono
        wf.setsampwidth(2)          # 16-bit
        wf.setframerate(target_rate)  # 16kHz
        wf.writeframes(audio_int16.tobytes())

    buffer.seek(0)
    return buffer.read()


def is_silent(audio_data: np.ndarray, threshold: float = 0.01) -> bool:
    """Check if an audio chunk is mostly silence.

    Args:
        audio_data: Float32 numpy array.
        threshold: RMS threshold below which audio is considered silent.

    Returns:
        True if the audio is below the silence threshold.
    """
    rms = np.sqrt(np.mean(audio_data ** 2))
    return bool(rms < threshold)
