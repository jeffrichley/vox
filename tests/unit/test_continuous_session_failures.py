"""Unit tests for ContinuousSession start and mic failures (#38)."""

from __future__ import annotations

import threading
from collections.abc import Callable

import pytest

from tests.unit.continuous_session_fakes import (
    PREROLL_FRAMES,
    ScriptedVad,
    silence_frame,
    tone_frame,
    wait_until,
)
from vox.continuous.session import ContinuousSession, ContinuousState


@pytest.mark.unit
class TestContinuousSessionClipboardRefuse:
    """Clipboard-only Injection refuses toggle-on without opening a stream."""

    def test_clipboard_refuse_publishes_error_plays_end_cue_no_stream(self) -> None:
        """Toggle-on in clipboard mode stays off with error state and end cue."""
        # Arrange - refusal gate and spies for stream, cues, reports, state
        reported: list[str] = []
        states: list[ContinuousState] = []
        cues: list[str] = []
        starter = threading.Event()
        stream_calls = 0

        def stream_starter(
            _on_frame: Callable[[object], None],
            stop_event: threading.Event,
        ) -> None:
            nonlocal stream_calls
            stream_calls += 1
            starter.set()
            stop_event.wait(timeout=5.0)

        session = ContinuousSession(
            stream_starter=stream_starter,
            speech_detector_factory=lambda: ScriptedVad([0.1]),
            transcriber=lambda _a: "x",
            deliverer=lambda _t: None,
            play_start=lambda: cues.append("start"),
            play_end=lambda: cues.append("end"),
            reporter=reported.append,
            state_publisher=states.append,
            start_refusal=lambda: (
                "Continuous dictation cannot run in clipboard-only mode."
            ),
        )
        session.start()

        # Act - toggle on while clipboard-only refusal is active
        session.request_toggle()
        wait_until(lambda: "end" in cues or bool(reported))

        # Assert - no stream, end cue, error published, still off
        assert stream_calls == 0
        assert starter.is_set() is False
        assert "start" not in cues
        assert "end" in cues
        assert reported == ["Continuous dictation cannot run in clipboard-only mode."]
        assert states[-1] == ContinuousState(
            active=False,
            error="Continuous dictation cannot run in clipboard-only mode.",
        )
        assert session.is_active() is False
        session.shutdown()


@pytest.mark.unit
class TestContinuousSessionStartFailures:
    """Speech detection and stream start failures stay off with error state."""

    def test_detector_load_failure_publishes_error_and_end_cue(self) -> None:
        """Factory raise → red report, end cue, error state, stays off."""
        # Arrange - detector factory that fails before any stream opens
        reported: list[str] = []
        states: list[ContinuousState] = []
        cues: list[str] = []
        stream_calls = 0

        def stream_starter(
            _on_frame: Callable[[object], None],
            stop_event: threading.Event,
        ) -> None:
            nonlocal stream_calls
            stream_calls += 1
            stop_event.wait(timeout=5.0)

        session = ContinuousSession(
            stream_starter=stream_starter,
            speech_detector_factory=lambda: (_ for _ in ()).throw(
                RuntimeError("vad unavailable")
            ),
            transcriber=lambda _a: "x",
            deliverer=lambda _t: None,
            play_start=lambda: cues.append("start"),
            play_end=lambda: cues.append("end"),
            reporter=reported.append,
            state_publisher=states.append,
        )
        session.start()

        # Act - toggle on with a broken speech-detector factory
        session.request_toggle()
        assert wait_until(lambda: not session.is_active() and "end" in cues)

        # Assert - no stream, end cue, error published, inactive
        assert stream_calls == 0
        assert "start" not in cues
        assert "end" in cues
        assert "vad unavailable" in reported
        assert states[-1] == ContinuousState(active=False, error="vad unavailable")
        assert session.is_active() is False
        session.shutdown()

    def test_stream_start_failure_publishes_error_and_end_cue(self) -> None:
        """Stream starter raise → red report, end cue, error state, stays off."""
        # Arrange - stream that fails immediately after detector loads
        reported: list[str] = []
        states: list[ContinuousState] = []
        cues: list[str] = []

        def stream_starter(
            _on_frame: Callable[[object], None],
            _stop_event: threading.Event,
        ) -> None:
            raise RuntimeError("mic open failed")

        session = ContinuousSession(
            stream_starter=stream_starter,
            speech_detector_factory=lambda: ScriptedVad([0.1]),
            transcriber=lambda _a: "x",
            deliverer=lambda _t: None,
            play_start=lambda: cues.append("start"),
            play_end=lambda: cues.append("end"),
            reporter=reported.append,
            state_publisher=states.append,
        )
        session.start()

        # Act - toggle on with a stream starter that raises
        session.request_toggle()
        assert wait_until(lambda: not session.is_active() and "end" in cues)

        # Assert - start then end cue, error published, inactive
        assert cues[0] == "start"
        assert "end" in cues
        assert "mic open failed" in reported
        assert states[-1] == ContinuousState(active=False, error="mic open failed")
        assert session.is_active() is False
        session.shutdown()


@pytest.mark.unit
class TestContinuousSessionMicStall:
    """No audio for the stall window turns Continuous off with mic failure."""

    def test_stalled_stream_turns_off_with_error_and_pending_commit(self) -> None:
        """Fake clock past 2 s with no frames → mic error; pending Commit lands."""
        # Arrange - controllable clock; mid-Utterance then stall (no more frames)
        reported: list[str] = []
        states: list[ContinuousState] = []
        cues: list[str] = []
        delivered: list[str] = []
        fake_now = 100.0

        def clock() -> float:
            return fake_now

        probs = [0.1] * PREROLL_FRAMES + [0.9] * 20
        session = ContinuousSession(
            stream_starter=lambda _on_frame, stop_event: stop_event.wait(timeout=5.0),
            speech_detector_factory=lambda: ScriptedVad(probs),
            transcriber=lambda _a: "pending",
            deliverer=delivered.append,
            play_start=lambda: cues.append("start"),
            play_end=lambda: cues.append("end"),
            reporter=reported.append,
            state_publisher=states.append,
            clock=clock,
            mic_stall_seconds=2.0,
        )
        session.start()
        session.request_toggle()
        assert wait_until(lambda: "start" in cues)
        for _ in range(PREROLL_FRAMES):
            session.ingest_frame(silence_frame())
        for _ in range(5):
            session.ingest_frame(tone_frame())

        # Act - advance fake clock past stall without delivering more frames
        fake_now += 2.1
        assert wait_until(
            lambda: not session.is_active() and "end" in cues and bool(delivered)
        )

        # Assert - mic failure message, error state, pending Commit landed
        assert "Microphone stopped delivering audio." in reported
        assert states[-1] == ContinuousState(
            active=False,
            error="Microphone stopped delivering audio.",
        )
        assert delivered == ["pending "]
        assert session.is_active() is False
        session.shutdown()
