# Task Management Module
"""Task management for projects and to-do items."""
from datetime import datetime
from typing import List, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, TaskSchema


class TaskManager:
    """Manager for tasks and projects."""

    def __init__(self):
        self.collection: AsyncIOMotorCollection = db.get_collection("tasks")

    async def create_task(
        self,
        title: str,
        description: str,
        status: str = TaskSchema.STATUS_PENDING,
        priority: str = TaskSchema.PRIORITY_MEDIUM,
        due_date: Optional[datetime] = None,
        assigned_to: Optional[List[str]] = None,
        progress: int = 0,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a new task.

        Args:
            title: Task title
            description: Task description
            status: Initial status (pending, in_progress, blocked, completed)
            priority: Priority level (low, medium, high, urgent)
            due_date: Optional due date
            assigned_to: List of assignees (user, ai, etc.)
            progress: Progress percentage (0-100)
            tags: List of tags for categorization

        Returns:
            The created task's ObjectId as string
        """
        task_doc = TaskSchema.create(
            title=title,
            description=description,
            status=status,
            priority=priority,
            due_date=due_date,
            assigned_to=assigned_to,
            progress=progress,
            tags=tags,
        )
        result = await self.collection.insert_one(task_doc)
        return str(result.inserted_id)

    async def get_task(self, task_id: str) -> Optional[Dict]:
        """Get a task by ID.

        Args:
            task_id: Task ObjectId as string

        Returns:
            Task document or None if not found
        """
        from bson import ObjectId

        try:
            task = await self.collection.find_one({"_id": ObjectId(task_id)})
            return task
        except Exception:
            return None

    async def list_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        due_before: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List tasks with optional filters.

        Args:
            status: Filter by status
            priority: Filter by priority
            due_before: Filter tasks due before this date
            limit: Maximum number of tasks to return

        Returns:
            List of task documents
        """
        query = {}
        if status:
            query["status"] = status
        if priority:
            query["priority"] = priority
        if due_before:
            query["due_date"] = {"$lt": due_before}

        cursor = self.collection.find(query).limit(limit)
        tasks = await cursor.to_list(length=limit)
        return tasks

    async def update_task(self, task_id: str, updates: Dict) -> bool:
        """Update a task.

        Args:
            task_id: Task ObjectId as string
            updates: Dictionary of fields to update

        Returns:
            True if task was updated, False otherwise
        """
        from bson import ObjectId

        update_doc = TaskSchema.update(task_id, updates)
        result = await self.collection.update_one(
            {"_id": ObjectId(task_id)}, update_doc
        )
        return result.modified_count > 0

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: Task ObjectId as string

        Returns:
            True if task was deleted, False otherwise
        """
        from bson import ObjectId

        result = await self.collection.delete_one({"_id": ObjectId(task_id)})
        return result.deleted_count > 0

    async def get_due_tasks(self, before: datetime) -> List[Dict]:
        """Get tasks due before a given date.

        Args:
            before: Get tasks due before this date

        Returns:
            List of task documents
        """
        cursor = self.collection.find({"due_date": {"$lt": before}})
        tasks = await cursor.to_list(length=None)
        return tasks

    async def get_urgent_tasks(self) -> List[Dict]:
        """Get urgent priority tasks.

        Returns:
            List of urgent task documents
        """
        cursor = self.collection.find({"priority": TaskSchema.PRIORITY_URGENT})
        tasks = await cursor.to_list(length=None)
        return tasks

    async def get_overdue_tasks(self) -> List[Dict]:
        """Get overdue tasks (due date in the past).

        Returns:
            List of overdue task documents
        """
        now = datetime.now(timezone.utc)
        cursor = self.collection.find(
            {"due_date": {"$lt": now, "$ne": None}, "status": {"$ne": "completed"}}
        )
        tasks = await cursor.to_list(length=None)
        return tasks