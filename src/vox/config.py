"""Configuration schema and load from file/env with validation."""

from __future__ import annotations

import os

# Use tomllib (stdlib in Python 3.11+) for reading TOML
import tomllib
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, ValidationError, field_validator


class ConfigError(ValueError):
    """Raised when config validation fails (e.g. missing or invalid field)."""

    pass


# Allowed faster-whisper model sizes (and .en). Custom paths also accepted.
ALLOWED_MODEL_SIZES: frozenset[str] = frozenset(
    {
        "tiny",
        "tiny.en",
        "base",
        "base.en",
        "small",
        "small.en",
        "medium",
        "medium.en",
        "large",
        "large-v1",
        "large-v2",
        "large-v3",
        "large-v3-turbo",
        "turbo",
        "distil-small.en",
        "distil-medium.en",
        "distil-large-v2",
        "distil-large-v3",
        "distil-large-v3.5",
    }
)

ALLOWED_COMPUTE_TYPES: frozenset[str] = frozenset(
    {
        "float32",
        "float16",
        "int8",
        "int8_float16",
    }
)

ALLOWED_INJECTION_MODES: frozenset[str] = frozenset(
    {
        "clipboard",
        "clipboard_and_paste",
        "type",
    }
)


def _is_model_path(s: str) -> bool:
    """True if s looks like a path (separator or ~).

    Args:
        s: Candidate model size or path string.

    Returns:
        True if s contains path separators or starts with ~.
    """
    return "/" in s or "\\" in s or s.startswith("~")


def _is_allowed_model(s: str) -> bool:
    """True if s is a known size name or a path.

    Args:
        s: Candidate model size or path string.

    Returns:
        True if s is in ALLOWED_MODEL_SIZES or looks like a path.
    """
    return s in ALLOWED_MODEL_SIZES or _is_model_path(s)


class TranscriptionOptions(BaseModel):
    """Options for transcription (model size, device, compute type)."""

    model_size: str = Field(
        default="base",
        min_length=1,
        description="Whisper model size (e.g. tiny, base, small) or path to model dir.",
    )
    compute_type: Literal["float32", "float16", "int8", "int8_float16"] = Field(
        default="float32",
        description="Compute type: float32, float16, int8, or int8_float16.",
    )
    compute_device: Literal["cpu", "cuda"] = Field(
        default="cpu",
        description="Device for inference",
    )

    @field_validator("model_size", mode="before")
    @classmethod
    def _validate_model_size(cls, v: str) -> str:
        _ = cls  # classmethod requires first arg; unused in this validator
        s = (v or "base").strip()
        if not s:
            return "base"
        if _is_allowed_model(s):
            return s
        raise ValueError(
            f"model_size must be one of {sorted(ALLOWED_MODEL_SIZES)} "
            f"or a path to a model dir; got {s!r}"
        )


def vox_user_dir() -> Path:
    """Return the user-level .vox directory (e.g. ~/.vox).

    Returns:
        Path to the .vox directory in the user's home directory.
    """
    return Path.home() / ".vox"


