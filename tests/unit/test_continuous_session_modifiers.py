"""Unit tests for ContinuousSession modifier-wait on toggle-off (#39)."""

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
from vox.hotkey.modifiers import ModifierTracker

_SPEECH_FRAMES = 10


def _make_session(  # noqa: PLR0913 — mirrors ContinuousSession injectables for tests
    *,
    probs: list[float],
    deliverer: Callable[[str], None],
    modifiers: ModifierTracker,
    warn: Callable[[str], None] | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    modifier_wait_seconds: float = 2.0,
) -> ContinuousSession:
    """Build a session with a shared modifier tracker."""

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
        play_start=lambda: None,
        play_end=lambda: None,
        modifier_tracker=modifiers,
        warn=warn,
        clock=clock,
        sleep=sleep,
        modifier_wait_seconds=modifier_wait_seconds,
    )


def _arm_with_speech(
    session: ContinuousSession, speech_frames: int = _SPEECH_FRAMES
) -> None:
    """Toggle on and feed enough speech frames for a Commit."""
    session.start()
    session.request_toggle()
    assert wait_until(session.is_active)
    for _ in range(PREROLL_FRAMES):
        session.ingest_frame(silence_frame())
    for _ in range(speech_frames):
        session.ingest_frame(tone_frame())


@pytest.mark.unit
class TestContinuousSessionModifierWait:
    """Toggle-off Commit waits for modifiers; Pause Commits do not."""

    def test_toggle_off_commit_waits_until_modifiers_released(self) -> None:
        """Final toggle-off Commit is delayed until held modifiers clear."""
        # Arrange - ctrl held so delivery cannot proceed until release
        delivered: list[str] = []
        modifiers = ModifierTracker(reconcile_physical=False)
        modifiers.press("ctrl")
        probs = [0.1] * PREROLL_FRAMES + [0.9] * 20
        session = _make_session(
            probs=probs,
            deliverer=delivered.append,
            modifiers=modifiers,
        )
        _arm_with_speech(session)

        # Act - toggle off while ctrl held, then release
        session.request_toggle()
        assert wait_until(lambda: not session.is_active())
        assert delivered == []
        modifiers.release("ctrl")
        assert wait_until(lambda: bool(delivered))

        # Assert - delivered only after modifiers cleared
        assert delivered == ["hello "]
        session.shutdown()

    def test_modifier_wait_timeout_warns_and_still_delivers(self) -> None:
        """After 2 s still held, yellow warning fires and text is Injected."""
        # Arrange - modifiers never released; short wait window
        delivered: list[str] = []
        warnings: list[str] = []
        fake_now = 0.0
        modifiers = ModifierTracker(reconcile_physical=False)
        modifiers.press("alt")

        def clock() -> float:
            return fake_now

        def sleep(seconds: float) -> None:
            nonlocal fake_now
            fake_now += seconds

        probs = [0.1] * PREROLL_FRAMES + [0.9] * 20
        session = _make_session(
            probs=probs,
            deliverer=delivered.append,
            modifiers=modifiers,
            warn=warnings.append,
            clock=clock,
            sleep=sleep,
            modifier_wait_seconds=2.0,
        )
        _arm_with_speech(session)

        # Act - toggle off with alt still held through the timeout
        session.request_toggle()
        assert wait_until(lambda: bool(delivered) and bool(warnings))

        # Assert - warning then Injection despite held modifier
        assert delivered == ["hello "]
        assert any("modifier" in w.lower() for w in warnings)
        assert fake_now >= 2.0
        session.shutdown()

    def test_pause_commit_delivers_despite_held_modifiers(self) -> None:
        """Pause Commits Inject immediately even when modifiers are held."""
        # Arrange - ctrl held during a Pause Commit (not toggle-off)
        delivered: list[str] = []
        modifiers = ModifierTracker(reconcile_physical=False)
        modifiers.press("ctrl")
        speech = [0.9] * _SPEECH_FRAMES
        silence = [0.1] * (PAUSE_FRAMES + 2)
        probs = [0.1] * PREROLL_FRAMES + speech + silence
        session = _make_session(
            probs=probs,
            deliverer=delivered.append,
            modifiers=modifiers,
        )
        session.start()
        session.request_toggle()
        assert wait_until(session.is_active)

        # Act - complete a Pause while ctrl is still held
        for _ in range(PREROLL_FRAMES):
            session.ingest_frame(silence_frame())
        for _ in range(_SPEECH_FRAMES):
            session.ingest_frame(tone_frame())
        for _ in range(PAUSE_FRAMES + 2):
            session.ingest_frame(silence_frame())
        assert wait_until(lambda: bool(delivered))

        # Assert - Pause Commit did not wait on modifiers
        assert delivered == ["hello "]
        assert modifiers.held() == frozenset({"ctrl"})
        session.shutdown()
