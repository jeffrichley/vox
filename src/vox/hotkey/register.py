"""Global hotkey registration for push-to-talk and Continuous dictation toggle."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from queue import Queue

import numpy as np

# pynput has no py.typed in some releases; type-check only.
from pynput import keyboard  # type: ignore[import-untyped]

from vox.capture import record_until_stop
from vox.hotkey.modifiers import ModifierTracker

_MODIFIER_MAP: dict[str, keyboard.Key] = {
    "ctrl": keyboard.Key.ctrl,
    "control": keyboard.Key.ctrl,
    "shift": keyboard.Key.shift,
    "alt": keyboard.Key.alt,
    "cmd": keyboard.Key.cmd,
    "meta": keyboard.Key.cmd,
    "win": keyboard.Key.cmd,
}

_MODIFIER_TO_LOGICAL: dict[keyboard.Key, keyboard.Key] = {
    keyboard.Key.ctrl_l: keyboard.Key.ctrl,
    keyboard.Key.ctrl_r: keyboard.Key.ctrl,
    keyboard.Key.shift_l: keyboard.Key.shift,
    keyboard.Key.shift_r: keyboard.Key.shift,
    keyboard.Key.alt_l: keyboard.Key.alt,
    keyboard.Key.alt_r: keyboard.Key.alt,
    keyboard.Key.cmd_l: keyboard.Key.cmd,
    keyboard.Key.cmd_r: keyboard.Key.cmd,
}

_LOGICAL_TO_NAME: dict[keyboard.Key, str] = {
    keyboard.Key.ctrl: "ctrl",
    keyboard.Key.shift: "shift",
    keyboard.Key.alt: "alt",
    keyboard.Key.cmd: "cmd",
}

_NAME_TO_LOGICAL: dict[str, keyboard.Key] = {
    "ctrl": keyboard.Key.ctrl,
    "shift": keyboard.Key.shift,
    "alt": keyboard.Key.alt,
    "cmd": keyboard.Key.cmd,
}


def _normalize_modifier(
    key: keyboard.Key | keyboard.KeyCode | None,
) -> keyboard.Key | None:
    """Return logical modifier key for comparison (e.g. ctrl_l -> ctrl).

    Args:
        key: Key from listener callback.

    Returns:
        Logical modifier (e.g. Key.ctrl) or None if not a modifier.
    """
    if key is None or not isinstance(key, keyboard.Key):
        return None
    out = _MODIFIER_TO_LOGICAL.get(key)
    return out if out is not None else (key if key in _MODIFIER_MAP.values() else None)


def _modifier_name(logical: keyboard.Key) -> str | None:
    """Return the tracker name for a logical modifier key.

    Args:
        logical: Normalized modifier (e.g. ``Key.ctrl``).

    Returns:
        Tracker name, or None if not a tracked modifier.
    """
    return _LOGICAL_TO_NAME.get(logical)


def _parse_hotkey(
    hotkey_str: str,
) -> tuple[frozenset[keyboard.Key], keyboard.Key | str]:
    """Parse 'ctrl+shift+v' into (modifier_keys, trigger_key).

    Args:
        hotkey_str: Combination like 'ctrl+v' or 'ctrl+shift+v'.

    Returns:
        (modifiers, trigger). Trigger is Key for special keys or single-char str.

    Raises:
        ValueError: If hotkey_str is empty or has no trigger key.
    """
    parts = [p.strip().lower() for p in hotkey_str.split("+") if p.strip()]
    if not parts:
        raise ValueError(
            "hotkey must be a combination like 'ctrl+v' or 'ctrl+shift+v'; "
            f"got {hotkey_str!r}"
        )
    modifiers: set[keyboard.Key] = set()
    trigger: keyboard.Key | str = ""
    for p in parts:
        if p in _MODIFIER_MAP:
            modifiers.add(_MODIFIER_MAP[p])
        elif len(p) == 1:
            trigger = p
        else:
            try:
                k = getattr(keyboard.Key, p, None)
                trigger = k if isinstance(k, keyboard.Key) else p
            except (TypeError, AttributeError):
                trigger = p
    if not trigger:
        raise ValueError(
            f"hotkey must include a non-modifier key (e.g. 'v'); got {hotkey_str!r}"
        )
    return frozenset(modifiers), trigger


def _key_matches(
    key: keyboard.Key | keyboard.KeyCode | None,
    trigger: keyboard.Key | str,
) -> bool:
    """Return True if key matches the trigger (modifier-agnostic).

    On Windows, holding Alt often clears ``KeyCode.char``; letter triggers then
    match via the virtual-key code instead.

    Args:
        key: Key from listener callback.
        trigger: Expected trigger key (char or Key).

    Returns:
        True if key matches trigger.
    """
    if key is None:
        return False
    if isinstance(trigger, str):
        if getattr(key, "char", None) == trigger or key == trigger:
            return True
        if len(trigger) == 1:
            vk = getattr(key, "vk", None)
            if vk is not None:
                return int(vk) == ord(trigger.upper())
        return False
    return bool(key == trigger)


@dataclass(frozen=True)
class _RecordingHooks:
    """Optional runtime hooks for recording start and stop events."""

    on_start: Callable[[], None] | None = None
    on_stop: Callable[[], None] | None = None


@dataclass(frozen=True)
class _RecordingConfig:
    """Static runtime settings for one push-to-talk session."""

    hotkey_str: str
    device_id: int | None
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class _ContinuousBinding:
    """Optional Continuous dictation toggle binding."""

    hotkey_str: str
    on_toggle: Callable[[], None]
    is_active: Callable[[], bool]


class _PushToTalkSession:
    """Holds state and callbacks for one push-to-talk (+ optional toggle) run."""

    def __init__(
        self,
        recording_config: _RecordingConfig,
        on_audio: Callable[[np.ndarray], None],
        recording_hooks: _RecordingHooks | None = None,
        continuous: _ContinuousBinding | None = None,
        modifier_tracker: ModifierTracker | None = None,
    ) -> None:
        """Initialize one push-to-talk session with optional Continuous toggle.

        Args:
            recording_config: Static hotkey and capture settings for the session.
            on_audio: Callback invoked with the completed recording buffer.
            recording_hooks: Optional start/stop callbacks around recording.
            continuous: Optional Continuous dictation toggle binding.
            modifier_tracker: Shared held-modifier tracker (created if omitted).
        """
        self.modifier_keys, self.trigger_key = _parse_hotkey(
            recording_config.hotkey_str
        )
        self.device_id = recording_config.device_id
        self.sample_rate = recording_config.sample_rate
        self.channels = recording_config.channels
        self.on_audio = on_audio
        self.recording_hooks = recording_hooks or _RecordingHooks()
        self.continuous = continuous
        if continuous is not None:
            self.continuous_modifiers, self.continuous_trigger = _parse_hotkey(
                continuous.hotkey_str
            )
        else:
            self.continuous_modifiers = frozenset()
            self.continuous_trigger = ""
        self.modifiers = (
            modifier_tracker if modifier_tracker is not None else ModifierTracker()
        )
        self.recording_thread: threading.Thread | None = None
        self.stop_event: threading.Event | None = None
        self.result_holder: list[np.ndarray | None] = []
        self.lock = threading.Lock()
        self.queue: Queue[tuple[threading.Thread, list[np.ndarray | None]] | None] = (
            Queue()
        )
        self._toggle_armed = True

    def _run_record(self, holder: list[np.ndarray | None]) -> None:
        """Record until stop_event is set; store buffer in holder[0].

        Args:
            holder: Single-element list to receive the recorded buffer.
        """
        if self.stop_event is None:
            return
        buf = record_until_stop(
            self.stop_event,
            device_id=self.device_id,
            sample_rate=self.sample_rate,
            channels=self.channels,
        )
        if holder:
            holder[0] = buf

    def _processor_loop(self) -> None:
        """Consume queue: join record thread, then call on_audio with buffer."""
        while True:
            item = self.queue.get()
            if item is None:
                break
            rec_thread, holder = item
            rec_thread.join()
            if holder and holder[0] is not None:
                self.on_audio(holder[0])

    def _combo_satisfied(self, required: frozenset[keyboard.Key]) -> bool:
        """Return True when all required modifiers are currently held.

        Args:
            required: Modifier set that must be a subset of current modifiers.

        Returns:
            Whether the combo's modifiers are satisfied.
        """
        self.modifiers.reconcile()
        held = {
            _NAME_TO_LOGICAL[name]
            for name in self.modifiers.held()
            if name in _NAME_TO_LOGICAL
        }
        return required <= held

    def _winning_binding(
        self,
        key: keyboard.Key | keyboard.KeyCode | None,
    ) -> str | None:
        """Return 'continuous', 'ptt', or None for the winning binding on press.

        When both combos are satisfied, the binding with more modifiers wins.

        Args:
            key: Trigger key from the listener.

        Returns:
            Winning binding name, or None if no combo matches.
        """
        ptt_match = _key_matches(key, self.trigger_key) and self._combo_satisfied(
            self.modifier_keys
        )
        cont_match = False
        if self.continuous is not None:
            cont_match = _key_matches(
                key, self.continuous_trigger
            ) and self._combo_satisfied(self.continuous_modifiers)
        if ptt_match and cont_match:
            if len(self.continuous_modifiers) > len(self.modifier_keys):
                return "continuous"
            if len(self.modifier_keys) > len(self.continuous_modifiers):
                return "ptt"
            # Equal modifier counts: prefer Continuous when both match.
            return "continuous"
        if cont_match:
            return "continuous"
        if ptt_match:
            return "ptt"
        return None

    def _start_recording(self) -> None:
        """Start a push-to-talk recording thread if not already recording."""
        if self.recording_thread is not None:
            return
        if self.continuous is not None and self.continuous.is_active():
            return
        self.stop_event = threading.Event()
        holder: list[np.ndarray | None] = [None]
        self.result_holder = holder
        self.recording_thread = threading.Thread(
            target=self._run_record, args=(holder,)
        )
        if self.recording_hooks.on_start is not None:
            self.recording_hooks.on_start()
        self.recording_thread.start()

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        """On key press: track modifiers; fire toggle or start recording.

        Args:
            key: Key from listener callback.
        """
        norm = _normalize_modifier(key)
        if norm is not None:
            name = _modifier_name(norm)
            if name is not None:
                self.modifiers.press(name)
            return
        with self.lock:
            winner = self._winning_binding(key)
            if winner == "continuous" and self.continuous is not None:
                if self._toggle_armed:
                    self._toggle_armed = False
                    self.continuous.on_toggle()
                return
            if winner == "ptt":
                self._start_recording()

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        """On release: re-arm toggle and/or stop push-to-talk recording.

        Args:
            key: Key from listener callback.
        """
        norm = _normalize_modifier(key)
        if norm is not None:
            name = _modifier_name(norm)
            if name is not None:
                self.modifiers.release(name)
            return
        with self.lock:
            if self.continuous is not None and _key_matches(
                key, self.continuous_trigger
            ):
                self._toggle_armed = True
            if not _key_matches(key, self.trigger_key):
                return
            if self.recording_thread is None or self.stop_event is None:
                return
            self.stop_event.set()
            if self.recording_hooks.on_stop is not None:
                self.recording_hooks.on_stop()
            self.queue.put((self.recording_thread, self.result_holder))
            self.recording_thread = None
            self.stop_event = None

    def run(self, stop_event: threading.Event | None = None) -> None:
        """Run the listener and processor until stopped.

        If stop_event is set from another thread, the listener is stopped
        and run() returns.

        Args:
            stop_event: Optional event; when set, a watcher thread stops the
                keyboard listener so this method returns.
        """
        listener_ref: list[keyboard.Listener] = []
        proc_thread = threading.Thread(target=self._processor_loop)
        proc_thread.start()

        def watcher() -> None:
            """When stop_event is set, call listener.stop() so join() returns."""
            if stop_event is None:
                return
            stop_event.wait()
            while not listener_ref:
                time.sleep(0.05)
            listener_ref[0].stop()

        watcher_thread = (
            threading.Thread(target=watcher) if stop_event is not None else None
        )
        if watcher_thread is not None:
            watcher_thread.start()
        try:
            with keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            ) as listener:
                listener_ref.append(listener)
                listener.join()
        finally:
            self.queue.put(None)
            proc_thread.join()


def run_push_to_talk_loop(  # noqa: PLR0913
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
    modifier_tracker: ModifierTracker | None = None,
) -> None:
    """Run push-to-talk with an optional Continuous dictation toggle.

    Blocks until the listener is stopped. On each hotkey release,
    on_audio(audio_buffer) is called with the recorded float32 mono array.
    Callbacks run in a dedicated processor thread to avoid blocking the listener.

    If stop_event is provided and set from another thread, the listener stops
    and this function returns (for use by CLI stop button, etc.).

    Args:
        hotkey_str: Push-to-talk combination like 'ctrl+shift+v'.
        device_id: Sounddevice device index; None for default input.
        sample_rate: Sample rate in Hz (e.g. 16000).
        channels: Number of channels (1 for mono).
        on_audio: Called with the recorded buffer (numpy array) on each release.
        on_recording_start: Optional callback invoked immediately before recording.
        on_recording_stop: Optional callback invoked immediately after stop signal.
        stop_event: Optional event; when set, the listener is stopped and run returns.
        continuous_hotkey: Optional Continuous toggle combo (default unused).
        on_continuous_toggle: Called when the Continuous toggle fires.
        is_continuous_active: When True, push-to-talk presses are ignored.
        modifier_tracker: Shared modifier tracker for Continuous wait and matching.
    """
    continuous: _ContinuousBinding | None = None
    if (
        continuous_hotkey
        and on_continuous_toggle is not None
        and is_continuous_active is not None
    ):
        continuous = _ContinuousBinding(
            hotkey_str=continuous_hotkey,
            on_toggle=on_continuous_toggle,
            is_active=is_continuous_active,
        )
    session = _PushToTalkSession(
        recording_config=_RecordingConfig(
            hotkey_str=hotkey_str,
            device_id=device_id,
            sample_rate=sample_rate,
            channels=channels,
        ),
        on_audio=on_audio,
        recording_hooks=_RecordingHooks(
            on_start=on_recording_start,
            on_stop=on_recording_stop,
        ),
        continuous=continuous,
        modifier_tracker=modifier_tracker,
    )
    session.run(stop_event=stop_event)
