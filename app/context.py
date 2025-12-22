"""Context retrieval helpers."""

from __future__ import annotations

from typing import List, Optional

from config import logger
from database import agent_memory_collection
from app.memory import MemoryStore, MemoryType


def get_recent_context_for_prompt(
    user_id: Optional[str] = None,
    message_limit: int = 20,
    summary_limit: int = 3,
) -> str:
    """Fetch recent context directly for inclusion in the prompt.
    
    Args:
        user_id: Optional user ID to filter memories by.
        message_limit: Maximum number of recent messages to include.
        summary_limit: Maximum number of summaries to include.
    
    Returns:
        Formatted string of recent context for the LLM prompt.
    """
    if agent_memory_collection is None:
        return ""
    
    try:
        memory_store = MemoryStore(agent_memory_collection)
        contexts: List[str] = []

        # Get recent episodic conversation memories
        recent_messages = memory_store.find_by_type(
            MemoryType.EPISODIC_CONVERSATION,
            user_id=user_id,
            limit=message_limit,
            include_shared=True,
        )
        
        seen_messages: set[str] = set()
        for msg in reversed(recent_messages):
            role = msg.metadata.get("role", "unknown")
            msg_key = f"{role}: {msg.content}"
            if msg_key not in seen_messages:
                seen_messages.add(msg_key)
                contexts.append(msg_key)

        # Get recent summaries
        recent_summaries = memory_store.find_by_type(
            MemoryType.EPISODIC_SUMMARY,
            user_id=user_id,
            limit=summary_limit,
            include_shared=True,
        )
        
        for summary in recent_summaries:
            if summary.content:
                contexts.append(f"Summary: {summary.content}")

        return "\n".join(contexts)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(f"Failed to build recent context: {exc}")
        return ""


