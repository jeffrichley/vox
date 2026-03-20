"""Unit tests for hotkey registration (run_push_to_talk_loop, parse, normalize, key_matches)."""

from __future__ import annotations

import threading
from unittest import mock

import pytest

# Import for listener simulation
from pynput import keyboard  # type: ignore[import-untyped]

from vox.hotkey.register import (
    _key_matches,
    _normalize_modifier,
    _parse_hotkey,
    _PushToTalkSession,
    _RecordingConfig,
    _RecordingHooks,
    run_push_to_talk_loop,
)


@pytest.mark.unit
class TestRunPushToTalkLoop:
    """run_push_to_talk_loop with stop_event set exits without invoking on_audio."""

    def test_run_push_to_talk_loop_exits_when_stop_event_set(self) -> None:
        """When stop_event is set, the loop exits; listener.stop() is called."""
        # Arrange - mock Listener and stop_event set so loop exits without real hotkey
        mock_listener = mock.Mock()
        release = threading.Event()
        mock_listener.join.side_effect = lambda: release.wait(timeout=2.0)
        mock_listener.stop.side_effect = release.set

        mock_cm = mock.Mock()
        mock_cm.__enter__ = mock.Mock(return_value=mock_listener)
        mock_cm.__exit__ = mock.Mock(return_value=None)

        stop_ev = threading.Event()
        stop_ev.set()
        on_audio = mock.Mock()

        with (
            mock.patch("vox.hotkey.register.keyboard.Listener", return_value=mock_cm),
            mock.patch("vox.hotkey.register.record_until_stop"),
        ):
            # Act - run loop in thread; watcher calls listener.stop(), join returns
            result: list[None] = []
            thread = threading.Thread(
                target=lambda: result.append(
                    run_push_to_talk_loop(
                        "ctrl+v",
                        None,
                        16000,
                        1,
                        on_audio,
                        stop_event=stop_ev,
                    )
                )
            )
            thread.start()
            thread.join(timeout=3.0)

            # Assert - loop returned, stop was called, on_audio never called
            assert len(result) == 1
            mock_listener.stop.assert_called_once()
            on_audio.assert_not_called()

    def test_push_to_talk_session_triggers_start_then_stop_callbacks_in_order(
        self,
    ) -> None:
        """Valid press/release fires cue callbacks around record start/stop in order."""
        # Arrange - track callback ordering without using a real listener thread
        events: list[str] = []
        mock_thread = mock.Mock()
        mock_thread.start.side_effect = lambda: events.append("thread-start")
        session = _PushToTalkSession(
            recording_config=_RecordingConfig(
                hotkey_str="ctrl+v",
                device_id=None,
                sample_rate=16_000,
                channels=1,
            ),
            on_audio=mock.Mock(),
            recording_hooks=_RecordingHooks(
                on_start=lambda: events.append("start"),
                on_stop=lambda: events.append(
                    f"stop:{session.stop_event is not None and session.stop_event.is_set()}"
                ),
            ),
        )
        session.queue.put = lambda _item: events.append("queued")  # type: ignore[method-assign]

        with mock.patch(
            "vox.hotkey.register.threading.Thread", return_value=mock_thread
        ):
            # Act - press ctrl, then trigger key, then release trigger key
            session._on_press(keyboard.Key.ctrl_l)
            session._on_press(keyboard.KeyCode.from_char("v"))
            session._on_release(keyboard.KeyCode.from_char("v"))

        # Assert - cue callbacks wrapped the record lifecycle in the intended order
        assert events == ["start", "thread-start", "stop:True", "queued"]

    def test_push_to_talk_session_does_not_trigger_cues_for_unrelated_keys(
        self,
    ) -> None:
        """Unrelated key presses/releases do not trigger start or stop callbacks."""
        # Arrange - session with cue callbacks and mocked record thread
        on_start = mock.Mock()
        on_stop = mock.Mock()
        session = _PushToTalkSession(
            recording_config=_RecordingConfig(
                hotkey_str="ctrl+v",
                device_id=None,
                sample_rate=16_000,
                channels=1,
            ),
            on_audio=mock.Mock(),
            recording_hooks=_RecordingHooks(on_start=on_start, on_stop=on_stop),
        )

        with mock.patch("vox.hotkey.register.threading.Thread"):
            # Act - use unrelated non-hotkey keys
            session._on_press(keyboard.KeyCode.from_char("x"))
            session._on_release(keyboard.KeyCode.from_char("x"))

        # Assert - no cue callback fired
        on_start.assert_not_called()
        on_stop.assert_not_called()


