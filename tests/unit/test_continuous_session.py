"""Unit tests for ContinuousSession: Pause Commit, FIFO, toggle-off, drain."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from unittest import mock

import numpy as np
import pytest

from vox.continuous.session import ContinuousSession
from vox.continuous.vad import FRAME_SAMPLES

_SAMPLE_RATE = 16_000
_PAUSE_FRAMES = int(1.0 * _SAMPLE_RATE / FRAME_SAMPLES)  # 31
_PREROLL_FRAMES = int(0.4 * _SAMPLE_RATE / FRAME_SAMPLES)  # 12
_SPEECH_FRAMES = 10  # just over 0.3 s junk-guard minimum


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


def _make_session(
    *,
    probs: list[float],
    deliverer: Callable[[str], None],
    transcriber: Callable[[np.ndarray], str] | None = None,
    play_start: Callable[[], None] | None = None,
    play_end: Callable[[], None] | None = None,
) -> ContinuousSession:
    """Build a session with a no-op stream starter and scripted VAD."""

    def default_transcribe(audio: np.ndarray) -> str:
        del audio
        return "hello"

    def stream_starter(
        _on_frame: Callable[[np.ndarray], None],
        stop_event: threading.Event,
    ) -> None:
        stop_event.wait(timeout=5.0)

    return ContinuousSession(
        stream_starter=stream_starter,
        speech_detector_factory=lambda: ScriptedVad(probs),
        transcriber=transcriber or default_transcribe,
        deliverer=deliverer,
        play_start=play_start or (lambda: None),
        play_end=play_end or (lambda: None),
    )


def _feed_preroll(session: ContinuousSession) -> None:
    """Fill the 0.4 s pre-roll ring with silence frames."""
    for _ in range(_PREROLL_FRAMES):
        session.ingest_frame(_silence_frame())


def _feed_speech_then_pause(
    session: ContinuousSession, speech_frames: int = _SPEECH_FRAMES
) -> None:
    """Feed speech frames then enough silence frames to trigger a Pause Commit."""
    for _ in range(speech_frames):
        session.ingest_frame(_tone_frame())
    # 32 frames * 512 >= 16000 pause samples
    for _ in range(_PAUSE_FRAMES + 2):
        session.ingest_frame(_silence_frame())


@pytest.mark.unit
class TestContinuousSessionPauseCommit:
    """Pause detection Commits an Utterance through the deliverer."""

    def test_pause_commits_transcribed_text_with_trailing_space(self) -> None:
        """Speech then 1 s silence Commits text plus a trailing space."""
        # Arrange - session with scripted speech then silence probabilities
        delivered: list[str] = []
        probs = (
            [0.1] * _PREROLL_FRAMES
            + [0.9] * _SPEECH_FRAMES
            + [0.1] * (_PAUSE_FRAMES + 2)
        )
        session = _make_session(probs=probs, deliverer=delivered.append)
        session.start()
        session.request_toggle()
        time.sleep(0.05)

        # Act - feed preroll, speech, and a full Pause of silence
        _feed_preroll(session)
        _feed_speech_then_pause(session)
        deadline = time.monotonic() + 2.0
        while not delivered and time.monotonic() < deadline:
            time.sleep(0.01)
        session.shutdown()

        # Assert - Commit delivered transcribed text with trailing space
        assert delivered == ["hello "]


@pytest.mark.unit
class TestContinuousSessionFifoOrder:
    """Commit thread preserves spoken order when transcription is slow."""

    def test_two_utterances_delivered_in_order_when_first_transcription_slower(
        self,
    ) -> None:
        """Second Utterance waits behind a slow first transcription."""
        # Arrange - slow first transcription gated behind the second enqueue
        delivered: list[str] = []
        release_first = threading.Event()
        second_queued = threading.Event()
        call_count = 0
        lock = threading.Lock()

        def transcriber(audio: np.ndarray) -> str:
            nonlocal call_count
            del audio
            with lock:
                call_count += 1
                n = call_count
            if n == 1:
                second_queued.wait(timeout=2.0)
                release_first.wait(timeout=2.0)
                return "first"
            second_queued.set()
            return "second"

        island = [0.9] * _SPEECH_FRAMES + [0.1] * (_PAUSE_FRAMES + 2)
        probs = [0.1] * _PREROLL_FRAMES + island + island
        session = _make_session(
            probs=probs,
            deliverer=delivered.append,
            transcriber=transcriber,
        )
        session.start()
        session.request_toggle()
        time.sleep(0.05)

        # Act - enqueue two Pause Commits while the first transcription blocks
        _feed_preroll(session)
        _feed_speech_then_pause(session)
        deadline = time.monotonic() + 2.0
        while call_count < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        _feed_speech_then_pause(session)
        deadline = time.monotonic() + 2.0
        while not second_queued.is_set() and time.monotonic() < deadline:
            time.sleep(0.01)
        release_first.set()
        deadline = time.monotonic() + 2.0
        while len(delivered) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        session.shutdown()

        # Assert - spoken order preserved despite slow first transcription
        assert delivered == ["first ", "second "]


@pytest.mark.unit
class TestContinuousSessionToggleOff:
    """Toggle-off Commits the pending Utterance then plays the end cue."""

    def test_toggle_off_commits_pending_utterance(self) -> None:
        """Mid-speech toggle-off Commits without waiting for a full Pause."""
        # Arrange - active session mid-Utterance before a Pause
        delivered: list[str] = []
        cues: list[str] = []
        probs = [0.1] * _PREROLL_FRAMES + [0.9] * 20
        session = _make_session(
            probs=probs,
            deliverer=delivered.append,
            play_start=lambda: cues.append("start"),
            play_end=lambda: cues.append("end"),
        )
        session.start()
        session.request_toggle()
        time.sleep(0.05)
        _feed_preroll(session)
        for _ in range(_SPEECH_FRAMES):
            session.ingest_frame(_tone_frame())

        # Act - toggle off while speech is still open
        session.request_toggle()
        deadline = time.monotonic() + 2.0
        while (not delivered or "end" not in cues) and time.monotonic() < deadline:
            time.sleep(0.01)
        session.shutdown()

        # Assert - pending Utterance Committed and end cue played
        assert delivered == ["hello "]
        assert cues[0] == "start"
        assert "end" in cues


@pytest.mark.unit
class TestContinuousSessionShutdown:
    """Shutdown is idempotent and drains in-flight Commits."""

    def test_idempotent_shutdown_drains_pending_commits(self) -> None:
        """Shutdown waits for queued Commits; a second call is a no-op."""
        # Arrange - in-flight Commit blocked inside the transcriber
        delivered: list[str] = []
        release = threading.Event()

        def transcriber(audio: np.ndarray) -> str:
            del audio
            release.wait(timeout=2.0)
            return "drained"

        probs = (
            [0.1] * _PREROLL_FRAMES
            + [0.9] * _SPEECH_FRAMES
            + [0.1] * (_PAUSE_FRAMES + 2)
        )
        session = _make_session(
            probs=probs,
            deliverer=delivered.append,
            transcriber=transcriber,
        )
        session.start()
        session.request_toggle()
        time.sleep(0.05)
        _feed_preroll(session)
        _feed_speech_then_pause(session)
        time.sleep(0.05)

        # Act - shutdown while Commit is in flight, then shutdown again
        def do_shutdown() -> None:
            session.shutdown()

        shut_thread = threading.Thread(target=do_shutdown)
        shut_thread.start()
        time.sleep(0.05)
        release.set()
        shut_thread.join(timeout=2.0)
        session.shutdown()

        # Assert - drained text delivered and second shutdown is a no-op
        assert shut_thread.is_alive() is False
        assert delivered == ["drained "]


@pytest.mark.unit
class TestContinuousSessionLazyStart:
    """No stream or VAD until the first toggle-on."""

    def test_no_detector_or_stream_before_first_toggle(self) -> None:
        """Factory and stream starter are unused until request_toggle."""
        # Arrange - session with mocked detector factory and stream starter
        factory = mock.Mock(side_effect=lambda: ScriptedVad([0.1]))
        starter = mock.Mock(
            side_effect=lambda _on_frame, stop_event: stop_event.wait(timeout=5.0)
        )
        session = ContinuousSession(
            stream_starter=starter,
            speech_detector_factory=factory,
            transcriber=lambda _a: "x",
            deliverer=lambda _t: None,
            play_start=lambda: None,
            play_end=lambda: None,
        )

        # Act - start only (no toggle-on)
        session.start()
        time.sleep(0.05)

        # Assert - no detector or stream created before first toggle
        factory.assert_not_called()
        starter.assert_not_called()
        session.shutdown()
