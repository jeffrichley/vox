"""Unit tests for Continuous dictation fields in SettingsController (#41)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from vox.config import (
    DEFAULT_CONTINUOUS_HOTKEY,
    DEFAULT_CONTINUOUS_IDLE_MINUTES,
    DEFAULT_CONTINUOUS_PAUSE_SECONDS,
    ConfigError,
)
from vox.gui.settings_window import DEFAULT_SETTINGS, SettingsController


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
class TestContinuousSettingsDefaults:
    """DEFAULT_SETTINGS includes Continuous dictation fields."""

    def test_defaults_include_continuous_fields(self) -> None:
        """Restore-defaults source includes Continuous hotkey, Pause, and idle."""
        # Arrange - no extra setup

        # Act - read exported defaults
        defaults = DEFAULT_SETTINGS

        # Assert - Continuous keys match config-layer defaults
        assert defaults["continuous_hotkey"] == DEFAULT_CONTINUOUS_HOTKEY
        assert defaults["continuous_pause_seconds"] == DEFAULT_CONTINUOUS_PAUSE_SECONDS
        assert defaults["continuous_idle_minutes"] == DEFAULT_CONTINUOUS_IDLE_MINUTES


@pytest.mark.unit
class TestContinuousNumberFields:
    """Pause and idle minutes save valid numbers and reject invalid input."""

    def test_commit_valid_pause_and_idle_numbers(self) -> None:
        """Valid Pause and idle strings persist as floats with restart guidance."""
        # Arrange - capture persisted updates; merge into growing config state
        saved_updates: list[Mapping[str, object]] = []
        persisted = dict(DEFAULT_SETTINGS)

        def save_updates(updates: Mapping[str, object]) -> dict[str, object]:
            saved_updates.append(dict(updates))
            persisted.update(dict(updates))
            return dict(persisted)

        controller = _build_controller(dependencies={"save_updates": save_updates})

        # Act - commit valid Pause then idle minutes from entry text
        pause_ok = controller.commit_text("continuous_pause_seconds", "1.5")
        idle_ok = controller.commit_text("continuous_idle_minutes", "3")

        # Assert - both saved as floats with restart messaging
        assert pause_ok is True
        assert idle_ok is True
        assert saved_updates == [
            {"continuous_pause_seconds": 1.5},
            {"continuous_idle_minutes": 3.0},
        ]
        assert controller.values["continuous_pause_seconds"] == 1.5
        assert controller.values["continuous_idle_minutes"] == 3.0
        assert "Restart Vox" in controller.status.text

    def test_reject_non_numeric_pause(self) -> None:
        """Non-numeric Pause text is rejected with a field-specific status."""
        # Arrange - controller with a known good Pause already stored
        saved_updates: list[Mapping[str, object]] = []

        def save_updates(updates: Mapping[str, object]) -> dict[str, object]:
            saved_updates.append(dict(updates))
            return dict(DEFAULT_SETTINGS) | dict(updates)

        controller = _build_controller(
            persisted_config={"continuous_pause_seconds": 1.0},
            dependencies={"save_updates": save_updates},
        )

        # Act - commit garbage text
        succeeded = controller.commit_text("continuous_pause_seconds", "abc")

        # Assert - nothing persisted; previous value kept; status names the field
        assert succeeded is False
        assert saved_updates == []
        assert controller.values["continuous_pause_seconds"] == 1.0
        assert "continuous_pause_seconds" in controller.status.text

    def test_reject_zero_idle_minutes(self) -> None:
        """Zero idle minutes is rejected and not saved."""
        # Arrange - controller whose save path rejects non-positive idle
        controller = _build_controller(
            persisted_config={"continuous_idle_minutes": 5.0},
            dependencies={
                "save_updates": lambda _updates: (_ for _ in ()).throw(
                    ConfigError(
                        "continuous_idle_minutes: must be a finite number greater than 0"
                    )
                )
            },
        )

        # Act - commit zero
        succeeded = controller.commit_text("continuous_idle_minutes", "0")

        # Assert - previous value kept; status names the field
        assert succeeded is False
        assert controller.values["continuous_idle_minutes"] == 5.0
        assert "continuous_idle_minutes" in controller.status.text


@pytest.mark.unit
class TestContinuousHotkeyCollision:
    """Continuous hotkey collision is rejected with a status message."""

    def test_reject_hotkey_collision(self) -> None:
        """Committing a Continuous hotkey that collides fails with status text."""
        # Arrange - Push-to-talk hotkey already ctrl+alt+d; collision on save
        controller = _build_controller(
            persisted_config={
                "hotkey": "ctrl+alt+d",
                "continuous_hotkey": "ctrl+alt+f",
            },
            dependencies={
                "save_updates": lambda _updates: (_ for _ in ()).throw(
                    ConfigError(
                        "continuous_hotkey: must differ from hotkey "
                        "(modifier order and aliases like control/ctrl, win/cmd "
                        "ignored); change continuous_hotkey"
                    )
                )
            },
        )

        # Act - try to set Continuous hotkey equal to Push-to-talk
        succeeded = controller.commit_text("continuous_hotkey", "ctrl+alt+d")

        # Assert - previous Continuous hotkey kept; status mentions collision
        assert succeeded is False
        assert controller.values["continuous_hotkey"] == "ctrl+alt+f"
        assert "continuous_hotkey" in controller.status.text


@pytest.mark.unit
class TestContinuousRestoreDefaults:
    """Restore-defaults covers Continuous dictation fields."""

    def test_restore_defaults_includes_continuous_fields(self) -> None:
        """Confirmed restore writes Continuous defaults with the other fields."""
        # Arrange - capture the full config written on restore
        replace_calls: list[Mapping[str, object]] = []
        controller = _build_controller(
            persisted_config={
                "continuous_hotkey": "ctrl+alt+f",
                "continuous_pause_seconds": 2.0,
                "continuous_idle_minutes": 10.0,
            },
            dependencies={
                "replace_all": lambda config: (
                    replace_calls.append(config) or Path("vox.toml")
                )
            },
        )

        # Act - restore supported defaults
        succeeded = controller.restore_defaults()

        # Assert - Continuous keys restored to defaults
        assert succeeded is True
        assert replace_calls == [DEFAULT_SETTINGS]
        assert controller.values["continuous_hotkey"] == DEFAULT_CONTINUOUS_HOTKEY
        assert (
            controller.values["continuous_pause_seconds"]
            == DEFAULT_CONTINUOUS_PAUSE_SECONDS
        )
        assert (
            controller.values["continuous_idle_minutes"]
            == DEFAULT_CONTINUOUS_IDLE_MINUTES
        )
