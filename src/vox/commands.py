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
from vox.capture import (
    list_devices,
    play_back,
    record_seconds,
    start_framed_input_stream,
)
from vox.config import (
    DEFAULT_CONTINUOUS_HOTKEY,
    DEFAULT_CONTINUOUS_IDLE_MINUTES,
    DEFAULT_CONTINUOUS_PAUSE_SECONDS,
    ConfigError,
    get_config,
    get_transcription_options,
)
from vox.continuous.session import ContinuousSession
from vox.continuous.vad import FRAME_SAMPLES, load_streaming_vad
from vox.inject import (
    InjectError,
    get_clipboard,
    paste_into_focused,
    set_clipboard,
    type_into_focused,
)
from vox.transcribe import TranscriptionError, load_model, transcribe

if TYPE_CHECKING:
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]


class HotkeyModuleProtocol(Protocol):
    """Minimal hotkey module protocol used by the runtime command layer."""

    run_push_to_talk_loop: Callable[..., None]


_HOTKEY_RELOAD_POLL_SECONDS = 0.25
_CLIPBOARD_RESTORE_DELAY_SECONDS = 0.15


def _pause_before_clipboard_restore() -> None:
    """Wait briefly so the focused app can consume the pasted transcription."""
    time.sleep(_CLIPBOARD_RESTORE_DELAY_SECONDS)


def _snapshot_clipboard(console: Console) -> str | None:
    """Read prior clipboard text for later restore, or None if snapshot failed.

    Args:
        console: Rich console for yellow skip warnings.

    Returns:
        Prior clipboard text, or None when the snapshot raised InjectError.
    """
    try:
        return get_clipboard()
    except InjectError as exc:
        console.print(f"[yellow]Clipboard restore skipped:[/yellow] {exc}")
        return None


def _restore_clipboard(console: Console, previous: str, injected: str) -> None:
    """Restore ``previous`` when the clipboard still holds ``injected``.

    Args:
        console: Rich console for yellow skip warnings.
        previous: Non-empty text to put back on the clipboard.
        injected: Transcription that was pasted; restore only while it remains.
    """
    try:
        _pause_before_clipboard_restore()
        if get_clipboard() == injected:
            set_clipboard(previous)
    except InjectError as exc:
        console.print(f"[yellow]Clipboard restore skipped:[/yellow] {exc}")


def _inject_clipboard(console: Console, text: str) -> None:
    """Place transcribed text on the clipboard only.

    Args:
        console: Rich console for status and errors.
        text: Transcribed text to inject.
    """
    try:
        set_clipboard(text)
    except InjectError as exc:
        console.print(f"[red]Clipboard error:[/red] {exc}")
        return
    console.print("[green]Injected.[/green]")


def _inject_clipboard_and_paste(console: Console, text: str) -> None:
    """Paste transcription, then restore the prior clipboard when safe.

    Args:
        console: Rich console for status and errors.
        text: Transcribed text to inject.
    """
    previous = _snapshot_clipboard(console)
    try:
        set_clipboard(text)
    except InjectError as exc:
        console.print(f"[red]Clipboard error:[/red] {exc}")
        return
    paste_ok = True
    try:
        paste_into_focused()
    except InjectError as exc:
        console.print(f"[yellow]Paste failed:[/yellow] {exc}")
        paste_ok = False
    if paste_ok and previous:
        _restore_clipboard(console, previous, text)
    console.print("[green]Injected.[/green]")


def _inject_type(console: Console, text: str) -> None:
    """Type transcribed text into the focused window.

    Args:
        console: Rich console for status and errors.
        text: Transcribed text to inject.
    """
    try:
        type_into_focused(text)
    except InjectError as exc:
        console.print(f"[red]Typing error:[/red] {exc}")
        return
    console.print("[green]Injected.[/green]")


_INJECTORS: dict[str, Callable[[Console, str], None]] = {
    "clipboard": _inject_clipboard,
    "clipboard_and_paste": _inject_clipboard_and_paste,
    "type": _inject_type,
}


