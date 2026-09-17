"""Unit tests for ContinuousSession junk guard (#36)."""

from __future__ import annotations

import threading
from collections.abc import Callable

import numpy as np
import pytest

from tests.unit.continuous_session_fakes import (
    PAUSE_FRAMES,
    PREROLL_FRAMES,
    ScriptedVad,
    silence_frame,
    tone_frame,
    wait_until,
)
from vox.continuous.session import ContinuousSession

# 0.3 s speech = 4800 samples → 9 frames under, 10 frames over
_SPEECH_FRAMES_UNDER = 9  # 4608 / 16000 = 0.288 s
_SPEECH_FRAMES_OVER = 10  # 5120 / 16000 = 0.320 s


def _make_session(
    *,
    probs: list[float],
    deliverer: Callable[[str], None],
    transcriber: Callable[[np.ndarray], str] | None = None,
    status: Callable[[str], None] | None = None,
) -> ContinuousSession:
    """Build a session with scripted VAD and optional status notifier."""

    def stream_starter(
        _on_frame: Callable[[np.ndarray], None],
        stop_event: threading.Event,
    ) -> None:
        stop_event.wait(timeout=5.0)

    return ContinuousSession(
        stream_starter=stream_starter,
        speech_detector_factory=lambda: ScriptedVad(probs),
        transcriber=transcriber or (lambda _a: "hello"),
        deliverer=deliverer,
        play_start=lambda: None,
        play_end=lambda: None,
        status=status,
    )


def _feed_speech_then_pause(session: ContinuousSession, speech_frames: int) -> None:
    """Feed preroll silence, speech frames, then a full Pause of silence."""
    for _ in range(PREROLL_FRAMES):
        session.ingest_frame(silence_frame())
    for _ in range(speech_frames):
        session.ingest_frame(tone_frame())
    for _ in range(PAUSE_FRAMES + 2):
        session.ingest_frame(silence_frame())


@pytest.mark.unit
class TestContinuousSessionShortSpeechDiscard:
    """Utterances under 0.3 s of detected speech are discarded."""

    def test_just_under_0_3s_speech_discards_without_transcription(self) -> None:
        """Nine speech frames (< 0.3 s) skip the transcriber and announce duration."""
        # Arrange - short speech island and spies
        delivered: list[str] = []
        status: list[str] = []
        transcribed: list[np.ndarray] = []
        speech = [0.9] * _SPEECH_FRAMES_UNDER
        silence = [0.1] * (PAUSE_FRAMES + 2)
        probs = [0.1] * PREROLL_FRAMES + speech + silence
        session = _make_session(
            probs=probs,
            deliverer=delivered.append,
            transcriber=lambda a: transcribed.append(a) or "nope",
            status=status.append,
        )
        session.start()
        session.request_toggle()
        assert wait_until(session.is_active)

        # Act - feed just under 0.3 s of detected speech then Pause
        _feed_speech_then_pause(session, _SPEECH_FRAMES_UNDER)
        assert wait_until(lambda: bool(status))

        # Assert - dim duration message; no transcription or Injection
        assert transcribed == []
        assert delivered == []
        assert status == ["Discarded short sound (0.288 s of speech)."]
        session.shutdown()

    def test_just_over_0_3s_speech_commits_normally(self) -> None:
        """Ten speech frames (>= 0.3 s) still Commit through the deliverer."""
        # Arrange - speech just over the discard boundary
        delivered: list[str] = []
        status: list[str] = []
        speech = [0.9] * _SPEECH_FRAMES_OVER
        silence = [0.1] * (PAUSE_FRAMES + 2)
        probs = [0.1] * PREROLL_FRAMES + speech + silence
        session = _make_session(
            probs=probs,
            deliverer=delivered.append,
            status=status.append,
        )
        session.start()
        session.request_toggle()
        assert wait_until(session.is_active)

        # Act - feed just over 0.3 s of detected speech then Pause
        _feed_speech_then_pause(session, _SPEECH_FRAMES_OVER)
        assert wait_until(lambda: bool(delivered))

        # Assert - Commit landed; no short-sound discard message
        assert delivered == ["hello "]
        assert status == []
        session.shutdown()


@pytest.mark.unit
class TestContinuousSessionEmptyTranscription:
    """Empty filtered transcription announces and does not Inject."""

    def test_empty_transcription_announces_no_speech_and_skips_injection(self) -> None:
        """Empty transcriber result → dim 'No speech detected.'; nothing Injected."""
        # Arrange - enough speech to pass the short-sound guard; empty text
        delivered: list[str] = []
        status: list[str] = []
        speech = [0.9] * _SPEECH_FRAMES_OVER
        silence = [0.1] * (PAUSE_FRAMES + 2)
        probs = [0.1] * PREROLL_FRAMES + speech + silence
        session = _make_session(
            probs=probs,
            deliverer=delivered.append,
            transcriber=lambda _a: "",
            status=status.append,
        )
        session.start()
        session.request_toggle()
        assert wait_until(session.is_active)

        # Act - Commit an Utterance that transcribes to empty
        _feed_speech_then_pause(session, _SPEECH_FRAMES_OVER)
        assert wait_until(lambda: "No speech detected." in status)

        # Assert - dim empty message; no Injection
        assert delivered == []
        assert status == ["No speech detected."]
        session.shutdown()
