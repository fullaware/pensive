# Episodic Memory Module
"""Episodic memory for past events and conversation history with vector search."""
from typing import List, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, EpisodicMemorySchema, COLLECTION_EPISODIC, Config
import time


class EpisodicMemory:
    """Episodic memory manager for past events with vector search."""

    def __init__(self):
        self.collection: AsyncIOMotorCollection = db.get_collection(COLLECTION_EPISODIC)
        self.dimensions = Config.EMBEDDING_DIMENSIONS  # Configurable embedding dimensions
        self.vector_limit = Config.VECTOR_SEARCH_LIMIT
        self._embedding_client = None

    @property
    def embedding_client(self):
        """Lazy load embedding client."""
        if self._embedding_client is None:
            from utils import EmbeddingClient
            self._embedding_client = EmbeddingClient()
        return self._embedding_client

    async def add_event(
        self,
        role: str,
        content: str,
        event_type: str = "conversation",
        context: Optional[Dict] = None,
    ) -> str:
        """Add an event to episodic memory.

        Args:
            role: Event role (user, assistant, system)
            content: Event content
            event_type: Type of event
            context: Additional context

        Returns:
            The created event's ObjectId as string
        """
        # Generate embedding using the embedding client
        embedding = await self.embedding_client.generate_embedding(content)
        if not embedding:
            # If embedding fails, raise error - we need proper embeddings
            raise RuntimeError(f"Failed to generate embedding for content: {content[:100]}...")

        event_doc = EpisodicMemorySchema.create(
            role=role,
            content=content,
            embedding=embedding,
            event_type=event_type,
            context=context or {},
        )
        
        start_time = time.time()
        result = await self.collection.insert_one(event_doc)
        
        duration_ms = (time.time() - start_time) * 1000
        if db._logging_enabled:
            await db.log_query(
                COLLECTION_EPISODIC, 
                "insert_one", 
                {"role": role},
                {"content_length": len(content)},
                duration_ms
            )
        return str(result.inserted_id)

    async def vector_search(
        self, query: str, filters: Optional[Dict] = None, limit: int = None
    ) -> List[Dict]:
        """Search episodic memory using vector similarity.

        Args:
            query: Query text to search for
            filters: Optional filters (session_id, event_type, etc.)
            limit: Number of results to return

        Returns:
            List of matching events sorted by similarity
        """
        # Generate embedding for the query
        query_embedding = await self.embedding_client.generate_embedding(query)
        
        # Log the query (embedding will be masked by MongoDB.log_query)
        start_time = time.time()
        if db._logging_enabled:
            await db.log_query(
                COLLECTION_EPISODIC, 
                "vectorSearch", 
                {"query": query[:100] + "..." if len(query) > 100 else query},
                {"limit": limit or self.vector_limit}
            )
        
        if not query_embedding:
            if db._logging_enabled:
                duration_ms = (time.time() - start_time) * 1000
                await db.log_query(
                    COLLECTION_EPISODIC, 
                    "vectorSearch", 
                    {"query": query[:100] + "..." if len(query) > 100 else query},
                    {"reason": "no_embedding", "count": 0},
                    duration_ms
                )
            return []

        try:
            # Build aggregation pipeline for vector search
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "v_idx_episodic_memories",
                        "path": "embedding",
                        "queryVector": query_embedding,
                        "numCandidates": limit or self.vector_limit * 5,
                        "limit": limit or self.vector_limit,
                    }
                },
                {"$set": {"score": {"$meta": "vectorSearchScore"}}},
            ]

            if filters:
                pipeline.insert(1, {"$match": filters})

            cursor = self.collection.aggregate(pipeline)
            results = await cursor.to_list(length=limit or self.vector_limit)
            
            duration_ms = (time.time() - start_time) * 1000
            if db._logging_enabled:
                await db.log_query(
                    COLLECTION_EPISODIC, 
                    "vectorSearch", 
                    {"query": query[:100] + "..." if len(query) > 100 else query},
                    {"results_count": len(results), "limit": limit or self.vector_limit},
                    duration_ms
                )
            return results
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            if db._logging_enabled:
                await db.log_query(
                    COLLECTION_EPISODIC, 
                    "vectorSearch_error", 
                    {"query": query[:100] + "..." if len(query) > 100 else query, "error": str(e)},
                    {},
                    duration_ms
                )
            return []

    async def get_session_history(
        self, session_id: str, limit: int = 50
    ) -> List[Dict]:
        """Get conversation history for a session.

        Args:
            session_id: Session identifier
            limit: Maximum number of messages to return

        Returns:
            List of message documents
        """
        start_time = time.time()
        cursor = (
            self.collection.find({"session_id": session_id})
            .sort("timestamp", 1)
            .limit(limit)
        )
        history = await cursor.to_list(length=limit)
        
        duration_ms = (time.time() - start_time) * 1000
        if db._logging_enabled:
            await db.log_query(
                COLLECTION_EPISODIC, 
                "find", 
                {"session_id": session_id, "limit": limit},
                {"count": len(history)},
                duration_ms
            )
        return history

    async def get_recent_events(
        self, limit: int = 10, event_type: Optional[str] = None
    ) -> List[Dict]:
        """Get most recent events.

        Args:
            limit: Maximum number of events to return
            event_type: Optional event type filter

        Returns:
            List of recent event documents
        """
        query = {}
        if event_type:
            query["event_type"] = event_type

        start_time = time.time()
        cursor = (
            self.collection.find(query)
            .sort("timestamp", -1)
            .limit(limit)
        )
        events = await cursor.to_list(length=limit)
        
        duration_ms = (time.time() - start_time) * 1000
        if db._logging_enabled:
            await db.log_query(
                COLLECTION_EPISODIC, 
                "find", 
                query,
                {"count": len(events), "limit": limit},
                duration_ms
            )
        return events

    async def delete_event(self, event_id: str) -> bool:
        """Delete an event.

        Args:
            event_id: Event ObjectId as string

        Returns:
            True if event was deleted, False otherwise
        """
        start_time = time.time()
        result = await self.collection.delete_one({"_id": event_id})
        
        duration_ms = (time.time() - start_time) * 1000
        if db._logging_enabled:
            await db.log_query(
                COLLECTION_EPISODIC, 
                "delete_one", 
                {"_id": event_id},
                {"deleted_count": result.deleted_count},
                duration_ms
            )
        return result.deleted_count > 0

    async def clear_session(self, session_id: str) -> bool:
        """Clear all events for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if session was cleared, False otherwise
        """
        start_time = time.time()
        result = await self.collection.delete_many({"session_id": session_id})
        
        duration_ms = (time.time() - start_time) * 1000
        if db._logging_enabled:
            await db.log_query(
                COLLECTION_EPISODIC, 
                "delete_many", 
                {"session_id": session_id},
                {"deleted_count": result.deleted_count},
                duration_ms
            )
        return result.deleted_count > 0

    async def close(self):
        """Close any resources."""
        pass


# No utility functions needed - all embedding generation is handled by EmbeddingClient