@pytest.mark.unit
class TestParseHotkey:
    """_parse_hotkey parses hotkey strings into modifiers and trigger."""

    def test_parse_hotkey_raises_on_empty_string(self) -> None:
        """Empty or whitespace-only hotkey string raises ValueError."""
        # Arrange - empty and whitespace strings
        # Act - parse empty string
        # Assert - ValueError with hotkey or combination in message
        with pytest.raises(ValueError, match=r"hotkey|combination"):
            _parse_hotkey("")
        # Act - parse whitespace-only
        # Assert - ValueError raised
        with pytest.raises(ValueError, match=r"hotkey|combination"):
            _parse_hotkey("   ")

    def test_parse_hotkey_raises_when_only_modifiers(self) -> None:
        """Hotkey with no trigger key (e.g. 'ctrl') raises ValueError."""
        # Arrange - hotkey string with only modifier
        # Act - parse hotkey with only modifier
        # Assert - ValueError with non-modifier or trigger in message
        with pytest.raises(ValueError, match=r"non-modifier|trigger"):
            _parse_hotkey("ctrl")

    def test_parse_hotkey_returns_modifiers_and_trigger_for_valid_string(self) -> None:
        """Valid hotkey like 'ctrl+v' returns (frozenset of modifiers, trigger)."""
        # Arrange - valid hotkey string ctrl+v
        # Act - parse valid hotkey string
        modifiers, trigger = _parse_hotkey("ctrl+v")
        # Assert - one or more modifiers and trigger v
        assert len(modifiers) >= 1
        assert trigger == "v"

    def test_parse_hotkey_accepts_shift_and_trigger(self) -> None:
        """'ctrl+shift+x' returns both modifiers and trigger x."""
        # Arrange - hotkey string with two modifiers and trigger
        # Act - parse two modifiers and trigger
        modifiers, trigger = _parse_hotkey("ctrl+shift+x")
        # Assert - two modifiers and trigger x
        assert len(modifiers) == 2
        assert trigger == "x"


@pytest.mark.unit
class TestNormalizeModifier:
    """_normalize_modifier maps key to logical modifier or None."""

    def test_normalize_modifier_returns_none_for_none_key(self) -> None:
        """When key is None, _normalize_modifier returns None."""
        # Arrange - key is None
        # Act - normalize None key
        result = _normalize_modifier(None)
        # Assert - result is None
        assert result is None

    def test_normalize_modifier_returns_logical_for_physical_modifier(self) -> None:
        """When key is ctrl_l, returns logical ctrl."""
        # Arrange - physical modifier key ctrl_l
        # Act - normalize physical ctrl_l key
        result = _normalize_modifier(keyboard.Key.ctrl_l)
        # Assert - result is logical Key.ctrl
        assert result is keyboard.Key.ctrl


@pytest.mark.unit
class TestKeyMatches:
    """_key_matches returns True when key matches trigger."""

    def test_key_matches_returns_false_for_none_key(self) -> None:
        """When key is None, _key_matches returns False."""
        # Arrange - key None and trigger v
        # Act - match None key to trigger v
        result = _key_matches(None, "v")
        # Assert - returns False
        assert result is False

    def test_key_matches_returns_true_when_char_matches_trigger(self) -> None:
        """When trigger is str and key has matching char, returns True."""
        # Arrange - KeyCode with char 'v'
        key = keyboard.KeyCode.from_char("v")
        # Act - match key to trigger v
        result = _key_matches(key, "v")
        # Assert - returns True
        assert result is True
