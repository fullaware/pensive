"""Knowledge management models.

Knowledge items are mutable facts that users explicitly ask to remember,
organized by domain and topic. Unlike session memory, knowledge can be
updated and is never auto-purged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class KnowledgeItem(BaseModel):
    """A knowledge item - a mutable fact stored by domain/topic."""
    
    id: Optional[str] = Field(default=None, alias="_id")  # MongoDB ObjectId as string
    user_id: str  # Owner of this knowledge
    domain: str  # e.g., "locations", "preferences", "facts", "contacts"
    topic: str   # e.g., "key_location", "favorite_color", "birthday"
    content: str  # The actual knowledge (e.g., "under the desk")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    model_config = {
        "populate_by_name": True,
    }
    
    def to_mongo_dict(self) -> dict[str, Any]:
        """Convert to MongoDB document format."""
        data = self.model_dump(by_alias=True, exclude={"id"})
        # Convert datetimes to ISO strings
        for field in ["created_at", "updated_at"]:
            if data.get(field):
                data[field] = data[field].isoformat()
        return data
    
    @classmethod
    def from_mongo_dict(cls, data: dict[str, Any]) -> "KnowledgeItem":
        """Create KnowledgeItem from MongoDB document."""
        if data is None:
            raise ValueError("Cannot create KnowledgeItem from None")
        
        # Handle _id
        if "_id" in data:
            data["_id"] = str(data["_id"])
        
        # Handle datetimes
        for field in ["created_at", "updated_at"]:
            if field in data and isinstance(data[field], str):
                data[field] = datetime.fromisoformat(data[field].replace("Z", "+00:00"))
        
        return cls(**data)

