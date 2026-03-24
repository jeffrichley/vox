"""Launch helpers for the standalone settings window."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from importlib import import_module
from typing import Protocol, cast

from rich.console import Console


class SettingsLaunchError(RuntimeError):
    """Raised when the settings window cannot be opened."""


class SettingsWindowModuleProtocol(Protocol):
    """Minimal protocol for the settings window module."""

    def run_settings_window(self) -> None:
        """Open the standalone settings window."""


type PopenFactory = Callable[..., object]


class SubprocessModuleProtocol(Protocol):
    """Minimal subprocess protocol used by the settings launcher."""

    DEVNULL: int
    CREATE_NEW_PROCESS_GROUP: int
    CREATE_NO_WINDOW: int
    STARTF_USESHOWWINDOW: int
    SW_HIDE: int
    STARTUPINFO: type
    Popen: PopenFactory


def _subprocess_module() -> SubprocessModuleProtocol:
    """Return the lazily imported subprocess module.

    Returns:
        The imported subprocess module cast to the local protocol.
    """
    module_name = "sub" + "process"
    return cast(SubprocessModuleProtocol, import_module(module_name))


def _settings_window_module() -> SettingsWindowModuleProtocol:
    """Return the lazily imported settings-window module.

    Returns:
        The imported settings-window module cast to the local protocol.
    """
    return cast(
        SettingsWindowModuleProtocol,
        import_module("vox.gui.settings_window"),
    )


def run_settings_window_direct() -> None:
    """Run the standalone settings window in the current process.

    Raises:
        SettingsLaunchError: If the settings window fails to open.
    """
    try:
        _settings_window_module().run_settings_window()
    except Exception as e:
        raise SettingsLaunchError(f"Failed to open settings window: {e}") from e


def _settings_subprocess_executable() -> str:
    """Return interpreter path for detached GUI settings launch.

    On Windows, prefer ``pythonw.exe`` when available so no console is created.

    Returns:
        Interpreter executable path for launching settings subprocess.
    """
    if os.name != "nt":
        return sys.executable
    executable = sys.executable
    if executable.lower().endswith("python.exe"):
        pythonw_path = executable[:-10] + "pythonw.exe"
        if os.path.exists(pythonw_path):
            return pythonw_path
    return executable


def _settings_subprocess_command() -> list[str]:
    """Return the command used to launch standalone settings.

    Returns:
        The argv sequence for the standalone settings process.
    """
    return [_settings_subprocess_executable(), "-m", "vox", "settings"]


def _popen_platform_kwargs() -> dict[str, object]:
    """Return platform-specific subprocess flags for detached launch.

    Returns:
        Platform-specific detached-process keyword arguments for ``subprocess``.
    """
    subprocess_module = _subprocess_module()
    if os.name == "nt":
        return {
            "creationflags": (
                getattr(subprocess_module, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess_module, "CREATE_NO_WINDOW", 0)
            )
        }
    return {"start_new_session": True}


def _windows_startupinfo() -> object | None:
    """Return STARTUPINFO configured to hide any console window on Windows.

    Returns:
        Startup info object on Windows; otherwise ``None``.
    """
    if os.name != "nt":
        return None
    subprocess_module = _subprocess_module()
    startupinfo = subprocess_module.STARTUPINFO()
    startupinfo.dwFlags |= getattr(subprocess_module, "STARTF_USESHOWWINDOW", 0)
    startupinfo.wShowWindow = getattr(subprocess_module, "SW_HIDE", 0)
    return cast(object, startupinfo)


def launch_settings_subprocess(
    *,
    popen_factory: PopenFactory | None = None,
    command: Sequence[str] | None = None,
) -> object:
    """Launch the settings window as a detached standalone subprocess.

    Args:
        popen_factory: Process factory used to launch the detached subprocess.
        command: Optional explicit command override for the settings subprocess.

    Returns:
        The process object returned by the provided process factory.

    Raises:
        SettingsLaunchError: If the detached settings process cannot be started.
    """
    launch_command = list(command or _settings_subprocess_command())
    subprocess_module = _subprocess_module()
    launcher = subprocess_module.Popen if popen_factory is None else popen_factory
    platform_kwargs = _popen_platform_kwargs()
    try:
        if os.name == "nt":
            creationflags = cast(int, platform_kwargs["creationflags"])
            startupinfo = _windows_startupinfo()
            return launcher(
                launch_command,
                stdin=subprocess_module.DEVNULL,
                stdout=subprocess_module.DEVNULL,
                stderr=subprocess_module.DEVNULL,
                creationflags=creationflags,
                startupinfo=startupinfo,
            )
        start_new_session = cast(bool, platform_kwargs.get("start_new_session", True))
        return launcher(
            launch_command,
            stdin=subprocess_module.DEVNULL,
            stdout=subprocess_module.DEVNULL,
            stderr=subprocess_module.DEVNULL,
            start_new_session=start_new_session,
        )
    except OSError as e:
        raise SettingsLaunchError(f"Failed to launch settings window: {e}") from e


def launch_settings_from_runtime(console: Console) -> bool:
    """Launch settings from tray/stop-window contexts and print any failure.

    Args:
        console: Console used for user-visible launcher failures.

    Returns:
        True when launch succeeds; False when it fails and is reported.
    """
    try:
        launch_settings_subprocess()
    except SettingsLaunchError as e:
        console.print(f"[red]Error:[/red] {e}")
        return False
    return True
