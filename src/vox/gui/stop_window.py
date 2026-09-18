"""Tk stop-window: run push-to-talk in a background thread until the user clicks Stop.

Purpose
-------
This module exists so that the CLI can show a small "Push-to-talk running" window
with a Stop button while ``handle_run()`` (hotkey listener, capture, transcribe,
inject) runs in a daemon thread. The window gives the user a clear way to stop
without relying on Ctrl+C or closing a terminal.

Why this is a separate module
------------------------------
- **Coverage.** This code is intentionally omitted from test coverage. GUI (Tk
  mainloop, widget creation, event handlers) and the threading coordination here
  are not unit-tested; testing them would require either heavy mocking or an
  actual display and user interaction. Rather than sprinkling ``# pragma: no
  cover`` on every line in the CLI, we moved the entire stop-window UI into this
  module and added ``src/vox/gui/*`` to ``[tool.coverage.run] omit`` in
  pyproject.toml. That keeps the CLI clean and makes the "no coverage by design"
  decision explicit in one place.

- **Separation of concerns.** The CLI layer (typer, Rich, exit codes) stays in
  ``vox.cli``; the minimal Tk UI and thread orchestration live here. The boundary
  is a single function: ``run_stop_window(console) -> BaseException | None``.

Return value contract
--------------------
We return an exception (or None) instead of raising RunWindowError here so that
``RunWindowError`` remains defined in ``vox.cli`` and the CLI can attach the
cause and handle it (print message, exit code 1). That avoids circular imports
(cli -> gui -> cli) and keeps "how to present the error to the user" in the CLI.
"""

from __future__ import annotations

import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from rich.console import Console

from vox.commands import handle_run
from vox.continuous.status_text import get_published_state, stop_window_label
from vox.gui.settings_launcher import launch_settings_from_runtime


@dataclass(frozen=True)
class _WorkerHandles:
    """Shared stop/done/error handles for the push-to-talk worker thread."""

    stop_event: threading.Event
    worker_done: threading.Event
    worker_error: list[BaseException]


def _launch_settings(console: Console) -> bool:
    """Launch settings from the stop-window surface.

    Args:
        console: Console used for user-visible launcher failures.

    Returns:
        True when launch succeeds; False when it fails and is reported.
    """
    return launch_settings_from_runtime(console)


def _start_worker(console: Console, handles: _WorkerHandles) -> threading.Thread:
    """Start the push-to-talk worker thread and return it.

    Args:
        console: Console passed into the runtime worker.
        handles: Stop/done/error events shared with the Stop window.

    Returns:
        Started daemon worker thread.
    """

    def run_worker() -> None:
        """Run handle_run in this thread; capture any exception for the caller."""
        try:
            handle_run(console, stop_event=handles.stop_event)
        except Exception as e:
            handles.worker_error.append(e)
        finally:
            handles.worker_done.set()

    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()
    return thread


def _schedule_continuous_label_poll(
    root: tk.Tk,
    status_label: ttk.Label,
    worker_done: threading.Event,
) -> None:
    """Poll published Continuous state and update ``status_label`` on the Tk thread.

    Args:
        root: Stop window root used to schedule ``after`` callbacks.
        status_label: Label showing Continuous dictation on/off/error.
        worker_done: When set, polling stops (worker has exited).
    """

    def _poll_continuous_status() -> None:
        """Refresh Continuous label from published state on the Tk thread."""
        next_text = stop_window_label(get_published_state())
        if str(status_label.cget("text")) != next_text:
            status_label.configure(text=next_text)
        if not worker_done.is_set():
            root.after(200, _poll_continuous_status)

    root.after(200, _poll_continuous_status)


def _wire_stop_window_controls(
    root: tk.Tk,
    main: ttk.Frame,
    console: Console,
    handles: _WorkerHandles,
) -> None:
    """Attach Settings/Stop handlers and worker-error polling to the Stop window.

    Args:
        root: Tk root window.
        main: Main content frame that receives the action buttons.
        console: Console for settings launcher failures.
        handles: Stop/done/error events shared with the worker thread.
    """

    def _wait_then_close() -> None:
        """Poll worker_done; when set, destroy the window (stops mainloop)."""
        if not handles.worker_done.wait(timeout=0.1):
            root.after(100, _wait_then_close)
            return
        root.destroy()

    def _on_stop() -> None:
        """User clicked Stop: signal worker, disable button, schedule window close."""
        handles.stop_event.set()
        stop_btn.state(["disabled"])  # type: ignore[no-untyped-call]  # ttk.Widget.state is unannotated in typeshed
        root.after(100, _wait_then_close)

    def _on_settings() -> None:
        """Launch settings in a separate process so this window stays responsive."""
        _launch_settings(console)

    def _check_worker_error() -> None:
        """If worker already exited with an error, close window immediately."""
        if handles.worker_done.is_set() and handles.worker_error:
            root.destroy()
            return
        root.after(200, _check_worker_error)

    actions = ttk.Frame(main)
    actions.pack(pady=4)
    ttk.Button(actions, text="Settings", command=_on_settings).pack(
        side=tk.LEFT,
        padx=(0, 8),
    )
    stop_btn = ttk.Button(actions, text="Stop", command=_on_stop)
    stop_btn.pack(side=tk.LEFT)
    root.protocol("WM_DELETE_WINDOW", _on_stop)
    root.after(200, _check_worker_error)


def run_stop_window(console: Console) -> BaseException | None:
    """Show a small window with Stop button; run push-to-talk in a thread until Stop.

    Starts a daemon thread that runs ``handle_run(console, stop_event=...)``.
    Displays a Tk window with "Push-to-talk running." and a Stop button. When the
    user clicks Stop (or closes the window), the stop event is set, the worker
    exits, and the window closes. If the worker raised before that, that exception
    is returned so the CLI can raise RunWindowError from it.

    Args:
        console: Rich console for CLI output (e.g. transcription status from
            handle_run).

    Returns:
        The exception from the worker thread if it failed before the user
        clicked Stop; None if the user stopped normally or the worker completed
        without error.
    """
    handles = _WorkerHandles(
        stop_event=threading.Event(),
        worker_done=threading.Event(),
        worker_error=[],
    )
    thread = _start_worker(console, handles)

    root = tk.Tk()
    root.title("Vox")
    root.resizable(False, False)
    root.geometry("320x110")
    root.minsize(280, 90)

    main = ttk.Frame(root, padding=12)
    main.pack(fill=tk.BOTH, expand=True)
    ttk.Label(main, text="Push-to-talk running.").pack(pady=(0, 4))
    status_label = ttk.Label(main, text=stop_window_label(get_published_state()))
    status_label.pack(pady=(0, 8))

    _wire_stop_window_controls(root, main, console, handles)
    _schedule_continuous_label_poll(root, status_label, handles.worker_done)
    root.mainloop()

    thread.join(timeout=1.0)
    if handles.worker_error:
        return handles.worker_error[0]
    return None
