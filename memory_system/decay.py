# Memory Decay Module
"""Memory decay system for confidence decay and expiration handling."""
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, COLLECTION_EPISODIC, COLLECTION_FACTS
import time


class MemoryDecay:
    """Manager for memory decay and expiration."""

    def __init__(self):
        self.facts_collection = db.get_collection(COLLECTION_FACTS)
        self.episodic_collection = db.get_collection(COLLECTION_EPISODIC)

    def calculate_confidence_decay(
        self,
        created_at: datetime,
        current_time: Optional[datetime] = None,
        half_life_days: float = 30.0,
        min_confidence: float = 0.1,
    ) -> float:
        """Calculate decayed confidence based on age.
        
        Uses exponential decay: confidence = initial * e^(-time/half_life)
        
        Args:
            created_at: When the memory was created
            current_time: Current time (defaults to now)
            half_life_days: How many days until confidence halves
            min_confidence: Minimum confidence floor
            
        Returns:
            Decayed confidence score (0-1)
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        
        age_days = (current_time - created_at).total_seconds() / 86400
        
        # Exponential decay
        decay_factor = 2 ** (-age_days / half_life_days)
        decayed_confidence = decay_factor
        
        # Ensure minimum confidence
        return max(min_confidence, decayed_confidence)

    def calculate_confidence_with_decay(
        self,
        initial_confidence: float,
        created_at: datetime,
        current_time: Optional[datetime] = None,
        half_life_days: float = 30.0,
    ) -> float:
        """Calculate final confidence with decay applied.
        
        Args:
            initial_confidence: Original confidence score
            created_at: When the memory was created
            current_time: Current time (defaults to now)
            half_life_days: How many days until confidence halves
            
        Returns:
            Final confidence score
        """
        decay_factor = self.calculate_confidence_decay(
            created_at, current_time, half_life_days
        )
        return initial_confidence * decay_factor

    async def get_expiring_facts(
        self,
        days_until_expiry: int = 7,
        include_expired: bool = False,
    ) -> List[Dict]:
        """Get facts that are about to expire or have expired.
        
        Args:
            days_until_expiry: How many days in advance to notify
            include_expired: Include already expired facts
            
        Returns:
            List of expiring/expired fact documents
        """
        now = datetime.now(timezone.utc)
        threshold_date = now + timedelta(days=days_until_expiry)
        
        query = {
            "temporal.expires_at": {"$ne": None}
        }
        
        if include_expired:
            query["temporal.expires_at"] = {"$lt": threshold_date}
        else:
            query["temporal.expires_at"] = {
                "$gte": now,
                "$lt": threshold_date
            }
        
        cursor = self.facts_collection.find(query).sort("temporal.expires_at", 1)
        return await cursor.to_list(length=None)

    async def get_expired_facts(self) -> List[Dict]:
        """Get all expired facts.
        
        Returns:
            List of expired fact documents
        """
        now = datetime.now(timezone.utc)
        
        query = {
            "temporal.expires_at": {"$ne": None, "$lt": now}
        }
        
        cursor = self.facts_collection.find(query)
        return await cursor.to_list(length=None)

    async def get_low_confidence_facts(
        self,
        threshold: float = 0.5,
        include_archived: bool = False,
    ) -> List[Dict]:
        """Get facts with confidence below threshold.
        
        Args:
            threshold: Confidence threshold
            include_archived: Include archived facts
            
        Returns:
            List of low confidence fact documents
        """
        query = {"confidence": {"$lt": threshold}}
        
        if not include_archived:
            query["archived"] = {"$ne": True}
        
        cursor = self.facts_collection.find(query)
        return await cursor.to_list(length=None)

    async def get_disputed_facts(self) -> List[Dict]:
        """Get facts with disputed status.
        
        Returns:
            List of disputed fact documents
        """
        query = {
            "temporal.conflict_status": "disputed"
        }
        
        cursor = self.facts_collection.find(query)
        return await cursor.to_list(length=None)

    async def update_fact_confidence_decay(
        self,
        fact_id: str,
        half_life_days: float = 30.0,
    ) -> bool:
        """Update a fact's confidence based on decay.
        
        Args:
            fact_id: Fact ObjectId as string
            half_life_days: Half-life in days
            
        Returns:
            True if fact was updated
        """
        from bson import ObjectId
        
        fact = await self.facts_collection.find_one({"_id": ObjectId(fact_id)})
        if not fact:
            return False
        
        decayed_confidence = self.calculate_confidence_with_decay(
            fact.get("confidence", 1.0),
            fact.get("created_at", datetime.now(timezone.utc)),
            half_life_days=half_life_days,
        )
        
        await self.facts_collection.update_one(
            {"_id": ObjectId(fact_id)},
            {"$set": {"confidence": decayed_confidence}}
        )
        
        return True

    async def decay_all_facts(
        self,
        half_life_days: float = 30.0,
    ) -> int:
        """Apply decay to all facts.
        
        Args:
            half_life_days: Half-life in days
            
        Returns:
            Number of facts updated
        """
        cursor = self.facts_collection.find({})
        facts = await cursor.to_list(length=None)
        
        updated_count = 0
        for fact in facts:
            decayed_confidence = self.calculate_confidence_with_decay(
                fact.get("confidence", 1.0),
                fact.get("created_at", datetime.now(timezone.utc)),
                half_life_days=half_life_days,
            )
            
            await self.facts_collection.update_one(
                {"_id": fact["_id"]},
                {"$set": {"confidence": decayed_confidence}}
            )
            updated_count += 1
        
        return updated_count

    async def archive_expired_facts(self) -> int:
        """Archive all expired facts.
        
        Returns:
            Number of facts archived
        """
        expired = await self.get_expired_facts()
        
        archived_count = 0
        for fact in expired:
            await self.facts_collection.update_one(
                {"_id": fact["_id"]},
                {"$set": {"archived": True, "archived_at": datetime.now(timezone.utc)}}
            )
            archived_count += 1
        
        return archived_count

    async def cleanup_expired_memories(self, hours: int = 24) -> int:
        """Archive memories older than specified hours.
        
        Args:
            hours: Age threshold in hours
            
        Returns:
            Number of memories archived
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        query = {
            "created_at": {"$lt": cutoff},
            "archived": {"$ne": True},
        }
        
        # Archive facts
        result = await self.facts_collection.update_many(
            query,
            {"$set": {"archived": True, "archived_at": datetime.now(timezone.utc)}}
        )
        
        return result.modified_count

    async def get_memory_health_stats(self) -> Dict:
        """Get memory health statistics.
        
        Returns:
            Dictionary with decay-related statistics
        """
        # Get total facts
        total_facts = await self.facts_collection.count_documents({})
        
        # Get low confidence facts
        low_confidence = await self.get_low_confidence_facts(threshold=0.5)
        
        # Get expired facts
        expired = await self.get_expired_facts()
        
        # Get disputed facts
        disputed = await self.get_disputed_facts()
        
        # Get expiring facts (within 7 days)
        expiring = await self.get_expiring_facts(days_until_expiry=7)
        
        return {
            "total_facts": total_facts,
            "low_confidence_count": len(low_confidence),
            "expired_count": len(expired),
            "disputed_count": len(disputed),
            "expiring_soon_count": len(expiring),
        }


class _MemoryDecayLazy:
    """Lazy initializer for MemoryDecay to avoid MongoDB connection at import time."""
    
    def __init__(self):
        self._instance: Optional[MemoryDecay] = None
    
    def _initialize(self):
        """Initialize the instance if not already done."""
        if self._instance is None:
            # At this point, MongoDB should be connected by main.py or api
            self._instance = MemoryDecay()
    
    def __getattr__(self, name):
        """Defer to the actual instance."""
        self._initialize()
        return getattr(self._instance, name)


# Global lazy instance
memory_decay = _MemoryDecayLazy()
