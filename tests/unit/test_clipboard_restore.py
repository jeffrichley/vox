"""Unit tests for clipboard restore after paste Injection."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import cast
from unittest import mock

import numpy as np
import pytest
from rich.console import Console

from vox.commands import handle_run
from vox.config import ConfigError
from vox.inject import InjectError


def _capture_on_audio(mode: str, console: Console) -> Callable[[np.ndarray], None]:
    """Build handle_run and return the captured on_audio callback for ``mode``.

    Args:
        mode: ``injection_mode`` value passed through config.
        console: Rich console used by handle_run.

    Returns:
        The ``on_audio`` callback registered with the push-to-talk loop.
    """
    stop_ev = threading.Event()
    stop_ev.set()
    on_audio_captured: list[object] = []

    def capture_loop(**kwargs: object) -> None:
        on_audio_captured.append(kwargs.get("on_audio"))

    with (
        mock.patch("vox.commands.get_config") as mock_cfg,
        mock.patch("vox.commands.load_model"),
        mock.patch("vox.commands.preload_default_cues"),
        mock.patch("vox.commands._run_push_to_talk_loop", side_effect=capture_loop),
    ):
        mock_cfg.return_value = {
            "hotkey": "ctrl+v",
            "device_id": None,
            "model_size": "base",
            "compute_type": "float32",
            "compute_device": "cpu",
            "injection_mode": mode,
            "cue_volume": 0.5,
        }
        handle_run(console, stop_event=stop_ev)

    assert len(on_audio_captured) == 1
    on_audio = on_audio_captured[0]
    assert callable(on_audio)
    return cast(Callable[[np.ndarray], None], on_audio)


@pytest.mark.unit
class TestClipboardRestore:
    """clipboard_and_paste restores prior clipboard text after a successful paste."""

    def test_restores_snapshot_after_paste_in_call_order(self) -> None:
        """Sequence is get → set(text) → paste → pause → get → set(previous)."""
        # Arrange - capture on_audio and record call order across clipboard ops
        mock_console = mock.Mock()
        on_audio = _capture_on_audio("clipboard_and_paste", mock_console)
        order: list[str] = []

        def record_get() -> str:
            order.append("get")
            if order.count("get") == 1:
                return "ORIGINAL"
            return "hello"

        def record_set(text: str) -> None:
            order.append(f"set:{text}")

        def record_paste() -> None:
            order.append("paste")

        def record_pause() -> None:
            order.append("pause")

        # Act - inject transcribed text with clipboard_and_paste
        with (
            mock.patch("vox.commands.transcribe", return_value="hello"),
            mock.patch("vox.commands.get_clipboard", side_effect=record_get),
            mock.patch("vox.commands.set_clipboard", side_effect=record_set),
            mock.patch("vox.commands.paste_into_focused", side_effect=record_paste),
            mock.patch(
                "vox.commands._pause_before_clipboard_restore",
                side_effect=record_pause,
            ),
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - full restore sequence and Injected printed
        assert order == [
            "get",
            "set:hello",
            "paste",
            "pause",
            "get",
            "set:ORIGINAL",
        ]
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("Injected" in c for c in calls)

    def test_skips_restore_when_snapshot_empty(self) -> None:
        """Empty or non-text snapshot leaves the transcription on the clipboard."""
        # Arrange - empty snapshot
        mock_console = mock.Mock()
        on_audio = _capture_on_audio("clipboard_and_paste", mock_console)

        # Act - inject with empty prior clipboard
        with (
            mock.patch("vox.commands.transcribe", return_value="hello"),
            mock.patch("vox.commands.get_clipboard", return_value="") as mock_get,
            mock.patch("vox.commands.set_clipboard") as mock_set,
            mock.patch("vox.commands.paste_into_focused"),
            mock.patch("vox.commands._pause_before_clipboard_restore") as mock_pause,
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - set once with transcription; no pause/restore
        mock_set.assert_called_once_with("hello")
        mock_pause.assert_not_called()
        assert mock_get.call_count == 1

    def test_skips_restore_when_clipboard_changed(self) -> None:
        """If the user copies something new during the delay, restore is skipped."""
        # Arrange - second get returns a different value than injected text
        mock_console = mock.Mock()
        on_audio = _capture_on_audio("clipboard_and_paste", mock_console)
        gets = iter(["ORIGINAL", "user copied"])

        # Act - inject while clipboard changes mid-delay
        with (
            mock.patch("vox.commands.transcribe", return_value="hello"),
            mock.patch("vox.commands.get_clipboard", side_effect=lambda: next(gets)),
            mock.patch("vox.commands.set_clipboard") as mock_set,
            mock.patch("vox.commands.paste_into_focused"),
            mock.patch("vox.commands._pause_before_clipboard_restore"),
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - only the initial set(text); no restore of ORIGINAL
        mock_set.assert_called_once_with("hello")

    def test_skips_restore_when_paste_fails(self) -> None:
        """Paste failure keeps the transcription on the clipboard for manual paste."""
        # Arrange - paste raises InjectError
        mock_console = mock.Mock()
        on_audio = _capture_on_audio("clipboard_and_paste", mock_console)

        # Act - inject while paste fails
        with (
            mock.patch("vox.commands.transcribe", return_value="hello"),
            mock.patch("vox.commands.get_clipboard", return_value="ORIGINAL"),
            mock.patch("vox.commands.set_clipboard") as mock_set,
            mock.patch(
                "vox.commands.paste_into_focused",
                side_effect=InjectError("paste failed"),
            ),
            mock.patch("vox.commands._pause_before_clipboard_restore") as mock_pause,
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - no restore; Paste failed + Injected still printed
        mock_set.assert_called_once_with("hello")
        mock_pause.assert_not_called()
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("Paste failed" in c for c in calls)
        assert any("Injected" in c for c in calls)

    def test_snapshot_error_warns_yellow_and_still_pastes(self) -> None:
        """Snapshot InjectError prints a yellow skip warning; paste still runs."""
        # Arrange - get_clipboard fails on snapshot
        mock_console = mock.Mock()
        on_audio = _capture_on_audio("clipboard_and_paste", mock_console)

        # Act - inject while snapshot raises
        with (
            mock.patch("vox.commands.transcribe", return_value="hello"),
            mock.patch(
                "vox.commands.get_clipboard",
                side_effect=InjectError("read failed"),
            ),
            mock.patch("vox.commands.set_clipboard") as mock_set,
            mock.patch("vox.commands.paste_into_focused") as mock_paste,
            mock.patch("vox.commands._pause_before_clipboard_restore") as mock_pause,
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - paste still happens; yellow skip; Injected
        mock_set.assert_called_once_with("hello")
        mock_paste.assert_called_once_with()
        mock_pause.assert_not_called()
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("Clipboard restore skipped" in c for c in calls)
        assert any("Injected" in c for c in calls)

    def test_restore_error_warns_yellow_and_still_injected(self) -> None:
        """Restore InjectError prints yellow skip; Injection still counts as done."""
        # Arrange - second get raises during restore verify
        mock_console = mock.Mock()
        on_audio = _capture_on_audio("clipboard_and_paste", mock_console)
        gets = iter(["ORIGINAL"])

        def get_side_effect() -> str:
            try:
                return next(gets)
            except StopIteration as exc:
                raise InjectError("restore read failed") from exc

        # Act - inject while restore verify fails
        with (
            mock.patch("vox.commands.transcribe", return_value="hello"),
            mock.patch("vox.commands.get_clipboard", side_effect=get_side_effect),
            mock.patch("vox.commands.set_clipboard"),
            mock.patch("vox.commands.paste_into_focused"),
            mock.patch("vox.commands._pause_before_clipboard_restore"),
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - yellow skip warning and Injected
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("Clipboard restore skipped" in c for c in calls)
        assert any("Injected" in c for c in calls)


@pytest.mark.unit
class TestInjectionDispatch:
    """Injection modes resolve once via a dispatch table at startup."""

    def test_unknown_mode_raises_config_error_at_startup(self) -> None:
        """Unsupported injection_mode fails in handle_run, not on first audio."""
        # Arrange - unsupported mode in config
        mock_console = mock.Mock()
        stop_ev = threading.Event()
        stop_ev.set()

        # Act - start handle_run with bad mode
        # Assert - ConfigError names injection_mode
        with (
            mock.patch("vox.commands.get_config") as mock_cfg,
            mock.patch("vox.commands.load_model"),
            mock.patch("vox.commands.preload_default_cues"),
            mock.patch("vox.commands._run_push_to_talk_loop"),
            pytest.raises(ConfigError, match=r"injection_mode"),
        ):
            mock_cfg.return_value = {
                "hotkey": "ctrl+v",
                "device_id": None,
                "model_size": "base",
                "compute_type": "float32",
                "compute_device": "cpu",
                "injection_mode": "telepathy",
                "cue_volume": 0.5,
            }
            handle_run(mock_console, stop_event=stop_ev)

    def test_clipboard_mode_never_calls_get_clipboard(self) -> None:
        """Clipboard mode sets the clipboard only and does not snapshot."""
        # Arrange - clipboard-only mode
        mock_console = mock.Mock()
        on_audio = _capture_on_audio("clipboard", mock_console)

        # Act - inject in clipboard mode
        with (
            mock.patch("vox.commands.transcribe", return_value="hello"),
            mock.patch("vox.commands.get_clipboard") as mock_get,
            mock.patch("vox.commands.set_clipboard") as mock_set,
            mock.patch("vox.commands.paste_into_focused") as mock_paste,
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - set only; no get/paste
        mock_set.assert_called_once_with("hello")
        mock_get.assert_not_called()
        mock_paste.assert_not_called()

    def test_type_mode_never_calls_get_clipboard(self) -> None:
        """Type mode types directly and never touches the clipboard."""
        # Arrange - type mode
        mock_console = mock.Mock()
        on_audio = _capture_on_audio("type", mock_console)

        # Act - inject in type mode
        with (
            mock.patch("vox.commands.transcribe", return_value="hello"),
            mock.patch("vox.commands.get_clipboard") as mock_get,
            mock.patch("vox.commands.set_clipboard") as mock_set,
            mock.patch("vox.commands.type_into_focused") as mock_type,
        ):
            on_audio(np.zeros(1600, dtype=np.float32))

        # Assert - type only
        mock_type.assert_called_once_with("hello")
        mock_get.assert_not_called()
        mock_set.assert_not_called()
