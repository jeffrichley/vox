"""Unit tests for capture: list_devices, record/playback, record_until_stop."""

from __future__ import annotations

import threading
from unittest import mock

import numpy as np
import pytest
import sounddevice as sd

from vox.capture import list_devices, play_back, record_seconds, record_until_stop


@pytest.mark.unit
class TestListDevices:
    """list_devices() returns input devices."""

    def test_returns_list_of_tuples(self) -> None:
        """list_devices returns list of (int, str, str) — id, name, host_api."""
        # Arrange - no setup required

        # Act - list devices
        result = list_devices()

        # Assert - shape and types
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 3
            assert isinstance(item[0], int)
            assert isinstance(item[1], str)
            assert isinstance(item[2], str)

    def test_only_input_devices(self) -> None:
        """All returned devices should be input-capable (no assertion on count)."""
        # Arrange - no setup required

        # Act - list devices
        result = list_devices()

        # Assert - each device has input channels
        for dev_id, _name, _host_api in result:
            dev = sd.query_devices(dev_id)
            assert dev.get("max_input_channels", 0) > 0

    def test_list_devices_raises_runtime_error_on_port_audio_error(self) -> None:
        """When sounddevice raises PortAudioError, list_devices raises RuntimeError."""
        # Arrange - query_devices raises PortAudioError
        mock_sd = mock.Mock()
        mock_sd.query_devices.side_effect = sd.PortAudioError()
        with (
            mock.patch("vox.capture.stream._sd", return_value=mock_sd),
            pytest.raises(RuntimeError, match=r"audio|device|permission"),
        ):
            # Act - call list_devices (expects RuntimeError)
            # Assert - RuntimeError with message about devices/permissions
            list_devices()


@pytest.mark.unit
class TestRecordUntilStop:
    """record_until_stop waits for stop_event then returns concatenated blocks."""

    def test_record_until_stop_returns_empty_array_when_stop_immediate(self) -> None:
        """When stop_event already set, recording returns empty array (no callback)."""
        # Arrange - stop_event set immediately; mock InputStream so callback never runs
        stop_ev = threading.Event()
        stop_ev.set()
        mock_stream = mock.Mock()

        mock_sd = mock.Mock()
        mock_sd.InputStream.return_value = mock_stream
        with mock.patch("vox.capture.stream._sd", return_value=mock_sd):
            # Act - call record_until_stop with pre-set stop event
            result = record_until_stop(stop_ev, sample_rate=16000, channels=1)
            # Assert - stream started, then wait; no blocks so empty array
            mock_stream.start.assert_called_once()
            assert result.shape == (0, 1)
            assert result.dtype == np.float32

    def test_record_until_stop_returns_concatenated_blocks_when_callback_invoked(
        self,
    ) -> None:
        """When callback invoked with blocks, record_until_stop returns concatenated array."""
        # Arrange - capture callback and invoke it with one block; then set stop_event
        stop_ev = threading.Event()
        callback_holder: list = []
        block = np.array([[0.1], [0.2]], dtype=np.float32)

        def capture_stream(*_args: object, **kwargs: object) -> mock.Mock:
            callback_holder.append(kwargs.get("callback"))
            stream = mock.Mock()
            stream.start = mock.Mock()
            stream.stop = mock.Mock()
            stream.close = mock.Mock()

            def start_side_effect() -> None:
                cb = callback_holder[0]
                if cb:
                    cb(block, 2, None, None)
                stop_ev.set()

            stream.start.side_effect = start_side_effect
            return stream

        mock_sd = mock.Mock()
        mock_sd.InputStream.side_effect = capture_stream
        with mock.patch("vox.capture.stream._sd", return_value=mock_sd):
            # Act - call record_until_stop; callback will run once then stop_event set
            result = record_until_stop(stop_ev, sample_rate=16000, channels=1)
            # Assert - one block (2 frames, 1 channel)
            assert result.shape == (2, 1)
            assert result.dtype == np.float32
            np.testing.assert_array_almost_equal(result[:, 0], [0.1, 0.2])


@pytest.mark.unit
class TestRecordSeconds:
    """record_seconds() returns float32 array."""

    @pytest.mark.usefixtures("requires_audio")
    def test_returns_float32_array(self) -> None:
        """record_seconds returns numpy array float32 with expected shape."""
        # Arrange - pick a short duration to keep test fast
        seconds = 0.1

        # Act - record samples
        samples = record_seconds(seconds, sample_rate=16000, channels=1)

        # Assert - dtype and shape
        assert isinstance(samples, np.ndarray)
        assert samples.dtype == np.float32
        assert samples.ndim == 2  # (frames, channels)
        assert samples.shape[1] == 1
        assert samples.shape[0] == int(seconds * 16000)

    @pytest.mark.usefixtures("requires_audio")
    def test_record_accepts_device_id_none(self) -> None:
        """record_seconds(..., device_id=None) uses default device."""
        # Arrange - choose small duration and default device
        seconds = 0.05

        # Act - record with device_id None
        samples = record_seconds(seconds, device_id=None, sample_rate=16000)

        # Assert - expected frame count
        assert samples.shape[0] == int(seconds * 16000)


@pytest.mark.unit
class TestPlayBack:
    """play_back() does not raise for valid input.

    These tests intentionally assert the *absence of an exception*.

    Rationale:
    - `play_back()` is a side-effecting function (it hands audio to the OS / device).
      In unit tests, we can't reliably assert "audio was audible" or "device played"
      across environments.
    - The contract we *can* enforce here is: for valid, well-formed sample arrays,
      the function should accept the input and return without error.

    What this does NOT validate:
    - actual audio output, timing, device selection, or host API behavior.
      Those belong in integration/e2e testing (or manual verification).
    """

    @pytest.mark.usefixtures("requires_audio")
    def test_play_back_accepts_mono_array(self) -> None:
        """play_back(samples) with (n,) or (n,1) does not raise."""
        # Arrange - generate silent mono samples
        mono = np.zeros(1600, dtype=np.float32)  # 0.1 s at 16 kHz

        # Act - play back
        play_back(mono, sample_rate=16000)

        # Assert - no exception (implicit in pytest: exceptions fail the test)

    @pytest.mark.usefixtures("requires_audio")
    def test_play_back_accepts_stereo_shape(self) -> None:
        """play_back with (n, 1) works."""
        # Arrange - generate silent (n, 1) samples
        mono = np.zeros((1600, 1), dtype=np.float32)

        # Act - play back
        play_back(mono, sample_rate=16000)

        # Assert - no exception (implicit in pytest: exceptions fail the test)
