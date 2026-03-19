# Temporal Memory Module
"""Temporal indexing and time-based queries for episodic and semantic memories."""
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, COLLECTION_EPISODIC, COLLECTION_FACTS
import time


class TimeRange:
    """Time bucket classifications."""
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


def get_time_bucket(dt: datetime, bucket_type: str = TimeRange.DAY) -> str:
    """Convert a datetime to a time bucket string.
    
    Args:
        dt: The datetime to bucket
        bucket_type: Type of bucket (hour, day, week, month, year)
        
    Returns:
        String representation of the time bucket
    """
    if bucket_type == TimeRange.HOUR:
        return dt.strftime("%Y-%m-%d %H:00")
    elif bucket_type == TimeRange.DAY:
        return dt.strftime("%Y-%m-%d")
    elif bucket_type == TimeRange.WEEK:
        # ISO week date
        iso_cal = dt.isocalendar()
        return f"{iso_cal[0]}-W{iso_cal[1]:02d}"
    elif bucket_type == TimeRange.MONTH:
        return dt.strftime("%Y-%m")
    elif bucket_type == TimeRange.YEAR:
        return dt.strftime("%Y")
    else:
        return dt.strftime("%Y-%m-%d")


def get_time_range_filter(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    bucket_type: Optional[str] = None,
    reference_time: Optional[datetime] = None
) -> Dict:
    """Create a MongoDB filter for time range queries.
    
    Args:
        start_time: Start of time range (inclusive)
        end_time: End of time range (inclusive)
        bucket_type: If provided, filter by specific time bucket
        reference_time: Reference time for relative time calculations
        
    Returns:
        MongoDB filter dictionary
    """
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    
    if bucket_type:
        # Filter by specific time bucket
        bucket_str = get_time_bucket(reference_time, bucket_type)
        return {"timeRange": bucket_str}
    
    filter_dict = {}
    
    if start_time:
        filter_dict["$gte"] = start_time
    if end_time:
        filter_dict["$lte"] = end_time
    
    return filter_dict


def get_relative_time_filter(
    relative_to: str = "now",
    bucket_type: str = TimeRange.WEEK,
    lookback: int = 1
) -> Dict:
    """Create a filter for relative time queries.
    
    Args:
        relative_to: Reference point ("now" or specific datetime)
        bucket_type: Type of time bucket to look back
        lookback: Number of buckets to look back
        
    Returns:
        MongoDB filter dictionary for time range
    """
    if relative_to == "now":
        now = datetime.now(timezone.utc)
    else:
        now = relative_to
    
    # Calculate start time based on lookback
    if bucket_type == TimeRange.HOUR:
        start = now - timedelta(hours=lookback)
    elif bucket_type == TimeRange.DAY:
        start = now - timedelta(days=lookback)
    elif bucket_type == TimeRange.WEEK:
        start = now - timedelta(weeks=lookback)
    elif bucket_type == TimeRange.MONTH:
        # Approximate month as 30 days
        start = now - timedelta(days=lookback * 30)
    elif bucket_type == TimeRange.YEAR:
        start = now - timedelta(days=lookback * 365)
    else:
        start = now - timedelta(days=lookback)
    
    return {"timestamp": {"$gte": start, "$lte": now}}


