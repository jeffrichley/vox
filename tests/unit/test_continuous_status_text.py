"""Unit tests for Continuous dictation Stop window / tray text (#40)."""

from __future__ import annotations

import pytest

from vox.continuous.session import ContinuousState
from vox.continuous.status_text import (
    WINDOWS_TOOLTIP_MAX_CHARS,
    get_published_state,
    publish_continuous_state,
    stop_window_label,
    subscribe_continuous_state,
    tray_notification,
    tray_tooltip,
)


@pytest.mark.unit
class TestStopWindowLabel:
    """Stop window label text from published ContinuousState."""

    def test_off_state(self) -> None:
        """Inactive with no error reads as Continuous dictation off."""
        # Arrange - inactive Continuous state with no error
        state = ContinuousState(active=False, error=None)

        # Act - build Stop window label
        label = stop_window_label(state)

        # Assert - label reads Continuous dictation off
        assert label == "Continuous dictation: off"

    def test_on_state(self) -> None:
        """Active with no error reads as Continuous dictation on."""
        # Arrange - active Continuous state with no error
        state = ContinuousState(active=True, error=None)

        # Act - build Stop window label
        label = stop_window_label(state)

        # Assert - label reads Continuous dictation on
        assert label == "Continuous dictation: on"

    def test_error_state(self) -> None:
        """Error message appears in the Stop window label."""
        # Arrange - inactive Continuous state with mic stall error
        state = ContinuousState(
            active=False, error="Microphone stopped delivering audio."
        )

        # Act - build Stop window label
        label = stop_window_label(state)

        # Assert - label includes the error message
        assert label == (
            "Continuous dictation: error — Microphone stopped delivering audio."
        )


@pytest.mark.unit
class TestTrayTooltip:
    """Tray tooltip mirrors Continuous state and respects platform length."""

    def test_off_tooltip(self) -> None:
        """Inactive state tooltip says Continuous dictation is off."""
        # Arrange - inactive Continuous state
        state = ContinuousState(active=False, error=None)

        # Act - build tray tooltip
        tip = tray_tooltip(state)

        # Assert - Vox-prefixed off tooltip
        assert tip == "Vox — Continuous dictation: off"

    def test_on_tooltip(self) -> None:
        """Active state tooltip says Continuous dictation is on."""
        # Arrange - active Continuous state
        state = ContinuousState(active=True, error=None)

        # Act - build tray tooltip
        tip = tray_tooltip(state)

        # Assert - Vox-prefixed on tooltip
        assert tip == "Vox — Continuous dictation: on"

    def test_error_tooltip(self) -> None:
        """Error state tooltip includes the error message."""
        # Arrange - Continuous error from clipboard-only refusal
        state = ContinuousState(active=False, error="Clipboard-only mode.")

        # Act - build tray tooltip
        tip = tray_tooltip(state)

        # Assert - Vox-prefixed error tooltip
        assert tip == "Vox — Continuous dictation: error — Clipboard-only mode."

    def test_truncates_to_windows_tooltip_limit(self) -> None:
        """Long error tooltips fit the Windows szTip limit (127 + null)."""
        # Arrange - error message longer than the Windows tooltip budget
        long_error = "x" * 200
        state = ContinuousState(active=False, error=long_error)

        # Act - build tray tooltip at the platform max
        tip = tray_tooltip(state)

        # Assert - length capped with ellipsis, still Vox-prefixed
        assert len(tip) == WINDOWS_TOOLTIP_MAX_CHARS
        assert tip.endswith("…")
        assert tip.startswith("Vox — Continuous dictation: error — ")


@pytest.mark.unit
class TestPublishedStateBridge:
    """Latest Continuous state is readable and fans out to subscribers."""

    def test_publish_updates_get_and_notifies_listener(self) -> None:
        """Publish stores state for polling and calls subscribers once."""
        # Arrange - subscribe a listener before publishing
        seen: list[ContinuousState] = []
        unsubscribe = subscribe_continuous_state(seen.append)
        on_state = ContinuousState(active=True, error=None)

        try:
            # Act - publish an active state
            publish_continuous_state(on_state)

            # Assert - poller and listener see the same state
            assert get_published_state() == on_state
            assert seen == [on_state]
        finally:
            unsubscribe()
            publish_continuous_state(ContinuousState(active=False, error=None))


@pytest.mark.unit
class TestTrayNotification:
    """Windows notification text only for Continuous error states."""

    def test_none_for_on(self) -> None:
        """Active with no error produces no notification."""
        # Arrange - active Continuous state
        state = ContinuousState(active=True, error=None)

        # Act - build notification payload
        note = tray_notification(state)

        # Assert - no notification for normal on
        assert note is None

    def test_none_for_off(self) -> None:
        """Inactive with no error produces no notification."""
        # Arrange - inactive Continuous state
        state = ContinuousState(active=False, error=None)

        # Act - build notification payload
        note = tray_notification(state)

        # Assert - no notification for normal off
        assert note is None

    def test_error_returns_title_and_message(self) -> None:
        """Error state yields a notification title and the error body."""
        # Arrange - Continuous error from clipboard-only refusal
        state = ContinuousState(
            active=False,
            error="Continuous dictation cannot run in clipboard-only mode.",
        )

        # Act - build notification payload
        note = tray_notification(state)

        # Assert - Vox title plus the error as the body
        assert note == (
            "Vox",
            "Continuous dictation cannot run in clipboard-only mode.",
        )
