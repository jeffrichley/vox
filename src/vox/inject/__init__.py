"""Injection: clipboard and optional keystroke. Phase 3."""

from vox.inject.clipboard import InjectError, get_clipboard, set_clipboard
from vox.inject.keystroke import paste_into_focused, type_into_focused

__all__ = [
    "InjectError",
    "get_clipboard",
    "paste_into_focused",
    "set_clipboard",
    "type_into_focused",
]
