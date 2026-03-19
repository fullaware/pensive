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
from .temporal import temporal_memory
from .links import memory_links
from .decay import memory_decay
from .thematic import thematic_memory
from .memory_metrics import memory_metrics
from .compression import memory_compression
from .system_prompts import SystemPromptsManager
from .router import QueryRouter
from .bootstrapper import Bootstrapper

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
    "temporal_memory",  # Temporal indexing
    "memory_links",     # Memory linking
    "memory_decay",     # Decay/expiration
    "thematic_memory",  # Thematic memories (multi-level abstraction)
    "memory_metrics",   # Memory metrics
    "memory_compression",  # Memory compression/archiving
    "SystemPromptsManager",
    "QueryRouter",
    "Bootstrapper",
]