def _resolve_injector(injection_mode: str) -> Callable[[Console, str], None]:
    """Return the injector for ``injection_mode`` or fail fast.

    Args:
        injection_mode: Configured injection mode name.

    Returns:
        Injector callable taking ``(console, text)``.

    Raises:
        ConfigError: If ``injection_mode`` is not a supported value.
    """
    try:
        return _INJECTORS[injection_mode]
    except KeyError as exc:
        raise ConfigError(
            f"injection_mode: unsupported value {injection_mode!r}"
        ) from exc


def _run_push_to_talk_loop(  # noqa: PLR0913
    hotkey_str: str,
    device_id: int | None,
    sample_rate: int,
    channels: int,
    on_audio: Callable[[np.ndarray], None],
    on_recording_start: Callable[[], None] | None = None,
    on_recording_stop: Callable[[], None] | None = None,
    stop_event: threading.Event | None = None,
    continuous_hotkey: str | None = None,
    on_continuous_toggle: Callable[[], None] | None = None,
    is_continuous_active: Callable[[], bool] | None = None,
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
        continuous_hotkey: Optional Continuous dictation toggle combo.
        on_continuous_toggle: Optional Continuous toggle callback.
        is_continuous_active: Optional predicate gating push-to-talk while active.
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
        continuous_hotkey,
        on_continuous_toggle,
        is_continuous_active,
    )


