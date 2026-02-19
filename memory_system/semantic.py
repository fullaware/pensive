# Semantic Memory Module
"""Semantic memory for facts and knowledge storage."""
from typing import List, Dict, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, FactSchema, COLLECTION_FACTS, Config
import time


class SemanticMemory:
    """Semantic memory manager for facts and knowledge."""

    def __init__(self):
        self.collection: AsyncIOMotorCollection = db.get_collection(COLLECTION_FACTS)
        self.dimensions = Config.EMBEDDING_DIMENSIONS
        self.vector_limit = Config.VECTOR_SEARCH_LIMIT
        self._embedding_client = None

    @property
    def embedding_client(self):
        """Lazy load embedding client."""
        if self._embedding_client is None:
            from utils import EmbeddingClient
            self._embedding_client = EmbeddingClient()
        return self._embedding_client

    async def add_fact(
        self,
        category: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        metadata: Optional[Dict] = None,
        increment_version: bool = True,
        embedding: Optional[List[float]] = None,
    ) -> str:
        """Add a new fact to semantic memory.

        Args:
            category: Fact category (user, system, preference, etc.)
            key: Unique fact key
            value: Fact value
            confidence: Confidence score (0-1)
            metadata: Additional context
            increment_version: If True and key exists, increment version and archive old; if False, always create new version
            embedding: Optional pre-computed embedding for vector search

        Returns:
            The created fact's ObjectId as string
        """
        # Generate embedding if not provided
        if embedding is None:
            fact_text = f"{key}: {value}"
            embedding = await self.embedding_client.generate_embedding(fact_text)
        
        # Check if fact with same key exists
        existing = await self.get_fact(key)
        
        if existing and increment_version:
            # Mark the current version as archived
            await self.collection.update_one(
                {"_id": existing["_id"]},
                {"$set": {"archived": True, "archived_at": datetime.now(timezone.utc)}}
            )
            
            # Create new version with incremented version number
            new_version = existing.get("version", 1) + 1
            fact_doc = FactSchema.create(
                category=category,
                key=key,
                value=value,
                confidence=confidence,
                metadata=metadata,
                version=new_version,
                embedding=embedding,
            )
        else:
            # Create new fact with version 1
            fact_doc = FactSchema.create(
                category=category,
                key=key,
                value=value,
                confidence=confidence,
                metadata=metadata,
                embedding=embedding,
            )
        
        result = await self.collection.insert_one(fact_doc)
        return str(result.inserted_id)

    async def get_fact(self, key: str, category: Optional[str] = None) -> Optional[Dict]:
        """Get a fact by key.

        Args:
            key: Fact key
            category: Optional category filter

        Returns:
            Fact document or None if not found
        """
        query = {"key": key}
        if category:
            query["category"] = category

        # Get the latest version of the fact
        fact = await self.collection.find_one(query, sort=[("version", -1)])
        return fact

    async def get_latest_fact_version(self, key: str) -> Optional[Dict]:
        """Get the latest version of a fact by key.

        Args:
            key: Fact key

        Returns:
            Latest version of fact document or None if not found
        """
        query = {"key": key}
        # Get the latest version (highest version number)
        fact = await self.collection.find_one(query, sort=[("version", -1)])
        return fact

    async def update_fact(self, key: str, updates: Dict, increment_version: bool = True) -> bool:
        """Update an existing fact with version tracking.

        This method archives the current version and creates a new version with incremented version number.

        Args:
            key: Fact key to update
            updates: Dictionary of fields to update
            increment_version: Whether to increment the version number (default: True)

        Returns:
            True if fact was updated, False otherwise
        """
        # Get current version
        current = await self.get_fact(key)
        if not current:
            return False

        # Get the collection
        collection = self.collection

        # Create new version with incremented version number
        new_version = current.get("version", 1) + 1
        
        # Update the current version to mark it as archived
        await collection.update_one(
            {"_id": current["_id"]},
            {"$set": {"archived": True, "archived_at": datetime.now(timezone.utc)}}
        )

        # Create new version document
        new_doc = dict(current)
        new_doc["version"] = new_version
        new_doc["archived"] = False
        new_doc["created_at"] = datetime.now(timezone.utc)
        new_doc["updated_at"] = datetime.now(timezone.utc)
        new_doc["metadata"] = current.get("metadata", {})
        new_doc["metadata"]["updated_from"] = str(current["_id"])
        new_doc.update(updates)
        # Remove the _id to allow new insert
        new_doc.pop("_id", None)

        # Insert new version
        result = await collection.insert_one(new_doc)
        return True

    async def delete_fact(self, key: str) -> bool:
        """Delete a fact.

        Args:
            key: Fact key to delete

        Returns:
            True if fact was deleted, False otherwise
        """
        result = await self.collection.delete_one({"key": key})
        return result.deleted_count > 0

    async def delete_facts_by_category(self, category: str) -> List[Dict]:
        """Delete all facts in a category and return them for proof.

        Args:
            category: Category to delete

        Returns:
            List of deleted fact documents
        """
        # First get the facts to be deleted
        cursor = self.collection.find({"category": category})
        facts_to_delete = await cursor.to_list(length=None)

        if not facts_to_delete:
            return []

        # Delete them
        result = await self.collection.delete_many({"category": category})

        return facts_to_delete

    async def delete_facts_by_query(self, query: Dict) -> List[Dict]:
        """Delete facts matching a query and return them for proof.

        Args:
            query: MongoDB query to match facts to delete

        Returns:
            List of deleted fact documents
        """
        # First get the facts to be deleted
        cursor = self.collection.find(query)
        facts_to_delete = await cursor.to_list(length=None)

        if not facts_to_delete:
            return []

        # Delete them
        result = await self.collection.delete_many(query)

        return facts_to_delete

    async def get_facts_by_category(self, category: str) -> List[Dict]:
        """Get all facts in a category.

        Args:
            category: Category to filter by

        Returns:
            List of fact documents
        """
        cursor = self.collection.find({"category": category})
        facts = await cursor.to_list(length=None)
        return facts

    async def get_all_facts(self) -> List[Dict]:
        """Get all non-archived facts.

        Returns:
            List of all non-archived fact documents
        """
        cursor = self.collection.find({"archived": {"$ne": True}})
        facts = await cursor.to_list(length=None)
        return facts

    async def get_user_name(self) -> Optional[str]:
        """Get the user's name from facts.

        Returns:
            User name or None if not stored
        """
        # Try to get name from user category first
        fact = await self.get_fact("user_name", category="user")
        if fact:
            return fact.get("value")
        
        # Try to get name from persona category
        fact = await self.get_fact("name", category="persona")
        if fact:
            return fact.get("value")
        
        # Try to get name from user category (just "name" key)
        fact = await self.get_fact("name", category="user")
        if fact:
            return fact.get("value")
        
        return None

    async def get_user_preferences(self) -> Dict[str, str]:
        """Get all user preferences as a dictionary.

        Returns:
            Dictionary of preference key-value pairs
        """
        facts = await self.get_facts_by_category("user")
        return {f.get("key", ""): f.get("value", "") for f in facts}

    async def vector_search(
        self, query: str, filters: Optional[Dict] = None, limit: int = None
    ) -> List[Dict]:
        """Search semantic memory using vector similarity.

        Args:
            query: Query text to search for
            filters: Optional filters (category, etc.)
            limit: Number of results to return

        Returns:
            List of matching facts sorted by similarity
        """
        # Generate embedding for the query
        query_embedding = await self.embedding_client.generate_embedding(query)
        
        # Log the query (embedding will be masked by MongoDB.log_query)
        start_time = time.time()
        if db._logging_enabled:
            await db.log_query(
                COLLECTION_FACTS, 
                "vectorSearch", 
                {"query": query[:100] + "..." if len(query) > 100 else query},
                {"limit": limit or self.vector_limit}
            )
        
        if not query_embedding:
            # Fall back to returning all non-archived facts
            cursor = self.collection.find({"archived": {"$ne": True}})
            results = await cursor.to_list(length=limit or self.vector_limit)
            duration_ms = (time.time() - start_time) * 1000
            if db._logging_enabled:
                await db.log_query(
                    COLLECTION_FACTS, 
                    "find", 
                    {"archived": {"$ne": True}},
                    {"count": len(results)},
                    duration_ms
                )
            return results

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
            
            duration_ms = (time.time() - start_time) * 1000
            if db._logging_enabled:
                await db.log_query(
                    COLLECTION_FACTS, 
                    "vectorSearch", 
                    {"query": query[:100] + "..." if len(query) > 100 else query},
                    {"results_count": len(results), "limit": limit or self.vector_limit},
                    duration_ms
                )
            
            # If no results from vector search, fall back to all non-archived facts
            if not results:
                cursor = self.collection.find({"archived": {"$ne": True}})
                results = await cursor.to_list(length=limit or self.vector_limit)
                if db._logging_enabled:
                    await db.log_query(
                        COLLECTION_FACTS, 
                        "find_fallback", 
                        {"archived": {"$ne": True}},
                        {"count": len(results)},
                        duration_ms
                    )
            
            return results
        except Exception as e:
            # Vector search not available, return all non-archived facts
            duration_ms = (time.time() - start_time) * 1000
            if db._logging_enabled:
                await db.log_query(
                    COLLECTION_FACTS, 
                    "vectorSearch_error", 
                    {"error": str(e)},
                    {},
                    duration_ms
                )
            cursor = self.collection.find({"archived": {"$ne": True}})
            return await cursor.to_list(length=limit or self.vector_limit)

    async def close(self):
        """Close any resources."""
        pass
