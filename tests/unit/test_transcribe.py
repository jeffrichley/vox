"""Unit tests for transcribe module (faster-whisper backend)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from vox.transcribe import TranscriptionError, load_model, transcribe


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

    def test_load_model_raises_transcription_error_when_whisper_raises(self) -> None:
        """When WhisperModel(...) raises, load_model raises TranscriptionError."""
        # Arrange - WhisperModel constructor raises
        with mock.patch(
            "vox.transcribe.faster_whisper_backend.WhisperModel"
        ) as mock_whisper:
            mock_whisper.side_effect = Exception("model not found")
            # Act - call load_model (expects TranscriptionError)
            # Assert - TranscriptionError with Failed or model or base in message
            with pytest.raises(TranscriptionError, match=r"Failed|model|base"):
                load_model("base", device="cpu", compute_type="float32")


@pytest.mark.unit
class TestTranscribeWithModelNone:
    """transcribe() when model is None loads model and can raise."""

    def test_transcribe_raises_transcription_error_when_load_model_raises_generic(
        self,
    ) -> None:
        """When model is None and load_model raises, transcribe raises TranscriptionError."""
        # Arrange - load_model raises generic Exception
        with (
            mock.patch(
                "vox.transcribe.faster_whisper_backend.load_model",
                side_effect=Exception("download failed"),
            ),
            pytest.raises(TranscriptionError, match=r"Failed|model"),
        ):
            # Act - call transcribe without model (expects TranscriptionError)
            # Assert - TranscriptionError with Failed or model in message
            transcribe(
                np.zeros(1600, dtype=np.float32),
                model_size_or_path="tiny",
                device="cpu",
                compute_type="int8",
            )

    def test_transcribe_reraises_transcription_error_from_load_model(self) -> None:
        """When load_model raises TranscriptionError, transcribe re-raises it."""
        # Arrange - load_model raises TranscriptionError
        with (
            mock.patch(
                "vox.transcribe.faster_whisper_backend.load_model",
                side_effect=TranscriptionError("invalid model"),
            ),
            pytest.raises(TranscriptionError, match=r"invalid model"),
        ):
            # Act - call transcribe without model (expects TranscriptionError)
            # Assert - same TranscriptionError re-raised
            transcribe(
                np.zeros(1600, dtype=np.float32),
                model_size_or_path="tiny",
                device="cpu",
                compute_type="int8",
            )


@pytest.mark.unit
class TestTranscribeFilePath:
    """transcribe() with Path or str uses model.transcribe(path)."""

    def test_transcribe_accepts_path_and_calls_model_transcribe(self) -> None:
        """When audio is Path, transcribe resolves it and calls model.transcribe(path)."""
        # Arrange - pre-loaded model and path; model.transcribe returns one segment
        mock_model = mock.Mock()
        mock_segment = mock.Mock()
        mock_segment.text = "hello"
        mock_model.transcribe.return_value = (iter([mock_segment]), None)
        path = Path("/tmp/test_audio.wav")
        # Act - call transcribe with Path and pre-loaded model
        result = transcribe(path, model=mock_model)
        # Assert - model.transcribe called with path; result is segment text
        mock_model.transcribe.assert_called_once()
        call_arg = mock_model.transcribe.call_args[0][0]
        assert str(path.resolve()) == call_arg or str(path) in call_arg
        assert result == "hello"
