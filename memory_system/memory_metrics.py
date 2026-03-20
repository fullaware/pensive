# Memory Quality Metrics Module
"""Memory quality metrics for tracking retrieval patterns and health."""
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, COLLECTION_EPISODIC, COLLECTION_FACTS


class MemoryMetrics:
    """Manager for memory quality metrics."""

    def __init__(self):
        self.episodic_collection = db.get_collection(COLLECTION_EPISODIC)
        self.facts_collection = db.get_collection(COLLECTION_FACTS)
        self.metrics_collection = db.get_collection("memory_metrics")

    async def record_retrieval(
        self,
        memory_id: str,
        memory_type: str,
        query: str,
        success: bool = True,
        user_satisfaction: Optional[float] = None,
    ) -> str:
        """Record a memory retrieval event.
        
        Args:
            memory_id: Memory ObjectId as string
            memory_type: "fact" or "episodic"
            query: Query that triggered retrieval
            success: Whether user found what they needed
            user_satisfaction: Optional satisfaction rating (0-1)
            
        Returns:
            The created metric's ObjectId as string
        """
        doc = {
            "type": "retrieval",
            "memory_id": memory_id,
            "memory_type": memory_type,
            "query": query,
            "success": success,
            "user_satisfaction": user_satisfaction,
            "timestamp": datetime.now(timezone.utc),
        }
        
        result = await self.metrics_collection.insert_one(doc)
        
        # Update memory's retrieval count
        update_field = "metrics.retrieval_count"
        if success:
            update_field = "metrics.successful_retrievals"
        
        update_doc = {
            "$inc": {
                "metrics.retrieval_count": 1,
                "metrics.last_retrieved_at": datetime.now(timezone.utc),
            }
        }
        
        if memory_type == "fact":
            await self.facts_collection.update_one(
                {"_id": memory_id},
                update_doc
            )
        else:
            await self.episodic_collection.update_one(
                {"_id": memory_id},
                update_doc
            )
        
        return str(result.inserted_id)

    async def record_search(
        self,
        query: str,
        results_count: int,
        success: bool = True,
    ) -> str:
        """Record a search event.
        
        Args:
            query: Search query
            results_count: Number of results returned
            success: Whether search was successful
            
        Returns:
            The created metric's ObjectId as string
        """
        doc = {
            "type": "search",
            "query": query,
            "results_count": results_count,
            "success": success,
            "timestamp": datetime.now(timezone.utc),
        }
        
        result = await self.metrics_collection.insert_one(doc)
        return str(result.inserted_id)

    async def get_memory_retrieval_stats(self, memory_id: str) -> Dict:
        """Get retrieval statistics for a specific memory.
        
        Args:
            memory_id: Memory ObjectId as string
            
        Returns:
            Dictionary with retrieval statistics
        """
        # Get metrics from the collection
        cursor = self.metrics_collection.find({
            "memory_id": memory_id,
        }).sort("timestamp", -1)
        
        metrics = await cursor.to_list(length=None)
        
        if not metrics:
            return {
                "total_retrievals": 0,
                "successful_retrievals": 0,
                "last_retrieved_at": None,
            }
        
        total = len(metrics)
        successful = sum(1 for m in metrics if m.get("success", False))
        
        return {
            "total_retrievals": total,
            "successful_retrievals": successful,
            "success_rate": successful / total if total > 0 else 0.0,
            "last_retrieved_at": metrics[0].get("timestamp"),
            "history": metrics[:10],  # Last 10 retrievals
        }

    async def get_hot_memories(
        self,
        min_retrieval_count: int = 5,
        memory_type: Optional[str] = None,
    ) -> List[Dict]:
        """Get memories with high retrieval counts (hot memories).
        
        Args:
            min_retrieval_count: Minimum retrieval count
            memory_type: Optional filter by type ("fact" or "episodic")
            
        Returns:
            List of memory documents ordered by retrieval count
        """
        query = {"metrics.retrieval_count": {"$gte": min_retrieval_count}}
        
        if memory_type == "fact":
            collection = self.facts_collection
        elif memory_type == "episodic":
            collection = self.episodic_collection
        else:
            # Return both by aggregating from metrics
            cursor = self.metrics_collection.find({
                "metrics.retrieval_count": {"$gte": min_retrieval_count}
            }).sort("metrics.retrieval_count", -1).limit(50)
            
            results = await cursor.to_list(length=None)
            return [
                {
                    "memory_id": m["memory_id"],
                    "memory_type": m["memory_type"],
                    "retrieval_count": m.get("metrics", {}).get("retrieval_count", 0),
                }
                for m in results
            ]
        
        cursor = collection.find(query).sort("metrics.retrieval_count", -1).limit(50)
        return await cursor.to_list(length=None)

    async def get_cold_memories(
        self,
        max_retrieval_count: int = 1,
        memory_type: Optional[str] = None,
    ) -> List[Dict]:
        """Get memories with low retrieval counts (cold memories).
        
        Args:
            max_retrieval_count: Maximum retrieval count
            memory_type: Optional filter by type
            
        Returns:
            List of memory documents ordered by retrieval count
        """
        query = {"metrics.retrieval_count": {"$lte": max_retrieval_count}}
        
        if memory_type == "fact":
            collection = self.facts_collection
        elif memory_type == "episodic":
            collection = self.episodic_collection
        else:
            cursor = self.metrics_collection.find(query).sort("metrics.retrieval_count", 1)
            
            results = await cursor.to_list(length=None)
            return [
                {
                    "memory_id": m["memory_id"],
                    "memory_type": m["memory_type"],
                    "retrieval_count": m.get("metrics", {}).get("retrieval_count", 0),
                }
                for m in results
            ]
        
        cursor = collection.find(query).sort("metrics.retrieval_count", 1).limit(50)
        return await cursor.to_list(length=None)

    async def get_age_distribution(self) -> Dict[str, int]:
        """Get age distribution of memories.
        
        Returns:
            Dictionary with age buckets and counts
        """
        now = datetime.now(timezone.utc)
        
        # Get fact age distribution
        facts = await self.facts_collection.find({}).to_list(length=None)
        
        age_buckets = {
            "0-7_days": 0,
            "7-30_days": 0,
            "30-90_days": 0,
            "90-180_days": 0,
            "180+_days": 0,
        }
        
        for fact in facts:
            created_at = fact.get("created_at", now)
            # Handle timezone-aware vs naive datetime comparison
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age_days = (now - created_at).days
            
            if age_days <= 7:
                age_buckets["0-7_days"] += 1
            elif age_days <= 30:
                age_buckets["7-30_days"] += 1
            elif age_days <= 90:
                age_buckets["30-90_days"] += 1
            elif age_days <= 180:
                age_buckets["90-180_days"] += 1
            else:
                age_buckets["180+_days"] += 1
        
        return age_buckets

    async def get_search_success_rate(self, days: int = 30) -> Dict:
        """Get search success rate over time period.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dictionary with search success statistics
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        cursor = self.metrics_collection.find({
            "timestamp": {"$gte": cutoff},
            "type": "search",
        })
        
        searches = await cursor.to_list(length=None)
        
        if not searches:
            return {
                "total_searches": 0,
                "successful_searches": 0,
                "success_rate": 0.0,
            }
        
        successful = sum(1 for s in searches if s.get("success", False))
        
        return {
            "total_searches": len(searches),
            "successful_searches": successful,
            "success_rate": successful / len(searches) if searches else 0.0,
        }

    async def get_memory_health_summary(self) -> Dict:
        """Get comprehensive memory health summary.
        
        Returns:
            Dictionary with all memory health metrics
        """
        # Get age distribution
        age_dist = await self.get_age_distribution()
        
        # Get hot memories stats
        hot = await self.get_hot_memories(min_retrieval_count=5)
        
        # Get cold memories stats
        cold = await self.get_cold_memories(max_retrieval_count=1)
        
        # Get search success rate (last 30 days)
        search_stats = await self.get_search_success_rate(days=30)
        
        # Get total counts
        total_facts = await self.facts_collection.count_documents({})
        total_episodic = await self.episodic_collection.count_documents({})
        
        return {
            "total_memories": total_facts + total_episodic,
            "facts_count": total_facts,
            "episodic_count": total_episodic,
            "age_distribution": age_dist,
            "hot_memories_count": len(hot),
            "cold_memories_count": len(cold),
            "search_success_rate": search_stats["success_rate"],
            "total_searches_last_30_days": search_stats["total_searches"],
        }

    async def archive_low_quality_memories(
        self,
        min_retrieval_count: int = 0,
        max_confidence: float = 0.5,
    ) -> int:
        """Archive memories with low quality metrics.
        
        Args:
            min_retrieval_count: Maximum retrieval count for archiving
            max_confidence: Maximum confidence threshold
            
        Returns:
            Number of memories archived
        """
        count = 0
        
        # Archive low retrieval, low confidence facts
        cursor = self.facts_collection.find({
            "metrics.retrieval_count": {"$lte": min_retrieval_count},
            "confidence": {"$lt": max_confidence},
            "archived": {"$ne": True},
        })
        
        facts_to_archive = await cursor.to_list(length=None)
        for fact in facts_to_archive:
            await self.facts_collection.update_one(
                {"_id": fact["_id"]},
                {"$set": {
                    "archived": True,
                    "archived_at": datetime.now(timezone.utc),
                    "metadata.archived_reason": "low_quality",
                }}
            )
            count += 1
        
        return count


class _MemoryMetricsLazy:
    """Lazy initializer for MemoryMetrics to avoid MongoDB connection at import time."""
    
    def __init__(self):
        self._instance: Optional[MemoryMetrics] = None
    
    def _initialize(self):
        """Initialize the instance if not already done."""
        if self._instance is None:
            # At this point, MongoDB should be connected by main.py or api
            self._instance = MemoryMetrics()
    
    def __getattr__(self, name):
        """Defer to the actual instance."""
        self._initialize()
        return getattr(self._instance, name)


# Global lazy instance
memory_metrics = _MemoryMetricsLazy()
