# Thematic Memory Module
"""Thematic memory layer for grouping and clustering episodic memories."""
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, COLLECTION_EPISODIC, COLLECTION_FACTS
import time


COLLECTION_THEMATIC = "thematic_memories"


class ThematicMemory:
    """Manager for thematic (clustered) memories."""

    def __init__(self):
        self.collection = db.get_collection(COLLECTION_THEMATIC)
        self.episodic_collection = db.get_collection(COLLECTION_EPISODIC)

    async def create_thematic_summary(
        self,
        title: str,
        description: str,
        related_event_ids: List[str],
        theme: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        category: Optional[str] = None,
    ) -> str:
        """Create a thematic summary of related events.
        
        Args:
            title: Summary title
            description: Summary description
            related_event_ids: List of related episodic memory IDs
            theme: Main theme of this cluster
            start_time: Optional start time of events
            end_time: Optional end time of events
            category: Optional category
            
        Returns:
            The created thematic memory's ObjectId as string
        """
        doc = {
            "type": "thematic",
            "title": title,
            "description": description,
            "theme": theme,
            "category": category,
            "related_events": related_event_ids,
            "start_time": start_time,
            "end_time": end_time,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "provenance": {
                "source": "auto_cluster",
                "event_count": len(related_event_ids),
                "created_by": "ai",
            },
        }
        
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def get_events_for_thematic(self, thematic_id: str) -> List[Dict]:
        """Get all events in a thematic cluster.
        
        Args:
            thematic_id: Thematic memory ObjectId as string
            
        Returns:
            List of related episodic memory documents
        """
        thematic = await self.collection.find_one({"_id": thematic_id})
        if not thematic:
            return []
        
        event_ids = thematic.get("related_events", [])
        if not event_ids:
            return []
        
        from bson import ObjectId
        cursor = self.episodic_collection.find({
            "_id": {"$in": [ObjectId(oid) for oid in event_ids]}
        })
        return await cursor.to_list(length=None)

    async def find_thematic_by_theme(
        self,
        theme: str,
        limit: int = 10,
    ) -> List[Dict]:
        """Find thematic memories by theme.
        
        Args:
            theme: Theme to search for
            limit: Maximum number of results
            
        Returns:
            List of matching thematic memories
        """
        cursor = self.collection.find({
            "theme": theme
        }).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=None)

    async def get_thematic_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        category: Optional[str] = None,
    ) -> List[Dict]:
        """Get thematic memories in a date range.
        
        Args:
            start_date: Start of date range
            end_date: End of date range
            category: Optional category filter
            
        Returns:
            List of matching thematic memories
        """
        query = {
            "start_time": {"$gte": start_date},
            "end_time": {"$lte": end_date},
        }
        
        if category:
            query["category"] = category
        
        cursor = self.collection.find(query).sort("start_time", 1)
        return await cursor.to_list(length=None)

    async def get_thematic_by_month(
        self,
        year: int,
        month: int,
        category: Optional[str] = None,
    ) -> List[Dict]:
        """Get thematic memories for a specific month.
        
        Args:
            year: Year
            month: Month (1-12)
            category: Optional category filter
            
        Returns:
            List of matching thematic memories
        """
        start_of_month = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end_of_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_of_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        
        query = {
            "start_time": {"$gte": start_of_month, "$lt": end_of_month},
        }
        
        if category:
            query["category"] = category
        
        cursor = self.collection.find(query).sort("start_time", 1)
        return await cursor.to_list(length=None)

    async def search_thematic(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict]:
        """Search thematic memories by text query.
        
        Args:
            query: Text query
            category: Optional category filter
            limit: Maximum number of results
            
        Returns:
            List of matching thematic memories
        """
        from bson.regex import Regex
        
        # Basic text search using regex (for simple cases)
        # For production, consider adding MongoDB text index
        query_regex = Regex(query, "i")
        
        match_stage = {
            "$or": [
                {"title": query_regex},
                {"description": query_regex},
                {"theme": query_regex},
            ]
        }
        
        if category:
            match_stage["$and"] = [{"category": category}]
        
        pipeline = [
            {"$match": match_stage},
            {"$sort": {"created_at": -1}},
            {"$limit": limit},
        ]
        
        cursor = self.collection.aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def add_event_to_thematic(
        self,
        thematic_id: str,
        event_id: str,
    ) -> bool:
        """Add an event to an existing thematic cluster.
        
        Args:
            thematic_id: Thematic memory ObjectId as string
            event_id: Event ObjectId as string
            
        Returns:
            True if event was added
        """
        from bson import ObjectId
        
        # Check if event is already in the thematic
        thematic = await self.collection.find_one({"_id": ObjectId(thematic_id)})
        if not thematic:
            return False
        
        if event_id in thematic.get("related_events", []):
            return True  # Already exists
        
        # Add event
        await self.collection.update_one(
            {"_id": ObjectId(thematic_id)},
            {"$push": {"related_events": event_id}}
        )
        
        # Update end time if needed
        event = await self.episodic_collection.find_one({"_id": ObjectId(event_id)})
        if event and event.get("timestamp"):
            current_end = thematic.get("end_time")
            new_end = event.get("timestamp")
            if current_end is None or new_end > current_end:
                await self.collection.update_one(
                    {"_id": ObjectId(thematic_id)},
                    {"$set": {"end_time": new_end}}
                )
        
        return True

    async def remove_event_from_thematic(
        self,
        thematic_id: str,
        event_id: str,
    ) -> bool:
        """Remove an event from a thematic cluster.
        
        Args:
            thematic_id: Thematic memory ObjectId as string
            event_id: Event ObjectId as string
            
        Returns:
            True if event was removed
        """
        result = await self.collection.update_one(
            {"_id": thematic_id},
            {"$pull": {"related_events": event_id}}
        )
        return result.modified_count > 0

    async def create_monthly_thematic(
        self,
        year: int,
        month: int,
        category: Optional[str] = None,
    ) -> Optional[str]:
        """Create a thematic summary for all events in a month.
        
        Args:
            year: Year
            month: Month (1-12)
            category: Optional category filter
            
        Returns:
            Thematic memory ID if created, None if no events found
        """
        start_of_month = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end_of_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_of_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        
        # Get events for this month
        query = {
            "timestamp": {"$gte": start_of_month, "$lt": end_of_month},
        }
        
        if category:
            query["event_type"] = category
        
        cursor = self.episodic_collection.find(query)
        events = await cursor.to_list(length=None)
        
        if not events:
            return None
        
        # Extract unique event types and themes
        event_types = {}
        for event in events:
            event_type = event.get("event_type", "unknown")
            if event_type not in event_types:
                event_types[event_type] = []
            event_types[event_type].append(event)
        
        # Build description
        type_descriptions = []
        for event_type, type_events in event_types.items():
            type_descriptions.append(f"- {len(type_events)} {event_type} events")
        
        # Create thematic summary
        title = f"{datetime(year, month, 1).strftime('%B %Y')} Summary"
        description = f"Summary of all events in {datetime(year, month, 1).strftime('%B %Y')}.\n\n" + "\n".join(type_descriptions)
        
        event_ids = [str(e["_id"]) for e in events]
        
        thematic_id = await self.create_thematic_summary(
            title=title,
            description=description,
            related_event_ids=event_ids,
            theme="monthly_summary",
            start_time=min(e.get("timestamp", end_of_month) for e in events),
            end_time=max(e.get("timestamp", start_of_month) for e in events),
            category="summary",
        )
        
        return thematic_id

    async def get_thematic_stats(self) -> Dict:
        """Get statistics about thematic memories.
        
        Returns:
            Dictionary with thematic memory statistics
        """
        total_thematics = await self.collection.count_documents({})
        
        # Get events by category
        category_counts = await self.collection.aggregate([
            {"$group": {"_id": "$category", "count": {"$sum": 1}}}
        ]).to_list(length=None)
        
        return {
            "total_thematics": total_thematics,
            "by_category": {item["_id"] or "uncategorized": item["count"] for item in category_counts},
        }


class _ThematicMemoryLazy:
    """Lazy initializer for ThematicMemory to avoid MongoDB connection at import time."""
    
    def __init__(self):
        self._instance: Optional[ThematicMemory] = None
    
    def _initialize(self):
        """Initialize the instance if not already done."""
        if self._instance is None:
            # At this point, MongoDB should be connected by main.py or api
            self._instance = ThematicMemory()
    
    def __getattr__(self, name):
        """Defer to the actual instance."""
        self._initialize()
        return getattr(self._instance, name)


# Global lazy instance
thematic_memory = _ThematicMemoryLazy()
