# Memory Compression Module
"""Memory compression for archiving and compressing old episodic memories."""
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, COLLECTION_EPISODIC


class MemoryCompression:
    """Manager for memory compression and archiving."""

    def __init__(self):
        self.episodic_collection = db.get_collection(COLLECTION_EPISODIC)
        self.compressed_collection = db.get_collection("compressed_memories")
        self.archived_collection = db.get_collection("archived_memories")

    async def create_compressed_summary(
        self,
        title: str,
        content: str,
        source_event_ids: List[str],
        created_at: Optional[datetime] = None,
    ) -> str:
        """Create a compressed summary of multiple episodic memories.
        
        Args:
            title: Summary title
            content: Compressed content
            source_event_ids: List of original event IDs
            created_at: Optional creation timestamp
            
        Returns:
            Compressed memory ObjectId as string
        """
        doc = {
            "type": "compressed",
            "title": title,
            "content": content,
            "source_event_ids": source_event_ids,
            "created_at": created_at or datetime.now(timezone.utc),
        }
        
        result = await self.compressed_collection.insert_one(doc)
        return str(result.inserted_id)

    async def archive_old_memories(
        self,
        days_old: int = 30,
    ) -> int:
        """Archive episodic memories older than specified days.
        
        Args:
            days_old: Age threshold in days
            
        Returns:
            Number of memories archived
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
        
        # Find memories to archive
        cursor = self.episodic_collection.find({
            "timestamp": {"$lt": cutoff},
            "archived": {"$ne": True},
        })
        
        memories_to_archive = await cursor.to_list(length=None)
        
        for memory in memories_to_archive:
            # Copy to archived collection
            doc = dict(memory)
            doc["archived_at"] = datetime.now(timezone.utc)
            
            await self.archived_collection.insert_one(doc)
            
            # Mark as archived in original collection
            await self.episodic_collection.update_one(
                {"_id": memory["_id"]},
                {"$set": {
                    "archived": True,
                    "archived_at": datetime.now(timezone.utc),
                    "archive_reason": f"older than {days_old} days",
                }}
            )
        
        return len(memories_to_archive)

    async def get_archived_memory(self, memory_id: str) -> Optional[Dict]:
        """Get an archived memory by ID.
        
        Args:
            memory_id: Memory ObjectId as string
            
        Returns:
            Archived memory document or None
        """
        doc = await self.archived_collection.find_one({"_id": memory_id})
        
        if not doc:
            # Try original collection
            doc = await self.episodic_collection.find_one({"_id": memory_id})
        
        return doc

    async def search_archived_memories(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict]:
        """Search archived memories by text.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching archived memories
        """
        from bson.regex import Regex
        
        # Basic text search using regex
        query_regex = Regex(query, "i")
        
        match_stage = {
            "$or": [
                {"title": query_regex},
                {"content": query_regex},
                {"event_type": query_regex},
            ]
        }
        
        pipeline = [
            {"$match": match_stage},
            {"$sort": {"created_at": -1}},
            {"$limit": limit},
        ]
        
        cursor = self.archived_collection.aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def get_memory_compression_stats(self) -> Dict:
        """Get memory compression statistics.
        
        Returns:
            Dictionary with compression stats
        """
        total_episodic = await self.episodic_collection.count_documents({})
        
        # Count archived
        archived_count = await self.archived_collection.count_documents({})
        
        # Count compressed
        compressed_count = await self.compressed_collection.count_documents({})
        
        return {
            "total_episodic": total_episodic,
            "archived_count": archived_count,
            "compressed_count": compressed_count,
        }

    async def get_retrieval_success_rate(self, days: int = 30) -> Dict:
        """Get retrieval success rate for recent queries.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dictionary with retrieval statistics
        """
        from memory_system import db as mongo_db
        
        metrics_collection = mongo_db.get_collection("memory_metrics")
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        cursor = metrics_collection.find({
            "timestamp": {"$gte": cutoff},
            "type": "retrieval",
        })
        
        retrievals = await cursor.to_list(length=None)
        
        if not retrievals:
            return {
                "total_retrievals": 0,
                "successful_retrievals": 0,
                "success_rate": 0.0,
            }
        
        successful = sum(1 for r in retrievals if r.get("success", False))
        
        return {
            "total_retrievals": len(retrievals),
            "successful_retrievals": successful,
            "success_rate": successful / len(retrievals) if retrievals else 0.0,
        }

    async def get_hot_vs_cold_memory_breakdown(self) -> Dict:
        """Get breakdown of hot (frequently retrieved) vs cold (rarely retrieved) memories.
        
        Returns:
            Dictionary with hot/cold breakdown
        """
        from memory_system import db as mongo_db
        
        metrics_collection = mongo_db.get_collection("memory_metrics")
        
        # Get hot memories (retrieved at least 5 times)
        hot_cursor = metrics_collection.aggregate([
            {"$group": {
                "_id": "$memory_id",
                "retrieval_count": {"$sum": 1},
            }},
            {"$match": {"retrieval_count": {"$gte": 5}}}
        ])
        
        hot_memories = await hot_cursor.to_list(length=None)
        
        # Get cold memories (never or rarely retrieved)
        cold_cursor = metrics_collection.aggregate([
            {"$group": {
                "_id": "$memory_id",
                "retrieval_count": {"$sum": 1},
            }},
            {"$match": {"retrieval_count": {"$lte": 2}}}
        ])
        
        cold_memories = await cold_cursor.to_list(length=None)
        
        return {
            "hot_memories_count": len(hot_memories),
            "cold_memories_count": len(cold_memories),
            "hot_memory_ids": [m["_id"] for m in hot_memories],
            "cold_memory_ids": [m["_id"] for m in cold_memories],
        }

    async def compress_old_episodic_memories(
        self,
        days_old: int = 90,
    ) -> int:
        """Create compressed summaries of old episodic memories.
        
        Args:
            days_old: Age threshold in days
            
        Returns:
            Number of memories compressed
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
        
        # Find memories to compress
        cursor = self.episodic_collection.find({
            "timestamp": {"$lt": cutoff},
            "archived": {"$ne": True},
        }).sort("timestamp", 1).limit(100)
        
        memories = await cursor.to_list(length=None)
        
        if not memories:
            return 0
        
        # Group by day
        from collections import defaultdict
        
        daily_groups = defaultdict(list)
        for memory in memories:
            day_key = memory.get("timestamp", datetime.now(timezone.utc)).strftime("%Y-%m-%d")
            daily_groups[day_key].append(memory)
        
        compressed_count = 0
        
        for day, memories_in_day in daily_groups.items():
            # Create compressed summary
            title = f"Summary for {day}"
            
            content_lines = []
            for memory in memories_in_day:
                event_type = memory.get("event_type", "unknown")
                content = memory.get("content", "")
                source = memory.get("provenance", {}).get("source", "unknown")
                
                content_lines.append(f"- [{event_type}] {content[:200]}... (source: {source})")
            
            content = "\n".join(content_lines)
            source_ids = [str(m["_id"]) for m in memories_in_day]
            
            await self.create_compressed_summary(
                title=title,
                content=content,
                source_event_ids=source_ids,
            )
            
            # Mark as archived
            for memory in memories_in_day:
                await self.episodic_collection.update_one(
                    {"_id": memory["_id"]},
                    {"$set": {
                        "archived": True,
                        "archive_reason": f"compressed into daily summary for {day}",
                    }}
                )
            
            compressed_count += len(memories_in_day)
        
        return compressed_count


class _MemoryCompressionLazy:
    """Lazy initializer for MemoryCompression to avoid MongoDB connection at import time."""
    
    def __init__(self):
        self._instance: Optional[MemoryCompression] = None
    
    def _initialize(self):
        """Initialize the instance if not already done."""
        if self._instance is None:
            # At this point, MongoDB should be connected by main.py or api
            self._instance = MemoryCompression()
    
    def __getattr__(self, name):
        """Defer to the actual instance."""
        self._initialize()
        return getattr(self._instance, name)


# Global lazy instance
memory_compression = _MemoryCompressionLazy()
