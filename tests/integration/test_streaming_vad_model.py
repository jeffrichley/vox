"""Integration: live StreamingSileroVad matches whole-file Silero probabilities."""

from __future__ import annotations

import numpy as np
import pytest
from faster_whisper.vad import get_vad_model

from vox.continuous.vad import FRAME_SAMPLES, load_streaming_vad


def _synthetic_audio() -> np.ndarray:
    """Build seeded noise plus a synthetic voiced burst, trimmed to frame multiples."""
    rng = np.random.default_rng(0)
    sample_rate = 16_000
    noise_a = (0.01 * rng.standard_normal(sample_rate)).astype(np.float32)
    noise_b = (0.01 * rng.standard_normal(sample_rate)).astype(np.float32)
    t = np.arange(int(1.5 * sample_rate), dtype=np.float32) / sample_rate
    carrier = (
        np.sin(2 * np.pi * 140 * t)
        + 0.5 * np.sin(2 * np.pi * 280 * t)
        + 0.25 * np.sin(2 * np.pi * 420 * t)
    )
    envelope = 0.5 * (1.0 + np.sin(2 * np.pi * 4 * t))
    burst = (0.2 * carrier * envelope).astype(np.float32)
    audio = np.concatenate([noise_a, burst, noise_b])
    usable = (audio.shape[0] // FRAME_SAMPLES) * FRAME_SAMPLES
    return audio[:usable]


@pytest.mark.integration
def test_streaming_matches_whole_file_silero() -> None:
    """Frame-by-frame probabilities match batched Silero within 1e-5 (no microphone)."""
    # Arrange - synthetic audio, whole-file Silero probs, and streaming adapter
    audio = _synthetic_audio()
    batch = get_vad_model()(audio)
    vad = load_streaming_vad()
    frames = audio.reshape(-1, FRAME_SAMPLES)

    # Act - score every 512-sample frame live
    streaming = np.array(
        [vad.probability(frame) for frame in frames],
        dtype=np.float32,
    )

    # Assert - streaming matches batched Silero within 1e-5
    np.testing.assert_allclose(streaming, batch.reshape(-1), atol=1e-5)
