"""GUI helpers for the CLI.

Contains the Tk stop-window used by ``vox run``. This package is omitted from
test coverage by design; see ``vox.gui.stop_window`` module docstring for
rationale.
"""

from vox.gui.stop_window import run_stop_window

__all__ = ["run_stop_window"]
