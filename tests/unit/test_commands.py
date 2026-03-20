"""Unit tests for handle_devices, handle_test_mic, handle_run."""
# drill-sergeant: file-length ignore

from __future__ import annotations

import threading
from unittest import mock

import numpy as np
import pytest

from vox.commands import handle_devices, handle_run, handle_test_mic
from vox.inject import InjectError
from vox.transcribe import TranscriptionError


@pytest.mark.unit
class TestHandleDevices:
    """handle_devices prints a Rich table or no-devices message."""

    def test_handle_devices_prints_table_when_devices_found(self) -> None:
        """When list_devices returns data, console.print is called with a table."""
        # Arrange - mock console and list_devices returning one device
        mock_console = mock.Mock()
        with mock.patch("vox.commands.list_devices") as mock_list:
            mock_list.return_value = [(0, "Default Mic", "MME")]

            # Act - call handle_devices
            handle_devices(mock_console)

            # Assert - print called once with table whose title mentions devices
            mock_console.print.assert_called_once()
            (arg,) = mock_console.print.call_args[0]
            assert "Audio input devices" in str(getattr(arg, "title", ""))

    def test_handle_devices_prints_warning_when_no_devices(self) -> None:
        """When list_devices returns empty, console prints no-devices message."""
        # Arrange - mock console and list_devices returning empty list
        mock_console = mock.Mock()
        with mock.patch("vox.commands.list_devices") as mock_list:
            mock_list.return_value = []

            # Act - call handle_devices
            handle_devices(mock_console)

            # Assert - print called with message containing no devices
            mock_console.print.assert_called_once()
            call_args = mock_console.print.call_args[0][0]
            assert "No input devices" in call_args


@pytest.mark.unit
class TestHandleTestMic:
    """handle_test_mic records, plays back, transcribes and prints."""

    def test_handle_test_mic_prints_transcription_when_speech_detected(self) -> None:
        """When transcribe returns text, console prints transcription and Done."""
        # Arrange - mock record, play_back, get_transcription_options, transcribe
        mock_console = mock.Mock()
        samples = np.zeros(1600, dtype=np.float32)
        with (
            mock.patch("vox.commands.record_seconds", return_value=samples),
            mock.patch("vox.commands.play_back"),
            mock.patch("vox.commands.get_transcription_options") as mock_opts,
            mock.patch("vox.commands.transcribe", return_value="hello world"),
        ):
            mock_opts.return_value = mock.Mock(
                model_size="base",
                compute_device="cpu",
                compute_type="float32",
            )

            # Act - call handle_test_mic
            handle_test_mic(mock_console, device_id=None, seconds=1.0)

            # Assert - Recording, Playing, Transcribing, Transcription text, Done printed
            assert mock_console.print.call_count >= 4
            calls = [str(c) for c in mock_console.print.call_args_list]
            assert any("Transcription" in c and "hello" in c for c in calls)
            assert any("Done" in c for c in calls)

    def test_handle_test_mic_prints_no_speech_when_transcribe_empty(self) -> None:
        """When transcribe returns empty string, console prints no speech detected."""
        # Arrange - mock transcribe to return empty
        mock_console = mock.Mock()
        samples = np.zeros(1600, dtype=np.float32)
        with (
            mock.patch("vox.commands.record_seconds", return_value=samples),
            mock.patch("vox.commands.play_back"),
            mock.patch("vox.commands.get_transcription_options") as mock_opts,
            mock.patch("vox.commands.transcribe", return_value=""),
        ):
            mock_opts.return_value = mock.Mock(
                model_size="base",
                compute_device="cpu",
                compute_type="float32",
            )

            # Act - call handle_test_mic
            handle_test_mic(mock_console, device_id=None, seconds=1.0)

            # Assert - no speech detected path printed
            calls = [str(c) for c in mock_console.print.call_args_list]
            assert any("no speech" in c.lower() for c in calls)

    def test_handle_test_mic_raises_when_seconds_zero(self) -> None:
        """When seconds <= 0, handle_test_mic raises ValueError with message about positive."""
        # Arrange - seconds is 0
        mock_console = mock.Mock()

        # Act - call handle_test_mic with zero seconds
        # Assert - ValueError with positive or seconds in message
        with pytest.raises(ValueError, match=r"positive|seconds"):
            handle_test_mic(mock_console, device_id=None, seconds=0.0)

    def test_handle_test_mic_raises_when_seconds_negative(self) -> None:
        """When seconds < 0, handle_test_mic raises ValueError."""
        # Arrange - mock console and negative seconds
        mock_console = mock.Mock()

        # Act - call handle_test_mic with negative seconds
        # Assert - ValueError raised
        with pytest.raises(ValueError, match=r"positive|seconds"):
            handle_test_mic(mock_console, device_id=None, seconds=-1.0)


