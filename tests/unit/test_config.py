"""Unit tests for config load and validation."""
# drill-sergeant: file-length ignore

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from vox import config as vox_config


@pytest.mark.unit
class TestValidateConfig:
    """Config validation: required and optional fields."""

    def test_missing_hotkey_raises_with_field_name(self) -> None:
        """Missing hotkey must raise ValueError with message containing 'hotkey'."""
        # Arrange - empty config

        # Act - validate empty config
        # Assert - validation fails with hotkey in message
        with pytest.raises(ValueError, match="hotkey"):
            vox_config.validate_config({})

    def test_empty_hotkey_raises(self) -> None:
        """Empty or whitespace hotkey raises."""
        # Arrange - invalid hotkey values

        # Act - validate empty string hotkey
        # Assert - validation fails with hotkey in message
        with pytest.raises(ValueError, match="hotkey"):
            vox_config.validate_config({"hotkey": ""})
        # Act - validate whitespace hotkey
        # Assert - validation fails with hotkey in message
        with pytest.raises(ValueError, match="hotkey"):
            vox_config.validate_config({"hotkey": "   "})

    def test_valid_hotkey_passes(self) -> None:
        """Non-empty string hotkey passes validation."""
        # Arrange - valid hotkey

        # Act - validate
        vox_config.validate_config({"hotkey": "ctrl+space"})

        # Assert - no exception

    def test_device_id_must_be_int_if_present(self) -> None:
        """If device_id is present and not None, it must be an int."""
        # Arrange - invalid then valid device_id values

        # Act / Assert - invalid type errors
        with pytest.raises(ValueError, match="device_id"):
            vox_config.validate_config({"hotkey": "x", "device_id": "not-an-int"})
        # Act - validate valid ids
        vox_config.validate_config({"hotkey": "x", "device_id": 0})
        vox_config.validate_config({"hotkey": "x", "device_id": None})

        # Assert - no exception

    def test_optional_fields_can_be_empty_in_raw(self) -> None:
        """Hotkey required; other fields optional."""
        # Arrange - only required field

        # Act - validate
        vox_config.validate_config({"hotkey": "a"})

        # Assert - no exception

    def test_valid_injection_mode_type_passes(self) -> None:
        """Direct typing mode is accepted when configured explicitly."""
        # Arrange - config with type injection

        # Act - validate
        vox_config.validate_config({"hotkey": "x", "injection_mode": "type"})

        # Assert - no exception

    def test_invalid_injection_mode_raises(self) -> None:
        """Unknown injection modes fail with a field-specific error."""
        # Arrange - unsupported injection mode

        # Act - validate config with unsupported injection mode

        # Assert - validation fails with injection_mode in message
        with pytest.raises(ValueError, match="injection_mode"):
            vox_config.validate_config({"hotkey": "x", "injection_mode": "paste"})


@pytest.mark.unit
class TestConfigPaths:
    """Config search order uses user .vox directory."""

    def test_vox_user_dir_used(self) -> None:
        """Config is looked up in ~/.vox/vox.toml (and VOX_CONFIG if set)."""
        # Arrange - no setup required

        # Act - compute paths
        paths = vox_config._get_config_paths()

        # Assert - contains user config and only vox.toml names
        assert vox_config.vox_user_dir() / "vox.toml" in paths
        assert all(p.name == "vox.toml" for p in paths)

    def test_get_config_paths_prepends_vox_config_env_when_set(self) -> None:
        """When VOX_CONFIG is set, that path is first in the list."""
        # Arrange - set VOX_CONFIG
        env_path = "/custom/vox.toml"
        with mock.patch.dict(os.environ, {"VOX_CONFIG": env_path}, clear=False):
            # Act - get paths
            paths = vox_config._get_config_paths()
            # Assert - first path is the env path
            assert paths[0] == Path(env_path)
            assert vox_config.vox_user_dir() / "vox.toml" in paths


