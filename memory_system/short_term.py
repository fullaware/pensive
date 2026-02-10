# Short-Term Memory Module
"""Short-term memory for session context and conversation history."""
from typing import List, Dict, Optional
from collections import deque
from memory_system import Config


class ShortTermMemory:
    """Short-term memory for session context (in-memory)."""

    def __init__(self, max_size: int = None):
        """Initialize short-term memory.

        Args:
            max_size: Maximum number of messages to keep (default from config)
        """
        self.max_size = max_size or Config.SHORT_TERM_MEMORY_SIZE
        self.messages: deque = deque(maxlen=self.max_size)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to short-term memory.

        Args:
            role: Message role (user, assistant, system)
            content: Message content
        """
        self.messages.append({"role": role, "content": content})

    def get_context(self) -> List[Dict[str, str]]:
        """Get all messages in context.

        Returns:
            List of message dictionaries
        """
        return list(self.messages)

    def get_recent_messages(self, n: int = 5) -> List[Dict[str, str]]:
        """Get the most recent messages.

        Args:
            n: Number of messages to retrieve

        Returns:
            List of most recent message dictionaries
        """
        return list(self.messages)[-n:]

    def clear(self) -> None:
        """Clear all messages from short-term memory."""
        self.messages.clear()

    def get_user_messages(self) -> List[str]:
        """Get all user messages.

        Returns:
            List of user message contents
        """
        return [
            msg["content"] for msg in self.messages if msg["role"] == "user"
        ]

    def get_assistant_messages(self) -> List[str]:
        """Get all assistant messages.

        Returns:
            List of assistant message contents
        """
        return [
            msg["content"] for msg in self.messages if msg["role"] == "assistant"
        ]

    def to_prompt_format(self) -> List[Dict[str, str]]:
        """Format messages for LLM prompt.

        Returns:
            List of messages in prompt format
        """
        return self.get_context()