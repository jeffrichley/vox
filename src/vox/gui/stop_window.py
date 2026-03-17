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
from tkinter import ttk

from rich.console import Console

from vox.commands import handle_run


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
    stop_event = threading.Event()
    worker_done = threading.Event()
    worker_error: list[BaseException] = []

    def run_worker() -> None:
        """Run handle_run in this thread; capture any exception for the caller."""
        try:
            handle_run(console, stop_event=stop_event)
        except Exception as e:
            worker_error.append(e)
        finally:
            worker_done.set()

    # Start push-to-talk in a background thread so the GUI can remain responsive.
    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()

    # --- Tk window: title, size, single frame with label and Stop button ---
    root = tk.Tk()
    root.title("Vox")
    root.resizable(False, False)
    root.geometry("220x90")
    root.minsize(200, 70)

    main = ttk.Frame(root, padding=12)
    main.pack(fill=tk.BOTH, expand=True)
    ttk.Label(main, text="Push-to-talk running.").pack(pady=(0, 8))

    def _wait_then_close() -> None:
        """Poll worker_done; when set, destroy the window (stops mainloop)."""
        if not worker_done.wait(timeout=0.1):
            root.after(100, _wait_then_close)
            return
        root.destroy()

    def _on_stop() -> None:
        """User clicked Stop: signal worker, disable button, schedule window close."""
        stop_event.set()
        stop_btn.state(["disabled"])
        root.after(100, _wait_then_close)

    def _check_worker_error() -> None:
        """If worker already exited with an error, close window immediately."""
        if worker_done.is_set() and worker_error:
            root.destroy()
            return
        root.after(200, _check_worker_error)

    stop_btn = ttk.Button(main, text="Stop", command=_on_stop)
    stop_btn.pack(pady=4)
    root.protocol("WM_DELETE_WINDOW", _on_stop)
    root.after(200, _check_worker_error)
    root.mainloop()

    # After mainloop: worker signalled or errored. Return any stored exception.
    thread.join(timeout=1.0)
    if worker_error:
        return worker_error[0]
    return None
