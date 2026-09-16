"""Unit tests for StreamingSileroVad with a fake ONNX session."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest

from vox.continuous.vad import (
    FRAME_SAMPLES,
    StreamingSileroVad,
    VadUnavailableError,
    load_streaming_vad,
)


class FakeSession:
    """Records input feeds and returns scripted speech probs with bumped state."""

    def __init__(
        self,
        *,
        input_names: tuple[str, ...] = ("input", "h", "c"),
        probs: list[float] | None = None,
    ) -> None:
        self._input_names = input_names
        self._probs = list(probs) if probs is not None else [0.42, 0.77]
        self.calls: list[dict[str, np.ndarray]] = []

    def get_inputs(self) -> list[SimpleNamespace]:
        """Return fake ONNX input metadata."""
        return [SimpleNamespace(name=name) for name in self._input_names]

    def run(
        self,
        output_names: None,
        input_feed: dict[str, np.ndarray],
    ) -> list[np.ndarray]:
        """Record the feed and return (prob, h+1, c+1)."""
        del output_names
        self.calls.append({key: value.copy() for key, value in input_feed.items()})
        index = min(len(self.calls) - 1, len(self._probs) - 1)
        prob = np.array([self._probs[index]], dtype=np.float32)
        h_out = input_feed["h"].astype(np.float32) + 1.0
        c_out = input_feed["c"].astype(np.float32) + 1.0
        return [prob, h_out, c_out]


@pytest.mark.unit
class TestStreamingSileroVad:
    """StreamingSileroVad carries state/context and validates frames."""

    def test_first_call_uses_zero_context_and_zero_state(self) -> None:
        """First frame is prepended with zero context and zero h/c."""
        # Arrange - fake session and first 512-sample frame
        session = FakeSession(probs=[0.3])
        vad = StreamingSileroVad(session)
        frame = np.arange(FRAME_SAMPLES, dtype=np.float32)

        # Act - score the first frame
        result = vad.probability(frame)

        # Assert - zero context/state used and probability returned
        assert result == pytest.approx(0.3)
        assert len(session.calls) == 1
        feed = session.calls[0]
        assert feed["input"].shape == (1, FRAME_SAMPLES + 64)
        np.testing.assert_array_equal(
            feed["input"][0, :64], np.zeros(64, dtype=np.float32)
        )
        np.testing.assert_array_equal(feed["input"][0, 64:], frame)
        np.testing.assert_array_equal(
            feed["h"], np.zeros((1, 1, 128), dtype=np.float32)
        )
        np.testing.assert_array_equal(
            feed["c"], np.zeros((1, 1, 128), dtype=np.float32)
        )

    def test_second_call_carries_state_and_previous_context(self) -> None:
        """Second frame receives prior hn/cn and the first frame's last 64 samples."""
        # Arrange - two sequential frames and a stateful fake session
        session = FakeSession(probs=[0.2, 0.9])
        vad = StreamingSileroVad(session)
        frame1 = np.arange(FRAME_SAMPLES, dtype=np.float32)
        frame2 = np.arange(FRAME_SAMPLES, FRAME_SAMPLES * 2, dtype=np.float32)

        # Act - score both frames in order
        first = vad.probability(frame1)
        second = vad.probability(frame2)

        # Assert - second call sees prior hn/cn and last 64 samples of frame1
        assert first == pytest.approx(0.2)
        assert second == pytest.approx(0.9)
        assert len(session.calls) == 2
        feed2 = session.calls[1]
        np.testing.assert_array_equal(feed2["input"][0, :64], frame1[-64:])
        np.testing.assert_array_equal(feed2["input"][0, 64:], frame2)
        np.testing.assert_array_equal(
            feed2["h"], np.ones((1, 1, 128), dtype=np.float32)
        )
        np.testing.assert_array_equal(
            feed2["c"], np.ones((1, 1, 128), dtype=np.float32)
        )

    def test_probability_returns_python_float(self) -> None:
        """probability() returns a built-in float, not a numpy scalar."""
        # Arrange - silent frame and fake session
        vad = StreamingSileroVad(FakeSession(probs=[0.55]))
        frame = np.zeros(FRAME_SAMPLES, dtype=np.float32)

        # Act - score the frame
        result = vad.probability(frame)

        # Assert - built-in float, not numpy scalar
        assert type(result) is float

    def test_rejects_wrong_length_frame(self) -> None:
        """Frames that are not exactly 512 samples raise ValueError."""
        # Arrange - frame with wrong sample count
        vad = StreamingSileroVad(FakeSession())
        frame = np.zeros(256, dtype=np.float32)

        # Act - score invalid frame
        # Assert - ValueError names the required length
        with pytest.raises(ValueError, match="512"):
            vad.probability(frame)

    def test_rejects_non_float32_or_non_1d_frame(self) -> None:
        """Frames that are not 1-D float32 raise ValueError."""
        # Arrange - float64 and 2-D frames
        vad = StreamingSileroVad(FakeSession())
        wrong_dtype = np.zeros(FRAME_SAMPLES, dtype=np.float64)
        wrong_shape = np.zeros((1, FRAME_SAMPLES), dtype=np.float32)

        # Act - score invalid frames
        # Assert - ValueError for dtype and dimensionality
        with pytest.raises(ValueError, match="float32"):
            vad.probability(wrong_dtype)
        with pytest.raises(ValueError, match=r"1-D|1D|one-dimensional"):
            vad.probability(wrong_shape)

    def test_wrong_input_names_raise_vad_unavailable(self) -> None:
        """Mismatched ONNX input names raise VadUnavailableError naming faster-whisper."""
        # Arrange - session with legacy/wrong ONNX input names
        session = FakeSession(input_names=("input", "state"))

        # Act - construct adapter
        # Assert - clear unavailable error naming faster-whisper>=1.2.1
        with pytest.raises(
            VadUnavailableError, match=r"(?i)speech detection unavailable"
        ):
            StreamingSileroVad(session)
        with pytest.raises(VadUnavailableError, match=r"1\.2\.1"):
            StreamingSileroVad(session)


@pytest.mark.unit
class TestLoadStreamingVad:
    """load_streaming_vad wraps failures in VadUnavailableError."""

    def test_wraps_import_failure(self) -> None:
        """Import failures become VadUnavailableError with actionable text."""
        # Arrange - import_module fails
        with mock.patch(
            "vox.continuous.vad.import_module",
            side_effect=ImportError("no module"),
        ):
            # Act - load streaming vad
            # Assert - wrapped as VadUnavailableError naming required version
            with pytest.raises(
                VadUnavailableError,
                match=r"(?i)speech detection unavailable",
            ):
                load_streaming_vad()
            with pytest.raises(VadUnavailableError, match=r"1\.2\.1"):
                load_streaming_vad()


@pytest.mark.unit
class TestCliDoesNotImportSpeechDetection:
    """CLI import stays free of speech-detection modules."""

    def test_importing_cli_does_not_load_vad(self) -> None:
        """Importing vox.cli must not pull in continuous.vad or faster_whisper.vad."""
        # Arrange - drop any previously loaded speech-detection modules
        for name in list(sys.modules):
            if (
                name == "vox.cli"
                or name.startswith("vox.continuous")
                or name == "faster_whisper.vad"
            ):
                del sys.modules[name]

        # Act - import the CLI package
        importlib.import_module("vox.cli")

        # Assert - speech detection modules stay unloaded
        assert "vox.continuous.vad" not in sys.modules
        assert "faster_whisper.vad" not in sys.modules
