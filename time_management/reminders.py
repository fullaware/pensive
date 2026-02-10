# Reminder Management Module
"""Reminder and alert system."""
from datetime import datetime
from typing import List, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, ReminderSchema


class ReminderManager:
    """Manager for reminders and alerts."""

    def __init__(self):
        self.collection: AsyncIOMotorCollection = db.get_collection("reminders")

    async def create_reminder(
        self,
        message: str,
        trigger_time: datetime,
        related_task_id: Optional[str] = None,
        status: str = ReminderSchema.STATUS_PENDING,
    ) -> str:
        """Create a new reminder.

        Args:
            message: Reminder message
            trigger_time: When to trigger the reminder
            related_task_id: Optional related task ID
            status: Initial status (pending, triggered, cancelled)

        Returns:
            The created reminder's ObjectId as string
        """
        reminder_doc = ReminderSchema.create(
            message=message,
            trigger_time=trigger_time,
            related_task_id=related_task_id,
            status=status,
        )
        result = await self.collection.insert_one(reminder_doc)
        return str(result.inserted_id)

    async def get_reminder(self, reminder_id: str) -> Optional[Dict]:
        """Get a reminder by ID.

        Args:
            reminder_id: Reminder ObjectId as string

        Returns:
            Reminder document or None if not found
        """
        from bson import ObjectId

        try:
            reminder = await self.collection.find_one({"_id": ObjectId(reminder_id)})
            return reminder
        except Exception:
            return None

    async def list_pending_reminders(self) -> List[Dict]:
        """List all pending reminders.

        Returns:
            List of pending reminder documents
        """
        cursor = self.collection.find(
            {"status": ReminderSchema.STATUS_PENDING}
        ).sort("trigger_time", 1)
        reminders = await cursor.to_list(length=None)
        return reminders

    async def list_overdue_reminders(self) -> List[Dict]:
        """List overdue reminders (trigger time in the past).

        Returns:
            List of overdue reminder documents
        """
        now = datetime.now(timezone.utc)
        cursor = self.collection.find(
            {"trigger_time": {"$lt": now}, "status": ReminderSchema.STATUS_PENDING}
        ).sort("trigger_time", 1)
        reminders = await cursor.to_list(length=None)
        return reminders

    async def trigger_reminder(self, reminder_id: str, notified: bool = True) -> bool:
        """Mark a reminder as triggered.

        Args:
            reminder_id: Reminder ObjectId as string
            notified: Whether to mark as notified

        Returns:
            True if reminder was updated, False otherwise
        """
        from bson import ObjectId

        updates = {
            "status": ReminderSchema.STATUS_TRIGGERED,
            "notified": notified,
        }
        update_doc = {"$set": updates}
        result = await self.collection.update_one(
            {"_id": ObjectId(reminder_id)}, update_doc
        )
        return result.modified_count > 0

    async def cancel_reminder(self, reminder_id: str) -> bool:
        """Cancel a reminder.

        Args:
            reminder_id: Reminder ObjectId as string

        Returns:
            True if reminder was cancelled, False otherwise
        """
        from bson import ObjectId

        updates = {"status": ReminderSchema.STATUS_CANCELLED}
        update_doc = {"$set": updates}
        result = await self.collection.update_one(
            {"_id": ObjectId(reminder_id)}, update_doc
        )
        return result.modified_count > 0

    async def delete_reminder(self, reminder_id: str) -> bool:
        """Delete a reminder.

        Args:
            reminder_id: Reminder ObjectId as string

        Returns:
            True if reminder was deleted, False otherwise
        """
        from bson import ObjectId

        result = await self.collection.delete_one({"_id": ObjectId(reminder_id)})
        return result.deleted_count > 0

    async def get_task_reminders(self, task_id: str) -> List[Dict]:
        """Get reminders for a specific task.

        Args:
            task_id: Task ObjectId as string

        Returns:
            List of reminder documents for the task
        """
        from bson import ObjectId

        cursor = self.collection.find({"related_task_id": task_id})
        reminders = await cursor.to_list(length=None)
        return reminders