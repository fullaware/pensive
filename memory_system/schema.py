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
COLLECTION_UNAUTHORIZED_ACCESS = "unauthorized_access"


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
        related_memories: Optional[List[str]] = None,
        source: Optional[str] = None,
        confidence_explanation: Optional[str] = None,
        human_verified: bool = False,
        expires_at: Optional[datetime] = None,
        conflict_status: str = "resolved",
        source_weight: float = 1.0,
    ) -> Dict:
        """Create a new fact document.
        
        Args:
            category: Fact category (user, system, preference, etc.)
            key: Unique fact key
            value: Fact value
            confidence: Confidence score (0-1)
            metadata: Additional context
            version: Version number
            embedding: Optional pre-computed embedding
            related_memories: List of related memory IDs (episodic or facts)
            source: Original source (conversation ID, external API, manual entry)
            confidence_explanation: Why the system is confident about this fact
            human_verified: Whether this fact was verified by a human
            expires_at: Optional expiration date for ephemeral facts
            conflict_status: "resolved", "disputed", or "pending"
            source_weight: Weight for conflict resolution (0-1)
        """
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
            "related_memories": related_memories or [],
            "provenance": {
                "source": source,
                "confidence_explanation": confidence_explanation,
                "human_verified": human_verified,
                "source_weight": source_weight,
            },
            "temporal": {
                "expires_at": expires_at,
                "conflict_status": conflict_status,
            },
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
        role: str,
        content: str,
        embedding: List[float],
        event_type: str = "conversation",
        context: Optional[Dict] = None,
        related_facts: Optional[List[str]] = None,
        source: Optional[str] = None,
    ) -> Dict:
        """Create a new episodic memory document.
        
        Args:
            role: Event role (user, assistant, system)
            content: Event content
            embedding: Vector embedding for the content
            event_type: Type of event
            context: Additional context
            related_facts: List of related fact IDs
            source: Original source (conversation ID)
        """
        now = datetime.now(timezone.utc)
        doc = {
            "type": "episodic",
            "role": role,
            "content": content,
            "embedding": embedding,
            "event_type": event_type,
            "timestamp": now,
            "context": context or {},
            "provenance": {
                "source": source,
                "created_at": now,
            },
            "temporal": {},
            "related_facts": related_facts or [],
            "timeRange": {
                "hour": now.strftime("%Y-%m-%d %H:00"),
                "day": now.strftime("%Y-%m-%d"),
                "week": f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}",
                "month": now.strftime("%Y-%m"),
            },
        }
        return doc

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


class UnauthorizedAccessSchema:
    """Schema for tracking unauthorized Telegram access attempts."""

    @staticmethod
    def create(
        user_id: int,
        username: Optional[str] = None,
        message_text: Optional[str] = None,
        attempt_time: Optional[datetime] = None,
    ) -> Dict:
        """Create a new unauthorized access record.

        Args:
            user_id: Telegram user ID
            username: Telegram username (if available)
            message_text: Content of the message (for context)
            attempt_time: Timestamp of the attempt (defaults to now)
        """
        if attempt_time is None:
            attempt_time = datetime.now(timezone.utc)
        return {
            "type": "unauthorized_access",
            "user_id": user_id,
            "username": username,
            "message_text": message_text,
            "attempt_time": attempt_time,
            "created_at": datetime.now(timezone.utc),
        }


class SystemPromptSchema:
    """Schema for system prompts with version tracking and bootstrap support."""

    TYPE_DEFAULT = "default"
    TYPE_USER_PREFERENCE = "user_preference"
    TYPE_CONTEXT = "context"
    TYPE_BOOTSTRAP = "bootstrap"  # Used for long-term memory persistence

    @staticmethod
    def create(
        name: str,
        prompt: str,
        prompt_type: str = TYPE_DEFAULT,
        version: int = 1,
        active: bool = True,
        metadata: Optional[Dict] = None,
        is_bootstrap: bool = False,
    ) -> Dict:
        """Create a new system prompt document.
        
        Args:
            name: Prompt name/identifier
            prompt: The prompt content
            prompt_type: Type (default, user_preference, context, bootstrap)
            version: Version number (for rollback capability)
            active: Whether prompt is active
            metadata: Additional context
            is_bootstrap: If True, this prompt is used for bootstrapping long-term memory
        """
        return {
            "type": "system_prompt",
            "name": name,
            "prompt": prompt,
            "type": prompt_type,
            "version": version,
            "active": active,
            "metadata": metadata or {},
            "is_bootstrap": is_bootstrap,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    @staticmethod
    def update(prompt_id: str, updates: Dict, increment_version: bool = False) -> Dict:
        """Create an update document for a system prompt.
        
        Args:
            prompt_id: Prompt ObjectId as string (not used, kept for compatibility)
            updates: Fields to update
            increment_version: If True, increment version number for version tracking
        """
        from copy import deepcopy
        update_doc = deepcopy(updates)
        update_doc["updated_at"] = datetime.now(timezone.utc)
        
        # Build proper MongoDB update document
        result = {"$set": update_doc}
        if increment_version:
            result["$inc"] = {"version": 1}
        return result
