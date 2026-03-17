"""Audio stream: list devices, record, and play back using sounddevice."""

from __future__ import annotations

import threading

import numpy as np

# sounddevice has no py.typed/stubs; ignore for type-checking only (plan Phase 1).
import sounddevice as sd  # type: ignore[import-untyped]


def list_devices() -> list[tuple[int, str, str]]:
    """List available audio input devices as (device_id, name, host_api).

    Returns only devices with max_input_channels > 0. On Windows the same
    physical device often appears multiple times (one per host API: MME,
    DirectSound, WASAPI); the host_api field disambiguates.

    Returns:
        List of (device_id, name, host_api) for each input device.

    Raises:
        RuntimeError: If no audio devices are available.
    """
    result: list[tuple[int, str, str]] = []
    try:
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                name = dev.get("name", "Unknown")
                hostapi_idx = dev.get("hostapi", 0)
                hostapi_info = sd.query_hostapis(hostapi_idx)
                hostapi_name = hostapi_info.get("name", "?")
                result.append((i, str(name), str(hostapi_name)))
    except sd.PortAudioError as e:
        raise RuntimeError(
            "No audio devices available; check microphone access and permissions."
        ) from e
    return result


def record_seconds(
    seconds: float,
    device_id: int | None = None,
    sample_rate: int = 16000,
    channels: int = 1,
) -> np.ndarray:
    """Record audio for the given duration; return float32 mono array.

    Args:
        seconds: Duration in seconds.
        device_id: Sounddevice device index; None for default input.
        sample_rate: Sample rate in Hz (16 kHz for faster-whisper).
        channels: Number of channels (1 = mono).

    Returns:
        numpy array (frames, channels) float32 in [-1, 1].
    """
    frames = int(seconds * sample_rate)
    rec: np.ndarray = np.asarray(
        sd.rec(
            frames=frames,
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            device=device_id,
        )
    )
    sd.wait()
    return rec


def play_back(samples: np.ndarray, sample_rate: int = 16000) -> None:
    """Play back an audio array (float32 mono) to the default output device.

    Args:
        samples: Audio data (frames,) or (frames, channels) float32 in [-1, 1].
        sample_rate: Sample rate in Hz.
    """
    if samples.ndim == 1:
        samples = samples[:, np.newaxis]
    sd.play(samples, samplerate=sample_rate)
    sd.wait()


def record_until_stop(
    stop_event: threading.Event,
    device_id: int | None = None,
    sample_rate: int = 16000,
    channels: int = 1,
) -> np.ndarray:
    """Record audio until stop_event is set; return float32 mono array.

    Used for push-to-talk: start recording, later set the event to stop and get
    the buffer. Call from a dedicated thread; the event is set from another
    thread (e.g. hotkey release).

    Args:
        stop_event: When set, recording stops and the function returns.
        device_id: Sounddevice device index; None for default input.
        sample_rate: Sample rate in Hz (16 kHz for faster-whisper).
        channels: Number of channels (1 = mono).

    Returns:
        numpy array (frames, channels) float32 in [-1, 1]; empty if no frames.
    """
    blocks: list[np.ndarray] = []

    def callback(
        indata: np.ndarray,
        _frames: int,
        _time: object,
        _status: object,
    ) -> None:
        """Append incoming audio block to list.

        Args:
            indata: Chunk of audio from the stream.
        """
        blocks.append(indata.copy())

    stream = sd.InputStream(
        device=device_id,
        channels=channels,
        samplerate=sample_rate,
        dtype="float32",
        callback=callback,
    )
    stream.start()
    try:
        stop_event.wait()
    finally:
        stream.stop()
        stream.close()
    if not blocks:
        return np.array([], dtype=np.float32).reshape(0, channels)
    return np.concatenate(blocks, axis=0)
