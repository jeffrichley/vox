"""Standalone Tk settings window with autosave orchestration."""

from __future__ import annotations

import importlib
import threading
import tkinter as tk
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Literal, cast

from rich.console import Console

from vox.config import (
    ConfigError,
    get_env_override_fields,
    load_persisted_config,
    update_persisted_config,
    write_persisted_config,
)

type SettingValue = str | int | float | bool | None
type PersistedConfig = dict[str, SettingValue]
type SaveUpdates = Callable[[Mapping[str, SettingValue]], PersistedConfig]
type ReplaceAll = Callable[[Mapping[str, SettingValue]], object]
type DeviceLoader = Callable[[], list[tuple[int, str, str]]]
type MicTester = Callable[[int | None], None]
type CueTester = Callable[[float], None]
type RestoreConfirmer = Callable[[], bool]
type SchedulerToken = str | None

STATUS_KIND_SUCCESS: Literal["success"] = "success"
STATUS_KIND_ERROR: Literal["error"] = "error"
STATUS_KIND_INFO: Literal["info"] = "info"
STATUS_KIND_IDLE: Literal["idle"] = "idle"

SETTINGS_SECTIONS: tuple[str, ...] = (
    "Recording",
    "Transcription",
    "Output",
    "Runtime",
)

DEFAULT_SETTINGS: PersistedConfig = {
    "hotkey": "ctrl+shift+v",
    "device_id": None,
    "model_size": "base",
    "compute_type": "float32",
    "compute_device": "cpu",
    "injection_mode": "clipboard",
    "cue_volume": 0.5,
    "use_tray": False,
}

MODEL_SIZE_OPTIONS: tuple[str, ...] = (
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large-v3",
    "large-v3-turbo",
)

COMPUTE_TYPE_OPTIONS: tuple[str, ...] = (
    "float32",
    "float16",
    "int8",
    "int8_float16",
)

COMPUTE_DEVICE_OPTIONS: tuple[str, ...] = ("cpu", "cuda")
INJECTION_MODE_OPTIONS: tuple[str, ...] = (
    "clipboard",
    "clipboard_and_paste",
    "type",
)

RESTART_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "hotkey",
        "device_id",
        "model_size",
        "compute_type",
        "compute_device",
        "injection_mode",
        "use_tray",
    }
)

_HOTKEY_MODIFIERS: tuple[str, ...] = ("ctrl", "shift", "alt", "cmd")
_CTRL_EVENT_MASK = 0x4
_SHIFT_EVENT_MASK = 0x1
_ALT_EVENT_MASK = 0x8


@dataclass(frozen=True)
class StatusState:
    """User-visible status banner state."""

    kind: Literal["idle", "info", "success", "error"]
    text: str


@dataclass(frozen=True)
class DeviceOption:
    """UI-friendly microphone device option."""

    label: str
    device_id: int | None


class DebounceScheduler:
    """Protocol-like base class for Tk and test schedulers."""

    def schedule(self, delay_ms: int, callback: Callable[[], None]) -> SchedulerToken:
        """Schedule a callback and return a cancellation token.

        Args:
            delay_ms: Delay before the callback should run.
            callback: Callback to invoke after the delay.

        Raises:
            NotImplementedError: Always, in the protocol-like base class.
        """
        raise NotImplementedError

    def cancel(self, token: SchedulerToken) -> None:
        """Cancel a scheduled callback by token.

        Args:
            token: Scheduler token returned by ``schedule``.

        Raises:
            NotImplementedError: Always, in the protocol-like base class.
        """
        raise NotImplementedError


class TkAfterScheduler(DebounceScheduler):
    """Tk-backed debouncer using ``after`` callbacks."""

    def __init__(self, root: tk.Tk) -> None:
        """Store the Tk root used to manage delayed callbacks.

        Args:
            root: Tk root that owns the ``after`` scheduling queue.
        """
        self._root = root

    def schedule(self, delay_ms: int, callback: Callable[[], None]) -> SchedulerToken:
        """Schedule a callback via ``root.after``.

        Args:
            delay_ms: Delay before the callback should run.
            callback: Callback to invoke after the delay.

        Returns:
            Tk ``after`` token string for later cancellation.
        """
        return str(self._root.after(delay_ms, callback))

    def cancel(self, token: SchedulerToken) -> None:
        """Cancel an ``after`` callback when one is pending.

        Args:
            token: Tk ``after`` token to cancel.
        """
        if token is None:
            return
        self._root.after_cancel(token)


