"""Memory models for hierarchical agent memory system.

Implements:
- Short Term Memory (STM): Working Memory, Semantic Cache
- Long Term Memory (LTM): Procedural, Episodic, Semantic, Shared
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MemoryTier(str, Enum):
    """Memory tier classification."""
    STM = "stm"  # Short Term Memory
    LTM = "ltm"  # Long Term Memory


class MemoryType(str, Enum):
    """Specific memory types within each tier."""
    # STM types
    WORKING = "working"                     # Current session context
    SEMANTIC_CACHE = "semantic_cache"       # Recent query embeddings
    
    # LTM types - Procedural
    PROCEDURAL_TOOL = "procedural_tool"     # Tool usage patterns
    PROCEDURAL_WORKFLOW = "procedural_workflow"  # Multi-step task patterns
    
    # LTM types - Episodic
    EPISODIC_CONVERSATION = "episodic_conversation"  # Individual messages
    EPISODIC_SUMMARY = "episodic_summary"   # Conversation summaries
    
    # LTM types - Semantic
    SEMANTIC_KNOWLEDGE = "semantic_knowledge"  # Learned facts
    
    # LTM types - Shared
    SHARED_ENTITY = "shared_entity"         # Entity memory (people, places)
    SHARED_PERSONA = "shared_persona"       # User profile/preferences


class Memory(BaseModel):
    """Base memory model stored in MongoDB."""
    id: Optional[str] = Field(default=None, alias="_id")
    
    # Core identification
    user_id: Optional[str] = None           # Owner of this memory (None = system/shared)
    is_shared: bool = False                 # Family-wide knowledge
    
    # Memory classification
    memory_tier: MemoryTier
    memory_type: MemoryType
    
    # Content
    content: str                            # The actual memory content
    embedding: Optional[list[float]] = None  # Vector embedding
    has_embedding: bool = False
    
    # Context
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    
    # Timestamps
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: Optional[datetime] = None
    expires_at: Optional[datetime] = None   # For TTL-based expiration (STM)
    
    # Scoring
    importance_score: float = 0.5
    decay_score: float = 1.0
    access_count: int = 0
    
    # Relationships
    promoted_from: Optional[str] = None     # Link to original STM if promoted
    consolidated_into: Optional[str] = None  # Link if merged into summary
    related_memories: list[str] = Field(default_factory=list)
    
    # Type-specific metadata
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }
    
    def to_mongo_dict(self) -> dict[str, Any]:
        """Convert to MongoDB document format."""
        data = self.model_dump(by_alias=True, exclude={"id"})
        
        # Convert datetimes to ISO strings
        for field in ["timestamp", "created_at", "last_accessed", "expires_at"]:
            if data.get(field):
                data[field] = data[field].isoformat()
        
        return data
    
    @classmethod
    def from_mongo_dict(cls, data: dict[str, Any]) -> "Memory":
        """Create Memory from MongoDB document."""
        if data is None:
            raise ValueError("Cannot create Memory from None")
        
        # Handle _id
        if "_id" in data:
            data["_id"] = str(data["_id"])
        
        # Handle datetimes
        for field in ["timestamp", "created_at", "last_accessed", "expires_at"]:
            if field in data and isinstance(data[field], str):
                data[field] = datetime.fromisoformat(data[field].replace("Z", "+00:00"))
        
        return cls(**data)


class WorkingMemory(Memory):
    """Short-term working memory for current session context."""
    memory_tier: MemoryTier = MemoryTier.STM
    memory_type: MemoryType = MemoryType.WORKING
    
    # Working memory specific
    role: str = "user"                      # user/assistant
    position_in_context: int = 0            # Order in context window
    
    model_config = {"use_enum_values": True}


class SemanticCacheEntry(Memory):
    """Cached semantic search results for fast retrieval."""
    memory_tier: MemoryTier = MemoryTier.STM
    memory_type: MemoryType = MemoryType.SEMANTIC_CACHE
    
    # Cache specific
    query_text: str = ""                    # Original query
    query_hash: str = ""                    # Hash for fast lookup
    result_count: int = 0                   # Number of results cached
    cache_hits: int = 0                     # Times this cache was used
    
    model_config = {"use_enum_values": True}


class ProceduralMemory(Memory):
    """Memory of tool usage patterns and workflows."""
    memory_tier: MemoryTier = MemoryTier.LTM
    memory_type: MemoryType = MemoryType.PROCEDURAL_TOOL
    
    # Procedural specific
    tool_name: str = ""
    tool_parameters: dict[str, Any] = Field(default_factory=dict)
    outcome: str = ""                       # success/failure/partial
    execution_time_ms: int = 0
    frequency: int = 1                      # Times this pattern occurred
    
    model_config = {"use_enum_values": True}


class EpisodicMemory(Memory):
    """Memory of conversations and summaries."""
    memory_tier: MemoryTier = MemoryTier.LTM
    memory_type: MemoryType = MemoryType.EPISODIC_CONVERSATION
    
    # Episodic specific
    role: str = "user"                      # user/assistant
    message_id: Optional[str] = None
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    summarized: bool = False
    
    # For summaries
    source_message_count: int = 0
    source_message_ids: list[str] = Field(default_factory=list)
    
    model_config = {"use_enum_values": True}


class SemanticMemory(Memory):
    """Memory of learned facts and knowledge."""
    memory_tier: MemoryTier = MemoryTier.LTM
    memory_type: MemoryType = MemoryType.SEMANTIC_KNOWLEDGE
    
    # Semantic specific
    fact_type: str = ""                     # fact/definition/relationship
    subject: str = ""                       # What the fact is about
    confidence: float = 1.0                 # Confidence in the fact
    source_memories: list[str] = Field(default_factory=list)  # Where we learned this
    verified: bool = False                  # If verified by user
    
    model_config = {"use_enum_values": True}


class SharedMemory(Memory):
    """Shared memory for entities and personas."""
    memory_tier: MemoryTier = MemoryTier.LTM
    memory_type: MemoryType = MemoryType.SHARED_ENTITY
    is_shared: bool = True
    
    # Entity specific
    entity_type: str = ""                   # person/place/project/organization
    entity_name: str = ""
    entity_aliases: list[str] = Field(default_factory=list)
    entity_attributes: dict[str, Any] = Field(default_factory=dict)
    mention_count: int = 0
    last_mentioned: Optional[datetime] = None
    
    model_config = {"use_enum_values": True}


# Type mapping for easy lookup
MEMORY_TYPE_CLASSES = {
    MemoryType.WORKING: WorkingMemory,
    MemoryType.SEMANTIC_CACHE: SemanticCacheEntry,
    MemoryType.PROCEDURAL_TOOL: ProceduralMemory,
    MemoryType.PROCEDURAL_WORKFLOW: ProceduralMemory,
    MemoryType.EPISODIC_CONVERSATION: EpisodicMemory,
    MemoryType.EPISODIC_SUMMARY: EpisodicMemory,
    MemoryType.SEMANTIC_KNOWLEDGE: SemanticMemory,
    MemoryType.SHARED_ENTITY: SharedMemory,
    MemoryType.SHARED_PERSONA: SharedMemory,
}


def create_memory(memory_type: MemoryType, **kwargs) -> Memory:
    """Factory function to create the appropriate memory type."""
    cls = MEMORY_TYPE_CLASSES.get(memory_type, Memory)
    return cls(memory_type=memory_type, **kwargs)







