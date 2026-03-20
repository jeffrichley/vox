"""Preloaded recording cues for the push-to-talk runtime.

This module uses a small service class plus a module-level singleton cache.
Startup calls :func:`preload_default_cues` once, then runtime code reuses the
returned service for non-blocking start/end cue playback.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from importlib import import_module
from importlib.resources import as_file, files
from pathlib import Path
from typing import Protocol, cast

import numpy as np


class AudioCueError(RuntimeError):
    """Base class for cue preload/playback failures."""


class CuePreloadError(AudioCueError):
    """Raised when packaged cue assets cannot be loaded during startup."""


class CuePlaybackError(AudioCueError):
    """Raised when a decoded cue cannot be played on the output device."""


@dataclass(frozen=True)
class CueSound:
    """Decoded cue samples and playback metadata."""

    samples: np.ndarray
    sample_rate: int


class SoundDeviceProtocol(Protocol):
    """Minimal sounddevice playback protocol used by this module."""

    def play(self, *_args: object, **_kwargs: object) -> None:
        """Play audio through the default output device.

        Args:
            *_args: Positional playback arguments forwarded to sounddevice.
            **_kwargs: Keyword playback arguments forwarded to sounddevice.
        """


class AudioFrameProtocol(Protocol):
    """Minimal decoded audio frame protocol used in tests and runtime."""

    def to_ndarray(self) -> np.ndarray:
        """Return frame samples as a NumPy array."""


class AudioResamplerProtocol(Protocol):
    """Minimal PyAV resampler protocol used by the cue decoder."""

    def resample(
        self,
        frame: object | None,
    ) -> AudioFrameProtocol | list[AudioFrameProtocol] | None:
        """Resample a decoded frame and return zero or more output frames.

        Args:
            frame: Decoded source frame or ``None`` during resampler flush.
        """


class AudioResamplerFactoryProtocol(Protocol):
    """Protocol for ``av.audio.resampler.AudioResampler`` construction."""

    def __call__(self, *_args: object, **_kwargs: object) -> AudioResamplerProtocol:
        """Construct an audio resampler.

        Args:
            *_args: Positional factory arguments.
            **_kwargs: Keyword factory arguments such as format/layout/rate.
        """


class AudioResamplerNamespaceProtocol(Protocol):
    """Protocol for the PyAV resampler namespace."""

    AudioResampler: AudioResamplerFactoryProtocol


class AudioNamespaceProtocol(Protocol):
    """Protocol for the PyAV audio namespace."""

    resampler: AudioResamplerNamespaceProtocol


class AudioStreamProtocol(Protocol):
    """Protocol for the decoded audio stream metadata."""

    rate: int


class ContainerStreamsProtocol(Protocol):
    """Protocol for the container stream collection."""

    audio: list[AudioStreamProtocol]


class AvContainerProtocol(Protocol):
    """Protocol for the opened PyAV container."""

    streams: ContainerStreamsProtocol

    def __enter__(self) -> AvContainerProtocol:
        """Enter the container context."""

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: object | None,
    ) -> bool | None:
        """Exit the container context."""

    def decode(self, audio_stream: object) -> list[object]:
        """Decode audio frames from the selected stream.

        Args:
            audio_stream: Selected audio stream descriptor.
        """


class AvModuleProtocol(Protocol):
    """Minimal PyAV module protocol used by the cue decoder."""

    audio: AudioNamespaceProtocol

    def open(self, path: str) -> AvContainerProtocol:
        """Open an audio container.

        Args:
            path: Filesystem path to the packaged cue asset.
        """


def _sd() -> SoundDeviceProtocol:
    """Return the lazily imported ``sounddevice`` module.

    Returns:
        Imported sounddevice module cast to the local protocol.
    """
    return cast(SoundDeviceProtocol, import_module("sounddevice"))


def _av() -> AvModuleProtocol:
    """Return the lazily imported ``av`` module.

    Returns:
        Imported PyAV module cast to the local protocol.
    """
    return cast(AvModuleProtocol, import_module("av"))


def _cue_resource_path(cue_name: str) -> Path:
    """Return a filesystem path for a packaged cue asset.

    Args:
        cue_name: Logical cue name, e.g. ``"start"`` or ``"end"``.

    Returns:
        Filesystem path for the packaged MP3 asset.

    Raises:
        CuePreloadError: If the packaged asset is missing.
    """
    resource = files("vox") / "assets" / f"{cue_name}.mp3"
    if not resource.is_file():
        raise CuePreloadError(
            f"Missing packaged cue asset for {cue_name!r}. "
            "Reinstall Vox or verify src/vox/assets contains the cue files."
        )
    with as_file(resource) as path:
        return Path(path)


def _iter_resampled_frames(
    resampler: AudioResamplerProtocol,
    frame: object | None,
) -> list[AudioFrameProtocol]:
    """Normalize PyAV resampler output to a list of frames.

    Args:
        resampler: PyAV audio resampler instance.
        frame: Source frame to resample or ``None`` to flush buffered output.

    Returns:
        Zero or more resampled frames.
    """
    result = resampler.resample(frame)
    if result is None:
        return []
    if isinstance(result, list):
        return result
    return [result]


def _decode_cue(path: Path, cue_name: str) -> CueSound:
    """Decode an MP3 cue into float32 mono PCM samples.

    Args:
        path: Filesystem path to the packaged cue asset.
        cue_name: Logical cue name for error messages.

    Returns:
        Decoded cue samples and sample-rate metadata.

    Raises:
        CuePreloadError: If decode fails or produces no samples.
    """
    av = _av()
    try:
        with av.open(str(path)) as container:
            audio_stream = container.streams.audio[0]
            sample_rate = int(audio_stream.rate)
            resampler = av.audio.resampler.AudioResampler(
                format="flt",
                layout="mono",
                rate=sample_rate,
            )
            blocks: list[np.ndarray] = []
            for frame in container.decode(audio_stream):
                for out_frame in _iter_resampled_frames(resampler, frame):
                    arr = np.asarray(out_frame.to_ndarray(), dtype=np.float32)
                    blocks.append(np.ravel(arr))
            for out_frame in _iter_resampled_frames(resampler, None):
                arr = np.asarray(out_frame.to_ndarray(), dtype=np.float32)
                blocks.append(np.ravel(arr))
    except Exception as e:
        raise CuePreloadError(
            f"Failed to decode packaged {cue_name!r} cue asset at {path}: {e}"
        ) from e
    if not blocks:
        raise CuePreloadError(
            f"Packaged {cue_name!r} cue asset decoded to no audio frames at {path}."
        )
    samples = np.concatenate(blocks).astype(np.float32, copy=False)
    mono_samples = np.clip(samples, -1.0, 1.0)[:, np.newaxis]
    return CueSound(samples=mono_samples, sample_rate=sample_rate)


class CuePlayer:
    """In-memory start/end cue cache with non-blocking playback helpers."""

    def __init__(self, start: CueSound, end: CueSound) -> None:
        """Store the decoded start and end cues for reuse.

        Args:
            start: Preloaded start cue samples and playback metadata.
            end: Preloaded end cue samples and playback metadata.
        """
        self._start = start
        self._end = end

    @classmethod
    def load_default(cls) -> CuePlayer:
        """Load and decode the packaged default start/end cues.

        Returns:
            Cue player with preloaded start and end sounds.
        """
        start_path = _cue_resource_path("start")
        end_path = _cue_resource_path("end")
        return cls(
            start=_decode_cue(start_path, "start"),
            end=_decode_cue(end_path, "end"),
        )

    @property
    def start(self) -> CueSound:
        """Return the preloaded start cue.

        Returns:
            Start cue samples and playback metadata.
        """
        return self._start

    @property
    def end(self) -> CueSound:
        """Return the preloaded end cue.

        Returns:
            End cue samples and playback metadata.
        """
        return self._end

    def play_start(self, volume_scale: float = 1.0) -> None:
        """Play the preloaded start cue without blocking the caller.

        Args:
            volume_scale: Playback volume multiplier between 0.0 and 1.0.
        """
        self._play(self._start, "start", volume_scale)

    def play_end(self, volume_scale: float = 1.0) -> None:
        """Play the preloaded end cue without blocking the caller.

        Args:
            volume_scale: Playback volume multiplier between 0.0 and 1.0.
        """
        self._play(self._end, "end", volume_scale)

    def _play(self, cue: CueSound, cue_name: str, volume_scale: float) -> None:
        """Play one cue using the shared sounddevice NumPy playback surface.

        Args:
            cue: Predecoded cue samples and playback metadata.
            cue_name: User-facing cue label for error reporting.
            volume_scale: Playback volume multiplier between 0.0 and 1.0.

        Raises:
            CuePlaybackError: If output-device playback fails.
        """
        try:
            scaled_samples = np.clip(cue.samples * volume_scale, -1.0, 1.0)
            _sd().play(scaled_samples, samplerate=cue.sample_rate, blocking=False)
        except Exception as e:
            raise CuePlaybackError(
                f"Failed to play the {cue_name!r} recording cue: {e}. "
                "Check output-device availability and audio permissions."
            ) from e


_DEFAULT_CUES_STATE: dict[str, CuePlayer | None] = {"player": None}
_DEFAULT_CUES_LOCK = threading.Lock()


def preload_default_cues(force_reload: bool = False) -> CuePlayer:
    """Load and cache the packaged default cues.

    Args:
        force_reload: Reload cues even if they are already cached.

    Returns:
        Cached cue player.
    """
    with _DEFAULT_CUES_LOCK:
        player = _DEFAULT_CUES_STATE["player"]
        if force_reload or player is None:
            player = CuePlayer.load_default()
            _DEFAULT_CUES_STATE["player"] = player
        return player
