"""
System audio capture using soundcard (WASAPI loopback on Windows).
Streams system output audio in configurable chunks.
"""

import asyncio
import numpy as np
import logging
from typing import AsyncGenerator

# ── Numpy 2.x compatibility patch for soundcard ──────────────────────
# soundcard internally calls numpy.fromstring() in binary mode,
# which was removed in numpy 2.0. Patch it to use frombuffer instead.
if not hasattr(np, "_original_fromstring"):
    np._original_fromstring = getattr(np, "fromstring", None)

    def _patched_fromstring(string, dtype=float, count=-1, *, sep="", like=None):
        if sep == "" or sep is None:
            # .copy() is critical — frombuffer returns a view, but fromstring
            # returned an owning copy. Without copy, soundcard's internal
            # buffer gets reused and overwrites our data.
            return np.frombuffer(string, dtype=dtype, count=count).copy()
        if np._original_fromstring is not None:
            return np._original_fromstring(string, dtype=dtype, count=count, sep=sep)
        raise TypeError("fromstring with sep requires original numpy.fromstring")

    np.fromstring = _patched_fromstring
# ─────────────────────────────────────────────────────────────────────

logger = logging.getLogger("interview_helper")


async def capture_system_audio(
    chunk_duration: float = 2.0,
    sample_rate: int = 48000,
) -> AsyncGenerator[np.ndarray, None]:
    """Async generator that yields system audio chunks as numpy float32 arrays.

    Uses WASAPI loopback to capture what is playing through the default
    speakers / headphones (i.e. the interviewer's voice on Zoom/Meet/Teams).

    Args:
        chunk_duration: Length of each audio chunk in seconds.
        sample_rate: Desired sample rate in Hz.

    Yields:
        np.ndarray of shape (frames, channels) with dtype float32.
    """
    try:
        import soundcard as sc
    except ImportError:
        logger.error(
            "soundcard is not installed. Run: pip install soundcard"
        )
        raise

    # Get default speaker for loopback recording
    try:
        default_speaker = sc.default_speaker()
        if default_speaker is None:
            raise RuntimeError("No default speaker found")
        logger.info(
            f"🎧 Capturing loopback audio from: {default_speaker.name}"
        )
    except Exception as e:
        logger.error(f"Failed to get default speaker: {e}")
        raise RuntimeError(
            f"Cannot access system audio device: {e}"
        ) from e

    num_frames = int(sample_rate * chunk_duration)

    # Use loopback recording (records what the speaker is outputting)
    try:
        mic = sc.get_microphone(
            id=str(default_speaker.id), include_loopback=True
        )
    except Exception as e:
        logger.error(f"Failed to open loopback microphone: {e}")
        raise RuntimeError(
            f"Cannot open loopback capture: {e}. "
            "Ensure you are on Windows with WASAPI support."
        ) from e

    logger.info(
        f"🎙  Recording config: {sample_rate}Hz, "
        f"chunk={chunk_duration}s ({num_frames} frames)"
    )

    try:
        with mic.recorder(samplerate=sample_rate, channels=2) as recorder:
            while True:
                # Record in a thread to avoid blocking the event loop
                audio_data = await asyncio.to_thread(
                    recorder.record, numframes=num_frames
                )
                yield audio_data.astype(np.float32)
    except Exception as e:
        logger.warning(f"Audio capture stopped: {e}")
        raise
