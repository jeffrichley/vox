"""Integration: capture -> transcribe."""

from __future__ import annotations

import pytest

from vox.capture import record_seconds
from vox.transcribe import transcribe


@pytest.mark.integration
@pytest.mark.slow
def test_capture_then_transcribe_returns_string(requires_audio: None) -> None:
    """Short record -> transcribe returns a string (content may be empty)."""
    # Arrange - record a short sample
    samples = record_seconds(0.2, sample_rate=16000, channels=1)

    # Act - transcribe recorded audio
    text = transcribe(
        samples,
        model_size_or_path="tiny",
        device="cpu",
        compute_type="int8",
    )

    # Assert - returns a string
    assert isinstance(text, str)
