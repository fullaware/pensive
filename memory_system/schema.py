# MongoDB schema definitions
"""MongoDB schema and collection definitions."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId


# ===== COLLECTION NAMES =====
COLLECTION_FACTS = "facts"
COLLECTION_EPISODIC = "episodic_memories"
COLLECTION_TASKS = "tasks"
COLLECTION_TIME_TRACKING = "time_tracking"
COLLECTION_REMINDERS = "reminders"
COLLECTION_SYSTEM_PROMPTS = "system_prompts"


# ===== SCHEMA DEFINITIONS =====

class FactSchema:
    """Schema for semantic memory facts with version tracking."""

    @staticmethod
    def create(
        category: str,
        key: str,
        value: Any,
        confidence: float = 1.0,
        metadata: Optional[Dict] = None,
        version: int = 1,
        embedding: Optional[List[float]] = None,
    ) -> Dict:
        """Create a new fact document."""
        now = datetime.now(timezone.utc)
        doc = {
            "type": "fact",
            "category": category,
            "key": key,
            "value": value,
            "confidence": confidence,
            "version": version,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {},
        }
        if embedding is not None:
            doc["embedding"] = embedding
        return doc

    @staticmethod
    def update(fact_id: str, updates: Dict, increment_version: bool = True) -> Dict:
        """Create an update document for a fact.

        Args:
            fact_id: The fact ID (not used in this method, kept for compatibility)
            updates: Fields to update
            increment_version: Whether to increment the version number

        Returns:
            MongoDB update document
        """
        from copy import deepcopy
        update_doc = deepcopy(updates)
        update_doc["updated_at"] = datetime.now(timezone.utc)
        
        # Build proper MongoDB update document
        result = {"$set": update_doc}
        if increment_version:
            result["$inc"] = {"version": 1}
        return result


class EpisodicMemorySchema:
    """Schema for episodic memories (conversation history, events)."""

    @staticmethod
    def create(
        session_id: str,
        role: str,
        content: str,
        embedding: List[float],
        event_type: str = "conversation",
        context: Optional[Dict] = None,
    ) -> Dict:
        """Create a new episodic memory document."""
        return {
            "type": "episodic",
            "session_id": session_id,
            "role": role,
            "content": content,
            "embedding": embedding,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc),
            "context": context or {},
        }

    @staticmethod
    def update(memory_id: str, updates: Dict) -> Dict:
        """Create an update document for an episodic memory."""
        updates["updated_at"] = datetime.now(timezone.utc)
        return {"$set": updates}


class TaskSchema:
    """Schema for tasks and projects."""

    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_BLOCKED = "blocked"
    STATUS_COMPLETED = "completed"

    PRIORITY_LOW = "low"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"

    @staticmethod
    def create(
        title: str,
        description: str,
        status: str = STATUS_PENDING,
        priority: str = PRIORITY_MEDIUM,
        due_date: Optional[datetime] = None,
        assigned_to: Optional[List[str]] = None,
        progress: int = 0,
        tags: Optional[List[str]] = None,
    ) -> Dict:
        """Create a new task document."""
        now = datetime.now(timezone.utc)
        return {
            "type": "task",
            "title": title,
            "description": description,
            "status": status,
            "priority": priority,
            "due_date": due_date,
            "created_at": now,
            "updated_at": now,
            "assigned_to": assigned_to or ["user", "ai"],
            "progress": progress,
            "tags": tags or [],
            "dependencies": [],
        }

    @staticmethod
    def update(task_id: str, updates: Dict) -> Dict:
        """Create an update document for a task."""
        updates["updated_at"] = datetime.now(timezone.utc)
        return {"$set": updates}


class TimeTrackingSchema:
    """Schema for time tracking records."""

    @staticmethod
    def create(
        task_id: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
    ) -> Dict:
        """Create a new time tracking record."""
        record = {
            "type": "time_tracking",
            "task_id": task_id,
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": 0,
        }
        if description:
            record["description"] = description
        return record

    @staticmethod
    def end_tracking(record_id: str, end_time: datetime, description: Optional[str] = None) -> Dict:
        """Create an update to end a time tracking record."""
        # Calculate duration
        # This would be done in the application logic
        updates = {"end_time": end_time}
        if description:
            updates["description"] = description
        return {"$set": updates}


class ReminderSchema:
    """Schema for reminders and alerts."""

    STATUS_PENDING = "pending"
    STATUS_TRIGGERED = "triggered"
    STATUS_CANCELLED = "cancelled"

    @staticmethod
    def create(
        message: str,
        trigger_time: datetime,
        related_task_id: Optional[str] = None,
        status: str = STATUS_PENDING,
    ) -> Dict:
        """Create a new reminder document."""
        return {
            "type": "reminder",
            "message": message,
            "trigger_time": trigger_time,
            "status": status,
            "related_task_id": related_task_id,
            "notified": False,
            "created_at": datetime.now(timezone.utc),
        }

    @staticmethod
    def update(reminder_id: str, updates: Dict) -> Dict:
        """Create an update document for a reminder."""
        updates["updated_at"] = datetime.now(timezone.utc)
        return {"$set": updates}


class SystemPromptSchema:
    """Schema for system prompts."""

    TYPE_DEFAULT = "default"
    TYPE_USER_PREFERENCE = "user_preference"
    TYPE_CONTEXT = "context"

    @staticmethod
    def create(
        name: str,
        prompt: str,
        prompt_type: str = TYPE_DEFAULT,
        version: int = 1,
        active: bool = True,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """Create a new system prompt document."""
        return {
            "type": "system_prompt",
            "name": name,
            "prompt": prompt,
            "type": prompt_type,
            "version": version,
            "active": active,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    @staticmethod
    def update(prompt_id: str, updates: Dict) -> Dict:
        """Create an update document for a system prompt."""
        updates["updated_at"] = datetime.now(timezone.utc)
        return {"$set": updates}