class SettingsController:
    """Pure autosave orchestration for the settings UI."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        persisted_config: Mapping[str, SettingValue] | None = None,
        overridden_fields: Mapping[str, str] | None = None,
        save_updates: SaveUpdates = update_persisted_config,
        replace_all: ReplaceAll = write_persisted_config,
        scheduler: DebounceScheduler | None = None,
        device_loader: DeviceLoader | None = None,
        mic_tester: MicTester | None = None,
        cue_tester: CueTester | None = None,
        restore_confirmer: RestoreConfirmer | None = None,
        debounce_ms: int = 250,
    ) -> None:
        """Store current config state and autosave collaborators.

        Args:
            persisted_config: Initial file-backed config values for the UI.
            overridden_fields: Mapping of field names to active override env vars.
            save_updates: Persistence function for incremental field updates.
            replace_all: Persistence function for full config replacement.
            scheduler: Optional debouncer used by slider-backed settings.
            device_loader: Function used to list available input devices.
            mic_tester: Callback used by the `Test Mic` action.
            cue_tester: Callback used for cue preview playback.
            restore_confirmer: Callback used to confirm restoring defaults.
            debounce_ms: Delay used before committing slider-backed changes.
        """
        self.values: PersistedConfig = dict(DEFAULT_SETTINGS)
        if persisted_config is not None:
            self.values.update(dict(persisted_config))
        self.overridden_fields = dict(overridden_fields or {})
        if save_updates is update_persisted_config:
            self._save_updates = lambda updates: update_persisted_config(
                updates,
                base=self.values,
            )
        else:
            self._save_updates = save_updates
        self._replace_all = replace_all
        self._scheduler = scheduler
        self._device_loader = device_loader or _default_device_loader
        self._mic_tester = mic_tester or _default_mic_tester
        self._cue_tester = cue_tester or _default_cue_tester
        self._restore_confirmer = restore_confirmer or (lambda: True)
        self._debounce_ms = debounce_ms
        self._pending_slider_token: SchedulerToken = None
        self._pending_slider_value: float | None = None
        self.status = StatusState(STATUS_KIND_IDLE, "Autosave enabled.")

    def attach_scheduler(self, scheduler: DebounceScheduler) -> None:
        """Attach a UI scheduler after controller construction.

        Args:
            scheduler: Debounce scheduler owned by the UI layer.
        """
        self._scheduler = scheduler

    def get_override_message(self, field_name: str) -> str | None:
        """Return an env-override warning for one field when applicable.

        Args:
            field_name: Config field name to inspect.

        Returns:
            Warning message when the field is overridden, else ``None``.
        """
        env_name = self.overridden_fields.get(field_name)
        if env_name is None:
            return None
        return f"Overridden by {env_name}."

    def load_device_options(self) -> list[DeviceOption]:
        """Load available input devices for the Recording section.

        Returns:
            Device options for the input-device combobox.
        """
        try:
            devices = self._device_loader()
        except RuntimeError as e:
            self.status = StatusState(
                STATUS_KIND_ERROR,
                f"Device list unavailable: {e}",
            )
            return [DeviceOption("Default device", None)]
        options = [DeviceOption("Default device", None)]
        options.extend(
            DeviceOption(f"{device_id}: {name} ({host_api})", device_id)
            for device_id, name, host_api in devices
        )
        return options

    def commit_text(self, field_name: str, value: str) -> bool:
        """Persist a text-like field on explicit edit completion.

        Args:
            field_name: Config field being committed.
            value: Completed text value to validate and persist.

        Returns:
            True when the update is saved; False when validation fails.
        """
        return self._persist_updates({field_name: value}, field_name)

    def commit_choice(self, field_name: str, value: SettingValue) -> bool:
        """Persist a combobox or checkbox change immediately.

        Args:
            field_name: Config field being updated.
            value: Selected value to persist.

        Returns:
            True when the update is saved; False when validation fails.
        """
        return self._persist_updates({field_name: value}, field_name)

    def schedule_slider_save(self, field_name: str, value: float) -> None:
        """Debounce slider writes while keeping the current value in memory.

        Args:
            field_name: Slider-backed config field being updated.
            value: Current slider value to save after the debounce delay.
        """
        self.values[field_name] = value
        self._pending_slider_value = value
        if self._scheduler is None:
            self._persist_updates({field_name: value}, field_name)
            return
        if self._pending_slider_token is not None:
            self._scheduler.cancel(self._pending_slider_token)
        self._pending_slider_token = self._scheduler.schedule(
            self._debounce_ms,
            lambda: self._flush_slider_callback(field_name),
        )
        self.status = StatusState(
            STATUS_KIND_INFO,
            f"Saving {field_name.replace('_', ' ')}...",
        )

    def flush_slider_save(self, field_name: str) -> bool:
        """Persist the pending slider value immediately.

        Args:
            field_name: Slider-backed config field being flushed.

        Returns:
            True when a pending slider value was saved; False otherwise.
        """
        self._pending_slider_token = None
        value = self._pending_slider_value
        self._pending_slider_value = None
        if value is None:
            return False
        succeeded = self._persist_updates({field_name: value}, field_name)
        if succeeded and field_name == "cue_volume":
            self._preview_cue(value)
        return succeeded

    def _flush_slider_callback(self, field_name: str) -> None:
        """Run the pending slider save inside a ``None``-returning callback.

        Args:
            field_name: Slider-backed config field being flushed.
        """
        self.flush_slider_save(field_name)

    def restore_defaults(self) -> bool:
        """Replace the current persisted config with the supported defaults.

        Returns:
            True when defaults were written; False when canceled or rejected.
        """
        if not self._restore_confirmer():
            self.status = StatusState(STATUS_KIND_INFO, "Restore defaults canceled.")
            return False
        try:
            self._replace_all(DEFAULT_SETTINGS)
        except ConfigError as e:
            self.status = StatusState(STATUS_KIND_ERROR, str(e))
            return False
        self.values = dict(DEFAULT_SETTINGS)
        self.status = StatusState(
            STATUS_KIND_SUCCESS,
            "Defaults restored. Restart Vox to apply runtime changes.",
        )
        return True

    def test_mic(self) -> None:
        """Run the microphone test action against the current device selection.

        Raises:
            Exception: Re-raises unexpected test-action exceptions after preserving
                user-facing handling for known runtime/config/model failures.
        """
        self.status = StatusState(STATUS_KIND_INFO, "Testing microphone...")
        try:
            device_id = self.values.get("device_id")
            self._mic_tester(device_id if isinstance(device_id, int) else None)
        except Exception as e:
            if not _is_expected_mic_test_error(e):
                raise
            self.status = StatusState(STATUS_KIND_ERROR, str(e))
            return
        self.status = StatusState(STATUS_KIND_SUCCESS, "Microphone test completed.")

    def _preview_cue(self, cue_volume: float) -> None:
        """Play the cue preview and update the user-visible status.

        Args:
            cue_volume: Playback volume multiplier for the preview cue.
        """
        try:
            self._cue_tester(cue_volume)
        except RuntimeError as e:
            self.status = StatusState(STATUS_KIND_ERROR, str(e))
            return
        self.status = StatusState(
            STATUS_KIND_SUCCESS,
            "Saved. Cue preview completed.",
        )

    def _persist_updates(
        self,
        updates: Mapping[str, SettingValue],
        field_name: str,
    ) -> bool:
        """Persist one or more settings and report the resulting status.

        Args:
            updates: Config key/value pairs to validate and persist.
            field_name: Primary field name used for status messaging.

        Returns:
            True when the update is saved; False when validation fails.
        """
        try:
            saved = self._save_updates(updates)
        except ConfigError as e:
            self.status = StatusState(STATUS_KIND_ERROR, str(e))
            return False
        self.values.update(saved)
        if field_name in RESTART_REQUIRED_FIELDS:
            self.status = StatusState(
                STATUS_KIND_SUCCESS,
                "Saved. Restart Vox to apply this change to an active session.",
            )
            return True
        self.status = StatusState(STATUS_KIND_SUCCESS, "Saved.")
        return True


class SettingsWindow:
    """Tk view for the standalone settings editor."""

    def __init__(self, root: tk.Tk, controller: SettingsController) -> None:
        """Build the settings window around a controller instance.

        Args:
            root: Tk root that owns the window.
            controller: Autosave controller backing the UI state.
        """
        self._root = root
        self._controller = controller
        self._scheduler = TkAfterScheduler(root)
        self._device_options = controller.load_device_options()

        root.title("Vox Settings")
        root.geometry("620x540")
        root.minsize(580, 500)
        root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self._status_var = tk.StringVar(value=controller.status.text)
        self._hotkey_var = tk.StringVar(value=str(controller.values["hotkey"]))
        self._hotkey_modifier_order: list[str] = []
        self._hotkey_active_modifiers: set[str] = set()
        self._hotkey_active_trigger: str | None = None
        self._captured_hotkey_value: str | None = None
        self._device_var = tk.StringVar(
            value=self._device_label(controller.values["device_id"])
        )
        self._model_size_var = tk.StringVar(value=str(controller.values["model_size"]))
        self._compute_type_var = tk.StringVar(
            value=str(controller.values["compute_type"])
        )
        self._compute_device_var = tk.StringVar(
            value=str(controller.values["compute_device"])
        )
        self._injection_mode_var = tk.StringVar(
            value=str(controller.values["injection_mode"])
        )
        self._cue_volume_var = tk.DoubleVar(
            value=_coerce_float(controller.values["cue_volume"], default=0.5)
        )
        self._cue_volume_text_var = tk.StringVar(value=self._cue_volume_text())
        self._use_tray_var = tk.BooleanVar(value=bool(controller.values["use_tray"]))

        controller.attach_scheduler(self._scheduler)

        main = ttk.Frame(root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main,
            text="Autosave writes each valid completed change immediately.",
            wraplength=560,
        ).pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(main, textvariable=self._status_var, wraplength=560).pack(
            anchor=tk.W,
            pady=(0, 12),
        )

        self._build_recording_section(main)
        self._build_transcription_section(main)
        self._build_output_section(main)
        self._build_runtime_section(main)

        footer = ttk.Frame(main)
        footer.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(
            footer,
            text="Restore Defaults",
            command=self._on_restore_defaults,
        ).pack(side=tk.LEFT)

    def _build_recording_section(self, parent: ttk.Frame) -> None:
        """Build the Recording section controls.

        Args:
            parent: Parent frame that owns the Recording section.
        """
        section = ttk.LabelFrame(parent, text="Recording", padding=12)
        section.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(section, text="Hotkey").grid(row=0, column=0, sticky=tk.W)
        hotkey_entry = ttk.Entry(section, textvariable=self._hotkey_var, width=28)
        hotkey_entry.grid(row=0, column=1, sticky=tk.W, padx=(8, 8))
        hotkey_entry.bind("<FocusIn>", self._on_hotkey_focus_in)
        hotkey_entry.bind("<KeyPress>", self._on_hotkey_key_press)
        hotkey_entry.bind("<KeyRelease>", self._on_hotkey_key_release)
        hotkey_entry.bind("<Return>", self._on_hotkey_commit)
        hotkey_entry.bind("<FocusOut>", self._on_hotkey_commit)
        self._add_override_note(section, "hotkey", row=1)

        ttk.Label(section, text="Input device").grid(row=2, column=0, sticky=tk.W)
        device_combo = ttk.Combobox(
            section,
            textvariable=self._device_var,
            values=[option.label for option in self._device_options],
            state="readonly",
            width=40,
        )
        device_combo.grid(row=2, column=1, sticky=tk.W, padx=(8, 8))
        device_combo.bind("<<ComboboxSelected>>", self._on_device_selected)
        ttk.Button(section, text="Test Mic", command=self._run_test_mic).grid(
            row=2,
            column=2,
            sticky=tk.W,
        )
        self._add_override_note(section, "device_id", row=3)

    def _build_transcription_section(self, parent: ttk.Frame) -> None:
        """Build the Transcription section controls.

        Args:
            parent: Parent frame that owns the Transcription section.
        """
        section = ttk.LabelFrame(parent, text="Transcription", padding=12)
        section.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(section, text="Model size").grid(row=0, column=0, sticky=tk.W)
        model_combo = self._make_combobox(
            section,
            variable=self._model_size_var,
            values=MODEL_SIZE_OPTIONS,
        )
        model_combo.grid(row=0, column=1, sticky=tk.W, padx=(8, 0))
        model_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._save_combo(
                "model_size",
                self._model_size_var.get(),
            ),
        )
        self._add_override_note(section, "model_size", row=1)

        ttk.Label(section, text="Compute device").grid(row=2, column=0, sticky=tk.W)
        compute_device_combo = self._make_combobox(
            section,
            variable=self._compute_device_var,
            values=COMPUTE_DEVICE_OPTIONS,
        )
        compute_device_combo.grid(row=2, column=1, sticky=tk.W, padx=(8, 0))
        compute_device_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._save_combo(
                "compute_device",
                self._compute_device_var.get(),
            ),
        )
        self._add_override_note(section, "compute_device", row=3)

        ttk.Label(section, text="Compute type").grid(row=4, column=0, sticky=tk.W)
        compute_type_combo = self._make_combobox(
            section,
            variable=self._compute_type_var,
            values=COMPUTE_TYPE_OPTIONS,
        )
        compute_type_combo.grid(row=4, column=1, sticky=tk.W, padx=(8, 0))
        compute_type_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._save_combo(
                "compute_type",
                self._compute_type_var.get(),
            ),
        )
        self._add_override_note(section, "compute_type", row=5)

    def _build_output_section(self, parent: ttk.Frame) -> None:
        """Build the Output section controls.

        Args:
            parent: Parent frame that owns the Output section.
        """
        section = ttk.LabelFrame(parent, text="Output", padding=12)
        section.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(section, text="Injection mode").grid(row=0, column=0, sticky=tk.W)
        injection_combo = self._make_combobox(
            section,
            variable=self._injection_mode_var,
            values=INJECTION_MODE_OPTIONS,
        )
        injection_combo.grid(row=0, column=1, sticky=tk.W, padx=(8, 0))
        injection_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._save_combo(
                "injection_mode",
                self._injection_mode_var.get(),
            ),
        )
        self._add_override_note(section, "injection_mode", row=1)

        ttk.Label(section, text="Cue volume").grid(row=2, column=0, sticky=tk.W)
        scale = ttk.Scale(
            section,
            from_=0.0,
            to=1.0,
            variable=self._cue_volume_var,
            command=self._on_cue_volume_changed,
        )
        scale.grid(row=2, column=1, sticky=tk.EW, padx=(8, 8))
        ttk.Label(section, textvariable=self._cue_volume_text_var).grid(
            row=2,
            column=2,
            sticky=tk.W,
        )
        self._add_override_note(section, "cue_volume", row=3)
        section.columnconfigure(1, weight=1)

    def _build_runtime_section(self, parent: ttk.Frame) -> None:
        """Build the Runtime section controls.

        Args:
            parent: Parent frame that owns the Runtime section.
        """
        section = ttk.LabelFrame(parent, text="Runtime", padding=12)
        section.pack(fill=tk.X)

        check = ttk.Checkbutton(
            section,
            text="Use system tray",
            variable=self._use_tray_var,
            command=self._on_use_tray_toggled,
        )
        check.grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            section,
            text="Changes affecting an active session apply after restart.",
            wraplength=520,
        ).grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        self._add_override_note(section, "use_tray", row=2)

    def _make_combobox(
        self,
        parent: ttk.LabelFrame,
        *,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> ttk.Combobox:
        """Build a readonly settings combobox.

        Args:
            parent: Parent section containing the combobox.
            variable: Tk string variable bound to the combobox selection.
            values: Allowed user-visible values for the combobox.

        Returns:
            Configured readonly ttk combobox instance.
        """
        return ttk.Combobox(
            parent,
            textvariable=variable,
            values=list(values),
            state="readonly",
            width=28,
        )

    def _add_override_note(
        self,
        parent: ttk.LabelFrame,
        field_name: str,
        *,
        row: int,
    ) -> None:
        """Render an env-override note for one field when needed.

        Args:
            parent: Parent section containing the note.
            field_name: Config field whose override note should be rendered.
            row: Grid row where the note should appear.
        """
        note = self._controller.get_override_message(field_name)
        if note is None:
            return
        ttk.Label(parent, text=note, wraplength=520).grid(
            row=row,
            column=0,
            columnspan=4,
            sticky=tk.W,
            pady=(4, 4),
        )

    def _device_label(self, current_device_id: SettingValue) -> str:
        """Return the current device label for the combobox selection.

        Args:
            current_device_id: Currently selected input-device ID.

        Returns:
            Label matching the selected device option.
        """
        for option in self._device_options:
            if option.device_id == current_device_id:
                return option.label
        return self._device_options[0].label

    def _cue_volume_text(self) -> str:
        """Return the user-facing cue-volume percentage.

        Returns:
            Percentage label for the current cue-volume slider value.
        """
        return f"{round(self._cue_volume_var.get() * 100)}%"

    def _sync_status(self) -> None:
        """Update the status label from controller state."""
        self._status_var.set(self._controller.status.text)

    def _save_combo(self, field_name: str, value: str) -> None:
        """Persist an immediate combobox selection.

        Args:
            field_name: Config field being updated.
            value: Selected combobox value to persist.
        """
        self._controller.commit_choice(field_name, value)
        self._sync_status()

    def _on_hotkey_commit(self, _event: tk.Event[tk.Entry] | None) -> None:
        """Persist the hotkey when editing is complete."""
        candidate = self._captured_hotkey_value or self._hotkey_var.get()
        normalized = _normalize_hotkey_capture_value(candidate)
        if normalized:
            self._hotkey_var.set(_format_hotkey_display(normalized))
        self._controller.commit_text("hotkey", normalized)
        self._sync_status()
        self._captured_hotkey_value = None
        self._hotkey_active_trigger = None
        self._hotkey_active_modifiers.clear()
        self._hotkey_modifier_order.clear()

    def _on_window_close(self) -> None:
        """Persist pending hotkey capture before closing the window."""
        self._on_hotkey_commit(None)
        self._root.destroy()

    def _on_hotkey_focus_in(self, _event: tk.Event[tk.Entry]) -> None:
        """Reset capture state when the hotkey field gains focus."""
        self._captured_hotkey_value = None
        self._hotkey_active_trigger = None
        self._hotkey_active_modifiers.clear()
        self._hotkey_modifier_order.clear()

    def _on_hotkey_key_press(self, event: tk.Event[tk.Entry]) -> str:
        """Capture and display hotkey parts from physical key presses.

        Args:
            event: Tk key-press event from the hotkey entry widget.

        Returns:
            Tk break marker so the entry does not insert raw key text.
        """
        token = _event_keysym_to_hotkey_token(event.keysym)
        if token is None:
            return "break"
        if token in _HOTKEY_MODIFIERS:
            self._hotkey_active_modifiers.add(token)
            self._hotkey_modifier_order = _ordered_modifiers(
                self._hotkey_active_modifiers
            )
        else:
            self._hotkey_active_trigger = token
        self._update_hotkey_capture_display()
        return "break"

    def _on_hotkey_key_release(self, event: tk.Event[tk.Entry]) -> str:
        """Update hotkey preview as held keys are released.

        Args:
            event: Tk key-release event from the hotkey entry widget.

        Returns:
            Tk break marker so release events do not alter entry text directly.
        """
        token = _event_keysym_to_hotkey_token(event.keysym)
        if token is None:
            return "break"
        if token in _HOTKEY_MODIFIERS:
            self._hotkey_active_modifiers.discard(token)
            self._hotkey_modifier_order = _ordered_modifiers(
                self._hotkey_active_modifiers
            )
        elif self._hotkey_active_trigger == token:
            self._hotkey_active_trigger = None
        self._update_hotkey_capture_display()
        return "break"

    def _update_hotkey_capture_display(self) -> None:
        """Refresh entry text from active held keys and captured combo."""
        active_modifiers = [
            modifier
            for modifier in self._hotkey_modifier_order
            if modifier in self._hotkey_active_modifiers
        ]
        active = _build_hotkey_value(active_modifiers, self._hotkey_active_trigger)
        if self._hotkey_active_trigger is not None and active:
            self._captured_hotkey_value = active
        preview = _choose_hotkey_preview(
            active=active,
            captured=self._captured_hotkey_value,
            has_trigger=(self._hotkey_active_trigger is not None),
        )
        if preview is None:
            return
        self._hotkey_var.set(_format_hotkey_display(preview))

    def _on_device_selected(self, _event: tk.Event[ttk.Combobox]) -> None:
        """Persist the selected input device immediately."""
        selected = next(
            (
                option.device_id
                for option in self._device_options
                if option.label == self._device_var.get()
            ),
            None,
        )
        self._controller.commit_choice("device_id", selected)
        self._sync_status()

    def _on_cue_volume_changed(self, _value: str) -> None:
        """Debounce cue-volume writes while keeping the label current."""
        self._cue_volume_text_var.set(self._cue_volume_text())
        self._controller.schedule_slider_save("cue_volume", self._cue_volume_var.get())
        self._sync_status()

    def _on_use_tray_toggled(self) -> None:
        """Persist the tray toggle immediately."""
        self._controller.commit_choice("use_tray", self._use_tray_var.get())
        self._sync_status()

    def _on_restore_defaults(self) -> None:
        """Replace config with defaults after explicit confirmation."""
        self._controller.restore_defaults()
        self._hotkey_var.set(str(self._controller.values["hotkey"]))
        self._device_var.set(self._device_label(self._controller.values["device_id"]))
        self._model_size_var.set(str(self._controller.values["model_size"]))
        self._compute_type_var.set(str(self._controller.values["compute_type"]))
        self._compute_device_var.set(str(self._controller.values["compute_device"]))
        self._injection_mode_var.set(str(self._controller.values["injection_mode"]))
        self._cue_volume_var.set(
            _coerce_float(self._controller.values["cue_volume"], default=0.5)
        )
        self._cue_volume_text_var.set(self._cue_volume_text())
        self._use_tray_var.set(bool(self._controller.values["use_tray"]))
        self._sync_status()

    def _run_test_mic(self) -> None:
        """Run the microphone test in a background thread."""
        self._run_background_action(self._controller.test_mic)

    def _run_background_action(self, action: Callable[[], None]) -> None:
        """Run one test action without blocking the Tk event loop.

        Args:
            action: Background action to run without blocking Tk.
        """

        def worker() -> None:
            """Execute the background action and resync status on the Tk thread."""
            action()
            self._root.after(0, self._sync_status)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self._sync_status()


def _default_mic_tester(device_id: int | None) -> None:
    """Run the existing CLI microphone test handler for the selected device.

    Args:
        device_id: Optional input-device ID to pass into `vox test-mic`.
    """
    commands_module = importlib.import_module("vox.commands")
    commands_module.handle_test_mic(Console(), device_id=device_id, seconds=2.0)


def _default_cue_tester(volume_scale: float) -> None:
    """Play the default recording cue at the configured preview volume.

    Args:
        volume_scale: Cue-preview volume multiplier between 0.0 and 1.0.
    """
    audio_cues_module = importlib.import_module("vox.audio_cues")
    audio_cues_module.preload_default_cues().play_start(volume_scale=volume_scale)


def _default_device_loader() -> list[tuple[int, str, str]]:
    """Load available audio-input devices via the capture module.

    Returns:
        Available input-device triples of device ID, device name, and host API.
    """
    capture_module = importlib.import_module("vox.capture")
    return cast(list[tuple[int, str, str]], capture_module.list_devices())


def _is_expected_mic_test_error(exc: BaseException) -> bool:
    """Return whether the exception should be shown as a user-facing mic-test error.

    Args:
        exc: Exception raised while running the microphone test action.

    Returns:
        True when the exception should be surfaced in the status banner.
    """
    transcribe_module = importlib.import_module("vox.transcribe")
    transcription_error = transcribe_module.TranscriptionError
    return isinstance(exc, (ConfigError, RuntimeError, ValueError, transcription_error))


def _coerce_float(value: SettingValue, *, default: float) -> float:
    """Return a float config value or the provided fallback.

    Args:
        value: Config value that may or may not be numeric.
        default: Fallback value when the config value is not numeric.

    Returns:
        Numeric float value or the provided default.
    """
    if isinstance(value, int | float):
        return float(value)
    return default


def _event_keysym_to_hotkey_token(keysym: str) -> str | None:
    """Map Tk keysym names to persisted hotkey tokens.

    Args:
        keysym: Tk keysym string from a key event.

    Returns:
        Normalized hotkey token or ``None`` when the keysym is unsupported.
    """
    normalized = keysym.lower()
    alias_map = {
        "control_l": "ctrl",
        "control_r": "ctrl",
        "shift_l": "shift",
        "shift_r": "shift",
        "alt_l": "alt",
        "alt_r": "alt",
        "option_l": "alt",
        "option_r": "alt",
        "meta_l": "cmd",
        "meta_r": "cmd",
        "super_l": "cmd",
        "super_r": "cmd",
        "win_l": "cmd",
        "win_r": "cmd",
    }
    token = alias_map.get(normalized, normalized)
    if token in _HOTKEY_MODIFIERS:
        return token
    if len(token) == 1 and token.isprintable():
        return token
    if token.startswith("f") and token[1:].isdigit():
        return token
    allowed_named = {
        "space",
        "tab",
        "escape",
        "enter",
        "backspace",
        "delete",
        "insert",
        "home",
        "end",
        "page_up",
        "page_down",
        "up",
        "down",
        "left",
        "right",
    }
    return token if token in allowed_named else None


def _modifier_tokens_from_event_state(state: int, *, include_alt: bool) -> list[str]:
    """Extract active modifier tokens from Tk event state bitmasks.

    Args:
        state: Tk event state bitmask.
        include_alt: Whether to include ALT when the ALT bit is present.

    Returns:
        Active normalized modifier tokens in deterministic order.
    """
    modifiers: list[str] = []
    if state & _CTRL_EVENT_MASK:
        modifiers.append("ctrl")
    if state & _SHIFT_EVENT_MASK:
        modifiers.append("shift")
    if include_alt and state & _ALT_EVENT_MASK:
        modifiers.append("alt")
    return modifiers


def _ordered_modifiers(modifiers: set[str]) -> list[str]:
    """Return modifiers in canonical display/persist order.

    Args:
        modifiers: Active modifier token set.

    Returns:
        Modifier list ordered for display and persistence.
    """
    return [modifier for modifier in _HOTKEY_MODIFIERS if modifier in modifiers]


def _choose_hotkey_preview(
    *, active: str, captured: str | None, has_trigger: bool
) -> str | None:
    """Choose what to show: active combo-in-progress or last complete combo.

    Args:
        active: Current in-progress capture text from held keys.
        captured: Last completed hotkey capture, if one exists.
        has_trigger: Whether the current in-progress state includes a trigger key.

    Returns:
        Preferred preview value for the hotkey entry or ``None``.
    """
    if has_trigger:
        return active or captured
    if captured:
        return captured
    return active or None


def _build_hotkey_value(modifiers: list[str], trigger: str | None) -> str:
    """Build normalized hotkey text from held modifiers and trigger.

    Args:
        modifiers: Ordered active modifiers.
        trigger: Trigger token or ``None`` when not captured yet.

    Returns:
        Normalized hotkey string suitable for persistence.
    """
    if trigger is None:
        return f"{'+'.join(modifiers)}+" if modifiers else ""
    if modifiers:
        return f"{'+'.join(modifiers)}+{trigger}"
    return trigger


def _format_hotkey_display(value: str) -> str:
    """Render normalized hotkey text in user-facing uppercase form.

    Args:
        value: Normalized persisted hotkey text.

    Returns:
        Display-formatted hotkey text for the settings entry.
    """
    return value.replace("+", "-").upper()


def _normalize_hotkey_capture_value(value: str) -> str:
    """Convert user-facing hotkey preview text into normalized persisted form.

    Args:
        value: User-facing hotkey capture text from the entry.

    Returns:
        Normalized hotkey string suitable for parser and persistence.
    """
    out = value.strip().lower().replace("-", "+")
    while "++" in out:
        out = out.replace("++", "+")
    if out.endswith("+"):
        out = out[:-1]
    return out


def _confirm_restore_defaults() -> bool:
    """Ask the user to confirm replacing the file-backed config with defaults.

    Returns:
        True when the user confirms restoring defaults.
    """
    return bool(
        messagebox.askyesno(
            "Restore defaults",
            "Restore the supported Vox settings defaults and autosave them now?",
        )
    )


def create_settings_controller() -> SettingsController:
    """Build the default controller using current persisted config state.

    Returns:
        Settings controller initialized from current persisted config state.
    """
    return SettingsController(
        persisted_config=load_persisted_config(),
        overridden_fields=get_env_override_fields(),
        restore_confirmer=_confirm_restore_defaults,
    )


def run_settings_window() -> None:
    """Open the standalone Vox settings window."""
    root = tk.Tk()
    controller = create_settings_controller()
    SettingsWindow(root, controller)
    root.mainloop()
