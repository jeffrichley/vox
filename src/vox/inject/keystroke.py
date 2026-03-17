"""Optional keystroke injection: paste (Ctrl+V) or type into focused window."""

from __future__ import annotations

# pynput has no py.typed in some releases; type-check only.
from pynput.keyboard import Controller, Key  # type: ignore[import-untyped]

from vox.inject.clipboard import InjectError


def paste_into_focused() -> None:
    """Send Ctrl+V to the focused window (assumes clipboard already set).

    Raises:
        InjectError: If key injection fails (e.g. permission denied).
    """
    try:
        controller = Controller()
        with controller.pressed(Key.ctrl):
            controller.press("v")
            controller.release("v")
    except Exception as e:
        raise InjectError(
            f"Failed to send paste key: {e}. "
            "Grant accessibility/input permission to the app if required."
        ) from e


def type_into_focused(text: str) -> None:
    """Type the given text into the focused window character by character.

    Args:
        text: String to type (no truncation).

    Raises:
        InjectError: If key injection fails or text is not a string.
    """
    if not isinstance(text, str):
        raise InjectError(
            f"type_into_focused expects a string; got {type(text).__name__}"
        ) from None
    try:
        controller = Controller()
        for char in text:
            controller.type(char)
    except Exception as e:
        raise InjectError(
            f"Failed to type into focused window: {e}. "
            "Grant accessibility/input permission if required."
        ) from e
