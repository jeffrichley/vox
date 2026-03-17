"""Unit tests for injection: clipboard and keystroke."""

from __future__ import annotations

from unittest import mock

import pyperclip
import pytest

from vox.inject import InjectError, set_clipboard


@pytest.mark.unit
class TestSetClipboard:
    """set_clipboard sets system clipboard and raises on failure."""

    def test_calls_pyperclip_copy_with_text(self) -> None:
        """set_clipboard calls pyperclip.copy with the given string."""
        # Arrange - text and mock
        text = "hello world"
        with mock.patch("vox.inject.clipboard.pyperclip") as m_pyperclip:
            # Act - set clipboard
            set_clipboard(text)

            # Assert - copy was called with exact text
            m_pyperclip.copy.assert_called_once_with(text)

    def test_non_string_raises_inject_error(self) -> None:
        """set_clipboard with non-string raises InjectError."""
        # Arrange - invalid input (non-string)

        # Act - call with int
        # Assert - raises with actionable message containing 'string'
        with pytest.raises(InjectError, match="string"):
            set_clipboard(123)  # type: ignore[arg-type]

    def test_pyperclip_failure_raises_inject_error(self) -> None:
        """PyperclipException is wrapped in InjectError with message."""
        # Arrange - pyperclip raises
        with mock.patch("vox.inject.clipboard.pyperclip.copy") as m_copy:
            m_copy.side_effect = pyperclip.PyperclipException("no display")

            # Act - set clipboard (triggers pyperclip.copy)
            # Assert - InjectError with hint containing 'clipboard'
            with pytest.raises(InjectError, match="clipboard"):
                set_clipboard("x")