class TemporalMemory:
    """Temporal memory manager for time-based queries."""

    def __init__(self):
        self.episodic_collection = db.get_collection(COLLECTION_EPISODIC)
        self.facts_collection = db.get_collection(COLLECTION_FACTS)

    async def add_time_bucket_to_event(
        self, event_id: str, bucket_types: List[str] = None
    ) -> bool:
        """Add time bucket fields to an existing event.
        
        Args:
            event_id: Event ObjectId as string
            bucket_types: List of bucket types to add (hour, day, week, month, year)
            
        Returns:
            True if successful
        """
        from bson import ObjectId
        
        event = await self.episodic_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            return False
        
        if bucket_types is None:
            bucket_types = [TimeRange.HOUR, TimeRange.DAY, TimeRange.WEEK, TimeRange.MONTH]
        
        updates = {}
        for bucket_type in bucket_types:
            bucket_str = get_time_bucket(event.get("timestamp", datetime.now(timezone.utc)), bucket_type)
            updates[f"timeRange.{bucket_type}"] = bucket_str
        
        await self.episodic_collection.update_one(
            {"_id": ObjectId(event_id)},
            {"$set": updates}
        )
        return True

    async def add_time_bucket_to_fact(
        self, fact_id: str, bucket_types: List[str] = None
    ) -> bool:
        """Add time bucket fields to an existing fact.
        
        Args:
            fact_id: Fact ObjectId as string
            bucket_types: List of bucket types to add
            
        Returns:
            True if successful
        """
        from bson import ObjectId
        
        fact = await self.facts_collection.find_one({"_id": ObjectId(fact_id)})
        if not fact:
            return False
        
        if bucket_types is None:
            bucket_types = [TimeRange.HOUR, TimeRange.DAY, TimeRange.WEEK, TimeRange.MONTH]
        
        updates = {}
        for bucket_type in bucket_types:
            bucket_str = get_time_bucket(fact.get("created_at", datetime.now(timezone.utc)), bucket_type)
            updates[f"timeRange.{bucket_type}"] = bucket_str
        
        await self.facts_collection.update_one(
            {"_id": ObjectId(fact_id)},
            {"$set": updates}
        )
        return True

    async def search_by_time_range(
        self,
        time_range_type: str = TimeRange.WEEK,
        lookback: int = 1,
        collection: str = COLLECTION_EPISODIC,
        filters: Optional[Dict] = None
    ) -> List[Dict]:
        """Search memories by time range.
        
        Args:
            time_range_type: Type of time bucket (hour, day, week, month)
            lookback: Number of buckets to look back
            collection: Collection to search (episodic or facts)
            filters: Additional MongoDB filters
            
        Returns:
            List of matching documents
        """
        collection_obj = self.episodic_collection if collection == COLLECTION_EPISODIC else self.facts_collection
        
        # Calculate time range
        now = datetime.now(timezone.utc)
        range_filter = get_relative_time_filter(
            relative_to=now,
            bucket_type=time_range_type,
            lookback=lookback
        )
        
        query = {"timestamp": range_filter["$gte"]}
        if filters:
            query.update(filters)
        
        start_time = time.time()
        cursor = collection_obj.find(query).sort("timestamp", -1)
        results = await cursor.to_list(length=None)
        
        duration_ms = (time.time() - start_time) * 1000
        if db._logging_enabled:
            await db.log_query(
                collection,
                "time_range_search",
                {"time_range_type": time_range_type, "lookback": lookback},
                {"count": len(results)},
                duration_ms
            )
        
        return results

    async def get_events_by_day(
        self, date_str: str, event_type: Optional[str] = None
    ) -> List[Dict]:
        """Get all events for a specific day.
        
        Args:
            date_str: Date string in format YYYY-MM-DD
            event_type: Optional event type filter
            
        Returns:
            List of events for the day
        """
        start_of_day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(days=1) - timedelta(seconds=1)
        
        query = {
            "timestamp": {"$gte": start_of_day, "$lte": end_of_day}
        }
        if event_type:
            query["event_type"] = event_type
        
        cursor = self.episodic_collection.find(query).sort("timestamp", 1)
        return await cursor.to_list(length=None)

    async def get_facts_by_day(self, date_str: str) -> List[Dict]:
        """Get all facts created on a specific day.
        
        Args:
            date_str: Date string in format YYYY-MM-DD
            
        Returns:
            List of facts created that day
        """
        start_of_day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(days=1) - timedelta(seconds=1)
        
        query = {
            "created_at": {"$gte": start_of_day, "$lte": end_of_day}
        }
        
        cursor = self.facts_collection.find(query).sort("created_at", -1)
        return await cursor.to_list(length=None)

    async def get_events_by_week(self, year: int, week: int) -> List[Dict]:
        """Get all events for a specific ISO week.
        
        Args:
            year: ISO year
            week: ISO week number (1-53)
            
        Returns:
            List of events for the week
        """
        # Find first day of week
        first_day_of_year = datetime(year, 1, 1, tzinfo=timezone.utc)
        days_to_week = (week - 1) * 7
        start_of_week = first_day_of_year + timedelta(days=days_to_week)
        end_of_week = start_of_week + timedelta(days=7)
        
        query = {
            "timestamp": {"$gte": start_of_week, "$lt": end_of_week}
        }
        
        cursor = self.episodic_collection.find(query).sort("timestamp", 1)
        return await cursor.to_list(length=None)

    async def get_events_by_month(self, year: int, month: int) -> List[Dict]:
        """Get all events for a specific month.
        
        Args:
            year: Year
            month: Month (1-12)
            
        Returns:
            List of events for the month
        """
        start_of_month = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end_of_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_of_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        
        query = {
            "timestamp": {"$gte": start_of_month, "$lt": end_of_month}
        }
        
        cursor = self.episodic_collection.find(query).sort("timestamp", 1)
        return await cursor.to_list(length=None)

    async def get_time_summary(
        self, 
        time_range_type: str = TimeRange.MONTH,
        lookback: int = 3
    ) -> Dict:
        """Get a summary of events across time buckets.
        
        Args:
            time_range_type: Type of time bucket
            lookback: Number of buckets to include
            
        Returns:
            Dictionary with time buckets as keys and event counts as values
        """
        now = datetime.now(timezone.utc)
        buckets = {}
        
        for i in range(lookback, 0, -1):
            bucket_time = now - timedelta(days=i * 30 if time_range_type == TimeRange.MONTH else i)
            bucket_str = get_time_bucket(bucket_time, time_range_type)
            
            # Get count for this bucket
            count = await self.episodic_collection.count_documents({
                "timeRange": {"$exists": True, "$eq": bucket_str}
            })
            
            buckets[bucket_str] = count
        
        return buckets


class _TemporalMemoryLazy:
    """Lazy initializer for TemporalMemory to avoid MongoDB connection at import time."""
    
    def __init__(self):
        self._instance: Optional[TemporalMemory] = None
    
    def _initialize(self):
        """Initialize the instance if not already done."""
        if self._instance is None:
            # At this point, MongoDB should be connected by main.py or api
            self._instance = TemporalMemory()
    
    def __getattr__(self, name):
        """Defer to the actual instance."""
        self._initialize()
        return getattr(self._instance, name)
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._initialize()
        return await self._instance.__aenter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self._initialize()
        return await self._instance.__aexit__(exc_type, exc_val, exc_tb)


# Global lazy instance
temporal_memory = _TemporalMemoryLazy()
