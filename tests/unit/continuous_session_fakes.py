"""Shared fakes and helpers for ContinuousSession unit tests."""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np

from vox.continuous.vad import FRAME_SAMPLES

SAMPLE_RATE = 16_000
PAUSE_FRAMES = int(1.0 * SAMPLE_RATE / FRAME_SAMPLES)  # 31
PREROLL_FRAMES = int(0.4 * SAMPLE_RATE / FRAME_SAMPLES)  # 12


class ScriptedVad:
    """SpeechProbabilityModel that returns scripted probabilities in order."""

    def __init__(self, probs: list[float]) -> None:
        self._probs = list(probs)
        self._index = 0

    def probability(self, frame: np.ndarray) -> float:
        """Return the next scripted probability."""
        del frame
        if self._index >= len(self._probs):
            return self._probs[-1]
        value = self._probs[self._index]
        self._index += 1
        return value


def silence_frame() -> np.ndarray:
    """Return a zeroed 512-sample mono frame."""
    return np.zeros(FRAME_SAMPLES, dtype=np.float32)


def tone_frame(level: float = 0.2) -> np.ndarray:
    """Return a constant-level 512-sample mono frame."""
    return np.full(FRAME_SAMPLES, level, dtype=np.float32)


def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Poll until predicate is true or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()
