# Time Tracking Module
"""Time tracking for tasks and work sessions."""
from datetime import datetime
from typing import List, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, TimeTrackingSchema


class TimeTracker:
    """Manager for time tracking and work sessions."""

    def __init__(self):
        self.collection: AsyncIOMotorCollection = db.get_collection("time_tracking")

    async def start_tracking(
        self,
        task_id: str,
        description: Optional[str] = None,
        start_time: Optional[datetime] = None,
    ) -> str:
        """Start a new time tracking session.

        Args:
            task_id: Task ID to track time against
            description: Optional description of work being done
            start_time: Optional start time (defaults to now)

        Returns:
            The created tracking record's ObjectId as string
        """
        record_doc = TimeTrackingSchema.create(
            task_id=task_id,
            start_time=start_time or datetime.now(timezone.utc),
            description=description,
        )
        result = await self.collection.insert_one(record_doc)
        return str(result.inserted_id)

    async def end_tracking(
        self,
        record_id: str,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
    ) -> bool:
        """End a time tracking session.

        Args:
            record_id: Tracking record ObjectId as string
            end_time: Optional end time (defaults to now)
            description: Optional final description

        Returns:
            True if tracking was ended, False otherwise
        """
        from bson import ObjectId

        record = await self.collection.find_one({"_id": ObjectId(record_id)})
        if not record:
            return False

        if record.get("end_time"):
            return False  # Already ended

        end = end_time or datetime.now(timezone.utc)
        duration = (end - record["start_time"]).total_seconds()

        updates = {
            "end_time": end,
            "duration_seconds": duration,
            "description": description,
        }
        update_doc = TimeTrackingSchema.end_tracking(record_id, end, description)
        result = await self.collection.update_one(
            {"_id": ObjectId(record_id)}, update_doc
        )
        return result.modified_count > 0

    async def get_active_sessions(self, task_id: Optional[str] = None) -> List[Dict]:
        """Get active (not ended) time tracking sessions.

        Args:
            task_id: Optional task ID to filter by

        Returns:
            List of active session documents
        """
        query = {"end_time": None}
        if task_id:
            query["task_id"] = task_id

        cursor = self.collection.find(query)
        sessions = await cursor.to_list(length=None)
        return sessions

    async def get_sessions_by_task(
        self, task_id: str, start_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Get time tracking sessions for a specific task.

        Args:
            task_id: Task ID to get sessions for
            start_date: Optional date filter

        Returns:
            List of session documents
        """
        query = {"task_id": task_id}
        if start_date:
            query["start_time"] = {"$gte": start_date}

        cursor = self.collection.find(query).sort("start_time", -1)
        sessions = await cursor.to_list(length=None)
        return sessions

    async def get_total_time_for_task(self, task_id: str) -> float:
        """Get total time spent on a task (in seconds).

        Args:
            task_id: Task ID to get total time for

        Returns:
            Total time in seconds, or 0 if no sessions
        """
        sessions = await self.get_sessions_by_task(task_id)
        total_seconds = sum(s.get("duration_seconds", 0) for s in sessions)
        return total_seconds

    async def get_daily_summary(
        self, date: Optional[datetime] = None
    ) -> List[Dict]:
        """Get time tracking summary for a specific date.

        Args:
            date: Date to get summary for (defaults to today)

        Returns:
            List of task summaries with total time spent
        """
        from bson import ObjectId

        if date is None:
            date = datetime.now(timezone.utc)

        start_of_day = datetime(date.year, date.month, date.day)
        end_of_day = datetime(date.year, date.month, date.day, 23, 59, 59)

        pipeline = [
            {
                "$match": {
                    "start_time": {"$gte": start_of_day, "$lt": end_of_day},
                    "end_time": {"$ne": None},
                }
            },
            {
                "$group": {
                    "_id": "$task_id",
                    "total_seconds": {"$sum": "$duration_seconds"},
                    "session_count": {"$sum": 1},
                    "description": {"$first": "$description"},
                }
            },
        ]

        cursor = self.collection.aggregate(pipeline)
        summaries = await cursor.to_list(length=None)
        return summaries

    async def delete_session(self, record_id: str) -> bool:
        """Delete a time tracking session.

        Args:
            record_id: Tracking record ObjectId as string

        Returns:
            True if session was deleted, False otherwise
        """
        from bson import ObjectId

        result = await self.collection.delete_one({"_id": ObjectId(record_id)})
        return result.deleted_count > 0