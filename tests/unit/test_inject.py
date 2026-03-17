"""Unit tests for injection: clipboard and keystroke."""

from __future__ import annotations

from unittest import mock

import pyperclip
import pytest

from vox.inject import InjectError, paste_into_focused, set_clipboard, type_into_focused


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


@pytest.mark.unit
class TestPasteIntoFocused:
    """paste_into_focused sends Ctrl+V via pynput; raises InjectError on failure."""

    def test_paste_into_focused_calls_controller_pressed_and_press_release(
        self,
    ) -> None:
        """paste_into_focused uses Controller and sends ctrl+v."""
        # Arrange - mock pynput Controller
        mock_controller = mock.Mock()
        mock_controller.pressed.return_value.__enter__ = mock.Mock(return_value=None)
        mock_controller.pressed.return_value.__exit__ = mock.Mock(return_value=None)

        with mock.patch(
            "vox.inject.keystroke.Controller", return_value=mock_controller
        ):
            # Act - call paste_into_focused
            paste_into_focused()
            # Assert - pressed used, press and release v called
            mock_controller.pressed.assert_called_once()
            mock_controller.press.assert_called_once_with("v")
            mock_controller.release.assert_called_once_with("v")

    def test_paste_into_focused_raises_inject_error_when_controller_raises(
        self,
    ) -> None:
        """When Controller or key action raises, paste_into_focused raises InjectError."""
        # Arrange - Controller raises on press
        with mock.patch("vox.inject.keystroke.Controller") as mock_controller_class:
            mock_controller = mock.Mock()
            mock_controller.pressed.return_value.__enter__ = mock.Mock(
                return_value=None
            )
            mock_controller.pressed.return_value.__exit__ = mock.Mock(return_value=None)
            mock_controller.press.side_effect = RuntimeError("permission denied")
            mock_controller_class.return_value = mock_controller
            # Act - call paste_into_focused (expects InjectError)
            # Assert - InjectError with paste or permission or Failed in message
            with pytest.raises(InjectError, match=r"paste|permission|Failed"):
                paste_into_focused()


@pytest.mark.unit
class TestTypeIntoFocused:
    """type_into_focused types text char by char; raises on non-string or failure."""

    def test_type_into_focused_calls_controller_type_per_char(self) -> None:
        """type_into_focused calls controller.type for each character."""
        # Arrange - mock Controller
        mock_controller = mock.Mock()
        with mock.patch(
            "vox.inject.keystroke.Controller", return_value=mock_controller
        ):
            # Act - type two characters
            type_into_focused("ab")
            # Assert - type called twice with a and b
            assert mock_controller.type.call_count == 2
            mock_controller.type.assert_any_call("a")
            mock_controller.type.assert_any_call("b")

    def test_type_into_focused_raises_when_not_string(self) -> None:
        """type_into_focused with non-string raises InjectError."""
        # Arrange - call with integer instead of string
        # Act - call type_into_focused with non-string (expects InjectError)
        # Assert - InjectError with string or type in message
        with pytest.raises(InjectError, match=r"string|type"):
            type_into_focused(123)  # type: ignore[arg-type]

    def test_type_into_focused_raises_inject_error_when_controller_raises(self) -> None:
        """When Controller.type raises, type_into_focused raises InjectError."""
        # Arrange - Controller.type raises
        with mock.patch("vox.inject.keystroke.Controller") as mock_controller_class:
            mock_controller = mock.Mock()
            mock_controller.type.side_effect = RuntimeError("access denied")
            mock_controller_class.return_value = mock_controller
            # Act - call type_into_focused (expects InjectError)
            # Assert - InjectError raised
            with pytest.raises(InjectError, match=r"type|permission|Failed"):
                type_into_focused("x")
