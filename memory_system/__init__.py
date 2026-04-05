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
    COLLECTION_UNAUTHORIZED_ACCESS,
    FactSchema,
    EpisodicMemorySchema,
    TaskSchema,
    TimeTrackingSchema,
    ReminderSchema,
    UnauthorizedAccessSchema,
    SystemPromptSchema,
)
from .short_term import ShortTermMemory
from .episodic import EpisodicMemory
from .semantic import SemanticMemory
from .temporal import temporal_memory
from .links import memory_links
from .decay import memory_decay
from .thematic import thematic_memory
from .memory_metrics import MemoryMetrics, memory_metrics
from .compression import MemoryCompression, memory_compression
from .system_prompts import SystemPromptsManager
from .router import QueryRouter
from .bootstrapper import Bootstrapper
from .automated_manager import AutomatedMemoryManager

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
    "COLLECTION_UNAUTHORIZED_ACCESS",
    "FactSchema",
    "EpisodicMemorySchema",
    "TaskSchema",
    "TimeTrackingSchema",
    "ReminderSchema",
    "UnauthorizedAccessSchema",
    "SystemPromptSchema",
    "ShortTermMemory",
    "EpisodicMemory",
    "SemanticMemory",
    "temporal_memory",  # Temporal indexing
    "memory_links",     # Memory linking
    "memory_decay",     # Decay/expiration
    "thematic_memory",  # Thematic memories (multi-level abstraction)
    "MemoryMetrics",    # Memory metrics class
    "memory_metrics",   # Memory metrics instance
    "MemoryCompression",
    "memory_compression",  # Memory compression/archiving
    "SystemPromptsManager",
    "QueryRouter",
    "Bootstrapper",
    "AutomatedMemoryManager",  # Background loop for memory management
]