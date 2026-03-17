"""CLI entry: thin wrapper that delegates to vox.commands."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from tkinter import ttk

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


def _run_stop_window(console: Console) -> None:
    """Show a small window with Stop button; run push-to-talk in a thread until Stop."""
    stop_event = threading.Event()
    worker_done = threading.Event()
    worker_error: list[BaseException] = []

    def run_worker() -> None:
        try:
            handle_run(console, stop_event=stop_event)
        except Exception as e:
            worker_error.append(e)
        finally:
            worker_done.set()

    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()

    root = tk.Tk()
    root.title("Vox")
    root.resizable(False, False)
    root.geometry("220x90")
    root.minsize(200, 70)

    main = ttk.Frame(root, padding=12)
    main.pack(fill=tk.BOTH, expand=True)
    ttk.Label(main, text="Push-to-talk running.").pack(pady=(0, 8))
    stop_btn = ttk.Button(main, text="Stop", command=lambda: _on_stop())

    def _on_stop() -> None:
        stop_event.set()
        stop_btn.state(["disabled"])
        root.after(100, _wait_then_close)

    def _wait_then_close() -> None:
        if not worker_done.wait(timeout=0.1):
            root.after(100, _wait_then_close)
            return
        root.destroy()

    def _check_worker_error() -> None:
        if worker_done.is_set() and worker_error:
            root.destroy()
            return
        root.after(200, _check_worker_error)

    stop_btn.pack(pady=4)
    root.protocol("WM_DELETE_WINDOW", _on_stop)
    root.after(200, _check_worker_error)
    root.mainloop()

    thread.join(timeout=1.0)
    if worker_error:
        raise worker_error[0]


@app.command()
def run() -> None:
    """Start push-to-talk: press hotkey to record, release to transcribe and inject.

    Loads config from ~/.vox/vox.toml (or VOX_CONFIG). On each hotkey release,
    recorded audio is transcribed and placed on the clipboard (and optionally
    pasted into the focused window if injection_mode is clipboard_and_paste).
    A small window with a Stop button is shown to exit.

    Raises:
        Exit: Code 1 if config is invalid or model fails to load (typer.Exit).
    """
    try:
        _run_stop_window(console)
    except ConfigError as e:
        console.print(f"[red]Config error:[/red] {e}")
        raise typer.Exit(1) from e
    except TranscriptionError as e:
        console.print(f"[red]Model error:[/red] {e}")
        raise typer.Exit(1) from e


def main() -> None:
    """Entry point for the vox CLI."""
    app()


if __name__ == "__main__":
    main()
