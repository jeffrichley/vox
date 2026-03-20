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

    def test_valid_cue_volume_passes(self) -> None:
        """Cue volume accepts bounded numeric values."""
        # Arrange - config with bounded cue volume

        # Act - validate
        vox_config.validate_config({"hotkey": "x", "cue_volume": 0.5})

        # Assert - no exception

    def test_invalid_cue_volume_raises(self) -> None:
        """Out-of-range cue volume fails with a field-specific error."""
        # Arrange - invalid cue volume

        # Act - validate config with invalid cue volume

        # Assert - validation fails with cue_volume in message
        with pytest.raises(ValueError, match="cue_volume"):
            vox_config.validate_config({"hotkey": "x", "cue_volume": 1.5})


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

    def test_load_config_applies_cue_volume_env_override(self) -> None:
        """VOX_CUE_VOLUME is parsed to float and overrides TOML."""
        # Arrange - TOML plus cue-volume env override
        with mock.patch.object(vox_config, "_get_config_paths") as mock_paths:
            mock_paths.return_value = [vox_config.vox_user_dir() / "vox.toml"]
            with (
                mock.patch.object(
                    vox_config,
                    "_load_toml",
                    return_value={"hotkey": "ctrl+space", "cue_volume": 1.0},
                ),
                mock.patch.dict(os.environ, {"VOX_CUE_VOLUME": "0.25"}, clear=False),
            ):
                # Act - call load_config
                out = vox_config.load_config()

        # Assert - env override applied to cue volume
        assert out["cue_volume"] == 0.25


@pytest.mark.unit
class TestPersistedConfig:
    """Editable config helpers should stay file-backed and deterministic."""

    def test_get_persisted_config_path_prefers_vox_config_env(self) -> None:
        """Writes should target VOX_CONFIG when it is set."""
        # Arrange - set a custom config path in the environment
        with mock.patch.dict(
            os.environ,
            {"VOX_CONFIG": "/custom/settings/vox.toml"},
            clear=False,
        ):
            # Act - resolve the writable config path
            out = vox_config.get_persisted_config_path()

        # Assert - writes target the configured path
        assert out == Path("/custom/settings/vox.toml")

    def test_load_persisted_config_does_not_apply_env_overrides(self) -> None:
        """Editable config should reflect TOML only, not effective runtime env values."""
        # Arrange - TOML contains one value while env overrides specify others
        with (
            mock.patch.object(
                vox_config,
                "_get_config_paths",
                return_value=[Path("/tmp/vox.toml")],
            ),
            mock.patch.object(
                vox_config,
                "_load_toml",
                return_value={"hotkey": "ctrl+space", "cue_volume": 0.5},
            ),
            mock.patch.dict(
                os.environ,
                {"VOX_HOTKEY": "alt+v", "VOX_CUE_VOLUME": "0.25"},
                clear=False,
            ),
        ):
            # Act - load the file-backed editable config
            out = vox_config.load_persisted_config()

        # Assert - env overrides are not folded into the editable dict
        assert out == {"hotkey": "ctrl+space", "cue_volume": 0.5}

    def test_serialize_persisted_config_is_deterministic(self) -> None:
        """Supported keys should be written in a stable order with TOML values."""
        # Arrange - provide supported keys in a non-output order
        serialized = vox_config.serialize_persisted_config(
            {
                "use_tray": True,
                "hotkey": "ctrl+space",
                "cue_volume": 0.25,
                "model_size": "small",
            }
        )

        # Act - serialization already executed above

        # Assert - TOML output is ordered and deterministic
        assert serialized == (
            'hotkey = "ctrl+space"\n'
            'model_size = "small"\n'
            "cue_volume = 0.25\n"
            "use_tray = true\n"
        )

    def test_write_persisted_config_uses_atomic_replace(self, tmp_path: Path) -> None:
        """Config writes should go through a temp file and replace into place."""
        # Arrange - capture replace calls while writing to a temp directory
        config_path = tmp_path / "vox.toml"
        replace_calls: list[tuple[Path, Path]] = []

        def fake_replace(
            src: str | os.PathLike[str], dst: str | os.PathLike[str]
        ) -> None:
            src_path = Path(src)
            dst_path = Path(dst)
            replace_calls.append((src_path, dst_path))
            dst_path.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
            src_path.unlink()

        with mock.patch("vox.config.os.replace", side_effect=fake_replace):
            # Act - write the persisted config
            out_path = vox_config.write_persisted_config(
                {"hotkey": "ctrl+space", "cue_volume": 0.5},
                path=config_path,
            )

        # Assert - the final write used os.replace from a temp file in the same directory
        assert out_path == config_path
        assert config_path.read_text(encoding="utf-8") == (
            'hotkey = "ctrl+space"\ncue_volume = 0.5\n'
        )
        assert len(replace_calls) == 1
        assert replace_calls[0][1] == config_path
        assert replace_calls[0][0].parent == tmp_path
        assert replace_calls[0][0].suffix == ".tmp"

    def test_write_persisted_config_rejects_invalid_edits(self, tmp_path: Path) -> None:
        """Invalid file-backed updates must fail before any disk write occurs."""
        # Arrange - attempt to persist an invalid hotkey to a new config path
        config_path = tmp_path / "vox.toml"

        with (
            pytest.raises(vox_config.ConfigError, match="hotkey"),
            mock.patch("vox.config.os.replace") as mock_replace,
        ):
            # Act - write invalid config
            vox_config.write_persisted_config({"hotkey": ""}, path=config_path)

        # Assert - the write fails before any atomic replace happens
        mock_replace.assert_not_called()
        assert not config_path.exists()

    def test_update_persisted_config_merges_changes_before_write(self) -> None:
        """Targeted updates should preserve other persisted keys."""
        # Arrange - existing persisted config already has unrelated keys
        with (
            mock.patch.object(
                vox_config,
                "load_persisted_config",
                return_value={"hotkey": "ctrl+space", "use_tray": False},
            ),
            mock.patch.object(vox_config, "write_persisted_config") as mock_write,
        ):
            # Act - update a single field
            out = vox_config.update_persisted_config({"use_tray": True})

        # Assert - the write payload preserves untouched fields
        assert out == {"hotkey": "ctrl+space", "use_tray": True}
        mock_write.assert_called_once_with(
            {"hotkey": "ctrl+space", "use_tray": True},
            path=None,
        )

    def test_get_env_override_fields_reports_active_overrides(self) -> None:
        """UI metadata should identify which fields are superseded by env vars."""
        # Arrange - activate a subset of config env overrides
        with mock.patch.dict(
            os.environ,
            {
                "VOX_HOTKEY": "alt+v",
                "VOX_DEVICE_ID": "3",
                "VOX_CUE_VOLUME": "0.1",
            },
            clear=False,
        ):
            # Act - inspect override metadata
            out = vox_config.get_env_override_fields()

        # Assert - only active overrides are reported with their source env vars
        assert out == {
            "hotkey": "VOX_HOTKEY",
            "device_id": "VOX_DEVICE_ID",
            "cue_volume": "VOX_CUE_VOLUME",
        }


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
        assert out["cue_volume"] == 0.5

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

    def test_returns_explicit_cue_volume(self) -> None:
        """get_config preserves an explicitly configured cue volume."""
        # Arrange - config provides cue volume
        with mock.patch.object(
            vox_config,
            "load_config",
            return_value={"hotkey": "ctrl+space", "cue_volume": 0.25},
        ):
            # Act - read config
            out = vox_config.get_config()

        # Assert - cue volume is preserved
        assert out["cue_volume"] == 0.25
