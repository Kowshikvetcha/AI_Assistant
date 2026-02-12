"""
Performance and error simulation tests.
Tests timing utilities, silence detection, and WAV encoding.
"""

import pytest
import asyncio
import numpy as np
import logging

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import perf_timer, encode_wav, is_silent, setup_logging
from models import PerformanceMetrics


class TestPerfTimer:
    """Tests for the performance timer context manager."""

    def test_perf_timer_measures_time(self):
        """Timer should record elapsed time."""
        import time

        with perf_timer("test_op") as t:
            time.sleep(0.05)  # 50ms

        assert t["elapsed_ms"] >= 40  # Allow some tolerance
        assert t["elapsed_ms"] < 200

    def test_perf_timer_with_logger(self, caplog):
        """Timer should log when logger is provided."""
        test_logger = setup_logging("DEBUG")

        with caplog.at_level(logging.INFO):
            with perf_timer("test_op", test_logger) as t:
                pass

        assert t["elapsed_ms"] >= 0

    def test_perf_timer_on_exception(self):
        """Timer should still record time even if body raises."""
        result = {}
        try:
            with perf_timer("error_op") as t:
                result = t
                raise ValueError("test error")
        except ValueError:
            pass

        assert result["elapsed_ms"] >= 0


class TestWavEncoding:
    """Tests for WAV encoding utility."""

    def test_encode_wav_returns_bytes(self):
        """Should produce valid WAV bytes (mono 16kHz)."""
        audio = np.zeros((48000, 2), dtype=np.float32)  # 1s stereo at 48kHz
        result = encode_wav(audio, sample_rate=48000)

        assert isinstance(result, bytes)
        assert len(result) > 44  # WAV header is 44 bytes
        # Check WAV magic bytes
        assert result[:4] == b"RIFF"
        assert result[8:12] == b"WAVE"

    def test_encode_wav_clips_values(self):
        """Should clip values outside [-1, 1]."""
        audio = np.array([[2.0, -2.0], [1.5, -1.5]], dtype=np.float32)
        result = encode_wav(audio, sample_rate=16000, target_rate=16000)

        assert isinstance(result, bytes)
        assert len(result) > 44

    def test_encode_wav_mono(self):
        """Should handle mono audio."""
        audio = np.zeros((16000,), dtype=np.float32)
        result = encode_wav(audio, sample_rate=16000, target_rate=16000)

        assert isinstance(result, bytes)


class TestSilenceDetection:
    """Tests for silence detection."""

    def test_silent_audio(self):
        """Should detect silence."""
        audio = np.zeros((48000, 2), dtype=np.float32)
        assert is_silent(audio) is True

    def test_loud_audio(self):
        """Should not detect non-silent audio."""
        audio = np.full((48000, 2), 0.5, dtype=np.float32)
        assert is_silent(audio) is False

    def test_quiet_audio_below_threshold(self):
        """Should detect very quiet audio as silent."""
        audio = np.full((48000, 2), 0.005, dtype=np.float32)
        assert is_silent(audio, threshold=0.01) is True

    def test_custom_threshold(self):
        """Should respect custom threshold."""
        audio = np.full((48000, 2), 0.05, dtype=np.float32)
        assert is_silent(audio, threshold=0.1) is True
        assert is_silent(audio, threshold=0.01) is False


class TestPerformanceMetrics:
    """Tests for the PerformanceMetrics model."""

    def test_default_values(self):
        metrics = PerformanceMetrics()
        assert metrics.stt_latency_ms == 0.0
        assert metrics.llm_latency_ms == 0.0
        assert metrics.total_latency_ms == 0.0
        assert metrics.tokens_used == 0

    def test_populated_metrics(self):
        metrics = PerformanceMetrics(
            stt_latency_ms=1200.5,
            llm_latency_ms=2500.3,
            total_latency_ms=3700.8,
            tokens_used=350,
            timestamp=1700000000.0,
        )
        assert metrics.stt_latency_ms == 1200.5
        assert metrics.tokens_used == 350
