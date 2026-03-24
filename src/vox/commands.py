"""Command implementations for the Vox CLI. Called by cli.py with a Rich console."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, cast

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vox.audio_cues import CuePlaybackError, CuePlayer, preload_default_cues
from vox.capture import list_devices, play_back, record_seconds
from vox.config import ConfigError, get_config, get_transcription_options
from vox.inject import InjectError, paste_into_focused, set_clipboard, type_into_focused
from vox.transcribe import TranscriptionError, load_model, transcribe

if TYPE_CHECKING:
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]


class HotkeyModuleProtocol(Protocol):
    """Minimal hotkey module protocol used by the runtime command layer."""

    run_push_to_talk_loop: Callable[
        [
            str,
            int | None,
            int,
            int,
            Callable[[np.ndarray], None],
            Callable[[], None] | None,
            Callable[[], None] | None,
            threading.Event | None,
        ],
        None,
    ]


_HOTKEY_RELOAD_POLL_SECONDS = 0.25


def _run_push_to_talk_loop(  # noqa: PLR0913
    hotkey_str: str,
    device_id: int | None,
    sample_rate: int,
    channels: int,
    on_audio: Callable[[np.ndarray], None],
    on_recording_start: Callable[[], None] | None = None,
    on_recording_stop: Callable[[], None] | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """Lazy-load and run the push-to-talk loop implementation.

    Args:
        hotkey_str: Global hotkey combination to register.
        device_id: Optional audio input device ID.
        sample_rate: Audio sample rate in Hz.
        channels: Number of input channels to record.
        on_audio: Callback invoked with each completed recording buffer.
        on_recording_start: Optional callback invoked immediately before recording.
        on_recording_stop: Optional callback invoked immediately after stop signal.
        stop_event: Optional signal used to stop the loop externally.
    """
    hotkey_module = cast(HotkeyModuleProtocol, import_module("vox.hotkey"))
    hotkey_module.run_push_to_talk_loop(
        hotkey_str,
        device_id,
        sample_rate,
        channels,
        on_audio,
        on_recording_start,
        on_recording_stop,
        stop_event,
    )


def _spawn_hotkey_reload_watcher(
    *,
    stop_event: threading.Event | None,
    hotkey_str: str,
    loop_stop_event: threading.Event,
    reload_requested: threading.Event,
) -> threading.Thread:
    """Start a watcher thread that requests a loop restart on hotkey change.

    Args:
        stop_event: Optional external stop signal from runtime surfaces.
        hotkey_str: Currently active hotkey string bound by the listener loop.
        loop_stop_event: Internal stop signal for the current listener iteration.
        reload_requested: Signal set when a hotkey change requires loop restart.

    Returns:
        Started daemon watcher thread.
    """

    def watch_hotkey() -> None:
        """Poll config hotkey and request listener-loop restart when changed."""
        while not loop_stop_event.is_set():
            if stop_event is not None and stop_event.is_set():
                loop_stop_event.set()
                return
            try:
                current_hotkey = str(get_config()["hotkey"]).strip()
            except (ConfigError, KeyError):
                current_hotkey = hotkey_str
            if current_hotkey and current_hotkey != hotkey_str:
                reload_requested.set()
                loop_stop_event.set()
                return
            time.sleep(_HOTKEY_RELOAD_POLL_SECONDS)

    thread = threading.Thread(target=watch_hotkey, daemon=True)
    thread.start()
    return thread


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


def _warn_on_cue_failure(
    console: Console,
    playback: Callable[[], None],
    cue_name: str,
) -> None:
    """Play a cue and degrade to a warning when playback fails.

    Args:
        console: Rich console used for warning output.
        playback: Cue playback callable to invoke.
        cue_name: User-facing cue label for the warning message.
    """
    try:
        playback()
    except CuePlaybackError as e:
        console.print(f"[yellow]{cue_name} cue warning:[/yellow] {e}")


def _build_cue_callbacks(
    console: Console,
    cue_player: CuePlayer,
    cue_volume: float,
) -> tuple[Callable[[], None], Callable[[], None]]:
    """Return runtime start/stop cue callbacks for the hotkey loop.

    Args:
        console: Rich console used for runtime warning output.
        cue_player: Preloaded cue player used by the callbacks.
        cue_volume: Playback volume multiplier applied to both cues.

    Returns:
        Start and stop cue callbacks for the hotkey loop.
    """

    def on_recording_start() -> None:
        """Play the preloaded start cue without aborting the main workflow."""
        _warn_on_cue_failure(
            console,
            lambda: cue_player.play_start(volume_scale=cue_volume),
            "Start",
        )

    def on_recording_stop() -> None:
        """Play the preloaded end cue without aborting the main workflow."""
        _warn_on_cue_failure(
            console,
            lambda: cue_player.play_end(volume_scale=cue_volume),
            "End",
        )

    return on_recording_start, on_recording_stop


def _build_audio_handler(
    console: Console,
    model: WhisperModel,
    injection_mode: str,
) -> Callable[[np.ndarray], None]:
    """Return the audio-processing callback used by the hotkey loop.

    Args:
        console: Rich console used for runtime status and errors.
        model: Preloaded Whisper model reused across recordings.
        injection_mode: Configured injection behavior for transcribed text.

    Returns:
        Audio callback passed into the push-to-talk loop.
    """

    def on_audio(audio_buffer: np.ndarray) -> None:
        """Transcribe buffer, set clipboard, optionally paste into focused window.

        Args:
            audio_buffer: Recorded float32 mono audio (e.g. from record_until_stop).
        """
        try:
            text = transcribe(audio_buffer, model=model)
        except TranscriptionError as e:
            console.print(f"[red]Transcription error:[/red] {e}")
            return
        if not text.strip():
            console.print("[dim]No speech detected.[/dim]")
            return
        if injection_mode == "type":
            try:
                type_into_focused(text)
            except InjectError as e:
                console.print(f"[red]Typing error:[/red] {e}")
                return
            console.print("[green]Injected.[/green]")
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

    return on_audio


def handle_run(
    console: Console,
    stop_event: threading.Event | None = None,
) -> None:
    """Start push-to-talk loop: hotkey to record, release to transcribe and inject.

    Loads config from ~/.vox/vox.toml (or VOX_CONFIG). On each hotkey release,
    recorded audio is transcribed and placed on the clipboard (and optionally
    pasted into the focused window if injection_mode is clipboard_and_paste).
    Runs until stopped (KeyboardInterrupt or stop_event set).

    Args:
        console: Rich console for output.
        stop_event: If set, the push-to-talk loop exits (e.g. for CLI stop button).
    """
    cfg = get_config()
    hotkey_str = cfg["hotkey"]
    device_id = cfg.get("device_id")
    model_size = cfg.get("model_size", "base")
    compute_type = cfg.get("compute_type", "float32")
    compute_device = cfg.get("compute_device", "cpu")
    injection_mode = cfg.get("injection_mode", "clipboard")
    cue_volume = cfg.get("cue_volume", 0.5)

    model = load_model(
        model_size_or_path=model_size,
        device=compute_device,
        compute_type=compute_type,
    )

    sample_rate = 16000
    channels = 1
    cue_player = preload_default_cues()
    on_recording_start, on_recording_stop = _build_cue_callbacks(
        console,
        cue_player,
        cue_volume,
    )
    on_audio = _build_audio_handler(console, model, injection_mode)

    console.print(
        Panel(
            f"Hotkey: [bold]{hotkey_str}[/bold]\n"
            "Press and hold to record, release to transcribe and inject.\n"
            "Press Ctrl+C to exit.",
            title="Vox push-to-talk",
        )
    )
    # Preserve terminal Ctrl+C behavior by keeping the original direct listener
    # path when no external stop_event is provided.
    if stop_event is None:
        _run_push_to_talk_loop(
            hotkey_str=hotkey_str,
            device_id=device_id,
            sample_rate=sample_rate,
            channels=channels,
            on_audio=on_audio,
            on_recording_start=on_recording_start,
            on_recording_stop=on_recording_stop,
            stop_event=None,
        )
        return

    active_hotkey = hotkey_str
    while True:
        loop_stop_event = threading.Event()
        reload_requested = threading.Event()
        watcher_thread = _spawn_hotkey_reload_watcher(
            stop_event=stop_event,
            hotkey_str=active_hotkey,
            loop_stop_event=loop_stop_event,
            reload_requested=reload_requested,
        )
        _run_push_to_talk_loop(
            hotkey_str=active_hotkey,
            device_id=device_id,
            sample_rate=sample_rate,
            channels=channels,
            on_audio=on_audio,
            on_recording_start=on_recording_start,
            on_recording_stop=on_recording_stop,
            stop_event=loop_stop_event,
        )
        loop_stop_event.set()
        watcher_thread.join(timeout=0.5)
        if stop_event is not None and stop_event.is_set():
            return
        if not reload_requested.is_set():
            return
        try:
            next_hotkey = str(get_config()["hotkey"]).strip()
        except (ConfigError, KeyError) as e:
            console.print(
                f"[yellow]Hotkey reload warning:[/yellow] {e}. Keeping {active_hotkey}."
            )
            continue
        if not next_hotkey or next_hotkey == active_hotkey:
            continue
        active_hotkey = next_hotkey
        console.print(f"[cyan]Rebound hotkey:[/cyan] [bold]{active_hotkey}[/bold]")
