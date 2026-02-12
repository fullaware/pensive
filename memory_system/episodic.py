# Episodic Memory Module
"""Episodic memory for past events and conversation history with vector search."""
from typing import List, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, EpisodicMemorySchema, COLLECTION_EPISODIC, Config


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
        session_id: str,
        role: str,
        content: str,
        event_type: str = "conversation",
        context: Optional[Dict] = None,
    ) -> str:
        """Add an event to episodic memory.

        Args:
            session_id: Session identifier
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
            session_id=session_id,
            role=role,
            content=content,
            embedding=embedding,
            event_type=event_type,
            context=context or {},
        )
        result = await self.collection.insert_one(event_doc)
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
        if not query_embedding:
            return []

        try:
            # Build aggregation pipeline for vector search
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "vector_index",
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
            return results
        except Exception as e:
            # Vector search not available, return empty
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
        cursor = (
            self.collection.find({"session_id": session_id})
            .sort("timestamp", 1)
            .limit(limit)
        )
        history = await cursor.to_list(length=limit)
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

        cursor = (
            self.collection.find(query)
            .sort("timestamp", -1)
            .limit(limit)
        )
        events = await cursor.to_list(length=limit)
        return events

    async def delete_event(self, event_id: str) -> bool:
        """Delete an event.

        Args:
            event_id: Event ObjectId as string

        Returns:
            True if event was deleted, False otherwise
        """
        result = await self.collection.delete_one({"_id": event_id})
        return result.deleted_count > 0

    async def clear_session(self, session_id: str) -> bool:
        """Clear all events for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if session was cleared, False otherwise
        """
        result = await self.collection.delete_many({"session_id": session_id})
        return result.deleted_count > 0

    async def close(self):
        """Close any resources."""
        pass


# No utility functions needed - all embedding generation is handled by EmbeddingClient
