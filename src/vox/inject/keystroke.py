"""Optional keystroke injection: paste (Ctrl+V) or type into focused window."""

from __future__ import annotations

# pynput has no py.typed in some releases; type-check only.
from pynput.keyboard import Controller, Key  # type: ignore[import-untyped]

from vox.inject.clipboard import InjectError


def paste_into_focused() -> None:
    """Send Ctrl+V to the focused window (assumes clipboard already set).

    Requires OS accessibility/permission for synthetic key events.
    On failure raises InjectError with a hint to check permissions.

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

    Use only for short text; for long text prefer set_clipboard + paste_into_focused.
    Requires OS accessibility permission.

    Args:
        text: String to type (no truncation).

    Raises:
        InjectError: If key injection fails.
    """
    if not isinstance(text, str):
        raise InjectError(
            f"type_into_focused expects a string; got {type(text).__name__}"
        ) from None
    try:
        controller = Controller()
        for char in text:
            # pynput types one character at a time; special keys need mapping
            controller.type(char)
    except Exception as e:
        raise InjectError(
            f"Failed to type into focused window: {e}. "
            "Grant accessibility/input permission if required."
        ) from e
