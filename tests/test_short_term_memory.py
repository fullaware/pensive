# Short-Term Memory Tests
"""Tests for short-term memory functionality."""
import pytest
from memory_system import ShortTermMemory


def test_add_message():
    """Test adding messages to short-term memory."""
    memory = ShortTermMemory(max_size=5)
    memory.add_message("user", "Hello")
    memory.add_message("assistant", "Hi there!")

    context = memory.get_context()
    assert len(context) == 2
    assert context[0]["role"] == "user"
    assert context[0]["content"] == "Hello"
    assert context[1]["role"] == "assistant"
    assert context[1]["content"] == "Hi there!"


def test_max_size_limit():
    """Test that max size limit is enforced."""
    memory = ShortTermMemory(max_size=3)
    memory.add_message("user", "Message 1")
    memory.add_message("user", "Message 2")
    memory.add_message("user", "Message 3")
    memory.add_message("user", "Message 4")  # Should evict oldest

    context = memory.get_context()
    assert len(context) == 3
    assert "Message 1" not in [m["content"] for m in context]
    assert "Message 4" in [m["content"] for m in context]


def test_get_recent_messages():
    """Test getting recent messages."""
    memory = ShortTermMemory(max_size=10)
    for i in range(5):
        memory.add_message("user", f"Message {i}")

    recent = memory.get_recent_messages(3)
    assert len(recent) == 3
    assert recent[0]["content"] == "Message 2"


def test_clear_memory():
    """Test clearing memory."""
    memory = ShortTermMemory(max_size=5)
    memory.add_message("user", "Hello")
    memory.add_message("assistant", "Hi")
    memory.clear()

    assert len(memory.get_context()) == 0


def test_get_user_messages():
    """Test getting only user messages."""
    memory = ShortTermMemory(max_size=10)
    memory.add_message("user", "User message")
    memory.add_message("assistant", "Assistant message")
    memory.add_message("user", "Another user message")

    user_messages = memory.get_user_messages()
    assert len(user_messages) == 2
    assert "User message" in user_messages
    assert "Another user message" in user_messages


def test_get_assistant_messages():
    """Test getting only assistant messages."""
    memory = ShortTermMemory(max_size=10)
    memory.add_message("user", "User message")
    memory.add_message("assistant", "Assistant message")
    memory.add_message("assistant", "Another assistant message")

    assistant_messages = memory.get_assistant_messages()
    assert len(assistant_messages) == 2
    assert "Assistant message" in assistant_messages
    assert "Another assistant message" in assistant_messages