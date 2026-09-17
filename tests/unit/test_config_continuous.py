"""Unit tests for Continuous dictation config keys (#35)."""

from __future__ import annotations

import math
import os
from unittest import mock

import pytest

import vox.config as vox_config


@pytest.mark.unit
class TestContinuousConfigDefaults:
    """get_config exposes Continuous defaults when keys are omitted."""

    def test_get_config_defaults_continuous_hotkey_and_pause(self) -> None:
        """Missing Continuous keys become ctrl+alt+d and 1.0."""
        # Arrange - only required hotkey present
        with mock.patch.object(
            vox_config,
            "load_config",
            return_value={"hotkey": "ctrl+f12"},
        ):
            # Act - load validated config
            out = vox_config.get_config()

        # Assert - Continuous defaults applied
        assert out["continuous_hotkey"] == "ctrl+alt+d"
        assert out["continuous_pause_seconds"] == 1.0

    def test_get_config_preserves_explicit_continuous_values(self) -> None:
        """Explicit Continuous keys survive get_config."""
        # Arrange - custom Continuous hotkey and Pause
        with mock.patch.object(
            vox_config,
            "load_config",
            return_value={
                "hotkey": "ctrl+f12",
                "continuous_hotkey": "ctrl+alt+d",
                "continuous_pause_seconds": 0.75,
            },
        ):
            # Act - load validated config
            out = vox_config.get_config()

        # Assert - explicit values preserved
        assert out["continuous_hotkey"] == "ctrl+alt+d"
        assert out["continuous_pause_seconds"] == 0.75


@pytest.mark.unit
class TestContinuousPauseValidation:
    """continuous_pause_seconds rejects non-positive and non-finite values."""

    @pytest.mark.parametrize(
        "value",
        [0, -1.0, True, "abc", math.inf, -math.inf],
    )
    def test_invalid_pause_raises_field_error(self, value: object) -> None:
        """Invalid Pause values fail with continuous_pause_seconds in the message."""
        # Arrange - config with invalid Pause value under test
        raw = {"hotkey": "ctrl+f12", "continuous_pause_seconds": value}

        # Act - validate config with invalid Pause
        # Assert - validation fails naming continuous_pause_seconds
        with pytest.raises(vox_config.ConfigError, match="continuous_pause_seconds"):
            vox_config.validate_config(raw)

    def test_positive_pause_passes(self) -> None:
        """A finite Pause greater than zero is accepted."""
        # Arrange - valid Pause
        raw = {"hotkey": "ctrl+f12", "continuous_pause_seconds": 0.5}

        # Act - validate
        vox_config.validate_config(raw)

        # Assert - no exception


@pytest.mark.unit
class TestContinuousHotkeyValidation:
    """continuous_hotkey must be a non-empty string when present."""

    def test_empty_continuous_hotkey_raises(self) -> None:
        """Empty Continuous hotkey fails with a field-specific error."""
        # Arrange - empty continuous_hotkey
        raw = {"hotkey": "ctrl+f12", "continuous_hotkey": "  "}

        # Act - validate empty Continuous hotkey
        # Assert - ConfigError names continuous_hotkey
        with pytest.raises(vox_config.ConfigError, match="continuous_hotkey"):
            vox_config.validate_config(raw)


@pytest.mark.unit
class TestHotkeyCollision:
    """Push-to-talk and Continuous hotkeys must not collide after normalization."""

    def test_identical_hotkeys_raise(self) -> None:
        """Same combo for both modes is a startup ConfigError."""
        # Arrange - identical strings
        raw = {
            "hotkey": "ctrl+alt+space",
            "continuous_hotkey": "ctrl+alt+space",
        }

        # Act - validate colliding hotkeys
        # Assert - error tells user to change continuous_hotkey
        with pytest.raises(vox_config.ConfigError, match="continuous_hotkey"):
            vox_config.validate_config(raw)

    def test_collision_despite_modifier_order_and_aliases(self) -> None:
        """Order and control/meta/win aliases still collide."""
        # Arrange - aliased / reordered equivalent combos
        raw = {
            "hotkey": "control+win+v",
            "continuous_hotkey": "cmd+ctrl+v",
        }

        # Act - validate aliased colliding hotkeys
        # Assert - collision detected after normalization
        with pytest.raises(vox_config.ConfigError, match="continuous_hotkey"):
            vox_config.validate_config(raw)

    def test_distinct_hotkeys_pass(self) -> None:
        """Different combos do not collide."""
        # Arrange - distinct combos
        raw = {
            "hotkey": "ctrl+f12",
            "continuous_hotkey": "ctrl+alt+d",
        }

        # Act - validate
        vox_config.validate_config(raw)

        # Assert - no exception


@pytest.mark.unit
class TestContinuousEnvOverrides:
    """Env vars override Continuous keys and appear in override metadata."""

    def test_load_config_applies_continuous_env_overrides(self) -> None:
        """VOX_CONTINUOUS_* override TOML values."""
        # Arrange - TOML plus Continuous env overrides
        with mock.patch.object(vox_config, "_get_config_paths") as mock_paths:
            mock_paths.return_value = [vox_config.vox_user_dir() / "vox.toml"]
            with (
                mock.patch.object(
                    vox_config,
                    "_load_toml",
                    return_value={
                        "hotkey": "ctrl+f12",
                        "continuous_hotkey": "ctrl+alt+d",
                        "continuous_pause_seconds": 1.0,
                    },
                ),
                mock.patch.dict(
                    os.environ,
                    {
                        "VOX_CONTINUOUS_HOTKEY": "ctrl+alt+f",
                        "VOX_CONTINUOUS_PAUSE_SECONDS": "0.8",
                    },
                    clear=False,
                ),
            ):
                # Act - load config
                out = vox_config.load_config()

        # Assert - env wins
        assert out["continuous_hotkey"] == "ctrl+alt+f"
        assert out["continuous_pause_seconds"] == 0.8

    def test_get_env_override_fields_includes_continuous(self) -> None:
        """Override metadata reports Continuous env sources."""
        # Arrange - Continuous env vars set
        with mock.patch.dict(
            os.environ,
            {
                "VOX_CONTINUOUS_HOTKEY": "ctrl+alt+d",
                "VOX_CONTINUOUS_PAUSE_SECONDS": "0.8",
            },
            clear=False,
        ):
            # Act - inspect override metadata
            out = vox_config.get_env_override_fields()

        # Assert - Continuous fields mapped to env names
        assert out["continuous_hotkey"] == "VOX_CONTINUOUS_HOTKEY"
        assert out["continuous_pause_seconds"] == "VOX_CONTINUOUS_PAUSE_SECONDS"
