"""Memory Coordinator for STM/LTM management, promotion, and consolidation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import hashlib

from pymongo.collection import Collection

from config import logger, DEFAULT_IMPORTANCE_SCORE, DEFAULT_DECAY_SCORE
from app.memory.models import Memory, MemoryTier, MemoryType
from app.memory.store import MemoryStore
from app.memory.retrieval import MemoryRetrieval


# Default TTL for STM memories (8 hours)
DEFAULT_STM_TTL_SECONDS = 8 * 60 * 60

# Promotion thresholds
IMPORTANCE_PROMOTION_THRESHOLD = 0.7
SEMANTIC_CACHE_REPEAT_THRESHOLD = 3


class MemoryCoordinator:
    """Orchestrates memory operations across STM and LTM."""
    
    def __init__(
        self,
        memory_collection: Collection,
        vector_collection: Optional[Collection] = None,
    ):
        """Initialize the coordinator.
        
        Args:
            memory_collection: The agent_memory collection.
            vector_collection: Optional separate vector collection.
        """
        self.store = MemoryStore(memory_collection, vector_collection)
        self.retrieval = MemoryRetrieval(memory_collection, vector_collection)
        self.collection = memory_collection
    
    # ==================== Query Routing ====================
    
    def route_query(
        self,
        query: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        include_stm: bool = True,
        include_ltm: bool = True,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Route a query to appropriate memory stores and combine results.
        
        Args:
            query: The search query.
            user_id: Optional user ID for filtering.
            session_id: Session ID for STM access.
            include_stm: Whether to search STM.
            include_ltm: Whether to search LTM.
            limit: Maximum total results.
        
        Returns:
            Combined list of relevant memories.
        """
        results = []
        
        # Check semantic cache first
        cached = self._check_semantic_cache(query, user_id)
        if cached:
            logger.debug("Semantic cache hit for query")
            return cached[:limit]
        
        # Determine which tiers to search
        tiers = []
        if include_stm:
            tiers.append(MemoryTier.STM)
        if include_ltm:
            tiers.append(MemoryTier.LTM)
        
        # Perform hybrid search across tiers
        for tier in tiers:
            tier_results = self.retrieval.hybrid_search(
                query=query,
                user_id=user_id,
                tier=tier,
                limit=limit,
            )
            results.extend(tier_results)
        
        # Sort by combined score and deduplicate
        seen_ids = set()
        unique_results = []
        for r in sorted(results, key=lambda x: x.get("combined_score", 0), reverse=True):
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                unique_results.append(r)
        
        final_results = unique_results[:limit]
        
        # Cache the results
        self._update_semantic_cache(query, user_id, final_results)
        
        return final_results
    
    def _check_semantic_cache(
        self,
        query: str,
        user_id: Optional[str],
    ) -> Optional[list[dict]]:
        """Check if query results are cached."""
        if self.collection is None:
            return None
        
        query_hash = hashlib.sha256(query.lower().encode()).hexdigest()[:16]
        
        cache_query = {
            "memory_type": MemoryType.SEMANTIC_CACHE.value,
            "metadata.query_hash": query_hash,
        }
        if user_id:
            cache_query["user_id"] = user_id
        
        try:
            cache_entry = self.collection.find_one(cache_query)
            if cache_entry:
                # Update cache hit count
                self.collection.update_one(
                    {"_id": cache_entry["_id"]},
                    {
                        "$inc": {"metadata.cache_hits": 1},
                        "$set": {"last_accessed": datetime.now(timezone.utc).isoformat()}
                    }
                )
                return cache_entry.get("metadata", {}).get("cached_results", [])
            return None
        except Exception as e:
            logger.error(f"Cache check failed: {e}")
            return None
    
    def _update_semantic_cache(
        self,
        query: str,
        user_id: Optional[str],
        results: list[dict],
    ) -> None:
        """Update semantic cache with query results."""
        if self.collection is None or not results:
            return
        
        query_hash = hashlib.sha256(query.lower().encode()).hexdigest()[:16]
        
        # Store truncated results in cache
        cached_results = [
            {
                "id": r["id"],
                "content": r.get("content", "")[:500],
                "memory_type": r.get("memory_type"),
                "combined_score": r.get("combined_score", 0),
            }
            for r in results[:20]
        ]
        
        try:
            self.store.store(
                memory_type=MemoryType.SEMANTIC_CACHE,
                content=query,
                user_id=user_id,
                importance_score=0.3,
                generate_vector=True,
                expires_in_seconds=3600,  # 1 hour TTL for cache
                metadata={
                    "query_hash": query_hash,
                    "cached_results": cached_results,
                    "result_count": len(results),
                    "cache_hits": 0,
                },
            )
        except Exception as e:
            logger.error(f"Cache update failed: {e}")
    
    # ==================== STM -> LTM Promotion ====================
    
    def promote_to_ltm(
        self,
        stm_memory_id: str,
        target_type: MemoryType = MemoryType.EPISODIC_CONVERSATION,
    ) -> Optional[str]:
        """Promote a STM memory to LTM.
        
        Args:
            stm_memory_id: The ID of the STM memory to promote.
            target_type: The LTM type to promote to.
        
        Returns:
            The new LTM memory ID, or None if failed.
        """
        if self.collection is None:
            return None
        
        # Get the STM memory
        stm_memory = self.store.get(stm_memory_id)
        if not stm_memory:
            logger.warning(f"STM memory {stm_memory_id} not found for promotion")
            return None
        
        if stm_memory.memory_tier != MemoryTier.STM:
            logger.warning(f"Memory {stm_memory_id} is not STM, cannot promote")
            return None
        
        # Create new LTM memory
        ltm_id = self.store.store(
            memory_type=target_type,
            content=stm_memory.content,
            user_id=stm_memory.user_id,
            conversation_id=stm_memory.conversation_id,
            importance_score=max(stm_memory.importance_score, 0.6),
            generate_vector=stm_memory.has_embedding,
            metadata={
                **stm_memory.metadata,
                "promoted_from": stm_memory_id,
                "promoted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        
        if ltm_id:
            # Mark original STM as consolidated
            self.store.update(stm_memory_id, {
                "consolidated_into": ltm_id,
            })
            logger.info(f"Promoted STM {stm_memory_id} to LTM {ltm_id}")
        
        return ltm_id
    
    def auto_promote_session(
        self,
        session_id: str,
        importance_threshold: float = IMPORTANCE_PROMOTION_THRESHOLD,
    ) -> list[str]:
        """Automatically promote important STM from a session to LTM.
        
        Args:
            session_id: The session to process.
            importance_threshold: Minimum importance for promotion.
        
        Returns:
            List of promoted LTM memory IDs.
        """
        if self.collection is None:
            return []
        
        # Find STM memories above threshold
        query = {
            "session_id": session_id,
            "memory_tier": MemoryTier.STM.value,
            "memory_type": MemoryType.WORKING.value,
            "importance_score": {"$gte": importance_threshold},
            "consolidated_into": {"$exists": False},
        }
        
        promoted_ids = []
        try:
            stm_memories = list(self.collection.find(query))
            
            for mem in stm_memories:
                ltm_id = self.promote_to_ltm(str(mem["_id"]))
                if ltm_id:
                    promoted_ids.append(ltm_id)
            
            logger.info(f"Auto-promoted {len(promoted_ids)} memories from session {session_id}")
            return promoted_ids
            
        except Exception as e:
            logger.error(f"Auto-promotion failed: {e}")
            return []
    
    # ==================== Memory Consolidation ====================
    
    def consolidate_memories(
        self,
        memory_ids: list[str],
        summary_content: str,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        """Consolidate multiple memories into a summary.
        
        Args:
            memory_ids: List of memory IDs to consolidate.
            summary_content: The summary text.
            user_id: Optional user ID for the summary.
        
        Returns:
            The new summary memory ID, or None if failed.
        """
        if self.collection is None or not memory_ids:
            return None
        
        # Aggregate metadata from source memories
        all_topics = []
        all_keywords = []
        all_entities = []
        
        for mid in memory_ids:
            mem = self.store.get(mid)
            if mem:
                all_topics.extend(mem.metadata.get("topics", []))
                all_keywords.extend(mem.metadata.get("keywords", []))
                all_entities.extend(mem.metadata.get("entities", []))
        
        # Create summary memory
        summary_id = self.store.store(
            memory_type=MemoryType.EPISODIC_SUMMARY,
            content=summary_content,
            user_id=user_id,
            importance_score=0.7,
            generate_vector=True,
            metadata={
                "source_memory_ids": memory_ids,
                "source_count": len(memory_ids),
                "topics": list(set(all_topics))[:10],
                "keywords": list(set(all_keywords))[:15],
                "entities": all_entities[:10],
                "consolidated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        
        if summary_id:
            # Mark source memories as consolidated
            for mid in memory_ids:
                self.store.update(mid, {"consolidated_into": summary_id})
            
            logger.info(f"Consolidated {len(memory_ids)} memories into {summary_id}")
        
        return summary_id
    
    # ==================== Maintenance ====================
    
    def run_maintenance(self, user_id: Optional[str] = None) -> dict[str, Any]:
        """Run maintenance tasks on the memory system.
        
        Args:
            user_id: Optional user to run maintenance for.
        
        Returns:
            Dictionary with maintenance results.
        """
        results = {
            "expired_cleaned": 0,
            "decay_updated": 0,
            "promoted": 0,
            "ready_for_consolidation": 0,
        }
        
        if self.collection is None:
            return results
        
        try:
            # Clean expired STM (handled by TTL index, but double-check)
            now = datetime.now(timezone.utc)
            expired = self.collection.delete_many({
                "memory_tier": MemoryTier.STM.value,
                "expires_at": {"$lt": now.isoformat()},
            })
            results["expired_cleaned"] = expired.deleted_count
            
            # Update decay scores for LTM
            ltm_query = {"memory_tier": MemoryTier.LTM.value}
            if user_id:
                ltm_query["$or"] = [{"user_id": user_id}, {"is_shared": True}]
            
            ltm_memories = list(self.collection.find(ltm_query).limit(500))
            
            for mem in ltm_memories:
                new_decay = self._calculate_decay(mem)
                old_decay = mem.get("decay_score", DEFAULT_DECAY_SCORE)
                
                if abs(new_decay - old_decay) > 0.05:
                    self.collection.update_one(
                        {"_id": mem["_id"]},
                        {"$set": {"decay_score": new_decay}}
                    )
                    results["decay_updated"] += 1
            
            # Count memories ready for consolidation
            consolidation_query = {
                "memory_tier": MemoryTier.LTM.value,
                "memory_type": MemoryType.EPISODIC_CONVERSATION.value,
                "consolidated_into": {"$exists": False},
                "decay_score": {"$lt": 0.3},
            }
            results["ready_for_consolidation"] = self.collection.count_documents(consolidation_query)
            
            logger.info(f"Maintenance complete: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Maintenance failed: {e}")
            return results
    
    def _calculate_decay(self, memory_doc: dict) -> float:
        """Calculate decay score for a memory."""
        timestamp = memory_doc.get("timestamp")
        if not timestamp:
            return DEFAULT_DECAY_SCORE
        
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except:
                return DEFAULT_DECAY_SCORE
        
        now = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        
        age_days = (now - timestamp).days
        
        # Base decay: 50% after 1 year
        base_decay = max(0.0, 1.0 - (age_days / 365.0) * 0.5)
        
        # Adjust by importance
        importance = memory_doc.get("importance_score", DEFAULT_IMPORTANCE_SCORE)
        decay = base_decay * (0.5 + importance * 0.5)
        
        # Adjust by access count
        access_count = memory_doc.get("access_count", 0)
        access_factor = 1.0 - min(access_count / 100.0, 0.3)
        decay *= access_factor
        
        return max(0.0, min(1.0, decay))
    
    # ==================== Working Memory Management ====================
    
    def add_to_working_memory(
        self,
        content: str,
        role: str,
        user_id: Optional[str],
        session_id: str,
        conversation_id: Optional[str] = None,
        importance_score: float = DEFAULT_IMPORTANCE_SCORE,
    ) -> Optional[str]:
        """Add a message to working memory.
        
        Args:
            content: The message content.
            role: user/assistant.
            user_id: The user ID.
            session_id: The current session ID.
            conversation_id: Optional conversation ID.
            importance_score: Initial importance.
        
        Returns:
            The working memory ID, or None if failed.
        """
        return self.store.store(
            memory_type=MemoryType.WORKING,
            content=content,
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            importance_score=importance_score,
            expires_in_seconds=DEFAULT_STM_TTL_SECONDS,
            generate_vector=importance_score >= 0.6,
            metadata={"role": role},
            role=role,
        )
    
    def get_working_memory_context(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        limit: int = 20,
    ) -> str:
        """Get working memory as formatted context string.
        
        Args:
            session_id: The session ID.
            user_id: Optional user filter.
            limit: Max messages to include.
        
        Returns:
            Formatted context string.
        """
        return self.retrieval.get_context_for_prompt(
            user_id=user_id,
            session_id=session_id,
            max_working=limit,
        )
    
    # ==================== Knowledge Extraction ====================
    
    def extract_knowledge(
        self,
        content: str,
        user_id: Optional[str] = None,
        source_memory_id: Optional[str] = None,
    ) -> Optional[str]:
        """Extract and store knowledge from content.
        
        Args:
            content: The content to extract knowledge from.
            user_id: Optional user ID.
            source_memory_id: Optional source memory reference.
        
        Returns:
            The knowledge memory ID, or None if failed.
        """
        # This is a placeholder - in a full implementation,
        # you would use an LLM to extract facts/knowledge
        # For now, just store the content as semantic knowledge
        
        return self.store.store(
            memory_type=MemoryType.SEMANTIC_KNOWLEDGE,
            content=content,
            user_id=user_id,
            importance_score=0.7,
            generate_vector=True,
            metadata={
                "source_memory_id": source_memory_id,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    
    # ==================== Entity Memory ====================
    
    def update_entity_memory(
        self,
        entity_name: str,
        entity_type: str,
        context: str,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        """Update or create entity memory.
        
        Args:
            entity_name: The entity name.
            entity_type: person/place/project/etc.
            context: Context about the entity.
            user_id: Optional user ID.
        
        Returns:
            The entity memory ID, or None if failed.
        """
        if self.collection is None:
            return None
        
        # Check if entity already exists
        existing = self.collection.find_one({
            "memory_type": MemoryType.SHARED_ENTITY.value,
            "metadata.entity_name": {"$regex": f"^{entity_name}$", "$options": "i"},
        })
        
        now = datetime.now(timezone.utc)
        
        if existing:
            # Update existing entity
            self.collection.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "content": context,
                        "last_accessed": now.isoformat(),
                        "metadata.last_mentioned": now.isoformat(),
                    },
                    "$inc": {"metadata.mention_count": 1},
                }
            )
            return str(existing["_id"])
        else:
            # Create new entity memory
            return self.store.store(
                memory_type=MemoryType.SHARED_ENTITY,
                content=context,
                user_id=user_id,
                is_shared=True,
                importance_score=0.6,
                generate_vector=True,
                metadata={
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "mention_count": 1,
                    "last_mentioned": now.isoformat(),
                },
            )







