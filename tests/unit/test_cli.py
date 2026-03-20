"""Unit tests for CLI entry (run error handling, devices, test_mic)."""

from __future__ import annotations

from unittest import mock

import pytest
import typer

from vox.cli import devices, run
from vox.cli import test_mic as cli_test_mic  # alias so pytest does not collect as test
from vox.config import ConfigError
from vox.transcribe import TranscriptionError


@pytest.mark.unit
class TestDevicesCommand:
    """devices() lists input devices or exits 1 on RuntimeError."""

    def test_devices_exits_1_when_handle_devices_raises_runtime_error(self) -> None:
        """When handle_devices raises RuntimeError, devices exits 1."""
        # Arrange - handle_devices raises RuntimeError
        mock_commands = mock.Mock()
        mock_commands.handle_devices.side_effect = RuntimeError("no audio devices")
        with mock.patch("vox.cli._commands_module", return_value=mock_commands):
            # Act - call devices (will raise Exit)
            # Assert - Exit(1)
            with pytest.raises(typer.Exit) as exc_info:
                devices()
            assert exc_info.value.exit_code == 1

    def test_devices_exits_1_and_prints_error_on_runtime_error(self) -> None:
        """When handle_devices raises RuntimeError, console.print is called with Error."""
        # Arrange - mock console and handle_devices raises
        mock_commands = mock.Mock()
        mock_commands.handle_devices.side_effect = RuntimeError("no devices")
        with (
            mock.patch("vox.cli.console") as mock_console,
            mock.patch("vox.cli._commands_module", return_value=mock_commands),
        ):
            # Act - call devices
            with pytest.raises(typer.Exit):
                devices()
            # Assert - print was called with Error and exception text
            mock_console.print.assert_called()
            call_str = str(mock_console.print.call_args)
            assert "Error" in call_str or "red" in call_str
            assert "no devices" in call_str


@pytest.mark.unit
class TestTestMicCommand:
    """test_mic() records, plays, transcribes; exits 1 on validation or runtime error."""

    def test_test_mic_exits_1_when_handle_test_mic_raises_value_error(self) -> None:
        """When handle_test_mic raises ValueError (e.g. seconds<=0), test_mic exits 1."""
        # Arrange - handle_test_mic raises ValueError
        mock_commands = mock.Mock()
        mock_commands.handle_test_mic.side_effect = ValueError(
            "seconds must be positive"
        )
        with mock.patch("vox.cli._commands_module", return_value=mock_commands):
            # Act - call test_mic command
            with pytest.raises(typer.Exit) as exc_info:
                cli_test_mic(device=None, seconds=1.0)
            # Assert - exit code 1
            assert exc_info.value.exit_code == 1

    def test_test_mic_exits_1_when_handle_test_mic_raises_config_error(self) -> None:
        """When handle_test_mic raises ConfigError, test_mic exits 1."""
        # Arrange - patch handle_test_mic to raise ConfigError
        mock_commands = mock.Mock()
        mock_commands.handle_test_mic.side_effect = ConfigError("bad config")
        with mock.patch("vox.cli._commands_module", return_value=mock_commands):
            # Act - call test_mic command
            with pytest.raises(typer.Exit) as exc_info:
                cli_test_mic(device=None, seconds=1.0)
            # Assert - exit code 1
            assert exc_info.value.exit_code == 1

    def test_test_mic_exits_1_when_handle_test_mic_raises_transcription_error(
        self,
    ) -> None:
        """When handle_test_mic raises TranscriptionError, test_mic exits 1."""
        # Arrange - handle_test_mic raises TranscriptionError
        mock_commands = mock.Mock()
        mock_commands.handle_test_mic.side_effect = TranscriptionError(
            "model not found"
        )
        with mock.patch("vox.cli._commands_module", return_value=mock_commands):
            # Act - call test_mic command
            with pytest.raises(typer.Exit) as exc_info:
                cli_test_mic(device=None, seconds=1.0)
            # Assert - exit code 1
            assert exc_info.value.exit_code == 1

    def test_test_mic_exits_1_when_handle_test_mic_raises_runtime_error(self) -> None:
        """When handle_test_mic raises RuntimeError, test_mic exits 1."""
        # Arrange - handle_test_mic raises RuntimeError
        mock_commands = mock.Mock()
        mock_commands.handle_test_mic.side_effect = RuntimeError("audio failed")
        with mock.patch("vox.cli._commands_module", return_value=mock_commands):
            # Act - call test_mic command
            with pytest.raises(typer.Exit) as exc_info:
                cli_test_mic(device=None, seconds=1.0)
            # Assert - exit code 1
            assert exc_info.value.exit_code == 1

    def test_test_mic_prints_error_message_on_failure(self) -> None:
        """When handle_test_mic raises, console.print is called with error."""
        # Arrange - mock console and handle_test_mic raising ValueError
        mock_commands = mock.Mock()
        mock_commands.handle_test_mic.side_effect = ValueError(
            "seconds must be positive"
        )
        with (
            mock.patch("vox.cli.console") as mock_console,
            mock.patch("vox.cli._commands_module", return_value=mock_commands),
        ):
            # Act - call test_mic command
            with pytest.raises(typer.Exit):
                cli_test_mic(device=None, seconds=1.0)
            # Assert - console printed and message contains Error and seconds
            mock_console.print.assert_called()
            call_str = str(mock_console.print.call_args)
            assert "Error" in call_str or "red" in call_str
            assert "seconds" in call_str


