"""Unit tests for standalone settings launch helpers."""

from __future__ import annotations

from unittest import mock

import pytest
from rich.console import Console

from vox.gui import settings_launcher, stop_window, tray


@pytest.mark.unit
class TestSettingsLauncher:
    """settings_launcher handles direct and detached launch modes."""

    def test_run_settings_window_direct_calls_window_module(self) -> None:
        """Direct CLI launch should import and run the settings window."""
        # Arrange - a fake settings window module with a run entrypoint
        fake_module = mock.Mock()

        with mock.patch.object(
            settings_launcher,
            "_settings_window_module",
            return_value=fake_module,
        ):
            # Act - run settings directly in-process
            settings_launcher.run_settings_window_direct()

        # Assert - the settings window entrypoint was invoked once
        fake_module.run_settings_window.assert_called_once_with()

    def test_launch_settings_subprocess_uses_module_entrypoint(self) -> None:
        """Runtime launch should spawn a detached ``python -m vox settings`` process."""
        # Arrange - capture subprocess launch arguments
        popen_factory = mock.Mock(return_value=object())
        fake_startupinfo = mock.Mock(dwFlags=0, wShowWindow=0)

        with (
            mock.patch.object(
                settings_launcher,
                "_popen_platform_kwargs",
                return_value={"creationflags": 0},
            ),
            mock.patch.object(
                settings_launcher,
                "_settings_subprocess_executable",
                return_value=settings_launcher.sys.executable,
            ),
            mock.patch.object(
                settings_launcher,
                "_windows_startupinfo",
                return_value=fake_startupinfo,
            ),
        ):
            # Act - launch the detached settings subprocess
            settings_launcher.launch_settings_subprocess(popen_factory=popen_factory)

        # Assert - the subprocess command targets the standalone settings command
        popen_factory.assert_called_once()
        launch_command = popen_factory.call_args.args[0]
        assert launch_command == [
            settings_launcher.sys.executable,
            "-m",
            "vox",
            "settings",
        ]
        assert popen_factory.call_args.kwargs["startupinfo"] is fake_startupinfo

    def test_launch_settings_subprocess_raises_settings_launch_error_on_oserror(
        self,
    ) -> None:
        """Launcher failures should surface as SettingsLaunchError."""
        # Arrange - a failing subprocess factory
        popen_factory = mock.Mock(side_effect=OSError("denied"))

        with (
            mock.patch.object(
                settings_launcher,
                "_popen_platform_kwargs",
                return_value={"creationflags": 0},
            ),
            pytest.raises(settings_launcher.SettingsLaunchError, match="denied"),
        ):
            # Act - attempt to launch settings through a failing subprocess call
            settings_launcher.launch_settings_subprocess(popen_factory=popen_factory)

        # Assert - SettingsLaunchError wraps subprocess startup failures

    def test_launch_settings_from_runtime_prints_user_visible_error(self) -> None:
        """Tray and stop-window launch failures should print a user-facing error."""
        # Arrange - runtime console with a failing subprocess launcher
        console = mock.Mock(spec=Console)

        with mock.patch.object(
            settings_launcher,
            "launch_settings_subprocess",
            side_effect=settings_launcher.SettingsLaunchError("boom"),
        ):
            # Act - launch settings from a runtime surface
            succeeded = settings_launcher.launch_settings_from_runtime(console)

        # Assert - the failure is reported without raising
        assert succeeded is False
        console.print.assert_called_once()


@pytest.mark.unit
class TestRuntimeAffordances:
    """Runtime surfaces route settings launches through the shared helper."""

    def test_tray_launch_helper_routes_through_shared_runtime_launcher(self) -> None:
        """The tray callback should delegate to the shared non-blocking launcher."""
        # Arrange - tray console and a patched runtime launcher
        console = mock.Mock(spec=Console)

        with mock.patch(
            "vox.gui.tray.launch_settings_from_runtime",
            return_value=True,
        ) as mock_launch:
            # Act - trigger the tray settings helper
            succeeded = tray._launch_settings(console)

        # Assert - the tray uses the shared runtime launcher helper
        assert succeeded is True
        mock_launch.assert_called_once_with(console)

    def test_stop_window_launch_helper_routes_through_shared_runtime_launcher(
        self,
    ) -> None:
        """The stop-window settings action should delegate to the shared launcher."""
        # Arrange - stop-window console and patched runtime launcher
        console = mock.Mock(spec=Console)

        with mock.patch(
            "vox.gui.stop_window.launch_settings_from_runtime",
            return_value=True,
        ) as mock_launch:
            # Act - trigger the stop-window settings helper
            succeeded = stop_window._launch_settings(console)

        # Assert - the stop window uses the shared runtime launcher helper
        assert succeeded is True
        mock_launch.assert_called_once_with(console)
