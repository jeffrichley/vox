"""Thread-safe modifier-key tracker with optional Windows physical reconcile."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable

# Virtual-key codes for GetAsyncKeyState (Windows).
_VK_SHIFT = 0x10
_VK_CONTROL = 0x11
_VK_MENU = 0x12  # Alt
_VK_LWIN = 0x5B
_VK_RWIN = 0x5C

_MODIFIER_VKS: dict[str, tuple[int, ...]] = {
    "ctrl": (_VK_CONTROL,),
    "shift": (_VK_SHIFT,),
    "alt": (_VK_MENU,),
    "cmd": (_VK_LWIN, _VK_RWIN),
}

_VK_TO_MODIFIER: dict[int, str] = {
    _VK_CONTROL: "ctrl",
    _VK_SHIFT: "shift",
    _VK_MENU: "alt",
    _VK_LWIN: "cmd",
    _VK_RWIN: "cmd",
}

_KEY_DOWN_BIT = 0x8000


def modifier_name_for_vk(vk: int) -> str | None:
    """Map a Windows virtual-key code to a logical modifier name.

    Args:
        vk: Virtual-key code (e.g. 0x11 for VK_CONTROL).

    Returns:
        Logical name (``ctrl``, ``alt``, ``shift``, ``cmd``), or None.
    """
    return _VK_TO_MODIFIER.get(vk)


def _windows_physical_key_state(vk: int) -> int:
    """Return GetAsyncKeyState for ``vk`` (Windows only).

    Args:
        vk: Virtual-key code.

    Returns:
        Raw GetAsyncKeyState result; high bit set means the key is down.
    """
    import ctypes  # noqa: PLC0415 — Windows-only API; avoid import cost on other OSes

    return int(ctypes.windll.user32.GetAsyncKeyState(vk))


class ModifierTracker:
    """Thread-safe set of held modifiers shared by hotkey listener and session.

    On Windows (or when ``reconcile_physical`` is True with an injectable
    key-state function), ``reconcile`` drops modifiers that are physically up
    so swallowed key-ups cannot leave a stale combo.
    """

    def __init__(
        self,
        *,
        reconcile_physical: bool | None = None,
        physical_key_state: Callable[[int], int] | None = None,
    ) -> None:
        """Create an empty tracker.

        Args:
            reconcile_physical: When True, ``reconcile`` consults physical key
                state. Defaults to True on Windows, False elsewhere.
            physical_key_state: Optional ``vk -> GetAsyncKeyState-like int``.
                Defaults to the OS API on Windows when reconcile is enabled.
        """
        if reconcile_physical is None:
            reconcile_physical = sys.platform == "win32"
        self._reconcile_physical = reconcile_physical
        if physical_key_state is not None:
            self._physical_key_state: Callable[[int], int] | None = physical_key_state
        elif reconcile_physical and sys.platform == "win32":
            self._physical_key_state = _windows_physical_key_state
        else:
            self._physical_key_state = None
        self._lock = threading.Lock()
        self._held: set[str] = set()

    def press(self, name: str) -> None:
        """Record a modifier key-down.

        Args:
            name: Logical modifier (``ctrl``, ``alt``, ``shift``, ``cmd``).
        """
        with self._lock:
            self._held.add(name)

    def release(self, name: str) -> None:
        """Record a modifier key-up.

        Args:
            name: Logical modifier name.
        """
        with self._lock:
            self._held.discard(name)

    def held(self) -> frozenset[str]:
        """Return the current held modifier set (no reconcile).

        Returns:
            Frozen set of logical modifier names.
        """
        with self._lock:
            return frozenset(self._held)

    def any_held(self) -> bool:
        """Return True if any modifier is currently held (after reconcile).

        Returns:
            Whether at least one modifier remains held.
        """
        self.reconcile()
        with self._lock:
            return bool(self._held)

    def reconcile(self) -> None:
        """Drop held modifiers that are physically up when reconciliation is on."""
        if not self._reconcile_physical or self._physical_key_state is None:
            return
        with self._lock:
            still: set[str] = set()
            for name in self._held:
                vks = _MODIFIER_VKS.get(name, ())
                if any(self._physical_key_state(vk) & _KEY_DOWN_BIT for vk in vks):
                    still.add(name)
            self._held = still
