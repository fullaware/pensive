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
                        "index": "v_idx_facts",
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

    async def get_fact_with_decay(self, key: str, category: Optional[str] = None) -> Optional[Dict]:
        """Get a fact by key with decayed confidence.
        
        Args:
            key: Fact key
            category: Optional category filter
            
        Returns:
            Fact document with updated confidence or None if not found
        """
        fact = await self.get_fact(key, category)
        if not fact:
            return None
        
        from memory_system.decay import memory_decay
        decayed_confidence = memory_decay.calculate_confidence_with_decay(
            fact.get("confidence", 1.0),
            fact.get("created_at", datetime.now(timezone.utc)),
        )
        
        return {
            **fact,
            "confidence": decayed_confidence,
            "decayed_at": datetime.now(timezone.utc),
        }

    async def resolve_fact_conflict(
        self,
        fact_key: str,
        new_value: str,
        source_weight: float = 1.0,
        merge_strategy: str = "latest_wins",
    ) -> Optional[str]:
        """Resolve a conflict when updating a fact.
        
        Args:
            fact_key: Fact key to update
            new_value: New value for the fact
            source_weight: Weight of this source (0-1)
            merge_strategy: "latest_wins", "weighted_average", or "majority_vote"
            
        Returns:
            The updated fact's ObjectId as string, or None if failed
        """
        current = await self.get_fact(fact_key)
        if not current:
            return await self.add_fact(
                category="user",
                key=fact_key,
                value=new_value,
                confidence=source_weight,
            )
        
        # Get current version for comparison
        current_version = current.get("version", 1)
        
        # Apply merge strategy
        if merge_strategy == "latest_wins":
            final_value = new_value
            final_confidence = source_weight
            final_confidence_explanation = f"Latest update from source with weight {source_weight}"
            
        elif merge_strategy == "weighted_average":
            current_weight = current.get("provenance", {}).get("source_weight", 1.0)
            final_confidence = (
                current.get("confidence", 1.0) * current_weight +
                source_weight * (1 - current_weight)
            )
            final_value = new_value
            final_confidence_explanation = f"Weighted average (current: {current_weight}, new: {source_weight})"
            
        else:  # majority_vote or default
            final_value = new_value
            final_confidence = source_weight
            final_confidence_explanation = f"Update with source weight {source_weight}"
        
        # Mark current version as archived
        await self.collection.update_one(
            {"_id": current["_id"]},
            {"$set": {"archived": True, "archived_at": datetime.now(timezone.utc)}}
        )
        
        # Create new version
        new_version = current_version + 1
        fact_doc = FactSchema.create(
            category=current.get("category", "user"),
            key=fact_key,
            value=final_value,
            confidence=final_confidence,
            metadata=current.get("metadata", {}),
            version=new_version,
            source="merge_operation",
            confidence_explanation=final_confidence_explanation,
            source_weight=source_weight,
            conflict_status="resolved",
        )
        
        result = await self.collection.insert_one(fact_doc)
        return str(result.inserted_id)

    async def set_fact_disputed(self, fact_key: str, reason: str) -> bool:
        """Mark a fact as disputed for human review.
        
        Args:
            fact_key: Fact key to mark as disputed
            reason: Reason for dispute
            
        Returns:
            True if fact was marked as disputed
        """
        result = await self.collection.update_one(
            {"key": fact_key},
            {"$set": {
                "temporal.conflict_status": "disputed",
                "metadata.dispute_reason": reason,
            }}
        )
        return result.modified_count > 0

    async def verify_fact(self, fact_key: str, verified_by: str) -> bool:
        """Mark a disputed fact as verified.
        
        Args:
            fact_key: Fact key to verify
            verified_by: Who verified (user/system)
            
        Returns:
            True if fact was verified
        """
        result = await self.collection.update_one(
            {"key": fact_key},
            {"$set": {
                "temporal.conflict_status": "resolved",
                "provenance.human_verified": True,
                "provenance.verified_by": verified_by,
                "provenance.verified_at": datetime.now(timezone.utc),
            }}
        )
        return result.modified_count > 0

    async def get_retrieval_stats(self, key: str) -> Dict:
        """Get retrieval statistics for a fact.
        
        Args:
            key: Fact key
            
        Returns:
            Dictionary with retrieval statistics
        """
        cursor = await self.collection.find({"key": key}).sort("version", 1)
        versions = await cursor.to_list(length=None)
        
        if not versions:
            return {}
        
        total_versions = len(versions)
        latest_version = max(v.get("version", 0) for v in versions)
        
        confidence_history = [
            {"version": v.get("version", 0), "confidence": v.get("confidence", 0)}
            for v in versions
        ]
        
        return {
            "key": key,
            "total_versions": total_versions,
            "latest_version": latest_version,
            "confidence_history": confidence_history,
            "created_at": versions[0].get("created_at"),
            "latest_updated": versions[-1].get("updated_at"),
        }

    async def get_all_facts_with_decay(self) -> List[Dict]:
        """Get all non-archived facts with decayed confidence.
        
        Returns:
            List of facts with updated confidence scores
        """
        facts = await self.get_all_facts()
        
        from memory_system.decay import memory_decay
        
        result = []
        for fact in facts:
            decayed_confidence = memory_decay.calculate_confidence_with_decay(
                fact.get("confidence", 1.0),
                fact.get("created_at", datetime.now(timezone.utc)),
            )
            result.append({
                **fact,
                "confidence": decayed_confidence,
                "decayed_at": datetime.now(timezone.utc),
            })
        
        return result

    async def get_facts_by_confidence_range(
        self,
        min_confidence: float = 0.0,
        max_confidence: float = 1.0,
        include_archived: bool = False,
    ) -> List[Dict]:
        """Get facts within a confidence range.
        
        Args:
            min_confidence: Minimum confidence threshold
            max_confidence: Maximum confidence threshold
            include_archived: Include archived facts
            
        Returns:
            List of matching facts
        """
        query = {
            "confidence": {"$gte": min_confidence, "$lte": max_confidence}
        }
        
        if not include_archived:
            query["archived"] = {"$ne": True}
        
        cursor = self.collection.find(query)
        return await cursor.to_list(length=None)

    async def get_memory_health_stats(self) -> Dict:
        """Get memory health statistics.
        
        Returns:
            Dictionary with memory health metrics
        """
        from memory_system.decay import memory_decay
        
        total_facts = await self.collection.count_documents({})
        
        category_counts = await self.collection.aggregate([
            {"$group": {"_id": "$category", "count": {"$sum": 1}}}
        ]).to_list(length=None)
        
        high_confidence = await self.collection.count_documents({
            "confidence": {"$gte": 0.8},
            "archived": {"$ne": True}
        })
        medium_confidence = await self.collection.count_documents({
            "confidence": {"$gte": 0.5, "$lt": 0.8},
            "archived": {"$ne": True}
        })
        low_confidence = await self.collection.count_documents({
            "confidence": {"$lt": 0.5},
            "archived": {"$ne": True}
        })
        
        # Get disputed facts
        disputed = await self.collection.count_documents({
            "temporal.conflict_status": "disputed"
        })
        
        return {
            "total_facts": total_facts,
            "non_archived_count": high_confidence + medium_confidence + low_confidence,
            "by_category": {item["_id"] or "uncategorized": item["count"] for item in category_counts},
            "by_confidence": {
                "high": high_confidence,
                "medium": medium_confidence,
                "low": low_confidence,
            },
            "disputed_count": disputed,
        }

    async def close(self):
        """Close any resources."""
        pass
