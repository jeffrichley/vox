"""Unit tests for ContinuousSession idle auto-off (#37)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import numpy as np
import pytest

from vox.continuous.session import ContinuousSession
from vox.continuous.vad import FRAME_SAMPLES

_SAMPLE_RATE = 16_000
_PREROLL_FRAMES = int(0.4 * _SAMPLE_RATE / FRAME_SAMPLES)  # 12


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


def _silence_frame() -> np.ndarray:
    return np.zeros(FRAME_SAMPLES, dtype=np.float32)


def _tone_frame(level: float = 0.2) -> np.ndarray:
    return np.full(FRAME_SAMPLES, level, dtype=np.float32)


def _make_session(  # noqa: PLR0913 — mirrors ContinuousSession injectables for tests
    *,
    probs: list[float],
    deliverer: Callable[[str], None],
    play_start: Callable[[], None] | None = None,
    play_end: Callable[[], None] | None = None,
    idle_minutes: float,
    on_idle_auto_off: Callable[[float], None] | None = None,
) -> ContinuousSession:
    """Build a session with scripted VAD and a configured idle window."""

    def stream_starter(
        _on_frame: Callable[[np.ndarray], None],
        stop_event: threading.Event,
    ) -> None:
        stop_event.wait(timeout=5.0)

    return ContinuousSession(
        stream_starter=stream_starter,
        speech_detector_factory=lambda: ScriptedVad(probs),
        transcriber=lambda _a: "hello",
        deliverer=deliverer,
        play_start=play_start or (lambda: None),
        play_end=play_end or (lambda: None),
        idle_minutes=idle_minutes,
        on_idle_auto_off=on_idle_auto_off,
    )


@pytest.mark.unit
class TestContinuousSessionIdleAutoOff:
    """Idle sample clock turns Continuous off once; speech resets the count."""

    def test_idle_auto_off_fires_once_with_end_cue(self) -> None:
        """Enough silence samples turn listening off exactly once."""
        # Arrange - tiny idle window (~5 silence frames) and scripted silence
        idle_frames = 5
        idle_minutes = idle_frames * FRAME_SAMPLES / (_SAMPLE_RATE * 60.0)
        idle_events: list[float] = []
        cues: list[str] = []
        probs = [0.1] * (idle_frames + 20)
        session = _make_session(
            probs=probs,
            deliverer=lambda _t: None,
            play_start=lambda: cues.append("start"),
            play_end=lambda: cues.append("end"),
            idle_minutes=idle_minutes,
            on_idle_auto_off=idle_events.append,
        )
        session.start()
        session.request_toggle()
        time.sleep(0.05)

        # Act - feed silence past the idle threshold, then more silence
        for _ in range(idle_frames + 10):
            session.ingest_frame(_silence_frame())
        deadline = time.monotonic() + 2.0
        while (
            session.is_active() or "end" not in cues
        ) and time.monotonic() < deadline:
            time.sleep(0.01)
        session.shutdown()

        # Assert - auto-off once, end cue played, session inactive
        assert idle_events == [idle_minutes]
        assert cues[0] == "start"
        assert cues.count("end") == 1
        assert session.is_active() is False

    def test_speech_resets_idle_count_before_auto_off(self) -> None:
        """A speech frame resets idle samples so auto-off does not fire early."""
        # Arrange - idle needs 8 silence frames; speech interrupts after 4
        idle_frames = 8
        idle_minutes = idle_frames * FRAME_SAMPLES / (_SAMPLE_RATE * 60.0)
        idle_events: list[float] = []
        cues: list[str] = []
        probs = [0.1] * 4 + [0.9] + [0.1] * 4
        session = _make_session(
            probs=probs,
            deliverer=lambda _t: None,
            play_start=lambda: cues.append("start"),
            play_end=lambda: cues.append("end"),
            idle_minutes=idle_minutes,
            on_idle_auto_off=idle_events.append,
        )
        session.start()
        session.request_toggle()
        time.sleep(0.05)

        # Act - silence, speech (reset), silence short of idle
        for _ in range(4):
            session.ingest_frame(_silence_frame())
        session.ingest_frame(_tone_frame())
        for _ in range(4):
            session.ingest_frame(_silence_frame())
        time.sleep(0.05)

        # Assert - still listening; idle callback not fired
        assert session.is_active() is True
        assert idle_events == []
        assert "end" not in cues
        session.shutdown()

    def test_idle_auto_off_commits_pending_utterance(self) -> None:
        """Auto-off drains like toggle-off: pending Utterance still Commits."""
        # Arrange - idle longer than preroll but shorter than Pause after speech
        delivered: list[str] = []
        cues: list[str] = []
        idle_frames = _PREROLL_FRAMES + 5
        idle_minutes = idle_frames * FRAME_SAMPLES / (_SAMPLE_RATE * 60.0)
        probs = [0.1] * _PREROLL_FRAMES + [0.9] * 5 + [0.1] * (idle_frames + 5)
        session = _make_session(
            probs=probs,
            deliverer=delivered.append,
            play_start=lambda: cues.append("start"),
            play_end=lambda: cues.append("end"),
            idle_minutes=idle_minutes,
            on_idle_auto_off=lambda _m: None,
        )
        session.start()
        session.request_toggle()
        time.sleep(0.05)
        for _ in range(_PREROLL_FRAMES):
            session.ingest_frame(_silence_frame())
        for _ in range(5):
            session.ingest_frame(_tone_frame())

        # Act - silence hits idle mid-Utterance before a full Pause
        for _ in range(idle_frames + 2):
            session.ingest_frame(_silence_frame())
        deadline = time.monotonic() + 2.0
        while (not delivered or "end" not in cues) and time.monotonic() < deadline:
            time.sleep(0.01)
        session.shutdown()

        # Assert - pending Commit landed and end cue played
        assert delivered == ["hello "]
        assert "end" in cues