def _get_config_paths() -> list[Path]:
    """Return candidate config file paths in search order.

    Order: VOX_CONFIG (if set), then ~/.vox/vox.toml.

    Returns:
        List of paths to try for vox.toml.
    """
    paths: list[Path] = [vox_user_dir() / "vox.toml"]
    env_path = os.environ.get("VOX_CONFIG")
    if env_path:
        paths.insert(0, Path(env_path))
    return paths


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file; return empty dict if not found or invalid.

    Args:
        path: Path to the TOML file.

    Returns:
        Parsed dict or empty dict if missing/invalid.
    """
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, ValueError):
        return {}


_ENV_OVERRIDES: list[tuple[str, str, bool]] = [
    ("VOX_HOTKEY", "hotkey", True),
    ("VOX_MODEL_SIZE", "model_size", True),
    ("VOX_COMPUTE_TYPE", "compute_type", True),
    ("VOX_COMPUTE_DEVICE", "compute_device", True),
    ("VOX_INJECTION_MODE", "injection_mode", True),
]


def _apply_device_id_env(raw: dict[str, Any]) -> None:
    """Set raw['device_id'] from VOX_DEVICE_ID if set.

    Args:
        raw: Config dict to update in place.
    """
    if "VOX_DEVICE_ID" not in os.environ:
        return
    try:
        raw["device_id"] = int(os.environ["VOX_DEVICE_ID"])
    except ValueError:
        raw["device_id"] = os.environ["VOX_DEVICE_ID"]


def _apply_use_tray_env(raw: dict[str, Any]) -> None:
    """Set raw['use_tray'] from VOX_TRAY if set (1, true, yes -> True).

    Args:
        raw: Config dict to update in place.
    """
    if "VOX_TRAY" not in os.environ:
        return
    v = os.environ["VOX_TRAY"].strip().lower()
    raw["use_tray"] = v in ("1", "true", "yes")


def _apply_env_overrides(raw: dict[str, Any]) -> None:
    """Mutate raw with env overrides (VOX_*).

    Args:
        raw: Config dict to update in place.
    """
    for env_key, key, strip in _ENV_OVERRIDES:
        if env_key in os.environ:
            raw[key] = os.environ[env_key].strip() if strip else os.environ[env_key]
    _apply_device_id_env(raw)
    _apply_use_tray_env(raw)


_CONFIG_KEYS = (
    "hotkey",
    "device_id",
    "model_size",
    "compute_type",
    "compute_device",
    "injection_mode",
    "use_tray",
)


def _merge_toml_into(data: dict[str, Any], raw: dict[str, Any]) -> None:
    """Copy known config keys from data into raw if present and not None.

    Args:
        data: Source dict (e.g. from TOML).
        raw: Target dict to update in place.
    """
    for key in _CONFIG_KEYS:
        if key in data and data[key] is not None:
            raw[key] = data[key]


def load_config() -> dict[str, Any]:
    """Load config from first found vox.toml then apply env overrides.

    Search order: VOX_CONFIG path (if set), ~/.vox/vox.toml.
    Env overrides: VOX_HOTKEY, VOX_DEVICE_ID, VOX_MODEL_SIZE, VOX_COMPUTE_TYPE,
    VOX_COMPUTE_DEVICE, VOX_INJECTION_MODE.

    Returns:
        Flat dict of config keys; no defaults for required fields.
    """
    raw: dict[str, Any] = {}
    for p in _get_config_paths():
        data = _load_toml(p)
        if data:
            _merge_toml_into(data, raw)
            break
    _apply_env_overrides(raw)
    return raw


def _validate_optional_str(raw: dict[str, Any], key: str) -> None:
    """Raise if key is present and not a non-empty string.

    Args:
        raw: Config dict to validate.
        key: Key to check.

    Raises:
        ValueError: If key is present and value is not a non-empty string.
    """
    if (
        key in raw
        and raw[key] is not None
        and (not isinstance(raw[key], str) or not raw[key].strip())
    ):
        raise ValueError(f"{key}: must be a non-empty string")


def _validate_injection_mode(raw: dict[str, Any]) -> None:
    """Raise if injection_mode is present and not one of the allowed values.

    Args:
        raw: Config dict to validate.

    Raises:
        ValueError: If injection_mode is present and invalid.
    """
    if "injection_mode" not in raw or raw["injection_mode"] is None:
        return
    value = raw["injection_mode"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("injection_mode: must be a non-empty string")
    normalized = value.strip()
    if normalized not in ALLOWED_INJECTION_MODES:
        raise ValueError(
            "injection_mode: must be one of "
            f"{sorted(ALLOWED_INJECTION_MODES)}; got {normalized!r}"
        )


def _validate_hotkey(raw: dict[str, Any]) -> None:
    """Raise if hotkey is missing or not a non-empty string.

    Args:
        raw: Config dict to validate.

    Raises:
        ValueError: If hotkey is missing or not a non-empty string.
    """
    if "hotkey" not in raw or raw["hotkey"] is None:
        raise ValueError(
            "hotkey: required field missing; set in config file or VOX_HOTKEY"
        )
    if not isinstance(raw["hotkey"], str) or not raw["hotkey"].strip():
        raise ValueError("hotkey: must be a non-empty string")


def _validate_device_id(raw: dict[str, Any]) -> None:
    """Raise if device_id is present and not an int.

    Args:
        raw: Config dict to validate.

    Raises:
        ValueError: If device_id is present and not an integer.
    """
    if (
        "device_id" in raw
        and raw["device_id"] is not None
        and not isinstance(raw["device_id"], int)
    ):
        raise ValueError("device_id: must be an integer (e.g. from `vox devices`)")


def _validate_use_tray(raw: dict[str, Any]) -> None:
    """Raise if use_tray is present and not a bool or bool-like string.

    Args:
        raw: Config dict to validate.

    Raises:
        ValueError: If use_tray is present and not bool or "true"/"false"/"1"/"0".
    """
    if "use_tray" not in raw or raw["use_tray"] is None:
        return
    v = raw["use_tray"]
    if isinstance(v, bool):
        return
    if isinstance(v, str) and v.strip().lower() in (
        "true",
        "false",
        "1",
        "0",
        "yes",
        "no",
    ):
        return
    raise ValueError("use_tray: must be true or false")


def validate_config(raw: dict[str, Any]) -> None:
    """Validate required and optional fields; raise ValueError with field name.

    Required: hotkey (non-empty string).
    Optional: device_id (int or None), use_tray (bool), model_size, compute_type,
    compute_device, injection_mode.
    No silent fallbacks for required fields.

    Args:
        raw: Config dict to validate.

    Raises:
        ConfigError: With field name for any validation failure.
    """
    try:
        _validate_hotkey(raw)
        _validate_device_id(raw)
        _validate_use_tray(raw)
        _validate_optional_str(raw, "model_size")
        _validate_optional_str(raw, "compute_type")
        _validate_optional_str(raw, "compute_device")
        _validate_injection_mode(raw)
    except ValueError as e:
        raise ConfigError(str(e)) from e


def _raw_transcription_options(raw: dict[str, Any]) -> dict[str, str]:
    """Extract transcription keys from raw config with defaults.

    Args:
        raw: Config dict from load_config().

    Returns:
        Dict with model_size, compute_type, compute_device (stripped, defaulted).
    """
    return {
        "model_size": _str_default(raw, "model_size", "base"),
        "compute_type": _str_default(raw, "compute_type", "float32"),
        "compute_device": _str_default(raw, "compute_device", "cpu").lower(),
    }


def get_transcription_options() -> TranscriptionOptions:
    """Return model_size, compute_type, compute_device with defaults.

    Loads from config file/env but does not require hotkey. Use when only
    transcription settings are needed (e.g. test-mic). Validates with Pydantic.

    Returns:
        TranscriptionOptions with model_size, compute_type, compute_device.

    Raises:
        ConfigError: If any value fails validation.
    """
    raw = load_config()
    d = _raw_transcription_options(raw)
    try:
        return TranscriptionOptions(
            model_size=d["model_size"],
            compute_type=cast(
                Literal["float32", "float16", "int8", "int8_float16"],
                d["compute_type"],
            ),
            compute_device=cast(Literal["cpu", "cuda"], d["compute_device"]),
        )
    except ValidationError as e:
        raise ConfigError(str(e)) from e


def _bool_default(raw: dict[str, Any], key: str, default: bool) -> bool:
    """Get key from raw as bool or return default.

    Args:
        raw: Config dict.
        key: Key to look up.
        default: Value if key missing or None.

    Returns:
        Boolean value; accepts bool or string "true"/"1"/"yes" (case-insensitive).
    """
    v = raw.get(key)
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return default


def _str_default(raw: dict[str, Any], key: str, default: str) -> str:
    """Get key from raw or return default; strip if string.

    Args:
        raw: Config dict.
        key: Key to look up.
        default: Value if key missing or None.

    Returns:
        Stripped string value or default.
    """
    v = raw.get(key)
    if v is None:
        return default
    return (v or default).strip() if isinstance(v, str) else default


def get_config() -> dict[str, Any]:
    """Load and validate config; return validated dict with required fields set.

    Returns:
        Dict with hotkey, device_id, model_size, compute_type, compute_device,
        injection_mode.

    Raises:
        ConfigError: When a required field is missing or invalid.
    """
    raw = load_config()
    try:
        validate_config(raw)
    except ConfigError:
        raise
    out: dict[str, Any] = {
        "hotkey": (raw["hotkey"] or "").strip(),
        "device_id": raw.get("device_id"),
        "model_size": _str_default(raw, "model_size", "base"),
        "compute_type": _str_default(raw, "compute_type", "float32"),
        "compute_device": _str_default(raw, "compute_device", "cpu"),
        "injection_mode": _str_default(raw, "injection_mode", "clipboard"),
        "use_tray": _bool_default(raw, "use_tray", False),
    }
    return out
