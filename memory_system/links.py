# Memory Links Module
"""Memory linking system for bidirectional relationships between facts and episodic memories."""
from typing import List, Dict, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, COLLECTION_EPISODIC, COLLECTION_FACTS
import time


class MemoryLink:
    """Represents a relationship between two memories."""
    
    TYPE_FACT_TO_EPISODIC = "fact_to_episodic"
    TYPE_EPISODIC_TO_FACT = "episodic_to_fact"
    TYPE_FACT_TO_FACT = "fact_to_fact"
    TYPE_EPISODIC_TO_EPISODIC = "episodic_to_episodic"
    
    def __init__(
        self,
        from_id: str,
        from_type: str,
        to_id: str,
        to_type: str,
        link_type: str,
        metadata: Optional[Dict] = None,
    ):
        self.from_id = from_id
        self.from_type = from_type  # "fact" or "episodic"
        self.to_id = to_id
        self.to_type = to_type  # "fact" or "episodic"
        self.link_type = link_type  # Relationship type
        self.metadata = metadata or {}
        self.created_at = datetime.now(timezone.utc)

    def to_document(self) -> Dict:
        """Convert to MongoDB document."""
        return {
            "from_id": self.from_id,
            "from_type": self.from_type,
            "to_id": self.to_id,
            "to_type": self.to_type,
            "link_type": self.link_type,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


class MemoryLinks:
    """Manager for memory links."""

    def __init__(self):
        self.collection = db.get_collection("memory_links")
        self.facts_collection = db.get_collection(COLLECTION_FACTS)
        self.episodic_collection = db.get_collection(COLLECTION_EPISODIC)

    async def create_link(self, link: MemoryLink) -> str:
        """Create a new memory link.
        
        Args:
            link: MemoryLink object
            
        Returns:
            The created link's ObjectId as string
        """
        doc = link.to_document()
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def create_fact_to_episodic_link(self, fact_id: str, episodic_id: str) -> str:
        """Create a link from a fact to an episodic memory.
        
        Args:
            fact_id: Fact ObjectId as string
            episodic_id: Episodic memory ObjectId as string
            
        Returns:
            The created link's ObjectId as string
        """
        link = MemoryLink(
            from_id=fact_id,
            from_type="fact",
            to_id=episodic_id,
            to_type="episodic",
            link_type=MemoryLink.TYPE_FACT_TO_EPISODIC,
            metadata={"source": "auto"},
        )
        return await self.create_link(link)

    async def create_episodic_to_fact_link(self, episodic_id: str, fact_id: str) -> str:
        """Create a link from an episodic memory to a fact.
        
        Args:
            episodic_id: Episodic memory ObjectId as string
            fact_id: Fact ObjectId as string
            
        Returns:
            The created link's ObjectId as string
        """
        link = MemoryLink(
            from_id=episodic_id,
            from_type="episodic",
            to_id=fact_id,
            to_type="fact",
            link_type=MemoryLink.TYPE_EPISODIC_TO_FACT,
            metadata={"source": "auto"},
        )
        return await self.create_link(link)

    async def create_fact_to_fact_link(self, from_fact_id: str, to_fact_id: str) -> str:
        """Create a link between two facts.
        
        Args:
            from_fact_id: Source fact ObjectId as string
            to_fact_id: Target fact ObjectId as string
            
        Returns:
            The created link's ObjectId as string
        """
        link = MemoryLink(
            from_id=from_fact_id,
            from_type="fact",
            to_id=to_fact_id,
            to_type="fact",
            link_type=MemoryLink.TYPE_FACT_TO_FACT,
            metadata={"source": "auto"},
        )
        return await self.create_link(link)

    async def create_episodic_to_episodic_link(self, from_id: str, to_id: str) -> str:
        """Create a link between two episodic memories.
        
        Args:
            from_id: Source episodic memory ObjectId as string
            to_id: Target episodic memory ObjectId as string
            
        Returns:
            The created link's ObjectId as string
        """
        link = MemoryLink(
            from_id=from_id,
            from_type="episodic",
            to_id=to_id,
            to_type="episodic",
            link_type=MemoryLink.TYPE_EPISODIC_TO_EPISODIC,
            metadata={"source": "auto"},
        )
        return await self.create_link(link)

    async def get_related_memories(self, memory_id: str, memory_type: str) -> Dict[str, List[Dict]]:
        """Get all memories related to a given memory.
        
        Args:
            memory_id: Memory ObjectId as string
            memory_type: "fact" or "episodic"
            
        Returns:
            Dictionary with keys: "facts", "episodic", and "links"
        """
        # Find links where this memory is the source
        forward_links = await self.collection.find({
            "from_id": memory_id,
            "from_type": memory_type,
        }).to_list(length=None)
        
        # Find links where this memory is the target
        backward_links = await self.collection.find({
            "to_id": memory_id,
            "to_type": memory_type,
        }).to_list(length=None)
        
        related = {
            "facts": [],
            "episodic": [],
            "links": [],
        }
        
        # Process forward links
        for link in forward_links:
            if link["to_type"] == "fact":
                fact = await self.facts_collection.find_one({"_id": link["to_id"]})
                if fact:
                    related["facts"].append(fact)
            elif link["to_type"] == "episodic":
                event = await self.episodic_collection.find_one({"_id": link["to_id"]})
                if event:
                    related["episodic"].append(event)
            related["links"].append(link)
        
        # Process backward links
        for link in backward_links:
            if link["from_type"] == "fact":
                fact = await self.facts_collection.find_one({"_id": link["from_id"]})
                if fact:
                    related["facts"].append(fact)
            elif link["from_type"] == "episodic":
                event = await self.episodic_collection.find_one({"_id": link["from_id"]})
                if event:
                    related["episodic"].append(event)
            related["links"].append(link)
        
        return related

    async def get_facts_for_episodic(self, episodic_id: str) -> List[Dict]:
        """Get all facts related to an episodic memory.
        
        Args:
            episodic_id: Episodic memory ObjectId as string
            
        Returns:
            List of related fact documents
        """
        links = await self.collection.find({
            "from_id": episodic_id,
            "from_type": "episodic",
            "to_type": "fact",
        }).to_list(length=None)
        
        fact_ids = [link["to_id"] for link in links]
        if not fact_ids:
            return []
        
        facts = await self.facts_collection.find({
            "_id": {"$in": fact_ids}
        }).to_list(length=None)
        
        return facts

    async def get_episodic_for_fact(self, fact_id: str) -> List[Dict]:
        """Get all episodic memories related to a fact.
        
        Args:
            fact_id: Fact ObjectId as string
            
        Returns:
            List of related episodic memory documents
        """
        links = await self.collection.find({
            "from_id": fact_id,
            "from_type": "fact",
            "to_type": "episodic",
        }).to_list(length=None)
        
        episodic_ids = [link["to_id"] for link in links]
        if not episodic_ids:
            return []
        
        events = await self.episodic_collection.find({
            "_id": {"$in": episodic_ids}
        }).to_list(length=None)
        
        return events

    async def get_all_links_for_memory(self, memory_id: str) -> List[Dict]:
        """Get all links involving a memory (both directions).
        
        Args:
            memory_id: Memory ObjectId as string
            
        Returns:
            List of link documents
        """
        links = await self.collection.find({
            "$or": [
                {"from_id": memory_id},
                {"to_id": memory_id}
            ]
        }).to_list(length=None)
        
        return links

    async def delete_link(self, link_id: str) -> bool:
        """Delete a memory link.
        
        Args:
            link_id: Link ObjectId as string
            
        Returns:
            True if link was deleted
        """
        result = await self.collection.delete_one({"_id": link_id})
        return result.deleted_count > 0

    async def delete_links_for_memory(self, memory_id: str) -> int:
        """Delete all links involving a memory.
        
        Args:
            memory_id: Memory ObjectId as string
            
        Returns:
            Number of links deleted
        """
        result = await self.collection.delete_many({
            "$or": [
                {"from_id": memory_id},
                {"to_id": memory_id}
            ]
        })
        return result.deleted_count

    async def get_memory_stats(self) -> Dict:
        """Get statistics about memory links.
        
        Returns:
            Dictionary with link statistics
        """
        total_links = await self.collection.count_documents({})
        
        # Count links by type
        type_counts = await self.collection.aggregate([
            {"$group": {"_id": "$link_type", "count": {"$sum": 1}}}
        ]).to_list(length=None)
        
        # Count unique memories linked
        from_memories = await self.collection.distinct("from_id")
        to_memories = await self.collection.distinct("to_id")
        all_unique_memories = set(from_memories) | set(to_memories)
        
        return {
            "total_links": total_links,
            "links_by_type": {item["_id"]: item["count"] for item in type_counts},
            "unique_memories_linked": len(all_unique_memories),
        }


class _MemoryLinksLazy:
    """Lazy initializer for MemoryLinks to avoid MongoDB connection at import time."""
    
    def __init__(self):
        self._instance: Optional[MemoryLinks] = None
    
    def _initialize(self):
        """Initialize the instance if not already done."""
        if self._instance is None:
            # At this point, MongoDB should be connected by main.py or api
            self._instance = MemoryLinks()
    
    def __getattr__(self, name):
        """Defer to the actual instance."""
        self._initialize()
        return getattr(self._instance, name)


# Global lazy instance
memory_links = _MemoryLinksLazy()
