"""Clipboard injection: set system clipboard to transcribed text."""

from __future__ import annotations

import pyperclip  # type: ignore[import-untyped]


class InjectError(Exception):
    """Raised when clipboard or keystroke injection fails."""

    pass


def set_clipboard(text: str) -> None:
    """Set the system clipboard to the given text.

    Args:
        text: UTF-8 string to place on the clipboard (exact; no truncation).

    Raises:
        InjectError: If clipboard access fails, with an actionable message.
    """
    if not isinstance(text, str):
        raise InjectError(
            f"Clipboard expects a string; got {type(text).__name__}. "
            "Ensure transcription returns plain text."
        ) from None
    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException as e:
        raise InjectError(
            f"Failed to set clipboard: {e}. "
            "On Linux install xclip or xsel; on headless/servers use a display or mock."
        ) from e