def _spawn_hotkey_reload_watcher(
    *,
    stop_event: threading.Event | None,
    hotkey_str: str,
    continuous_hotkey_str: str,
    loop_stop_event: threading.Event,
    reload_requested: threading.Event,
) -> threading.Thread:
    """Start a watcher thread that requests a loop restart on hotkey change.

    Args:
        stop_event: Optional external stop signal from runtime surfaces.
        hotkey_str: Currently active Push-to-talk hotkey string.
        continuous_hotkey_str: Currently active Continuous dictation hotkey.
        loop_stop_event: Internal stop signal for the current listener iteration.
        reload_requested: Signal set when a hotkey change requires loop restart.

    Returns:
        Started daemon watcher thread.
    """

    def watch_hotkey() -> None:
        """Poll config hotkeys and request listener-loop restart when changed."""
        while not loop_stop_event.is_set():
            if stop_event is not None and stop_event.is_set():
                loop_stop_event.set()
                return
            try:
                cfg = get_config()
                current_hotkey = str(cfg["hotkey"]).strip()
                current_continuous = str(
                    cfg.get("continuous_hotkey", DEFAULT_CONTINUOUS_HOTKEY)
                ).strip()
            except (ConfigError, KeyError):
                current_hotkey = hotkey_str
                current_continuous = continuous_hotkey_str
            if (current_hotkey and current_hotkey != hotkey_str) or (
                current_continuous and current_continuous != continuous_hotkey_str
            ):
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
    injector = _resolve_injector(injection_mode)

    def on_audio(audio_buffer: np.ndarray) -> None:
        """Transcribe buffer and inject text via the resolved injector.

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
        injector(console, text)

    return on_audio


def _build_continuous_session(  # noqa: PLR0913
    console: Console,
    model: WhisperModel,
    injection_mode: str,
    device_id: int | None,
    sample_rate: int,
    channels: int,
    on_recording_start: Callable[[], None],
    on_recording_stop: Callable[[], None],
    pause_seconds: float = DEFAULT_CONTINUOUS_PAUSE_SECONDS,
    idle_minutes: float = DEFAULT_CONTINUOUS_IDLE_MINUTES,
) -> ContinuousSession:
    """Build the Continuous dictation session for one ``handle_run`` lifetime.

    Args:
        console: Rich console for Injection and error reporting.
        model: Preloaded Whisper model reused across Commits.
        injection_mode: Configured Injection mode name.
        device_id: Optional input device index.
        sample_rate: Capture sample rate in Hz.
        channels: Capture channel count.
        on_recording_start: Start cue callback reused as Continuous start cue.
        on_recording_stop: End cue callback reused as Continuous end cue.
        pause_seconds: Trailing silence that ends an Utterance.
        idle_minutes: Silence minutes before Continuous auto-off.

    Returns:
        Idle ContinuousSession (no stream/VAD until first toggle-on).
    """
    injector = _resolve_injector(injection_mode)

    def deliverer(text: str) -> None:
        """Inject committed Continuous text (already includes trailing space).

        Args:
            text: Committed transcription including a trailing space.
        """
        injector(console, text)

    def stream_starter(
        on_frame: Callable[[np.ndarray], None],
        stop_event: threading.Event,
    ) -> None:
        """Start the long-lived 512-sample Continuous microphone stream.

        Args:
            on_frame: Callback invoked with each mono float32 frame.
            stop_event: Set when listening should stop.
        """
        start_framed_input_stream(
            on_frame,
            stop_event,
            device_id=device_id,
            sample_rate=sample_rate,
            channels=channels,
            blocksize=FRAME_SAMPLES,
        )

    def transcriber(audio: np.ndarray) -> str:
        """Transcribe one Committed Utterance.

        Args:
            audio: Utterance samples as a float32 array.

        Returns:
            Transcribed text for Injection.
        """
        return transcribe(audio, model=model)

    def reporter(message: str) -> None:
        """Surface Continuous runtime failures without failing silently.

        Args:
            message: Error detail to print.
        """
        console.print(f"[red]Continuous dictation error:[/red] {message}")

    def on_idle_auto_off(minutes: float) -> None:
        """Print a dim message when Continuous auto-off fires.

        Args:
            minutes: Configured idle minutes that triggered auto-off.
        """
        console.print(
            f"[dim]Continuous dictation auto-off after {minutes:g} minutes "
            "of idle.[/dim]"
        )

    return ContinuousSession(
        stream_starter=stream_starter,
        speech_detector_factory=load_streaming_vad,
        transcriber=transcriber,
        deliverer=deliverer,
        play_start=on_recording_start,
        play_end=on_recording_stop,
        reporter=reporter,
        pause_seconds=pause_seconds,
        idle_minutes=idle_minutes,
        on_idle_auto_off=on_idle_auto_off,
    )


def _read_reload_hotkeys(
    console: Console,
    *,
    active_hotkey: str,
    active_continuous_hotkey: str,
) -> tuple[str, str] | None:
    """Load next Push-to-talk / Continuous hotkeys after a reload request.

    Args:
        console: Rich console for warning output.
        active_hotkey: Currently bound Push-to-talk hotkey.
        active_continuous_hotkey: Currently bound Continuous hotkey.

    Returns:
        ``(next_hotkey, next_continuous)`` or None when config reload fails.
    """
    try:
        next_cfg = get_config()
        return (
            str(next_cfg["hotkey"]).strip(),
            str(next_cfg.get("continuous_hotkey", DEFAULT_CONTINUOUS_HOTKEY)).strip(),
        )
    except (ConfigError, KeyError) as e:
        console.print(
            f"[yellow]Hotkey reload warning:[/yellow] {e}. "
            f"Keeping {active_hotkey} / {active_continuous_hotkey}."
        )
        return None


def _announce_hotkey_rebinds(
    console: Console,
    *,
    active_hotkey: str,
    active_continuous_hotkey: str,
    next_hotkey: str,
    next_continuous: str,
) -> tuple[str, str]:
    """Print rebind messages and return the updated active hotkey pair.

    Args:
        console: Rich console for rebind messages.
        active_hotkey: Currently bound Push-to-talk hotkey.
        active_continuous_hotkey: Currently bound Continuous hotkey.
        next_hotkey: Newly loaded Push-to-talk hotkey.
        next_continuous: Newly loaded Continuous hotkey.

    Returns:
        Updated ``(active_hotkey, active_continuous_hotkey)``.
    """
    if next_hotkey and next_hotkey != active_hotkey:
        active_hotkey = next_hotkey
        console.print(f"[cyan]Rebound hotkey:[/cyan] [bold]{active_hotkey}[/bold]")
    if next_continuous and next_continuous != active_continuous_hotkey:
        active_continuous_hotkey = next_continuous
        console.print(
            "[cyan]Rebound continuous hotkey:[/cyan] "
            f"[bold]{active_continuous_hotkey}[/bold]"
        )
    return active_hotkey, active_continuous_hotkey


def handle_run(
    console: Console,
    stop_event: threading.Event | None = None,
) -> None:
    """Start push-to-talk and Continuous dictation for one run.

    Loads config from ~/.vox/vox.toml (or VOX_CONFIG). On each push-to-talk
    hotkey release, recorded audio is transcribed and Injected. Continuous
    dictation is toggled with ``continuous_hotkey`` and Commits on Pause.
    Runs until stopped (KeyboardInterrupt or stop_event set).

    Args:
        console: Rich console for output.
        stop_event: If set, the hotkey loop exits (e.g. for CLI stop button).
    """
    cfg = get_config()
    hotkey_str = cfg["hotkey"]
    device_id = cfg.get("device_id")
    model_size = cfg.get("model_size", "base")
    compute_type = cfg.get("compute_type", "float32")
    compute_device = cfg.get("compute_device", "cpu")
    injection_mode = cfg.get("injection_mode", "clipboard")
    cue_volume = cfg.get("cue_volume", 0.5)
    continuous_hotkey = str(
        cfg.get("continuous_hotkey", DEFAULT_CONTINUOUS_HOTKEY)
    ).strip()
    pause_seconds = float(
        cfg.get("continuous_pause_seconds", DEFAULT_CONTINUOUS_PAUSE_SECONDS)
    )
    idle_minutes = float(
        cfg.get("continuous_idle_minutes", DEFAULT_CONTINUOUS_IDLE_MINUTES)
    )

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
    continuous = _build_continuous_session(
        console,
        model,
        injection_mode,
        device_id,
        sample_rate,
        channels,
        on_recording_start,
        on_recording_stop,
        pause_seconds=pause_seconds,
        idle_minutes=idle_minutes,
    )
    continuous.start()

    console.print(
        Panel(
            f"Push-to-talk: [bold]{hotkey_str}[/bold] "
            "(hold to record, release to transcribe and inject)\n"
            f"Continuous dictation: [bold]{continuous_hotkey}[/bold] "
            f"(tap to toggle; Commits after {pause_seconds:g}s Pause)\n"
            "Press Ctrl+C to exit.",
            title="Vox",
        )
    )

    def run_loop(
        *,
        active_hotkey: str,
        active_continuous_hotkey: str,
        loop_stop: threading.Event | None,
    ) -> None:
        """Run one hotkey listener pass with Continuous toggle wired in.

        Args:
            active_hotkey: Push-to-talk hotkey for this listener pass.
            active_continuous_hotkey: Continuous dictation toggle hotkey.
            loop_stop: Optional stop event for reload or external quit.
        """
        _run_push_to_talk_loop(
            hotkey_str=active_hotkey,
            device_id=device_id,
            sample_rate=sample_rate,
            channels=channels,
            on_audio=on_audio,
            on_recording_start=on_recording_start,
            on_recording_stop=on_recording_stop,
            stop_event=loop_stop,
            continuous_hotkey=active_continuous_hotkey,
            on_continuous_toggle=continuous.request_toggle,
            is_continuous_active=continuous.is_active,
        )

    try:
        if stop_event is None:
            run_loop(
                active_hotkey=hotkey_str,
                active_continuous_hotkey=continuous_hotkey,
                loop_stop=None,
            )
            return

        active_hotkey = hotkey_str
        active_continuous_hotkey = continuous_hotkey
        while True:
            loop_stop_event = threading.Event()
            reload_requested = threading.Event()
            watcher_thread = _spawn_hotkey_reload_watcher(
                stop_event=stop_event,
                hotkey_str=active_hotkey,
                continuous_hotkey_str=active_continuous_hotkey,
                loop_stop_event=loop_stop_event,
                reload_requested=reload_requested,
            )
            run_loop(
                active_hotkey=active_hotkey,
                active_continuous_hotkey=active_continuous_hotkey,
                loop_stop=loop_stop_event,
            )
            loop_stop_event.set()
            watcher_thread.join(timeout=0.5)
            if stop_event.is_set() or not reload_requested.is_set():
                return
            next_keys = _read_reload_hotkeys(
                console,
                active_hotkey=active_hotkey,
                active_continuous_hotkey=active_continuous_hotkey,
            )
            if next_keys is None:
                continue
            active_hotkey, active_continuous_hotkey = _announce_hotkey_rebinds(
                console,
                active_hotkey=active_hotkey,
                active_continuous_hotkey=active_continuous_hotkey,
                next_hotkey=next_keys[0],
                next_continuous=next_keys[1],
            )
    finally:
        continuous.shutdown()
