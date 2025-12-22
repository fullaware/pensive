"""Hybrid search and retrieval for agent memory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo.collection import Collection

from config import logger
from app.memory.models import Memory, MemoryType, MemoryTier
from app.vector_memory import generate_embedding


class MemoryRetrieval:
    """Hybrid vector + text search for memory retrieval."""
    
    def __init__(
        self,
        memory_collection: Collection,
        vector_collection: Optional[Collection] = None,
    ):
        """Initialize with MongoDB collections.
        
        Args:
            memory_collection: The agent_memory collection.
            vector_collection: Optional separate vector collection.
        """
        self.collection = memory_collection
        self.vector_collection = vector_collection
    
    def hybrid_search(
        self,
        query: str,
        user_id: Optional[str] = None,
        memory_types: Optional[list[MemoryType]] = None,
        tier: Optional[MemoryTier] = None,
        limit: int = 10,
        min_score: float = 0.3,
        vector_weight: float = 0.6,
        text_weight: float = 0.4,
    ) -> list[dict[str, Any]]:
        """Perform hybrid vector + text search with RRF fusion.
        
        Args:
            query: The search query text.
            user_id: Optional filter by user.
            memory_types: Optional filter by memory types.
            tier: Optional filter by memory tier.
            limit: Maximum number of results.
            min_score: Minimum similarity score threshold.
            vector_weight: Weight for vector search results (0-1).
            text_weight: Weight for text search results (0-1).
        
        Returns:
            List of memory documents with combined relevance scores.
        """
        if self.collection is None:
            return []
        
        if not query or not query.strip():
            return []
        
        # Perform both searches
        vector_results = self._vector_search(
            query, user_id, memory_types, tier, limit * 2, min_score
        )
        text_results = self._text_search(
            query, user_id, memory_types, tier, limit * 2
        )
        
        # Combine with Reciprocal Rank Fusion (RRF)
        combined = self._rrf_fusion(
            vector_results,
            text_results,
            vector_weight,
            text_weight,
            limit
        )
        
        return combined
    
    def _vector_search(
        self,
        query: str,
        user_id: Optional[str],
        memory_types: Optional[list[MemoryType]],
        tier: Optional[MemoryTier],
        limit: int,
        min_score: float,
    ) -> list[dict[str, Any]]:
        """Perform vector similarity search using $vectorSearch."""
        if self.collection is None:
            return []
        
        # Generate query embedding
        query_embedding = generate_embedding(query)
        if query_embedding is None:
            logger.warning("Could not generate query embedding for vector search")
            return []
        
        try:
            # Build $vectorSearch pipeline
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "embedding_vector_search_idx",
                        "path": "embedding",
                        "queryVector": query_embedding,
                        "numCandidates": limit * 10,
                        "limit": limit * 2,
                    }
                },
                {
                    "$addFields": {
                        "vector_score": {"$meta": "vectorSearchScore"}
                    }
                },
            ]
            
            # Build match conditions
            match_conditions = []
            
            if min_score > 0:
                match_conditions.append({"vector_score": {"$gte": min_score}})
            
            if user_id:
                match_conditions.append({
                    "$or": [
                        {"user_id": user_id},
                        {"is_shared": True},
                    ]
                })
            
            if memory_types:
                match_conditions.append({
                    "memory_type": {"$in": [mt.value for mt in memory_types]}
                })
            
            if tier:
                match_conditions.append({"memory_tier": tier.value})
            
            if match_conditions:
                pipeline.append({
                    "$match": {"$and": match_conditions} if len(match_conditions) > 1 else match_conditions[0]
                })
            
            # Project needed fields
            pipeline.append({
                "$project": {
                    "_id": 1,
                    "content": 1,
                    "memory_type": 1,
                    "memory_tier": 1,
                    "user_id": 1,
                    "timestamp": 1,
                    "importance_score": 1,
                    "metadata": 1,
                    "vector_score": 1,
                }
            })
            
            pipeline.append({"$limit": limit})
            
            results = []
            for doc in self.collection.aggregate(pipeline):
                results.append({
                    "id": str(doc["_id"]),
                    "content": doc.get("content", ""),
                    "memory_type": doc.get("memory_type"),
                    "memory_tier": doc.get("memory_tier"),
                    "user_id": doc.get("user_id"),
                    "timestamp": doc.get("timestamp"),
                    "importance_score": doc.get("importance_score", 0.5),
                    "metadata": doc.get("metadata", {}),
                    "vector_score": doc.get("vector_score", 0.0),
                    "source": "vector",
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            # Fall back to brute-force if $vectorSearch not available
            return self._fallback_vector_search(
                query_embedding, user_id, memory_types, tier, limit, min_score
            )
    
    def _fallback_vector_search(
        self,
        query_embedding: list[float],
        user_id: Optional[str],
        memory_types: Optional[list[MemoryType]],
        tier: Optional[MemoryTier],
        limit: int,
        min_score: float,
    ) -> list[dict[str, Any]]:
        """Fallback brute-force vector search."""
        if self.collection is None:
            return []
        
        query = {"has_embedding": True}
        
        if user_id:
            query["$or"] = [{"user_id": user_id}, {"is_shared": True}]
        
        if memory_types:
            query["memory_type"] = {"$in": [mt.value for mt in memory_types]}
        
        if tier:
            query["memory_tier"] = tier.value
        
        try:
            docs = self.collection.find(query).limit(500)
            
            results = []
            for doc in docs:
                doc_embedding = doc.get("embedding")
                if not doc_embedding:
                    continue
                
                # Cosine similarity
                score = self._cosine_similarity(query_embedding, doc_embedding)
                
                if score >= min_score:
                    results.append({
                        "id": str(doc["_id"]),
                        "content": doc.get("content", ""),
                        "memory_type": doc.get("memory_type"),
                        "memory_tier": doc.get("memory_tier"),
                        "user_id": doc.get("user_id"),
                        "timestamp": doc.get("timestamp"),
                        "importance_score": doc.get("importance_score", 0.5),
                        "metadata": doc.get("metadata", {}),
                        "vector_score": score,
                        "source": "vector",
                    })
            
            results.sort(key=lambda x: x["vector_score"], reverse=True)
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Fallback vector search failed: {e}")
            return []
    
    def _text_search(
        self,
        query: str,
        user_id: Optional[str],
        memory_types: Optional[list[MemoryType]],
        tier: Optional[MemoryTier],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Perform full-text search using MongoDB $text."""
        if self.collection is None:
            return []
        
        try:
            search_query = {"$text": {"$search": query}}
            
            if user_id:
                search_query["$or"] = [{"user_id": user_id}, {"is_shared": True}]
            
            if memory_types:
                search_query["memory_type"] = {"$in": [mt.value for mt in memory_types]}
            
            if tier:
                search_query["memory_tier"] = tier.value
            
            docs = self.collection.find(
                search_query,
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(limit)
            
            results = []
            for doc in docs:
                results.append({
                    "id": str(doc["_id"]),
                    "content": doc.get("content", ""),
                    "memory_type": doc.get("memory_type"),
                    "memory_tier": doc.get("memory_tier"),
                    "user_id": doc.get("user_id"),
                    "timestamp": doc.get("timestamp"),
                    "importance_score": doc.get("importance_score", 0.5),
                    "metadata": doc.get("metadata", {}),
                    "text_score": doc.get("score", 0.0),
                    "source": "text",
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Text search failed: {e}")
            return []
    
    def _rrf_fusion(
        self,
        vector_results: list[dict],
        text_results: list[dict],
        vector_weight: float,
        text_weight: float,
        limit: int,
        k: int = 60,
    ) -> list[dict[str, Any]]:
        """Combine results using Reciprocal Rank Fusion.
        
        RRF Score = sum(weight / (k + rank)) for each result list
        """
        scores = {}
        
        # Process vector results
        for rank, result in enumerate(vector_results, start=1):
            doc_id = result["id"]
            rrf_score = vector_weight / (k + rank)
            
            if doc_id not in scores:
                scores[doc_id] = {
                    "result": result,
                    "rrf_score": 0.0,
                    "sources": [],
                }
            
            scores[doc_id]["rrf_score"] += rrf_score
            scores[doc_id]["sources"].append("vector")
            scores[doc_id]["result"]["vector_score"] = result.get("vector_score", 0.0)
        
        # Process text results
        for rank, result in enumerate(text_results, start=1):
            doc_id = result["id"]
            rrf_score = text_weight / (k + rank)
            
            if doc_id not in scores:
                scores[doc_id] = {
                    "result": result,
                    "rrf_score": 0.0,
                    "sources": [],
                }
            
            scores[doc_id]["rrf_score"] += rrf_score
            scores[doc_id]["sources"].append("text")
            scores[doc_id]["result"]["text_score"] = result.get("text_score", 0.0)
        
        # Sort by combined RRF score
        sorted_results = sorted(
            scores.values(),
            key=lambda x: x["rrf_score"],
            reverse=True
        )
        
        # Build final results
        final_results = []
        for item in sorted_results[:limit]:
            result = item["result"]
            result["combined_score"] = item["rrf_score"]
            result["search_sources"] = item["sources"]
            final_results.append(result)
        
        return final_results
    
    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def get_context_for_prompt(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        max_working: int = 20,
        max_summaries: int = 3,
    ) -> str:
        """Get formatted context for LLM prompt.
        
        Args:
            user_id: Optional user ID for filtering.
            session_id: Session ID for working memory.
            max_working: Max working memory items.
            max_summaries: Max summaries to include.
        
        Returns:
            Formatted context string.
        """
        if self.collection is None:
            return ""
        
        contexts = []
        
        # Get working memory from current session
        if session_id:
            query = {
                "session_id": session_id,
                "memory_type": MemoryType.WORKING.value,
            }
            working = list(
                self.collection.find(query).sort("timestamp", 1).limit(max_working)
            )
            
            for mem in working:
                role = mem.get("metadata", {}).get("role", "user")
                content = mem.get("content", "")
                if content:
                    contexts.append(f"{role}: {content}")
        
        # Get recent summaries
        summary_query = {"memory_type": MemoryType.EPISODIC_SUMMARY.value}
        if user_id:
            summary_query["$or"] = [{"user_id": user_id}, {"is_shared": True}]
        
        summaries = list(
            self.collection.find(summary_query).sort("timestamp", -1).limit(max_summaries)
        )
        
        for summary in summaries:
            content = summary.get("content", "")
            if content:
                contexts.append(f"Summary: {content}")
        
        return "\n".join(contexts) if contexts else ""







