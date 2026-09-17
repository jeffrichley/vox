"""Unit tests for Continuous dictation toggle binding on the hotkey listener."""

from __future__ import annotations

from unittest import mock

import pytest
from pynput import keyboard  # type: ignore[import-untyped]

from vox.hotkey.modifiers import ModifierTracker
from vox.hotkey.register import (
    _ContinuousBinding,
    _PushToTalkSession,
    _RecordingConfig,
    _RecordingHooks,
)


def _session(
    *,
    ptt: str = "ctrl+space",
    continuous: str = "ctrl+alt+space",
    on_toggle: mock.Mock | None = None,
    is_active: mock.Mock | None = None,
    modifier_tracker: ModifierTracker | None = None,
) -> tuple[_PushToTalkSession, mock.Mock, mock.Mock]:
    """Build a dual-binding session with mocked Continuous callbacks."""
    toggle = on_toggle if on_toggle is not None else mock.Mock()
    active = is_active if is_active is not None else mock.Mock(return_value=False)
    session = _PushToTalkSession(
        recording_config=_RecordingConfig(
            hotkey_str=ptt,
            device_id=None,
            sample_rate=16_000,
            channels=1,
        ),
        on_audio=mock.Mock(),
        recording_hooks=_RecordingHooks(),
        continuous=_ContinuousBinding(
            hotkey_str=continuous,
            on_toggle=toggle,
            is_active=active,
        ),
        modifier_tracker=modifier_tracker or ModifierTracker(reconcile_physical=False),
    )
    return session, toggle, active


@pytest.mark.unit
class TestContinuousToggleHotkey:
    """Continuous toggle fires once, ignores auto-repeat, and re-arms on release."""

    def test_toggle_fires_once_on_combo(self) -> None:
        """ctrl+alt+d fires the Continuous toggle once (vk path under Alt)."""
        # Arrange - dual-binding session with Continuous inactive
        session, toggle, _active = _session(continuous="ctrl+alt+d")

        # Act - press Continuous combo with Alt-cleared char (vk only)
        session._on_press(keyboard.Key.ctrl_l)
        session._on_press(keyboard.Key.alt_l)
        session._on_press(keyboard.KeyCode.from_vk(ord("D")))

        # Assert - toggle invoked once
        toggle.assert_called_once()

    def test_auto_repeat_ignored_until_trigger_released(self) -> None:
        """Repeated space presses without release do not re-fire the toggle."""
        # Arrange - armed session after first toggle press
        session, toggle, _active = _session()
        session._on_press(keyboard.Key.ctrl_l)
        session._on_press(keyboard.Key.alt_l)
        session._on_press(keyboard.Key.space)
        toggle.reset_mock()

        # Act - auto-repeat space while still held
        session._on_press(keyboard.Key.space)
        session._on_press(keyboard.Key.space)

        # Assert - no additional toggle
        toggle.assert_not_called()

    def test_releasing_trigger_rearms_toggle(self) -> None:
        """Releasing space re-arms so the next combo fires again."""
        # Arrange - toggle already fired once
        session, toggle, _active = _session()
        session._on_press(keyboard.Key.ctrl_l)
        session._on_press(keyboard.Key.alt_l)
        session._on_press(keyboard.Key.space)
        session._on_release(keyboard.Key.space)
        toggle.reset_mock()

        # Act - press Continuous combo again
        session._on_press(keyboard.Key.space)

        # Assert - toggle fires again after re-arm
        toggle.assert_called_once()


