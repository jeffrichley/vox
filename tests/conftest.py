"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import numpy as np
import pytest
import sounddevice as sd

from vox.capture import list_devices


def _has_working_audio() -> bool:
    """Return True if we can open minimal input and output streams (CI may have neither)."""
    try:
        devs = list_devices()
        if not devs:
            return False
        # Open a 1-frame input stream; list_devices can pass but rec() can fail (e.g. 0 channels).
        sd.rec(frames=1, samplerate=16000, channels=1, dtype="float32")
        sd.wait()
        sd.play(np.zeros(1, dtype="float32"), samplerate=16000)
        sd.wait()
        return True
    except (sd.PortAudioError, OSError, RuntimeError):
        return False
    finally:
        sd.stop()


@pytest.fixture(scope="session")
def requires_audio() -> None:
    """Skip the test when no working audio input/output is available (e.g. headless CI)."""
    if not _has_working_audio():
        pytest.skip("No working audio device (e.g. headless CI)")
