"""Unit tests for ContinuousSession exception resilience (#38)."""

from __future__ import annotations

import pytest

from tests.unit.continuous_session_fakes import (
    PAUSE_FRAMES,
    PREROLL_FRAMES,
    ScriptedVad,
    silence_frame,
    tone_frame,
    wait_until,
)
from vox.continuous.session import ContinuousSession, ContinuousState


@pytest.mark.unit
class TestContinuousSessionRobustness:
    """Cue / publish / deliver exceptions and transcription errors stay alive."""

    def test_transcription_error_reports_and_keeps_session_running(self) -> None:
        """A raising transcriber prints red and leaves Continuous active."""
        # Arrange - first Commit fails transcription; session stays on
        reported: list[str] = []
        delivered: list[str] = []
        call_count = 0

        def transcriber(audio: object) -> str:
            nonlocal call_count
            del audio
            call_count += 1
            if call_count == 1:
                raise RuntimeError("whisper blew up")
            return "recovered"

        island = [0.9] * 10 + [0.1] * (PAUSE_FRAMES + 2)
        probs = [0.1] * PREROLL_FRAMES + island + island
        session = ContinuousSession(
            stream_starter=lambda _on_frame, stop_event: stop_event.wait(timeout=5.0),
            speech_detector_factory=lambda: ScriptedVad(probs),
            transcriber=transcriber,
            deliverer=delivered.append,
            play_start=lambda: None,
            play_end=lambda: None,
            reporter=reported.append,
        )
        session.start()
        session.request_toggle()
        assert wait_until(session.is_active)

        # Act - two Pause Commits; first transcription fails
        for _ in range(PREROLL_FRAMES):
            session.ingest_frame(silence_frame())
        for _ in range(10):
            session.ingest_frame(tone_frame())
        for _ in range(PAUSE_FRAMES + 2):
            session.ingest_frame(silence_frame())
        for _ in range(10):
            session.ingest_frame(tone_frame())
        for _ in range(PAUSE_FRAMES + 2):
            session.ingest_frame(silence_frame())
        assert wait_until(lambda: delivered == ["recovered "] and bool(reported))

        # Assert - error reported; second Commit landed; still listening
        assert "whisper blew up" in reported
        assert delivered == ["recovered "]
        assert session.is_active() is True
        session.shutdown()

    def test_raising_cue_and_deliverer_do_not_kill_session(self) -> None:
        """Exceptions from cues and deliverer are reported; Commit path continues."""
        # Arrange - start cue and deliverer raise; end cue also raises once
        reported: list[str] = []
        states: list[ContinuousState] = []

        def play_start() -> None:
            raise RuntimeError("start cue failed")

        def play_end() -> None:
            raise RuntimeError("end cue failed")

        def deliverer(text: str) -> None:
            raise RuntimeError(f"deliver failed: {text}")

        def publisher(state: ContinuousState) -> None:
            states.append(state)
            if len(states) == 1:
                raise RuntimeError("publish failed")

        probs = [0.1] * PREROLL_FRAMES + [0.9] * 10 + [0.1] * (PAUSE_FRAMES + 2)
        session = ContinuousSession(
            stream_starter=lambda _on_frame, stop_event: stop_event.wait(timeout=5.0),
            speech_detector_factory=lambda: ScriptedVad(probs),
            transcriber=lambda _a: "hello",
            deliverer=deliverer,
            play_start=play_start,
            play_end=play_end,
            reporter=reported.append,
            state_publisher=publisher,
        )
        session.start()

        # Act - toggle on (raising start/publish), Commit once, toggle off
        session.request_toggle()
        assert wait_until(session.is_active)
        for _ in range(PREROLL_FRAMES):
            session.ingest_frame(silence_frame())
        for _ in range(10):
            session.ingest_frame(tone_frame())
        for _ in range(PAUSE_FRAMES + 2):
            session.ingest_frame(silence_frame())
        assert wait_until(lambda: any("deliver failed" in m for m in reported))
        session.request_toggle()
        assert wait_until(lambda: states and not states[-1].active)

        # Assert - all three failure classes reported; threads survived
        assert any("start cue failed" in m for m in reported)
        assert any("publish failed" in m for m in reported)
        assert any("deliver failed" in m for m in reported)
        assert any("end cue failed" in m for m in reported)
        session.shutdown()