@pytest.mark.unit
class TestPushToTalkGating:
    """Push-to-talk is ignored while Continuous is active and works when off."""

    def test_push_to_talk_ignored_while_continuous_active(self) -> None:
        """PTT combo does not start recording while Continuous is active."""
        # Arrange - Continuous reports active
        session, _toggle, _active = _session(is_active=mock.Mock(return_value=True))

        with mock.patch("vox.hotkey.register.threading.Thread") as mock_thread:
            # Act - press PTT combo (ctrl+space)
            session._on_press(keyboard.Key.ctrl_l)
            session._on_press(keyboard.Key.space)

            # Assert - no recording thread started
            mock_thread.assert_not_called()
            assert session.recording_thread is None

    def test_push_to_talk_works_while_continuous_inactive(self) -> None:
        """PTT combo starts recording when Continuous is inactive."""
        # Arrange - Continuous reports inactive
        session, _toggle, _active = _session(is_active=mock.Mock(return_value=False))
        mock_thread = mock.Mock()

        with mock.patch(
            "vox.hotkey.register.threading.Thread", return_value=mock_thread
        ):
            # Act - press PTT combo
            session._on_press(keyboard.Key.ctrl_l)
            session._on_press(keyboard.Key.space)

            # Assert - recording thread started
            mock_thread.start.assert_called_once()
            assert session.recording_thread is mock_thread


@pytest.mark.unit
class TestComboOverlap:
    """When both combos match, the binding with more modifiers wins."""

    def test_more_modifiers_wins_continuous_over_ptt(self) -> None:
        """ctrl+alt+space prefers Continuous when PTT is ctrl+space."""
        # Arrange - Continuous has more modifiers
        session, toggle, _active = _session(
            ptt="ctrl+space",
            continuous="ctrl+alt+space",
        )

        with mock.patch("vox.hotkey.register.threading.Thread") as mock_thread:
            # Act - press the richer Continuous combo
            session._on_press(keyboard.Key.ctrl_l)
            session._on_press(keyboard.Key.alt_l)
            session._on_press(keyboard.Key.space)

            # Assert - Continuous wins; PTT does not start
            toggle.assert_called_once()
            mock_thread.assert_not_called()

    def test_more_modifiers_wins_ptt_over_continuous(self) -> None:
        """ctrl+alt+space prefers PTT when Continuous is ctrl+space."""
        # Arrange - PTT has more modifiers
        session, toggle, _active = _session(
            ptt="ctrl+alt+space",
            continuous="ctrl+space",
        )
        mock_thread = mock.Mock()

        with mock.patch(
            "vox.hotkey.register.threading.Thread", return_value=mock_thread
        ):
            # Act - press the richer PTT combo
            session._on_press(keyboard.Key.ctrl_l)
            session._on_press(keyboard.Key.alt_l)
            session._on_press(keyboard.Key.space)

            # Assert - PTT wins; Continuous does not fire
            toggle.assert_not_called()
            mock_thread.start.assert_called_once()


@pytest.mark.unit
class TestHotkeyStaleModifierReconcile:
    """Physical reconcile prevents stale modifiers from matching Continuous."""

    def test_plain_space_does_not_toggle_when_stale_modifiers_cleared(self) -> None:
        """Fake physical-up state clears ctrl+alt so plain Space does not toggle."""
        # Arrange - fake physical-up state clears ctrl+alt so plain Space does not toggle
        tracker = ModifierTracker(
            reconcile_physical=True,
            physical_key_state=lambda _vk: 0,
        )
        tracker.press("ctrl")
        tracker.press("alt")
        toggle = mock.Mock()
        session = _PushToTalkSession(
            recording_config=_RecordingConfig(
                hotkey_str="ctrl+space",
                device_id=None,
                sample_rate=16_000,
                channels=1,
            ),
            on_audio=mock.Mock(),
            recording_hooks=_RecordingHooks(),
            continuous=_ContinuousBinding(
                hotkey_str="ctrl+alt+space",
                on_toggle=toggle,
                is_active=mock.Mock(return_value=False),
            ),
            modifier_tracker=tracker,
        )

        # Act - plain Space with stale event modifiers reconciled away
        session._on_press(keyboard.Key.space)

        # Assert - Continuous combo no longer matches
        toggle.assert_not_called()
        assert tracker.held() == frozenset()
