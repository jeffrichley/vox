"""Unit tests for transcribe module (faster-whisper backend)."""

from __future__ import annotations

import numpy as np
import pytest

from vox.transcribe import load_model, transcribe


@pytest.mark.unit
@pytest.mark.slow
class TestTranscribe:
    """transcribe() returns plain text from audio."""

    def test_transcribe_silent_audio_returns_string(self) -> None:
        """Silent float32 16 kHz mono returns a string (may be empty)."""
        # Arrange - silent mono audio
        audio = np.zeros(16000, dtype=np.float32)  # 1 s silence

        # Act - transcribe
        result = transcribe(
            audio,
            model_size_or_path="tiny",
            device="cpu",
            compute_type="int8",
        )

        # Assert - returns a string
        assert isinstance(result, str)

    def test_transcribe_2d_array_returns_string(self) -> None:
        """Audio (frames, 1) is accepted and returns string."""
        # Arrange - silent (frames, 1) audio
        audio = np.zeros((16000, 1), dtype=np.float32)

        # Act - transcribe
        result = transcribe(
            audio,
            model_size_or_path="tiny",
            device="cpu",
            compute_type="int8",
        )

        # Assert - returns a string
        assert isinstance(result, str)


@pytest.mark.unit
@pytest.mark.slow
class TestLoadModel:
    """load_model() loads WhisperModel."""

    def test_load_tiny_cpu_int8(self) -> None:
        """Load tiny model on CPU with int8 (fast, low memory)."""
        # Arrange - model id and runtime settings

        # Act - load model
        model = load_model("tiny", device="cpu", compute_type="int8")

        # Assert - model loaded
        assert model is not None