@pytest.mark.unit
class TestLoadToml:
    """_load_toml returns dict or empty on missing/invalid."""

    def test_load_toml_returns_empty_when_path_not_file(self) -> None:
        """When path is not a file, _load_toml returns empty dict."""
        # Arrange - path that does not exist (no patch; Path.is_file is read-only on Windows)
        path = Path("/nonexistent_xyz_12345/vox.toml")
        # Act - call _load_toml with non-existent path
        result = vox_config._load_toml(path)
        # Assert - returns empty dict
        assert result == {}

    def test_load_toml_returns_empty_on_read_error(self) -> None:
        """When opening/parsing fails, _load_toml returns empty dict."""
        # Arrange - use temp path that exists; patch open to raise OSError
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            path = Path(f.name)
        try:
            with mock.patch("builtins.open", side_effect=OSError("permission denied")):
                # Act - call _load_toml
                result = vox_config._load_toml(path)
                # Assert - returns empty dict
                assert result == {}
        finally:
            path.unlink(missing_ok=True)

    def test_load_toml_returns_empty_on_value_error(self) -> None:
        """When tomllib.load raises ValueError (invalid TOML), _load_toml returns empty dict."""
        # Arrange - temp file that exists; patch tomllib.load to raise ValueError
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            path = Path(f.name)
        try:
            with mock.patch(
                "vox.config.tomllib.load", side_effect=ValueError("invalid TOML")
            ):
                # Act - call _load_toml (open will succeed, tomllib.load will raise)
                result = vox_config._load_toml(path)
                # Assert - returns empty dict
                assert result == {}
        finally:
            path.unlink(missing_ok=True)


@pytest.mark.unit
class TestApplyDeviceIdEnv:
    """_apply_device_id_env sets device_id from VOX_DEVICE_ID."""

    def test_apply_device_id_env_sets_int_when_vox_device_id_is_int_string(
        self,
    ) -> None:
        """When VOX_DEVICE_ID is a string of an int, raw['device_id'] becomes int."""
        # Arrange - env has VOX_DEVICE_ID as int string
        raw: dict = {}
        with mock.patch.dict(os.environ, {"VOX_DEVICE_ID": "3"}, clear=False):
            # Act - apply env overrides
            vox_config._apply_device_id_env(raw)
            # Assert - device_id is int 3
            assert raw["device_id"] == 3

    def test_apply_device_id_env_sets_string_when_vox_device_id_not_int(self) -> None:
        """When VOX_DEVICE_ID is not an int string, raw['device_id'] is still set (string)."""
        # Arrange - env has non-int VOX_DEVICE_ID
        raw: dict[str, object] = {}
        with mock.patch.dict(os.environ, {"VOX_DEVICE_ID": "default"}, clear=False):
            # Act - apply env overrides
            vox_config._apply_device_id_env(raw)
            # Assert - device_id is string
            assert raw["device_id"] == "default"


@pytest.mark.unit
class TestLoadConfig:
    """load_config merges TOML and applies env overrides."""

    def test_load_config_merges_first_found_toml_and_breaks(self) -> None:
        """load_config loads first path that returns data and applies env overrides."""

        # Arrange - first path returns empty, second returns data
        def load_toml(p: Path) -> dict:
            if "user" in str(p) or ".vox" in str(p):
                return {"hotkey": "ctrl+space", "model_size": "small"}
            return {}

        with mock.patch.object(vox_config, "_get_config_paths") as mock_paths:
            mock_paths.return_value = [
                Path("/first/vox.toml"),
                vox_config.vox_user_dir() / "vox.toml",
            ]
            with (
                mock.patch.object(vox_config, "_load_toml", side_effect=load_toml),
                mock.patch.object(vox_config, "_apply_env_overrides"),
            ):
                # Act - call load_config
                out = vox_config.load_config()
                # Assert - hotkey and model_size from TOML
                assert out["hotkey"] == "ctrl+space"
                assert out.get("model_size") == "small"

    def test_load_config_applies_env_overrides(self) -> None:
        """load_config calls _apply_env_overrides so VOX_HOTKEY overrides TOML."""
        # Arrange - one path returns data; env has VOX_HOTKEY
        with mock.patch.object(vox_config, "_get_config_paths") as mock_paths:
            mock_paths.return_value = [vox_config.vox_user_dir() / "vox.toml"]
            with (
                mock.patch.object(
                    vox_config, "_load_toml", return_value={"hotkey": "ctrl+space"}
                ),
                mock.patch.dict(os.environ, {"VOX_HOTKEY": "alt+v"}, clear=False),
            ):
                # Act - call load_config
                out = vox_config.load_config()
                # Assert - env override applied to hotkey
                assert out["hotkey"] == "alt+v"


@pytest.mark.unit
class TestValidateOptionalStr:
    """_validate_optional_str raises when key present and not non-empty string."""

    def test_validate_optional_str_raises_when_key_empty_string(self) -> None:
        """When key is present and value is empty string, ValueError is raised."""
        # Arrange - optional key present but empty
        raw = {"hotkey": "x", "model_size": ""}
        # Act - validate optional string for model_size
        # Assert - ValueError with model_size or non-empty in message
        with pytest.raises(ValueError, match=r"model_size|non-empty"):
            vox_config._validate_optional_str(raw, "model_size")


