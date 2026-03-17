"""CLI entry: thin wrapper that delegates to vox.commands."""

from __future__ import annotations

import sys

import typer
from rich.console import Console

from vox.commands import handle_devices, handle_run, handle_test_mic
from vox.config import ConfigError
from vox.transcribe import TranscriptionError

app = typer.Typer(
    name="vox",
    help="Vox: voice input layer — capture, transcribe, inject.",
)
console = Console()


@app.command()
def devices() -> None:
    """List available audio input devices (for config device_id).

    On Windows the same device may appear multiple times (once per host API
    such as MME, DirectSound, WASAPI); use the Host API column to choose.

    Raises:
        Exit: Exit with code 1 if listing devices fails (typer.Exit).
    """
    try:
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
    Press Ctrl+C to exit.

    Raises:
        Exit: Code 1 if config is invalid or model fails to load (typer.Exit).
    """
    try:
        handle_run(console)
    except ConfigError as e:
        console.print(f"[red]Config error:[/red] {e}")
        raise typer.Exit(1) from e
    except TranscriptionError as e:
        console.print(f"[red]Model error:[/red] {e}")
        raise typer.Exit(1) from e
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
        sys.exit(0)


def main() -> None:
    """Entry point for the vox CLI."""
    app()


if __name__ == "__main__":
    main()
