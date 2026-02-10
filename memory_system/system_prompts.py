# System Prompts Manager
"""System prompt management and generation."""
from typing import List, Dict, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorCollection
from memory_system import db, SystemPromptSchema
from .config import Config


class SystemPromptsManager:
    """Manager for system prompts and user preferences."""

    def __init__(self):
        self.collection: AsyncIOMotorCollection = db.get_collection("system_prompts")

    async def create_prompt(
        self,
        name: str,
        prompt: str,
        prompt_type: str = SystemPromptSchema.TYPE_DEFAULT,
        version: int = 1,
        active: bool = True,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Create a new system prompt.

        Args:
            name: Prompt name/identifier
            prompt: The prompt content
            prompt_type: Type (default, user_preference, context)
            version: Version number
            active: Whether prompt is active
            metadata: Additional context

        Returns:
            The created prompt's ObjectId as string
        """
        prompt_doc = SystemPromptSchema.create(
            name=name,
            prompt=prompt,
            prompt_type=prompt_type,
            version=version,
            active=active,
            metadata=metadata,
        )
        result = await self.collection.insert_one(prompt_doc)
        return str(result.inserted_id)

    async def get_prompt(self, name: str, active: bool = True) -> Optional[Dict]:
        """Get the latest active prompt by name.

        Args:
            name: Prompt name/identifier
            active: Whether to only get active prompts

        Returns:
            Prompt document or None if not found
        """
        query = {"name": name}
        if active:
            query["active"] = True

        prompt = await self.collection.find_one(
            query, sort=[("version", -1), ("created_at", -1)]
        )
        return prompt

    async def get_all_prompts(self, active: bool = True) -> List[Dict]:
        """Get all active prompts.

        Args:
            active: Whether to only get active prompts

        Returns:
            List of prompt documents
        """
        query = {"active": True} if active else {}
        cursor = self.collection.find(query).sort("created_at", -1)
        prompts = await cursor.to_list(length=None)
        return prompts

    async def update_prompt(self, prompt_id: str, updates: Dict) -> bool:
        """Update a prompt.

        Args:
            prompt_id: Prompt ObjectId as string
            updates: Dictionary of fields to update

        Returns:
            True if prompt was updated, False otherwise
        """
        from bson import ObjectId

        update_doc = SystemPromptSchema.update(prompt_id, updates)
        result = await self.collection.update_one(
            {"_id": ObjectId(prompt_id)}, update_doc
        )
        return result.modified_count > 0

    async def deactivate_prompt(self, prompt_id: str) -> bool:
        """Deactivate a prompt.

        Args:
            prompt_id: Prompt ObjectId as string

        Returns:
            True if prompt was deactivated, False otherwise
        """
        return await self.update_prompt(prompt_id, {"active": False})

    async def activate_prompt(self, prompt_id: str) -> bool:
        """Activate a prompt.

        Args:
            prompt_id: Prompt ObjectId as string

        Returns:
            True if prompt was activated, False otherwise
        """
        return await self.update_prompt(prompt_id, {"active": True})

    # ===== USER PREFERENCE METHODS =====

    async def set_user_preference(
        self, key: str, value: str, category: str = "user"
    ) -> str:
        """Set a user preference as a system prompt.

        Args:
            key: Preference key (e.g., "communication_style", "tech_stack")
            value: Preference value
            category: Category (user, system, etc.)

        Returns:
            The created fact's ObjectId as string
        """
        from memory_system import FactSchema

        fact_doc = FactSchema.create(
            category=category,
            key=key,
            value=value,
            confidence=1.0,
            metadata={"preference": True},
        )
        result = await self.collection.insert_one(fact_doc)
        return str(result.inserted_id)

    async def get_user_preference(self, key: str) -> Optional[str]:
        """Get a user preference value.

        Args:
            key: Preference key

        Returns:
            Preference value or None if not found
        """
        fact = await self.collection.find_one(
            {"type": "fact", "category": "user", "key": key}
        )
        return fact.get("value") if fact else None

    async def get_all_user_preferences(self) -> Dict[str, str]:
        """Get all user preferences.

        Returns:
            Dictionary of preference key-value pairs
        """
        cursor = self.collection.find({"type": "fact", "category": "user"})
        preferences = {}
        async for doc in cursor:
            preferences[doc.get("key", "")] = doc.get("value", "")
        return preferences

    # ===== SYSTEM PROMPT BUILDING =====

    async def build_system_prompt(self, context: Optional[Dict] = None) -> str:
        """Build a complete system prompt from all active prompts.

        Args:
            context: Optional context dictionary for prompt formatting

        Returns:
            Combined system prompt string
        """
        prompts = await self.get_all_prompts(active=True)

        sections = []
        for prompt in prompts:
            prompt_text = prompt.get("prompt", "")
            if context:
                try:
                    prompt_text = prompt_text.format(**context)
                except KeyError:
                    pass  # Skip formatting errors
            sections.append(prompt_text)

        return "\n\n".join(sections)

    async def get_user_preferences_context(self) -> Dict[str, str]:
        """Get user preferences formatted for prompt context.

        Returns:
            Dictionary of preference key-value pairs
        """
        return await self.get_all_user_preferences()