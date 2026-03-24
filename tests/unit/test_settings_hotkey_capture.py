"""Unit tests for hotkey-capture helpers in settings window."""

from __future__ import annotations

import pytest

from vox.gui.settings_window import (
    _build_hotkey_value,
    _choose_hotkey_preview,
    _event_keysym_to_hotkey_token,
    _format_hotkey_display,
    _modifier_tokens_from_event_state,
    _normalize_hotkey_capture_value,
    _ordered_modifiers,
)


@pytest.mark.unit
def test_modifier_press_preview_matches_alt_dash_requirement() -> None:
    """Single held modifier should render with a trailing dash preview."""
    # Arrange - build a normalized value with only ALT held
    value = _build_hotkey_value(["alt"], None)

    # Act - convert to the field display format
    display = _format_hotkey_display(value)

    # Assert - preview matches expected progressive capture behavior
    assert display == "ALT-"


@pytest.mark.unit
def test_modifier_plus_trigger_preview_matches_alt_f12_requirement() -> None:
    """Held modifier plus trigger should render as one combined sequence."""
    # Arrange - build a normalized ALT+F12 capture value
    value = _build_hotkey_value(["alt"], "f12")

    # Act - convert to the user-facing display
    display = _format_hotkey_display(value)

    # Assert - display shows the expected combination
    assert display == "ALT-F12"


@pytest.mark.unit
def test_display_value_normalizes_back_to_persisted_hotkey_string() -> None:
    """Displayed capture text should normalize to parser-compatible format."""
    # Arrange - use the progressive display shape produced by capture
    display_value = "ALT-F12"

    # Act - normalize for persisted config
    normalized = _normalize_hotkey_capture_value(display_value)

    # Assert - the persisted value remains parse-compatible
    assert normalized == "alt+f12"


@pytest.mark.unit
def test_keysym_to_hotkey_token_maps_modifier_alias() -> None:
    """Modifier keysyms should normalize to persisted modifier tokens."""
    # Arrange - use a Tk left-alt keysym alias
    keysym = "Alt_L"

    # Act - map the keysym to a capture token
    token = _event_keysym_to_hotkey_token(keysym)

    # Assert - alias normalizes to the expected modifier name
    assert token == "alt"


@pytest.mark.unit
def test_keysym_to_hotkey_token_maps_function_key() -> None:
    """Function-key keysyms should be preserved as hotkey trigger tokens."""
    # Arrange - use the F12 keysym
    keysym = "F12"

    # Act - map the keysym to a capture token
    token = _event_keysym_to_hotkey_token(keysym)

    # Assert - function key maps to the expected normalized trigger
    assert token == "f12"


@pytest.mark.unit
def test_keysym_to_hotkey_token_ignores_unsupported_keysyms() -> None:
    """Unsupported keysyms should not be included in captured hotkeys."""
    # Arrange - use a keysym that should not be captured
    keysym = "NoSymbol"

    # Act - map the unsupported keysym
    token = _event_keysym_to_hotkey_token(keysym)

    # Assert - unsupported keys are ignored
    assert token is None


@pytest.mark.unit
def test_modifier_tokens_from_event_state_extracts_common_modifier_bits() -> None:
    """Event-state bitmasks should provide ctrl/shift/alt modifier tokens."""
    # Arrange - include ctrl + shift + alt bits in one event state
    state = 0x4 | 0x1 | 0x8

    # Act - extract normalized modifier tokens from event state
    tokens = _modifier_tokens_from_event_state(state, include_alt=True)

    # Assert - all expected modifier tokens are present in stable order
    assert tokens == ["ctrl", "shift", "alt"]


@pytest.mark.unit
def test_modifier_tokens_from_event_state_can_exclude_alt_when_state_is_noisy() -> None:
    """Trigger-key parsing should ignore sticky alt state bits when requested."""
    # Arrange - include ctrl + alt in one event state
    state = 0x4 | 0x8

    # Act - extract modifiers while excluding alt from state parsing
    tokens = _modifier_tokens_from_event_state(state, include_alt=False)

    # Assert - ctrl remains while alt is ignored
    assert tokens == ["ctrl"]


@pytest.mark.unit
def test_ordered_modifiers_uses_canonical_order_without_stale_leak() -> None:
    """Modifier ordering should remain canonical and exclude stale entries."""
    # Arrange - simulate a new combo that should include cmd only
    modifiers = {"cmd"}

    # Act - order modifiers for hotkey display/persist building
    ordered = _ordered_modifiers(modifiers)

    # Assert - only cmd remains; no previous alt/ctrl modifiers leak in
    assert ordered == ["cmd"]


@pytest.mark.unit
def test_choose_hotkey_preview_keeps_captured_combo_after_trigger_release() -> None:
    """Releasing trigger should not regress preview back to modifier-only text."""
    # Arrange - active state has only a held modifier after a full combo capture
    active = "ctrl+"
    captured = "ctrl+f1"

    # Act - choose preview after trigger release
    preview = _choose_hotkey_preview(
        active=active,
        captured=captured,
        has_trigger=False,
    )

    # Assert - last complete combo remains visible for save/commit
    assert preview == "ctrl+f1"
