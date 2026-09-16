"""Streaming Silero speech-probability adapter for Continuous dictation."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import Protocol, cast

import numpy as np

FRAME_SAMPLES = 512
_CONTEXT_SAMPLES = 64
_STATE_SHAPE = (1, 1, 128)
_REQUIRED_INPUTS = frozenset({"input", "h", "c"})
_REQUIRED_FASTER_WHISPER = "faster-whisper>=1.2.1"


class VadUnavailableError(RuntimeError):
    """Raised when the bundled Silero speech-detection model cannot be used."""


class _OnnxInputProtocol(Protocol):
    """Minimal ONNX input metadata used for the input-name contract check."""

    name: str


class OnnxSessionProtocol(Protocol):
    """Minimal ONNX InferenceSession surface used by StreamingSileroVad."""

    def get_inputs(self) -> list[_OnnxInputProtocol]:
        """Return session input metadata."""

    def run(
        self,
        output_names: None,
        input_feed: dict[str, np.ndarray],
    ) -> list[np.ndarray]:
        """Run inference and return ``[speech_probs, hn, cn]``.

        Args:
            output_names: Unused; pass ``None`` to fetch all outputs.
            input_feed: Mapping of ``input`` / ``h`` / ``c`` arrays.
        """


class _VadModelProtocol(Protocol):
    """Minimal Silero VAD model surface exposing the ONNX session."""

    session: OnnxSessionProtocol


class _VadModuleProtocol(Protocol):
    """Minimal faster_whisper.vad module surface."""

    get_vad_model: Callable[[], _VadModelProtocol]


class SpeechProbabilityModel(Protocol):
    """Per-frame speech probability model used by Continuous dictation."""

    def probability(self, frame: np.ndarray) -> float:
        """Return speech probability for one 512-sample float32 frame.

        Args:
            frame: Mono float32 audio of length ``FRAME_SAMPLES``.
        """


def _unavailable_message(reason: str) -> str:
    """Build actionable speech-detection failure text.

    Args:
        reason: Specific failure detail.

    Returns:
        Message naming the required faster-whisper version.
    """
    return (
        f"Speech detection unavailable: {reason}. Require {_REQUIRED_FASTER_WHISPER}."
    )


class StreamingSileroVad:
    """Drive Silero one 512-sample frame at a time, carrying LSTM state and context."""

    def __init__(self, session: OnnxSessionProtocol) -> None:
        """Validate ONNX inputs and initialize zero state/context.

        Args:
            session: ONNX session with inputs ``input``, ``h``, and ``c``.

        Raises:
            VadUnavailableError: If session inputs are not exactly the required set.
        """
        names = {item.name for item in session.get_inputs()}
        if names != _REQUIRED_INPUTS:
            detail = (
                f"Silero ONNX inputs must be exactly {_REQUIRED_INPUTS}, got {names}"
            )
            raise VadUnavailableError(_unavailable_message(detail))
        self._session = session
        self._h = np.zeros(_STATE_SHAPE, dtype=np.float32)
        self._c = np.zeros(_STATE_SHAPE, dtype=np.float32)
        self._context = np.zeros((1, _CONTEXT_SAMPLES), dtype=np.float32)

    def probability(self, frame: np.ndarray) -> float:
        """Return speech probability for one frame, updating carried state.

        Args:
            frame: 1-D float32 array of exactly ``FRAME_SAMPLES`` samples.

        Returns:
            Speech probability as a Python float.

        Raises:
            ValueError: If ``frame`` is not 1-D float32 of length ``FRAME_SAMPLES``.
        """
        if frame.ndim != 1:
            raise ValueError("Speech detection frame must be a 1-D array")
        if frame.dtype != np.float32:
            raise ValueError("Speech detection frame must be float32")
        if frame.shape[0] != FRAME_SAMPLES:
            raise ValueError(
                f"Speech detection frame must have exactly {FRAME_SAMPLES} samples"
            )

        window = np.concatenate([self._context, frame[None, :]], axis=1)
        out, self._h, self._c = self._session.run(
            None,
            {"input": window, "h": self._h, "c": self._c},
        )
        self._context = frame[None, -_CONTEXT_SAMPLES:].copy()
        return float(np.asarray(out).reshape(-1)[0])


def load_streaming_vad() -> StreamingSileroVad:
    """Load a streaming adapter around faster-whisper's bundled Silero session.

    Returns:
        Fresh StreamingSileroVad with zeroed state (safe to build per toggle-on).

    Raises:
        VadUnavailableError: If the model cannot be loaded or fails the input contract.
    """
    try:
        vad_module = cast(_VadModuleProtocol, import_module("faster_whisper.vad"))
        session = vad_module.get_vad_model().session
        return StreamingSileroVad(session)
    except VadUnavailableError:
        raise
    except Exception as exc:
        raise VadUnavailableError(_unavailable_message(str(exc))) from exc
