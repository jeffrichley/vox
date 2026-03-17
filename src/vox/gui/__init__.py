"""GUI helpers for the CLI.

Contains the Tk stop-window and system tray used by ``vox run`` (or ``vox``).
This package is omitted from test coverage by design; see ``vox.gui.stop_window``
module docstring for rationale.
"""

from vox.gui.stop_window import run_stop_window
from vox.gui.tray import run_tray

__all__ = ["run_stop_window", "run_tray"]
