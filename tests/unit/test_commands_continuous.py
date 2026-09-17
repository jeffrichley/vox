"""Unit tests for Continuous dictation run wiring (#35)."""

from __future__ import annotations

import threading
from unittest import mock

import pytest

from vox.commands import handle_run


@pytest.mark.unit
class TestContinuousHotkeyRebind:
    """handle_run rebinds Continuous hotkey without a full restart."""

    def test_handle_run_rebinds_continuous_hotkey_without_restart(self) -> None:
        """Runtime should restart listener when continuous_hotkey changes."""
        # Arrange - simulate continuous hotkey change then final stop
        mock_console = mock.Mock()
        stop_ev = threading.Event()
        continuous_calls: list[str] = []
        watcher_calls = 0

        def fake_loop(**kwargs: object) -> None:
            continuous_calls.append(str(kwargs["continuous_hotkey"]))
            loop_stop = kwargs["stop_event"]
            assert isinstance(loop_stop, threading.Event)
            loop_stop.wait(timeout=0.05)

        def fake_spawn_watcher(
            *,
            stop_event: threading.Event | None,
            hotkey_str: str,
            continuous_hotkey_str: str,
            loop_stop_event: threading.Event,
            reload_requested: threading.Event,
        ) -> threading.Thread:
            _ = (hotkey_str, continuous_hotkey_str)
            nonlocal watcher_calls
            watcher_calls += 1

            def worker() -> None:
                if watcher_calls == 1:
                    reload_requested.set()
                    loop_stop_event.set()
                    return
                if stop_event is not None:
                    stop_event.set()
                loop_stop_event.set()

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            return thread

        with (
            mock.patch("vox.commands.get_config") as mock_cfg,
            mock.patch("vox.commands.load_model"),
            mock.patch("vox.commands.preload_default_cues", return_value=mock.Mock()),
            mock.patch("vox.commands._run_push_to_talk_loop", side_effect=fake_loop),
            mock.patch(
                "vox.commands._spawn_hotkey_reload_watcher",
                side_effect=fake_spawn_watcher,
            ),
        ):
            mock_cfg.side_effect = [
                {
                    "hotkey": "ctrl+f12",
                    "device_id": None,
                    "model_size": "base",
                    "compute_type": "float32",
                    "compute_device": "cpu",
                    "injection_mode": "clipboard",
                    "continuous_hotkey": "ctrl+alt+space",
                    "continuous_pause_seconds": 1.0,
                },
                {
                    "hotkey": "ctrl+f12",
                    "device_id": None,
                    "model_size": "base",
                    "compute_type": "float32",
                    "compute_device": "cpu",
                    "injection_mode": "clipboard",
                    "continuous_hotkey": "ctrl+alt+d",
                    "continuous_pause_seconds": 1.0,
                },
            ]

            # Act - run with continuous hotkey reload
            handle_run(mock_console, stop_event=stop_ev)

        # Assert - Continuous hotkey rebound and message printed
        assert continuous_calls == ["ctrl+alt+space", "ctrl+alt+d"]
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("Rebound continuous hotkey" in c for c in calls)
