"""Unit tests for speech-only transcription filter (#36)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest

from vox.transcribe import TranscriptionError
from vox.transcribe.faster_whisper_backend import transcribe_speech_only


def _fake_model(segments: list[object]) -> mock.Mock:
    """Build a WhisperModel mock whose transcribe yields ``segments``."""
    model = mock.Mock()
    model.transcribe.return_value = (iter(segments), None)
    return model


@pytest.mark.unit
class TestTranscribeSpeechOnly:
    """Speech-only filter drops high no_speech_prob segments."""

    def test_drops_segments_with_no_speech_prob_above_0_6(self) -> None:
        """Segments with no_speech_prob > 0.6 are omitted from the text."""
        # Arrange - one keepable segment and one hallucination above 0.6
        segments = [
            SimpleNamespace(text=" hello ", no_speech_prob=0.4),
            SimpleNamespace(text=" Thank you. ", no_speech_prob=0.61),
        ]
        model = _fake_model(segments)
        audio = np.zeros(1600, dtype=np.float32)

        # Act - speech-only transcribe with mixed segments
        result = transcribe_speech_only(audio, model=model)

        # Assert - only the speech segment remains
        assert result == "hello"

    def test_keeps_segments_at_or_below_0_6(self) -> None:
        """Segments with no_speech_prob <= 0.6 are kept."""
        # Arrange - boundary 0.6 and a clear speech segment
        segments = [
            SimpleNamespace(text=" keep ", no_speech_prob=0.6),
            SimpleNamespace(text=" me ", no_speech_prob=0.1),
        ]
        model = _fake_model(segments)
        audio = np.zeros(1600, dtype=np.float32)

        # Act - speech-only transcribe at the keep boundary
        result = transcribe_speech_only(audio, model=model)

        # Assert - both segments concatenated
        assert result == "keep me"

    def test_wraps_segment_iteration_errors_as_transcription_error(self) -> None:
        """Errors while iterating segments become TranscriptionError."""

        # Arrange - generator that raises mid-iteration
        def boom() -> object:
            yield SimpleNamespace(text="ok", no_speech_prob=0.1)
            raise RuntimeError("decoder failed")

        model = mock.Mock()
        model.transcribe.return_value = (boom(), None)
        audio = np.zeros(1600, dtype=np.float32)

        # Act - speech-only transcribe when the segment iterator raises
        with pytest.raises(
            TranscriptionError, match=r"decoder|failed|transcri"
        ) as exc_info:
            transcribe_speech_only(audio, model=model)

        # Assert - failure is TranscriptionError wrapping the decoder error
        assert exc_info.value.__cause__ is not None
        assert "decoder failed" in str(exc_info.value.__cause__)
