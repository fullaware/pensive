# Automated Memory Manager
"""Background loop for automated memory management, organization, and cleanup."""
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
import asyncio
import time

from memory_system import (
    Config,
    MongoDB,
    db,
    COLLECTION_EPISODIC,
    COLLECTION_FACTS,
    COLLECTION_SYSTEM_PROMPTS,
)
from utils import EmbeddingClient
from memory_system.system_prompts import SystemPromptsManager


class AutomatedMemoryManager:
    """
    Background loop for automated memory management.
    
    Responsibilities:
    - Automatic memory organization and tagging
    - Staleness detection (removing outdated memories)
    - System prompt version limit enforcement (max 5 versions)
    - Priority scoring for memory retrieval
    - Creating tasks for pending questions needing tools
    """

    def __init__(self):
        self.embedding_client = EmbeddingClient()
        self.system_prompts_manager = SystemPromptsManager()
        self.is_running = False
        self.last_cleanup: Optional[datetime] = None
        self.loop_task: Optional[asyncio.Task] = None
        
        # Schedule configuration
        self.cron_expression: str = "0 2 * * *"  # Default: daily at 2 AM UTC
        self.enabled: bool = True
        self.tasks_to_run: List[str] = [
            "system_prompt_versions",
            "stale_memories", 
            "low_confidence_archival",
            "compression",
            "memory_health_metrics"
        ]

    async def start(self, interval_hours: float = 24.0):
        """Start the automated memory management loop.

        Args:
            interval_hours: How often to run cleanup tasks (default: 24 hours)
        """
        self.is_running = True
        print(f"[AutomatedManager] Starting background loop (interval: {interval_hours}h)")

        while self.is_running:
            try:
                # Run all cleanup tasks
                await self.run_cleanup_tasks()

                # Update last cleanup time
                self.last_cleanup = datetime.now(timezone.utc)

                # Wait for next interval (check every minute if stopped)
                check_interval = 60
                total_wait = 0
                while total_wait < (interval_hours * 3600) and self.is_running:
                    await asyncio.sleep(check_interval)
                    total_wait += check_interval

            except Exception as e:
                print(f"[AutomatedManager] Error in cleanup loop: {e}")
                # Wait before retrying
                await asyncio.sleep(60)

    async def stop(self):
        """Stop the automated memory management loop."""
        self.is_running = False
        if self.loop_task:
            self.loop_task.cancel()
            try:
                await self.loop_task
            except asyncio.CancelledError:
                pass

    async def run_cleanup_tasks(
        self, 
        task_names: Optional[List[str]] = None,
        compression_age_days: int = 30,
        staleness_threshold_days: int = 14,
        archive_confidence_threshold: float = 0.3,
        archive_age_days: int = 90
    ):
        """
        Run cleanup and organization tasks.

        Args:
            task_names: Optional list of specific task names to run.
                       If None, runs all configured tasks. If provided,
                       only runs the specified tasks from the configured list.
            compression_age_days: Age threshold for compression (default: 30 days)
            staleness_threshold_days: Age threshold for staleness tagging (default: 14 days)
            archive_confidence_threshold: Confidence threshold for archiving (default: 0.3)
            archive_age_days: Age threshold for archiving (default: 90 days)
        """
        # Determine which tasks to run
        if task_names is None:
            tasks_to_run = self.tasks_to_run
        else:
            # Filter to only run enabled/valid tasks from the provided list
            valid_tasks = set(self.tasks_to_run)
            tasks_to_run = [t for t in task_names if t in valid_tasks]

        if not self.enabled:
            print("[AutomatedManager] Automated memory management is disabled")
            return

        print(f"[AutomatedManager] Running memory cleanup tasks: {tasks_to_run}")

        try:
            # 1. Enforce system prompt version limit
            if "system_prompt_versions" in tasks_to_run:
                await self.enforce_system_prompt_versions(limit=5)

            # 2. Detect and tag stale memories
            if "stale_memories" in tasks_to_run:
                await self.tag_stale_memories(threshold_days=staleness_threshold_days)

            # 3. Archive low-confidence, old memories
            if "low_confidence_archival" in tasks_to_run:
                await self.archive_low_confidence_memories(
                    confidence_threshold=archive_confidence_threshold,
                    age_days=archive_age_days
                )

            # 4. Run compression on old episodic memories
            if "compression" in tasks_to_run:
                await self.run_compression(age_days=compression_age_days)

            # 5. Update memory health metrics
            if "memory_health_metrics" in tasks_to_run:
                await self.update_memory_health_metrics()

            print("[AutomatedManager] Cleanup tasks completed")

        except Exception as e:
            print(f"[AutomatedManager] Error running cleanup tasks: {e}")

    # ===== SYSTEM PROMPT VERSION MANAGEMENT =====

    async def enforce_system_prompt_versions(self, limit: int = 5) -> int:
        """
        Enforce maximum number of system prompt versions.
        Archives older versions beyond the limit.

        Args:
            limit: Maximum number of versions to keep

        Returns:
            Number of versions archived
        """
        print(f"[AutomatedManager] Enforcing system prompt version limit (max {limit})")

        # Get all bootstrap prompts sorted by version (newest first)
        collection = db.get_collection(COLLECTION_SYSTEM_PROMPTS)

        # Find all bootstrap prompts for the 'bootstrap' name
        cursor = collection.find({
            "name": "bootstrap",
            "is_bootstrap": True
        }).sort([("version", -1)])

        all_prompts = await cursor.to_list(length=None)

        archived_count = 0
        for i, prompt in enumerate(all_prompts):
            # Skip the first `limit` versions (keep them)
            if i < limit:
                continue

            # Archive this version
            prompt_id = str(prompt["_id"])
            await collection.update_one(
                {"_id": prompt["_id"]},
                {"$set": {
                    "active": False,
                    "archived_at": datetime.now(timezone.utc),
                    "archive_reason": f"Archived: exceeded version limit (kept {limit} most recent)"
                }}
            )
            archived_count += 1

        if archived_count > 0:
            print(f"[AutomatedManager] Archived {archived_count} old system prompt versions")

        return archived_count

    # ===== STALENESS DETECTION =====

    async def tag_stale_memories(self, threshold_days: int = 14) -> Dict:
        """
        Detect and tag memories that have become stale/outdated.

        Args:
            threshold_days: How many days old before marking as potentially stale

        Returns:
            Statistics about stale memories found
        """
        print(f"[AutomatedManager] Checking for stale memories (>{threshold_days} days old)")

        episodic = db.get_collection(COLLECTION_EPISODIC)
        facts = db.get_collection(COLLECTION_FACTS)

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=threshold_days)

        stale_count = 0

        # Check episodic memories for staleness indicators
        # Look for temporal keywords like "today", "yesterday", "last week" etc.
        cursor = episodic.find({
            "timestamp": {"$lt": cutoff_date},
            "$or": [
                {"content": {"$regex": r"\b(today|yesterday|last week)\b", "$options": "i"}},
                {"metadata.stale_tagged": {"$ne": True}}
            ]
        }).limit(100)

        async for memory in cursor:
            content = memory.get("content", "")
            timestamp = memory.get("timestamp", datetime.now(timezone.utc))

            # Calculate how old this memory is
            age_days = (datetime.now(timezone.utc) - timestamp).days

            # Determine staleness score
            staleness_score = min(1.0, age_days / 90)  # Normalize to 0-1

            # Check if content suggests it's time-sensitive
            time_sensitive_keywords = [
                "today", "yesterday", "tomorrow", "current",
                "now", "latest", "recently", "tonight"
            ]
            is_time_sensitive = any(kw in content.lower() for kw in time_sensitive_keywords)

            if is_time_sensitive:
                staleness_score = max(staleness_score, 0.7)

            # Update memory with stale tag
            await episodic.update_one(
                {"_id": memory["_id"]},
                {"$set": {
                    "metadata.stale_tagged": True,
                    "metadata.staleness_score": staleness_score,
                    "metadata.last_checked": datetime.now(timezone.utc),
                }}
            )
            stale_count += 1

        # Check facts for temporal/conditional content
        cursor = facts.find({
            "created_at": {"$lt": cutoff_date},
            "key": {
                "$regex": r"(location|status|mood|current_\w+)",
                "$options": "i"
            }
        }).limit(100)

        async for fact in cursor:
            key = fact.get("key", "")

            # Some facts naturally expire (location, status, mood)
            should_expire_keys = [
                "current_location", "current_status", "current_mood",
                "today_weather", "current_task"
            ]

            is_temporal_key = any(kw in key.lower() for kw in should_expire_keys)

            if is_temporal_key:
                # Mark as potentially expiring
                await facts.update_one(
                    {"_id": fact["_id"]},
                    {"$set": {
                        "metadata.stale_tagged": True,
                        "temporal.should_expire": True,
                        "temporal.expiry_reason": "time-sensitive fact",
                    }}
                )
                stale_count += 1

        print(f"[AutomatedManager] Tagged {stale_count} potentially stale memories")

        return {
            "tagged_stale": stale_count,
            "threshold_days": threshold_days
        }

    # ===== LOW CONFIDENCE ARCHIVAL =====

    async def archive_low_confidence_memories(
        self,
        confidence_threshold: float = 0.3,
        age_days: int = 90
    ) -> Dict:
        """
        Archive low-confidence memories that are older than threshold.
        Low confidence + old age = high probability of being wrong/outdated.

        Args:
            confidence_threshold: Confidence below this gets archived
            age_days: Age threshold in days

        Returns:
            Statistics about archived memories
        """
        print(f"[AutomatedManager] Archiving low-confidence memories (confidence<{confidence_threshold}, age>{age_days}d)")

        episodic = db.get_collection(COLLECTION_EPISODIC)
        facts = db.get_collection(COLLECTION_FACTS)

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=age_days)
        archived_count = 0

        # Archive low-confidence facts
        cursor = facts.find({
            "confidence": {"$lt": confidence_threshold},
            "created_at": {"$lt": cutoff_date},
            "archived": {"$ne": True}
        })

        async for fact in cursor:
            await facts.update_one(
                {"_id": fact["_id"]},
                {"$set": {
                    "archived": True,
                    "archived_at": datetime.now(timezone.utc),
                    "archive_reason": f"Low confidence ({fact.get('confidence', 0):.2f}) + age > {age_days} days"
                }}
            )
            archived_count += 1

        # Archive low-confidence episodic memories
        cursor = episodic.find({
            "confidence": {"$lt": confidence_threshold},
            "timestamp": {"$lt": cutoff_date},
            "archived": {"$ne": True}
        })

        async for memory in cursor:
            await episodic.update_one(
                {"_id": memory["_id"]},
                {"$set": {
                    "archived": True,
                    "archived_at": datetime.now(timezone.utc),
                    "archive_reason": f"Low confidence ({memory.get('confidence', 0):.2f}) + age > {age_days} days"
                }}
            )
            archived_count += 1

        print(f"[AutomatedManager] Archived {archived_count} low-confidence memories")

        return {
            "archived": archived_count,
            "confidence_threshold": confidence_threshold,
            "age_days": age_days
        }

    # ===== MEMORY COMPRESSION =====

    async def run_compression(self, age_days: int = 30) -> Dict:
        """
        Compress old episodic memories by creating daily summaries.

        Args:
            age_days: Age threshold for compression

        Returns:
            Statistics about compressed memories
        """
        from memory_system import MemoryCompression

        print(f"[AutomatedManager] Running compression on memories older than {age_days} days")

        try:
            compressor = MemoryCompression()
            compressed_count = await compressor.compress_old_episodic_memories(
                days_old=age_days
            )

            print(f"[AutomatedManager] Compressed {compressed_count} old episodic memories")

            return {
                "compressed": compressed_count,
                "age_days": age_days
            }
        except Exception as e:
            print(f"[AutomatedManager] Compression error: {e}")
            return {"error": str(e)}

    # ===== MEMORY HEALTH METRICS =====

    async def update_memory_health_metrics(self) -> Dict:
        """
        Update memory health metrics collection.
        Tracks: retrieval counts, success rates, age distribution.
        """
        from memory_system import MemoryMetrics

        print("[AutomatedManager] Updating memory health metrics")

        try:
            metrics = MemoryMetrics()
            stats = await metrics.get_memory_health_summary()

            print(f"[AutomatedManager] Memory health stats: {stats}")

            return stats
        except Exception as e:
            print(f"[AutomatedManager] Metrics update error: {e}")
            return {"error": str(e)}

    # ===== PRIORITY SCORING HELPERS =====

    async def calculate_memory_priority(
        self,
        memory: Dict,
        collection_type: str = "episodic"
    ) -> Dict:
        """
        Calculate priority score for a memory.

        Returns priority score and breakdown of factors.
        """
        from datetime import datetime

        now = datetime.now(timezone.utc)
        created_at = memory.get("created_at") or memory.get("timestamp") or now

        # Calculate age in days
        if isinstance(created_at, datetime):
            age_days = (now - created_at).total_seconds() / 86400
        else:
            age_days = 0

        # Base confidence from memory
        base_confidence = memory.get("confidence", 0.5)

        # Decay factor (recency matters)
        decay_factor = 2 ** (-age_days / 30)  # Half-life of 30 days

        # Recency score (0-1)
        recency_score = min(1.0, decay_factor)

        # Get retrieval count from metrics
        retrieval_count = memory.get("metadata", {}).get("retrieval_count", 0)

        # Hotness bonus (frequently retrieved = higher priority)
        hotness_bonus = min(0.3, retrieval_count * 0.05)

        # Staleness penalty
        staleness_score = memory.get("metadata", {}).get("staleness_score", 0)
        staleness_penalty = -staleness_score * 0.3

        # Final priority score (0-1)
        priority_score = (
            base_confidence * 0.4 +
            recency_score * 0.3 +
            hotness_bonus +
            staleness_penalty
        )

        priority_score = max(0.0, min(1.0, priority_score))

        return {
            "priority": round(priority_score, 3),
            "factors": {
                "base_confidence": base_confidence,
                "recency_score": round(recency_score, 3),
                "hotness_bonus": hotness_bonus,
                "staleness_penalty": staleness_penalty
            },
            "age_days": round(age_days, 1)
        }

    async def create_pending_task(
        self,
        title: str,
        description: str,
        reason: str = "auto-generated",
        priority: str = "medium",
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Create a pending task (e.g., for questions needing tools/user input).
        """
        from memory_system import TaskManager

        task_manager = TaskManager()

        task_id = await task_manager.create_task(
            title=title,
            description=description,
            status="pending",
            priority=priority,
            tags=tags or ["auto-generated", "pending"]
        )

        print(f"[AutomatedManager] Created pending task: {task_id}")

        return task_id

    # ===== BACKGROUND TASK MONITOR =====

    async def monitor_pending_tasks(self) -> Dict:
        """
        Monitor tasks that have been pending for too long.
        Create reminders for tasks waiting on user input or external tools.

        Returns:
            Statistics about pending tasks
        """
        from time_management import TaskManager

        print("[AutomatedManager] Monitoring pending tasks")

        task_manager = TaskManager()

        # Find tasks that are pending but not updated in 24 hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        pending_tasks = await task_manager.list_tasks(
            status="pending",
            limit=50
        )

        pending_24h = [
            t for t in pending_tasks
            if t.get("created_at", datetime.now(timezone.utc)) < cutoff
        ]

        # Create reminders for old pending tasks
        for task in pending_24h:
            if not task.get("metadata", {}).get("reminder_created"):
                await task_manager.update_task(
                    str(task["_id"]),
                    {
                        "$set": {
                            "metadata.reminder_created": True,
                            "metadata.reminder_count": 1
                        }
                    }
                )

        print(f"[AutomatedManager] Found {len(pending_24h)} pending tasks > 24 hours old")

        return {
            "pending_tasks_total": len(pending_tasks),
            "pending_24h_plus": len(pending_24h)
        }

    # ===== TEMPORAL CONTEXT HELPERS =====

    async def get_time_relative_context(self) -> Dict:
        """Get current time context for memory operations."""
        now = datetime.now(timezone.utc)

        return {
            "now_utc": now.isoformat(),
            "date_formatted": now.strftime("%B %d, %Y at %I:%M %p UTC"),
            "day_of_week": now.strftime("%A"),
            "hour_utc": now.hour,
            "is_business_hours": 9 <= now.hour <= 17,
        }

    # ===== SCHEDULE MANAGEMENT =====

    def is_enabled(self) -> bool:
        """Check if automated memory management is enabled."""
        return self.enabled

    def update_schedule(
        self,
        cron_expression: Optional[str] = None,
        enabled: Optional[bool] = None,
        tasks_to_run: Optional[List[str]] = None
    ) -> Dict:
        """
        Update the schedule configuration for automated memory management.

        Args:
            cron_expression: Cron expression for scheduling (e.g., "0 2 * * *" for daily at 2 AM)
            enabled: Whether to enable/disable automated runs
            tasks_to_run: List of task names to run

        Returns:
            Updated schedule configuration
        """
        if cron_expression is not None:
            self.cron_expression = cron_expression
        if enabled is not None:
            self.enabled = enabled
        if tasks_to_run is not None:
            # Validate task names
            valid_tasks = [
                "system_prompt_versions",
                "stale_memories",
                "low_confidence_archival",
                "compression",
                "memory_health_metrics"
            ]
            invalid_tasks = [t for t in tasks_to_run if t not in valid_tasks]
            if invalid_tasks:
                raise ValueError(f"Invalid task names: {invalid_tasks}. Valid tasks: {valid_tasks}")
            self.tasks_to_run = tasks_to_run

        return {
            "cron_expression": self.cron_expression,
            "enabled": self.enabled,
            "tasks": self.tasks_to_run
        }

    def get_next_run_time(self) -> Optional[datetime]:
        """
        Calculate the next scheduled run time based on cron expression.
        
        For simplicity, if cron expression matches current pattern,
        return next matching time. Returns None if disabled.
        
        Returns:
            Next run datetime or None if disabled
        """
        if not self.enabled:
            return None
        
        try:
            import croniter
            
            now = datetime.now(timezone.utc)
            cron = croniter.croniter(self.cron_expression, now)
            next_run = cron.get_next(datetime)
            
            return next_run.replace(tzinfo=timezone.utc)
        except ImportError:
            # Fallback: simple hourly calculation if croniter not available
            print("[AutomatedManager] croniter not installed, using fallback scheduling")
            return datetime.now(timezone.utc) + timedelta(hours=24)
        except Exception as e:
            print(f"[AutomatedManager] Error calculating next run time: {e}")
            return None
