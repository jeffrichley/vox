"""CLI entry: thin wrapper that delegates to vox.commands."""

from __future__ import annotations

import typer
from rich.console import Console

from vox.config import ConfigError, get_config


class RunWindowError(Exception):
    """Run stop-window worker failed before the user clicked Stop.

    The cause (e.g. ConfigError, TranscriptionError) is available as __cause__.
    """

    pass


app = typer.Typer(
    name="vox",
    help="Vox: voice input layer — capture, transcribe, inject.",
)
console = Console()


def _run_impl() -> None:
    """Run push-to-talk (tray or stop window + worker).

    Uses tray if config or VOX_TRAY has use_tray enabled; otherwise the Tk stop
    window. Same error handling for both.

    Raises:
        Exit: Code 1 if config is invalid or the worker failed (e.g. model error).
    """
    # IMPORTANT: keep GUI / input-hook imports lazy.
    # `./dist/vox/vox --help` still imports `vox.cli` via `vox.__main__`, so any
    # import-time side effects (e.g. `pynput` selecting an X backend) would break
    # help in headless environments.
    from vox.gui import run_stop_window, run_tray
    from vox.transcribe import TranscriptionError

    try:
        cfg = get_config()
    except ConfigError as e:
        console.print(f"[red]Config error:[/red] {e}")
        raise typer.Exit(1) from e
    use_tray = cfg.get("use_tray", False)
    runner = run_tray if use_tray else run_stop_window
    try:
        err = runner(console)
        if err is not None:
            raise RunWindowError() from err
    except RunWindowError as e:
        cause = e.__cause__
        if isinstance(cause, ConfigError):
            console.print(f"[red]Config error:[/red] {cause}")
        elif isinstance(cause, TranscriptionError):
            console.print(f"[red]Model error:[/red] {cause}")
        elif cause is not None:
            console.print(f"[red]Error:[/red] {cause}")
        raise typer.Exit(1) from e


@app.callback(invoke_without_command=True)
def _default_callback(ctx: typer.Context) -> None:
    """When no subcommand is given, run push-to-talk (same as `vox run`).

    Args:
        ctx: Typer context; used to detect if a subcommand was invoked.
    """
    # During Click/Typer help/usage generation, Click performs a resilient parse
    # pass. In that mode we must not start the capture/transcribe/inject loop.
    if getattr(ctx, "resilient_parsing", False):
        return
    if ctx.invoked_subcommand is not None:
        return
    _run_impl()


@app.command()
def devices() -> None:
    """List available audio input devices (for config device_id).

    On Windows the same device may appear multiple times (once per host API
    such as MME, DirectSound, WASAPI); use the Host API column to choose.

    Raises:
        Exit: Exit with code 1 if listing devices fails (typer.Exit).
    """
    try:
        from vox.commands import handle_devices

        handle_devices(console)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command("test-mic")
def test_mic(
    device: int | None = typer.Option(
        None, "--device", "-d", help="Device ID from `vox devices`"
    ),
    seconds: float = typer.Option(
        2.0, "--seconds", "-s", help="Record duration in seconds"
    ),
) -> None:
    """Record for N seconds, play back, then transcribe and print text.

    Args:
        device: Optional device ID from `vox devices`.
        seconds: Record duration in seconds.

    Raises:
        Exit: Code 1 if seconds <= 0 or on capture/transcribe error (typer.Exit).
    """
    try:
        from vox.commands import handle_test_mic

        handle_test_mic(console, device_id=device, seconds=seconds)
    except (ValueError, ConfigError, TranscriptionError, RuntimeError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def run() -> None:
    """Start push-to-talk: press hotkey to record, release to transcribe and inject.

    Loads config from ~/.vox/vox.toml (or VOX_CONFIG). On each hotkey release,
    recorded audio is transcribed and placed on the clipboard (and optionally
    pasted into the focused window if injection_mode is clipboard_and_paste).
    A small window with a Stop button is shown to exit. Exits with code 1 if
    the worker failed (e.g. config or model error).
    """
    _run_impl()


def main() -> None:
    """Entry point for the vox CLI."""
    app()


if __name__ == "__main__":
    main()