@pytest.mark.unit
class TestGetTranscriptionOptions:
    """get_transcription_options() returns defaults when keys missing."""

    def test_returns_defaults_when_no_config(self) -> None:
        """When load_config returns empty, we get base/float32/cpu."""
        # Arrange - empty config
        with mock.patch.object(vox_config, "load_config", return_value={}):
            # Act - read transcription options
            out = vox_config.get_transcription_options()
        # Assert - defaults applied
        assert out.model_size == "base"
        assert out.compute_type == "float32"
        assert out.compute_device == "cpu"

    def test_uses_config_when_present(self) -> None:
        """When config has values, they are returned."""
        # Arrange - config provides transcription settings
        with mock.patch.object(
            vox_config,
            "load_config",
            return_value={
                "model_size": "small",
                "compute_type": "int8",
                "compute_device": "cuda",
            },
        ):
            # Act - read transcription options
            out = vox_config.get_transcription_options()
        # Assert - returned settings match config
        assert out.model_size == "small"
        assert out.compute_type == "int8"
        assert out.compute_device == "cuda"

    def test_invalid_compute_device_raises(self) -> None:
        """Invalid compute_device (e.g. gpu) raises ConfigError."""
        # Arrange - invalid device
        with (
            mock.patch.object(
                vox_config,
                "load_config",
                return_value={"compute_device": "gpu"},
            ),
            pytest.raises(vox_config.ConfigError),
        ):
            # Act - build transcription options
            vox_config.get_transcription_options()
        # Assert - exception raised

    def test_invalid_model_size_raises(self) -> None:
        """Invalid model_size (unknown name, not a path) raises ConfigError."""
        # Arrange - invalid model size
        with (
            mock.patch.object(
                vox_config,
                "load_config",
                return_value={"model_size": "huge"},
            ),
            pytest.raises(vox_config.ConfigError, match="model_size"),
        ):
            # Act - build transcription options
            vox_config.get_transcription_options()
        # Assert - exception raised

    def test_invalid_compute_type_raises(self) -> None:
        """Invalid compute_type raises ConfigError."""
        # Arrange - invalid compute_type
        with (
            mock.patch.object(
                vox_config,
                "load_config",
                return_value={"compute_type": "float64"},
            ),
            pytest.raises(vox_config.ConfigError, match="compute_type"),
        ):
            # Act - build transcription options
            vox_config.get_transcription_options()
        # Assert - exception raised

    def test_model_size_path_accepted(self) -> None:
        """model_size can be a path to a model dir."""
        # Arrange - path-like model size should pass
        with mock.patch.object(
            vox_config,
            "load_config",
            return_value={"model_size": "/path/to/model"},
        ):
            # Act - build transcription options
            out = vox_config.get_transcription_options()
        # Assert - path accepted
        assert out.model_size == "/path/to/model"


@pytest.mark.unit
class TestGetConfig:
    """get_config() loads and validates; applies optional defaults."""

    def test_missing_hotkey_raises(self) -> None:
        """When no config has hotkey, get_config raises with 'hotkey' in message."""
        # Arrange - empty config
        with (
            mock.patch.object(vox_config, "load_config", return_value={}),
            pytest.raises(ValueError, match="hotkey"),
        ):
            # Act - read config
            vox_config.get_config()
        # Assert - exception raised

    def test_returns_dict_with_required_and_defaults(self) -> None:
        """get_config returns dict with hotkey and optional defaults."""
        # Arrange - minimal required config
        with mock.patch.object(
            vox_config,
            "load_config",
            return_value={"hotkey": "ctrl+space"},
        ):
            # Act - read config
            out = vox_config.get_config()
        # Assert - required + defaults present
        assert out["hotkey"] == "ctrl+space"
        assert out["device_id"] is None
        assert out["model_size"] == "base"
        assert out["compute_type"] == "float32"
        assert out["compute_device"] == "cpu"
        assert out["injection_mode"] == "clipboard"

    def test_returns_explicit_type_injection_mode(self) -> None:
        """get_config preserves the direct typing injection mode."""
        # Arrange - config provides type injection
        with mock.patch.object(
            vox_config,
            "load_config",
            return_value={"hotkey": "ctrl+space", "injection_mode": "type"},
        ):
            # Act - read config
            out = vox_config.get_config()
        # Assert - injection mode is preserved
        assert out["injection_mode"] == "type"
