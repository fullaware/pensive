# Semantic Memory Module
"""Semantic memory for facts and knowledge storage."""
from typing import List, Dict, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, FactSchema, COLLECTION_FACTS


class SemanticMemory:
    """Semantic memory manager for facts and knowledge."""

    def __init__(self):
        self.collection: AsyncIOMotorCollection = db.get_collection(COLLECTION_FACTS)

    async def add_fact(
        self,
        category: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        metadata: Optional[Dict] = None,
        increment_version: bool = True,
    ) -> str:
        """Add a new fact to semantic memory.

        Args:
            category: Fact category (user, system, preference, etc.)
            key: Unique fact key
            value: Fact value
            confidence: Confidence score (0-1)
            metadata: Additional context
            increment_version: If True and key exists, increment version; if False, always create new version

        Returns:
            The created fact's ObjectId as string
        """
        # Check if fact with same key exists
        existing = await self.get_fact(key)
        
        if existing and increment_version:
            # Increment version and create new fact with incremented version
            new_version = existing.get("version", 1) + 1
            fact_doc = FactSchema.create(
                category=category,
                key=key,
                value=value,
                confidence=confidence,
                metadata=metadata,
                version=new_version,
            )
        else:
            # Create new fact with version 1
            fact_doc = FactSchema.create(
                category=category,
                key=key,
                value=value,
                confidence=confidence,
                metadata=metadata,
            )
        
        result = await self.collection.insert_one(fact_doc)
        return str(result.inserted_id)

    async def get_fact(self, key: str, category: Optional[str] = None) -> Optional[Dict]:
        """Get a fact by key.

        Args:
            key: Fact key
            category: Optional category filter

        Returns:
            Fact document or None if not found
        """
        query = {"key": key}
        if category:
            query["category"] = category

        # Get the latest version of the fact
        fact = await self.collection.find_one(query, sort=[("version", -1)])
        return fact

    async def get_latest_fact_version(self, key: str) -> Optional[Dict]:
        """Get the latest version of a fact by key.

        Args:
            key: Fact key

        Returns:
            Latest version of fact document or None if not found
        """
        query = {"key": key}
        # Get the latest version (highest version number)
        fact = await self.collection.find_one(query, sort=[("version", -1)])
        return fact

    async def update_fact(self, key: str, updates: Dict, increment_version: bool = True) -> bool:
        """Update an existing fact with version tracking.

        This method archives the current version and creates a new version with incremented version number.

        Args:
            key: Fact key to update
            updates: Dictionary of fields to update
            increment_version: Whether to increment the version number (default: True)

        Returns:
            True if fact was updated, False otherwise
        """
        # Get current version
        current = await self.get_fact(key)
        if not current:
            return False

        # Get the collection
        collection = self.collection

        # Create new version with incremented version number
        new_version = current.get("version", 1) + 1
        
        # Update the current version to mark it as archived
        await collection.update_one(
            {"_id": current["_id"]},
            {"$set": {"archived": True, "archived_at": datetime.now(timezone.utc)}}
        )

        # Create new version document
        new_doc = dict(current)
        new_doc["version"] = new_version
        new_doc["archived"] = False
        new_doc["created_at"] = datetime.now(timezone.utc)
        new_doc["updated_at"] = datetime.now(timezone.utc)
        new_doc["metadata"] = current.get("metadata", {})
        new_doc["metadata"]["updated_from"] = str(current["_id"])
        new_doc.update(updates)
        # Remove the _id to allow new insert
        new_doc.pop("_id", None)

        # Insert new version
        result = await collection.insert_one(new_doc)
        return True

    async def delete_fact(self, key: str) -> bool:
        """Delete a fact.

        Args:
            key: Fact key to delete

        Returns:
            True if fact was deleted, False otherwise
        """
        result = await self.collection.delete_one({"key": key})
        return result.deleted_count > 0

    async def delete_facts_by_category(self, category: str) -> List[Dict]:
        """Delete all facts in a category and return them for proof.

        Args:
            category: Category to delete

        Returns:
            List of deleted fact documents
        """
        # First get the facts to be deleted
        cursor = self.collection.find({"category": category})
        facts_to_delete = await cursor.to_list(length=None)

        if not facts_to_delete:
            return []

        # Delete them
        result = await self.collection.delete_many({"category": category})

        return facts_to_delete

    async def delete_facts_by_query(self, query: Dict) -> List[Dict]:
        """Delete facts matching a query and return them for proof.

        Args:
            query: MongoDB query to match facts to delete

        Returns:
            List of deleted fact documents
        """
        # First get the facts to be deleted
        cursor = self.collection.find(query)
        facts_to_delete = await cursor.to_list(length=None)

        if not facts_to_delete:
            return []

        # Delete them
        result = await self.collection.delete_many(query)

        return facts_to_delete

    async def get_facts_by_category(self, category: str) -> List[Dict]:
        """Get all facts in a category.

        Args:
            category: Category to filter by

        Returns:
            List of fact documents
        """
        cursor = self.collection.find({"category": category})
        facts = await cursor.to_list(length=None)
        return facts

    async def get_all_facts(self) -> List[Dict]:
        """Get all facts.

        Returns:
            List of all fact documents
        """
        cursor = self.collection.find({})
        facts = await cursor.to_list(length=None)
        return facts

    async def get_user_name(self) -> Optional[str]:
        """Get the user's name from facts.

        Returns:
            User name or None if not stored
        """
        fact = await self.get_fact("user_name", category="user")
        return fact.get("value") if fact else None

    async def get_user_preferences(self) -> Dict[str, str]:
        """Get all user preferences as a dictionary.

        Returns:
            Dictionary of preference key-value pairs
        """
        facts = await self.get_facts_by_category("user")
        return {f.get("key", ""): f.get("value", "") for f in facts}

    async def get_tech_stack(self) -> Optional[str]:
        """Get the user's preferred tech stack.

        Returns:
            Tech stack string or None if not stored
        """
        fact = await self.get_fact("tech_stack", category="preference")
        return fact.get("value") if fact else None

    async def get_communication_style(self) -> Optional[str]:
        """Get the user's preferred communication style.

        Returns:
            Communication style string or None if not stored
        """
        fact = await self.get_fact("communication_style", category="preference")
        return fact.get("value") if fact else None