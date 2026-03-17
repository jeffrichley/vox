"""System tray icon: run push-to-talk until the user chooses Quit from the menu.

Purpose
-------
This module provides a tray icon (pystray) so the user can run Vox without a visible
window and stop it via the tray menu (Quit). Same return contract as
``run_stop_window``: return exception or None for the CLI to handle.

Coverage
--------
Like ``stop_window``, this module is omitted from test coverage via
``src/vox/gui/*`` in pyproject.toml.
"""

from __future__ import annotations

import io
import threading
from importlib.resources import files

import pystray  # type: ignore[import-untyped]
from PIL import Image
from rich.console import Console

from vox.commands import handle_run


def _load_icon_image() -> Image.Image:
    """Load the Vox tray icon from package data.

    Returns:
        PIL Image suitable for pystray (will be scaled by the backend if needed).
    """
    data = (files("vox.gui") / "vox_icon.png").read_bytes()
    return Image.open(io.BytesIO(data)).copy()


def run_tray(console: Console) -> BaseException | None:
    """Show a system tray icon with Quit; run push-to-talk in a thread until Quit.

    Starts a daemon thread that runs ``handle_run(console, stop_event=...)``.
    Displays a pystray icon with a "Quit" menu item. When the user selects Quit,
    the stop event is set, the icon stops, and the worker thread exits. If the
    worker raised before that, that exception is returned so the CLI can raise
    RunWindowError from it.

    Args:
        console: Rich console for CLI output (e.g. transcription status from
            handle_run).

    Returns:
        The exception from the worker thread if it failed before the user
        chose Quit; None if the user quit normally or the worker completed
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

    def on_quit(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        """Set stop event and stop the icon so run() returns.

        Args:
            icon: The tray icon; stopping it ends the run loop.
            _item: The menu item that was clicked (unused).
        """
        stop_event.set()
        icon.stop()

    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()

    image = _load_icon_image()
    menu = pystray.Menu(pystray.MenuItem("Quit", on_quit))
    icon = pystray.Icon("vox", image, "Vox — push-to-talk", menu=menu)
    icon.run()

    thread.join(timeout=2.0)
    if worker_error:
        return worker_error[0]
    return None
