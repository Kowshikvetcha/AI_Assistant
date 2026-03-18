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


def _find_capture_device(sc):
    """Find the best available system-audio loopback device.

    Priority:
      1. WASAPI loopback on the default speaker (captures Zoom/Meet/Teams audio)
      2. Any available loopback device (e.g. Stereo Mix, VB-Cable)

    Raises RuntimeError with setup instructions if no loopback device exists.
    """
    # 1. Try default speaker loopback
    try:
        speaker = sc.default_speaker()
        if speaker:
            mic = sc.get_microphone(id=str(speaker.id), include_loopback=True)
            logger.info(f"🎧 Loopback capture from default speaker: {speaker.name}")
            return mic
    except Exception as e:
        logger.warning(f"Default speaker loopback unavailable: {e}")

    # 2. Try any loopback device available on the system
    try:
        for m in sc.all_microphones(include_loopback=True):
            if "loopback" in m.name.lower():
                logger.info(f"🎧 Loopback capture from: {m.name}")
                return m
    except Exception as e:
        logger.warning(f"Loopback device enumeration failed: {e}")

    # No loopback device found — raise a clear, actionable error
    raise RuntimeError(
        "No system audio loopback device found on this machine.\n"
        "\n"
        "To fix this, do ONE of the following:\n"
        "  1. Enable 'Stereo Mix' in Windows:\n"
        "     Right-click the speaker icon → Sounds → Recording tab\n"
        "     → right-click empty area → Show Disabled Devices\n"
        "     → right-click 'Stereo Mix' → Enable\n"
        "\n"
        "  2. Install VB-Audio Virtual Cable (free):\n"
        "     https://vb-audio.com/Cable\n"
        "     Then set it as your default playback device.\n"
        "\n"
        "  3. Update your audio driver — some drivers disable loopback by default."
    )


async def capture_system_audio(
    chunk_duration: float = 2.0,
    sample_rate: int = 48000,
) -> AsyncGenerator[np.ndarray, None]:
    """Async generator that yields system audio chunks as numpy float32 arrays.

    Uses WASAPI loopback to capture what is playing through the default
    speakers / headphones (i.e. the interviewer's voice on Zoom/Meet/Teams).

    Tries stereo (2ch) first; automatically falls back to mono (1ch) if the
    device does not support stereo — without opening the device twice.

    Args:
        chunk_duration: Length of each audio chunk in seconds.
        sample_rate: Desired sample rate in Hz.

    Yields:
        np.ndarray of shape (frames, channels) with dtype float32.
    """
    try:
        import soundcard as sc
    except ImportError:
        logger.error("soundcard is not installed. Run: pip install soundcard")
        raise

    mic = _find_capture_device(sc)
    num_frames = int(sample_rate * chunk_duration)

    # Open the recorder — try stereo first, fall back to mono.
    # We manage the context manager manually so we only open the device once.
    recorder_ctx = None
    recorder = None
    for channels in (2, 1):
        try:
            recorder_ctx = mic.recorder(samplerate=sample_rate, channels=channels)
            recorder = recorder_ctx.__enter__()
            logger.info(
                f"🎙  Recording: {sample_rate}Hz, {channels}ch, "
                f"{chunk_duration}s chunks ({num_frames} frames)"
            )
            break
        except Exception as e:
            if channels == 2:
                logger.warning(f"Stereo not supported ({e}), retrying in mono...")
                recorder_ctx = None
                continue
            raise RuntimeError(
                f"Cannot open audio recorder on '{mic.name}': {e}.\n"
                "Try closing other apps that use audio, or check your audio driver settings."
            ) from e

    try:
        while True:
            # Record in a thread to avoid blocking the event loop
            audio_data = await asyncio.to_thread(
                recorder.record, numframes=num_frames
            )
            yield audio_data.astype(np.float32)
    except Exception as e:
        logger.warning(f"Audio capture stopped: {e}")
        raise
    finally:
        if recorder_ctx is not None:
            try:
                recorder_ctx.__exit__(None, None, None)
            except Exception:
                pass
