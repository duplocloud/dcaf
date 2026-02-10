"""
Test case for the empty content list fix.
Add this to libs/agno/tests/unit/models/test_message.py
"""

from agno.models.message import Message


class TestGetContentString:
    """Tests for Message.get_content_string() method."""

    def test_get_content_string_with_string_content(self):
        """String content should be returned as-is."""
        message = Message(role="assistant", content="Hello, world!")
        assert message.get_content_string() == "Hello, world!"

    def test_get_content_string_with_empty_list(self):
        """
        Empty list content should return empty string, not "[]".

        This is the bug fix test - previously this would return "[]"
        which caused responses like "I'll help you.[]"
        """
        message = Message(role="assistant", content=[])
        result = message.get_content_string()

        assert result == "", f"Expected empty string, got {repr(result)}"
        assert result != "[]", "Empty list should not return '[]'"

    def test_get_content_string_with_text_block(self):
        """List with text block should extract text."""
        message = Message(role="assistant", content=[{"type": "text", "text": "Hello from block"}])
        assert message.get_content_string() == "Hello from block"

    def test_get_content_string_with_none_content(self):
        """None content should return empty string."""
        message = Message(role="assistant", content=None)
        assert message.get_content_string() == ""

    def test_get_content_string_with_non_text_list(self):
        """List without text blocks should be JSON serialized."""
        message = Message(
            role="assistant", content=[{"type": "image", "url": "http://example.com/img.png"}]
        )
        # This should still JSON serialize non-text content
        result = message.get_content_string()
        assert "image" in result
        assert "example.com" in result


class TestContentConcatenation:
    """
    Integration test demonstrating the bug scenario.

    When tool execution results in an empty assistant message,
    the content should not have "[]" appended.
    """

    def test_concatenation_with_empty_second_message(self):
        """Simulates the tool execution flow that triggers the bug."""
        # First message has content
        msg1 = Message(role="assistant", content="I'll help you run the command.")

        # Second message after tool execution has empty content
        msg2 = Message(role="assistant", content=[])

        # Simulate the concatenation that happens in base.py
        combined = msg1.get_content_string() + msg2.get_content_string()

        assert combined == "I'll help you run the command."
        assert not combined.endswith("[]"), f"Content should not end with '[]': {repr(combined)}"
