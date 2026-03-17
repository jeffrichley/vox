"""CLI entry: vox devices, vox test-mic, vox run (Phase 3)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from vox.capture import list_devices, play_back, record_seconds
from vox.config import get_transcription_options
from vox.transcribe import transcribe

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
    table = Table(title="Audio input devices")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Host API", style="dim")
    try:
        devs = list_devices()
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    for dev_id, name, host_api in devs:
        table.add_row(str(dev_id), name, host_api)
    if not devs:
        console.print("[yellow]No input devices found.[/yellow]")
    else:
        console.print(table)


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
    if seconds <= 0:
        console.print("[red]Error:[/red] --seconds must be positive.")
        raise typer.Exit(1)
    try:
        console.print(f"Recording for [bold]{seconds}[/bold] seconds...")
        samples = record_seconds(seconds, device_id=device)
        console.print("Playing back...")
        play_back(samples)
        opts = get_transcription_options()
        console.print("Transcribing...")
        text = transcribe(
            samples,
            model_size_or_path=opts.model_size,
            device=opts.compute_device,
            compute_type=opts.compute_type,
        )
        if text:
            console.print("[bold]Transcription:[/bold]", text)
        else:
            console.print("[dim]Transcription: (no speech detected)[/dim]")
        console.print("[green]Done.[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


def main() -> None:
    """Entry point for the vox CLI."""
    app()


if __name__ == "__main__":
    main()
