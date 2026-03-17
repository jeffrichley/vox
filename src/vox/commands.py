"""Command implementations for the Vox CLI. Called by cli.py with a Rich console."""

from __future__ import annotations

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vox.capture import list_devices, play_back, record_seconds
from vox.config import get_config, get_transcription_options
from vox.hotkey import run_push_to_talk_loop
from vox.inject import InjectError, paste_into_focused, set_clipboard
from vox.transcribe import TranscriptionError, load_model, transcribe


def handle_devices(console: Console) -> None:
    """List available audio input devices in a Rich table.

    On Windows the same device may appear multiple times (once per host API).
    Use the Host API column to choose.

    Args:
        console: Rich console for output.
    """
    table = Table(title="Audio input devices")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Host API", style="dim")
    devs = list_devices()
    for dev_id, name, host_api in devs:
        table.add_row(str(dev_id), name, host_api)
    if not devs:
        console.print("[yellow]No input devices found.[/yellow]")
    else:
        console.print(table)


def handle_test_mic(
    console: Console,
    device_id: int | None = None,
    seconds: float = 2.0,
) -> None:
    """Record for N seconds, play back, then transcribe and print text.

    Args:
        console: Rich console for output.
        device_id: Optional device ID from `vox devices`.
        seconds: Record duration in seconds.

    Raises:
        ValueError: If seconds <= 0.
    """
    if seconds <= 0:
        raise ValueError("--seconds must be positive.")
    console.print(f"Recording for [bold]{seconds}[/bold] seconds...")
    samples = record_seconds(seconds, device_id=device_id)
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


def handle_run(console: Console) -> None:
    """Start push-to-talk loop: hotkey to record, release to transcribe and inject.

    Loads config from ~/.vox/vox.toml (or VOX_CONFIG). On each hotkey release,
    recorded audio is transcribed and placed on the clipboard (and optionally
    pasted into the focused window if injection_mode is clipboard_and_paste).
    Runs until KeyboardInterrupt.

    Args:
        console: Rich console for output.
    """
    cfg = get_config()
    hotkey_str = cfg["hotkey"]
    device_id = cfg.get("device_id")
    model_size = cfg.get("model_size", "base")
    compute_type = cfg.get("compute_type", "float32")
    compute_device = cfg.get("compute_device", "cpu")
    injection_mode = cfg.get("injection_mode", "clipboard")

    model = load_model(
        model_size_or_path=model_size,
        device=compute_device,
        compute_type=compute_type,
    )

    sample_rate = 16000
    channels = 1

    def on_audio(audio_buffer: np.ndarray) -> None:
        """Transcribe buffer, set clipboard, optionally paste into focused window.

        Args:
            audio_buffer: Recorded float32 mono array (16 kHz).
        """
        try:
            text = transcribe(audio_buffer, model=model)
        except TranscriptionError as e:
            console.print(f"[red]Transcription error:[/red] {e}")
            return
        if not text.strip():
            console.print("[dim]No speech detected.[/dim]")
            return
        try:
            set_clipboard(text)
        except InjectError as e:
            console.print(f"[red]Clipboard error:[/red] {e}")
            return
        if injection_mode == "clipboard_and_paste":
            try:
                paste_into_focused()
            except InjectError as e:
                console.print(f"[yellow]Paste failed:[/yellow] {e}")
        console.print("[green]Injected.[/green]")

    console.print(
        Panel(
            f"Hotkey: [bold]{hotkey_str}[/bold]\n"
            "Press and hold to record, release to transcribe and inject.\n"
            "Press Ctrl+C to exit.",
            title="Vox push-to-talk",
        )
    )
    run_push_to_talk_loop(
        hotkey_str=hotkey_str,
        device_id=device_id,
        sample_rate=sample_rate,
        channels=channels,
        on_audio=on_audio,
    )
