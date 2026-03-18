"""Audio capture: device enumeration and recording.

This module intentionally lazy-loads `sounddevice` so that running commands like
`vox --help` (or importing `vox`) doesn't require PortAudio to be present.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import numpy as np
    import threading


def list_devices() -> list[tuple[int, str, str]]:
    from vox.capture.stream import list_devices as _list_devices

    return _list_devices()


def record_seconds(
    seconds: float,
    device_id: int | None = None,
    sample_rate: int = 16000,
    channels: int = 1,
):  # -> np.ndarray
    from vox.capture.stream import record_seconds as _record_seconds

    return _record_seconds(
        seconds, device_id=device_id, sample_rate=sample_rate, channels=channels
    )


def record_until_stop(
    stop_event,  # threading.Event
    device_id: int | None = None,
    sample_rate: int = 16000,
    channels: int = 1,
):  # -> np.ndarray
    from vox.capture.stream import record_until_stop as _record_until_stop

    return _record_until_stop(
        stop_event, device_id=device_id, sample_rate=sample_rate, channels=channels
    )


def play_back(samples, sample_rate: int = 16000) -> None:  # samples: np.ndarray
    from vox.capture.stream import play_back as _play_back

    _play_back(samples, sample_rate=sample_rate)


__all__ = ["list_devices", "play_back", "record_seconds", "record_until_stop"]
