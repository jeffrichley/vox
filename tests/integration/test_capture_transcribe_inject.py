"""Integration: capture -> transcribe -> inject (clipboard)."""

from __future__ import annotations

from unittest import mock

import pytest

from vox.inject import set_clipboard


@pytest.mark.integration
def test_transcribe_then_inject_to_clipboard_mock() -> None:
    """Mock transcribe -> set_clipboard -> verify pyperclip.copy called with text."""
    # Arrange - fixed transcription and mock pyperclip
    fixed_text = "mocked transcription result"
    with mock.patch("vox.inject.clipboard.pyperclip") as m_pyperclip:
        # Act - simulate pipeline: transcribe (mocked) -> inject
        set_clipboard(fixed_text)

        # Assert - clipboard was set with exact text
        m_pyperclip.copy.assert_called_once_with(fixed_text)
