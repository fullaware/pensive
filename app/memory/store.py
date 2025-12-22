"""Memory storage operations for the unified agent_memory collection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from bson import ObjectId
from pymongo.collection import Collection

from config import logger, DEFAULT_IMPORTANCE_SCORE, DEFAULT_DECAY_SCORE
from app.memory.models import (
    Memory,
    MemoryTier,
    MemoryType,
    create_memory,
    MEMORY_TYPE_CLASSES,
)
from app.vector_memory import generate_embedding


class MemoryStore:
    """Unified memory storage operations."""
    
    def __init__(self, collection: Collection, vector_collection: Optional[Collection] = None):
        """Initialize with MongoDB collections.
        
        Args:
            collection: The agent_memory collection.
            vector_collection: Optional separate vector collection for embeddings.
        """
        self.collection = collection
        self.vector_collection = vector_collection
        self._ensure_indexes()
    
    def _ensure_indexes(self) -> None:
        """Ensure required indexes exist."""
        if self.collection is None:
            return
        
        try:
            # Compound indexes for efficient querying
            self.collection.create_index([
                ("memory_tier", 1),
                ("memory_type", 1),
                ("timestamp", -1),
            ], name="tier_type_time_idx")
            
            self.collection.create_index([
                ("user_id", 1),
                ("memory_type", 1),
                ("timestamp", -1),
            ], name="user_type_time_idx")
            
            self.collection.create_index([
                ("session_id", 1),
                ("timestamp", -1),
            ], name="session_time_idx")
            
            self.collection.create_index([
                ("conversation_id", 1),
                ("timestamp", -1),
            ], name="conversation_time_idx")
            
            # TTL index for automatic STM expiration
            self.collection.create_index(
                "expires_at",
                expireAfterSeconds=0,
                name="ttl_idx",
                sparse=True,
            )
            
            # Text index for content search
            self.collection.create_index(
                [("content", "text")],
                name="content_text_idx",
            )
            
            logger.info("Memory store indexes ensured")
        except Exception as e:
            logger.error(f"Failed to create memory indexes: {e}")
    
    # ==================== CRUD Operations ====================
    
    def store(
        self,
        memory_type: MemoryType,
        content: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        importance_score: float = DEFAULT_IMPORTANCE_SCORE,
        generate_vector: bool = True,
        expires_in_seconds: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs,
    ) -> Optional[str]:
        """Store a new memory with optional embedding generation.
        
        Args:
            memory_type: The type of memory to store.
            content: The text content of the memory.
            user_id: Optional user who owns this memory.
            session_id: Optional session ID for STM.
            conversation_id: Optional conversation ID.
            importance_score: Initial importance score.
            generate_vector: Whether to generate embedding.
            expires_in_seconds: TTL for STM memories.
            metadata: Additional type-specific metadata.
            **kwargs: Additional fields for specific memory types.
        
        Returns:
            The inserted document ID as string, or None if failed.
        """
        if self.collection is None:
            logger.error("Cannot store memory: collection is None")
            return None
        
        if not content or not content.strip():
            logger.warning("Cannot store empty memory content")
            return None
        
        now = datetime.now(timezone.utc)
        
        # Determine tier from type
        tier = MemoryTier.STM if memory_type in [
            MemoryType.WORKING, MemoryType.SEMANTIC_CACHE
        ] else MemoryTier.LTM
        
        # Create memory object (memory_type passed separately to create_memory)
        memory_data = {
            "memory_tier": tier,
            "content": content,
            "user_id": user_id,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "importance_score": importance_score,
            "decay_score": DEFAULT_DECAY_SCORE,
            "timestamp": now,
            "created_at": now,
            "metadata": metadata or {},
            **kwargs,
        }
        
        # Set expiration for STM
        if expires_in_seconds and tier == MemoryTier.STM:
            from datetime import timedelta
            memory_data["expires_at"] = now + timedelta(seconds=expires_in_seconds)
        
        # Generate embedding if requested
        if generate_vector:
            embedding = generate_embedding(content)
            if embedding:
                memory_data["embedding"] = embedding
                memory_data["has_embedding"] = True
            else:
                memory_data["has_embedding"] = False
        
        try:
            memory = create_memory(memory_type, **memory_data)
            doc = memory.to_mongo_dict()
            
            result = self.collection.insert_one(doc)
            memory_id = str(result.inserted_id)
            
            logger.debug(f"Stored {memory_type.value} memory: {memory_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return None
    
    def get(self, memory_id: str) -> Optional[Memory]:
        """Get a memory by ID.
        
        Args:
            memory_id: The MongoDB ObjectId as string.
        
        Returns:
            The Memory object, or None if not found.
        """
        if self.collection is None:
            return None
        
        try:
            doc = self.collection.find_one({"_id": ObjectId(memory_id)})
            if doc:
                # Update access tracking
                self.collection.update_one(
                    {"_id": ObjectId(memory_id)},
                    {
                        "$inc": {"access_count": 1},
                        "$set": {"last_accessed": datetime.now(timezone.utc).isoformat()}
                    }
                )
                return Memory.from_mongo_dict(doc)
            return None
        except Exception as e:
            logger.error(f"Failed to get memory {memory_id}: {e}")
            return None
    
    def update(self, memory_id: str, updates: dict[str, Any]) -> bool:
        """Update a memory's fields.
        
        Args:
            memory_id: The MongoDB ObjectId as string.
            updates: Dictionary of fields to update.
        
        Returns:
            True if successful, False otherwise.
        """
        if self.collection is None:
            return False
        
        try:
            # Don't allow updating certain fields directly
            protected = ["_id", "created_at", "memory_tier", "memory_type"]
            for field in protected:
                updates.pop(field, None)
            
            result = self.collection.update_one(
                {"_id": ObjectId(memory_id)},
                {"$set": updates}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update memory {memory_id}: {e}")
            return False
    
    def delete(self, memory_id: str) -> bool:
        """Delete a memory (soft delete by marking consolidated).
        
        Args:
            memory_id: The MongoDB ObjectId as string.
        
        Returns:
            True if successful, False otherwise.
        """
        if self.collection is None:
            return False
        
        try:
            result = self.collection.delete_one({"_id": ObjectId(memory_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False
    
    # ==================== Query Operations ====================
    
    def find_by_type(
        self,
        memory_type: MemoryType,
        user_id: Optional[str] = None,
        limit: int = 50,
        include_shared: bool = True,
    ) -> list[Memory]:
        """Find memories by type.
        
        Args:
            memory_type: The type of memories to find.
            user_id: Optional filter by user.
            limit: Maximum number of results.
            include_shared: Whether to include shared memories.
        
        Returns:
            List of Memory objects.
        """
        if self.collection is None:
            return []
        
        query = {"memory_type": memory_type.value}
        
        if user_id:
            if include_shared:
                query["$or"] = [
                    {"user_id": user_id},
                    {"is_shared": True},
                ]
            else:
                query["user_id"] = user_id
        
        try:
            docs = self.collection.find(query).sort("timestamp", -1).limit(limit)
            return [Memory.from_mongo_dict(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Failed to find memories by type: {e}")
            return []
    
    def find_by_session(
        self,
        session_id: str,
        memory_types: Optional[list[MemoryType]] = None,
        limit: int = 100,
    ) -> list[Memory]:
        """Find memories by session ID (for STM).
        
        Args:
            session_id: The session ID.
            memory_types: Optional filter by types.
            limit: Maximum number of results.
        
        Returns:
            List of Memory objects.
        """
        if self.collection is None:
            return []
        
        query = {"session_id": session_id}
        
        if memory_types:
            query["memory_type"] = {"$in": [mt.value for mt in memory_types]}
        
        try:
            docs = self.collection.find(query).sort("timestamp", 1).limit(limit)
            return [Memory.from_mongo_dict(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Failed to find memories by session: {e}")
            return []
    
    def find_by_user(
        self,
        user_id: str,
        tier: Optional[MemoryTier] = None,
        include_shared: bool = True,
        limit: int = 100,
    ) -> list[Memory]:
        """Find memories by user.
        
        Args:
            user_id: The user ID.
            tier: Optional filter by tier.
            include_shared: Whether to include shared memories.
            limit: Maximum number of results.
        
        Returns:
            List of Memory objects.
        """
        if self.collection is None:
            return []
        
        if include_shared:
            query = {"$or": [{"user_id": user_id}, {"is_shared": True}]}
        else:
            query = {"user_id": user_id}
        
        if tier:
            query["memory_tier"] = tier.value
        
        try:
            docs = self.collection.find(query).sort("timestamp", -1).limit(limit)
            return [Memory.from_mongo_dict(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Failed to find memories by user: {e}")
            return []
    
    def text_search(
        self,
        query_text: str,
        user_id: Optional[str] = None,
        memory_types: Optional[list[MemoryType]] = None,
        limit: int = 20,
    ) -> list[Memory]:
        """Full-text search on memory content.
        
        Args:
            query_text: The text to search for.
            user_id: Optional filter by user.
            memory_types: Optional filter by types.
            limit: Maximum number of results.
        
        Returns:
            List of Memory objects sorted by relevance.
        """
        if self.collection is None:
            return []
        
        query = {"$text": {"$search": query_text}}
        
        if user_id:
            query["$or"] = [{"user_id": user_id}, {"is_shared": True}]
        
        if memory_types:
            query["memory_type"] = {"$in": [mt.value for mt in memory_types]}
        
        try:
            docs = self.collection.find(
                query,
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(limit)
            
            return [Memory.from_mongo_dict(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Text search failed: {e}")
            return []
    
    # ==================== Statistics ====================
    
    def get_stats(self, user_id: Optional[str] = None) -> dict[str, Any]:
        """Get memory statistics.
        
        Args:
            user_id: Optional filter by user.
        
        Returns:
            Dictionary with memory statistics.
        """
        if self.collection is None:
            return {"error": "Collection not available"}
        
        try:
            match_stage = {}
            if user_id:
                match_stage = {"$or": [{"user_id": user_id}, {"is_shared": True}]}
            
            pipeline = [
                {"$match": match_stage} if match_stage else {"$match": {}},
                {
                    "$group": {
                        "_id": {
                            "tier": "$memory_tier",
                            "type": "$memory_type"
                        },
                        "count": {"$sum": 1},
                        "avg_importance": {"$avg": "$importance_score"},
                        "avg_decay": {"$avg": "$decay_score"},
                    }
                },
            ]
            
            results = list(self.collection.aggregate(pipeline))
            
            stats = {
                "stm": {"total": 0, "types": {}},
                "ltm": {"total": 0, "types": {}},
                "total": 0,
            }
            
            for r in results:
                tier = r["_id"]["tier"]
                mtype = r["_id"]["type"]
                count = r["count"]
                
                if tier in stats:
                    stats[tier]["total"] += count
                    stats[tier]["types"][mtype] = {
                        "count": count,
                        "avg_importance": r.get("avg_importance", 0.5),
                        "avg_decay": r.get("avg_decay", 1.0),
                    }
                stats["total"] += count
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"error": str(e)}
    
    def count_by_type(self, memory_type: MemoryType, user_id: Optional[str] = None) -> int:
        """Count memories of a specific type.
        
        Args:
            memory_type: The type to count.
            user_id: Optional filter by user.
        
        Returns:
            Count of memories.
        """
        if self.collection is None:
            return 0
        
        query = {"memory_type": memory_type.value}
        if user_id:
            query["$or"] = [{"user_id": user_id}, {"is_shared": True}]
        
        try:
            return self.collection.count_documents(query)
        except Exception as e:
            logger.error(f"Failed to count memories: {e}")
            return 0


