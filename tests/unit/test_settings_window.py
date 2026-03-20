"""Unit tests for settings-window autosave orchestration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from vox.config import ConfigError, load_persisted_config
from vox.gui.settings_window import (
    DEFAULT_SETTINGS,
    SETTINGS_SECTIONS,
    SettingsController,
)
from vox.transcribe import TranscriptionError


@dataclass
class FakeScheduler:
    """Simple scheduler test double that stores one pending callback."""

    token_counter: int = 0
    canceled_tokens: list[str] | None = None
    callbacks: dict[str, Callable[[], None]] | None = None

    def __post_init__(self) -> None:
        """Initialize mutable scheduler storage."""
        self.canceled_tokens = []
        self.callbacks = {}

    def schedule(self, _delay_ms: int, callback: Callable[[], None]) -> str:
        """Store the callback and return a unique token."""
        self.token_counter += 1
        token = f"token-{self.token_counter}"
        assert self.callbacks is not None
        self.callbacks[token] = callback
        return token

    def cancel(self, token: str | None) -> None:
        """Track canceled tokens and drop the pending callback."""
        if token is None:
            return
        assert self.canceled_tokens is not None
        assert self.callbacks is not None
        self.canceled_tokens.append(token)
        self.callbacks.pop(token, None)

    def flush_latest(self) -> None:
        """Run the most recently scheduled callback."""
        assert self.callbacks is not None
        token = sorted(self.callbacks)[-1]
        callback = self.callbacks.pop(token)
        callback()


def _build_controller(
    *,
    persisted_config: Mapping[str, object] | None = None,
    dependencies: Mapping[str, object] | None = None,
    overridden_fields: Mapping[str, str] | None = None,
) -> SettingsController:
    """Build a controller with safe test doubles by default."""
    dependency_overrides = dict(dependencies or {})
    updates_writer = dependency_overrides.get(
        "save_updates",
        lambda updates: dict(DEFAULT_SETTINGS) | dict(updates),
    )
    replace_writer = dependency_overrides.get(
        "replace_all",
        lambda _config: Path("vox.toml"),
    )
    return SettingsController(
        persisted_config=persisted_config,
        overridden_fields=overridden_fields,
        save_updates=updates_writer,
        replace_all=replace_writer,
        scheduler=dependency_overrides.get("scheduler"),
        device_loader=dependency_overrides.get(
            "device_loader",
            lambda: [(1, "USB Mic", "WASAPI")],
        ),
        mic_tester=dependency_overrides.get("mic_tester", lambda _device_id: None),
        cue_tester=dependency_overrides.get("cue_tester", lambda _volume: None),
        restore_confirmer=dependency_overrides.get(
            "restore_confirmer",
            lambda: True,
        ),
    )


@pytest.mark.unit
class TestSettingsController:
    """SettingsController handles autosave and status messaging."""

    def test_sections_constant_covers_required_settings_groups(self) -> None:
        """The settings surface should advertise the planned top-level sections."""
        # Arrange - no additional setup required

        # Act - inspect the exported section titles
        sections = SETTINGS_SECTIONS

        # Assert - all required sections are present
        assert sections == ("Recording", "Transcription", "Output", "Runtime")

    def test_commit_choice_persists_immediately_and_sets_restart_message(self) -> None:
        """Combobox and toggle changes should autosave as soon as selection completes."""
        # Arrange - capture persisted updates from an immediate selection change
        saved_updates: list[Mapping[str, object]] = []

        def save_updates(updates: Mapping[str, object]) -> dict[str, object]:
            saved_updates.append(updates)
            return dict(DEFAULT_SETTINGS) | dict(updates)

        controller = _build_controller(dependencies={"save_updates": save_updates})

        # Act - commit a restart-sensitive combobox change
        succeeded = controller.commit_choice("model_size", "small")

        # Assert - the update persisted immediately with restart guidance
        assert succeeded is True
        assert saved_updates == [{"model_size": "small"}]
        assert controller.values["model_size"] == "small"
        assert "Restart Vox" in controller.status.text

    def test_commit_choice_uses_controller_state_as_persist_base(
        self, tmp_path: Path
    ) -> None:
        """First-run autosave should not fail when only defaults supply required fields."""
        # Arrange - use the real persisted-config writer against an empty config file
        config_path = tmp_path / "vox.toml"
        config_path.write_text("", encoding="utf-8")
        controller = SettingsController(persisted_config={})

        # Act - change a restart-sensitive field before ever editing hotkey
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setenv("VOX_CONFIG", str(config_path))
            succeeded = controller.commit_choice("model_size", "small")
            persisted = load_persisted_config()

        # Assert - the save succeeds and persists the implied default hotkey too
        assert succeeded is True
        assert persisted["hotkey"] == DEFAULT_SETTINGS["hotkey"]
        assert persisted["model_size"] == "small"

    def test_schedule_slider_save_debounces_repeated_updates_and_previews_cue(
        self,
    ) -> None:
        """Rapid slider movement should save and preview only the final value."""
        # Arrange - use a fake scheduler and capture saved slider updates
        scheduler = FakeScheduler()
        saved_updates: list[Mapping[str, object]] = []
        previewed_volumes: list[float] = []

        def save_updates(updates: Mapping[str, object]) -> dict[str, object]:
            saved_updates.append(updates)
            return dict(DEFAULT_SETTINGS) | dict(updates)

        def cue_tester(volume: float) -> None:
            previewed_volumes.append(volume)

        controller = _build_controller(
            dependencies={
                "save_updates": save_updates,
                "scheduler": scheduler,
                "cue_tester": cue_tester,
            }
        )

        # Act - schedule two rapid cue-volume changes, then flush the debounce
        controller.schedule_slider_save("cue_volume", 0.2)
        controller.schedule_slider_save("cue_volume", 0.4)
        scheduler.flush_latest()

        # Assert - only the final value is persisted
        assert scheduler.canceled_tokens == ["token-1"]
        assert saved_updates == [{"cue_volume": 0.4}]
        assert previewed_volumes == [0.4]
        assert controller.values["cue_volume"] == 0.4
        assert controller.status.text == "Saved. Cue preview completed."

    def test_commit_text_waits_for_explicit_completion(self) -> None:
        """Text-like settings should persist only when editing finishes."""
        # Arrange - controller with a save spy
        saved_updates: list[Mapping[str, object]] = []

        def save_updates(updates: Mapping[str, object]) -> dict[str, object]:
            saved_updates.append(updates)
            return dict(DEFAULT_SETTINGS) | dict(updates)

        controller = _build_controller(dependencies={"save_updates": save_updates})

        # Act - make no commit, then explicitly commit a hotkey edit
        controller.values["hotkey"] = "ctrl+space"
        before_commit = list(saved_updates)
        succeeded = controller.commit_text("hotkey", "ctrl+alt+v")

        # Assert - persistence only happens on explicit completion
        assert before_commit == []
        assert succeeded is True
        assert saved_updates == [{"hotkey": "ctrl+alt+v"}]
        assert controller.values["hotkey"] == "ctrl+alt+v"

    def test_commit_error_leaves_previous_value_and_surfaces_validation_feedback(
        self,
    ) -> None:
        """Invalid completed edits should not replace the last good saved value."""
        # Arrange - a controller whose persistence layer rejects the edit
        controller = _build_controller(
            persisted_config={"hotkey": "ctrl+shift+v"},
            dependencies={
                "save_updates": lambda _updates: (_ for _ in ()).throw(
                    ConfigError("hotkey: must be a non-empty string")
                )
            },
        )

        # Act - attempt to commit an invalid text edit
        succeeded = controller.commit_text("hotkey", "")

        # Assert - the invalid value is not accepted as the saved state
        assert succeeded is False
        assert controller.values["hotkey"] == "ctrl+shift+v"
        assert controller.status.text == "hotkey: must be a non-empty string"

    def test_restore_defaults_requires_confirmation(self) -> None:
        """Restore defaults should not write anything unless the user confirms."""
        # Arrange - a controller with a rejecting confirmer and replace spy
        replace_calls: list[Mapping[str, object]] = []
        controller = _build_controller(
            dependencies={
                "replace_all": lambda config: (
                    replace_calls.append(config) or Path("vox.toml")
                ),
                "restore_confirmer": lambda: False,
            }
        )

        # Act - try to restore defaults without confirmation
        succeeded = controller.restore_defaults()

        # Assert - no write occurs and the status reflects cancellation
        assert succeeded is False
        assert replace_calls == []
        assert controller.status.text == "Restore defaults canceled."

    def test_restore_defaults_writes_supported_defaults(self) -> None:
        """Confirmed restore-defaults should replace the config with known defaults."""
        # Arrange - capture the config written by a confirmed restore
        replace_calls: list[Mapping[str, object]] = []
        controller = _build_controller(
            persisted_config={"hotkey": "alt+v", "use_tray": True},
            dependencies={
                "replace_all": lambda config: (
                    replace_calls.append(config) or Path("vox.toml")
                )
            },
        )

        # Act - restore the supported defaults
        succeeded = controller.restore_defaults()

        # Assert - the file-backed config is replaced with the expected defaults
        assert succeeded is True
        assert replace_calls == [DEFAULT_SETTINGS]
        assert controller.values == dict(DEFAULT_SETTINGS)
        assert "Defaults restored" in controller.status.text

    def test_override_message_reports_env_source_for_ui_warning(self) -> None:
        """The UI should be able to show which env var supersedes a field."""
        # Arrange - controller with one active env override
        controller = _build_controller(
            overridden_fields={"model_size": "VOX_MODEL_SIZE"}
        )

        # Act - request the field-specific override note
        message = controller.get_override_message("model_size")

        # Assert - the warning mentions the source env var
        assert message == "Overridden by VOX_MODEL_SIZE."

    def test_test_mic_surfaces_success_status(self) -> None:
        """The microphone test action should report a successful completion state."""
        # Arrange - build a controller with a no-op mic test action
        controller = _build_controller()

        # Act - run the microphone test action
        controller.test_mic()

        # Assert - the action completes with user-visible success feedback
        assert controller.status.text == "Microphone test completed."

    @pytest.mark.parametrize(
        ("error", "expected_text"),
        [
            (ConfigError("bad config"), "bad config"),
            (ValueError("bad seconds"), "bad seconds"),
            (TranscriptionError("model missing"), "model missing"),
        ],
    )
    def test_test_mic_surfaces_expected_failures(
        self,
        error: Exception,
        expected_text: str,
    ) -> None:
        """User-facing mic test failures should update the status instead of escaping."""
        # Arrange - build a controller whose mic test raises a handled error
        controller = _build_controller(
            dependencies={
                "mic_tester": lambda _device_id: (_ for _ in ()).throw(error),
            }
        )

        # Act - run the microphone test action
        controller.test_mic()

        # Assert - the failure is reflected in the status text
        assert controller.status.text == expected_text
