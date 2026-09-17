"""Unit tests for ModifierTracker (#39)."""

from __future__ import annotations

import pytest

from vox.hotkey.modifiers import ModifierTracker, modifier_name_for_vk


@pytest.mark.unit
class TestModifierTrackerPhysicalReconcile:
    """Windows physical key state drops stale held modifiers."""

    def test_fake_physical_key_state_clears_stale_modifiers(self) -> None:
        """Held modifiers that are physically up are dropped on reconcile."""
        # Arrange - event state says ctrl+alt held; physical API says both up
        down: set[int] = set()

        def key_state(vk: int) -> int:
            return 0x8000 if vk in down else 0

        tracker = ModifierTracker(
            reconcile_physical=True,
            physical_key_state=key_state,
        )
        tracker.press("ctrl")
        tracker.press("alt")
        assert tracker.held() == frozenset({"ctrl", "alt"})

        # Act - reconcile against physically-up keys
        tracker.reconcile()

        # Assert - stale modifiers cleared so a plain Space would not match
        assert tracker.held() == frozenset()

    def test_mapping_key_codes_to_modifiers_via_fake_key_state(self) -> None:
        """VK codes map to logical modifiers and survive when physically down."""
        # Arrange - only VK_CONTROL physically down
        down = {0x11}

        def key_state(vk: int) -> int:
            return 0x8000 if vk in down else 0

        tracker = ModifierTracker(
            reconcile_physical=True,
            physical_key_state=key_state,
        )
        tracker.press("ctrl")
        tracker.press("alt")
        tracker.press("shift")

        # Act - reconcile while only VK_CONTROL is physically down
        tracker.reconcile()

        # Assert - only physically-down ctrl remains; vk maps to ctrl
        assert modifier_name_for_vk(0x11) == "ctrl"
        assert modifier_name_for_vk(0x12) == "alt"
        assert modifier_name_for_vk(0x10) == "shift"
        assert modifier_name_for_vk(0x5B) == "cmd"
        assert tracker.held() == frozenset({"ctrl"})

    def test_without_physical_reconcile_trusts_key_events(self) -> None:
        """Non-Windows mode keeps event-tracked modifiers without OS checks."""
        # Arrange - no physical key-state function
        tracker = ModifierTracker(reconcile_physical=False)
        tracker.press("ctrl")
        tracker.press("alt")

        # Act - reconcile with physical checks disabled
        tracker.reconcile()

        # Assert - still held from key events alone
        assert tracker.held() == frozenset({"ctrl", "alt"})
