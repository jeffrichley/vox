"""Pure Continuous dictation UI text and published-state access for Stop/tray.

Label, tooltip, and notification strings are derived only from
``ContinuousState``. The latest published state is held here so the Stop window
can poll on the Tk thread and the tray can subscribe to changes.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from vox.continuous.session import ContinuousState

# Windows NOTIFYICONDATAW.szTip is 128 chars including the terminating null.
WINDOWS_TOOLTIP_MAX_CHARS = 127

_lock = threading.Lock()
_latest_cell: list[ContinuousState] = [ContinuousState(active=False, error=None)]
_listeners: list[Callable[[ContinuousState], None]] = []


def stop_window_label(state: ContinuousState) -> str:
    """Return the Stop window Continuous status label for ``state``.

    Args:
        state: Published Continuous dictation state.

    Returns:
        Human-readable on / off / error label.
    """
    if state.error is not None:
        return f"Continuous dictation: error — {state.error}"
    if state.active:
        return "Continuous dictation: on"
    return "Continuous dictation: off"


def tray_tooltip(
    state: ContinuousState,
    *,
    max_chars: int = WINDOWS_TOOLTIP_MAX_CHARS,
) -> str:
    """Return the tray tooltip for ``state``, capped to the platform limit.

    Args:
        state: Published Continuous dictation state.
        max_chars: Maximum tooltip length (default: Windows szTip usable chars).

    Returns:
        Tooltip text, truncated with an ellipsis when longer than ``max_chars``.
    """
    text = f"Vox — {stop_window_label(state)}"
    return _truncate(text, max_chars)


def tray_notification(state: ContinuousState) -> tuple[str, str] | None:
    """Return ``(title, message)`` for a tray notification, or None.

    Normal on/off states produce no notification. Only error states do.

    Args:
        state: Published Continuous dictation state.

    Returns:
        Notification title and body when ``state.error`` is set; otherwise None.
    """
    if state.error is None:
        return None
    return ("Vox", state.error)


def get_published_state() -> ContinuousState:
    """Return the latest Continuous state published for UI surfaces.

    Returns:
        Most recently published ``ContinuousState`` (defaults to inactive).
    """
    with _lock:
        return _latest_cell[0]


def publish_continuous_state(state: ContinuousState) -> None:
    """Store ``state`` and notify tray (and other) subscribers.

    Args:
        state: Active flag plus optional error from the session.
    """
    with _lock:
        _latest_cell[0] = state
        listeners = list(_listeners)
    for listener in listeners:
        listener(state)


def subscribe_continuous_state(
    listener: Callable[[ContinuousState], None],
) -> Callable[[], None]:
    """Register a listener for Continuous state publishes.

    Args:
        listener: Called with each newly published ``ContinuousState``.

    Returns:
        Zero-arg unsubscribe callable.
    """
    with _lock:
        _listeners.append(listener)

    def unsubscribe() -> None:
        """Remove this listener if still registered."""
        with _lock:
            if listener in _listeners:
                _listeners.remove(listener)

    return unsubscribe


def _truncate(text: str, max_chars: int) -> str:
    """Return ``text`` if short enough; otherwise truncate with an ellipsis.

    Args:
        text: Full string.
        max_chars: Maximum length of the returned string.

    Returns:
        ``text`` or a truncated version ending in ``…``.
    """
    if max_chars < 1:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars == 1:
        return "…"
    return text[: max_chars - 1] + "…"
