# Memory System Package
"""Memory system for agentic AI."""
from .config import Config, get_config
from .mongodb import MongoDB, db
from .schema import (
    COLLECTION_FACTS,
    COLLECTION_EPISODIC,
    COLLECTION_TASKS,
    COLLECTION_TIME_TRACKING,
    COLLECTION_REMINDERS,
    COLLECTION_SYSTEM_PROMPTS,
    FactSchema,
    EpisodicMemorySchema,
    TaskSchema,
    TimeTrackingSchema,
    ReminderSchema,
    SystemPromptSchema,
)
from .short_term import ShortTermMemory
from .episodic import EpisodicMemory
from .semantic import SemanticMemory
from .system_prompts import SystemPromptsManager
from .router import QueryRouter

__all__ = [
    "Config",
    "get_config",
    "MongoDB",
    "db",
    "COLLECTION_FACTS",
    "COLLECTION_EPISODIC",
    "COLLECTION_TASKS",
    "COLLECTION_TIME_TRACKING",
    "COLLECTION_REMINDERS",
    "COLLECTION_SYSTEM_PROMPTS",
    "FactSchema",
    "EpisodicMemorySchema",
    "TaskSchema",
    "TimeTrackingSchema",
    "ReminderSchema",
    "SystemPromptSchema",
    "ShortTermMemory",
    "EpisodicMemory",
    "SemanticMemory",
    "SystemPromptsManager",
    "QueryRouter",
]