@pytest.mark.unit
class TestHandleRun:
    """handle_run loads config, model, and runs push-to-talk loop until stop_event."""

    def test_handle_run_exits_when_stop_event_set_immediately(self) -> None:
        """When stop_event is set right away, handle_run returns after printing panel."""
        # Arrange - mock get_config, load_model, run_push_to_talk_loop; stop_event set
        mock_console = mock.Mock()
        stop_ev = threading.Event()
        stop_ev.set()
        with (
            mock.patch("vox.commands.get_config") as mock_cfg,
            mock.patch("vox.commands.load_model"),
            mock.patch("vox.commands._run_push_to_talk_loop") as mock_loop,
        ):
            mock_cfg.return_value = {
                "hotkey": "ctrl+v",
                "device_id": None,
                "model_size": "base",
                "compute_type": "float32",
                "compute_device": "cpu",
                "injection_mode": "clipboard",
            }

            # Act - call handle_run with stop_event
            handle_run(mock_console, stop_event=stop_ev)

            # Assert - run_push_to_talk_loop called with stop_event; panel printed
            mock_loop.assert_called_once()
            assert mock_loop.call_args[1]["stop_event"] is stop_ev
            assert mock_console.print.call_count >= 1

    def test_on_audio_transcribes_sets_clipboard_and_prints_injected(self) -> None:
        """When on_audio is invoked with speech, it transcribes, sets clipboard, prints Injected."""
        # Arrange - capture on_audio from handle_run via run_push_to_talk_loop mock
        mock_console = mock.Mock()
        stop_ev = threading.Event()
        stop_ev.set()
        on_audio_captured: list = []

        def capture_loop(**kwargs: object) -> None:
            on_audio_captured.append(kwargs.get("on_audio"))

        with (
            mock.patch("vox.commands.get_config") as mock_cfg,
            mock.patch("vox.commands.load_model"),
            mock.patch("vox.commands._run_push_to_talk_loop", side_effect=capture_loop),
        ):
            mock_cfg.return_value = {
                "hotkey": "ctrl+v",
                "device_id": None,
                "model_size": "base",
                "compute_type": "float32",
                "compute_device": "cpu",
                "injection_mode": "clipboard",
            }
            handle_run(mock_console, stop_event=stop_ev)

        assert len(on_audio_captured) == 1
        on_audio = on_audio_captured[0]
        assert on_audio is not None

        # Act - call on_audio with buffer; transcribe returns text, set_clipboard succeeds
        with (
            mock.patch("vox.commands.transcribe", return_value="hello"),
            mock.patch("vox.commands.set_clipboard") as mock_set,
        ):
            on_audio(np.zeros(1600, dtype=np.float32))
            # Assert - set_clipboard called with transcribed text
            mock_set.assert_called_once_with("hello")
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("Injected" in c for c in calls)

    def test_on_audio_prints_transcription_error_and_returns(self) -> None:
        """When transcribe raises TranscriptionError, on_audio prints error and returns."""
        # Arrange - capture on_audio
        mock_console = mock.Mock()
        stop_ev = threading.Event()
        stop_ev.set()
        on_audio_captured: list = []

        def capture_loop(**kwargs: object) -> None:
            on_audio_captured.append(kwargs.get("on_audio"))

        with (
            mock.patch("vox.commands.get_config") as mock_cfg,
            mock.patch("vox.commands.load_model"),
            mock.patch("vox.commands._run_push_to_talk_loop", side_effect=capture_loop),
        ):
            mock_cfg.return_value = {
                "hotkey": "ctrl+v",
                "device_id": None,
                "model_size": "base",
                "compute_type": "float32",
                "compute_device": "cpu",
                "injection_mode": "clipboard",
            }
            handle_run(mock_console, stop_event=stop_ev)

        on_audio = on_audio_captured[0]
        assert on_audio is not None

        # Act - invoke on_audio while transcribe raises TranscriptionError
        with mock.patch(
            "vox.commands.transcribe",
            side_effect=TranscriptionError("model load failed"),
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - red Transcription error printed, set_clipboard not called
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any(
            "Transcription error" in c or "transcription" in c.lower() for c in calls
        )

    def test_on_audio_prints_no_speech_when_transcribe_returns_empty(self) -> None:
        """When transcribe returns empty/whitespace, on_audio prints no speech and returns."""
        # Arrange - mock console and capture on_audio from handle_run with clipboard mode
        mock_console = mock.Mock()
        stop_ev = threading.Event()
        stop_ev.set()
        on_audio_captured: list = []

        def capture_loop(**kwargs: object) -> None:
            on_audio_captured.append(kwargs.get("on_audio"))

        with (
            mock.patch("vox.commands.get_config") as mock_cfg,
            mock.patch("vox.commands.load_model"),
            mock.patch("vox.commands._run_push_to_talk_loop", side_effect=capture_loop),
        ):
            mock_cfg.return_value = {
                "hotkey": "ctrl+v",
                "device_id": None,
                "model_size": "base",
                "compute_type": "float32",
                "compute_device": "cpu",
                "injection_mode": "clipboard",
            }
            handle_run(mock_console, stop_event=stop_ev)

        on_audio = on_audio_captured[0]
        assert on_audio is not None

        # Act - invoke on_audio with transcribe returning whitespace-only
        with mock.patch("vox.commands.transcribe", return_value="   "):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - no speech detected message printed
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("No speech" in c or "no speech" in c.lower() for c in calls)

    def test_on_audio_prints_clipboard_error_when_set_clipboard_raises(self) -> None:
        """When set_clipboard raises InjectError, on_audio prints clipboard error and returns."""
        # Arrange - mock console and capture on_audio from handle_run
        mock_console = mock.Mock()
        stop_ev = threading.Event()
        stop_ev.set()
        on_audio_captured: list = []

        def capture_loop(**kwargs: object) -> None:
            on_audio_captured.append(kwargs.get("on_audio"))

        with (
            mock.patch("vox.commands.get_config") as mock_cfg,
            mock.patch("vox.commands.load_model"),
            mock.patch("vox.commands._run_push_to_talk_loop", side_effect=capture_loop),
        ):
            mock_cfg.return_value = {
                "hotkey": "ctrl+v",
                "device_id": None,
                "model_size": "base",
                "compute_type": "float32",
                "compute_device": "cpu",
                "injection_mode": "clipboard",
            }
            handle_run(mock_console, stop_event=stop_ev)

        on_audio = on_audio_captured[0]
        assert on_audio is not None

        # Act - invoke on_audio while set_clipboard raises InjectError
        with (
            mock.patch("vox.commands.transcribe", return_value="hi"),
            mock.patch(
                "vox.commands.set_clipboard",
                side_effect=InjectError("clipboard failed"),
            ),
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - Clipboard error printed
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("Clipboard error" in c or "clipboard" in c.lower() for c in calls)

    def test_on_audio_calls_paste_and_prints_yellow_when_paste_fails(self) -> None:
        """When injection_mode is clipboard_and_paste and paste_into_focused raises, print yellow."""
        # Arrange - mock console and capture on_audio with clipboard_and_paste mode
        mock_console = mock.Mock()
        stop_ev = threading.Event()
        stop_ev.set()
        on_audio_captured: list = []

        def capture_loop(**kwargs: object) -> None:
            on_audio_captured.append(kwargs.get("on_audio"))

        with (
            mock.patch("vox.commands.get_config") as mock_cfg,
            mock.patch("vox.commands.load_model"),
            mock.patch("vox.commands._run_push_to_talk_loop", side_effect=capture_loop),
        ):
            mock_cfg.return_value = {
                "hotkey": "ctrl+v",
                "device_id": None,
                "model_size": "base",
                "compute_type": "float32",
                "compute_device": "cpu",
                "injection_mode": "clipboard_and_paste",
            }
            handle_run(mock_console, stop_event=stop_ev)

        on_audio = on_audio_captured[0]
        assert on_audio is not None

        # Act - invoke on_audio with clipboard_and_paste and paste_into_focused raising
        with (
            mock.patch("vox.commands.transcribe", return_value="hi"),
            mock.patch("vox.commands.set_clipboard"),
            mock.patch(
                "vox.commands.paste_into_focused",
                side_effect=InjectError("paste failed"),
            ),
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - Paste failed or yellow printed; Injected still printed
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any(
            "Paste failed" in c or "paste" in c.lower() or "yellow" in c for c in calls
        )
        assert any("Injected" in c for c in calls)

    def test_on_audio_types_directly_without_touching_clipboard(self) -> None:
        """When injection_mode is type, the text is typed directly and clipboard is skipped."""
        # Arrange - mock console and capture on_audio with direct typing mode
        mock_console = mock.Mock()
        stop_ev = threading.Event()
        stop_ev.set()
        on_audio_captured: list = []

        def capture_loop(**kwargs: object) -> None:
            on_audio_captured.append(kwargs.get("on_audio"))

        with (
            mock.patch("vox.commands.get_config") as mock_cfg,
            mock.patch("vox.commands.load_model"),
            mock.patch("vox.commands._run_push_to_talk_loop", side_effect=capture_loop),
        ):
            mock_cfg.return_value = {
                "hotkey": "ctrl+v",
                "device_id": None,
                "model_size": "base",
                "compute_type": "float32",
                "compute_device": "cpu",
                "injection_mode": "type",
            }
            handle_run(mock_console, stop_event=stop_ev)

        on_audio = on_audio_captured[0]
        assert on_audio is not None

        # Act - invoke on_audio while direct typing succeeds
        with (
            mock.patch("vox.commands.transcribe", return_value="hello"),
            mock.patch("vox.commands.type_into_focused") as mock_type,
            mock.patch("vox.commands.set_clipboard") as mock_set_clipboard,
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - direct typing used and clipboard skipped
        mock_type.assert_called_once_with("hello")
        mock_set_clipboard.assert_not_called()
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("Injected" in c for c in calls)

    def test_on_audio_prints_typing_error_when_direct_typing_fails(self) -> None:
        """When injection_mode is type and typing fails, an actionable error is printed."""
        # Arrange - mock console and capture on_audio with direct typing mode
        mock_console = mock.Mock()
        stop_ev = threading.Event()
        stop_ev.set()
        on_audio_captured: list = []

        def capture_loop(**kwargs: object) -> None:
            on_audio_captured.append(kwargs.get("on_audio"))

        with (
            mock.patch("vox.commands.get_config") as mock_cfg,
            mock.patch("vox.commands.load_model"),
            mock.patch("vox.commands._run_push_to_talk_loop", side_effect=capture_loop),
        ):
            mock_cfg.return_value = {
                "hotkey": "ctrl+v",
                "device_id": None,
                "model_size": "base",
                "compute_type": "float32",
                "compute_device": "cpu",
                "injection_mode": "type",
            }
            handle_run(mock_console, stop_event=stop_ev)

        on_audio = on_audio_captured[0]
        assert on_audio is not None

        # Act - invoke on_audio while direct typing fails
        with (
            mock.patch("vox.commands.transcribe", return_value="hello"),
            mock.patch(
                "vox.commands.type_into_focused",
                side_effect=InjectError("access denied"),
            ),
            mock.patch("vox.commands.set_clipboard") as mock_set_clipboard,
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - typing error printed and clipboard still skipped
        mock_set_clipboard.assert_not_called()
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("Typing error" in c or "typing" in c.lower() for c in calls)