@pytest.mark.unit
class TestRunCommand:
    """run() handles RunWindowError and exits with code 1."""

    def test_run_exits_when_run_stop_window_returns_config_error(self) -> None:
        """When run_stop_window returns a ConfigError, run prints and exits 1."""
        # Arrange - use stop-window path (not tray) and run_stop_window returns ConfigError
        cause = ConfigError("missing hotkey")
        mock_run_stop_window = mock.Mock(return_value=cause)
        with (
            mock.patch("vox.cli.get_config", return_value={"use_tray": False}),
            mock.patch(
                "vox.cli._gui_runners",
                return_value=(mock_run_stop_window, mock.Mock()),
            ),
        ):
            # Act - call run (will raise Exit)
            # Assert - Exit(1) raised
            with pytest.raises(typer.Exit) as exc_info:
                run()
            assert exc_info.value.exit_code == 1

    def test_run_exits_when_run_stop_window_returns_transcription_error(self) -> None:
        """When run_stop_window returns a TranscriptionError, run prints and exits 1."""
        # Arrange - use stop-window path and run_stop_window returns TranscriptionError
        cause = TranscriptionError("model not found")
        mock_run_stop_window = mock.Mock(return_value=cause)
        with (
            mock.patch("vox.cli.get_config", return_value={"use_tray": False}),
            mock.patch(
                "vox.cli._gui_runners",
                return_value=(mock_run_stop_window, mock.Mock()),
            ),
        ):
            # Act - call run (will raise Exit)
            # Assert - Exit(1) raised
            with pytest.raises(typer.Exit) as exc_info:
                run()
            assert exc_info.value.exit_code == 1

    def test_run_exits_when_run_stop_window_returns_other_error(self) -> None:
        """When run_stop_window returns another exception, run exits 1."""
        # Arrange - use stop-window path and run_stop_window returns RuntimeError
        cause = RuntimeError("other")
        mock_run_stop_window = mock.Mock(return_value=cause)
        with (
            mock.patch("vox.cli.get_config", return_value={"use_tray": False}),
            mock.patch(
                "vox.cli._gui_runners",
                return_value=(mock_run_stop_window, mock.Mock()),
            ),
        ):
            # Act - call run (will raise Exit)
            # Assert - Exit(1) raised
            with pytest.raises(typer.Exit) as exc_info:
                run()
            assert exc_info.value.exit_code == 1

    def test_run_prints_config_error_when_cause_is_config_error(self) -> None:
        """When run_stop_window returns ConfigError, run prints Config error and exits 1."""
        # Arrange - use stop-window path and run_stop_window returns ConfigError
        cause = ConfigError("missing hotkey")
        mock_run_stop_window = mock.Mock(return_value=cause)
        with (
            mock.patch("vox.cli.get_config", return_value={"use_tray": False}),
            mock.patch("vox.cli.console") as mock_console,
            mock.patch(
                "vox.cli._gui_runners",
                return_value=(mock_run_stop_window, mock.Mock()),
            ),
        ):
            # Act - call run (will raise Exit)
            with pytest.raises(typer.Exit):
                run()
            # Assert - Config error message printed
            calls = [str(c) for c in mock_console.print.call_args_list]
            assert any("Config error" in c or "config" in c.lower() for c in calls)

    def test_run_prints_model_error_when_cause_is_transcription_error(self) -> None:
        """When run_stop_window returns TranscriptionError, run prints Model error, exits 1."""
        # Arrange - use stop-window path and run_stop_window returns TranscriptionError
        cause = TranscriptionError("model not found")
        mock_run_stop_window = mock.Mock(return_value=cause)
        with (
            mock.patch("vox.cli.get_config", return_value={"use_tray": False}),
            mock.patch("vox.cli.console") as mock_console,
            mock.patch(
                "vox.cli._gui_runners",
                return_value=(mock_run_stop_window, mock.Mock()),
            ),
        ):
            # Act - call run (will raise Exit)
            with pytest.raises(typer.Exit):
                run()
            # Assert - Model error message printed
            calls = [str(c) for c in mock_console.print.call_args_list]
            assert any("Model error" in c or "model" in c.lower() for c in calls)

    def test_run_prints_generic_error_when_cause_is_other(self) -> None:
        """When run_stop_window returns other exception, run prints Error and exits 1."""
        # Arrange - use stop-window path and run_stop_window returns RuntimeError
        cause = RuntimeError("other")
        mock_run_stop_window = mock.Mock(return_value=cause)
        with (
            mock.patch("vox.cli.get_config", return_value={"use_tray": False}),
            mock.patch("vox.cli.console") as mock_console,
            mock.patch(
                "vox.cli._gui_runners",
                return_value=(mock_run_stop_window, mock.Mock()),
            ),
        ):
            # Act - call run (will raise Exit)
            with pytest.raises(typer.Exit):
                run()
            # Assert - generic Error message printed
            calls = [str(c) for c in mock_console.print.call_args_list]
            assert any("Error" in c or "red" in c for c in calls)
