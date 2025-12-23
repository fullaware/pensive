"""Knowledge storage operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo.collection import Collection

from config import logger
from app.knowledge.models import KnowledgeItem


class KnowledgeStore:
    """Manages knowledge items (mutable facts) separate from session memory."""
    
    def __init__(self, collection: Collection):
        """Initialize with MongoDB collection."""
        self.collection = collection
        self._ensure_indexes()
    
    def _ensure_indexes(self) -> None:
        """Ensure required indexes exist."""
        if self.collection is None:
            return
        
        try:
            # Unique index on user_id + domain + topic
            self.collection.create_index(
                [("user_id", 1), ("domain", 1), ("topic", 1)],
                unique=True,
                name="user_domain_topic_idx"
            )
            
            # Index for listing by user and domain
            self.collection.create_index(
                [("user_id", 1), ("domain", 1)],
                name="user_domain_idx"
            )
            
            # Index for search
            self.collection.create_index(
                [("user_id", 1), ("content", "text")],
                name="user_content_text_idx"
            )
            
            logger.info("Knowledge collection indexes ensured")
        except Exception as e:
            logger.error(f"Failed to create knowledge indexes: {e}")
    
    def upsert(
        self,
        user_id: str,
        domain: str,
        topic: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[str]:
        """Create or update a knowledge item.
        
        Args:
            user_id: User who owns this knowledge
            domain: Domain category (e.g., "locations", "preferences")
            topic: Specific topic within domain (e.g., "key_location")
            content: The knowledge content
            metadata: Optional metadata
        
        Returns:
            Knowledge item ID, or None if failed
        """
        if self.collection is None:
            logger.error("Knowledge collection not available")
            return None
        
        try:
            now = datetime.now(timezone.utc)
            
            # Check if item exists
            existing = self.collection.find_one({
                "user_id": user_id,
                "domain": domain,
                "topic": topic,
            })
            
            if existing:
                # Update existing
                update_data = {
                    "content": content,
                    "updated_at": now.isoformat(),
                }
                if metadata:
                    update_data["metadata"] = metadata
                
                self.collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": update_data}
                )
                logger.info(f"Updated knowledge: {user_id}/{domain}/{topic}")
                return str(existing["_id"])
            else:
                # Create new
                item = KnowledgeItem(
                    user_id=user_id,
                    domain=domain,
                    topic=topic,
                    content=content,
                    metadata=metadata or {},
                )
                result = self.collection.insert_one(item.to_mongo_dict())
                logger.info(f"Created knowledge: {user_id}/{domain}/{topic}")
                return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to upsert knowledge: {e}")
            return None
    
    def get(
        self,
        user_id: str,
        domain: str,
        topic: str,
    ) -> Optional[KnowledgeItem]:
        """Get a specific knowledge item."""
        if self.collection is None:
            return None
        
        try:
            doc = self.collection.find_one({
                "user_id": user_id,
                "domain": domain,
                "topic": topic,
            })
            if doc:
                return KnowledgeItem.from_mongo_dict(doc)
            return None
        except Exception as e:
            logger.error(f"Failed to get knowledge: {e}")
            return None
    
    def list(
        self,
        user_id: str,
        domain: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeItem]:
        """List knowledge items, optionally filtered by domain."""
        if self.collection is None:
            return []
        
        try:
            query: dict[str, Any] = {"user_id": user_id}
            if domain:
                query["domain"] = domain
            
            cursor = self.collection.find(query).sort("updated_at", -1).skip(offset).limit(limit)
            docs = list(cursor)
            return [KnowledgeItem.from_mongo_dict(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Failed to list knowledge: {e}")
            return []
    
    def delete(
        self,
        user_id: str,
        domain: str,
        topic: str,
    ) -> bool:
        """Delete a knowledge item."""
        if self.collection is None:
            return False
        
        try:
            result = self.collection.delete_one({
                "user_id": user_id,
                "domain": domain,
                "topic": topic,
            })
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete knowledge: {e}")
            return False
    
    def search(
        self,
        user_id: str,
        query_text: str,
        limit: int = 20,
    ) -> list[KnowledgeItem]:
        """Search knowledge items by content."""
        if self.collection is None:
            return []
        
        try:
            # Use text search if available, otherwise regex
            cursor = self.collection.find({
                "user_id": user_id,
                "content": {"$regex": query_text, "$options": "i"},
            }).limit(limit)
            
            docs = list(cursor)
            return [KnowledgeItem.from_mongo_dict(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Failed to search knowledge: {e}")
            return []
    
    def get_domains(self, user_id: str) -> list[str]:
        """Get all unique domains for a user."""
        if self.collection is None:
            return []
        
        try:
            pipeline = [
                {"$match": {"user_id": user_id}},
                {"$group": {"_id": "$domain"}},
                {"$sort": {"_id": 1}},
            ]
            results = list(self.collection.aggregate(pipeline))
            return [r["_id"] for r in results]
        except Exception as e:
            logger.error(f"Failed to get domains: {e}")
            return []
    
    def count(self, user_id: str, domain: Optional[str] = None) -> int:
        """Count knowledge items."""
        if self.collection is None:
            return 0
        
        try:
            query: dict[str, Any] = {"user_id": user_id}
            if domain:
                query["domain"] = domain
            return self.collection.count_documents(query)
        except Exception as e:
            logger.error(f"Failed to count knowledge: {e}")
            return 0

